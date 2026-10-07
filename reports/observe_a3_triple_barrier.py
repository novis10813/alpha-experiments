"""A3: 4h reversal after a large 24h move, triple-barrier evaluation. Discovery splits only.

Preregistered (fixed before results):
- C1: abs_ret_1440 >= trailing 7d q67 of abs_ret_1440.
- Signal: ret_240 >= trailing 7d q90 -> short; ret_240 <= trailing 7d q10 -> long. One position at a time.
- Control: same signal without C1. BNB is the negative control.
- Barriers (TP, SL) bps: (40,40), (60,60), (100,100), (60,120); time limit 240 min.
  Barriers checked on minute-close mid; fill at that minute's bid/ask (long exits at bid, short at ask).
- Cost: 10 bps fee per side on top of bid/ask. Entry at t (optimistic) or t+1 minute (conservative).
- Pass: conservative entry, BTC and ETH each have one barrier config with mean net > 0,
  >= 4 of 6 blocks positive, n >= 30.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from reports.observe_a2_precursors import ALL_INSTRUMENTS, FEE_RATE, load

OUT = Path("outputs/observe-a3")
W7 = 7 * 1440
BARRIERS = ((40, 40), (60, 60), (100, 100), (60, 120))
T_MAX = 240
FEE_BPS = FEE_RATE * 1e4


def signals(df: pd.DataFrame) -> pd.DataFrame:
    m = df.mid
    ret240 = (m / m.shift(240) - 1) * 1e4
    abs1440 = ((m / m.shift(1440) - 1) * 1e4).abs()
    roll = lambda s, q: s.rolling(W7, min_periods=3 * 1440).quantile(q)  # trailing, includes t
    c1 = abs1440 >= roll(abs1440, 0.67)
    side = pd.Series(0, index=df.index)
    side[ret240 >= roll(ret240, 0.90)] = -1
    side[ret240 <= roll(ret240, 0.10)] = 1
    return pd.DataFrame({"side": side, "c1": c1})


def simulate(df: pd.DataFrame, sig: pd.DataFrame, use_c1: bool, tp: float, sl: float, delay: int) -> pd.DataFrame:
    mid, bid, ask = df.mid.to_numpy(), df.bid.to_numpy(), df.ask.to_numpy()
    block = df.block.to_numpy()
    side = sig.side.to_numpy()
    ok = (side != 0) & (sig.c1.to_numpy() if use_c1 else True)
    trades, free_at = [], -1
    n = len(df)
    for i in np.flatnonzero(ok):
        e = i + delay
        if e < free_at or e + T_MAX >= n:
            continue
        path = mid[e + 1: e + T_MAX + 1]
        if np.isnan(path).any() or np.isnan(mid[e]) or not (bid[e] > 0 and ask[e] > 0):
            continue
        s = side[i]
        entry = ask[e] if s > 0 else bid[e]
        move = s * (path / mid[e] - 1) * 1e4  # signed mid move from entry minute
        hit_tp = np.flatnonzero(move >= tp)
        hit_sl = np.flatnonzero(move <= -sl)
        k_tp = hit_tp[0] if len(hit_tp) else T_MAX
        k_sl = hit_sl[0] if len(hit_sl) else T_MAX
        k = min(k_tp, k_sl, T_MAX - 1)
        outcome = "tp" if k_tp <= k_sl and k_tp < T_MAX else ("sl" if k_sl < T_MAX else "time")
        x = e + 1 + k
        exit_px = bid[x] if s > 0 else ask[x]
        if not exit_px > 0:
            continue
        gross = s * (exit_px / entry - 1) * 1e4
        trades.append({"ts": df.index[i], "block": block[i], "side": s, "outcome": outcome, "hold_min": k + 1,
                       "gross_bps": gross, "net_bps": gross - 2 * FEE_BPS,
                       "mae_bps": float(move[: k + 1].min()), "mfe_bps": float(move[: k + 1].max())})
        free_at = x + 1
    return pd.DataFrame(trades)


def summarize(t: pd.DataFrame, blocks: list[str], **key) -> dict:
    if t.empty:
        return {**key, "n": 0}
    per = t.groupby("block").net_bps.mean().reindex(blocks)
    se = t.net_bps.std(ddof=1) / np.sqrt(len(t)) if len(t) > 1 else np.nan
    return {**key, "n": len(t), "mean_net": t.net_bps.mean(), "t_stat": t.net_bps.mean() / se,
            "mean_gross": t.gross_bps.mean(), "tp_rate": (t.outcome == "tp").mean(),
            "sl_rate": (t.outcome == "sl").mean(), "time_rate": (t.outcome == "time").mean(),
            "mae_mean": t.mae_bps.mean(), "mfe_mean": t.mfe_bps.mean(), "hold_mean": t.hold_min.mean(),
            "blocks_pos": int((per > 0).sum()), "blocks_with_trades": int(per.notna().sum()),
            "per_block_net": [None if np.isnan(v) else round(v, 1) for v in per]}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows, all_trades = [], []
    for inst in ALL_INSTRUMENTS:
        df = load(inst)
        sig = signals(df)
        blocks = [b for b in pd.unique(df.block) if isinstance(b, str)]
        for use_c1 in (True, False):
            for tp, sl in BARRIERS:
                for delay in (0, 1):
                    t = simulate(df, sig, use_c1, tp, sl, delay)
                    key = dict(inst=inst[:3], cond="C1" if use_c1 else "noC1", tp=tp, sl=sl, delay=delay)
                    rows.append(summarize(t, blocks, **key))
                    if not t.empty:
                        all_trades.append(t.assign(**key))
        print(inst, "done", flush=True)
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "summary.csv", index=False)
    pd.concat(all_trades).to_csv(OUT / "trades.csv", index=False)


if __name__ == "__main__":
    main()
