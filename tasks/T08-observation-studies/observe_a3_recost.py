"""Re-cost A1 breakeven and A3 trades under perpetual fee scenarios (draft cost profile v2).

Reads outputs/observe-a1/summary.csv and outputs/observe-a3/trades.csv; run those reports first.
Round-trip fee scenarios: taker/taker 10 bps, maker/taker 7 bps, maker/maker 4 bps.
A3 maker-entry scenario: take-profit exits are maker (2 bps), stop and time exits are taker (5 bps).
Maker scenarios assume fills with no adverse selection, so they are optimistic.
"""
from __future__ import annotations

import pandas as pd

SCENARIOS = (("taker/taker 10", 10), ("maker/taker 7", 7), ("maker/maker 4", 4))


def main() -> None:
    s = pd.read_csv("outputs/observe-a1/summary.csv")
    s["inst"] = s.instrument.str[:3]
    spread = s.cost_bps - 20  # A1 cost = 20 bps spot fees + median spread
    for name, fee_rt in SCENARIOS:
        s[name] = 0.5 + (fee_rt + spread) / (2 * s.abs_mean)
    print(s.pivot_table(index="h_min", columns="inst", values=[n for n, _ in SCENARIOS]).round(3).to_string())

    t = pd.read_csv("outputs/observe-a3/trades.csv")
    t = t[t.delay == 1]
    rows = []
    for (inst, cond, tp, sl), g in t.groupby(["inst", "cond", "tp", "sl"]):
        exit_taker = (g.outcome != "tp").astype(float)
        rows.append({"inst": inst, "cond": cond, "tp/sl": f"{tp}/{sl}", "n": len(g), "gross": g.gross_bps.mean(),
                     "net_taker_10": (g.gross_bps - 10).mean(),
                     "net_maker_entry_7to10": (g.gross_bps - 2 - (2 + 3 * exit_taker)).mean(),
                     "net_all_maker_4": (g.gross_bps - 4).mean()})
    pd.set_option("display.width", 200, "display.float_format", "{:.1f}".format)
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
