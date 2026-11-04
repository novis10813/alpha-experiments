"""T09 vol-gate-v1: absolute volatility estimators as a trading gate. Discovery splits only.

Definitions (agreed before the run):
- Data: BTC, ETH, BNB discovery_1..5, the August supplement 2026-07-25..2026-08-28 (end exclusive, block
  "august") and the existing supplemental splits (block "supplemental"): 7 chronological blocks. Minute-close mid.
- Estimators, all absolute, per-minute volatility sigma in bps, using rows <= t only:
  rv_15, rv_60, rv_240 = std of 1-min log mid returns over the trailing n minutes (all n required);
  park_60 = Parkinson estimator from minute trade high/low over the trailing 60 min (>= 45 minutes required);
  ewma_60 = EWMA of squared 1-min log returns, half-life 60 min, reset after gaps of >= 60 missing minutes;
  season = sqrt of the median, over the previous 7 UTC days (>= 3 required), of the mean squared 1-min return
  in the same UTC hour (hours with >= 45 returns). Uses no data from the current day.
- Expected move x = sigma * sqrt(h) in bps, h in {30, 60, 240} min.
- Targets over (t, t+h], no missing minute allowed: |r_h| = |mid(t+h) / mid(t) - 1|, R = max path |excursion|.
- Sample: every minute where all six estimators and the target exist (one common sample per instrument and h).
- Costs per instrument: c_v1 = 2 x 10 bps + median spread, c_v2 = 2 x 5 bps + median spread (draft perp taker).
- M1 mean |r_h| and mean R per x bin. M2 net = mean |r_h| - c. M3 breakeven hit rate p* = 1/2 + c / (2 mean |r_h|),
  which assumes a direction signal whose accuracy does not depend on move size.
- M4 daily Spearman IC of sigma with |r_h| per UTC day (>= 720 samples): mean, std, IR = mean / std, share > 0.
- M5 gate curve: for threshold X on x, coverage = share of minutes with x >= X, and M1-M3 on those minutes.
- x bins: fixed edges EDGES (bps), same for all instruments. CIs: 5-95% day bootstrap, B = 1000, seed 0.
- O3 cross-instrument: daily partial Spearman IC of the source instrument's sigma with the target's |r_h|,
  controlling the target's own sigma (rank residuals), same estimator on both sides; heat map of mean |r_h| on
  coarse bins of own x by source x.
- O4: z = R / x and |r_h| / x quantiles per x bin, and P(R >= k x) for k = 1, 2, 3.
- No pass/fail check. Conclusions are read from per-block curves, CIs, and IC IR.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from evolution.spec import FEE_RATE
from analysis.discovery_minutes import load
from analysis.market_regime_report import ALL_INSTRUMENTS, default_split_map

RUN_ID = "vol-gate-v1"
OUT = Path("outputs/T09-vol-excursion") / RUN_ID
AUGUST = (("discovery_supplemental_20260725_20260828", "august"),)
HS = (30, 60, 240)
V2_FEE_BPS = 5.0
ESTIMATORS = ("rv_15", "rv_60", "rv_240", "park_60", "ewma_60", "season")
EDGES = (0, 10, 15, 20, 25, 30, 40, 50, 70, 100, np.inf)
COARSE = (0, 15, 25, 40, np.inf)
GATE_X = tuple(np.arange(5.0, 150.1, 2.5))
MIN_DAY_N = 720
B, SEED = 1000, 0
QS = (0.1, 0.25, 0.5, 0.75, 0.9)
MIN_NS = 60_000_000_000


def estimators(df: pd.DataFrame) -> pd.DataFrame:
    lr = np.log(df.mid).diff()
    out = {f"rv_{n}": lr.rolling(n, min_periods=n).std() * 1e4 for n in (15, 60, 240)}
    hl = np.log(df.high / df.low) ** 2 / (4 * np.log(2))
    out["park_60"] = np.sqrt(hl.rolling(60, min_periods=45).mean()) * 1e4
    gap = df.mid.isna()
    run_len = gap.groupby((gap != gap.shift()).cumsum()).transform("size")
    seg = (gap & (run_len >= 60)).cumsum()
    ew = (lr ** 2).groupby(seg).transform(lambda s: s.ewm(halflife=60, min_periods=60, ignore_na=True).mean())
    out["ewma_60"] = np.sqrt(ew) * 1e4
    ts = pd.to_datetime(df.index, utc=True)
    hourly = (lr ** 2).groupby([ts.floor("D"), ts.hour]).agg(["mean", "count"])
    hourly = hourly["mean"].where(hourly["count"] >= 45).unstack()  # day x hour
    hourly = hourly.reindex(pd.date_range(hourly.index.min(), hourly.index.max(), freq="D"))
    prior = hourly.shift(1).rolling(7, min_periods=3).median()
    out["season"] = pd.Series(np.sqrt(prior.stack().reindex(list(zip(ts.floor("D"), ts.hour))).to_numpy()) * 1e4,
                              index=df.index)
    return pd.DataFrame(out, index=df.index)


def targets(mid: np.ndarray, h: int) -> tuple[np.ndarray, np.ndarray]:
    n = len(mid)
    abs_r, R = np.full(n, np.nan), np.full(n, np.nan)
    path = (sliding_window_view(mid[1:], h) / mid[: n - h, None] - 1) * 1e4
    ok = ~np.isnan(path).any(axis=1)
    abs_r[: n - h] = np.where(ok, np.abs(path[:, -1]), np.nan)
    R[: n - h] = np.where(ok, np.abs(path).max(axis=1), np.nan)
    return abs_r, R


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.corrcoef(pd.Series(a).rank().to_numpy(), pd.Series(b).rank().to_numpy())[0, 1])


def partial_spearman(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> float:
    rx, ry, rz = (pd.Series(v).rank().to_numpy() for v in (x, y, z))
    A = np.column_stack([np.ones_like(rz), rz])
    ex = rx - A @ np.linalg.lstsq(A, rx, rcond=None)[0]
    ey = ry - A @ np.linalg.lstsq(A, ry, rcond=None)[0]
    return float(np.corrcoef(ex, ey)[0, 1])


def ic_summary(daily: pd.Series) -> dict:
    d = daily.dropna()
    return {"n_days": len(d), "ic_mean": d.mean(), "ic_std": d.std(), "ic_ir": d.mean() / d.std(),
            "ic_pos_share": (d > 0).mean()}


def boot_ci(s: pd.DataFrame, mask: np.ndarray, day_codes: np.ndarray, W: np.ndarray) -> tuple[float, float]:
    sums = np.bincount(day_codes[mask], weights=s.abs_r.to_numpy()[mask], minlength=W.shape[1])
    cnts = np.bincount(day_codes[mask], minlength=W.shape[1])
    with np.errstate(invalid="ignore", divide="ignore"):
        means = (W @ sums) / (W @ cnts)
    return tuple(np.nanquantile(means, (0.05, 0.95))) if np.isfinite(means).any() else (np.nan, np.nan)


def econ(abs_r_mean: float, cost: dict[str, float]) -> dict:
    row = {}
    for c, v in cost.items():
        row[f"net_{c}"] = abs_r_mean - v
        row[f"p_star_{c}"] = 0.5 + v / (2 * abs_r_mean) if abs_r_mean > 0 else np.nan
    return row


def manifest_hashes(inst: str) -> dict[str, str]:
    sm = default_split_map()[inst]
    parts = [(sm.original_folds_root, s) for s in sm.original_folds] + [
        (sm.supplemental_root, s) for s in (*sm.supplemental_splits, *(a for a, _ in AUGUST))
    ]
    return {f"{root}/{split}/{inst}/manifest.json": hashlib.sha256((root / split / inst / "manifest.json").read_bytes())
            .hexdigest() for root, split in parts}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    run = {"run_id": RUN_ID, "command": " ".join(["python", "-m", "tasks.T09-vol-excursion.observe_vol_gate", *sys.argv[1:]]),
           "edges_bps": [str(e) for e in EDGES], "coarse_edges_bps": [str(e) for e in COARSE], "bootstrap": B,
           "seed": SEED, "min_day_n": MIN_DAY_N, "instruments": {}}
    frames, costs = {}, {}
    for inst in ALL_INSTRUMENTS:
        df = load(inst, extra=AUGUST)
        est = estimators(df)
        spread = float(df.spread_bps[df.spread_bps > 0].median())
        costs[inst] = {"v1": 2 * FEE_RATE * 1e4 + spread, "v2": 2 * V2_FEE_BPS + spread}
        frames[inst] = pd.concat([df[["block", "mid", "high", "low"]], est], axis=1)
        frames[inst].to_parquet(OUT / f"features_{inst[:3]}.parquet")
        run["instruments"][inst] = {"median_spread_bps": spread, "cost_bps": costs[inst],
                                    "blocks": [b for b in pd.unique(df.block) if isinstance(b, str)],
                                    "minutes_with_mid": int(df.mid.notna().sum()),
                                    "manifests_sha256": manifest_hashes(inst)}
        print(f"{inst}: minutes={int(df.mid.notna().sum())} spread={spread:.2f}bps", flush=True)

    rng = np.random.default_rng(SEED)
    ic_rows, bin_rows, gate_rows, z_rows, o3_rows, heat_rows = [], [], [], [], [], []
    for inst in ALL_INSTRUMENTS:
        f, cost = frames[inst], costs[inst]
        blocks = run["instruments"][inst]["blocks"]
        for h in HS:
            abs_r, R = targets(f.mid.to_numpy(dtype=float), h)
            s = f[["block", *ESTIMATORS]].assign(abs_r=abs_r, R=R)
            s = s[s[list(ESTIMATORS)].notna().all(axis=1) & s.abs_r.notna()].copy()
            s["day"] = pd.to_datetime(s.index, utc=True).floor("D")
            day_codes, days = pd.factorize(s.day)
            W = rng.multinomial(len(days), np.full(len(days), 1 / len(days)), size=B).astype(float)
            full_days = s.groupby("day").size().loc[lambda c: c >= MIN_DAY_N].index
            sd = s[s.day.isin(full_days)]
            key = dict(inst=inst[:3], h=h)
            for e in ESTIMATORS:
                x = s[e].to_numpy() * np.sqrt(h)
                daily = sd.groupby("day").apply(lambda g: spearman(g[e].to_numpy(), g.abs_r.to_numpy()),
                                                include_groups=False)
                daily_R = sd.groupby("day").apply(lambda g: spearman(g[e].to_numpy(), g.R.to_numpy()),
                                                  include_groups=False)
                ic_rows.append({**key, "estimator": e, "n": len(s), **ic_summary(daily),
                                "ic_R_mean": daily_R.mean(), "ic_R_ir": daily_R.mean() / daily_R.std(),
                                "ic_pooled": spearman(s[e].to_numpy(), s.abs_r.to_numpy()),
                                "daily_ic": json.dumps({str(d.date()): round(float(v), 4) for d, v in daily.items()})})
                b = pd.cut(x, EDGES, right=False)
                for i, (lo, hi) in enumerate(zip(EDGES[:-1], EDGES[1:])):
                    m = b.codes == i
                    g = s[m]
                    if not len(g):
                        continue
                    mean = g.abs_r.mean()
                    ci = boot_ci(s, m, day_codes, W)
                    per_block = g.groupby("block").abs_r.mean().reindex(blocks)
                    bin_rows.append({**key, "estimator": e, "bin_lo": lo, "bin_hi": hi, "n": len(g),
                                     "n_days": g.day.nunique(), "x_mean": x[m].mean(), "abs_r_mean": mean,
                                     "abs_r_ci_lo": ci[0], "abs_r_ci_hi": ci[1], "R_mean": g.R.mean(),
                                     "R_med": g.R.median(), **econ(mean, cost),
                                     **{f"abs_r_{bk}": v for bk, v in per_block.items()},
                                     **{f"n_{bk}": int((g.block == bk).sum()) for bk in blocks}})
                    zr, zabs = g.R.to_numpy() / x[m], g.abs_r.to_numpy() / x[m]
                    z_rows.append({**key, "estimator": e, "bin_lo": lo, "bin_hi": hi, "n": len(g),
                                   **{f"z_R_q{int(q * 100)}": np.quantile(zr, q) for q in QS},
                                   **{f"z_abs_q{int(q * 100)}": np.quantile(zabs, q) for q in QS},
                                   **{f"p_R_ge_{k}x": (zr >= k).mean() for k in (1, 2, 3)}})
                for X in GATE_X:
                    m = x >= X
                    if m.sum() < 30:
                        break
                    g = s[m]
                    mean = g.abs_r.mean()
                    ci = boot_ci(s, m, day_codes, W)
                    per_block = g.groupby("block").abs_r.mean().reindex(blocks)
                    gate_rows.append({**key, "estimator": e, "X": X, "coverage": m.mean(), "n": int(m.sum()),
                                      "n_days": g.day.nunique(), "abs_r_mean": mean, "abs_r_ci_lo": ci[0],
                                      "abs_r_ci_hi": ci[1], "R_mean": g.R.mean(), **econ(mean, cost),
                                      **{f"abs_r_{bk}": v for bk, v in per_block.items()},
                                      **{f"coverage_{bk}": float((s.block == bk)[m].sum() / max((s.block == bk).sum(), 1))
                                         for bk in blocks}})
            # O3: other instruments' sigma at the same minute
            for src in ALL_INSTRUMENTS:
                if src == inst:
                    continue
                o = frames[src][list(ESTIMATORS)].reindex(s.index)
                for e in ESTIMATORS:
                    t = s.assign(src=o[e].to_numpy()).dropna(subset=["src"])
                    td = t[t.day.isin(full_days)]
                    daily = td.groupby("day").apply(
                        lambda g: partial_spearman(g.src.to_numpy(), g.abs_r.to_numpy(), g[e].to_numpy()),
                        include_groups=False)
                    o3_rows.append({**key, "source": src[:3], "estimator": e, "n": len(t), **ic_summary(daily),
                                    "ic_raw_pooled": spearman(t.src.to_numpy(), t.abs_r.to_numpy())})
                    own = pd.cut(t[e] * np.sqrt(h), COARSE, right=False)
                    other = pd.cut(t.src * np.sqrt(h), COARSE, right=False)
                    for (ob, sb), g in t.groupby([own, other], observed=True):
                        heat_rows.append({**key, "source": src[:3], "estimator": e, "own_lo": ob.left,
                                          "src_lo": sb.left, "n": len(g), "n_days": g.day.nunique(),
                                          "abs_r_mean": g.abs_r.mean(), "R_mean": g.R.mean()})
            print(f"{inst} h={h}: n={len(s)} days={len(days)} full_days={len(full_days)}", flush=True)

    pd.DataFrame(ic_rows).to_csv(OUT / "o1_ic.csv", index=False)
    pd.DataFrame(bin_rows).to_csv(OUT / "o1_bins.csv", index=False)
    pd.DataFrame(gate_rows).to_csv(OUT / "o1_gate.csv", index=False)
    pd.DataFrame(o3_rows).to_csv(OUT / "o3_ic.csv", index=False)
    pd.DataFrame(heat_rows).to_csv(OUT / "o3_heat.csv", index=False)
    pd.DataFrame(z_rows).to_csv(OUT / "o4_z.csv", index=False)
    (OUT / "run.json").write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
