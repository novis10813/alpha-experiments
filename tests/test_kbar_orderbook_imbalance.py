import tempfile
import unittest
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


@dataclass(frozen=True)
class FakeTradeTick:
    instrument_id: str
    ts_event: int
    price: Decimal
    size: Decimal
    trade_id: int


@dataclass(frozen=True)
class FakeLevel:
    size: Decimal


@dataclass(frozen=True)
class FakeDepth:
    instrument_id: str
    ts_event: int
    bids: list[FakeLevel]
    asks: list[FakeLevel]


class KbarOrderbookImbalanceTests(unittest.TestCase):
    def test_rows_keep_only_buckets_with_contiguous_trade_ids_and_orderbook_coverage(self):
        from data.kbar_orderbook_imbalance import kbar_orderbook_imbalance_rows

        rows = kbar_orderbook_imbalance_rows(
            [
                FakeTradeTick("BTCUSDT.BINANCE", 100_000_000, Decimal("100"), Decimal("0.5"), 10),
                FakeTradeTick("BTCUSDT.BINANCE", 1_100_000_000, Decimal("101"), Decimal("1.5"), 11),
                FakeTradeTick("BTCUSDT.BINANCE", 2_100_000_000, Decimal("102"), Decimal("2.0"), 12),
                FakeTradeTick("BTCUSDT.BINANCE", 3_100_000_000, Decimal("103"), Decimal("1.0"), 20),
                FakeTradeTick("BTCUSDT.BINANCE", 4_100_000_000, Decimal("104"), Decimal("1.0"), 22),
                FakeTradeTick("BTCUSDT.BINANCE", 5_100_000_000, Decimal("105"), Decimal("1.0"), 23),
            ],
            [
                FakeDepth(
                    "BTCUSDT.BINANCE",
                    200_000_000,
                    [FakeLevel(Decimal("3"))],
                    [FakeLevel(Decimal("1"))],
                ),
                FakeDepth(
                    "BTCUSDT.BINANCE",
                    1_200_000_000,
                    [FakeLevel(Decimal("1"))],
                    [FakeLevel(Decimal("3"))],
                ),
                FakeDepth(
                    "BTCUSDT.BINANCE",
                    2_200_000_000,
                    [FakeLevel(Decimal("3"))],
                    [FakeLevel(Decimal("1"))],
                ),
                FakeDepth(
                    "BTCUSDT.BINANCE",
                    3_200_000_000,
                    [FakeLevel(Decimal("9"))],
                    [FakeLevel(Decimal("1"))],
                ),
                FakeDepth(
                    "BTCUSDT.BINANCE",
                    4_200_000_000,
                    [FakeLevel(Decimal("9"))],
                    [FakeLevel(Decimal("1"))],
                ),
            ],
            interval_seconds=3,
            orderbook_coverage_seconds=1,
        )

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.start_time, 0)
        self.assertEqual(row.end_time, 3_000_000_000)
        self.assertEqual(row.ts_event, 3_000_000_000)
        self.assertEqual(row.open, 100.0)
        self.assertEqual(row.high, 102.0)
        self.assertEqual(row.low, 100.0)
        self.assertEqual(row.close, 102.0)
        self.assertEqual(row.volume, 4.0)
        self.assertEqual(row.trade_count, 3)
        self.assertEqual(row.trade_id_start, 10)
        self.assertEqual(row.trade_id_end, 12)
        self.assertEqual(row.expected_trade_count, 3)
        self.assertEqual(row.trade_id_gap_count, 0)
        self.assertEqual(row.expected_coverage_count, 3)
        self.assertEqual(row.orderbook_coverage_count, 3)
        self.assertEqual(row.orderbook_sample_count, 3)
        self.assertAlmostEqual(row.orderbook_imbalance_mean, 1 / 6)
        self.assertAlmostEqual(row.orderbook_imbalance_last, 0.5)

    def test_imbalance_basis_can_use_volume_or_trade_count_interaction(self):
        from data.kbar_orderbook_imbalance import kbar_orderbook_imbalance_rows

        trades = [
            FakeTradeTick("BTCUSDT.BINANCE", 1_000_000_000, Decimal("100"), Decimal("2"), 1),
            FakeTradeTick("BTCUSDT.BINANCE", 2_000_000_000, Decimal("101"), Decimal("3"), 2),
        ]
        depths = [
            FakeDepth(
                "BTCUSDT.BINANCE",
                3_000_000_000,
                [FakeLevel(Decimal("3"))],
                [FakeLevel(Decimal("1"))],
            ),
        ]

        volume_row = kbar_orderbook_imbalance_rows(
            trades,
            depths,
            imbalance_basis="volume",
            orderbook_coverage_seconds=60,
        )[0]
        count_row = kbar_orderbook_imbalance_rows(
            trades,
            depths,
            imbalance_basis="trade_count",
            orderbook_coverage_seconds=60,
        )[0]
        mean_row = kbar_orderbook_imbalance_rows(
            trades,
            depths,
            imbalance_basis="mean",
            orderbook_coverage_seconds=60,
        )[0]

        self.assertAlmostEqual(mean_row.imbalance_value, 0.5)
        self.assertAlmostEqual(volume_row.imbalance_x_volume, 2.5)
        self.assertAlmostEqual(volume_row.imbalance_value, 2.5)
        self.assertAlmostEqual(count_row.imbalance_x_trade_count, 1.0)
        self.assertAlmostEqual(count_row.imbalance_value, 1.0)

    def test_write_csv_includes_activity_adjusted_columns(self):
        from data.kbar_orderbook_imbalance import kbar_orderbook_imbalance_rows
        from data.kbar_orderbook_imbalance import write_kbar_orderbook_imbalance_csv

        rows = kbar_orderbook_imbalance_rows(
            [FakeTradeTick("BTCUSDT.BINANCE", 1_000_000_000, Decimal("100"), Decimal("2"), 1)],
            [
                FakeDepth(
                    "BTCUSDT.BINANCE",
                    2_000_000_000,
                    [FakeLevel(Decimal("3"))],
                    [FakeLevel(Decimal("1"))],
                ),
            ],
            orderbook_coverage_seconds=60,
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "aligned.csv"
            rows_written = write_kbar_orderbook_imbalance_csv(rows, output)
            contents = output.read_text(encoding="utf-8")

        self.assertEqual(rows_written, 1)
        self.assertIn("imbalance_basis,imbalance_value,imbalance_x_volume,imbalance_x_trade_count", contents)
        self.assertIn("BTCUSDT.BINANCE", contents)


if __name__ == "__main__":
    unittest.main()
