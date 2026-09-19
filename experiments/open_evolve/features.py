"""Causal TradeTick/Depth10 features, with explicit availability and ordering.

Flow windows are (now - window, now]. Unknown aggressor volume is excluded
from imbalance, but included in the coverage denominator. OFI is the sum of
best-level snapshot flow in quantity units (not normalized), with a fresh
window required after an invalid/stale book. A configured K requires K valid
levels on each side; missing depth is not silently treated as zero liquidity.

Price samples use a fixed availability-time grid anchored at the first event.
A grid boundary is finalized only when an event strictly after it arrives,
using the last book observed at/before the boundary. Return is log(last/first);
volatility is sqrt(sum(log-return ** 2)), without annualization. Missing/stale
samples invalidate the entire price window. No future quote interpolation,
persisted cache, or sorting occurs here. Instances belong to one fold/scenario.

one_sidedness_age_ns is the age of the current run of book_imbalance strictly
above ONE_SIDEDNESS_THRESHOLD (0.45), measured between valid book snapshots:
0 at the snapshot that first exceeds the threshold, increasing while the run
persists, and 0.0 again while at or below threshold. Invalid books neither
start nor end a run. It is declared feature state, not policy memory.

microstructure-v3 adds: trade_size_ratio (last trade size / median trade size
in the flow window, needing >= 5 trades); large_trade_imbalance (signed volume
of trades with size >= 2x the window median, divided by total known volume);
ofi_accel (OFI of the current flow window minus the previous one, needing 2x
flow window of continuous book); depth_concentration_bid/ask (level-1 size /
total size over the configured depth, per side); trade_density (trade count in
the trailing TRADE_DENSITY_WINDOW_NS).
"""

from collections import deque
from dataclasses import dataclass
from math import isfinite, log, sqrt
from statistics import median

from nautilus_trader.model.data import OrderBookDepth10, TradeTick
from nautilus_trader.model.enums import AggressorSide
from nautilus_trader.model.identifiers import InstrumentId

from experiments.open_evolve.contracts import FeatureSnapshot, MarketState


SCHEMA_VERSION = "microstructure-v3"

# Declared feature definitions.
ONE_SIDEDNESS_THRESHOLD = 0.45
TRADE_DENSITY_WINDOW_NS = 1_000_000_000
MIN_TRADES_FOR_SIZE_STATS = 5


