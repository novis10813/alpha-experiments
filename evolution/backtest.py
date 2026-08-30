from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from uuid import uuid4

from evolution.instruments import SPECS
from evolution.instruments import build_instrument
from evolution.instruments import build_bar_type
from evolution.market_state import EvolutionMarketState
from evolution.metrics import FoldMetrics
from evolution.metrics import max_drawdown
from evolution.metrics import profit_factor
from evolution.spec import STARTING_BALANCE_USDT
from data.orderbook_quotes import QuoteRow
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.backtest.engine import BacktestEngineConfig
from nautilus_trader.common.config import LoggingConfig
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import CustomData
from nautilus_trader.model.data import DataType
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.enums import AccountType
from nautilus_trader.model.enums import BookType
from nautilus_trader.model.enums import OmsType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import ClientId
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Money
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity


@dataclass(frozen=True)
class BacktestResult:
    metrics: FoldMetrics
    fill_count: int
    position_count: int


def run_candidate(
    program_path: str | Path,
    instrument_id: str,
    states: list[EvolutionMarketState],
    execution_delay_seconds: int = 0,
    quotes: list[QuoteRow] | None = None,
    bars: list[Bar] | None = None,
) -> BacktestResult:
    if not states:
        raise ValueError("states cannot be empty")
    module = _load_candidate(Path(program_path))
    parsed_id = InstrumentId.from_str(instrument_id)
    data_type = DataType(EvolutionMarketState, metadata={"instrument_id": parsed_id})
    engine = BacktestEngine(BacktestEngineConfig(logging=LoggingConfig(bypass_logging=True)))
    try:
        base_currency = SPECS[instrument_id].base_currency
        engine.add_venue(
            venue=Venue("BINANCE"),
            oms_type=OmsType.NETTING,
            account_type=AccountType.CASH,
            starting_balances=[Money(STARTING_BALANCE_USDT, USDT), Money(0, base_currency)],
            base_currency=None,
            book_type=BookType.L1_MBP,
            use_random_ids=False,
        )
        instrument = build_instrument(instrument_id)
        engine.add_instrument(instrument)
        config = module.EvolutionStrategyConfig(
            instrument_id=parsed_id,
            bar_type=build_bar_type(parsed_id),
            state_data_type=data_type,
        )
        engine.add_strategy(module.EvolvedStrategy(config))
        quote_ticks = (
            [_quote_tick(row, instrument) for row in quotes]
            if quotes is not None
            else [_quote_for(state, instrument, execution_delay_seconds) for state in states]
        )
        replay_states = [_with_init_delay(state, execution_delay_seconds) for state in states]
        wrapped = [CustomData(data_type, state) for state in replay_states]
        engine.add_data(quote_ticks)
        engine.add_data(bars if bars is not None else [_bar_for(state, instrument) for state in states])
        engine.add_data(wrapped, client_id=ClientId("EVOLUTION"))
        engine.run()

        fills = engine.trader.generate_order_fills_report()
        orders_report = engine.trader.generate_orders_report()
        positions = engine.trader.generate_positions_report()
        account = engine.cache.account_for_venue(Venue("BINANCE"))
        final_balance = float(str(account.balance_total(USDT).as_decimal()))
        closed_pnls = _closed_pnls(positions)
        equity = [float(STARTING_BALANCE_USDT)]
        running = equity[0]
        for pnl in closed_pnls:
            running += pnl
            equity.append(running)
        if final_balance > 0 and equity[-1] != final_balance:
            equity.append(final_balance)
        exposure = _exposure_ratio(positions, states[0].ts_event, states[-1].ts_event)
        rejected = _has_rejection(engine)
        metrics = FoldMetrics(
            net_return=(final_balance - STARTING_BALANCE_USDT) / STARTING_BALANCE_USDT,
            max_drawdown=max_drawdown(equity),
            profit_factor=profit_factor(closed_pnls),
            closed_positions=len(positions),
            orders=len(orders_report),
            exposure_ratio=exposure,
            daily_returns=_daily_returns(states, fills, execution_delay_seconds),
            rejected=rejected,
            error="order rejection" if rejected else None,
        )
        return BacktestResult(metrics, len(fills), len(positions))
    finally:
        engine.dispose()


