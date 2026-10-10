# T09: Volatility State and Forward Excursion

Status: in progress. Run `excursion-v1` is descriptive, with preregistered check
C1 (magnitude) passed and C2 (direction) failed.

## Question

A2 ([T08](../T08-observation-studies/REPORT.md)) measured large moves with the
return between the start and the end of a fixed window. A trade is closed by
whichever barrier the path reaches first, so this run measures the forward
maximum and minimum within the window instead, grouped by the trailing volatility
state.

## Setup

- Data: BTC, ETH, and BNB spot discovery splits, 51 days per instrument, 6 blocks
  (discovery_1..5 and supplemental). No validation or holdout data.
- State: decile of `rv_60` (trailing 60 min realized volatility) within the
  trailing 7 days. Uses data up to t only, which fixes the full-sample percentile
  used in the A2 conditional table.
- Targets over (t, t+h], h = 30, 60, 240 min, minute-close mid:
  maximum return U, minimum return D, R = max(U, |D|), the minute each barrier is
  first reached, and the end return for comparison.
- Barrier b = 2 x v1 round-trip cost, 40 bps on all three instruments (median
  spread is at most 0.2 bps).
- Main table: non-overlapping samples, one every h minutes. Checks: minute-pooled
  samples with the A2 block rule (same sign in at least 5 of 6 blocks on at least
  2 of 3 instruments).
- Trials: 18 screened cells (C1 and C2, 3 instruments x 3 horizons). The
  descriptive tables cover 6 barriers (1 to 3 x v1 and draft v2 cost) and both
  samplings.

## Results

### Path touches are about twice as frequent as end-of-window moves

Probability that |move| reaches 40 bps, all deciles, non-overlapping samples:

| Instrument | h | Path touch | End of window |
| --- | --- | --- | --- |
| BTC | 30 | 0.19 | 0.11 |
| BTC | 60 | 0.38 | 0.20 |
| BTC | 240 | 0.80 | 0.47 |
| ETH | 30 | 0.30 | 0.17 |
| ETH | 60 | 0.54 | 0.28 |
| ETH | 240 | 0.89 | 0.57 |
| BNB | 30 | 0.22 | 0.12 |
| BNB | 60 | 0.44 | 0.24 |
| BNB | 240 | 0.89 | 0.53 |

A2's end-of-window target understated how often a 40 bps barrier is reached by a
factor of 1.6 to 1.9.

### Volatility state predicts the touch at 30 and 60 minutes

Path touch probability at 40 bps by `rv_60` decile:

| Instrument | h | Decile 1 | Decile 5 | Decile 10 |
| --- | --- | --- | --- | --- |
| BTC | 30 | 0.05 | 0.11 | 0.56 |
| BTC | 60 | 0.13 | 0.25 | 0.73 |
| ETH | 30 | 0.10 | 0.22 | 0.63 |
| ETH | 60 | 0.25 | 0.51 | 0.81 |
| BNB | 30 | 0.07 | 0.19 | 0.53 |
| BNB | 60 | 0.20 | 0.45 | 0.73 |

C1 (deciles 9-10 touch more often than deciles 1-2) passed in all 9 cells: 6 of 6
blocks at 30 min on all instruments, and 5 or 6 of 6 at 60 and 240 min. At 240
min most windows reach 40 bps in every decile (0.56 to 1.00), so the state mainly
changes the time to the touch. Median minutes to first touch, decile 1 against
decile 10, are 84 and 26 (BTC), 50 and 19 (ETH), and 94 and 20 (BNB). The 240 min
deciles hold only 20 to 34 non-overlapping samples each.

### Direction of the first touch is a coin flip

Share of touched windows that reach +40 bps before -40 bps, minute-pooled, deciles
9-10, and the C2 block count:

| Instrument | 30 min | 60 min | 240 min |
| --- | --- | --- | --- |
| BTC | 0.510 (3/6) | 0.490 (4/6) | 0.483 (4/6) |
| ETH | 0.513 (3/6) | 0.505 (3/6) | 0.493 (4/6) |
| BNB | 0.521 (3/6) | 0.516 (3/6) | 0.534 (4/6) |

C2 failed in all 9 cells. In non-overlapping samples the up-first share ranges
from 0.25 to 0.71 across deciles with no monotone pattern.

### Trade high/low gives slightly higher touch rates

Using minute trade high and low instead of minute-close mid raises the touch
probability by 0 to 15 percentage points. Part of that is bid-ask bounce, so the
mid values above are the main estimate.

## Interpretation

High volatility tells when a 40 bps barrier will be reached, and that is stable
across blocks and instruments. It does not tell which side is reached first, so
symmetric barriers entered at t have no gross edge in any state. A tradable rule
needs a second step: what the path does after the first touch.

## Rejected follow-ups

Two follow-ups searched for direction instead of studying volatility and were
reverted. Breakout events were defined as a b bps move from an arbitrary
reference price (the end of the previous event), which is not a channel or range
breakout.

- `excursion-v2`: continuation after a first b bps touch, b = 20 to 60 bps.
  Continuation was 0.44 to 0.55 against 0.625 needed. Rejected: 9 direction cells
  and 54 economics configs, none passed.
- `excursion-v3`: taker flow and top-10 OBI at the same events, with an August
  discovery supplement (2026-07-25 to 2026-08-27). Rejected: 24 direction cells
  and 432 instrument configs, none passed.

The code and full results are kept in the task branch history and the
`exp/T09-excursion-v2` and `exp/T09-excursion-v3` tags.

## Limitations

- Spot data as a proxy for the perpetual venue.
- 51 days per instrument. The 240 min decile cells are small.
- Minute-close mid misses moves within the minute.
