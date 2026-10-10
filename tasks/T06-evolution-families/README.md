# T06: Evolution Hypothesis Families

This document describes how to reproduce [REPORT.md](REPORT.md) using the registered entry signal diagnostic.

## Inputs and data window

The diagnostic uses the registered family seed's `RULE_SPEC` entry conditions and
an explicitly allowed supplemental discovery dataset. The source command uses
`BTCUSDT.BINANCE` and `trend-flow-confirmation-v1`. Its supplemental split and
start/end dates are placeholders; no concrete diagnostic data window is recorded.
Use the allowed supplemental split and corresponding dates in place of
`discovery_supplemental_YYYYMMDD_YYYYMMDD`, `YYYY-MM-DD`, and `YYYY-MM-DD`.

## Reproduction command

Run from the repository root, without remote catalog access:

```bash
uv run python -m evolution signal-diagnostic \
  --instrument-id BTCUSDT.BINANCE \
  --family-id trend-flow-confirmation-v1 \
  --split discovery_supplemental_YYYYMMDD_YYYYMMDD \
  --start YYYY-MM-DD --end YYYY-MM-DD \
  --root data/evolution-data-supplemental \
  --output outputs/evolution-diagnostics/registered-entry-signal.json
```

## Output and code notes

The command writes `outputs/evolution-diagnostics/registered-entry-signal.json`.
The output records the fixed specification, event timestamps, exclusion reasons,
family/rule/code/dataset hashes, and per-day/overall gross/net bps summaries.

The fixed protocol is documented in [REPORT.md](REPORT.md). Supplemental
date/split guards, manifest/profile/hash checks, and the existing local Nautilus
loader are used; all validation occurs before the loader.
