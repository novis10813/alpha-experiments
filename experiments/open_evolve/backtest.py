"""Trusted single-instrument L2 taker runner.

Supports linear quote-settled instruments, netting, and no funding/borrowing.
Market observation follows catalog ts_init (explicit receive-clock assumption).
Observation/compute delay defers immutable snapshots, not exchange book updates.
Confirmation latency is zero; contracts requesting other accounting are rejected.
"""

from dataclasses import dataclass, asdict
from decimal import Decimal
from math import isfinite

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.backtest.models import LatencyModel
from nautilus_trader.config import LoggingConfig
from nautilus_trader.model.data import OrderBookDepth10, TradeTick
from nautilus_trader.model.enums import AccountType, BookType, OmsType, OrderSide
from nautilus_trader.model.objects import Money
from nautilus_trader.trading.strategy import Strategy

from experiments.open_evolve.contracts import PositionState, TargetPosition
from experiments.open_evolve.features import FeatureConfig, FeatureEngine
from experiments.open_evolve.policy import Policy, InvalidPolicy
from experiments.open_evolve.runtime import PolicyProcess
from experiments.open_evolve.evaluation import Fill, Quote, MetricConfig, metrics, markouts


@dataclass(frozen=True)
class Fold:
    name: str
    warmup_start: int
    start: int
    entry_end: int
    end: int
    tail_end: int

    def __post_init__(self):
        if not self.name or not 0 <= self.warmup_start < self.start < self.entry_end < self.end < self.tail_end:
            raise ValueError("invalid fold boundaries")
        if self.tail_end - self.end < 1_000_000_000:
            raise ValueError("fold needs at least 1s markout tail")


@dataclass(frozen=True)
class Scenario:
    name: str
    observation_ns: int
    compute_ns: int
    order_ns: int

    def __post_init__(self):
        if not self.name or any(type(v) is not int or v < 0 for v in (self.observation_ns, self.compute_ns, self.order_ns)):
            raise ValueError("invalid latency scenario")


@dataclass(frozen=True)
class ExecutionConfig:
    quantity: str
    initial_cash: str
    account_type: str
    allow_short: bool
    max_holding_ns: int
    max_loss: float
    min_order_interval_ns: int
    max_orders: int
    max_depth_fraction: float
    equity_interval_ns: int

    def __post_init__(self):
        if (not Decimal(self.quantity).is_finite() or Decimal(self.quantity) <= 0
                or not Decimal(self.initial_cash).is_finite() or Decimal(self.initial_cash) <= 0
                or self.account_type not in ("CASH", "MARGIN")
                or (self.account_type == "CASH" and self.allow_short)
                or self.max_holding_ns <= 0 or self.min_order_interval_ns < 0
                or self.max_orders < 1 or not isfinite(self.max_loss) or self.max_loss <= 0
                or not 0 < self.max_depth_fraction <= 1 or self.equity_interval_ns <= 0):
            raise ValueError("invalid execution configuration")


