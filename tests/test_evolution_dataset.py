import json
import tempfile
import unittest
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch


@dataclass(frozen=True)
class FakeTrade:
    instrument_id: str
    ts_event: int
    price: Decimal
    size: Decimal


@dataclass(frozen=True)
class FakeLevel:
    price: Decimal
    size: Decimal


@dataclass(frozen=True)
class FakeDepth:
    instrument_id: str
    ts_event: int
    bids: list[FakeLevel]
    asks: list[FakeLevel]


class EvolutionDatasetTests(unittest.TestCase):
    def _depth(self, ts_event: int) -> FakeDepth:
        return FakeDepth(
            "BTCUSDT.BINANCE", ts_event,
            [FakeLevel(Decimal("99.90"), Decimal("3"))],
            [FakeLevel(Decimal("100.10"), Decimal("1"))],
        )

    def test_state_is_complete_minute_end_and_contains_microstructure(self):
        from evolution.dataset import build_market_states

        states = build_market_states(
            [
                FakeTrade("BTCUSDT.BINANCE", 1_000_000_000, Decimal("100"), Decimal("2")),
                FakeTrade("BTCUSDT.BINANCE", 2_000_000_000, Decimal("101"), Decimal("3")),
            ],
            [self._depth(1_500_000_000), self._depth(2_500_000_000)],
        )
        state = states[0]
        self.assertEqual(state.ts_event, 60_000_000_000)
        self.assertGreater(state.ts_init, state.ts_event)
        self.assertEqual((state.open, state.high, state.low, state.close), (100, 101, 100, 101))
        self.assertEqual((state.trade_count, state.buy_trade_count, state.sell_trade_count), (2, 1, 0))
        self.assertAlmostEqual(state.depth10_obi_mean, 0.5)
        self.assertAlmostEqual(state.spread_bps, 20.0)

    def test_tick_rule_state_can_cross_a_utc_day_boundary(self):
        from evolution.dataset import _build_market_states

        first, price, sign = _build_market_states(
            [FakeTrade("BTCUSDT.BINANCE", 86_399_000_000_000, Decimal("101"), Decimal("1"))],
            [self._depth(86_399_000_000_000)],
            Decimal("100"),
            1,
        )
        second, _, _ = _build_market_states(
            [FakeTrade("BTCUSDT.BINANCE", 86_401_000_000_000, Decimal("101"), Decimal("2"))],
            [self._depth(86_401_000_000_000)],
            price,
            sign,
        )
        self.assertEqual(first[0].buy_trade_count, 1)
        self.assertEqual(second[0].buy_trade_count, 1)
        self.assertEqual(second[0].buy_volume, 2)

    def test_manifest_counts_gaps_and_hashes_local_file(self):
        from evolution.dataset import manifest_for
        from evolution.dataset import sha256_file
        from evolution.spec import Window
        from evolution.spec import utc

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data"
            path.write_bytes(b"safe-local-data")
            digest = sha256_file(path)
        window = Window("tiny", utc("2026-01-01T00:00:00Z"), utc("2026-01-01T00:02:00Z"), 60, 0)
        manifest = manifest_for("BTCUSDT.BINANCE", window, [], {"data": digest})
        self.assertEqual(manifest.missing_bucket_count, 2)
        self.assertEqual(len(manifest.files["data"]), 64)
        self.assertNotIn("secret", str(manifest).lower())

    def test_manifest_execution_profile_guard(self):
        from evolution.dataset import manifest_for
        from evolution.dataset import verify_manifest
        from evolution.dataset import write_manifest
        from evolution.spec import Window
        from evolution.spec import utc

        window = Window("discovery_1", utc("2026-01-01T00:00:00Z"), utc("2026-01-01T00:01:00Z"), 60, 0)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data").mkdir()
            manifest = manifest_for("BTCUSDT.BINANCE", window, [], {})
            write_manifest(manifest, root / "manifest.json")
            verified = verify_manifest(
                root / "manifest.json", "BTCUSDT.BINANCE", "discovery_1", "fast",
            )
            self.assertEqual(verified.quote_interval_seconds, 60)
            with self.assertRaisesRegex(ValueError, "execution profile"):
                verify_manifest(
                    root / "manifest.json", "BTCUSDT.BINANCE", "discovery_1", "executable",
                )

    def test_build_window_writes_per_stage_metric(self):
        from evolution.dataset import build_window_from_catalog
        from evolution.spec import Window
        from evolution.spec import utc

        class FakeCatalog:
            def trade_ticks(self, **kwargs):
                return [FakeTrade("BTCUSDT.BINANCE", 1_000_000_000, Decimal("100"), Decimal("1"))]

            def query(self, *args, **kwargs):
                return [self_depth]

        self_depth = self._depth(1_000_000_000)
        window = Window("discovery_test", utc("1970-01-01T00:00:00Z"), utc("1970-01-01T00:01:00Z"), 60, 0)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                patch("evolution.dataset.make_catalog", return_value=FakeCatalog()),
                patch("evolution.dataset.ParquetDataCatalog"),
                patch("evolution.dataset._write_catalog_chunk"),
            ):
                build_window_from_catalog("BTCUSDT.BINANCE", window, root)
            metrics = (root / "_metrics" / "dataset-build.jsonl").read_text(encoding="utf-8").splitlines()

        self.assertEqual(len(metrics), 1)
        metric = json.loads(metrics[0])
        self.assertEqual(metric["event"], "dataset_day_built")
        self.assertEqual(metric["instrument_id"], "BTCUSDT.BINANCE")
        self.assertEqual(metric["trade_count"], 1)
        self.assertEqual(metric["depth_count"], 1)
        for field in (
            "trade_fetch_seconds", "depth_fetch_seconds", "aggregate_seconds",
            "quote_build_seconds", "local_write_seconds", "max_rss_mib",
        ):
            self.assertGreaterEqual(metric[field], 0)

    def test_executable_builder_rejects_non_discovery_window(self):
        from evolution.dataset import build_executable_discovery_from_fast
        from evolution.spec import Window
        from evolution.spec import utc

        window = Window("validation", utc("2026-01-01T00:00:00Z"), utc("2026-01-01T00:01:00Z"), 1, 1)
        with self.assertRaisesRegex(ValueError, "discovery windows only"):
            build_executable_discovery_from_fast(
                "BTCUSDT.BINANCE", window, Path("fast"), Path("output"),
            )

    def test_local_nautilus_catalog_round_trip_and_manifest_verification(self):
        from data.orderbook_quotes import QuoteRow
        from evolution.dataset import manifest_for
        from evolution.dataset import verify_manifest
        from evolution.dataset import write_local_catalog
        from evolution.dataset import write_manifest
        from evolution.market_state import EvolutionMarketState
        from evolution.spec import Window
        from evolution.spec import utc
        from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog

        state = EvolutionMarketState(
            "BTCUSDT.BINANCE", 100, 100, 100, 100, 1, 1, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 99.9, 100.1, 20, 60_000_000_000, 60_000_000_002,
        )
        quote = QuoteRow(60_000_000_000, "BTCUSDT.BINANCE", 99.9, 100.1, 100, 0.2, 20)
        window = Window("tiny", utc("1970-01-01T00:00:00Z"), utc("1970-01-01T00:01:00Z"), 60, 0)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = write_local_catalog([state], [quote], root, "BTCUSDT.BINANCE")
            manifest = manifest_for("BTCUSDT.BINANCE", window, [state], files)
            write_manifest(manifest, root / "manifest.json")
            verified = verify_manifest(root / "manifest.json", "BTCUSDT.BINANCE", "tiny")
            catalog = ParquetDataCatalog(root)
            values = catalog.query(EvolutionMarketState, identifiers=["BTCUSDT.BINANCE"])
            quote_tick = catalog.quote_ticks(instrument_ids=["BTCUSDT.BINANCE"])[0]
            bar = catalog.bars(instrument_ids=["BTCUSDT.BINANCE"])[0]
        self.assertEqual(verified.row_count, 1)
        self.assertEqual(values[0].data.close, 100)
        self.assertEqual(quote_tick.ts_init, bar.ts_init)
        self.assertLess(bar.ts_init, values[0].data.ts_init)


if __name__ == "__main__":
    unittest.main()
