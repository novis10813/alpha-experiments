from __future__ import annotations

from decimal import Decimal

from evolution.initial_program import EvolutionStrategyConfig
from evolution.market_state import EvolutionMarketState
from nautilus_trader.model.data import CustomData
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.trading.strategy import Strategy


class EvolvedStrategy(Strategy):
    def __init__(self, config: EvolutionStrategyConfig) -> None:
        super().__init__(config)
        self.instrument: CurrencyPair | None = None
        self.entered = False

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.config.instrument_id)
        self.subscribe_data(self.config.state_data_type)

    def on_data(self, data: CustomData) -> None:
        state: EvolutionMarketState = data
        if self.entered or self.instrument is None:
            return
        quantity = self.instrument.make_qty(self.config.position_notional / Decimal(str(state.close)))
        self.submit_order(
            self.order_factory.market(
                instrument_id=self.config.instrument_id,
                order_side=OrderSide.BUY,
                quantity=quantity,
                time_in_force=TimeInForce.IOC,
            ),
        )
        self.entered = True

    def on_stop(self) -> None:
        self.close_all_positions(self.config.instrument_id)