class PolicyStrategy(Strategy):
    def __init__(self, instrument, policy, features, execution, fold, scenario, snapshots=None):
        super().__init__()
        self.instrument = instrument
        self.policy = policy
        self.features = FeatureEngine(features)
        self.execution = execution
        self.fold = fold
        self.scenario = scenario
        self.snapshots = snapshots
        self.ordinal = -1
        self.pending = None
        self.quantity = 0.0
        self.entry_price = None
        self.entry_at = None
        self.cash = float(execution.initial_cash)
        self.trip_cash = None
        self.trips = []
        self.fills = []
        self.quotes = []
        self.equity = [self.cash]
        self.equity_times = [fold.start]
        self.next_equity = fold.start + execution.equity_interval_ns
        self.last_mid = None
        self.book_at = None
        self.depth_bid = self.depth_ask = 0.0
        self.count = 0
        self.last_order = -execution.min_order_interval_ns
        self.forced = False
        self.killed = False
        self.failure = None
        self.finalized = False
        self.last_market = None
        self.target_history = []
        self.held_ns = 0
        self.holding_durations_ns = []

    def on_start(self):
        self.subscribe_trade_ticks(self.instrument.id)
        self.subscribe_order_book_depth(self.instrument.id, BookType.L2_MBP, depth=10)
        import pandas as pd
        self.clock.set_time_alert(
            name="force-exit", alert_time=pd.Timestamp(self.fold.entry_end, unit="ns", tz="UTC"),
            callback=lambda event: self._risk_exit(),
        )

    def _risk_exit(self):
        now = self.clock.timestamp_ns()
        expired = self.entry_at is not None and now - self.entry_at >= self.execution.max_holding_ns
        # An old holding timer may fire during a newer position. It must not
        # invoke candidate code using an undelayed exchange-side snapshot.
        if self.last_market is not None and (expired or now >= self.fold.entry_end or self.killed):
            self._decide(self.last_market)

    def _equity(self):
        if self.quantity and self.last_mid is None:
            raise ValueError("cannot mark open position without valid book")
        return self.cash + self.quantity * (self.last_mid or 0)

    def _sample(self, now):
        while self.next_equity < min(now, self.fold.end + 1):
            if (self.quantity and (self.book_at is None or
                    self.next_equity - self.book_at > self.features.config.max_book_age_ns)):
                raise ValueError("stale quote while marking an open position")
            self.equity.append(self._equity())
            self.equity_times.append(self.next_equity)
            self.next_equity += self.execution.equity_interval_ns

    def on_order_book_depth(self, depth):
        self._event(depth)

    def on_trade_tick(self, tick):
        self._event(tick)

    def _event(self, event):
        if self.failure:
            return
        now = self.clock.timestamp_ns()
        self.ordinal += 1
        try:
            self._sample(now)
            if self.snapshots is None:
                snapshot = self.features.update(event, available_at=now, event_ordinal=self.ordinal)
            else:
                snapshot = self.snapshots[self.ordinal]
                if (snapshot.available_at != now or snapshot.source_ts_event != event.ts_event
                        or snapshot.source_ts_init != event.ts_init or snapshot.event_ordinal != self.ordinal):
                    raise ValueError("feature cache replay mismatch")
            self.last_market = snapshot.market
            if isinstance(event, OrderBookDepth10):
                self.last_mid = snapshot.market.mid
                self.book_at = now
                self.depth_bid = sum(float(o.size) for o in event.bids)
                self.depth_ask = sum(float(o.size) for o in event.asks)
                self.quotes.append(Quote(now, self.ordinal, self.last_mid))
            if now >= self.fold.end:
                if not self.finalized:
                    if abs(self.quantity) > 1e-10 or self.pending is not None:
                        raise ValueError("fold ended with open position or pending order")
                    self.finalized = True
                return
            if now < self.fold.start:
                return
            delay = self.scenario.observation_ns + self.scenario.compute_ns
            if delay:
                # Clock accepts nanosecond timestamps through pandas Timestamp.
                import pandas as pd
                self.clock.set_time_alert(
                    name=f"policy-{self.ordinal}",
                    alert_time=pd.Timestamp(now + delay, unit="ns", tz="UTC"),
                    callback=lambda timer, state=snapshot.market: self._decide(state),
                )
            else:
                self._decide(snapshot.market)
        except InvalidPolicy as exc:
            self.failure = ("invalid_candidate", str(exc))
        except (ValueError, ArithmeticError) as exc:
            self.failure = ("constraint_failed", str(exc))

    def _decide(self, market):
        if self.failure:
            return
        now = self.clock.timestamp_ns()
        if now >= self.fold.end:
            return
        try:
            forced = (now >= self.fold.entry_end or self.killed
                      or (self.entry_at is not None and now - self.entry_at >= self.execution.max_holding_ns))
            if self._equity() - float(self.execution.initial_cash) <= -self.execution.max_loss:
                self.killed = forced = True
            position = PositionState(
                self.quantity, self.entry_price,
                now - self.entry_at if self.entry_at is not None else 0,
                (10_000 * (1 if self.quantity > 0 else -1) * (market.mid / self.entry_price - 1)
                 if self.entry_price and market.mid else None),
                self.pending is not None,
            )
            delayed_age = self.scenario.observation_ns + self.scenario.compute_ns
            observation_fresh = (
                market.book_age_ns is not None
                and market.book_age_ns + delayed_age <= self.features.config.max_book_age_ns
                and market.trade_age_ns is not None
                and market.trade_age_ns + delayed_age <= self.features.config.max_trade_age_ns
            )
            if (not market.ready or not observation_fresh) and not forced:
                return
            target = TargetPosition.FLAT if forced else self.policy(market, position, allow_short=self.execution.allow_short)
            last = self.target_history[-1] if self.target_history else None
            if last is None or last["target"] != target.name or last["forced"] != forced:
                self.target_history.append({"ts": now, "target": target.name, "forced": forced})
            if self.pending is not None:
                return
            desired = target.value * float(self.execution.quantity)
            if self.quantity * desired < 0:
                desired = 0.0
            delta = desired - self.quantity
            if abs(delta) < 1e-10:
                return
            if (self.last_mid is None or self.book_at is None
                    or now - self.book_at > self.features.config.max_book_age_ns):
                return
            if now - self.last_order < self.execution.min_order_interval_ns:
                return
            if self.count >= self.execution.max_orders:
                raise ValueError("order limit exhausted")
            depth = self.depth_ask if delta > 0 else self.depth_bid
            if abs(delta) > depth * self.execution.max_depth_fraction:
                return
            qty = self.instrument.make_qty(abs(delta))
            if self.instrument.min_notional and float(qty) * self.last_mid < float(self.instrument.min_notional):
                raise ValueError("order below minimum notional")
            order = self.order_factory.market(
                instrument_id=self.instrument.id,
                order_side=OrderSide.BUY if delta > 0 else OrderSide.SELL,
                quantity=qty,
            )
            self.pending = order
            self.forced = forced
            self.count += 1
            self.last_order = now
            self.submit_order(order)
        except InvalidPolicy as exc:
            self.failure = ("invalid_candidate", str(exc))
        except (ValueError, ArithmeticError) as exc:
            self.failure = ("constraint_failed", str(exc))

    def on_order_filled(self, event):
        try:
            self._sample(event.ts_event)
        except ValueError as exc:
            self.failure = ("constraint_failed", str(exc))
        side = 1 if event.order_side == OrderSide.BUY else -1
        quantity, price = float(event.last_qty), float(event.last_px)
        if event.commission.currency != self.instrument.quote_currency:
            self.failure = ("infrastructure_error", "unsupported fee currency")
            return
        fee = float(event.commission)
        entry = abs(self.quantity) < 1e-10 or self.quantity * side > 0
        if abs(self.quantity) < 1e-10:
            self.trip_cash = self.cash
            self.entry_at = event.ts_event
            self.entry_price = price
            import pandas as pd
            self.clock.set_time_alert(
                name=f"holding-{self.count}",
                alert_time=pd.Timestamp(event.ts_event + self.execution.max_holding_ns, unit="ns", tz="UTC"),
                callback=lambda timer: self._risk_exit(),
            )
        elif entry:
            self.entry_price = (abs(self.quantity) * self.entry_price + quantity * price) / (abs(self.quantity) + quantity)
        self.cash -= side * quantity * price + fee
        self.quantity += side * quantity
        self.fills.append(Fill(event.ts_event, self.ordinal, side, quantity, price, fee, entry, self.forced))
        if abs(self.quantity) < 1e-10:
            self.quantity = 0.0
            self.trips.append(self.cash - self.trip_cash)
            duration = event.ts_event - self.entry_at
            self.held_ns += duration
            self.holding_durations_ns.append(duration)
            self.entry_at = self.entry_price = self.trip_cash = None
        if self.pending is not None and self.pending.is_closed:
            self.pending = None

    def on_order_event(self, event):
        if self.pending is not None and self.pending.is_closed:
            if self.pending.is_rejected or self.pending.is_denied:
                self.failure = ("constraint_failed", "order rejected or denied")
            self.pending = None


