# AGENTS.md

## Project context

This repository is for local alpha experiments built on Nautilus Trader. Code should
prefer Nautilus Trader objects and APIs instead of ad hoc market-data structures.

Current experiment code lives under:

- `experiments/` for strategies and runnable backtests.
- `data/` for catalog loading helpers.
- `tests/` for unit tests.

Use `uv` for Python commands. The project targets Python `>=3.13` and depends on
`nautilus-trader` and `s3fs`.

## Nautilus catalog data

Market data comes from the homestack `nautilus-catalog-builder` setup under
`/opt/docker/`.

The main local reference is:

- `/opt/docker/docs/homestack/nautilus-catalog-builder.md`

Related deployment files are:

- `/opt/docker/compose/homestack/nautilus-catalog-builder.yml`
- `/opt/docker/secrets/nautilus-catalog-builder.env`
- `/opt/docker/site/homestack/nautilus-catalog-builder`

Treat those `/opt/docker/` files as operational context for how the catalog is built
and published. This repository should read the finished Nautilus Parquet catalog; it
should not trigger conversion jobs, write to S3, or require joining the homestack
Docker network unless explicitly requested.

Known catalog shape:

- S3 bucket: `nautilus-data`
- Catalog prefix: bucket root
- Symbols: `BNBUSDT.BINANCE`, `BTCUSDT.BINANCE`, `ETHUSDT.BINANCE`
- Data types: `trade_tick`, `order_book_depths`

## Catalog connection rules

Do not commit secrets. Runtime catalog access is configured through environment
variables or a local untracked `.env`:

- `CATALOG_S3_ENDPOINT`
- `CATALOG_S3_ACCESS_KEY`
- `CATALOG_S3_SECRET_KEY`
- `CATALOG_OUTPUT_S3_BUCKET`

If credentials are needed on the deployment host, inspect
`/opt/docker/secrets/nautilus-catalog-builder.env`, but never copy secret values into
tracked files, test fixtures, logs, or examples.

For this MinIO/S3 catalog, preserve the path-style options in
`data/nautilus_catalog.py`:

- `config_kwargs={"s3": {"addressing_style": "path"}}`
- `virtual_hosted_style_request=false`
- `fs_rust_storage_options["endpoint_url"]`

Do not replace the current direct `ParquetDataCatalog(...)` construction with
`ParquetDataCatalog.from_uri("s3://nautilus-data")`; the local `s3fs` combination has
been documented as passing an incompatible `host` option in this environment.

## Alpha signal conventions

Use `docs/alpha-signal-format.md` as the canonical reference for alpha signal shape.
The minimal logical alpha row is:

```text
ts_event, instrument_id, alpha_name, value
```

`ts_event` means the event time when the signal is knowable from market data. Do not
use write time, report generation time, or a timestamp that implies lookahead.

Keep the core alpha signal narrow. Prices, forward returns, z-scores, thresholds,
trigger flags, positions, fills, PnL, and drawdown belong in diagnostics, reports, or
backtests unless explicitly requested as part of a derived dataset.

## Research framework

Before starting new research work, read `docs/research/current-focus.md`. Use
`docs/research/research-framework.md` as the operating model for factor research.
The repository currently prioritizes hypothesis-based and rule-based alpha
research: start from an explicit market-structure hypothesis, define observable
features or rule states, run focused diagnostics, and document whether the
result is a standalone alpha, feature candidate, filter, execution input, or
rejected idea.

Do not prematurely frame raw market variables as tradable alphas. Keep the
distinction clear between raw features, states, rule alphas, diagnostics, and
backtests. Prediction-oriented modeling can come later after there are clear
feature candidates, rule alphas, and diagnostic targets worth predicting.

## Development commands

Run the test suite with:

```bash
uv run python -m unittest discover -s tests
```

Run the current SMA crossing backtest with:

```bash
uv run python -m experiments.ma_crossing
```

The backtest requires catalog environment variables and actual catalog connectivity.
Unit tests should avoid real S3/MinIO access unless an integration test is explicitly
requested.

## Change guidelines

- Keep changes small and focused on the requested experiment or catalog behavior.
- Match existing Python style: typed functions where useful, simple dataclasses for
  small config/result objects, and `unittest` for current tests.
- Prefer adding tests for catalog configuration and strategy helpers before changing
  behavior.
- Avoid broad refactors, unrelated formatting churn, or new abstractions unless they
  remove concrete duplication in the current code.
