# Policy evolution runtime

This implementation is independent of the repository's existing strategies and indicators.
It runs restricted Python policies against real NautilusTrader `BacktestEngine` instances,
not a replacement fill simulator.

## Offline smoke run

```bash
uv run python -m experiments.open_evolve.demo --backend openevolve --output outputs/open_evolve/demo-oe
uv run python -m unittest discover -s tests
```

The demo generates synthetic trending TradeTick/Depth10 data, runs three candidates
against two folds and two latency scenarios, freezes the selection, then evaluates a
separate synthetic holdout. Its deterministic proposer exercises the feedback interface
without a model API. Synthetic profitability is not evidence of alpha.

The output directory must be new/empty. It contains the contract, per-generation source,
lineage, metrics, fills, target history, equity, errors, frozen selection and holdout results.

## Catalog-backed search

Copy `example.config.json` to a local configuration and replace its **illustrative**
parameters, model and epoch-nanosecond boundaries. The supplied dates are near the Unix
epoch, deliberately not a claim about catalog coverage. Thresholds and weights are examples,
not recommendations or calibrated fitness. `seed_policy.py` is interpreted source, not a
Python module to import or an established alpha.

```bash
uv run python -m experiments.open_evolve evolve /path/to/config.json outputs/open_evolve/run-001
uv run python -m experiments.open_evolve finalize outputs/open_evolve/run-001 \
  --contract-hash HASH_FROM_SELECTION
```

Catalog credentials use the existing `CATALOG_S3_*` environment variables. Model access uses
`EVOLVE_MODEL_ENDPOINT` (full OpenAI-compatible `/chat/completions` URL) and
`EVOLVE_MODEL_API_KEY`. Neither is written to artifacts or forwarded to policy workers.
Configure `model`, `temperature` and `max_tokens` in the `model` object. To evaluate seeds
without contacting a model, set `budget` equal to the number of seeds.

The default backend uses **OpenEvolve** (currently `0.3.2`), pinned in
`pyproject.toml` and `uv.lock`. It is not Google's AlphaEvolve service. Existing configs
without `search` now select OpenEvolve; use
`"search": {"backend": "legacy"}` explicitly for the old best/latest baseline.

```json
"search": {
  "backend": "openevolve",
  "random_seed": 42,
  "population_size": 32,
  "num_islands": 2,
  "migration_interval": 10,
  "feature_bins": 5
}
```

`openevolve_backend.py` uses the package's `ProgramDatabase` (MAP-Elites, island
sampling/migration), `PromptSampler`, and `LLMEnsemble`. A project-owned **serial**
controller connects them to the restricted interpreter. We deliberately do not use
upstream's generic evaluator, parallel controller, or exception-swallowing iteration
helper. This avoids importing candidate modules and ensures infrastructure failures
abort rather than becoming low scores. No parallel speedup is claimed.

The database uses mean per-cell trade count and turnover as behavior dimensions,
not objectives to maximize. Executable but ineligible policies remain useful parents;
invalid policies are recorded but excluded from the population. Parent diagnostics
survive migration through a source-hash lookup. Recent failures also reach the prompt.
Full prompts/responses, attempt IDs, parent/inspiration lineage, candidate results,
search feedback, and database snapshots are persisted. The snapshot is for audit;
automatic resume is not implemented. A seed does not guarantee deterministic API
responses or byte-identical population evolution (upstream uses UUIDs and set ordering).

Search-only `combined_score` uses disjoint bands: invalid=0, ineligible=(0,1],
eligible=(2,3). Ineligible scores use normalized constraint distances; eligible scores
monotonically map the original fitness. Raw distances and violations accompany the
score. **Final selection uses our original eligibility gates and fitness across all
recorded candidates**, never OpenEvolve's best-program pointer. Missing/duplicate
fold-scenario cells abort. Fees, limits, features and ranking gates do not evolve.

`budget` counts all attempted candidates, including seeds, duplicates and invalid
responses. Duplicate raw source hashes reuse evaluation, but still consume an attempt.
Malformed candidate source is an invalid attempt; endpoint failures, empty/truncated
model content, or infrastructure errors stop the run without freezing selection.
Qwen requests use `extra_body.chat_template_kwargs.enable_thinking=false`; the local
HTTP test verifies that the wire request contains the top-level template option.
Credentials are read only at runtime and are not serialized with backend settings.

The prompt includes units, the microprice half-spread bound, fees, selected execution
settings and evolution scoring rules. Position entry price/unrealized return can be
None when flat even if the market is ready. Feedback includes gross PnL, fees and net
PnL; gross PnL still includes spread/slippage. Large per-trade arrays are omitted from
model feedback. No holdout timestamps/data or catalog paths are included in prompts.

## Safe shell execution

`evolve` only searches; it does not automatically finalize. A completed search with
`no_eligible_candidate` is a valid outcome. Do not call finalize in that case. A failed
command must not be hidden by `tee`:

```bash
set -euo pipefail
RUN=outputs/open_evolve/new-run
uv run python -m experiments.open_evolve evolve /path/to/config.json "$RUN" 2>&1 | tee "${RUN}.log"
# Inspect selection.json. Invoke finalize separately only if status == selected.
```

Never delete previous outputs to retry. Use a new run directory. The implementation
and dependency hashes change with this integration, so historical selections cannot
be finalized using this new runtime.

## Execution assumptions

