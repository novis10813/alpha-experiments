import unittest
from dataclasses import dataclass


@dataclass(frozen=True)
class PricePoint:
    ts_event: int
    instrument_id: str
    price: float


class CommonKbarTests(unittest.TestCase):
    def test_aggregate_price_kbars_uses_fixed_bucket_boundaries_per_instrument(self):
        from common.kbars import aggregate_price_kbars

        bars = aggregate_price_kbars(
            [
                PricePoint(61_000_000_000, "ETHUSDT.BINANCE", 2000),
                PricePoint(1_000_000_000, "BTCUSDT.BINANCE", 100),
                PricePoint(59_000_000_000, "BTCUSDT.BINANCE", 99),
                PricePoint(30_000_000_000, "ETHUSDT.BINANCE", 2010),
                PricePoint(119_000_000_000, "BTCUSDT.BINANCE", 101),
            ],
            60,
            lambda point: point.ts_event,
            lambda point: point.instrument_id,
            lambda point: point.price,
        )

        self.assertEqual(
            [(bar.start_time, bar.end_time, bar.instrument_id) for bar in bars],
            [
                (0, 60_000_000_000, "BTCUSDT.BINANCE"),
                (0, 60_000_000_000, "ETHUSDT.BINANCE"),
                (60_000_000_000, 120_000_000_000, "BTCUSDT.BINANCE"),
                (60_000_000_000, 120_000_000_000, "ETHUSDT.BINANCE"),
            ],
        )
        btc_first = bars[0]
        self.assertEqual(btc_first.open, 100)
        self.assertEqual(btc_first.high, 100)
        self.assertEqual(btc_first.low, 99)
        self.assertEqual(btc_first.close, 99)
        self.assertEqual(btc_first.ts_event, btc_first.end_time)


if __name__ == "__main__":
    unittest.main()
