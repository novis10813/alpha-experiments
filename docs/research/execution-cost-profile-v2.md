# Execution Cost Profile v2 (Preregistration Draft)

Status: DRAFT, 2026-10-07. Not in force. No code, gate, or ranking changes until
the activation checklist below is complete and the operator approves.

## Decision

Replace the official execution cost profile for new research families:

| Item | v1 (current) | v2 (proposed) |
| --- | --- | --- |
| Venue assumption | Binance spot | Binance USDⓈ-M perpetual |
| Fee per fill | 10 bps, both sides | 5 bps taker, both sides |
| Maker fills | not modeled | not modeled (see Out of scope) |
| Quotes and delay | one-second quotes, one-second delay | unchanged |
| Funding | not applicable | 1 bp charged against the position per funding timestamp crossed |
| Sensitivity fees | 0, 5, 10, 15 bps | 0, 2, 5, 10, 15 bps |
| Sensitivity delays | 0, 1, 5 seconds | unchanged |
| Profile ID | `spot-taker-v1` | `perp-taker-v2` |

Rationale for each value:

- **5 bps taker.** The intended trading venue is Binance USDⓈ-M perpetuals. The
  value is the published VIP0 taker fee, not a tuned parameter. No BNB discount is
  applied.
- **Taker on both sides.** Maker fills are adversely selected. Minute states and
  one-second quotes cannot model queue position or non-fills, so assuming maker
  fees would overstate the edge.
- **1 bp funding charge.** Binance's baseline funding rate is 0.01% per interval.
  Spot data has no funding series, so v2 charges this amount against the position
  in either direction. This is conservative for long holds and a placeholder
  until real funding data exists.
- **Sensitivity grid.** 2 bps is the maker reference, 5 bps is official, 10 bps
  is the v1 official value kept for comparability and as a 2x stress, and 15 bps
  is retained from v1.

Labels keep the v1 definitions, evaluated against the v2 official scenario:
`cost_fragile`, `delay_fragile`, `economically_rejected`, and
`delay_sensitive`. v2 adds one label and tightens one:

- `stress_fragile`: official (5 bps, 1 s) net Sharpe > 0 and stress (10 bps,
  1 s) net Sharpe <= 0. Blocks discovery qualification.
- `cost_robust`: official, delayed (5 bps, 5 s), and stress net Sharpe are all
  > 0.

## Why this is not a post-hoc cost change

The change is motivated by the venue, not by results. The operator confirmed on
2026-10-07 that the target venue is USDⓈ-M perpetuals.

Disclosure: before this decision, discovery-only observation studies A1-A3 and
F9 (artifacts under `outputs/observe-a1` through `outputs/observe-a3`) were
re-costed under perpetual fees. None of them passes under v2: the A3 4h reversal
was -4 to -11 bps per trade under taker/taker fees. The three v1 executable
champions were already negative at 5 bps in
[Cost and Delay Sensitivity](cost-delay-sensitivity.md). The fee value is fixed
by the venue's published schedule and cannot be chosen to rescue a result.

## Data basis: spot proxy

The catalog currently holds spot data only (`CurrencyPair` in
`evolution/instruments.py`). Until perpetual trade, depth, and funding data are
added (decision D2), v2 runs on spot data and results carry the label
`perp-taker-v2/spot-proxy`.

Known proxy gaps:

- Microstructure features (OBI, signed flow, spread) describe spot, not the
  perpetual book.
- Basis and real funding are not modeled.
- Price discovery may lead on perpetuals, which would make spot flow features
  lagging.

## Governance rules

1. **Scope.** v2 applies to families registered on or after the activation date.
2. **Existing families keep their v1 verdicts.** Re-evaluating
   `trend-flow-confirmation-v1`, `pullback-exhaustion-v1`, or
   `down-streak-risk-off-btc-v1` under v2 requires a new family ID and a newly
   registered hypothesis that discloses the v1 result. Rerunning a family under a
   lower cost after seeing its results is not allowed under the same ID.
3. **Spot-proxy ceiling.** Under `perp-taker-v2/spot-proxy`, a family may pass
   discovery qualification and consume validation. Holdout consumption requires
   perpetual data (see Q1).
4. **One holdout per underlying period.** Once perpetual data exists, the
   holdout lock must treat spot and perpetual instruments over the same
   underlying and period as one holdout. A new instrument ID such as
   `BTCUSDT-PERP.BINANCE` must not reopen a consumed holdout.
5. **Profile ID on every artifact.** Discovery manifests, rerank output,
   sensitivity output, and the family ledger record the profile ID. Gates refuse
   to compare results across profiles.

## Implementation scope after approval

Nothing in this list is implemented by this draft.

| File | Change |
| --- | --- |
| `evolution/spec.py` | Versioned fee constants per profile. Keep `spot-taker-v1` for legacy reproduction. |
| `evolution/sensitivity.py` | Official fee from the active profile, v2 fee grid, profile ID in payload, `stress_fragile` label and tightened `cost_robust`. |
| `evolution/qualification.py` | Reject `stress_fragile` candidates. |
| `evolution/backtest.py` | Funding charge per crossed funding timestamp. |
| `evolution/ledger.py` | Record profile ID per family. Enforce rules 3 and 4. |
| `evolution/instruments.py` | Unchanged under spot proxy. `CryptoPerpetual` once D2 lands. |
| `docs/research/promotion-protocol.md` | Update "Registered execution and sensitivity" and add `stress_fragile` to the discovery qualification list. |
| `tests/` | Profile selection, funding charge, ledger rules, cross-profile refusal. |

## Out of scope

- Maker execution modeling (decision D3). It needs tick-level queue and fill
  simulation from trade and depth data.
- Adding perpetual data to the catalog (decision D2). This happens in the
  homestack catalog builder, outside this repository.
- Re-running any existing family.

## Resolved questions (2026-10-07, operator)

- **Q1** Spot-proxy families may consume validation. Holdout waits for
  perpetual data (governance rule 3).
- **Q2** Funding is charged at 1 bp per funding timestamp crossed until real
  funding data exists.
- **Q3** `stress_fragile` is added and blocks discovery qualification.

## Activation checklist

- [ ] Operator verifies the current USDⓈ-M taker fee for the account tier and
      records the source and date here.
- [ ] Operator verifies the funding interval for each target symbol.
- [x] Q1-Q3 answered and recorded here.
- [ ] Operator approves activation and sets the activation date.
- [ ] Implementation and tests land as a separate change.
