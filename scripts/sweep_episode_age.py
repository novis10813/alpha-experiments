"""Pre-registered robustness sweep for the mid/late-episode 30s mid-move.

Hypothesis (derived from evolution-1/2, run007): while book_imbalance > 0.45,
the 30s forward mid move is large at episode age 20-45s and small at onset.
Confirmation on 16 fresh 3h windows (evolution folds and final holdout
excluded). Diagnostic only: no backtest, no fees, no selection.
"""
import bisect
import json
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import experiments.open_evolve.cli as cli
from experiments.open_evolve.backtest import Fold
from experiments.open_evolve.features import FeatureConfig, FeatureEngine

HORIZON = 30_000_000_000
WARMUP = 30 * 60 * 1_000_000_000
TAIL = 120 * 1_000_000_000

WINDOWS = [
    "06-11 03:00", "06-11 21:00", "06-13 03:00", "06-13 21:00",
    "06-15 09:00", "06-15 21:00", "06-17 09:00", "06-17 21:00",
    "06-19 09:00", "06-19 21:00", "06-21 03:00", "06-21 21:00",
    "06-23 03:00", "06-23 15:00", "06-24 03:00", "06-24 15:00",
]
BUCKETS = [(0, 5e9), (5e9, 10e9), (10e9, 20e9), (20e9, 30e9), (30e9, 60e9)]


def main() -> None:
    cfg = json.loads(Path("outputs/open_evolve/config_run007.json").read_text())
    catalog = cli.make_catalog()
    iid = cli.InstrumentId.from_str(cfg["instrument_id"])
    instrument, _ = cli.resolve_instrument(catalog, iid)
    rows = []
    for label in WINDOWS:
        a = datetime.strptime("2026-" + label, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        b = a + timedelta(hours=3)
        fold = Fold(name=label,
                    warmup_start=int(a.timestamp() * 1e9) - WARMUP,
                    start=int(a.timestamp() * 1e9),
                    entry_end=int(b.timestamp() * 1e9) - 2_000_000_000,
                    end=int(b.timestamp() * 1e9),
                    tail_end=int(b.timestamp() * 1e9) + TAIL)
        try:
            trades, depths, _ = cli.load_fold(catalog, iid, fold, cfg["max_events"])
        except ValueError as exc:
            print(f"{label}: SKIP ({exc})", flush=True)
            continue
        fe = FeatureEngine(FeatureConfig(instrument_id=instrument.id, **cfg["features"]))
        ordered = sorted([e for e in [*depths, *trades]
                          if fold.warmup_start <= e.ts_init <= fold.tail_end],
                         key=lambda e: e.ts_init)
        snaps = [fe.update(e, available_at=e.ts_init, event_ordinal=i)
                 for i, e in enumerate(ordered)]
        ts = [s.available_at for s in snaps]
        mids = [s.market.mid for s in snaps]
        seen: set[tuple[int, int]] = set()
        per_bucket: dict[int, list[float]] = {i: [] for i in range(len(BUCKETS))}
        ep_id = -1
        last_above = False
        for i, s in enumerate(snaps):
            m = s.market
            above = (m.ready and m.book_imbalance is not None
                     and m.book_imbalance > 0.45 and m.one_sidedness_age_ns is not None)
            if above and not last_above:
                ep_id += 1
            last_above = above
            if not above:
                continue
            if not (fold.start <= s.available_at <= fold.end - HORIZON - 2_000_000_000):
                continue
            bi = next((k for k, (lo, hi) in enumerate(BUCKETS)
                       if lo <= m.one_sidedness_age_ns < hi), None)
            if bi is None:
                continue
            key = (ep_id, bi)
            if key in seen:
                continue
            seen.add(key)
            j = bisect.bisect_right(ts, s.available_at + HORIZON) - 1
            if j <= i or mids[j] is None or mids[i] is None:
                continue
            per_bucket[bi].append(10_000 * (mids[j] - mids[i]) / mids[i])
        cells = []
        for bi, vals in per_bucket.items():
            cells.append(f"{statistics.median(vals):+.2f}({len(vals)})" if vals else "   -  (  0)")
        rows.append((label, cells))
        print(f"{label}: " + "  ".join(cells), flush=True)
    header = "window      " + "  ".join(f"{lo/1e9:3.0f}-{hi/1e9 if hi < 1e15 else 60:3.0f}s" for lo, hi in BUCKETS)
    print("\nmedian 30s mid-move (bps), n episodes per bucket")
    print(header)
    for label, cells in rows:
        print(f"{label}   " + "  ".join(cells))


if __name__ == "__main__":
    sys.exit(main())
