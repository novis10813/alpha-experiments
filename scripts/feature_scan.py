"""Feature scan: 30s forward mid move vs each declared feature.

Pre-registered protocol (declared before results were seen):
- 14 fresh 3h windows (evolution folds and final holdout excluded).
- Causal samples: ready snapshots, non-overlapping forward windows
  (next sample > last + 30s).
- Pooled across windows; per feature, 10 pooled quantile bins, median
  30s mid move per bin; window-level sign count of top-minus-bottom bin.
Diagnostic only: no backtest, no fees, no selection.
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
    "06-11 03:00", "06-13 03:00", "06-13 21:00", "06-15 09:00",
    "06-15 21:00", "06-17 09:00", "06-17 21:00", "06-19 09:00",
    "06-19 21:00", "06-21 03:00", "06-21 21:00", "06-23 03:00",
    "06-23 15:00", "06-24 03:00",
]
FEATURES = [
    "book_imbalance", "one_sidedness_age_ns", "ofi", "ofi_accel",
    "trade_imbalance", "trade_size_ratio", "large_trade_imbalance",
    "depth_concentration_bid", "depth_concentration_ask", "trade_density",
    "log_return", "microprice_offset_bps", "spread_bps",
]


def main() -> None:
    cfg = json.loads(Path("outputs/open_evolve/config_run007.json").read_text())
    catalog = cli.make_catalog()
    iid = cli.InstrumentId.from_str(cfg["instrument_id"])
    instrument, _ = cli.resolve_instrument(catalog, iid)
    per_window: dict[str, dict[str, list[tuple[float, float]]]] = {}
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
        last = None
        n = 0
        bucket = {f: [] for f in FEATURES}
        for i, s in enumerate(snaps):
            m = s.market
            if not m.ready or m.mid is None:
                continue
            if not (fold.start <= s.available_at <= fold.end - HORIZON - 2_000_000_000):
                continue
            if last is not None and s.available_at <= last + HORIZON:
                continue
            last = s.available_at
            j = bisect.bisect_right(ts, s.available_at + HORIZON) - 1
            if j <= i or mids[j] is None:
                continue
            move = 10_000 * (mids[j] - mids[i]) / mids[i]
            n += 1
            for f in FEATURES:
                v = getattr(m, f)
                if v is not None:
                    bucket[f].append((float(v), move))
        per_window[label] = bucket
        print(f"{label}: {n} non-overlapping samples", flush=True)

    pooled = {f: [row for w in per_window.values() for row in w[f]] for f in FEATURES}
    print("\n" + "=" * 78)
    print("pooled decile profiles: median 30s mid move (bps) per feature decile")
    print("=" * 78)
    for f in FEATURES:
        rows = pooled[f]
        if len(rows) < 200:
            print(f"{f:28} insufficient n={len(rows)}")
            continue
        values = sorted(v for v, _ in rows)
        edges = [values[int(q * (len(values) - 1) / 10)] for q in range(11)]

        def bin_of(v: float) -> int:
            return min(max(bisect.bisect_right(edges, v) - 1, 0), 9)

        bins: dict[int, list[float]] = {k: [] for k in range(10)}
        for v, move in rows:
            bins[bin_of(v)].append(move)
        nonempty = [k for k in range(10) if bins[k]]
        if len(nonempty) < 3:
            print(f"{f:28} degenerate distribution (n={len(rows)})")
            continue
        bot_k, top_k = nonempty[0], nonempty[-1]
        prof = [f"{statistics.median(b):+.1f}" if b else "-" for b in bins.values()]
        top, bottom = statistics.median(bins[top_k]), statistics.median(bins[bot_k])
        # Window-level sign of top-minus-bottom bin, pooled edges.
        signs = []
        for w in per_window.values():
            wb = {k: [] for k in range(10)}
            for v, move in w[f]:
                wb[bin_of(v)].append(move)
            if wb[bot_k] and wb[top_k]:
                signs.append(statistics.median(wb[top_k]) - statistics.median(wb[bot_k]))
        pos = sum(x > 0 for x in signs)
        print(f"{f:28} n={len(rows):6d}  spread(top-bot)={top - bottom:+7.2f} bps  "
              f"windows>0: {pos}/{len(signs)}  (bins {bot_k}-{top_k})")
        print(f"{'':28} D0..D9: " + " ".join(f"{p:>6}" for p in prof))

    out = Path("outputs/open_evolve/feature_scan_rows.json")
    out.write_text(json.dumps({f: [[v, mv] for v, mv in rows] for f, rows in pooled.items()}))
    print(f"\nrows dumped to {out}")


if __name__ == "__main__":
    sys.exit(main())
