import unittest
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class FakeLevel:
    size: Decimal


@dataclass(frozen=True)
class FakeDepth:
    instrument_id: str
    ts_event: int
    bids: list[FakeLevel]
    asks: list[FakeLevel]


class OrderBookImbalanceTests(unittest.TestCase):
    def test_imbalance_value_uses_bid_minus_ask_over_total_depth(self):
        from alphas.orderbook_imbalance import orderbook_imbalance_value

        depth = FakeDepth(
            instrument_id="BTCUSDT.BINANCE",
            ts_event=1,
            bids=[FakeLevel(Decimal("3.0")), FakeLevel(Decimal("2.0"))],
            asks=[FakeLevel(Decimal("1.5")), FakeLevel(Decimal("0.5"))],
        )

        self.assertAlmostEqual(orderbook_imbalance_value(depth), 0.42857142857142855)

    def test_imbalance_value_is_zero_when_book_has_no_size(self):
        from alphas.orderbook_imbalance import orderbook_imbalance_value

        depth = FakeDepth(
            instrument_id="BTCUSDT.BINANCE",
            ts_event=1,
            bids=[FakeLevel(Decimal("0"))],
            asks=[FakeLevel(Decimal("0"))],
        )

        self.assertEqual(orderbook_imbalance_value(depth), 0.0)

    def test_imbalance_signals_use_canonical_alpha_shape(self):
        from alphas.orderbook_imbalance import orderbook_imbalance_signals

        depth = FakeDepth(
            instrument_id="ETHUSDT.BINANCE",
            ts_event=123,
            bids=[FakeLevel(Decimal("4"))],
            asks=[FakeLevel(Decimal("1"))],
        )

        signal = orderbook_imbalance_signals([depth])[0]

        self.assertEqual(signal.ts_event, 123)
        self.assertEqual(signal.instrument_id, "ETHUSDT.BINANCE")
        self.assertEqual(signal.alpha_name, "orderbook_imbalance_depth10")
        self.assertEqual(signal.value, 0.6)

    def test_past_week_range_uses_seven_days_ending_at_now(self):
        from alphas.orderbook_imbalance import past_week_range

        now = datetime(2026, 6, 25, 0, 0, tzinfo=UTC)

        self.assertEqual(
            past_week_range(now),
            ("2026-06-18T00:00:00Z", "2026-06-25T00:00:00Z"),
        )


if __name__ == "__main__":
    unittest.main()
