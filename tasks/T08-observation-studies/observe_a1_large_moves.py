"""A1: where do moves large enough to beat round-trip cost occur? Discovery splits only."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog

from evolution.market_state import EvolutionMarketState
from evolution.spec import FEE_RATE
from analysis.market_regime_report import ALL_INSTRUMENTS, default_split_map

HORIZONS = (1, 5, 15, 30, 60, 240, 1440)
MULTIPLES = (1.0, 2.0, 3.0)
MIN_NS = 60_000_000_000
OUT = Path("outputs/observe-a1")


def load(instrument_id: str) -> pd.DataFrame:
    sm = default_split_map()[instrument_id]
    parts = [(sm.original_folds_root, s) for s in sm.original_folds] + [
        (sm.supplemental_root, s) for s in sm.supplemental_splits
    ]
    rows = []
    for root, split in parts:
        cat = ParquetDataCatalog(root / split / instrument_id)
        for item in cat.query(EvolutionMarketState, identifiers=[instrument_id]):
            s = item.data
            rows.append((s.ts_event, s.close, s.best_bid, s.best_ask, s.spread_bps))
    df = pd.DataFrame(rows, columns=["ts", "close", "bid", "ask", "spread_bps"])
    df = df.drop_duplicates("ts").sort_values("ts").set_index("ts")
    df["mid"] = np.where((df.bid > 0) & (df.ask > 0), (df.bid + df.ask) / 2, df.close)
    df["day"] = pd.to_datetime((df.index - MIN_NS) // 86_400_000_000_000, unit="D").strftime("%Y-%m-%d")
    return df


def fwd_return(df: pd.DataFrame, h: int) -> pd.Series:
    target = df.index + h * MIN_NS
    fut = df["mid"].reindex(target).to_numpy()
    return pd.Series(fut / df["mid"].to_numpy() - 1.0, index=df.index) * 1e4  # bps


def episodes(r: pd.Series, h: int, thr: float) -> pd.Series:
    """Greedy non-overlapping events: first qualifying minute, then skip h minutes."""
    hits = r[r.abs() >= thr].index.to_numpy()
    keep, nxt = [], -1
    for t in hits:
        if t >= nxt:
            keep.append(t)
            nxt = t + h * MIN_NS
    return r.loc[keep]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    regime = json.loads(Path("outputs/evolution-diagnostics/market-regime-map.json").read_text())
    summary, by_regime, day_conc = [], [], []
    for inst in sys.argv[1:] or ALL_INSTRUMENTS:
        df = load(inst)
        spread = float(df.spread_bps[df.spread_bps > 0].median())
        cost = 2 * FEE_RATE * 1e4 + spread  # taker in + out, plus one spread crossing
        labels = {d["day"]: (d.get("regime_label") or d.get("status")) for d in regime["instruments"][inst]["daily"]}
        df["regime"] = df.day.map(labels).fillna("unmapped")
        print(f"{inst}: rows={len(df)} days={df.day.nunique()} median_spread={spread:.3f}bps cost={cost:.2f}bps")
        for h in HORIZONS:
            r = fwd_return(df, h).dropna()
            a = r.abs()
            row = {
                "instrument": inst, "h_min": h, "n": len(r), "cost_bps": round(cost, 2),
                "abs_p50": a.median(), "abs_p90": a.quantile(0.9), "abs_p99": a.quantile(0.99),
                "p50_over_cost": a.median() / cost, "abs_mean": a.mean(), "breakeven_hit": 0.5 + cost / (2 * a.mean()),
            }
            for m in MULTIPLES:
                thr = m * cost
                ev = episodes(r, h, thr)
                row[f"share_ge_{m:g}x"] = float((a >= thr).mean())
                row[f"episodes_ge_{m:g}x"] = len(ev)
                row[f"episodes_per_day_{m:g}x"] = len(ev) / df.day.nunique()
                row[f"up_share_{m:g}x"] = float((ev > 0).mean()) if len(ev) else np.nan
            summary.append(row)
            # regime + day concentration at 2x cost
            thr = 2 * cost
            ev = episodes(r, h, thr)
            evd = df.loc[ev.index, ["day", "regime"]].assign(r=ev.values)
            minutes = df.loc[r.index].groupby("regime").size()
            for reg, n_min in minutes.items():
                sub = evd[evd.regime == reg]
                by_regime.append({
                    "instrument": inst, "h_min": h, "regime": reg, "days": df[df.regime == reg].day.nunique(),
                    "episodes_2x": len(sub), "episodes_per_day": len(sub) / max(1, df[df.regime == reg].day.nunique()),
                    "up_share": float((sub.r > 0).mean()) if len(sub) else np.nan,
                })
            per_day = evd.groupby("day").size().sort_values(ascending=False)
            ndays = df.day.nunique()
            top = per_day.head(max(1, round(0.1 * ndays))).sum()
            day_conc.append({
                "instrument": inst, "h_min": h, "episodes_2x": len(evd), "days_with_event": len(per_day),
                "total_days": ndays, "top10pct_days_share": top / len(evd) if len(evd) else np.nan,
            })
    pd.DataFrame(summary).to_csv(OUT / "summary.csv", index=False)
    pd.DataFrame(by_regime).to_csv(OUT / "by_regime.csv", index=False)
    pd.DataFrame(day_conc).to_csv(OUT / "day_concentration.csv", index=False)
    pd.set_option("display.width", 250, "display.max_columns", 40, "display.float_format", "{:.3f}".format)
    print(pd.DataFrame(summary).drop(columns=["n"]))
    print(pd.DataFrame(day_conc))


if __name__ == "__main__":
    main()
