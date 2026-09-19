from dataclasses import FrozenInstanceError, replace
from math import log, sqrt
import unittest

from nautilus_trader.model.data import BookOrder, OrderBookDepth10, TradeTick
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import InstrumentId, TradeId
from nautilus_trader.model.objects import Price, Quantity

from experiments.open_evolve.features import FeatureConfig, FeatureEngine


INSTRUMENT = InstrumentId.from_str("BTCUSDT.BINANCE")


def book(ts, *, bid=99, ask=101, bid_qty=3, ask_qty=1, sequence=1, ts_init=None):
    return OrderBookDepth10(
        instrument_id=INSTRUMENT,
        bids=[BookOrder(OrderSide.BUY, Price.from_int(bid), Quantity.from_int(bid_qty), 0)],
        asks=[BookOrder(OrderSide.SELL, Price.from_int(ask), Quantity.from_int(ask_qty), 0)],
        bid_counts=[1], ask_counts=[1], flags=0, sequence=sequence,
        ts_event=ts, ts_init=ts if ts_init is None else ts_init,
    )


def trade(ts, *, size=1, side=AggressorSide.BUYER):
    return TradeTick(
        INSTRUMENT, Price.from_int(100), Quantity.from_int(size),
        side, TradeId(str(ts)), ts, ts,
    )


def config(**kwargs):
    return replace(FeatureConfig(
        instrument_id=INSTRUMENT, depth=1, flow_window_ns=20,
        price_window_ns=20, sample_interval_ns=10, warmup_ns=20,
        max_book_age_ns=30, max_trade_age_ns=20, min_known_trade_fraction=0.5,
    ), **kwargs)


class FeatureEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = FeatureEngine(config())
        self.ordinal = -1

    def push(self, event, *, now=None):
        self.ordinal += 1
        return self.engine.update(
            event, available_at=event.ts_event if now is None else now,
            event_ordinal=self.ordinal,
        )

    def test_quote_features_and_immutable_envelope(self):
        snapshot = self.push(book(10, sequence=42, ts_init=999), now=15)
        state = snapshot.market
        self.assertEqual(state.mid, 100)
        self.assertEqual(state.spread_bps, 200)
        self.assertAlmostEqual(state.microprice_offset_bps, 50)
        self.assertEqual(state.book_imbalance, 0.5)
        self.assertFalse(state.ready)
        self.assertIsNone(state.ofi)
        self.assertIsNone(state.trade_imbalance)
        self.assertEqual((snapshot.source_ts_event, snapshot.source_ts_init), (10, 999))
        self.assertEqual(snapshot.source_sequence, 42)
        self.assertEqual(snapshot.available_at, 15)
        with self.assertRaises(FrozenInstanceError):
            state.mid = 200
        self.assertFalse(hasattr(state, "source_ts_event"))
        self.assertIsNone(self.push(book(16, sequence=0)).source_sequence)

    def test_microprice_is_bounded_by_half_spread(self):
        for bid_qty, ask_qty in ((1, 1), (1, 1000000), (1000000, 1), (3, 7)):
            with self.subTest(bid_qty=bid_qty, ask_qty=ask_qty):
                engine = FeatureEngine(config())
                state = engine.update(book(0, bid_qty=bid_qty, ask_qty=ask_qty),
                                      available_at=0, event_ordinal=0).market
                self.assertLessEqual(abs(state.microprice_offset_bps), state.spread_bps / 2 + 1e-9)

    def test_signed_flow_unknown_coverage_and_open_left_window(self):
        self.push(book(0))
        self.push(trade(1, size=3))
        self.push(trade(2, size=1, side=AggressorSide.SELLER))
        state = self.push(trade(3, size=4, side=AggressorSide.NO_AGGRESSOR)).market
        self.assertEqual(state.known_trade_fraction, 0.5)
        self.assertEqual(state.trade_imbalance, 0.5)
        # t=1 is excluded from (1, 21], leaving one sell and four unknown.
        state = self.push(book(21)).market
        self.assertEqual(state.known_trade_fraction, 0.2)
        self.assertEqual(state.trade_imbalance, -1)
        self.assertFalse(state.ready)
        state = self.push(book(24)).market
        self.assertIsNone(state.known_trade_fraction)
        self.assertIsNone(state.trade_imbalance)

    def test_one_sidedness_episode_age(self):
        # No book yet: field absent.
        state = self.push(trade(0)).market
        self.assertIsNone(state.one_sidedness_age_ns)
        # First above-threshold snapshot starts the episode at age 0.
        state = self.push(book(10, bid_qty=3, ask_qty=1)).market
        self.assertEqual(state.one_sidedness_age_ns, 0)
        # Age grows between valid snapshots while above threshold.
        state = self.push(book(15, bid_qty=3, ask_qty=1)).market
        self.assertEqual(state.one_sidedness_age_ns, 5)
        state = self.push(book(25, bid_qty=3, ask_qty=1)).market
        self.assertEqual(state.one_sidedness_age_ns, 15)
        # At or below threshold: not an episode (strict > 0.45).
        state = self.push(book(30, bid_qty=2, ask_qty=2)).market
        self.assertEqual(state.one_sidedness_age_ns, 0)
        state = self.push(book(35, bid_qty=29, ask_qty=11)).market  # exactly 0.45
        self.assertEqual(state.one_sidedness_age_ns, 0)
        # A new crossing starts a fresh episode.
        state = self.push(book(40, bid_qty=3, ask_qty=1)).market
        self.assertEqual(state.one_sidedness_age_ns, 0)
        state = self.push(book(50, bid_qty=3, ask_qty=1)).market
        self.assertEqual(state.one_sidedness_age_ns, 10)

    def test_one_sidedness_age_invalid_book_preserves_episode(self):
        self.push(book(10, bid_qty=3, ask_qty=1))
        # Invalid book: field None, but the episode is neither started nor ended.
        state = self.push(book(15, ask_qty=0)).market
        self.assertFalse(state.book_valid)
        self.assertIsNone(state.one_sidedness_age_ns)
        state = self.push(book(25, bid_qty=3, ask_qty=1)).market
        self.assertEqual(state.one_sidedness_age_ns, 15)

    def test_trade_size_and_density_features(self):
        engine = FeatureEngine(config(
            flow_window_ns=2_000_000_000, price_window_ns=2_000_000_000,
            sample_interval_ns=1_000_000_000, warmup_ns=2_000_000_000,
            max_book_age_ns=5_000_000_000, max_trade_age_ns=2_000_000_000,
        ))
        ordinal = -1

        def push(event, *, now=None):
            nonlocal ordinal
            ordinal += 1
            return engine.update(event, available_at=event.ts_event if now is None else now,
                                 event_ordinal=ordinal)

        push(book(0))
        state = push(trade(1_000_000_000, size=1)).market
        # One trade: no size stats yet (need >= 5), density counts it.
        self.assertIsNone(state.trade_size_ratio)
        self.assertIsNone(state.large_trade_imbalance)
        self.assertEqual(state.trade_density, 1)
        for t in (1_200_000_000, 1_400_000_000, 1_600_000_000, 1_800_000_000):
            push(trade(t, size=1))
        # Five 1-unit trades: median 1, last 1 -> ratio 1, no large trades.
        state = push(trade(2_000_000_000, size=1)).market
        self.assertEqual(state.trade_size_ratio, 1.0)
        self.assertEqual(state.large_trade_imbalance, 0.0)
        self.assertEqual(state.trade_density, 5)  # (1.0e9, 2.0e9]
        # A 4-unit buy: ratio 4, large imbalance +4/10.
        state = push(trade(2_200_000_000, size=4)).market
        self.assertEqual(state.trade_size_ratio, 4.0)
        self.assertAlmostEqual(state.large_trade_imbalance, 4 / 10)
        # A 4-unit sell cancels the large imbalance: (4 - 4)/14.
        state = push(trade(2_400_000_000, size=4, side=AggressorSide.SELLER)).market
        self.assertAlmostEqual(state.large_trade_imbalance, 0.0)
        self.assertEqual(state.trade_size_ratio, 4.0)

    def test_ofi_acceleration(self):
        # Test flow window is 20; acceleration needs 2x = 40 of history.
        self.push(book(0))
        self.push(book(10, bid_qty=5, ask_qty=2))  # flow +1 at t=10
        state = self.push(book(20, bid_qty=5, ask_qty=2)).market
        self.assertEqual(state.ofi, 1)  # (0, 20]
        self.assertIsNone(state.ofi_accel)  # only 20 < 40 of history
        state = self.push(book(40, bid_qty=5, ask_qty=2)).market
        # ofi (20, 40] = 0; previous (0, 20] = +1 -> accel -1.
        self.assertEqual(state.ofi, 0)
        self.assertEqual(state.ofi_accel, -1)
        state = self.push(book(60, bid_qty=5, ask_qty=2)).market
        # ofi (40, 60] = 0; previous (20, 40] = 0 -> accel 0.
        self.assertEqual(state.ofi_accel, 0)

    def test_depth_concentration(self):
        engine = FeatureEngine(config(depth=2))

        def book2(ts, b1q, b2q, a1q, a2q):
            bids = [BookOrder(OrderSide.BUY, Price.from_int(100), Quantity.from_int(b1q), 0),
                    BookOrder(OrderSide.BUY, Price.from_int(99), Quantity.from_int(b2q), 0)]
            asks = [BookOrder(OrderSide.SELL, Price.from_int(101), Quantity.from_int(a1q), 0),
                    BookOrder(OrderSide.SELL, Price.from_int(102), Quantity.from_int(a2q), 0)]
            return OrderBookDepth10(instrument_id=INSTRUMENT, bids=bids, asks=asks,
                                    bid_counts=[2, 2], ask_counts=[2, 2], flags=0,
                                    sequence=1, ts_event=ts, ts_init=ts)

        state = engine.update(book2(0, 1, 7, 5, 3), available_at=0, event_ordinal=0).market
        self.assertAlmostEqual(state.depth_concentration_bid, 1 / 8)
        self.assertAlmostEqual(state.depth_concentration_ask, 5 / 8)

    def test_ofi_size_changes_and_price_changes(self):
        self.push(book(0))
        # Same prices: bid +2, ask +1 => +1.
        self.push(book(10, bid_qty=5, ask_qty=2))
        # Bid improves => +4. Ask worsens => +2 (previous ask qty).
        self.push(book(15, bid=100, ask=102, bid_qty=4, ask_qty=3))
        state = self.push(book(20, bid=100, ask=102, bid_qty=4, ask_qty=3)).market
        self.assertEqual(state.ofi, 7)
        # Bid worsens => -4. Ask improves => -2.
        state = self.push(book(21, bid=99, ask=101, bid_qty=6, ask_qty=2)).market
        self.assertEqual(state.ofi, 1)
        # t=10 contribution expires exactly at 30.
        state = self.push(book(30, bid=99, ask=101, bid_qty=6, ask_qty=2)).market
        self.assertEqual(state.ofi, 0)

    def test_fixed_grid_returns_and_volatility_are_causal(self):
        self.push(book(0))  # grid t=0: 100
        self.push(book(10, bid=109, ask=111))  # grid t=10: 110
        self.push(book(20, bid=120, ask=122))  # grid t=20: 121, not finalized yet
        state = self.push(trade(21)).market
        self.assertAlmostEqual(state.log_return, log(1.21))
        self.assertAlmostEqual(state.realized_volatility, sqrt(2) * log(1.1))
        self.assertTrue(state.ready)

    def test_same_timestamp_later_event_does_not_rewrite_earlier_snapshot(self):
        first = self.push(book(0))
        second = self.push(book(0, bid=109, ask=111))
        self.assertEqual(first.market.mid, 100)
        self.assertEqual(second.market.mid, 110)
        self.assertEqual(second.event_ordinal, first.event_ordinal + 1)
        self.push(book(20, bid=120, ask=122))
        state = self.push(trade(21)).market
        # Final sample at t=0 uses the last same-time event only after time advances.
        self.assertAlmostEqual(state.log_return, log(121 / 110))

    def test_invalid_book_clears_ofi_and_requires_new_warmup(self):
        self.push(book(0))
        self.push(book(20))
        state = self.push(book(21, bid=101, ask=101)).market
        self.assertFalse(state.book_valid)
        self.assertIsNone(state.mid)
        self.assertIsNone(state.ofi)
        self.assertFalse(state.ready)
        state = self.push(book(22)).market
        self.assertTrue(state.book_valid)
        self.assertIsNone(state.ofi)
        self.assertIsNotNone(self.push(book(42)).market.ofi)

    def test_empty_book_and_crossed_book_are_invalid(self):
        for event in [book(0, bid_qty=0), book(1, bid=102, ask=101)]:
            with self.subTest(event=event):
                state = self.push(event).market
                self.assertFalse(state.book_valid)
                self.assertFalse(state.ready)

    def test_configured_depth_requires_available_levels(self):
        self.engine = FeatureEngine(config(depth=10))
        self.assertFalse(self.push(book(0)).market.book_valid)

    def test_ten_level_imbalance_and_unsorted_depth(self):
        bids = [BookOrder(OrderSide.BUY, Price.from_int(99 - i),
                          Quantity.from_int(i + 1), i) for i in range(10)]
        asks = [BookOrder(OrderSide.SELL, Price.from_int(101 + i),
                          Quantity.from_int(1), i) for i in range(10)]
        self.engine = FeatureEngine(config(depth=10))
        event = OrderBookDepth10(INSTRUMENT, bids, asks, [1] * 10, [1] * 10, 0, 1, 0, 0)
        state = self.push(event).market
        self.assertTrue(state.book_valid)
        self.assertAlmostEqual(state.book_imbalance, (55 - 10) / (55 + 10))
        self.assertEqual(state.microprice_offset_bps, 0)
        event = OrderBookDepth10(INSTRUMENT, list(reversed(bids)), asks,
                                 [1] * 10, [1] * 10, 0, 2, 1, 1)
        self.assertFalse(self.push(event).market.book_valid)

    def test_unknown_only_flow_never_becomes_ready(self):
        self.push(book(0))
        self.push(book(20))
        state = self.push(trade(21, side=AggressorSide.NO_AGGRESSOR)).market
        self.assertEqual(state.known_trade_fraction, 0)
        self.assertIsNone(state.trade_imbalance)
        self.assertFalse(state.ready)

    def test_stale_quotes_and_long_gap_do_not_fill_from_future_book(self):
        self.push(book(0))
        state = self.push(trade(31)).market
        self.assertEqual(state.book_age_ns, 31)
        self.assertFalse(state.book_valid)
        self.assertIsNone(state.mid)
        state = self.push(book(10**12)).market
        self.assertTrue(state.book_valid)
        self.assertIsNone(state.log_return)
        self.assertIsNone(state.ofi)
        self.assertFalse(state.ready)

    def test_rejected_order_or_instrument_does_not_advance_engine(self):
        self.push(book(10))
        wrong = TradeTick(
            InstrumentId.from_str("ETHUSDT.BINANCE"), Price.from_int(100),
            Quantity.from_int(1), AggressorSide.BUYER, TradeId("wrong"), 11, 11,
        )
        for event, now, ordinal in [
            (book(9), 9, 1), (book(11), 10, 1), (book(10), 10, 0),
            (wrong, 11, 1), (book(11), 11.0, 1), (book(11), 11, True),
        ]:
            with self.subTest(now=now, ordinal=ordinal, event=event):
                with self.assertRaises(ValueError):
                    self.engine.update(event, available_at=now, event_ordinal=ordinal)
        self.assertEqual(self.push(book(11)).available_at, 11)

    def test_reset_matches_fresh_engine_and_future_suffix_cannot_change_prefix(self):
        events = [book(0), trade(5), book(10), book(20), trade(21)]
        first = [self.push(event) for event in events]
        saved = repr(first)
        self.push(book(100, bid=999, ask=1001))
        self.assertEqual(repr(first), saved)
        self.engine.reset()
        self.ordinal = -1
        self.assertEqual([self.push(event) for event in events], first)
        fresh = FeatureEngine(config())
        self.assertEqual([
            fresh.update(event, available_at=event.ts_event, event_ordinal=i)
            for i, event in enumerate(events)
        ], first)

    def test_config_has_no_implicit_windows_or_thresholds(self):
        for values in [
            {"depth": 0}, {"depth": 11}, {"depth": True},
            {"sample_interval_ns": 0}, {"price_window_ns": 21},
            {"warmup_ns": 10}, {"max_book_age_ns": -1},
            {"min_known_trade_fraction": float("nan")},
            {"min_known_trade_fraction": 1.1},
        ]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                config(**values)


if __name__ == "__main__":
    unittest.main()
