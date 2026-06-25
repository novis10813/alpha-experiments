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


class TradePriceTests(unittest.TestCase):
    def test_trade_ticks_to_price_rows_use_canonical_market_price_shape(self):
        from data.trade_prices import trade_ticks_to_price_rows

        rows = trade_ticks_to_price_rows(
            [
                FakeTradeTick(
                    instrument_id="BTCUSDT.BINANCE",
                    ts_event=100,
                    price=Decimal("101.25"),
                ),
            ],
        )

        self.assertEqual(rows[0].ts_event, 100)
        self.assertEqual(rows[0].instrument_id, "BTCUSDT.BINANCE")
        self.assertEqual(rows[0].price, 101.25)

    def test_trade_ticks_to_price_rows_can_downsample_for_visualization(self):
        from data.trade_prices import trade_ticks_to_price_rows

        rows = trade_ticks_to_price_rows(
            [
                FakeTradeTick("BTCUSDT.BINANCE", 100, Decimal("100")),
                FakeTradeTick("BTCUSDT.BINANCE", 200, Decimal("101")),
                FakeTradeTick("BTCUSDT.BINANCE", 300, Decimal("102")),
                FakeTradeTick("BTCUSDT.BINANCE", 400, Decimal("103")),
            ],
            max_rows=2,
        )

        self.assertEqual([row.ts_event for row in rows], [100, 400])

    def test_write_price_rows_csv_writes_report_overlay_columns(self):
        from data.trade_prices import PriceRow
        from data.trade_prices import write_price_rows_csv

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "prices.csv"
            rows_written = write_price_rows_csv(
                [
                    PriceRow(
                        ts_event=100,
                        instrument_id="BTCUSDT.BINANCE",
                        price=101.25,
                    ),
                ],
                output,
            )

            contents = output.read_text(encoding="utf-8")

        self.assertEqual(rows_written, 1)
        self.assertIn("ts_event,instrument_id,price", contents)
        self.assertIn("100,BTCUSDT.BINANCE,101.25", contents)


if __name__ == "__main__":
    unittest.main()