def run_backtest(instrument, trades, depths, policy: Policy, features: FeatureConfig,
                 execution: ExecutionConfig, fold: Fold, scenario: Scenario, metric_config: MetricConfig,
                 *, snapshots=None):
    if (instrument.is_inverse or float(instrument.multiplier) != 1
            or instrument.id != features.instrument_id):
        raise ValueError("runner supports only matching linear unit-multiplier instruments")
    trades = [e for e in trades if fold.warmup_start <= e.ts_init <= fold.tail_end]
    depths = [e for e in depths if fold.warmup_start <= e.ts_init <= fold.tail_end]
    qty = instrument.make_qty(Decimal(execution.quantity))
    if qty.as_decimal() != Decimal(execution.quantity):
        raise ValueError("quantity violates instrument precision")
    if instrument.min_quantity and qty < instrument.min_quantity:
        raise ValueError("quantity below instrument minimum")
    if instrument.max_quantity and qty > instrument.max_quantity:
        raise ValueError("quantity exceeds instrument maximum")
    if Decimal(execution.quantity) % instrument.size_increment.as_decimal():
        raise ValueError("quantity violates instrument size increment")
    if (fold.end - fold.start) % execution.equity_interval_ns:
        raise ValueError("equity grid must divide scoring period")
    if fold.start - fold.warmup_start < features.warmup_ns:
        raise ValueError("insufficient warmup")
    if fold.end - fold.entry_end <= scenario.order_ns + scenario.compute_ns + scenario.observation_ns:
        raise ValueError("exit buffer must exceed latency")
    if not trades or not depths:
        raise ValueError("both trade and depth data are required")
    for stream in (trades, depths):
        if any(e.instrument_id != instrument.id or e.ts_init < e.ts_event for e in stream):
            raise ValueError("instrument mismatch or noncausal ts_init")
        if any(a.ts_init > b.ts_init for a, b in zip(stream, stream[1:])):
            raise ValueError("input stream must be sorted by ts_init")
    engine = BacktestEngine(BacktestEngineConfig(logging=LoggingConfig(bypass_logging=True)))
    worker = None
    try:
        worker = PolicyProcess(policy)
        strategy = PolicyStrategy(instrument, worker, features, execution, fold, scenario, snapshots)
        engine.add_venue(
            venue=instrument.id.venue, oms_type=OmsType.NETTING,
            account_type=AccountType[execution.account_type],
            starting_balances=[Money(execution.initial_cash, instrument.quote_currency)],
            book_type=BookType.L2_MBP,
            latency_model=LatencyModel(base_latency_nanos=scenario.order_ns),
            liquidity_consumption=True, trade_execution=False, bar_execution=False,
            queue_position=False, use_random_ids=False,
        )
        engine.add_instrument(instrument)
        engine.add_strategy(strategy)
        # Stable book-before-trade ties; timestamps and vendor sequence are unchanged.
        engine.add_data([e for e in depths if fold.warmup_start <= e.ts_init <= fold.tail_end])
        engine.add_data([e for e in trades if fold.warmup_start <= e.ts_init <= fold.tail_end])
        engine.run()
        diagnostics = {
            "fold": fold.name, "scenario": scenario.name,
            "fills": [asdict(f) for f in strategy.fills], "targets": strategy.target_history,
            "equity": strategy.equity, "equity_times": strategy.equity_times,
            "remaining_quantity": strategy.quantity, "order_count": strategy.count,
        }
        if strategy.failure:
            return {**diagnostics, "status": strategy.failure[0], "reason": strategy.failure[1]}
        if not strategy.finalized or strategy.equity_times[-1] != fold.end:
            return {**diagnostics, "status": "constraint_failed", "reason": "incomplete scoring coverage"}
        account = engine.cache.account_for_venue(instrument.id.venue)
        balance = float(account.balance_total(instrument.quote_currency))
        if abs(balance - strategy.cash) > 1e-5:
            raise ValueError("Nautilus account and fill-ledger reconciliation failed")
        result = metrics(strategy.equity, strategy.trips, strategy.fills, metric_config)
        result.update({
            "order_count": strategy.count,
            "exposure_fraction": strategy.held_ns / (fold.end - fold.start),
            "holding_durations_ns": strategy.holding_durations_ns,
            "turnover_per_day": result["turnover"] * 86_400_000_000_000 / (fold.end - fold.start),
        })
        entries = [f for f in strategy.fills if f.entry and not f.forced]
        groups = {"entry": entries, "exit": [f for f in strategy.fills if not f.entry and not f.forced],
                  "forced": [f for f in strategy.fills if f.forced]}
        horizons = metric_config.markout_horizons
        return {
            "status": "valid", "fold": fold.name, "scenario": scenario.name,
            "metrics": result,
            "markout": {name: markouts(entries, strategy.quotes, h, metric_config.max_quote_age_ns)
                        for name, h in horizons.items()},
            "markout_groups": {
                group: {name: markouts(fills, strategy.quotes, h, metric_config.max_quote_age_ns)
                        for name, h in horizons.items()}
                for group, fills in groups.items()
            },
            "fills": [asdict(f) for f in strategy.fills], "round_trip_pnls": strategy.trips,
            "equity": strategy.equity, "equity_times": strategy.equity_times,
            "account_balance": balance, "targets": strategy.target_history,
        }
    finally:
        if worker is not None:
            worker.close()
        engine.dispose()
