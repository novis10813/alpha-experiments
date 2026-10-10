"""T09: forward max/min excursion by trailing volatility state. Discovery splits only.

Preregistered (fixed before results):
- Data: BTC, ETH, BNB discovery_1..5 + supplemental (6 chronological blocks). Minute-close mid.
- Feature: rv_60 = std of 1-min log mid returns over the trailing 60 min (bps).
  State: percentile of rv_60 within the trailing 7d (min 3d of data), decile 1..10. Uses rows <= t only.
- Targets for h in {30, 60, 240} min, path = mid over (t, t+h], no gaps allowed:
  U = max path return, D = min path return (bps), tU / tD = minutes to first max / min,
  R = max(U, |D|), r_end = return at t+h (A2 target, for comparison).
  Sensitivity price: minute trade high/low (U_hl, D_hl); bid-ask bounce overstates it.
- Thresholds b = k x round-trip cost, k in {1, 2, 3}, for cost_v1 = 2 x 10 bps + median spread and
  cost_v2 = 2 x 5 bps + median spread (draft perp taker, descriptive only).
  Per sample and b: minutes to first U >= b and to first D <= -b. Touched = either within h.
- Main table: non-overlapping samples (every h-th grid minute). Minute-pooled table (every minute) is screening only.
- Checks on minute-pooled samples, A2 rule (sign repeats in >= 5 of 6 blocks on >= 2 of 3 instruments), b = 2 x cost_v1:
  C1 magnitude: P(touch) in rv decile 9-10 > decile 1-2.
  C2 direction: P(up first | touched) in decile 9-10 on the same side of 0.5 as the pooled value.
  9 cells each (3 instruments x 3 horizons).
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

RUN_ID = "excursion-v1"
OUT = Path("outputs/T09-vol-excursion") / RUN_ID
HS = (30, 60, 240)
W7, MIN7 = 7 * 1440, 3 * 1440
V2_FEE_BPS = 5.0
KS = (1, 2, 3)
CHECK_B = "v1x2"


def state(df: pd.DataFrame) -> pd.DataFrame:
    lr = np.log(df.mid).diff()
    rv = lr.rolling(60, min_periods=60).std() * 1e4
    pct = rv.rolling(W7, min_periods=MIN7).rank(pct=True)
    dec = np.clip(np.ceil(pct * 10), 1, 10)
    return pd.DataFrame({"rv_60": rv, "rv_pct": pct, "decile": dec}, index=df.index)


def first_hit(hit: np.ndarray) -> np.ndarray:
    k = hit.argmax(axis=1).astype(float) + 1
    k[~hit.any(axis=1)] = np.nan
    return k


def samples(df: pd.DataFrame, st: pd.DataFrame, h: int, step: int, thresholds: dict[str, float]) -> pd.DataFrame:
    mid, hi, lo = (df[c].to_numpy(dtype=float) for c in ("mid", "high", "low"))
    n = len(df)
    idx = np.arange(0, n - h, step)
    idx = idx[np.isfinite(mid[idx]) & st.decile.notna().to_numpy()[idx]]
    m0 = mid[idx, None]
    path = (sliding_window_view(mid[1:], h)[idx] / m0 - 1) * 1e4
    ok = ~np.isnan(path).any(axis=1)
    idx, path, m0 = idx[ok], path[ok], m0[ok]
    up_hl = (sliding_window_view(hi[1:], h)[idx].max(axis=1) / m0[:, 0] - 1) * 1e4
    dn_hl = (sliding_window_view(lo[1:], h)[idx].min(axis=1) / m0[:, 0] - 1) * 1e4
    out = pd.DataFrame({
        "ts": df.index[idx], "block": df.block.to_numpy()[idx],
        "rv_60": st.rv_60.to_numpy()[idx], "rv_pct": st.rv_pct.to_numpy()[idx], "decile": st.decile.to_numpy()[idx],
        "U": path.max(axis=1), "D": path.min(axis=1),
        "tU": path.argmax(axis=1) + 1, "tD": path.argmin(axis=1) + 1, "r_end": path[:, -1],
        "U_hl": up_hl, "D_hl": dn_hl,
    })
    out["R"] = np.maximum(out.U, -out.D)
    out["R_hl"] = np.maximum(out.U_hl, -out.D_hl)  # NaN if any minute lacks a trade high/low
    for name, b in thresholds.items():
        out[f"up_{name}"] = first_hit(path >= b)
        out[f"dn_{name}"] = first_hit(path <= -b)
    return out


def aggregate(s: pd.DataFrame, thresholds: dict[str, float]) -> dict:
    row = {"n": len(s)}
    for col in ("U", "R", "R_hl"):
        x = s[col].dropna()
        row |= {f"{col}_med": x.median(), f"{col}_q75": x.quantile(0.75), f"{col}_q90": x.quantile(0.9)}
    row |= {"drop_med": (-s.D).median(), "drop_q90": (-s.D).quantile(0.9), "abs_end_med": s.r_end.abs().median()}
    for name, b in thresholds.items():
        up, dn = s[f"up_{name}"], s[f"dn_{name}"]
        touched = up.notna() | dn.notna()
        first = np.fmin(up, dn)
        row |= {
            f"p_touch_{name}": touched.mean(),
            f"p_both_{name}": (up.notna() & dn.notna()).mean(),
            f"p_up_first_{name}": (up[touched].fillna(np.inf) < dn[touched].fillna(np.inf)).mean(),
            f"t_touch_med_{name}": first[touched].median(),
            f"p_end_{name}": (s.r_end.abs() >= b).mean(),
            f"p_touch_hl_{name}": (s.R_hl.dropna() >= b).mean(),
        }
    return row


def by_decile(s: pd.DataFrame, thresholds: dict[str, float], **key) -> list[dict]:
    rows = [{**key, "decile": 0, **aggregate(s, thresholds)}]
    for d, g in s.groupby("decile"):
        rows.append({**key, "decile": int(d), **aggregate(g, thresholds)})
    return rows


def checks(s: pd.DataFrame, blocks: list[str], **key) -> list[dict]:
    up, dn = s[f"up_{CHECK_B}"], s[f"dn_{CHECK_B}"]
    s = s.assign(touched=up.notna() | dn.notna(), up_first=up.fillna(np.inf) < dn.fillna(np.inf))
    top, bot = s[s.decile >= 9], s[s.decile <= 2]

    def c1(t, b):
        return t.touched.mean() - b.touched.mean()

    def c2(t):
        t = t[t.touched]
        return t.up_first.mean() - 0.5 if len(t) else np.nan

    rows = []
    for name, pooled, per in (
        ("C1", c1(top, bot), [c1(top[top.block == b], bot[bot.block == b]) for b in blocks]),
        ("C2", c2(top), [c2(top[top.block == b]) for b in blocks]),
    ):
        same = sum(1 for v in per if np.isfinite(v) and np.sign(v) == np.sign(pooled))
        rows.append({**key, "check": name, "pooled": pooled, "blocks_same_sign": same, "n_blocks": len(blocks),
                     "n_top": len(top), "n_top_touched": int(top.touched.sum()),
                     "per_block": [None if not np.isfinite(v) else round(float(v), 3) for v in per]})
    return rows


def manifest_hashes(inst: str) -> dict[str, str]:
    sm = default_split_map()[inst]
    parts = [(sm.original_folds_root, s) for s in sm.original_folds] + [
        (sm.supplemental_root, s) for s in sm.supplemental_splits
    ]
    return {f"{root}/{split}/{inst}/manifest.json": hashlib.sha256((root / split / inst / "manifest.json").read_bytes())
            .hexdigest() for root, split in parts}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    dec_rows, check_rows, main_samples = [], [], []
    run = {"run_id": RUN_ID, "command": " ".join(["python", "-m", "tasks.T09-vol-excursion.observe_excursion", *sys.argv[1:]]),
           "instruments": {}}
    for inst in ALL_INSTRUMENTS:
        df = load(inst)
        st = state(df)
        spread = float(df.spread_bps[df.spread_bps > 0].median())
        cost = {"v1": 2 * FEE_RATE * 1e4 + spread, "v2": 2 * V2_FEE_BPS + spread}
        thresholds = {f"{c}x{k}": k * v for c, v in cost.items() for k in KS}
        blocks = [b for b in pd.unique(df.block) if isinstance(b, str)]
        for h in HS:
            for step, label in ((h, "non_overlap"), (1, "minute_pooled")):
                s = samples(df, st, h, step, thresholds)
                key = dict(inst=inst[:3], h=h, sample=label)
                dec_rows += by_decile(s, thresholds, **key)
                if label == "minute_pooled":
                    check_rows += checks(s, blocks, inst=inst[:3], h=h)
                else:
                    main_samples.append(s.assign(inst=inst[:3], h=h))
        run["instruments"][inst] = {"median_spread_bps": spread, "thresholds_bps": thresholds, "blocks": blocks,
                                    "minutes_with_mid": int(df.mid.notna().sum()), "manifests_sha256": manifest_hashes(inst)}
        print(f"{inst}: minutes={int(df.mid.notna().sum())} spread={spread:.2f}bps", flush=True)
    pd.DataFrame(dec_rows).to_csv(OUT / "by_decile.csv", index=False)
    pd.DataFrame(check_rows).to_csv(OUT / "checks.csv", index=False)
    pd.concat(main_samples).to_csv(OUT / "samples_non_overlap.csv", index=False)
    (OUT / "run.json").write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
