"""Pure diagnostics and two-stage ranking. No candidate-provided PnL."""

from bisect import bisect_right
from dataclasses import dataclass
from math import isfinite, sqrt
from statistics import mean, median, pstdev


@dataclass(frozen=True)
class Quote:
    ts: int
    ordinal: int
    mid: float | None


@dataclass(frozen=True)
class Fill:
    ts: int
    ordinal: int
    side: int
    quantity: float
    price: float
    fee: float
    entry: bool
    forced: bool


@dataclass(frozen=True)
class MetricConfig:
    annualization: float
    risk_free_per_sample: float
    downside_target: float
    ratio_cap: float
    max_quote_age_ns: int
    markout_horizons: dict[str, int] = None

    def __post_init__(self):
        if self.markout_horizons is None:
            object.__setattr__(self, "markout_horizons",
                               {"100ms": 100_000_000, "1s": 1_000_000_000})
        if not self.markout_horizons or len(self.markout_horizons) != len(set(self.markout_horizons)):
            raise ValueError("need at least one unique markout horizon")
        for name, ns in self.markout_horizons.items():
            if not name or type(ns) is not int or ns <= 0:
                raise ValueError("invalid markout horizon")
        if (not all(isfinite(v) for v in (self.annualization, self.risk_free_per_sample,
                                         self.downside_target, self.ratio_cap))
                or self.annualization <= 0 or self.ratio_cap <= 0
                or self.max_quote_age_ns < 0):
            raise ValueError("invalid metric configuration")


def markouts(fills: list[Fill], quotes: list[Quote], horizon_ns: int, max_age_ns: int):
    if horizon_ns <= 0 or max_age_ns < 0:
        raise ValueError("invalid markout horizon/age")
    keys = [(q.ts, q.ordinal) for q in quotes]
    if keys != sorted(keys):
        raise ValueError("quotes must be in replay order")

    def mid_at(ts, ordinal):
        i = bisect_right(keys, (ts, ordinal)) - 1
        if i < 0 or ts - quotes[i].ts > max_age_ns:
            return None
        return quotes[i].mid

    rows = []
    for fill in fills:
        future = mid_at(fill.ts + horizon_ns, float("inf"))
        current = mid_at(fill.ts, fill.ordinal)
        valid = future is not None and current is not None
        value = 10_000 * fill.side * (future - fill.price) / fill.price if valid else None
        rows.append({
            "fill_bps": value,
            "net_fill_bps": value - 10_000 * fill.fee / (fill.quantity * fill.price) if valid else None,
            "mid_move_bps": 10_000 * fill.side * (future - current) / current if valid else None,
            "notional": fill.quantity * fill.price,
        })
    valid_rows = [row for row in rows if row["fill_bps"] is not None]
    notional = sum(row["notional"] for row in valid_rows)
    return {
        "coverage": len(valid_rows) / len(rows) if rows else 0.0,
        "weighted_mean": sum(r["fill_bps"] * r["notional"] for r in valid_rows) / notional if notional else None,
        "median": median(r["fill_bps"] for r in valid_rows) if valid_rows else None,
        "positive_fraction": mean(r["fill_bps"] > 0 for r in valid_rows) if valid_rows else None,
        "rows": rows,
    }


def metrics(equity: list[float], round_trip_pnls: list[float], fills: list[Fill], config: MetricConfig):
    if len(equity) < 2 or any(not isfinite(v) or v <= 0 for v in equity):
        raise ValueError("need at least two positive finite fixed-grid equity samples")
    returns = [b / a - 1 for a, b in zip(equity, equity[1:])]
    excess = [r - config.risk_free_per_sample for r in returns]
    std = pstdev(excess)
    downside = sqrt(mean(min(r - config.downside_target, 0) ** 2 for r in returns))
    def ratio(numerator, denominator):
        if denominator == 0:
            return config.ratio_cap if numerator > 0 else None
        return max(-config.ratio_cap, min(config.ratio_cap, numerator / denominator))
    sharpe = ratio(mean(excess) * sqrt(config.annualization), std) if std else None
    sortino = ratio((mean(returns) - config.downside_target) * sqrt(config.annualization), downside)
    peak = equity[0]
    drawdown = 0.0
    for value in equity:
        peak = max(peak, value)
        drawdown = max(drawdown, 1 - value / peak)
    wins = sum(max(pnl, 0) for pnl in round_trip_pnls)
    losses = -sum(min(pnl, 0) for pnl in round_trip_pnls)
    return {
        "net_pnl": equity[-1] - equity[0],
        "fees": sum(f.fee for f in fills),
        # Includes spread/slippage; adding fees back does not undo execution cost.
        "gross_pnl": equity[-1] - equity[0] + sum(f.fee for f in fills),
        "sharpe": sharpe, "sortino": sortino,
        "max_drawdown": drawdown, "profit_factor": ratio(wins, losses),
        "expectancy": mean(round_trip_pnls) if round_trip_pnls else None,
        "trade_count": len(round_trip_pnls), "fill_count": len(fills),
        "turnover": sum(f.quantity * f.price for f in fills) / equity[0],
    }


