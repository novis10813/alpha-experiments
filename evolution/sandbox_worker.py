from __future__ import annotations

import json
import os
from pathlib import Path

from data.orderbook_quotes import QuoteRow
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog

from evolution.backtest import run_candidate
from evolution.candidate import validate_candidate_file
from evolution.dataset import verify_manifest
from evolution.market_state import EvolutionMarketState
from evolution.metrics import aggregate_folds
from evolution.metrics import screen_passes
from evolution.spec import DISCOVERY_FOLDS


PROGRAM_PATH = Path("/candidate/program.py")
REFERENCE_PATH = Path("/app/evolution/initial_program.py")
DATASET_ROOT = Path("/dataset")


def main() -> None:
    instrument_id = os.environ["EVOLUTION_INSTRUMENT_ID"]
    validation = validate_candidate_file(PROGRAM_PATH, REFERENCE_PATH)
    if not validation.valid:
        print(json.dumps({"ok": False, "stage": 1, "error": "; ".join(validation.errors)}))
        return
    try:
        run_candidate(PROGRAM_PATH, instrument_id, _synthetic_states(instrument_id))
        folds = []
        for index, window in enumerate(DISCOVERY_FOLDS):
            states, quotes, bars = _load_split(DATASET_ROOT / window.name / instrument_id, instrument_id)
            if index == 0:
                screen_end = states[0].ts_event + 7 * 86_400_000_000_000 if states else 0
                screen = run_candidate(
                    PROGRAM_PATH,
                    instrument_id,
                    [s for s in states if s.ts_event < screen_end],
                    quotes=[quote for quote in quotes if quote.ts_event < screen_end],
                    bars=[bar for bar in bars if bar.ts_event < screen_end],
                )
                if not screen_passes(screen.metrics):
                    print(json.dumps({"ok": False, "stage": 2, "error": screen.metrics.error or "screen rejected"}))
                    return
            folds.append(run_candidate(PROGRAM_PATH, instrument_id, states, quotes=quotes, bars=bars).metrics)
        aggregate = aggregate_folds(folds)
        print(json.dumps({"ok": True, "stage": 3, "metrics": aggregate.to_open_evolve()}))
    except Exception as exc:
        stage = 1 if "folds" not in locals() else 2
        message = f"{type(exc).__name__}: {exc}"[:500]
        print(json.dumps({"ok": False, "stage": stage, "error": message}))


def _load_split(path: Path, instrument_id: str):
    verify_manifest(path / "manifest.json", instrument_id, path.parent.name)
    catalog = ParquetDataCatalog(path)
    wrapped = catalog.query(EvolutionMarketState, identifiers=[instrument_id])
    states = [item.data for item in wrapped]
    ticks = catalog.quote_ticks(instrument_ids=[InstrumentId.from_str(instrument_id)])
    bars = catalog.bars(instrument_ids=[instrument_id])
    quotes = [QuoteRow(
        ts_event=tick.ts_event,
        instrument_id=str(tick.instrument_id),
        bid=float(str(tick.bid_price)),
        ask=float(str(tick.ask_price)),
        mid=(float(str(tick.bid_price)) + float(str(tick.ask_price))) / 2,
        spread=float(str(tick.ask_price)) - float(str(tick.bid_price)),
        spread_bps=(float(str(tick.ask_price)) - float(str(tick.bid_price)))
        / ((float(str(tick.bid_price)) + float(str(tick.ask_price))) / 2) * 10_000,
    ) for tick in ticks]
    return states, quotes, bars


def _synthetic_states(instrument_id: str) -> list[EvolutionMarketState]:
    states = []
    for index, close in enumerate((100.0, 100.1, 100.2, 100.1, 100.0, 100.1, 100.2, 100.3, 100.2, 100.1)):
        ts_event = (index + 1) * 60_000_000_000
        states.append(EvolutionMarketState(
            instrument_id, close, close, close, close, 1.0, 2, 1, 1, 0.5, 0.5,
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0, close - 0.01, close + 0.01, 2.0,
            ts_event, ts_event + 2,
        ))
    return states


if __name__ == "__main__":
    main()