- NautilusTrader 1.228.0, `L2_MBP`, MARKET, NETTING, `liquidity_consumption=True`,
  `trade_execution=False`, `bar_execution=False`.
- This catalog layout stores no instrument objects, so the CLI resolves the
  instrument from a pinned Binance spot BTCUSDT spec (price 2dp / tick 0.01,
  size 5dp / increment 0.00001, USDT-quoted, maker/taker fee 0.1%, min notional
  10 USDT). The pinned spec is verified against loaded data (2dp prices) before
  each fold, and its full dictionary is fingerprinted into the frozen contract.
  The 0.1% fee is a research assumption; substitute the actual fee schedule via
  a new contract before interpreting absolute PnL. The pinned spec currently
  supports BTCUSDT.BINANCE only.
- Catalog `ts_init` equals `ts_event` in this catalog (verified over the full
  coverage range), so the receive-clock model is event-time replay; explicit
  observation/compute latency still defers decisions via clock alerts.
- Stable book-before-trade ties; within-stream order is preserved. Sequence is retained,
  not assumed to be globally comparable across channels.
- Observation/compute delays deliver immutable older feature snapshots through clock alerts;
  exchange book updates are not delayed. Order latency is Nautilus `LatencyModel`.
  Confirmation delay is zero. The implementation does not support separate nonzero
  confirmation latency or arbitrary reordering of observation channels.
- Fixed quantity, one pending order, close before reversal, bounded order frequency/count,
  depth participation, maximum holding timer, loss kill switch, fixed end-of-fold liquidation.
  Rejections fail the cell; no automatic retries or discretionary execution fallback.
- Fresh engines per cell. No reuse/reset optimization. Actual Nautilus fills drive a
  quote-currency ledger which is reconciled against the final Nautilus account balance.
- Only linear unit-multiplier, quote-settled accounting without funding/borrow costs is
  implemented. CASH is long-only; MARGIN permits shorting when explicitly enabled.
  Do not use this accounting contract for a funded perpetual interval without implementing
  and testing its funding events. No impact or queue-position modeling is provided.
- New snapshots replenish Nautilus tracked liquidity according to the locked engine version.
  The historical feed does not react to our orders. Visible-depth participation is a
  preflight limit, not proof of real-world capacity.
- Fixed-grid equity marks use the last available book; stale marks on open positions fail.
  A fill callback finalizes earlier grid points before changing the ledger. This prevents
  applying a later fill retroactively to earlier equity samples.
- Markouts use backward as-of valid midpoint, with quote-age checks and invalid-book
  barriers. Entry, exit and forced-liquidation groups are reported separately; ranking uses
  non-forced entries. Undefined required metrics fail ranking rather than disappearing.

## Candidate isolation

Candidate source uses Python syntax but only an allowlisted scalar subset: local
assignments, if/else, return, comparisons, boolean/arithmetic operators and abs/min/max.
No imports, loops, object traversal, indexing, containers, globals, nested functions,
strings or arbitrary calls. The interpreter **never exec/eval's candidate code**.

Each cell starts a separate `python -I` worker with a clean environment and value-only JSON
IPC. The worker limits address space to 256 MiB, lifetime CPU to 120 seconds, file size to
zero and open descriptors to 16. Requests have a two-second response timeout; syntax has
configured source/node/step limits. A worker audit hook denies file opens, sockets and
process creation after startup. These fixed runtime limits are versioned through the
implementation hash, not performance-tuning defaults for unrestricted Python.

The capability boundary is the restricted interpreter, reinforced by process isolation and
resource limits. This is **not** a general-purpose hostile-Python container sandbox; do not
replace interpretation with exec or broaden attribute/call permissions without review.
The worker process is not placed in a filesystem/network namespace. Production deployments
requiring kernel-enforced isolation should add a container/seccomp profile around it.

## Cache, resources and holdout

Feature snapshots are computed once per evolution fold and kept in trusted runner memory.
Workers never receive cache references. Streaming/cache equivalence is tested against
actual Nautilus callbacks. Persisted/shared cache and distributed execution are not provided.

Catalog loading currently loads one fold into memory and keeps all evolution folds plus
features for the run. `max_events` rejects oversized loaded folds; it is not a streaming
memory bound during the catalog read. Size real runs conservatively. Runtime and process
peak RSS are recorded; large runs need a streaming adapter before exceeding memory capacity.

Evolution loads only configured evolution folds. The final command checks source/contract,
implementation, dependency-lock and runtime hashes before evaluation. An exclusive
`holdout-started.json` marker prevents repeated final evaluation, including after failure.
An infrastructure recovery requires an external audited procedure, not deleting the marker
because performance was poor. Holdout data is fingerprinted on first access, not inspected
by evolution. Use a frozen catalog snapshot and separate read permissions for strict
operational holdout isolation; application checks cannot prevent the human operator from
opening catalog data or editing local manifests.

## Verification scope

Tests cover causal features, restricted syntax, worker lifecycle/credentials, actual L2
market sweeps and partial fills, fees/account reconciliation, long/short bounded exposure,
forced liquidation, pending deduplication, latency alerts, metrics/markouts, cache parity,
future-suffix invariance, search lineage, failures and one-shot holdout. The offline demo
runs the complete synthetic workflow. No live catalog or external model call is required
by the test suite. Real catalog ordering/cadence, external model compatibility, capacity,
and research profitability require separately configured integration runs.
