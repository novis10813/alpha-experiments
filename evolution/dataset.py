from __future__ import annotations

import hashlib
import json
import math
import shutil
from decimal import Decimal
from dataclasses import asdict
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Iterable

from alphas.orderbook_imbalance import orderbook_imbalance_value
from data.nautilus_catalog import make_catalog
from evolution.market_state import EvolutionMarketState
from evolution.instruments import build_instrument
from evolution.instruments import build_bar_type
from evolution.spec import EXECUTABLE_DISCOVERY_PROFILE
from evolution.spec import SCHEMA_VERSION
from evolution.spec import ExecutionProfile
from evolution.spec import Window
from nautilus_trader.model.data import OrderBookDepth10
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.data import Bar
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog
from data.orderbook_quotes import QuoteRow
from data.orderbook_quotes import depths_to_quote_rows


NS_PER_MINUTE = 60_000_000_000
STATE_INIT_OFFSET_NS = 2


@dataclass(frozen=True)
class DatasetManifest:
    schema_version: int
    instrument_id: str
    split: str
    source_start: str
    source_end: str
    row_count: int
    missing_bucket_count: int
    first_ts_event: int | None
    last_ts_event: int | None
    files: dict[str, str]
    execution_profile: str = "fast"
    quote_interval_seconds: int = 60
    execution_delay_seconds: int = 0
    quote_count: int = 0


def build_market_states(
    trade_ticks: Iterable[object],
    depths: Iterable[object],
) -> list[EvolutionMarketState]:
    states, _, _ = _build_market_states(trade_ticks, depths, None, 0)
    return states


def _build_market_states(
    trade_ticks: Iterable[object],
    depths: Iterable[object],
    previous_price: float | None,
    previous_sign: int,
) -> tuple[list[EvolutionMarketState], float | None, int]:
    trades = sorted(trade_ticks, key=lambda tick: int(getattr(tick, "ts_event")))
    books = sorted(depths, key=lambda depth: int(getattr(depth, "ts_event")))
    trade_buckets: dict[int, list[tuple[object, int]]] = {}
    for tick in trades:
        price = float(str(getattr(tick, "price")))
        sign = previous_sign
        if previous_price is not None:
            sign = 1 if price > previous_price else -1 if price < previous_price else previous_sign
        trade_buckets.setdefault(int(getattr(tick, "ts_event")) // NS_PER_MINUTE, []).append((tick, sign))
        previous_price = price
        previous_sign = sign

    depth_buckets: dict[int, list[object]] = {}
    for depth in books:
        depth_buckets.setdefault(int(getattr(depth, "ts_event")) // NS_PER_MINUTE, []).append(depth)

    states: list[EvolutionMarketState] = []
    for bucket in sorted(trade_buckets.keys() & depth_buckets.keys()):
        signed_ticks = trade_buckets[bucket]
        bucket_depths = depth_buckets[bucket]
        prices = [float(str(getattr(tick, "price"))) for tick, _ in signed_ticks]
        sizes = [float(str(getattr(tick, "size"))) for tick, _ in signed_ticks]
        buy_sizes = [size for size, (_, sign) in zip(sizes, signed_ticks, strict=True) if sign > 0]
        sell_sizes = [size for size, (_, sign) in zip(sizes, signed_ticks, strict=True) if sign < 0]
        buy_count = sum(sign > 0 for _, sign in signed_ticks)
        sell_count = sum(sign < 0 for _, sign in signed_ticks)
        obi = [orderbook_imbalance_value(depth) for depth in bucket_depths]
        last_depth = bucket_depths[-1]
        bid = _best_price(getattr(last_depth, "bids"))
        ask = _best_price(getattr(last_depth, "asks"))
        mid = (bid + ask) / 2
        end = (bucket + 1) * NS_PER_MINUTE
        states.append(
            EvolutionMarketState(
                instrument_id=str(getattr(signed_ticks[0][0], "instrument_id")),
                open=prices[0], high=max(prices), low=min(prices), close=prices[-1],
                volume=sum(sizes), trade_count=len(signed_ticks),
                buy_trade_count=buy_count, sell_trade_count=sell_count,
                buy_volume=sum(buy_sizes), sell_volume=sum(sell_sizes),
                trade_imbalance=_ratio(buy_count - sell_count, buy_count + sell_count),
                volume_imbalance=_ratio(sum(buy_sizes) - sum(sell_sizes), sum(buy_sizes) + sum(sell_sizes)),
                depth10_obi_mean=sum(obi) / len(obi), depth10_obi_last=obi[-1],
                depth10_obi_min=min(obi), depth10_obi_max=max(obi),
                best_bid=bid, best_ask=ask,
                spread_bps=(ask - bid) / mid * 10_000 if mid else 0.0,
                ts_event=end, ts_init=end + STATE_INIT_OFFSET_NS,
            ),
        )
    return states, previous_price, previous_sign


def write_state_file(states: list[EvolutionMarketState], path: Path) -> str:
    import pyarrow.parquet as pq

    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa_table(states)
    pq.write_table(table, path, compression="zstd")
    return sha256_file(path)


def write_quote_file(quotes: list[QuoteRow], path: Path) -> str:
    import pyarrow as pa
    import pyarrow.parquet as pq

    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist([asdict(quote) for quote in quotes]), path, compression="zstd")
    return sha256_file(path)


def write_local_catalog(
    states: list[EvolutionMarketState],
    quotes: list[QuoteRow],
    root: Path,
    instrument_id: str,
) -> dict[str, str]:
    if (root / "data").exists():
        raise RuntimeError(f"local catalog already exists: {root}")
    root.mkdir(parents=True, exist_ok=True)
    catalog = ParquetDataCatalog(root)
    _write_catalog_chunk(catalog, states, quotes, instrument_id)
    return _catalog_hashes(root)


def _write_catalog_chunk(
    catalog: ParquetDataCatalog,
    states: list[EvolutionMarketState],
    quotes: list[QuoteRow],
    instrument_id: str,
) -> None:
    if states:
        catalog.write_data(states, identifier=instrument_id)
        instrument = build_instrument(instrument_id)
        catalog.write_data([_bar(state, instrument) for state in states])
    if quotes:
        instrument = build_instrument(instrument_id)
        catalog.write_data([_quote_tick(quote, instrument) for quote in quotes])


def _catalog_hashes(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): sha256_file(path)
        for path in sorted((root / "data").rglob("*.parquet"))
    }


