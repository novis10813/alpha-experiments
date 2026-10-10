"""A2: reverse event study on discovery splits only.

Line 1 (direction): signed trailing features vs forward 240-min mid return.
Line 2 (magnitude): trailing features vs P(|forward 30/60-min return| >= 2x round-trip cost).

Preregistered screen (fixed before looking at results):
- Blocks = discovery_1..5 + supplemental (6 chronological blocks).
- A feature is a "candidate" only if its pooled effect sign repeats in >= 5 of 6 blocks
  on >= 2 of 3 instruments. Everything else is noise at this sample size.
All features use only rows with ts_event <= t (trailing windows on a full minute grid; gaps -> NaN).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog

from evolution.market_state import EvolutionMarketState
from evolution.spec import FEE_RATE
from analysis.market_regime_report import ALL_INSTRUMENTS, default_split_map

MIN_NS = 60_000_000_000
OUT = Path("outputs/observe-a2")
DIR_H = 240
MAG_HS = (30, 60)
SIGNED = ["ret_15", "ret_60", "ret_240", "flow_15", "flow_60", "obi_15", "obi_60", "loc_240", "trend_240"]
UNSIGNED = ["rv_15", "rv_60", "rv_240", "rv_ratio", "relvol_15", "reltrades_15", "abs_ret_60", "abs_flow_15",
            "abs_obi_15", "spread_15", "range_compress"]


def load(inst: str) -> pd.DataFrame:
    sm = default_split_map()[inst]
    parts = [(sm.original_folds_root, s, s) for s in sm.original_folds] + [
        (sm.supplemental_root, s, "supplemental") for s in sm.supplemental_splits
    ]
    rows = []
    for root, split, block in parts:
        for item in ParquetDataCatalog(root / split / inst).query(EvolutionMarketState, identifiers=[inst]):
            s = item.data
            rows.append((s.ts_event, block, s.close, s.high, s.low, s.best_bid, s.best_ask, s.spread_bps, s.volume,
                         s.buy_volume, s.sell_volume, s.trade_count, s.depth10_obi_mean))
    df = pd.DataFrame(rows, columns=["ts", "block", "close", "high", "low", "bid", "ask", "spread_bps", "volume",
                                     "buy_vol", "sell_vol", "trades", "obi"])
    df = df.drop_duplicates("ts").set_index("ts").sort_index()
    grid = np.arange(df.index[0], df.index[-1] + MIN_NS, MIN_NS)
    df = df.reindex(grid)  # full minute grid so rolling windows never bridge gaps
    df["mid"] = np.where((df.bid > 0) & (df.ask > 0), (df.bid + df.ask) / 2, df.close)
    return df


def features(df: pd.DataFrame) -> pd.DataFrame:
    f = pd.DataFrame(index=df.index)
    m = df.mid
    lr = np.log(m).diff()
    roll = lambda s, w, fn: getattr(s.rolling(w, min_periods=w), fn)()
    for w in (15, 60, 240):
        f[f"ret_{w}"] = (m / m.shift(w) - 1) * 1e4
        f[f"rv_{w}"] = roll(lr, w, "std") * 1e4
    for w in (15, 60):
        f[f"flow_{w}"] = roll(df.buy_vol - df.sell_vol, w, "sum") / roll(df.volume, w, "sum")
        f[f"obi_{w}"] = roll(df.obi, w, "mean")
    hi, lo = roll(df.high, 240, "max"), roll(df.low, 240, "min")
    f["loc_240"] = (m - lo) / (hi - lo)
    f["trend_240"] = (m - m.shift(240)) / roll(m.diff().abs(), 240, "sum")  # signed efficiency
    f["rv_ratio"] = f.rv_15 / f.rv_240
    f["relvol_15"] = roll(df.volume, 15, "sum") / (roll(df.volume, 1440, "sum") / 96)
    f["reltrades_15"] = roll(df.trades, 15, "sum") / (roll(df.trades, 1440, "sum") / 96)
    f["abs_ret_60"] = f.ret_60.abs()
    f["abs_flow_15"] = f.flow_15.abs()
    f["abs_obi_15"] = f.obi_15.abs()
    f["spread_15"] = roll(df.spread_bps, 15, "mean")
    f["range_compress"] = (roll(df.high, 60, "max") - roll(df.low, 60, "min")) / (
        (roll(df.high, 1440, "max") - roll(df.low, 1440, "min")) / 24)
    f["hour"] = ((df.index // MIN_NS) // 60) % 24
    f["block"] = df.block
    return f


def fwd(df: pd.DataFrame, h: int) -> pd.Series:
    """Forward mid return in bps; df rows may be non-contiguous, so align by timestamp."""
    fut = df.mid.reindex(df.index + h * MIN_NS).to_numpy()
    return pd.Series((fut / df.mid.to_numpy() - 1) * 1e4, index=df.index)


def spearman(x: pd.Series, y: pd.Series) -> float:
    ok = x.notna() & y.notna()
    return float(np.corrcoef(x[ok].rank(), y[ok].rank())[0, 1]) if ok.sum() > 100 else np.nan


def auc(score: pd.Series, label: pd.Series) -> float:
    ok = score.notna() & label.notna()
    s, l = score[ok], label[ok].astype(bool)
    npos, nneg = l.sum(), (~l).sum()
    if npos < 20 or nneg < 20:
        return np.nan
    r = s.rank()
    return float((r[l].sum() - npos * (npos + 1) / 2) / (npos * nneg))


def consistency(pooled: float, per_block: list[float], center: float) -> int:
    return sum(1 for v in per_block if np.isfinite(v) and np.sign(v - center) == np.sign(pooled - center))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    dir_rows, mag_rows, strat_rows, hour_rows = [], [], [], []
    for inst in ALL_INSTRUMENTS:
        df = load(inst)
        cost = 2 * FEE_RATE * 1e4 + float(df.spread_bps[df.spread_bps > 0].median())
        f = features(df)
        valid = df.close.notna()
        f, df = f[valid], df[valid]
        blocks = [b for b in f.block.unique() if isinstance(b, str)]
        # Line 1: direction at 240 min
        y = fwd(df, DIR_H)
        for feat in SIGNED:
            x = f[feat]
            pooled = spearman(x, y)
            per = [spearman(x[f.block == b], y[f.block == b]) for b in blocks]
            ok = x.notna() & y.notna()
            dec = pd.qcut(x[ok].rank(method="first"), 10, labels=False)
            top, bot = y[ok][dec == 9].mean(), y[ok][dec == 0].mean()
            dir_rows.append({"instrument": inst[:3], "feature": feat, "ic": pooled,
                             "blocks_same_sign": consistency(pooled, per, 0.0), "n_blocks": len(blocks),
                             "top_dec_bps": top, "bot_dec_bps": bot, "long_short_half_bps": (top - bot) / 2,
                             "cost_bps": cost, "per_block_ic": [round(v, 3) for v in per]})
        # Line 2: magnitude at 30/60 min
        for h in MAG_HS:
            r = fwd(df, h)
            big = (r.abs() >= 2 * cost).where(r.notna())
            base = float(big.mean())
            for feat in UNSIGNED:
                x = f[feat]
                pooled = auc(x, big)
                per = [auc(x[f.block == b], big[f.block == b]) for b in blocks]
                ok = x.notna() & big.notna()
                dec = pd.qcut(x[ok].rank(method="first"), 10, labels=False)
                mag_rows.append({"instrument": inst[:3], "h_min": h, "feature": feat, "auc": pooled,
                                 "blocks_same_side": consistency(pooled, per, 0.5), "n_blocks": len(blocks),
                                 "base_rate": base, "top_dec_rate": float(big[ok][dec == 9].mean()),
                                 "lift_top_dec": float(big[ok][dec == 9].mean()) / base,
                                 "per_block_auc": [round(v, 3) for v in per]})
                # incremental over vol clustering: AUC within rv_60 quintiles
                if feat != "rv_60":
                    q = pd.qcut(f.rv_60.rank(method="first"), 5, labels=False)
                    within = [auc(x[q == k], big[q == k]) for k in range(5)]
                    strat_rows.append({"instrument": inst[:3], "h_min": h, "feature": feat,
                                       "auc_within_rv60_quintile_mean": float(np.nanmean(within)),
                                       "per_quintile": [round(v, 3) for v in within]})
            hr = pd.DataFrame({"hour": f.hour, "big": big}).dropna().groupby("hour").big.mean() / base
            for hour, lift in hr.items():
                hour_rows.append({"instrument": inst[:3], "h_min": h, "hour_utc": int(hour), "lift": lift})
        print(f"{inst}: rows={len(df)} blocks={blocks} cost={cost:.2f}bps", flush=True)
    pd.DataFrame(dir_rows).to_csv(OUT / "direction_240.csv", index=False)
    pd.DataFrame(mag_rows).to_csv(OUT / "magnitude.csv", index=False)
    pd.DataFrame(strat_rows).to_csv(OUT / "magnitude_within_vol.csv", index=False)
    pd.DataFrame(hour_rows).to_csv(OUT / "magnitude_by_hour.csv", index=False)


if __name__ == "__main__":
    main()