@dataclass(frozen=True)
class ScoreConfig:
    min_trades: int
    max_drawdown: float
    max_turnover: float
    min_worst_sharpe: float
    min_markout_coverage: float
    # Names, positive scaling denominators, signed weights. Penalties use negative weights.
    weights: dict[str, float]
    scales: dict[str, float]
    clip: float
    # Markout horizons subject to the coverage gate and ranking vector.
    markout_horizons: tuple[str, ...] = ("100ms", "1s")

    def __post_init__(self):
        if (self.min_trades < 1 or not 0 <= self.max_drawdown <= 1
                or self.max_turnover <= 0 or not isfinite(self.max_turnover)
                or not isfinite(self.min_worst_sharpe)
                or not 0 <= self.min_markout_coverage <= 1
                or not isfinite(self.clip) or self.clip <= 0
                or not self.weights or self.weights.keys() != self.scales.keys()
                or any(not isfinite(v) for v in self.weights.values())
                or any(not isfinite(v) or v <= 0 for v in self.scales.values())
                or not self.markout_horizons or len(set(self.markout_horizons)) != len(self.markout_horizons)):
            raise ValueError("invalid score configuration")


def rank_results(cells: list[dict], complexity: int, config: ScoreConfig):
    violations = []
    for i, cell in enumerate(cells):
        m = cell.get("metrics", {})
        if cell.get("status") != "valid":
            violations.append(f"cell {i}: {cell.get('status')}")
            continue
        checks = {
            "trade_count": m["trade_count"] >= config.min_trades,
            "drawdown": m["max_drawdown"] <= config.max_drawdown,
            "turnover": m["turnover"] <= config.max_turnover,
            "sharpe": m["sharpe"] is not None and m["sharpe"] >= config.min_worst_sharpe,
            "coverage": all(cell["markout"][h]["coverage"] >= config.min_markout_coverage for h in config.markout_horizons),
        }
        violations.extend(f"cell {i}: {name}" for name, passed in checks.items() if not passed)
    if not cells or violations:
        return {"status": "constraint_failed", "violations": violations or ["no evaluation cells"], "fitness": None}
    by_scenario = {}
    for cell in cells:
        by_scenario.setdefault(cell["scenario"], []).append(cell)
    vector = {"complexity": float(complexity)}
    for metric in ("sharpe", "sortino", "profit_factor"):
        values = [[c["metrics"][metric] for c in group] for group in by_scenario.values()]
        vector[f"median_{metric}"] = min(median(v) for v in values) if all(all(x is not None for x in v) for v in values) else None
    vector["worst_sharpe"] = min(c["metrics"]["sharpe"] for c in cells)
    vector["dispersion"] = max(pstdev([c["metrics"]["sharpe"] for c in group]) for group in by_scenario.values())
    vector["drawdown"] = max(c["metrics"]["max_drawdown"] for c in cells)
    for h in config.markout_horizons:
        values = [[c["markout"][h]["weighted_mean"] for c in group] for group in by_scenario.values()]
        vector[f"markout_{h}"] = min(median(v) for v in values) if all(all(x is not None for x in v) for v in values) else None
    if any(name not in vector for name in config.weights):
        raise ValueError("unknown score component")
    if any(vector[name] is None for name in config.weights):
        return {"status": "constraint_failed", "violations": ["undefined ranking metric"], "fitness": None, "vector": vector}
    fitness = sum(weight * max(-config.clip, min(config.clip, vector[name] / config.scales[name]))
                  for name, weight in config.weights.items())
    return {"status": "valid", "violations": [], "fitness": fitness, "vector": vector}
