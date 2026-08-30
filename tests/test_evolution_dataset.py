import json
import math
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
    def _depth(self, ts_event: int, bid: str = "99.90", ask: str = "100.10") -> FakeDepth:
        return FakeDepth(
            "BTCUSDT.BINANCE", ts_event,
            [FakeLevel(Decimal(bid), Decimal("3"))],
            [FakeLevel(Decimal(ask), Decimal("1"))],
        )

    def _feature_ticks_and_depths(self, count: int):
        trades = []
        depths = []
        for index in range(count):
            bucket_start = index * 60_000_000_000
            trade_count = 2 + index % 3
            base = Decimal(100 + index)
            for trade_index in range(trade_count):
                trades.append(FakeTrade(
                    "BTCUSDT.BINANCE",
                    bucket_start + (trade_index + 1) * 1_000_000_000,
                    base + Decimal(trade_index) / 2,
                    Decimal(index + 1) / trade_count,
                ))
            mid = 100 + index
            depths.append(FakeDepth(
                "BTCUSDT.BINANCE", bucket_start + 30_000_000_000,
                [FakeLevel(Decimal(f"{mid - 0.1:.1f}"), Decimal(index + 2))],
                [FakeLevel(Decimal(f"{mid + 0.1:.1f}"), Decimal("1"))],
            ))
        return trades, depths

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

    def test_completed_bar_features_use_only_current_and_prior_bars(self):
        from evolution.dataset import build_market_states

        trades, depths = self._feature_ticks_and_depths(61)
        states = build_market_states(trades, depths)
        state = states[-1]
        self.assertEqual(state.ts_event, 61 * 60_000_000_000)
        self.assertAlmostEqual(state.return_5m, state.close / states[-6].close - 1.0)
        self.assertAlmostEqual(state.return_15m, state.close / states[-16].close - 1.0)
        self.assertAlmostEqual(state.return_60m, state.close / states[0].close - 1.0)
        self.assertAlmostEqual(state.close_location, 1.0)

        close_returns = [states[index].close / states[index - 1].close - 1.0 for index in range(1, len(states))]
        trailing_returns = close_returns[-15:]
        average = sum(trailing_returns) / len(trailing_returns)
        expected_volatility = math.sqrt(
            sum((value - average) ** 2 for value in trailing_returns) / len(trailing_returns),
        )
        self.assertAlmostEqual(state.realized_volatility_15m, expected_volatility)
        self.assertAlmostEqual(state.relative_volume_15m, 61 / (sum(range(46, 61)) / 15))
        self.assertAlmostEqual(state.relative_trade_density_15m, 2 / (sum(2 + i % 3 for i in range(45, 60)) / 15))
        self.assertAlmostEqual(
            state.signed_flow_persistence_5m,
            sum(item.volume_imbalance for item in states[-5:]) / 5,
        )
        self.assertAlmostEqual(
            state.obi_change_5m,
            state.depth10_obi_mean - states[-6].depth10_obi_mean,
        )
        self.assertNotEqual(state.obi_change_5m, state.volume_imbalance - states[-6].volume_imbalance)
        self.assertAlmostEqual(
            state.relative_spread_15m,
            state.spread_bps / (sum(item.spread_bps for item in states[-16:-1]) / 15),
        )
        self.assertTrue(all(math.isfinite(value) for item in states for value in (
            item.return_5m, item.return_15m, item.return_60m, item.close_location,
            item.realized_volatility_15m, item.relative_volume_15m,
            item.relative_trade_density_15m, item.signed_flow_persistence_5m,
            item.obi_change_5m, item.relative_spread_15m,
        )))

    def test_completed_bar_feature_warmup_and_zero_range_are_neutral(self):
        from evolution.dataset import build_market_states

        states = build_market_states(
            [
                FakeTrade("BTCUSDT.BINANCE", 1_000_000_000, Decimal("100"), Decimal("1")),
                FakeTrade("BTCUSDT.BINANCE", 61_000_000_000, Decimal("101"), Decimal("1")),
            ],
            [self._depth(30_000_000_000), self._depth(90_000_000_000)],
        )
        for state in states:
            self.assertEqual((state.return_5m, state.return_15m, state.return_60m), (0.0, 0.0, 0.0))
            self.assertEqual(state.realized_volatility_15m, 0.0)
            self.assertEqual(state.relative_volume_15m, 1.0)
            self.assertEqual(state.relative_trade_density_15m, 1.0)
            self.assertEqual(state.signed_flow_persistence_5m, 0.0)
            self.assertEqual(state.obi_change_5m, 0.0)
            self.assertEqual(state.relative_spread_15m, 1.0)
            self.assertEqual(state.close_location, 0.5)

    def test_features_are_not_changed_by_a_future_bucket(self):
        from evolution.dataset import build_market_states

        trades, depths = self._feature_ticks_and_depths(7)
        prefix = build_market_states(trades[:sum(2 + i % 3 for i in range(3))], depths[:3])
        complete = build_market_states(trades, depths)
        feature_names = (
            "return_5m", "return_15m", "return_60m", "close_location",
            "realized_volatility_15m", "relative_volume_15m",
            "relative_trade_density_15m", "signed_flow_persistence_5m",
            "obi_change_5m", "relative_spread_15m",
        )
        for prefix_state, complete_state in zip(prefix, complete[:len(prefix)], strict=True):
            for name in feature_names:
                self.assertEqual(getattr(prefix_state, name), getattr(complete_state, name))

    def test_feature_history_does_not_cross_dataset_boundaries(self):
        from evolution.dataset import build_market_states

        trades, depths = self._feature_ticks_and_depths(20)
        split = sum(2 + i % 3 for i in range(15))
        first = build_market_states(trades[:split], depths[:15])
        second = build_market_states(trades[split:], depths[15:])
        self.assertEqual(len(first), 15)
        self.assertEqual(second[0].return_5m, 0.0)
        self.assertEqual(second[0].relative_volume_15m, 1.0)
        self.assertEqual(second[0].realized_volatility_15m, 0.0)

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
            payload = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            payload["schema_version"] = 1
            (root / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unsupported dataset schema version"):
                verify_manifest(root / "manifest.json", "BTCUSDT.BINANCE", "discovery_1")

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

    def test_executable_builder_uses_local_source_quotes(self):
        from data.orderbook_quotes import QuoteRow
        from evolution.dataset import build_executable_discovery_from_fast
        from evolution.dataset import manifest_for
        from evolution.dataset import write_local_catalog
        from evolution.dataset import write_manifest
        from evolution.spec import Window
        from evolution.spec import utc
        from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog

        window = Window("discovery_1", utc("1970-01-01T00:00:00Z"), utc("1970-01-01T00:00:02Z"), 60, 0)
        quotes = [
            QuoteRow(1_000_000_000, "BTCUSDT.BINANCE", 99.9, 100.1, 100, 0.2, 20),
            QuoteRow(2_000_000_000, "BTCUSDT.BINANCE", 100.0, 100.2, 100.1, 0.2, 20),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "fast" / window.name / "BTCUSDT.BINANCE"
            files = write_local_catalog([], [quotes[0]], source, "BTCUSDT.BINANCE")
            write_manifest(manifest_for("BTCUSDT.BINANCE", window, [], files), source / "manifest.json")
            write_local_catalog([], quotes, source / "source-quotes-1s", "BTCUSDT.BINANCE")
            with patch("evolution.dataset.make_catalog", side_effect=AssertionError("remote catalog used")):
                manifest = build_executable_discovery_from_fast(
                    "BTCUSDT.BINANCE", window, root / "fast", root / "executable",
                )
            catalog = ParquetDataCatalog(root / "executable" / window.name / "BTCUSDT.BINANCE")
            output_quotes = catalog.quote_ticks(instrument_ids=["BTCUSDT.BINANCE"])

        self.assertEqual(manifest.quote_count, 2)
        self.assertEqual(len(output_quotes), 2)

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
            return_5m=0.01, return_15m=0.02, return_60m=0.03, close_location=0.5,
            realized_volatility_15m=0.04, relative_volume_15m=1.1,
            relative_trade_density_15m=0.9, signed_flow_persistence_5m=-0.2,
            obi_change_5m=0.3, relative_spread_15m=1.2,
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
        self.assertAlmostEqual(values[0].data.return_15m, 0.02)
        restored = EvolutionMarketState.from_json(state.to_json())
        self.assertEqual(restored.to_dict(), state.to_dict())
        self.assertEqual(quote_tick.ts_init, bar.ts_init)
        self.assertLess(bar.ts_init, values[0].data.ts_init)


if __name__ == "__main__":
    unittest.main()