def pa_table(states: list[EvolutionMarketState]):
    import pyarrow as pa

    return pa.Table.from_pylist([state.to_dict() for state in states], schema=EvolutionMarketState._schema)


def write_manifest(manifest: DatasetManifest, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(manifest), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def verify_manifest(
    path: Path,
    instrument_id: str,
    split: str,
    execution_profile: str | None = None,
) -> DatasetManifest:
    payload = json.loads(path.read_text(encoding="utf-8"))
    manifest = DatasetManifest(**payload)
    if manifest.schema_version != SCHEMA_VERSION:
        raise ValueError(f"unsupported dataset schema version: {manifest.schema_version}")
    if manifest.instrument_id != instrument_id or manifest.split != split:
        raise ValueError("dataset manifest identity does not match requested split")
    if execution_profile is not None and manifest.execution_profile != execution_profile:
        raise ValueError("dataset manifest execution profile does not match request")
    root = path.parent
    actual = {str(item.relative_to(root)) for item in (root / "data").rglob("*.parquet")}
    if actual != set(manifest.files):
        raise ValueError("dataset files do not match manifest")
    for relative, expected_hash in manifest.files.items():
        if sha256_file(root / relative) != expected_hash:
            raise ValueError(f"dataset hash mismatch: {relative}")
    return manifest


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def manifest_for(
    instrument_id: str,
    window: Window,
    states: list[EvolutionMarketState],
    files: dict[str, str],
) -> DatasetManifest:
    expected = int((window.end - window.start).total_seconds() // 60)
    return DatasetManifest(
        schema_version=SCHEMA_VERSION,
        instrument_id=instrument_id,
        split=window.name,
        source_start=window.start.isoformat().replace("+00:00", "Z"),
        source_end=window.end.isoformat().replace("+00:00", "Z"),
        row_count=len(states),
        missing_bucket_count=max(0, expected - len(states)),
        first_ts_event=states[0].ts_event if states else None,
        last_ts_event=states[-1].ts_event if states else None,
        files=dict(sorted(files.items())),
        execution_profile="fast",
        quote_interval_seconds=window.quote_interval_seconds,
        execution_delay_seconds=window.execution_delay_seconds,
    )


def build_executable_discovery_from_fast(
    instrument_id: str,
    window: Window,
    fast_root: Path,
    output_root: Path,
    profile: ExecutionProfile = EXECUTABLE_DISCOVERY_PROFILE,
) -> DatasetManifest:
    if not window.name.startswith("discovery_"):
        raise ValueError("executable discovery data may use discovery windows only")
    source = fast_root / window.name / instrument_id
    fast_manifest = verify_manifest(source / "manifest.json", instrument_id, window.name)
    target = output_root / window.name / instrument_id
    if target.exists():
        raise RuntimeError(f"local catalog already exists: {target}")
    target.mkdir(parents=True)
    for data_type in ("custom_evolution_market_state", "bar"):
        source_type = source / "data" / data_type
        if source_type.exists():
            shutil.copytree(source_type, target / "data" / data_type)

    catalog = make_catalog()
    quotes = catalog.query(
        OrderBookDepth10,
        identifiers=[instrument_id],
        start=fast_manifest.source_start,
        end=fast_manifest.source_end,
    )
    quote_rows = depths_to_quote_rows(quotes, resample_seconds=profile.quote_interval_seconds)
    local_catalog = ParquetDataCatalog(target)
    _write_catalog_chunk(local_catalog, [], quote_rows, instrument_id)
    files = _catalog_hashes(target)
    manifest = DatasetManifest(
        schema_version=SCHEMA_VERSION,
        instrument_id=instrument_id,
        split=window.name,
        source_start=fast_manifest.source_start,
        source_end=fast_manifest.source_end,
        row_count=fast_manifest.row_count,
        missing_bucket_count=fast_manifest.missing_bucket_count,
        first_ts_event=fast_manifest.first_ts_event,
        last_ts_event=fast_manifest.last_ts_event,
        files=dict(sorted(files.items())),
        execution_profile=profile.name,
        quote_interval_seconds=profile.quote_interval_seconds,
        execution_delay_seconds=profile.execution_delay_seconds,
        quote_count=len(quote_rows),
    )
    write_manifest(manifest, target / "manifest.json")
    return manifest


def build_window_from_catalog(instrument_id: str, window: Window, output_root: Path) -> DatasetManifest:
    """Read closed UTC days and write only to a local split-specific dataset."""
    catalog = make_catalog()
    split_dir = output_root / window.name / instrument_id
    if (split_dir / "data").exists():
        raise RuntimeError(f"local catalog already exists: {split_dir}")
    split_dir.mkdir(parents=True, exist_ok=True)
    local_catalog = ParquetDataCatalog(split_dir)
    row_count = 0
    first_ts_event: int | None = None
    last_ts_event: int | None = None
    previous_price: float | None = None
    previous_sign = 0
    day = window.start
    while day < window.end:
        day_end = min(day + timedelta(days=1), window.end)
        start = day.isoformat().replace("+00:00", "Z")
        end = day_end.isoformat().replace("+00:00", "Z")
        trades = catalog.trade_ticks(instrument_ids=[InstrumentId.from_str(instrument_id)], start=start, end=end)
        depths = catalog.query(OrderBookDepth10, identifiers=[instrument_id], start=start, end=end)
        day_states, previous_price, previous_sign = _build_market_states(
            trades,
            depths,
            previous_price,
            previous_sign,
        )
        day_quotes = depths_to_quote_rows(depths, resample_seconds=window.quote_interval_seconds)
        _write_catalog_chunk(local_catalog, day_states, day_quotes, instrument_id)
        if day_states:
            first_ts_event = first_ts_event or day_states[0].ts_event
            last_ts_event = day_states[-1].ts_event
            row_count += len(day_states)
        day = day_end
    expected = int((window.end - window.start).total_seconds() // 60)
    manifest = DatasetManifest(
        schema_version=SCHEMA_VERSION,
        instrument_id=instrument_id,
        split=window.name,
        source_start=window.start.isoformat().replace("+00:00", "Z"),
        source_end=window.end.isoformat().replace("+00:00", "Z"),
        row_count=row_count,
        missing_bucket_count=max(0, expected - row_count),
        first_ts_event=first_ts_event,
        last_ts_event=last_ts_event,
        files=dict(sorted(_catalog_hashes(split_dir).items())),
        execution_profile="fast",
        quote_interval_seconds=window.quote_interval_seconds,
        execution_delay_seconds=window.execution_delay_seconds,
    )
    write_manifest(manifest, split_dir / "manifest.json")
    return manifest


def _best_price(levels: Iterable[object]) -> float:
    for level in levels:
        if level is not None:
            value = float(str(getattr(level, "price")))
            if math.isfinite(value):
                return value
    return 0.0


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _quote_tick(quote: QuoteRow, instrument) -> QuoteTick:
    size = Quantity.from_str(f"1000.{'0' * instrument.size_precision}")
    return QuoteTick(
        instrument_id=instrument.id,
        bid_price=Price.from_str(f"{quote.bid:.2f}"),
        ask_price=Price.from_str(f"{quote.ask:.2f}"),
        bid_size=size,
        ask_size=size,
        ts_event=quote.ts_event,
        ts_init=quote.ts_event,
    )


def _bar(state: EvolutionMarketState, instrument) -> Bar:
    return Bar(
        bar_type=build_bar_type(instrument.id),
        open=Price.from_str(f"{state.open:.2f}"),
        high=Price.from_str(f"{state.high:.2f}"),
        low=Price.from_str(f"{state.low:.2f}"),
        close=Price.from_str(f"{state.close:.2f}"),
        volume=instrument.make_qty(Decimal(str(state.volume))),
        ts_event=state.ts_event,
        ts_init=state.ts_event,
    )
