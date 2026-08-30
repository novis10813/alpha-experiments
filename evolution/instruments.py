from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from evolution.spec import FEE_RATE
from evolution.spec import INSTRUMENT_IDS
from nautilus_trader.model.currencies import BNB
from nautilus_trader.model.currencies import BTC
from nautilus_trader.model.currencies import ETH
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.data import BarAggregation
from nautilus_trader.model.data import BarSpecification
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import AggregationSource
from nautilus_trader.model.enums import PriceType
from nautilus_trader.model.objects import Money
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity


@dataclass(frozen=True)
class InstrumentSpec:
    instrument_id: str
    size_precision: int
    size_increment: str
    base_currency: object


SPECS = {
    "BTCUSDT.BINANCE": InstrumentSpec("BTCUSDT.BINANCE", 5, "0.00001", BTC),
    "ETHUSDT.BINANCE": InstrumentSpec("ETHUSDT.BINANCE", 4, "0.0001", ETH),
    "BNBUSDT.BINANCE": InstrumentSpec("BNBUSDT.BINANCE", 3, "0.001", BNB),
}


def build_instrument(instrument_id: str) -> CurrencyPair:
    if instrument_id not in INSTRUMENT_IDS:
        raise ValueError(f"unsupported instrument: {instrument_id}")
    spec = SPECS[instrument_id]
    symbol_text = instrument_id.split(".", 1)[0]
    symbol = Symbol(symbol_text)
    return CurrencyPair(
        instrument_id=InstrumentId(symbol, Venue("BINANCE")),
        raw_symbol=symbol,
        base_currency=spec.base_currency,
        quote_currency=USDT,
        price_precision=2,
        size_precision=spec.size_precision,
        price_increment=Price.from_str("0.01"),
        size_increment=Quantity.from_str(spec.size_increment),
        lot_size=None,
        max_quantity=Quantity.from_str(f"9000.{''.join('0' for _ in range(spec.size_precision))}"),
        min_quantity=Quantity.from_str(spec.size_increment),
        max_notional=None,
        min_notional=Money(1, USDT),
        max_price=Price.from_str("1000000.00"),
        min_price=Price.from_str("0.01"),
        margin_init=Decimal("0"),
        margin_maint=Decimal("0"),
        maker_fee=Decimal(str(FEE_RATE)),
        taker_fee=Decimal(str(FEE_RATE)),
        ts_event=0,
        ts_init=0,
    )


def quantity_for_notional(instrument_id: str, price: Decimal, notional: Decimal) -> Quantity:
    if price <= 0 or notional <= 0:
        raise ValueError("price and notional must be positive")
    return build_instrument(instrument_id).make_qty(notional / price)


def build_bar_type(instrument_id: str | InstrumentId) -> BarType:
    parsed = instrument_id if isinstance(instrument_id, InstrumentId) else InstrumentId.from_str(instrument_id)
    return BarType(
        parsed,
        BarSpecification(1, BarAggregation.MINUTE, PriceType.LAST),
        AggregationSource.EXTERNAL,
    )
