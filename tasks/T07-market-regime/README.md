# T07: Market Regime

This document describes how to reproduce REPORT.md. All commands run from the repository root.

## Characterization inputs and data window

| Instrument | Original folds (2026-06-13..2026-07-12) | Supplemental (2026-08-29..2026-09-20) |
| --- | --- | --- |
| BTCUSDT.BINANCE | `data/evolution-data-v2/discovery_1..5` (manifest schema 2) | `discovery_supplemental_20260829_20260830` + `discovery_supplemental_20260830_20260905` + `discovery_supplemental_20260905_20260921` |
| ETHUSDT.BINANCE | `data/evolution-data-v2/discovery_1..5` (schema 2) | `discovery_supplemental_20260829_20260921` |
| BNBUSDT.BINANCE | `data/evolution-data/discovery_1..5` (legacy root, schema 1) | `discovery_supplemental_20260829_20260921` |

The supplemental splits use `data/evolution-data-supplemental`. Inputs are local discovery split files only; the characterization requires no catalog access, network, validation, or holdout data. Regime math uses only `close` and `ts_event` from `EvolutionMarketState`.

## Reproduction

```bash
uv run python -m analysis.market_regime_report \
  --output outputs/evolution-diagnostics/market-regime-map.json
uv run python -m unittest tests.test_market_regime_report -v
```

The report runs offline (no catalog env required) and is deterministic: two
runs produce byte-identical JSON.

## Artifacts

- `outputs/evolution-diagnostics/market-regime-map.json` — per-day rows
  (date, return, sigma, efficiency, vol/trend/direction, label, source
  split), per-period coverage summaries, and split records with manifest
  bookkeeping.
- `analysis/market_regime_report.py` — report code.
- `tests/test_market_regime_report.py` — synthetic-fixture tests covering
  hand-computable classification, trailing-only baselines, insufficient-day
  exclusion, and source-split attribution.

The market-regime command writes `outputs/evolution-diagnostics/market-regime-map.json`; the unittest command writes no `outputs/` files.

## Classifier v2 investigation provenance

Provenance: multi-agent investigation workflow run
`crypto-regime-classifier-investigation-mulerbs7-bx1dg4` (5 agents: repo audit,
method survey, signal catalog, evaluation protocol, synthesis). Full raw outputs
are stored in the workflow run store (result file under
`~/.pi/workflows/projects/alpha-experiments-8b57728fcc53/runs/`). Subagent web
search fell back to arXiv HTML search, OpenAlex, Crossref, GitHub REST, and PyPI
when the primary search endpoints were unavailable; a few DOIs are flagged in the
references in [REPORT.md](REPORT.md#8-key-references-from-the-surveys) as not machine-verified.

Status: v2 rule implemented 2026-09-29 (`analysis/market_regime_report.py`, map schema_version 2, v2 preregistration in [REPORT.md](REPORT.md#preregistered-rules-v2-2026-09-29)). Evaluation (section 6 of the investigation in REPORT.md) is deferred until the data prerequisite (section 4.7) is met.

## Classifier v2 code notes (investigation section 4.6)

The investigation's no-alpha-row-consumer finding was grep-verified across `alphas/`, historical `reports/`, and `evolution/`.

- `analysis/market_regime_report.py`: new constants block replacing L51-56;
  `classify_days_v2` as the single named rule function; map emits
  schema_version 2. `load_day_observations` and `merge_days` unchanged.
- `tests/test_market_regime_report.py`: keep existing no-lookahead and
  insufficient-day tests; add synthetic-fixture regressions: (i) efficiency rule
  fires when trailing eff median > 0.5 (the documented defect); (ii) hysteresis
  enter/exit on a synthetic choppy series; (iii) `break_flag` fires on the
  synthetic shock day and never before; (iv) `no_baseline` with < 30 eligible
  prior days; (v) schema-1 (closes-only) BNB folds classify identically to
  schema-2 for the same close series.
- [REPORT.md](REPORT.md#preregistered-rules-v2-2026-09-29): dated v2 preregistration
  (candidate sets + selection rule + primary variant); "Rule selection
  rationale" updated to record why 2x-median efficiency was replaced.
- `evolution/supplemental.py`: unchanged; its guarded CLI used only for the data
  prerequisite below.

## Classifier v2 data prerequisite (verify Day 0)

Only 51 days/instrument are local. Assumption: the read-only catalog has 1-min
history to at least mid-2025. Action: build supplemental discovery splits via
`uv run python -m evolution build-supplemental-discovery` targeting >= 365 UTC
days ending 2026-09-20, respecting the guards in `evolution/supplemental.py`
(exclude validation 2026-07-12..07-18, holdout 2026-07-18..07-25, quarantined
2026-08-28). Without >= ~120 days the 90-day anchor is meaningless and section 6
cannot start. If depth is unavailable: fix defects #2 and #5 of section 1 on
the 51-day sample as a documented improvement and defer all evaluation claims —
say so in the preregistration.

The investigation specifies the supplemental-discovery CLI action and data window above, but does not provide a complete invocation or exact output paths.

## Future alpha-row consumption code notes

If the classifier graduates, the proposed module is `alphas/market_regime.py`. Diagnostic features, trailing statistics, CUSUM path, `break_flag`, per-day quadrant, and anchor values remain in `outputs/evolution-diagnostics/market-regime-map.json` (schema_version 1 -> 2) and this note family.