def _load_candidate(path: Path) -> ModuleType:
    name = f"evolved_candidate_{uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load candidate {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


def _quote_for(state: EvolutionMarketState, instrument, delay_seconds: int) -> QuoteTick:
    ts = state.ts_event + delay_seconds * 1_000_000_000
    size = Quantity.from_str(f"1000.{'0' * instrument.size_precision}")
    return QuoteTick(
        instrument_id=instrument.id,
        bid_price=Price.from_str(f"{state.best_bid:.2f}"),
        ask_price=Price.from_str(f"{state.best_ask:.2f}"),
        bid_size=size,
        ask_size=size,
        ts_event=ts,
        ts_init=ts,
    )


def _quote_tick(row: QuoteRow, instrument) -> QuoteTick:
    size = Quantity.from_str(f"1000.{'0' * instrument.size_precision}")
    return QuoteTick(
        instrument_id=instrument.id,
        bid_price=Price.from_str(f"{row.bid:.2f}"),
        ask_price=Price.from_str(f"{row.ask:.2f}"),
        bid_size=size,
        ask_size=size,
        ts_event=row.ts_event,
        ts_init=row.ts_event,
    )


def _bar_for(state: EvolutionMarketState, instrument) -> Bar:
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


def _with_init_delay(state: EvolutionMarketState, delay_seconds: int) -> EvolutionMarketState:
    if delay_seconds < 0:
        raise ValueError("execution delay cannot be negative")
    values = state.to_dict()
    values["ts_init"] = state.ts_event + delay_seconds * 1_000_000_000 + 2
    return EvolutionMarketState(**values)


def _closed_pnls(report) -> list[float]:
    if report is None or len(report) == 0:
        return []
    for name in ("realized_pnl", "realized_return"):
        if name in report.columns:
            values: list[float] = []
            for value in report[name].tolist():
                text = str(value).split(" ", 1)[0]
                try:
                    values.append(float(text))
                except ValueError:
                    continue
            return values
    return []


def _exposure_ratio(report, start_ns: int, end_ns: int) -> float:
    if report is None or len(report) == 0 or end_ns <= start_ns:
        return 0.0
    if "ts_opened" not in report.columns or "ts_closed" not in report.columns:
        return 0.0
    duration = sum(
        max(0, _timestamp_ns(closed) - _timestamp_ns(opened))
        for opened, closed in zip(report.ts_opened, report.ts_closed)
    )
    return min(1.0, duration / (end_ns - start_ns))


def _timestamp_ns(value) -> int:
    return int(value.value) if hasattr(value, "value") else int(value)


def _daily_returns(states: list[EvolutionMarketState], fills, delay_seconds: int) -> tuple[float, ...]:
    day_ns = 86_400_000_000_000
    day_ends: dict[int, EvolutionMarketState] = {}
    for state in states:
        day_ends[state.ts_event // day_ns] = state

    fill_rows = [] if fills is None else fills.to_dict(orient="records")
    fill_rows.sort(key=lambda row: _timestamp_ns(row["ts_last"]))
    cash = float(STARTING_BALANCE_USDT)
    quantity = 0.0
    fill_index = 0
    equities = [cash]
    for day in sorted(day_ends):
        state = day_ends[day]
        cutoff = state.ts_event + delay_seconds * 1_000_000_000 + 2
        while fill_index < len(fill_rows) and _timestamp_ns(fill_rows[fill_index]["ts_last"]) <= cutoff:
            row = fill_rows[fill_index]
            filled = float(str(row["filled_qty"]))
            price = float(row["avg_px"])
            commission = _commission_total(row.get("commissions", []))
            if str(row["side"]).upper() == "BUY":
                cash -= filled * price + commission
                quantity += filled
            else:
                cash += filled * price - commission
                quantity -= filled
            fill_index += 1
        equities.append(cash + quantity * state.best_bid)
    return tuple(
        (current - previous) / previous
        for previous, current in zip(equities, equities[1:])
        if previous > 0
    )


def _commission_total(commissions) -> float:
    return sum(float(str(value).split(" ", 1)[0]) for value in commissions)


def _has_rejection(engine: BacktestEngine) -> bool:
    report = engine.trader.generate_orders_report()
    if report is None or len(report) == 0 or "status" not in report.columns:
        return False
    return any("REJECT" in str(status).upper() for status in report.status)
