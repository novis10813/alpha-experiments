from __future__ import annotations

import json
from typing import ClassVar
from typing import Iterable

import pyarrow as pa
from nautilus_trader.core.data import Data
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.serialization.arrow.serializer import register_arrow


class EvolutionMarketState(Data):
    FIELDS: ClassVar[tuple[str, ...]] = (
        "instrument_id", "open", "high", "low", "close", "volume", "trade_count",
        "buy_trade_count", "sell_trade_count", "buy_volume", "sell_volume", "trade_imbalance",
        "volume_imbalance", "depth10_obi_mean", "depth10_obi_last", "depth10_obi_min",
        "depth10_obi_max", "best_bid", "best_ask", "spread_bps", "ts_event", "ts_init",
    )

    def __init__(
        self,
        instrument_id: str | InstrumentId,
        open: float,
        high: float,
        low: float,
        close: float,
        volume: float,
        trade_count: int,
        buy_trade_count: int,
        sell_trade_count: int,
        buy_volume: float,
        sell_volume: float,
        trade_imbalance: float,
        volume_imbalance: float,
        depth10_obi_mean: float,
        depth10_obi_last: float,
        depth10_obi_min: float,
        depth10_obi_max: float,
        best_bid: float,
        best_ask: float,
        spread_bps: float,
        ts_event: int,
        ts_init: int,
    ) -> None:
        self.instrument_id = (
            instrument_id if isinstance(instrument_id, InstrumentId) else InstrumentId.from_str(instrument_id)
        )
        self.open = open
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume
        self.trade_count = trade_count
        self.buy_trade_count = buy_trade_count
        self.sell_trade_count = sell_trade_count
        self.buy_volume = buy_volume
        self.sell_volume = sell_volume
        self.trade_imbalance = trade_imbalance
        self.volume_imbalance = volume_imbalance
        self.depth10_obi_mean = depth10_obi_mean
        self.depth10_obi_last = depth10_obi_last
        self.depth10_obi_min = depth10_obi_min
        self.depth10_obi_max = depth10_obi_max
        self.best_bid = best_bid
        self.best_ask = best_ask
        self.spread_bps = spread_bps
        self._ts_event = ts_event
        self._ts_init = ts_init

    @property
    def ts_event(self) -> int:
        return self._ts_event

    @property
    def ts_init(self) -> int:
        return self._ts_init

    _schema: ClassVar[pa.Schema] = pa.schema(
        [
            ("instrument_id", pa.string()),
            ("open", pa.float64()),
            ("high", pa.float64()),
            ("low", pa.float64()),
            ("close", pa.float64()),
            ("volume", pa.float64()),
            ("trade_count", pa.int64()),
            ("buy_trade_count", pa.int64()),
            ("sell_trade_count", pa.int64()),
            ("buy_volume", pa.float64()),
            ("sell_volume", pa.float64()),
            ("trade_imbalance", pa.float64()),
            ("volume_imbalance", pa.float64()),
            ("depth10_obi_mean", pa.float64()),
            ("depth10_obi_last", pa.float64()),
            ("depth10_obi_min", pa.float64()),
            ("depth10_obi_max", pa.float64()),
            ("best_bid", pa.float64()),
            ("best_ask", pa.float64()),
            ("spread_bps", pa.float64()),
            ("ts_event", pa.uint64()),
            ("ts_init", pa.uint64()),
        ],
    )

    @classmethod
    def type_name_static(cls) -> str:
        return cls.__name__

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)

    def to_dict(self) -> dict[str, str | float | int]:
        values = {name: getattr(self, name) for name in self.FIELDS}
        values["instrument_id"] = str(self.instrument_id)
        return values

    @classmethod
    def from_json(cls, value: str) -> EvolutionMarketState:
        return cls(**json.loads(value))

    def encode_record_batch_py(self, items: Iterable[EvolutionMarketState]) -> pa.RecordBatch:
        return pa.RecordBatch.from_pylist([item.to_dict() for item in items], schema=self._schema)

    @classmethod
    def decode_record_batch_py(
        cls,
        metadata: dict[str, str] | None,
        batch: pa.RecordBatch,
    ) -> list[EvolutionMarketState]:
        del metadata
        return [cls(**row) for row in batch.to_pylist()]


def _encode_one(state: EvolutionMarketState) -> pa.RecordBatch:
    return pa.RecordBatch.from_pylist([state.to_dict()], schema=EvolutionMarketState._schema)


def _encode_batch(states: list[EvolutionMarketState]) -> pa.RecordBatch:
    return pa.RecordBatch.from_pylist([state.to_dict() for state in states], schema=EvolutionMarketState._schema)


def _decode_batch(batch: pa.RecordBatch | pa.Table) -> list[EvolutionMarketState]:
    return [EvolutionMarketState(**row) for row in batch.to_pylist()]


register_arrow(
    EvolutionMarketState,
    EvolutionMarketState._schema,
    encoder=_encode_one,
    decoder=_decode_batch,
    batch_encoder=_encode_batch,
)
