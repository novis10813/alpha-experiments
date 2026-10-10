"""T09 excursion-v2: does price continue after it first reaches +-b? Discovery splits only.

Preregistered (fixed before results):
- Data, mid, rv_60 decile (trailing 7d percentile) as in observe_excursion.py.
- Events, sequential and non-overlapping per instrument: from reference mid at minute i, the first minute tau
  in (i, i+h] with |mid / ref - 1| >= b is a breakout with side s = sign of that move. No touch within h
  resets the reference at i+h. A gap resets the reference after the gap. The next reference starts when
  both the continuation and the trade below have ended.
- Continuation (mid): from mid at tau, first of s-move >= +b (continue) or <= -b (reverse) within h, else time.
  A martingale gives P(continue | resolved) = 0.5.
- Trade: entry at minute tau+1 at ask (long) or bid (short). Barriers +-b on mid relative to mid at tau+1,
  time limit h. Exit at bid (long) or ask (short) of the exit minute. Fees per side: 10 bps (v1),
  5 bps (draft v2 taker, descriptive until v2 is active).
- Grid: b = k x cost_v1 for k in {1, 2, 3} (20, 40, 60 bps), h in {30, 60, 240}. Groups: all events, and
  rv_60 decile 9-10 at tau.
- C3 direction: at b = 2 x cost_v1, P(continue | resolved) in decile 9-10 on the same side of 0.5 as the
  pooled value in >= 5 of 6 blocks on >= 2 of 3 instruments. 9 cells.
- C4 economics: a config passes for an instrument if v2 mean net > 0, t >= 2, >= 4 of 6 blocks positive,
  n >= 30. Candidate if BTC and ETH both have a passing config. 54 configs (3 x 3 x 2 x 3 instruments).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from evolution.spec import FEE_RATE
from analysis.discovery_minutes import load
from analysis.market_regime_report import ALL_INSTRUMENTS
from .observe_excursion import state

RUN_ID = "excursion-v2"
OUT = Path("outputs/T09-vol-excursion") / RUN_ID
HS = (30, 60, 240)
KS = (1, 2, 3)
FEE_BPS = {"v1": FEE_RATE * 1e4, "v2": 5.0}
C3_K = 2


def first(mask: np.ndarray) -> int | None:
    k = np.flatnonzero(mask)
    return int(k[0]) if len(k) else None


def resolve(mid: np.ndarray, start: int, side: int, b: float, h: int) -> tuple[str, int] | None:
    """First barrier on mid relative to mid[start]; returns (outcome, exit index) or None on a gap."""
    path = mid[start + 1: start + h + 1]
    if len(path) < h or not np.isfinite(path).all() or not np.isfinite(mid[start]):
        return None
    move = side * (path / mid[start] - 1) * 1e4
    up, dn = first(move >= b), first(move <= -b)
    if up is not None and (dn is None or up < dn):
        return "continue", start + 1 + up
    if dn is not None:
        return "reverse", start + 1 + dn
    return "time", start + h


def events(df: pd.DataFrame, st: pd.DataFrame, b: float, h: int) -> pd.DataFrame:
    mid, bid, ask = (df[c].to_numpy(dtype=float) for c in ("mid", "bid", "ask"))
    dec, rv, block = st.decile.to_numpy(), st.rv_60.to_numpy(), df.block.to_numpy()
    n, i, rows = len(df), 0, []
    while i + h + 1 < n:
        if not np.isfinite(mid[i]):
            i += 1
            continue
        seg = mid[i + 1: i + h + 1]
        gap = first(~np.isfinite(seg))
        lim = h if gap is None else gap
        move = (seg[:lim] / mid[i] - 1) * 1e4
        k = first(np.abs(move) >= b)
        if k is None:
            i = i + h if gap is None else i + 1 + gap
            continue
        tau = i + 1 + k
        side = int(np.sign(move[k]))
        cont = resolve(mid, tau, side, b, h)
        trade = resolve(mid, tau + 1, side, b, h) if tau + 1 < n else None
        if cont is None or trade is None or not (bid[tau + 1] > 0 and ask[tau + 1] > 0):
            i = tau + 1
            continue
        x = trade[1]
        entry, exit_px = (ask[tau + 1], bid[x]) if side > 0 else (bid[tau + 1], ask[x])
        if not exit_px > 0:
            i = tau + 1
            continue
        gross = side * (exit_px / entry - 1) * 1e4
        rows.append({"ts": df.index[tau], "block": block[tau], "side": side, "decile": dec[tau], "rv_60": rv[tau],
                     "wait_min": k + 1, "overshoot_bps": abs(move[k]) - b, "cont": cont[0],
                     "cont_min": cont[1] - tau, "trade": trade[0], "hold_min": x - tau - 1, "gross_bps": gross,
                     **{f"net_{c}": gross - 2 * fee for c, fee in FEE_BPS.items()}})
        i = max(cont[1], x)
    return pd.DataFrame(rows)


def summarize(e: pd.DataFrame, blocks: list[str], **key) -> dict:
    row = {**key, "n": len(e)}
    if e.empty:
        return row
    res = e[e.cont != "time"]
    per = e.groupby("block").net_v2.mean().reindex(blocks)
    se = e.net_v2.std(ddof=1) / np.sqrt(len(e)) if len(e) > 1 else np.nan
    p = lambda s: (s.cont == "continue").sum() / max((s.cont != "time").sum(), 1)
    return row | {
        "p_cont": p(e), "p_cont_up": p(e[e.side > 0]), "p_cont_down": p(e[e.side < 0]),
        "p_time": (e.cont == "time").mean(), "n_resolved": len(res),
        "mean_gross": e.gross_bps.mean(), "mean_net_v1": e.net_v1.mean(), "mean_net_v2": e.net_v2.mean(),
        "t_net_v2": e.net_v2.mean() / se, "blocks_pos_v2": int((per > 0).sum()),
        "per_block_net_v2": [None if np.isnan(v) else round(float(v), 1) for v in per],
        "per_block_p_cont": [round(float(p(e[e.block == bk])), 3) if (e[e.block == bk].cont != "time").any()
                             else None for bk in blocks],
        "wait_med": e.wait_min.median(), "overshoot_med": e.overshoot_bps.median(), "hold_med": e.hold_min.median(),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows, dec_rows, all_events = [], [], []
    for inst in ALL_INSTRUMENTS:
        df = load(inst)
        st = state(df)
        spread = float(df.spread_bps[df.spread_bps > 0].median())
        cost_v1 = 2 * FEE_RATE * 1e4 + spread
        blocks = [bk for bk in pd.unique(df.block) if isinstance(bk, str)]
        for k in KS:
            b = k * cost_v1
            for h in HS:
                e = events(df, st, b, h)
                key = dict(inst=inst[:3], k=k, b_bps=round(b, 2), h=h)
                rows.append(summarize(e, blocks, group="all", **key))
                rows.append(summarize(e[e.decile >= 9], blocks, group="dec9_10", **key))
                for d, g in e.groupby("decile"):
                    dec_rows.append(summarize(g, blocks, group=f"dec{int(d)}", **key))
                all_events.append(e.assign(**key))
        print(f"{inst}: done", flush=True)
    summ = pd.DataFrame(rows)
    summ.to_csv(OUT / "summary.csv", index=False)
    pd.DataFrame(dec_rows).to_csv(OUT / "by_decile.csv", index=False)
    pd.concat(all_events).to_csv(OUT / "events.csv", index=False)

    checks = []
    top = summ[(summ.group == "dec9_10") & (summ.k == C3_K)]
    for _, r in top.iterrows():
        pooled = r.p_cont - 0.5
        same = sum(1 for v in r.per_block_p_cont if v is not None and np.sign(v - 0.5) == np.sign(pooled))
        checks.append({"check": "C3", "inst": r.inst, "h": r.h, "p_cont": r.p_cont, "blocks_same_side": same,
                       "pass_cell": same >= 5})
    c4 = summ[summ.group.isin(["all", "dec9_10"])]
    c4 = c4.assign(pass_cfg=(c4.mean_net_v2 > 0) & (c4.t_net_v2 >= 2) & (c4.blocks_pos_v2 >= 4) & (c4.n >= 30))
    for inst, g in c4.groupby("inst"):
        checks.append({"check": "C4", "inst": inst, "configs": len(g), "passing": int(g.pass_cfg.sum()),
                       "best_net_v2": g.mean_net_v2.max()})
    pd.DataFrame(checks).to_csv(OUT / "checks.csv", index=False)
    (OUT / "run.json").write_text(json.dumps({"run_id": RUN_ID, "fees_bps": FEE_BPS}, indent=2) + "\n",
                                  encoding="utf-8")


if __name__ == "__main__":
    main()
