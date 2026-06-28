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


class TradeFeatureTests(unittest.TestCase):
    def test_trade_ticks_to_feature_rows_resamples_last_price_and_sum_volume(self):
        from data.trade_features import trade_ticks_to_feature_rows

        rows = trade_ticks_to_feature_rows(
            [
                FakeTradeTick("BTCUSDT.BINANCE", 1_100_000_000, Decimal("100"), Decimal("0.5")),
                FakeTradeTick("BTCUSDT.BINANCE", 1_900_000_000, Decimal("101"), Decimal("1.25")),
                FakeTradeTick("BTCUSDT.BINANCE", 2_100_000_000, Decimal("102"), Decimal("2.0")),
            ],
            resample_seconds=1,
        )

        self.assertEqual([row.ts_event for row in rows], [2_000_000_000, 3_000_000_000])
        self.assertEqual([row.price for row in rows], [101.0, 102.0])
        self.assertEqual([row.volume for row in rows], [1.75, 2.0])
        self.assertEqual([row.trade_count for row in rows], [2, 1])

    def test_trade_ticks_to_feature_rows_adds_tick_rule_signed_flow(self):
        from data.trade_features import trade_ticks_to_feature_rows

        rows = trade_ticks_to_feature_rows(
            [
                FakeTradeTick("BTCUSDT.BINANCE", 1_100_000_000, Decimal("100"), Decimal("0.5")),
                FakeTradeTick("BTCUSDT.BINANCE", 1_200_000_000, Decimal("101"), Decimal("1.0")),
                FakeTradeTick("BTCUSDT.BINANCE", 1_300_000_000, Decimal("101"), Decimal("2.0")),
                FakeTradeTick("BTCUSDT.BINANCE", 1_400_000_000, Decimal("100.5"), Decimal("4.0")),
            ],
            resample_seconds=1,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].buy_trade_count, 2)
        self.assertEqual(rows[0].sell_trade_count, 1)
        self.assertEqual(rows[0].buy_volume, 3.0)
        self.assertEqual(rows[0].sell_volume, 4.0)
        self.assertEqual(rows[0].signed_trade_count, 1)
        self.assertEqual(rows[0].signed_volume, -1.0)
        self.assertAlmostEqual(rows[0].trade_imbalance, 1 / 3)
        self.assertAlmostEqual(rows[0].volume_imbalance, -1 / 7)

    def test_write_feature_rows_csv_writes_price_and_volume_columns(self):
        from data.trade_features import TradeFeatureRow
        from data.trade_features import write_feature_rows_csv

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "features.csv"
            rows_written = write_feature_rows_csv(
                [
                    TradeFeatureRow(
                        ts_event=100,
                        instrument_id="BTCUSDT.BINANCE",
                        price=101.25,
                        volume=2.5,
                        trade_count=3,
                        buy_trade_count=2,
                        sell_trade_count=1,
                        buy_volume=2.0,
                        sell_volume=0.5,
                        signed_trade_count=1,
                        signed_volume=1.5,
                        trade_imbalance=1 / 3,
                        volume_imbalance=0.6,
                    ),
                ],
                output,
            )

            contents = output.read_text(encoding="utf-8")

        self.assertEqual(rows_written, 1)
        self.assertIn(
            "ts_event,instrument_id,price,volume,trade_count,buy_trade_count,sell_trade_count,"
            "buy_volume,sell_volume,signed_trade_count,signed_volume,trade_imbalance,volume_imbalance",
            contents,
        )
        self.assertIn("100,BTCUSDT.BINANCE,101.25,2.5,3,2,1,2.0,0.5,1,1.5", contents)


if __name__ == "__main__":
    unittest.main()
