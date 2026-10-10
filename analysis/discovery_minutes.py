"""Minute-level discovery frames for observation studies (discovery splits only)."""
from __future__ import annotations

import numpy as np
import pandas as pd
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog

from evolution.market_state import EvolutionMarketState
from analysis.market_regime_report import default_split_map

MIN_NS = 60_000_000_000


def load(inst: str, extra: tuple[tuple[str, str], ...] = ()) -> pd.DataFrame:
    """extra: (supplemental split, block label) pairs added to the default discovery splits."""
    sm = default_split_map()[inst]
    parts = [(sm.original_folds_root, s, s) for s in sm.original_folds] + [
        (sm.supplemental_root, s, "supplemental") for s in sm.supplemental_splits
    ] + [(sm.supplemental_root, s, block) for s, block in extra]
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
