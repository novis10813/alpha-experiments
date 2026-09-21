# Supplemental Data + Market Regime Research (2026-09-21)

## Goal

1. Supplement local discovery data so every instrument has executable-profile
   discovery coverage from 2026-08-29 (or 2026-09-05 for BTC, already built)
   through the last completed UTC day 2026-09-20.
2. Characterize market regimes (volatility x trend, with direction) across the
   full locally available history, so Milestone 2.6's "extended discovery
   covers more than one market regime" can be backed by a documented,
   preregistered extended discovery calendar.

Both parts are **discovery-only diagnostics and data preparation**. Neither
part feeds candidate generation, fitness, ranking, promotion gates, or
validation/holdout access. No code may read validation or holdout splits.

## Ground truth established 2026-09-21 (catalog probes, 1h windows)

- Catalog (read-only S3 Nautilus catalog) has trade data for all three
  instruments, every UTC day 2026-09-05 through 2026-09-20, and also
  2026-08-29 through 2026-09-04 for ETH and BNB (spot-checked 08-29, 08-31,
  09-02, 09-04; per-day full verification happens in the builder).
- Existing supplemental data: BTC only, `discovery_supplemental_20260829_20260830`
  and `discovery_supplemental_20260830_20260905` under
  `.local/evolution-data-supplemental/`. ETH and BNB have none.
- Protected/untouchable: validation 2026-07-12..2026-07-18, holdout
  2026-07-18..2026-07-25 (all instruments); quarantined day 2026-08-28.
  These guards are enforced in `evolution/supplemental.py`.
- `trend-flow-confirmation-v1` holdout is consumed (rejected); the other
  families have unconsumed holdout. This task consumes nothing.

## Slices

### Slice 1 — Build supplemental executable discovery splits (long-running)

**Status: complete 2026-09-21 11:11 UTC.** All three splits built and audited
in one background job (`.local/build-supplemental-20260921.sh`, log
`.local/build-supplemental-20260921.log`): each audit report shows zero
missing state buckets, zero missing quote seconds, empty manifest issues.
Audit reports under `outputs/evolution-diagnostics/supplemental-audit-*`.

Build with the existing guarded CLI (executable profile: 1-second quotes,
1-second delay), writing to `.local/evolution-data-supplemental/`:

| Instrument | Start (incl.) | End (excl.) | Split name |
| --- | --- | --- | --- |
| BTCUSDT.BINANCE | 2026-09-05 | 2026-09-21 | `discovery_supplemental_20260905_20260921` |
| ETHUSDT.BINANCE | 2026-08-29 | 2026-09-21 | `discovery_supplemental_20260829_20260921` |
| BNBUSDT.BINANCE | 2026-08-29 | 2026-09-21 | `discovery_supplemental_20260829_20260921` |

Commands (run sequentially, one background job):

```bash
uv run python -m evolution build-supplemental-discovery \
  --instrument-id BTCUSDT.BINANCE --start 2026-09-05 --end 2026-09-21 \
  --output-root .local/evolution-data-supplemental
# same for ETHUSDT.BINANCE and BNBUSDT.BINANCE with --start 2026-08-29
```

After each successful build, audit the split (offline, local files only):

```bash
uv run python -m evolution audit-supplemental-discovery \
  --instrument-id <INST> --split <SPLIT> --start <START> --end <END> \
  --dataset-root .local/evolution-data-supplemental \
  --output outputs/evolution-diagnostics/supplemental-audit-<SPLIT>-<inst-slug>.json
```

Acceptance:

- Each split has `manifest.json` with schema version 2, executable profile,
  correct UTC bounds, row/quote counts, and file hashes.
- Each audit report: no `error`, `state_timestamps.continuous` true (or gaps
  explicitly reported), `quote_quality.continuous` true (or gaps reported),
  `manifest_checks.issues` empty.
- A partial/failed build leaves no half-validated split presented as
  complete: if a build fails mid-window, record the failure and the split is
  not used until rebuilt and audited (note: the builder refuses to overwrite
  an existing target directory; a failed partial directory must be removed
  manually before retry, with the reason recorded in the background log).
- Transient S3 read errors are expected occasionally; a retry of the failed
  instrument is acceptable, and the final audit is the source of truth.

### Slice 2 — Market regime characterization (discovery-only diagnostic)

New report code + tests + durable note. All inputs are local dataset files;
no catalog access.

**Create:**

- `reports/market_regime_report.py`
- `tests/test_market_regime_report.py`
- `docs/research/market-regime-characterization.md`
- Generated artifact: `outputs/evolution-diagnostics/market-regime-map.json`

**Inputs (per instrument):** the five registered discovery folds and the
supplemental splits. Both expose the same `EvolutionMarketState` minute bars;
use `close` only for the regime math plus `ts_event`. Split sources (verified
2026-09-21):

| Instrument | Original folds source | Manifest schema |
| --- | --- | --- |
| BTCUSDT.BINANCE | `.local/evolution-data-v2/discovery_1..5` | 2 |
| ETHUSDT.BINANCE | `.local/evolution-data-v2/discovery_1..5` | 2 |
| BNBUSDT.BINANCE | `.local/evolution-data/discovery_1..5` (legacy root; no v2 rebuild exists) | 1 |
| all three | `.local/evolution-data-supplemental/discovery_supplemental_*` | 2 |

