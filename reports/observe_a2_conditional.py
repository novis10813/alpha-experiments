"""A2 follow-up: breakeven hit rate after volatility and UTC-hour filters. Discovery splits only.

Descriptive only: rv_60 percentiles use the full sample, so the thresholds are not tradable rules.
"""
from __future__ import annotations

import pandas as pd

from reports.observe_a2_precursors import ALL_INSTRUMENTS, FEE_RATE, features, fwd, load


def main() -> None:
    rows = []
    for inst in ALL_INSTRUMENTS:
        df = load(inst)
        cost = 2 * FEE_RATE * 1e4 + float(df.spread_bps[df.spread_bps > 0].median())
        f = features(df)
        ok = df.close.notna()
        f, df = f[ok], df[ok]
        rvq = f.rv_60.rank(pct=True)
        us = f.hour.between(13, 15)
        conds = {"all": rvq.notna(), "rv60_top20": rvq >= 0.8, "rv60_top10": rvq >= 0.9, "us_13_15": us,
                 "rv60_top20&us": (rvq >= 0.8) & us}
        for h in (30, 60, 240):
            a = fwd(df, h).abs()
            for name, c in conds.items():
                x = a[c].dropna()
                rows.append({"inst": inst[:3], "h": h, "cond": name, "share": c.mean(), "E|r|": x.mean(),
                             "breakeven_hit": 0.5 + cost / (2 * x.mean())})
    r = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    print(r.pivot_table(index=["h", "cond"], columns="inst", values="breakeven_hit", sort=False).round(3))
    print(r[r.inst == "BTC"].pivot_table(index="cond", columns="h", values=["share", "E|r|"], sort=False).round(2))


if __name__ == "__main__":
    main()
