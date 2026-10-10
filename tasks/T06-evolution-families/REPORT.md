# T06: Evolution Hypothesis Families

Milestone 2 hypothesis families are documented in their preregistrations below. The registered entry signal diagnostic fixes a bounded, discovery-only protocol; the source records no measured diagnostic results.

## Family status

| Family | Status | Preregistration |
| --- | --- | --- |
| `trend-flow-confirmation-v1` | Holdout consumed, `rejected` (recorded 2026-09-21; the local family ledger is authoritative). | [Trend Flow Confirmation v1](../../evolution/families/trend-flow-confirmation-v1/README.md) |
| `pullback-exhaustion-v1` | Preregistered; no final status recorded in the family README. | [Pullback Exhaustion v1](../../evolution/families/pullback-exhaustion-v1/README.md) |
| `down-streak-risk-off-btc-v1` | Preregistered; no final status recorded in the family README. | [Down Streak Risk Off BTC v1](../../evolution/families/down-streak-risk-off-btc-v1/README.md) |

## Registered entry signal diagnostic

### Fixed protocol, not governance approval

The specification below fixes this diagnostic's protocol in code and documentation.
Calling it preregistered does not mean that a governance review approved the
hypothesis, family, or results. This is a bounded, discovery-only diagnostic for a
registered declarative family on an explicitly allowed supplemental discovery
dataset. It is not a strategy, a full portfolio backtest, a significance test, or an
alpha claim.

- **Signal:** the registered family seed's `RULE_SPEC` entry conditions.
- **Entry semantics:** all entry conditions must match on the current completed
  `EvolutionMarketState`; confirmations are exact consecutive finite states, using
  the same confirmation semantics as the declarative rule interpreter.
- **State order:** chronological `ts_event` order. A missing/non-one-minute state
  transition resets confirmations and starts a new warmup period.
- **Warmup:** exclude the first 60 minutes and every event during the first 60
  contiguous minutes after a gap.
- **Event sampling:** select events chronologically with at least 60 minutes between
  events for the family. Sampling is performed before outcomes are calculated and
  never uses outcomes to select events.
- **Horizons:** 15, 30, and 60 minutes, all evaluated at the same event times.
- **Execution:** with the executable 1-second quote profile and a 1-second delay,
  buy the ask at the first quote at or after `event_ts + 1s`; sell the bid at the
  first quote at or after `event_ts + horizon + 1s`.
- **Quote tolerance:** the selected quote may be at most one second late. Missing,
  invalid, crossed, mismatched, or late quotes exclude the observation. There is no
  interpolation.
- **Boundaries/gaps:** an observation is excluded if its scheduled execution crosses
  the split end or if the quote path from entry through scheduled exit crosses a
  quote gap.
- **Costs:** 10 bps on each side. Reports include gross and fee-adjusted net bps,
  counts, and win rate by UTC day and overall.
- **Audit:** supplemental date/split guards, manifest/profile/hash checks, and the
  existing local Nautilus loader are used. All validation occurs before the loader.
- **Mechanism label:** `down-streak-risk-off-btc-v1` is reported as a risk-off
  long/flat filter; the diagnostic does not invent a bullish interpretation.

### Results and limitations

No measured counts, win rates, or gross/net bps summaries are recorded in the
source diagnostic note. The diagnostic must not feed candidate generation,
threshold sweeps, ranking, promotion gates, or validation/holdout access.