Loading rule: query `EvolutionMarketState` rows only from each split directory
via `ParquetDataCatalog(split_dir).query(...)` (do NOT use
`evolution.sandbox_worker.load_split` — it enforces `verify_manifest`, which
rejects the schema-1 BNB folds, and it also loads 1-second quotes that the
regime math does not need). Read each `manifest.json` as plain JSON for
bookkeeping (schema version, source bounds, row count); record
`manifest_schema` per split and flag any manifest/observed row-count mismatch
in the report output instead of crashing. Never read the remote catalog.

**Per UTC day, per instrument (deterministic, preregistered rules):**

- `r_d`: simple daily return, `close(last minute of d) / close(last minute of
  d-1) - 1`. Day 1 of the whole available sample has no prior day; mark
  `r` as null and skip that day for trend classification.
- `sigma_d`: standard deviation of 1-minute log returns within day `d`,
  annualized by sqrt(525600). Days with fewer than 600 one-minute closes are
  excluded from classification and reported as `insufficient_data`.
- `eff_d`: `|close_d - open_d| / sum(|1-minute close changes|)` (0..1);
  undefined denominator -> `insufficient_data`.
- Trailing baseline: the 30 complete UTC days strictly before `d` (all
  available earlier days for the first 30 days). Trailing only — no future
  data.
- **Vol regime:** `sigma_d >= median(trailing sigma)` -> `high_vol`, else
  `low_vol`.
- **Trend regime:** OPEN — to be decided in a follow-up session. Candidates
  under discussion: (A) `|r_d| >= 2 * median(trailing |r|)` only; (B)
  `eff_d >= 2 * median(trailing eff)` only; (C) both conditions (AND). The
  report must make the rule a single named, deterministic function so the
  choice can be fixed and the map regenerated without rework. Until decided,
  the daily table records `r_d`, `sigma_d`, `eff_d` and direction, and the
  coverage summary is produced per agreed rule at that time.
- **Direction:** `up` / `down` from the sign of `r_d` (recorded for every
  classified day; not part of the quadrant).
- **Regime label:** `<vol>_<trend>`, e.g. `high_vol_trending_up`.

**Report contents (`market-regime-map.json` + note tables):**

- Per instrument: per-day rows (date, r, sigma, eff, vol regime, trend
  regime, direction, source split).
- Regime coverage summary per instrument: day counts per regime label for
  (a) original discovery folds 2026-06-13..2026-07-12, (b) new supplemental
  2026-08-29..2026-09-20, (c) combined.
- A short "what the supplement adds" section: regime labels (or vol/trend
  combinations) materially under-represented in (a) but present in (b).

**Research note requirements** (`docs/research/market-regime-characterization.md`):

- State scope: discovery-only diagnostic, not a factor, not a hypothesis
  acceptance, no fitness/promotion use.
- Preregister the regime rules exactly as above (so the calendar in the note
  is reproducible).
- Record the documented **extended discovery calendar**: the original five
  folds plus the three new supplemental splits, each labeled with its
  regime coverage summary, and an explicit statement of which regimes the
  extended set covers that the original folds did not.
- Record data window, instruments, inputs, output paths, and the exact
  command to regenerate the map.
- Do not copy validation/holdout data or results anywhere in the note.

**Acceptance:**

- `uv run python -m unittest discover -s tests` passes, including new tests:
  synthetic state fixtures verify (i) vol/trend/direction classification on
  hand-computable series, (ii) trailing-only baseline (shifting a future day
  does not change an earlier day's label), (iii) gap/insufficient-day
  exclusion, (iv) source-split attribution.
- The report runs offline (no network, no catalog env required) and is
  deterministic (two runs produce identical JSON).
- Note follows `docs/research/README.md` conventions and is linked from
  `docs/research/current-focus.md`.

### Slice 3 — Documentation close-out (orchestrator)

- Update `docs/research/current-focus.md` (new supplemental data + regime map
  available; next-step list refreshed).
- Update `docs/ROADMAP.md` 2.6 checklist items that are now satisfied
  (documented extended discovery calendar; fold manifests/hashes via audit
  reports). Leave Sharpe-uncertainty and multiple-testing items open.
- Update `docs/research/openevolve-strategy-evolution.md` data section with
  the new supplemental coverage bounds.

## Global constraints

- No reads of validation or holdout splits by any new code or command.
- No writes to the catalog; read-only catalog access only (Slice 1 builds).
- Generated artifacts stay in `outputs/` and `.local/`; secrets stay out of
  tracked files.
- Timestamp semantics: completed one-minute states at interval end, no
  lookahead anywhere in the regime math.
- Preserve the two pre-existing dirty files (`.gitignore`,
  `docs/repository-guide.md`); do not touch them.
- Verification before reporting completion:
  `uv run python -m unittest discover -s tests` and `git diff --check`.
