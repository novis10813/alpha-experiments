import tempfile
import unittest
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


@dataclass(frozen=True)
class FakeLevel:
    price: Decimal
    size: Decimal


@dataclass(frozen=True)
class FakeDepth:
    instrument_id: str
    ts_event: int
    bids: list[FakeLevel | None]
    asks: list[FakeLevel | None]


class OrderBookQuoteTests(unittest.TestCase):
    def test_depths_to_quote_rows_emit_best_bid_ask_mid_and_spread(self):
        from data.orderbook_quotes import depths_to_quote_rows

        rows = depths_to_quote_rows(
            [
                FakeDepth(
                    instrument_id="BTCUSDT.BINANCE",
                    ts_event=1_000_000_000,
                    bids=[FakeLevel(Decimal("100.00"), Decimal("1.5"))],
                    asks=[FakeLevel(Decimal("100.10"), Decimal("2.0"))],
                ),
            ],
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].ts_event, 1_000_000_000)
        self.assertEqual(rows[0].instrument_id, "BTCUSDT.BINANCE")
        self.assertEqual(rows[0].bid, 100.0)
        self.assertEqual(rows[0].ask, 100.1)
        self.assertAlmostEqual(rows[0].mid, 100.05)
        self.assertAlmostEqual(rows[0].spread, 0.1)
        self.assertAlmostEqual(rows[0].spread_bps, 0.1 / 100.05 * 10_000)

    def test_depths_to_quote_rows_resample_to_last_quote_and_fill_empty_buckets(self):
        from data.orderbook_quotes import depths_to_quote_rows

        rows = depths_to_quote_rows(
            [
                FakeDepth(
                    "BTCUSDT.BINANCE",
                    1_100_000_000,
                    [FakeLevel(Decimal("100"), Decimal("1"))],
                    [FakeLevel(Decimal("101"), Decimal("1"))],
                ),
                FakeDepth(
                    "BTCUSDT.BINANCE",
                    1_900_000_000,
                    [FakeLevel(Decimal("102"), Decimal("1"))],
                    [FakeLevel(Decimal("103"), Decimal("1"))],
                ),
                FakeDepth(
                    "BTCUSDT.BINANCE",
                    3_100_000_000,
                    [FakeLevel(Decimal("104"), Decimal("1"))],
                    [FakeLevel(Decimal("105"), Decimal("1"))],
                ),
            ],
            resample_seconds=1,
        )

        self.assertEqual(
            [row.ts_event for row in rows],
            [2_000_000_000, 3_000_000_000, 4_000_000_000],
        )
        self.assertEqual([row.bid for row in rows], [102.0, 102.0, 104.0])
        self.assertEqual([row.ask for row in rows], [103.0, 103.0, 105.0])

    def test_write_quote_rows_csv_writes_expected_columns(self):
        from data.orderbook_quotes import QuoteRow
        from data.orderbook_quotes import write_quote_rows_csv

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "quotes.csv"
            rows_written = write_quote_rows_csv(
                [
                    QuoteRow(
                        ts_event=100,
                        instrument_id="BTCUSDT.BINANCE",
                        bid=100.0,
                        ask=100.2,
                        mid=100.1,
                        spread=0.2,
                        spread_bps=19.98001998001998,
                    ),
                ],
                output,
            )
            contents = output.read_text(encoding="utf-8")

        self.assertEqual(rows_written, 1)
        self.assertIn("ts_event,instrument_id,bid,ask,mid,spread,spread_bps", contents)
        self.assertIn("100,BTCUSDT.BINANCE,100.0,100.2,100.1,0.2", contents)


if __name__ == "__main__":
    unittest.main()
