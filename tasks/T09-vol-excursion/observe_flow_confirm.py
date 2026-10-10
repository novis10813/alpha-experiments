"""T09 excursion-v3: does flow or order book imbalance at a breakout separate continuation from reversal?

Discovery splits only. Preregistered (fixed before results):
- Data: discovery_1..5, the August supplement 2026-07-25..2026-08-28 (end exclusive, block "august"), and the
  existing supplemental splits (block "supplemental"): 7 chronological blocks per instrument.
  2026-09-21 onward is not read (reserved out-of-sample). Mid, rv_60 decile, and breakout events, continuation
  and breakout-direction trade exactly as excursion-v2 (observe_continuation.events).
- Features at the breakout minute tau (rows <= tau only), as in A2: flow_w = sum(buy - sell) / sum(volume) and
  obi_w = mean depth10 OBI over the trailing w minutes, w in {15, 60}. Aligned value a = side x feature.
  Groups: confirm (a > 0) and oppose (a < 0).
- Fade trade: the opposite side of the same event, entry at tau+1 bid (fading an up break) or ask, the same
  barriers and exit minute (symmetric barriers mirror the outcome), exit at ask or bid.
- C5 direction: diff = P(continue | resolved, confirm) - P(continue | resolved, oppose), all deciles.
  A cell (feature, h, b) passes on an instrument if diff has the pooled sign in >= 6 of 7 blocks. The cell passes
  if >= 2 of 3 instruments pass with the same pooled sign. b in {1, 2} x cost_v1, h in {30, 60, 240}:
  24 cells, 72 instrument cells.
- C6 economics: config = (feature, rule, b, h, rv group), rule confirm -> follow the breakout, oppose -> fade it,
  b in {1, 2, 3} x cost_v1, rv group all or decile 9-10 at tau: 144 configs per instrument.
  An instrument passes a config if v2 mean net > 0, t >= 2, >= 5 of 7 blocks positive, n >= 30.
  Candidate if the same config passes on >= 2 instruments.
- Descriptive only (uses full-sample event quantiles): P(continue) by quintile of a.
- Limitation: events keep the excursion-v2 sequence, so skipping an oppose event does not start an earlier
  search for the next breakout.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from evolution.spec import FEE_RATE
from analysis.discovery_minutes import load
from analysis.market_regime_report import ALL_INSTRUMENTS
from .observe_continuation import FEE_BPS, HS, KS, events
from .observe_excursion import state

RUN_ID = "excursion-v3"
OUT = Path("outputs/T09-vol-excursion") / RUN_ID
AUGUST = (("discovery_supplemental_20260725_20260828", "august"),)
FEATURES = ("flow_15", "flow_60", "obi_15", "obi_60")
C5_KS = (1, 2)
C5_MIN_BLOCKS, C6_MIN_BLOCKS = 6, 5


def features(df: pd.DataFrame) -> pd.DataFrame:
    roll = lambda s, w, fn: getattr(s.rolling(w, min_periods=w), fn)()
    f = pd.DataFrame(index=df.index)
    for w in (15, 60):
        f[f"flow_{w}"] = roll(df.buy_vol - df.sell_vol, w, "sum") / roll(df.volume, w, "sum")
        f[f"obi_{w}"] = roll(df.obi, w, "mean")
    return f


def add_fade(df: pd.DataFrame, e: pd.DataFrame) -> pd.DataFrame:
    bid, ask = df.bid.to_numpy(float), df.ask.to_numpy(float)
    tau = df.index.get_indexer(e.ts)
    x = tau + 1 + e.hold_min.to_numpy()
    up = e.side.to_numpy() > 0
    entry = np.where(up, bid[tau + 1], ask[tau + 1])
    exit_px = np.where(up, ask[x], bid[x])
    gross = -e.side.to_numpy() * (exit_px / entry - 1) * 1e4
    out = e.assign(fade_gross_bps=gross)
    for c, fee in FEE_BPS.items():
        out[f"fade_net_{c}"] = gross - 2 * fee
    return out


def p_cont(e: pd.DataFrame) -> float:
    res = e.cont != "time"
    return (e.cont == "continue").sum() / res.sum() if res.any() else np.nan


def trade_stats(net: pd.Series, block: pd.Series, blocks: list[str]) -> dict:
    n = len(net)
    per = net.groupby(block).mean().reindex(blocks)
    se = net.std(ddof=1) / np.sqrt(n) if n > 1 else np.nan
    return {"n": n, "mean_net_v2": net.mean() if n else np.nan, "t_net_v2": net.mean() / se if n > 1 else np.nan,
            "blocks_pos_v2": int((per > 0).sum()),
            "per_block_net_v2": [None if np.isnan(v) else round(float(v), 1) for v in per]}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    c5, c6, quint, all_events = [], [], [], []
    for inst in ALL_INSTRUMENTS:
        df = load(inst, extra=AUGUST)
        st, ft = state(df), features(df)
        spread = float(df.spread_bps[df.spread_bps > 0].median())
        cost_v1 = 2 * FEE_RATE * 1e4 + spread
        blocks = [bk for bk in pd.unique(df.block) if isinstance(bk, str)]
        for k in KS:
            b = k * cost_v1
            for h in HS:
                e = add_fade(df, events(df, st, b, h))
                fv = ft.reindex(e.ts)
                for f in FEATURES:
                    e[f"a_{f}"] = e.side.to_numpy() * fv[f].to_numpy()
                key = dict(inst=inst[:3], k=k, b_bps=round(b, 2), h=h)
                all_events.append(e.assign(**key))
                for f in FEATURES:
                    a = e[f"a_{f}"]
                    conf, opp = e[a > 0], e[a < 0]
                    if k in C5_KS:
                        per = [p_cont(conf[conf.block == bk]) - p_cont(opp[opp.block == bk]) for bk in blocks]
                        c5.append({**key, "feature": f, "n_confirm": len(conf), "n_oppose": len(opp),
                                   "p_cont_confirm": p_cont(conf), "p_cont_oppose": p_cont(opp),
                                   "diff": p_cont(conf) - p_cont(opp),
                                   "per_block_diff": [None if np.isnan(v) else round(float(v), 3) for v in per]})
                    for grp, sub in (("all", e), ("dec9_10", e[e.decile >= 9])):
                        sa = sub[f"a_{f}"]
                        for rule, s, col in (("confirm_follow", sub[sa > 0], "net_v2"),
                                             ("oppose_fade", sub[sa < 0], "fade_net_v2")):
                            c6.append({**key, "feature": f, "rule": rule, "group": grp,
                                       "p_cont": p_cont(s), **trade_stats(s[col], s.block, blocks)})
                    q = pd.qcut(a, 5, labels=False, duplicates="drop")
                    for qi, g in e.groupby(q):
                        quint.append({**key, "feature": f, "quintile": int(qi) + 1, "n": len(g),
                                      "a_med": g[f"a_{f}"].median(), "p_cont": p_cont(g),
                                      "mean_net_v2": g.net_v2.mean(), "mean_fade_net_v2": g.fade_net_v2.mean()})
        print(f"{inst}: done, blocks {blocks}", flush=True)

    c5 = pd.DataFrame(c5)
    c5["blocks_same_sign"] = [sum(1 for v in r.per_block_diff if v is not None and np.sign(v) == np.sign(r["diff"]))
                              for _, r in c5.iterrows()]
    c5["pass_inst"] = c5.blocks_same_sign >= C5_MIN_BLOCKS
    c6 = pd.DataFrame(c6)
    c6["pass_inst"] = (c6.mean_net_v2 > 0) & (c6.t_net_v2 >= 2) & (c6.blocks_pos_v2 >= C6_MIN_BLOCKS) & (c6.n >= 30)
    c5.to_csv(OUT / "c5_direction.csv", index=False)
    c6.to_csv(OUT / "c6_economics.csv", index=False)
    pd.DataFrame(quint).to_csv(OUT / "quintiles.csv", index=False)
    pd.concat(all_events).to_csv(OUT / "events.csv", index=False)

    checks = []
    for (f, k, h), g in c5.groupby(["feature", "k", "h"]):
        passed = g[g.pass_inst]
        best = max((passed["diff"] > 0).sum(), (passed["diff"] < 0).sum())
        checks.append({"check": "C5", "feature": f, "k": k, "h": h, "instruments_passed": len(passed),
                       "same_sign_passed": int(best), "pass": bool(best >= 2)})
    for cfg, g in c6.groupby(["feature", "rule", "k", "h", "group"]):
        if g.pass_inst.sum():
            checks.append({"check": "C6", "feature": cfg[0], "rule": cfg[1], "k": cfg[2], "h": cfg[3],
                           "group": cfg[4], "instruments_passed": int(g.pass_inst.sum()),
                           "pass": bool(g.pass_inst.sum() >= 2)})
    checks.append({"check": "C6_total", "configs_per_instrument": len(c6) // len(ALL_INSTRUMENTS),
                   "instrument_configs_passed": int(c6.pass_inst.sum())})
    pd.DataFrame(checks).to_csv(OUT / "checks.csv", index=False)
    (OUT / "run.json").write_text(json.dumps({"run_id": RUN_ID, "fees_bps": FEE_BPS, "extra_splits": AUGUST},
                                             indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
