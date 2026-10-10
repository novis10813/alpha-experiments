# T09: Volatility State and Forward Excursion

Status: in progress. `excursion-v1` is descriptive: C1 (magnitude) passed and C2
(direction) failed. `excursion-v2` (continuation after the first touch) is
`rejected`: C3 and C4 failed. `excursion-v3` (flow and OBI at the breakout) is
`rejected`: C5 and C6 failed, with an OBI pattern on BTC and ETH recorded below as
a hypothesis.

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
symmetric barriers entered at t have no gross edge in any state. `excursion-v2`
tested the next step, continuation after the first touch, and found none.

## excursion-v2: continuation after the first touch

### Setup

- Breakout events, sequential and non-overlapping: the first minute that mid moves
  b away from a reference price within h minutes. Side = direction of that move.
- Continuation: from the breakout mid, whether the price moves a further b in the
  same direction before b back, within h. A random walk gives 0.5.
- Trade: enter one minute after the breakout at the ask (long) or bid (short),
  same barriers, exit at the bid or ask. Fees 5 bps per side (draft v2 taker) and
  10 bps (v1).
- Grid: b = 20, 40, 60 bps (1 to 3 x v1 cost), h = 30, 60, 240 min, all events and
  `rv_60` decile 9-10 at the breakout.
- Trials: C3 9 cells, C4 54 configs.

### Continuation is not above 0.5

Decile 9-10 at b = 40 bps. Continuation share of resolved events, mean gross and
v2 net per trade in bps:

| Instrument | h | Events | Continuation | Gross | Net v2 |
| --- | --- | --- | --- | --- | --- |
| BTC | 30 | 245 | 0.457 | -3.6 | -13.6 |
| BTC | 60 | 226 | 0.462 | -1.8 | -11.8 |
| BTC | 240 | 222 | 0.516 | 1.6 | -8.4 |
| ETH | 30 | 311 | 0.468 | -1.5 | -11.5 |
| ETH | 60 | 302 | 0.467 | 0.6 | -9.4 |
| ETH | 240 | 310 | 0.461 | 2.6 | -7.4 |
| BNB | 30 | 224 | 0.553 | 5.2 | -4.8 |
| BNB | 60 | 212 | 0.541 | 4.7 | -5.3 |
| BNB | 240 | 213 | 0.435 | -2.1 | -12.1 |

With symmetric barriers, breakeven continuation is

$$
p^* = 0.5 + \frac{\text{round-trip cost}}{2b}
$$

which is 0.625 at b = 40 bps under v2 fees. No cell comes close.

- C3 failed. Only ETH at 60 and 240 min kept the same side of 0.5 in 5 of 6
  blocks, both below 0.5 (0.467 and 0.461). No horizon has two instruments.
- C4 failed. None of the 54 configs has positive v2 net. The best per instrument
  is -1.8 bps (ETH, b = 60, h = 240, decile 9-10), -4.8 bps (BNB), and -7.2 bps
  (BTC). Gross per trade ranges from -10.3 to +8.2 bps across the grid.
- At b = 20 bps, with 1,334 to 2,111 events per cell, continuation is 0.47 to 0.49
  on every instrument and horizon. That is a slight reversal, far below the 1.0
  that a 20 bps barrier would need under v1 cost.

### Conclusion

After a first touch the path is again close to a coin flip, in every volatility
state. Price and `rv_60` alone give no direction edge on this spot data.

## excursion-v3: flow and order book imbalance at the breakout

### Setup

- Data: the six blocks above plus an August discovery supplement, 2026-07-25 to
  2026-08-27 (34 days, coverage audit passed), as a seventh block. Data from
  2026-09-21 onward is reserved as out-of-sample and was not built.
- Events, continuation, and the breakout-direction trade as in excursion-v2.
- Features at the breakout minute, from data up to that minute: `flow_w`, net
  taker buy volume over total volume, and `obi_w`, mean top-10-level order book
  imbalance, over the trailing w = 15 or 60 minutes. Each is multiplied by the
  breakout side. Positive means the feature supports the breakout (confirm),
  negative means it opposes it (oppose).
- C5 direction: continuation share of confirm minus oppose. An instrument passes
  if the sign repeats in at least 6 of 7 blocks. A cell passes if at least 2
  instruments pass with the same sign. 24 cells (4 features, 3 horizons, b = 20
  or 40 bps).
- C6 economics: follow the breakout when the feature confirms, fade it when the
  feature opposes. Pass on an instrument: v2 net > 0, t >= 2, at least 5 of 7
  blocks positive, n >= 30. Candidate if the same config passes on at least 2
  instruments. 144 configs per instrument.

### Results

- C5 failed in all 24 cells. Flow has no consistent sign. OBI is positive on BTC
  and ETH and negative on BNB: four cells have two passing instruments, but each
  pair has opposite signs (BTC positive, BNB negative).
- On BTC and ETH, confirming OBI raises continuation by 0.02 to 0.14. ETH
  `obi_60` at b = 20 bps passes 6 of 7 blocks at every horizon (+0.04 at each).
  The confirm group still stays near 0.5 (0.47 to 0.58), below the 0.625 that b =
  40 bps needs under v2 cost.
- C6 failed. 11 of 432 instrument configs have positive v2 net, none has t >= 2,
  and the largest of those 11 have 19 to 32 trades. The best config with at least
  100 trades is +1.7 bps (ETH, `obi_60`, b = 60, h = 240, decile 9-10, t = 0.27).

Descriptive, using full-sample quintiles of the aligned feature (not a pass rule):
at b = 40 bps, events whose `obi_60` most strongly opposes the breakout
(quintile 1) continue in 0.34 to 0.41 of resolved cases on BTC and ETH. That is a
reversal share of 0.59 to 0.66, around the 0.625 a fade needs. BNB shows no such
pattern (0.56 to 0.66 in quintile 1).

### Conclusion

Flow at the breakout carries no information about continuation. OBI that opposes a
breakout is followed by more reversals on BTC and ETH, but the effect is not
consistent across instruments, does not pass the block rule, and is too small to
pay v2 cost under the preregistered sign split. The strong-opposition fade is a
hypothesis for a separate preregistered test with trailing thresholds, not a
result.

## Limitations

- Spot data as a proxy for the perpetual venue.
- 51 days per instrument (85 in excursion-v3). The 240 min decile cells are
  small.
- Minute-close mid misses moves within the minute.