@dataclass(frozen=True, slots=True)
class FeatureConfig:
    instrument_id: InstrumentId
    depth: int
    flow_window_ns: int
    price_window_ns: int
    sample_interval_ns: int
    warmup_ns: int
    max_book_age_ns: int
    max_trade_age_ns: int
    min_known_trade_fraction: float

    def __post_init__(self) -> None:
        if not isinstance(self.instrument_id, InstrumentId):
            raise ValueError("instrument_id must be a Nautilus InstrumentId")
        if type(self.depth) is not int or not 1 <= self.depth <= 10:
            raise ValueError("depth must be an integer in [1, 10]")
        for name in ("flow_window_ns", "price_window_ns", "sample_interval_ns",
                     "warmup_ns", "max_book_age_ns", "max_trade_age_ns"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if self.price_window_ns % self.sample_interval_ns:
            raise ValueError("price_window_ns must be a multiple of sample_interval_ns")
        if self.warmup_ns < max(self.flow_window_ns, self.price_window_ns):
            raise ValueError("warmup must cover both windows")
        if not 0 <= self.min_known_trade_fraction <= 1:
            raise ValueError("min_known_trade_fraction must be in [0, 1]")


class FeatureEngine:
    def __init__(self, config: FeatureConfig) -> None:
        self.config = config
        self.reset()

    def reset(self) -> None:
        self._start: int | None = None
        self._now: int | None = None
        self._ordinal = -1
        self._next_sample: int | None = None
        self._book_at: int | None = None
        self._trade_at: int | None = None
        self._top: tuple[float, float, float, float] | None = None
        self._imbalance: float | None = None
        self._conc_bid: float | None = None
        self._conc_ask: float | None = None
        self._last_trade_size: float | None = None
        self._one_sidedness_since: int | None = None
        self._one_sidedness_age: int = 0
        self._ofi_start: int | None = None
        self._flows: deque[tuple[int, float]] = deque()
        self._trades: deque[tuple[int, float, float]] = deque()
        self._prices: deque[float | None] = deque(
            maxlen=self.config.price_window_ns // self.config.sample_interval_ns + 1,
        )

    def update(
        self,
        event: TradeTick | OrderBookDepth10,
        *,
        available_at: int,
        event_ordinal: int,
    ) -> FeatureSnapshot:
        """Consume one event in caller-defined order; rejected inputs change no state.

        available_at is supplied by a trusted replay adapter. ts_init is preserved,
        not interpreted as receive time. Ordinals must strictly increase, including
        for events with the same availability timestamp.
        """
        if not isinstance(event, (TradeTick, OrderBookDepth10)):
            raise TypeError("expected Nautilus TradeTick or OrderBookDepth10")
        if event.instrument_id != self.config.instrument_id:
            raise ValueError("wrong instrument")
        if (type(available_at) is not int or available_at < event.ts_event
                or (self._now is not None and available_at < self._now)):
            raise ValueError("availability must be causal and nondecreasing")
        if type(event_ordinal) is not int or event_ordinal <= self._ordinal:
            raise ValueError("event ordinal must strictly increase")
        if isinstance(event, TradeTick):
            if not isfinite(float(event.price)) or float(event.price) <= 0:
                raise ValueError("trade price must be positive and finite")
        if self._start is None:
            self._start = available_at
            self._next_sample = available_at
        self._sample_before(available_at)
        self._now, self._ordinal = available_at, event_ordinal
        if isinstance(event, OrderBookDepth10):
            self._update_book(event, available_at)
        else:
            size = float(event.size)
            sign = {AggressorSide.BUYER: 1, AggressorSide.SELLER: -1}.get(
                event.aggressor_side, 0,
            )
            self._trades.append((available_at, size, sign * size))
            self._last_trade_size = size
            self._trade_at = available_at
        flow_cutoff = available_at - 2 * self.config.flow_window_ns
        while self._flows and self._flows[0][0] <= flow_cutoff:
            self._flows.popleft()
        cutoff = available_at - self.config.flow_window_ns
        while self._trades and self._trades[0][0] <= cutoff:
            self._trades.popleft()
        return FeatureSnapshot(
            source_ts_event=event.ts_event,
            source_ts_init=event.ts_init,
            source_sequence=(event.sequence if isinstance(event, OrderBookDepth10)
                             and event.sequence != 0 else None),
            available_at=available_at,
            event_ordinal=event_ordinal,
            schema_version=SCHEMA_VERSION,
            market=self._market(available_at),
        )

    def _sample_before(self, now: int) -> None:
        assert self._next_sample is not None
        step = self.config.sample_interval_ns
        # Only the last window matters; bound work even after a long feed outage.
        count = max(0, (now - 1 - self._next_sample) // step + 1)
        if count > self._prices.maxlen:
            self._prices.clear()
            self._next_sample += (count - self._prices.maxlen) * step
        while self._next_sample < now:
            fresh = (self._top is not None and self._book_at is not None
                     and self._next_sample - self._book_at <= self.config.max_book_age_ns)
            mid = (self._top[0] + self._top[1]) / 2 if fresh else None
            self._prices.append(mid)
            self._next_sample += step

    def _update_book(self, event: OrderBookDepth10, now: int) -> None:
        bids = [(float(o.price), float(o.size)) for o in event.bids if float(o.size) > 0]
        asks = [(float(o.price), float(o.size)) for o in event.asks if float(o.size) > 0]
        valid = min(len(bids), len(asks)) >= self.config.depth
        valid = valid and all(isfinite(p) and isfinite(q) and p > 0 for p, q in bids + asks)
        valid = valid and all(bids[i][0] > bids[i + 1][0] for i in range(len(bids) - 1))
        valid = valid and all(asks[i][0] < asks[i + 1][0] for i in range(len(asks) - 1))
        valid = valid and bids[0][0] < asks[0][0]
        previous = self._top
        continuous = (previous is not None and self._book_at is not None
                      and now - self._book_at <= self.config.max_book_age_ns)
        self._book_at = now
        if not valid:
            self._top, self._imbalance, self._ofi_start = None, None, None
            self._flows.clear()
            return
        b, qb = bids[0]
        a, qa = asks[0]
        if continuous:
            pb, pa, pqb, pqa = previous
            flow = ((qb if b >= pb else 0) - (pqb if b <= pb else 0)
                    - (qa if a <= pa else 0) + (pqa if a >= pa else 0))
            self._flows.append((now, flow))
        else:
            self._flows.clear()
            self._ofi_start = now
        self._top = b, a, qb, qa
        bid_qty = sum(q for _, q in bids[:self.config.depth])
        ask_qty = sum(q for _, q in asks[:self.config.depth])
        self._imbalance = (bid_qty - ask_qty) / (bid_qty + ask_qty)
        self._conc_bid = bids[0][1] / bid_qty if bid_qty else None
        self._conc_ask = asks[0][1] / ask_qty if ask_qty else None
        if self._imbalance > ONE_SIDEDNESS_THRESHOLD:
            if self._one_sidedness_since is None:
                self._one_sidedness_since = now
            self._one_sidedness_age = now - self._one_sidedness_since
        else:
            self._one_sidedness_since = None
            self._one_sidedness_age = 0

    def _market(self, now: int) -> MarketState:
        book_age = None if self._book_at is None else now - self._book_at
        trade_age = None if self._trade_at is None else now - self._trade_at
        valid = self._top is not None and book_age <= self.config.max_book_age_ns
        mid = spread = micro = None
        if valid:
            b, a, qb, qa = self._top
            mid = (b + a) / 2
            spread = 10_000 * (a - b) / mid
            micro = 10_000 * (((a * qb + b * qa) / (qb + qa)) / mid - 1)
        total = sum(q for _, q, _ in self._trades)
        known = sum(abs(signed) for _, _, signed in self._trades)
        fraction = known / total if total else None
        imbalance = sum(s for _, _, s in self._trades) / known if known else None
        trade_density = sum(1 for ts_, _, _ in self._trades
                            if ts_ > now - TRADE_DENSITY_WINDOW_NS)
        trade_size_ratio = large_trade_imbalance = None
        sizes = [size for _, size, _ in self._trades]
        if len(sizes) >= MIN_TRADES_FOR_SIZE_STATS:
            window_median = median(sizes)
            if window_median > 0 and self._last_trade_size is not None:
                trade_size_ratio = self._last_trade_size / window_median
            if known:
                large = sum(s for _, size, s in self._trades
                            if size >= 2 * window_median)
                large_trade_imbalance = large / known
        ofi = ofi_prev = None
        if valid and self._ofi_start is not None:
            window = self.config.flow_window_ns
            if now - self._ofi_start >= window:
                ofi = sum(f for ts_, f in self._flows if ts_ > now - window)
            if now - self._ofi_start >= 2 * window:
                ofi_prev = sum(f for ts_, f in self._flows
                               if now - 2 * window < ts_ <= now - window)
        ofi_accel = (ofi - ofi_prev) if ofi is not None and ofi_prev is not None else None
        price_return = volatility = None
        if len(self._prices) == self._prices.maxlen and all(p is not None for p in self._prices):
            prices = list(self._prices)
            returns = [log(right / left) for left, right in zip(prices, prices[1:])]
            price_return = log(prices[-1] / prices[0])
            volatility = sqrt(sum(r * r for r in returns))
        ready = bool(
            valid and now - self._start >= self.config.warmup_ns
            and trade_age is not None and trade_age <= self.config.max_trade_age_ns
            and fraction is not None and fraction >= self.config.min_known_trade_fraction
            and imbalance is not None and ofi is not None and price_return is not None
        )
        return MarketState(
            ready=ready, book_valid=valid, book_age_ns=book_age, trade_age_ns=trade_age,
            mid=mid, spread_bps=spread, microprice_offset_bps=micro,
            book_imbalance=self._imbalance if valid else None,
            ofi=ofi, ofi_accel=ofi_accel, trade_imbalance=imbalance,
            known_trade_fraction=fraction,
            log_return=price_return, realized_volatility=volatility,
            one_sidedness_age_ns=self._one_sidedness_age if valid else None,
            trade_size_ratio=trade_size_ratio,
            large_trade_imbalance=large_trade_imbalance,
            depth_concentration_bid=self._conc_bid if valid else None,
            depth_concentration_ask=self._conc_ask if valid else None,
            trade_density=trade_density,
        )
