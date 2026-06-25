from __future__ import annotations

import argparse
import warnings
from dataclasses import dataclass
from decimal import Decimal

from data.nautilus_catalog import make_catalog
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.backtest.engine import BacktestEngineConfig
from nautilus_trader.common.config import LoggingConfig
from nautilus_trader.config import PositiveInt
from nautilus_trader.config import StrategyConfig
from nautilus_trader.core.correctness import PyCondition
from nautilus_trader.indicators import SimpleMovingAverage
from nautilus_trader.model.currencies import BTC
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import BarAggregation
from nautilus_trader.model.data import BarSpecification
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import AccountType
from nautilus_trader.model.enums import AggregationSource
from nautilus_trader.model.enums import OmsType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import PriceType
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.objects import Money
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity
from nautilus_trader.model.orders import MarketOrder
from nautilus_trader.trading.strategy import Strategy


DEFAULT_INSTRUMENT_ID = "BTCUSDT.BINANCE"
DEFAULT_START = "2026-06-17T00:00:00Z"
DEFAULT_END = "2026-06-17T01:00:00Z"


class SMACrossConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal
    fast_period: PositiveInt = 3
    slow_period: PositiveInt = 8
    close_positions_on_stop: bool = True


class SMACrossLongOnly(Strategy):
    def __init__(self, config: SMACrossConfig) -> None:
        PyCondition.is_true(
            config.fast_period < config.slow_period,
            "fast_period must be less than slow_period",
        )
        super().__init__(config)
        self.instrument: CurrencyPair | None = None
        self.fast_sma = SimpleMovingAverage(config.fast_period)
        self.slow_sma = SimpleMovingAverage(config.slow_period)

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.config.instrument_id)
        if self.instrument is None:
            self.log.error(f"Could not find instrument for {self.config.instrument_id}")
            self.stop()
            return

        self.register_indicator_for_bars(self.config.bar_type, self.fast_sma)
        self.register_indicator_for_bars(self.config.bar_type, self.slow_sma)
        self.subscribe_bars(self.config.bar_type)
        self.subscribe_trade_ticks(self.config.instrument_id)

    def on_bar(self, bar: Bar) -> None:
        if not self.indicators_initialized():
            return

        if self.fast_sma.value >= self.slow_sma.value:
            if self.portfolio.is_flat(self.config.instrument_id):
                self.buy()
        elif self.portfolio.is_net_long(self.config.instrument_id):
            self.close_all_positions(self.config.instrument_id)

    def buy(self) -> None:
        if self.instrument is None:
            return

        order: MarketOrder = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=OrderSide.BUY,
            quantity=self.instrument.make_qty(self.config.trade_size),
            time_in_force=TimeInForce.IOC,
        )
        self.submit_order(order)

    def on_stop(self) -> None:
        self.cancel_all_orders(self.config.instrument_id)
        if self.config.close_positions_on_stop:
            self.close_all_positions(self.config.instrument_id)

        self.unsubscribe_bars(self.config.bar_type)
        self.unsubscribe_trade_ticks(self.config.instrument_id)

    def on_reset(self) -> None:
        self.fast_sma.reset()
        self.slow_sma.reset()


@dataclass(frozen=True)
class BacktestSummary:
    instrument_id: str
    start: str
    end: str
    trade_ticks: int
    fills: int
    positions: int


def build_bar_type(instrument_id: str | InstrumentId) -> BarType:
    parsed_id = (
        instrument_id if isinstance(instrument_id, InstrumentId) else InstrumentId.from_str(instrument_id)
    )
    return BarType(
        parsed_id,
        BarSpecification(1, BarAggregation.MINUTE, PriceType.LAST),
        AggregationSource.INTERNAL,
    )


def build_btcusdt_binance_spot() -> CurrencyPair:
    return CurrencyPair(
        instrument_id=InstrumentId(Symbol("BTCUSDT"), Venue("BINANCE")),
        raw_symbol=Symbol("BTCUSDT"),
        base_currency=BTC,
        quote_currency=USDT,
        price_precision=2,
        size_precision=5,
        price_increment=Price.from_str("0.01"),
        size_increment=Quantity.from_str("0.00001"),
        lot_size=None,
        max_quantity=Quantity.from_str("9000.00000"),
        min_quantity=Quantity.from_str("0.00001"),
        max_notional=None,
        min_notional=Money(1, USDT),
        max_price=Price.from_str("1000000.00"),
        min_price=Price.from_str("0.01"),
        margin_init=Decimal("0"),
        margin_maint=Decimal("0"),
        maker_fee=Decimal("0.001"),
        taker_fee=Decimal("0.001"),
        ts_event=0,
        ts_init=0,
    )


def run_backtest(
    instrument_id: str = DEFAULT_INSTRUMENT_ID,
    start: str = DEFAULT_START,
    end: str = DEFAULT_END,
    fast_period: int = 3,
    slow_period: int = 8,
    trade_size: Decimal = Decimal("0.00020"),
) -> BacktestSummary:
    warnings.filterwarnings(
        "ignore",
        message="The 'generic' unit for NumPy timedelta is deprecated.*",
        category=DeprecationWarning,
    )

    parsed_id = InstrumentId.from_str(instrument_id)
    bar_type = build_bar_type(parsed_id)
    catalog = make_catalog()
    trades = catalog.trade_ticks(instrument_ids=[parsed_id], start=start, end=end)
    if not trades:
        raise RuntimeError(f"No trade ticks found for {instrument_id} from {start} to {end}")

    engine = BacktestEngine(
        BacktestEngineConfig(logging=LoggingConfig(bypass_logging=True)),
    )
    try:
        engine.add_venue(
            venue=Venue("BINANCE"),
            oms_type=OmsType.NETTING,
            account_type=AccountType.CASH,
            starting_balances=[Money(100_000, USDT), Money(0, BTC)],
            base_currency=None,
        )
        engine.add_instrument(build_btcusdt_binance_spot())
        engine.add_strategy(
            SMACrossLongOnly(
                SMACrossConfig(
                    instrument_id=parsed_id,
                    bar_type=bar_type,
                    trade_size=trade_size,
                    fast_period=fast_period,
                    slow_period=slow_period,
                    close_positions_on_stop=True,
                ),
            ),
        )
        engine.add_data(trades)
        engine.run()

        fills_report = engine.trader.generate_order_fills_report()
        positions_report = engine.trader.generate_positions_report()
        if len(fills_report) == 0:
            raise RuntimeError("Backtest ran, but the MA crossing strategy produced no fills")

        return BacktestSummary(
            instrument_id=instrument_id,
            start=start,
            end=end,
            trade_ticks=len(trades),
            fills=len(fills_report),
            positions=len(positions_report),
        )
    finally:
        engine.dispose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a Nautilus Trader SMA crossing backtest.")
    parser.add_argument("--instrument-id", default=DEFAULT_INSTRUMENT_ID)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--fast-period", type=int, default=3)
    parser.add_argument("--slow-period", type=int, default=8)
    parser.add_argument("--trade-size", type=Decimal, default=Decimal("0.00020"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = run_backtest(
        instrument_id=args.instrument_id,
        start=args.start,
        end=args.end,
        fast_period=args.fast_period,
        slow_period=args.slow_period,
        trade_size=args.trade_size,
    )
    print("MA crossing backtest completed")
    print(summary)
    # print(f"instrument_id={summary.instrument_id}")
    # print(f"start={summary.start}")
    # print(f"end={summary.end}")
    # print(f"trade_ticks={summary.trade_ticks}")
    # print(f"fills={summary.fills}")
    # print(f"positions={summary.positions}")


if __name__ == "__main__":
    main()
