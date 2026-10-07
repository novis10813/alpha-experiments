"""F9: why does 240-min reversal flip sign in discovery_4? Discovery splits only.

Step 1: describe blocks. Step 2: per-day IC (is the flip concentrated?).
Step 3: preregistered trailing state variables (fixed before looking):
  S1 abs_ret_1440   |trailing 24h return|
  S2 vr_72h         trailing 72h variance ratio of 4h returns vs 15m returns (>1 trending, <1 reverting)
  S3 ac_4h_72h      trailing 72h lag-1 autocorrelation of non-overlapping 4h returns
  S4 rv_240_rel     rv_240 / trailing 7-day median rv_240
Pass rule: IC of ret_240 differs in the same direction across state terciles in >= 5 of 6 blocks
(or the tercile containing most of discovery_4 also has weaker IC outside discovery_4), on BTC and ETH.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from reports.observe_a2_precursors import ALL_INSTRUMENTS, MIN_NS, features, fwd, load, spearman

pd.set_option("display.width", 250, "display.max_columns", 40, "display.float_format", "{:.3f}".format)


def state_vars(df: pd.DataFrame) -> pd.DataFrame:
    m = df.mid
    s = pd.DataFrame(index=df.index)
    s["abs_ret_1440"] = (m / m.shift(1440) - 1).abs() * 1e4
    r15 = np.log(m).diff(15)
    r240 = np.log(m).diff(240)
    w = 72 * 60
    s["vr_72h"] = r240.rolling(w, min_periods=w // 2).var() / (16 * r15.rolling(w, min_periods=w // 2).var())
    # lag-1 autocorr of 4h returns sampled every 240 min inside the trailing 72h window
    lagged = r240.shift(240)
    s["ac_4h_72h"] = r240.rolling(w, min_periods=w // 2).corr(lagged)
    rv = np.log(m).diff().rolling(240, min_periods=240).std()
    s["rv_240_rel"] = rv / rv.rolling(7 * 1440, min_periods=1440).median()
    return s


def main() -> None:
    for inst in ALL_INSTRUMENTS:
        df = load(inst)
        f = features(df)
        s = state_vars(df)
        ok = df.close.notna()
        df, f, s = df[ok], f[ok], s[ok]
        y = fwd(df, 240)
        f["day"] = pd.to_datetime((df.index - MIN_NS) // 86_400_000_000_000, unit="D").strftime("%m-%d")
        print(f"\n===== {inst}")
        # Step 1: block description
        desc = []
        for b, g in f.groupby("block"):
            mid = df.mid[g.index]
            r4 = np.log(mid.iloc[::240]).diff().dropna()
            desc.append({"block": b, "days": g.day.nunique(), "net_ret_%": (mid.iloc[-1] / mid.iloc[0] - 1) * 100,
                         "rv_15_bps": f.rv_15[g.index].mean(), "ac1_4h": r4.autocorr(1),
                         "ic_ret240": spearman(f.ret_240[g.index], y[g.index]),
                         **{k: s[k][g.index].median() for k in s.columns}})
        print(pd.DataFrame(desc).set_index("block"))
        # Step 2: per-day IC in discovery_4 and neighbours
        g = f[f.block.isin(["discovery_3", "discovery_4", "discovery_5"])]
        daily = g.groupby("day").apply(lambda d: pd.Series({
            "block": d.block.iloc[0], "ic": spearman(f.ret_240[d.index], y[d.index]),
            "day_ret_%": (df.mid[d.index].iloc[-1] / df.mid[d.index].iloc[0] - 1) * 100}))
        print(daily.T)
        # Step 3: IC by state tercile (terciles over whole sample; descriptive)
        for k in s.columns:
            q = pd.qcut(s[k].rank(method="first"), 3, labels=["T1", "T2", "T3"])
            tab = {}
            for b in sorted(f.block.dropna().unique()):
                for t in ("T1", "T2", "T3"):
                    idx = (f.block == b) & (q == t)
                    tab.setdefault(b, {})[t] = spearman(f.ret_240[idx], y[idx]) if idx.sum() > 500 else np.nan
            tab = pd.DataFrame(tab).T
            share4 = q[f.block == "discovery_4"].value_counts(normalize=True).reindex(["T1", "T2", "T3"]).round(2)
            print(f"\n-- {k}: d4 tercile share {share4.to_dict()}")
            print(tab)


if __name__ == "__main__":
    main()
