from __future__ import annotations

from collections import deque
from decimal import Decimal
from math import exp
from math import isfinite
from math import log
from math import sqrt
from statistics import mean
from statistics import median
from statistics import pstdev

from evolution.market_state import EvolutionMarketState
from evolution.spec import POSITION_NOTIONAL_USDT
from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import BarType
from nautilus_trader.model.data import CustomData
from nautilus_trader.model.data import DataType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.trading.strategy import Strategy
from nautilus_trader.indicators import AverageTrueRange
from nautilus_trader.indicators import BollingerBands
from nautilus_trader.indicators import ExponentialMovingAverage
from nautilus_trader.indicators import RelativeStrengthIndex
from nautilus_trader.indicators import SimpleMovingAverage


class EvolutionStrategyConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType
    state_data_type: DataType
    position_notional: Decimal = Decimal(POSITION_NOTIONAL_USDT)
    close_positions_on_stop: bool = True


class EvolvedStrategy(Strategy):
# EVOLVE-BLOCK-START
    def __init__(self, config: EvolutionStrategyConfig) -> None:
        super().__init__(config)
        self.instrument: CurrencyPair | None = None
        self.closes: deque[float] = deque(maxlen=240)

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.config.instrument_id)
        if self.instrument is None:
            self.stop()
            return
        self.subscribe_data(self.config.state_data_type)

    def on_data(self, data: CustomData) -> None:
        state: EvolutionMarketState = data
        self.closes.append(state.close)
        if len(self.closes) < 240:
            return
        fast = mean(tuple(self.closes)[-60:])
        slow = mean(self.closes)
        if fast >= slow:
            self.enter_long(state.close)
        else:
            self.exit_long()

    def on_reset(self) -> None:
        self.closes.clear()
# EVOLVE-BLOCK-END

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
