"""Trusted Nautilus strategy lifecycle shared by fixed and declarative programs."""

from __future__ import annotations

from decimal import Decimal

from evolution.spec import POSITION_NOTIONAL_USDT
from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import BarType, DataType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.trading.strategy import Strategy


class EvolutionStrategyConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType
    state_data_type: DataType
    position_notional: Decimal = Decimal(POSITION_NOTIONAL_USDT)
    close_positions_on_stop: bool = True


class EvolutionStrategyBase(Strategy):
    """Trusted long/flat execution and subscription lifecycle."""

    def __init__(self, config: EvolutionStrategyConfig) -> None:
        super().__init__(config)
        self.instrument: CurrencyPair | None = None

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.config.instrument_id)
        if self.instrument is None:
            self.stop()
            return
        self.subscribe_data(self.config.state_data_type)

    def on_reset(self) -> None:
        if hasattr(self, "closes"):
            self.closes.clear()

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
        if self.portfolio.is_net_long(self.config.instrument_id):
            self.close_all_positions(self.config.instrument_id)

    def on_stop(self) -> None:
        self.cancel_all_orders(self.config.instrument_id)
        if self.config.close_positions_on_stop:
            self.close_all_positions(self.config.instrument_id)
        self.unsubscribe_data(self.config.state_data_type)
