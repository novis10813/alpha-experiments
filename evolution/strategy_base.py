"""Trusted Nautilus strategy lifecycle shared by fixed and declarative programs."""

from __future__ import annotations

from decimal import Decimal
from typing import ClassVar

from evolution.spec import LEGACY_EXECUTION_CONTRACT
from evolution.spec import POSITION_NOTIONAL_USDT
from evolution.spec import TRUSTED_INTRADAY_EXECUTION_CONTRACT
from evolution.spec import TRUSTED_INTRADAY_MAX_HOLD_SECONDS
from evolution.spec import validate_execution_contract
from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import BarType, DataType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.events import (
    OrderCanceled,
    OrderDenied,
    OrderFilled,
    OrderRejected,
    PositionClosed,
)
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.trading.strategy import Strategy


class EvolutionStrategyConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType
    state_data_type: DataType
    position_notional: Decimal = Decimal(POSITION_NOTIONAL_USDT)
    close_positions_on_stop: bool = True
    execution_contract: str = LEGACY_EXECUTION_CONTRACT


class EvolutionStrategyBase(Strategy):
    """Trusted long/flat execution and subscription lifecycle."""

    _MAX_HOLD_TIMER_PREFIX: ClassVar[str] = "TRUSTED_MAX_HOLD"

    def __init__(self, config: EvolutionStrategyConfig) -> None:
        super().__init__(config)
        self.instrument: CurrencyPair | None = None
        self._max_hold_deadline_ns: int | None = None
        self._max_hold_close_pending = False
        self.execution_events: list[dict[str, object]] = []
        validate_execution_contract(config.execution_contract)

    @property
    def trusted_intraday_enabled(self) -> bool:
        return self.config.execution_contract == TRUSTED_INTRADAY_EXECUTION_CONTRACT

    @property
    def max_hold_deadline_ns(self) -> int | None:
        return self._max_hold_deadline_ns

    @property
    def max_hold_close_pending(self) -> bool:
        return self._max_hold_close_pending

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.config.instrument_id)
        if self.instrument is None:
            self.stop()
            return
        self.subscribe_data(self.config.state_data_type)

    def on_reset(self) -> None:
        if hasattr(self, "closes"):
            self.closes.clear()
        if self.trusted_intraday_enabled:
            self._cancel_max_hold_timer()
            self._max_hold_deadline_ns = None
            self._max_hold_close_pending = False

    def enter_long(self, reference_price: float) -> None:
        if self.instrument is None or not self.portfolio.is_flat(self.config.instrument_id):
            return
        quantity = self.instrument.make_qty(self.config.position_notional / Decimal(str(reference_price)))
        order = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=OrderSide.BUY,
            quantity=quantity,
            time_in_force=TimeInForce.IOC,
        )
        self.submit_order(order)

    def exit_long(self) -> None:
        if self.portfolio.is_net_long(self.config.instrument_id) and not self._max_hold_close_pending:
            self.close_all_positions(self.config.instrument_id)

    def on_position_closed(self, event: PositionClosed) -> None:
        if not self.trusted_intraday_enabled or event.instrument_id != self.config.instrument_id:
            return
        self._cancel_max_hold_timer()
        self._max_hold_deadline_ns = None
        self._max_hold_close_pending = False

    def on_order_filled(self, event: OrderFilled) -> None:
        if event.instrument_id != self.config.instrument_id or not self.trusted_intraday_enabled:
            return
        if event.is_buy:
            self._arm_max_hold_timer(event.ts_event)
        elif event.is_sell and self._max_hold_close_pending:
            if self.portfolio.is_net_long(self.config.instrument_id):
                self.execution_events.append({"event": "max_hold_close_partial"})
            else:
                self._cancel_max_hold_timer()
                self._max_hold_deadline_ns = None
                self._max_hold_close_pending = False

    def _record_max_hold_close_rejection(self, event) -> None:
        if event.instrument_id == self.config.instrument_id and self._max_hold_close_pending:
            self._max_hold_close_pending = False
            self.execution_events.append({"event": "max_hold_close_rejected", "reason": event.reason})

    def on_order_rejected(self, event: OrderRejected) -> None:
        self._record_max_hold_close_rejection(event)

    def on_order_denied(self, event: OrderDenied) -> None:
        self._record_max_hold_close_rejection(event)

    def on_order_canceled(self, event: OrderCanceled) -> None:
        if event.instrument_id == self.config.instrument_id and self._max_hold_close_pending:
            self._max_hold_close_pending = False
            self.execution_events.append({"event": "max_hold_close_canceled"})

    def _arm_max_hold_timer(self, filled_ns: int) -> None:
        self._cancel_max_hold_timer()
        self._max_hold_deadline_ns = filled_ns + TRUSTED_INTRADAY_MAX_HOLD_SECONDS * 1_000_000_000
        self._max_hold_close_pending = False
        self.clock.set_time_alert_ns(
            name=self._max_hold_timer_name,
            alert_time_ns=self._max_hold_deadline_ns,
            callback=self._on_max_hold_deadline,
        )

    @property
    def _max_hold_timer_name(self) -> str:
        return f"{self._MAX_HOLD_TIMER_PREFIX}:{self.id}"

    def _cancel_max_hold_timer(self) -> None:
        if self._max_hold_timer_name in self.clock.timer_names:
            self.clock.cancel_timer(self._max_hold_timer_name)

    def _on_max_hold_deadline(self, _event) -> None:
        if not self.trusted_intraday_enabled or self._max_hold_close_pending:
            return
        if self.portfolio.is_net_long(self.config.instrument_id):
            self._max_hold_close_pending = True
            self.execution_events.append({"event": "max_hold_close_requested", "deadline_ns": self._max_hold_deadline_ns})
            self.close_all_positions(self.config.instrument_id, time_in_force=TimeInForce.IOC)

    def on_stop(self) -> None:
        if self.trusted_intraday_enabled:
            self._cancel_max_hold_timer()
        self.cancel_all_orders(self.config.instrument_id)
        if self.config.close_positions_on_stop and not self._max_hold_close_pending:
            self.close_all_positions(self.config.instrument_id)
        self.unsubscribe_data(self.config.state_data_type)
