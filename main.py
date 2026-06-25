from data.nautilus_catalog import make_catalog
from nautilus_trader.model.data import OrderBookDepth10
from nautilus_trader.model.identifiers import InstrumentId


catalog = make_catalog()
instrument = InstrumentId.from_str("BTCUSDT.BINANCE")

trades = catalog.trade_ticks(
    instrument_ids=[instrument],
    start="2026-06-17T00:00:00Z",
    end="2026-06-17T00:01:00Z",
)

depths = catalog.query(
    OrderBookDepth10,
    identifiers=[str(instrument)],
    start="2026-06-17T00:00:00Z",
    end="2026-06-17T00:01:00Z",
)

print(trades)
