# Down-Streak Pressure

## Status

`feature_candidate`

Down-down-down 1 minute kbar streaks with confirmed sell pressure show
conditional downside continuation on BTC. The effect is more structured than raw
order book imbalance, but it weakens after transaction costs and stricter event
de-overlap and does not generalize cleanly to ETH or BNB. Treat it as an
instrument- and regime-dependent filter candidate rather than a standalone
trading rule.

## Rule Definition

The rule combines a realized price pattern with pressure confirmation:

```text
down-down-down 1m kbar streak
+ confirmed orderbook sell pressure
=> possible downside continuation filter
```

The kbars are built from 1 second last trade prices:

```text
1m kbar return = close / open - 1
```

Events are clustered so each same-direction run contributes one event when it
first reaches three bars. This avoids counting every overlapping bar inside the
same streak as a separate event.

Pressure confirmation comes from 1 minute pressure persistence signals derived
from raw order book imbalance and signed trade flow:

```text
aligned_pressure = kbar_direction * confirmed_pressure_persistence_1m
```

where `kbar_direction` is `+1` for up-up-up and `-1` for down-down-down. The
screen below uses `aligned_pressure > 0.2` as the confirmation threshold.

## Data Windows

Initial 7 day diagnostic:

- Instrument: `BTCUSDT.BINANCE`
- Start: `2026-06-18T00:00:00Z`
- End: `2026-06-25T00:00:00Z`
- 1 minute kbars: `10,080`
- Clustered three-bar events: `1,235`

Longer stability request:

- Requested start: `2026-05-25T00:00:00Z`
- Requested end: `2026-06-25T00:00:00Z`
- Catalog returned: `2026-06-11T00:00:00Z` through
  `2026-06-24T23:59:59Z`
- 1 minute kbars: `18,718`
- Clustered three-bar events: `2,223`

Cross-instrument validation request:

- Instruments: `ETHUSDT.BINANCE`, `BNBUSDT.BINANCE`
- Requested start: `2026-05-25T00:00:00Z`
- Requested end: `2026-06-25T00:00:00Z`
- Catalog returned raw imbalance from `2026-06-11T00:00:00Z` through
  `2026-06-24T23:59:59Z`.
- 1 second trade price and feature exports covered `1,209,600` rows per
  instrument, from `2026-06-11T00:00:01Z` through `2026-06-25T00:00:00Z`.

## Commands

Generate the longer-window raw imbalance, prices, and signed trade features:

```bash
uv run python -m alphas.orderbook_imbalance \
  --instrument-id BTCUSDT.BINANCE \
  --start 2026-05-25T00:00:00Z \
  --end 2026-06-25T00:00:00Z \
  --output outputs/alphas/orderbook_imbalance_BTCUSDT_2026-05-25_2026-06-25.csv

uv run python -m data.trade_prices \
  --instrument-id BTCUSDT.BINANCE \
  --start 2026-05-25T00:00:00Z \
  --end 2026-06-25T00:00:00Z \
  --resample-seconds 1 \
  --output outputs/market/trade_prices_BTCUSDT_2026-05-25_2026-06-25_1s.csv

uv run python -m data.trade_features \
  --instrument-id BTCUSDT.BINANCE \
  --start 2026-05-25T00:00:00Z \
  --end 2026-06-25T00:00:00Z \
  --resample-seconds 1 \
  --output outputs/market/trade_features_BTCUSDT_2026-05-25_2026-06-25_1s_signed.csv
```

Generate the down-streak pressure screens:

```bash
uv run python -m reports.down_streak_pressure_report \
  --price-source outputs/market/trade_prices_BTCUSDT_2026-05-25_2026-06-25_1s.csv \
  --pressure-source outputs/alphas/confirmed_pressure_persistence_BTCUSDT_2026-06-11_2026-06-25_1m.csv \
  --feature-source outputs/market/trade_features_BTCUSDT_2026-05-25_2026-06-25_1s_signed.csv \
  --horizons-minutes 5 10 30 \
  --pressure-threshold 0.2 \
  --cooldown-minutes 0 5 30 \
  --cost-bps 0 2 5 10 \
  --output outputs/reports/down_streak_pressure_trade_count_BTCUSDT_2026-06-11_2026-06-25.html
```

Repeat with
`outputs/alphas/confirmed_volume_pressure_persistence_BTCUSDT_2026-06-11_2026-06-25_1m.csv`
and output
`outputs/reports/down_streak_pressure_volume_BTCUSDT_2026-06-11_2026-06-25.html`
for the signed-volume pressure version.

For ETH and BNB, repeat the same commands with the symbol-specific sources:

```bash
uv run python -m reports.down_streak_pressure_report \
  --price-source outputs/market/trade_prices_ETHUSDT_2026-05-25_2026-06-25_1s.csv \
  --pressure-source outputs/alphas/confirmed_pressure_persistence_ETHUSDT_2026-06-11_2026-06-25_1m.csv \
  --feature-source outputs/market/trade_features_ETHUSDT_2026-05-25_2026-06-25_1s_signed.csv \
  --horizons-minutes 5 10 30 \
  --pressure-threshold 0.2 \
  --cooldown-minutes 0 5 30 \
  --cost-bps 0 2 5 10 \
  --output outputs/reports/down_streak_pressure_trade_count_ETHUSDT_2026-06-11_2026-06-25.html
```

Repeat for `BNBUSDT`, and repeat both symbols with the corresponding
`confirmed_volume_pressure_persistence` source for the signed-volume pressure
version.

## Initial 7 Day Diagnostic

On the original 7 day window, `10,080` 1 minute kbars produced `1,235`
clustered three-bar events:

| Event | Count | 3-bar mean return | 3-bar median return |
| --- | ---: | ---: | ---: |
| up-up-up | `579` | `0.1080%` | `0.0837%` |
| down-down-down | `656` | `-0.1096%` | `-0.0870%` |

Three same-direction kbars identify a realized short-horizon move of roughly 8
to 11 basis points. However, simply following the third bar did not show broad
continuation edge. Up-up-up events leaned toward short-term pullback, while
down-down-down events showed only a small continuation bias.

Using `aligned_pressure > 0.2` as a confirmation threshold, the 7 day result was:

| Event | Pressure filter | Count | +5m directional return | +5m directional hit rate |
| --- | --- | ---: | ---: | ---: |
| up-up-up | trade-count pressure confirm | `256` | `-0.00975%` | `44.92%` |
| up-up-up | trade-count pressure neutral | `275` | `-0.02320%` | `42.55%` |
| down-down-down | trade-count pressure confirm | `257` | `0.00763%` | `50.58%` |
| down-down-down | trade-count pressure neutral | `353` | `-0.00026%` | `45.33%` |

Interpretation: up-up-up remained poor for chasing even with confirming
pressure, while down-down-down plus confirming sell pressure had a modest
downside continuation bias.

## Longer Stability Check

The longer request returned a 14 day available sample rather than a full month.
It produced `18,718` 1 minute kbars and `2,223` clustered three-bar events:

| Event | Count | 3-bar mean return |
| --- | ---: | ---: |
| up-up-up | `1,119` | `0.1058%` |
| down-down-down | `1,104` | `-0.1081%` |

For down-down-down events, pressure confirmation improved average directional
returns relative to unfiltered down-down-down events:

| Event | Filter | Count | +1m | +3m | +5m | +10m | +30m |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| down-down-down | unfiltered | `1,104` | `0.00244%` | `0.00157%` | `0.00117%` | `0.00037%` | `0.00699%` |
| down-down-down | trade-count pressure confirm | `405` | `0.00312%` | `0.00270%` | `0.00391%` | `0.00374%` | `0.01640%` |
| down-down-down | volume pressure confirm | `463` | `0.00332%` | `0.00329%` | `0.00383%` | `0.00601%` | `0.01984%` |

Interpretation: the downside continuation asymmetry survived the longer
available sample, but the edge is smaller than the initial 7 day result. At the
5 minute horizon the pressure-confirmed edge is around 0.4 basis points before
fees, spread, slippage, latency, and queue effects. The 30 minute result is
larger, but it is also more exposed to broader market regime and overlapping
event effects.

## Transaction Cost, De-Overlap, And Regime Screen

The down-streak pressure report computes:

- Gross directional forward return after the third down kbar.
- Net return after fixed round-trip costs of `0`, `2`, `5`, and `10` bps.
- Cooldown de-overlap using `0`, `5`, and `30` minute cooldowns.
- Regime splits by event-time trade density, realized volatility, and recent
  trend.

Trade-count pressure, all confirmed events:

| Cooldown | Horizon | Events | Gross avg | Net @ 2 bps | Net @ 5 bps | Net @ 10 bps |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0m | 5m | `405` | `0.00391%` | `-0.01609%` | `-0.04609%` | `-0.09609%` |
| 0m | 10m | `405` | `0.00374%` | `-0.01626%` | `-0.04626%` | `-0.09626%` |
| 0m | 30m | `404` | `0.01640%` | `-0.00360%` | `-0.03360%` | `-0.08360%` |
| 5m | 30m | `395` | `0.01607%` | `-0.00393%` | `-0.03393%` | `-0.08393%` |
| 30m | 30m | `254` | `0.00678%` | `-0.01322%` | `-0.04322%` | `-0.09322%` |

Signed-volume pressure, all confirmed events:

| Cooldown | Horizon | Events | Gross avg | Net @ 2 bps | Net @ 5 bps | Net @ 10 bps |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0m | 5m | `463` | `0.00383%` | `-0.01617%` | `-0.04617%` | `-0.09617%` |
| 0m | 10m | `463` | `0.00601%` | `-0.01399%` | `-0.04399%` | `-0.09399%` |
| 0m | 30m | `462` | `0.01984%` | `-0.00016%` | `-0.03016%` | `-0.08016%` |
| 5m | 30m | `450` | `0.02006%` | `0.00006%` | `-0.02994%` | `-0.07994%` |
| 30m | 30m | `277` | `0.00706%` | `-0.01294%` | `-0.04294%` | `-0.09294%` |

De-overlap interpretation: a 5 minute cooldown barely changes the 30 minute
gross result, but a 30 minute cooldown cuts event count by about 40% and reduces
the gross edge to roughly 0.7 bps. This suggests part of the 30 minute edge is
path overlap or clustered market state, not fully independent event edge.

Regime split highlights at the 30 minute horizon:

| Pressure | Regime | Events | Gross avg | Net @ 2 bps |
| --- | --- | ---: | ---: | ---: |
| trade-count | density high | `214` | `0.02388%` | `0.00388%` |
| trade-count | volatility high | `202` | `0.02262%` | `0.00262%` |
| trade-count | trend down | `235` | `0.02434%` | `0.00434%` |
| volume | density high | `243` | `0.03104%` | `0.01104%` |
| volume | volatility high | `231` | `0.03304%` | `0.01304%` |
| volume | trend down | `264` | `0.02415%` | `0.00415%` |

After a 30 minute cooldown, the same regime edges weaken materially:

| Pressure | Regime | Events | 30m gross avg | Net @ 2 bps |
| --- | --- | ---: | ---: | ---: |
| trade-count | density high | `133` | `0.01938%` | `-0.00062%` |
| trade-count | volatility high | `127` | `0.01678%` | `-0.00322%` |
| volume | density high | `142` | `0.02427%` | `0.00427%` |
| volume | volatility high | `138` | `0.02711%` | `0.00711%` |

Interpretation: the structure does not survive even modest taker-style costs at
5m or 10m. At 30m, the gross edge can approach 2 bps and the high-density or
high-volatility signed-volume regimes can remain slightly positive after a 2 bps
cost assumption, but this weakens under stricter 30 minute de-overlap. Treat the
result as a regime/filter candidate, not an executable standalone rule.

## ETH And BNB Validation

The same down-streak pressure screen was repeated for ETH and BNB on the
available `2026-06-11` to `2026-06-25` sample. This is a validation of whether
the BTC structure persists across instruments, not a new rule definition.

Raw down-streak counts and pressure-confirmed events:

| Instrument | Pressure | 1m kbars | Raw down3 events | Confirmed events | 30m cooldown events |
| --- | --- | ---: | ---: | ---: | ---: |
| ETHUSDT | trade-count | `20,161` | `1,101` | `217` | `167` |
| ETHUSDT | volume | `20,161` | `1,101` | `217` | `161` |
| BNBUSDT | trade-count | `20,161` | `1,069` | `203` | `145` |
| BNBUSDT | volume | `20,161` | `1,069` | `227` | `155` |

All confirmed events:

| Instrument | Pressure | Cooldown | 5m gross | 10m gross | 30m gross | 30m net @ 2 bps |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| ETHUSDT | trade-count | 0m | `-0.01522%` | `-0.02255%` | `-0.04912%` | `-0.06912%` |
| ETHUSDT | trade-count | 30m | `-0.00765%` | `-0.01498%` | `-0.03604%` | `-0.05604%` |
| ETHUSDT | volume | 0m | `-0.02259%` | `-0.03278%` | `-0.05624%` | `-0.07624%` |
| ETHUSDT | volume | 30m | `-0.01232%` | `-0.02445%` | `-0.04394%` | `-0.06394%` |
| BNBUSDT | trade-count | 0m | `-0.00543%` | `-0.00913%` | `0.00012%` | `-0.01988%` |
| BNBUSDT | trade-count | 30m | `-0.00530%` | `-0.00488%` | `0.02229%` | `0.00229%` |
| BNBUSDT | volume | 0m | `-0.00127%` | `-0.00035%` | `0.01254%` | `-0.00746%` |
| BNBUSDT | volume | 30m | `-0.00360%` | `-0.00025%` | `0.02500%` | `0.00500%` |

Regime highlights at the 30 minute horizon after a 30 minute cooldown:

| Instrument | Pressure | Regime | Events | 30m gross avg | Net @ 2 bps |
| --- | --- | --- | ---: | ---: | ---: |
| ETHUSDT | trade-count | density high | `84` | `-0.04474%` | `-0.06474%` |
| ETHUSDT | trade-count | volatility high | `84` | `-0.05118%` | `-0.07118%` |
| ETHUSDT | volume | density high | `106` | `-0.03460%` | `-0.05460%` |
| ETHUSDT | volume | volatility high | `81` | `-0.06503%` | `-0.08503%` |
| BNBUSDT | trade-count | density high | `76` | `0.00798%` | `-0.01202%` |
| BNBUSDT | trade-count | volatility high | `73` | `0.01895%` | `-0.00105%` |
| BNBUSDT | volume | density high | `84` | `0.02644%` | `0.00644%` |
| BNBUSDT | volume | volatility high | `78` | `0.02875%` | `0.00875%` |
| BNBUSDT | volume | trend down | `80` | `0.02768%` | `0.00768%` |

Interpretation: ETH rejects the BTC continuation structure in this sample. The
pressure-confirmed down-streak events lean toward rebound rather than downside
continuation, including in high-density, high-volatility, and down-trend
regimes. BNB has a weak 30 minute signed-volume continuation pattern, but 5m and
10m horizons are flat to negative and the 30m edge is thin after a 2 bps
round-trip cost. This makes down-streak pressure instrument-specific rather than
a robust cross-instrument rule alpha.

## Caveats

- The longer sample was requested as one month, but the catalog returned about
  14 days.
- The report clusters same-direction runs, but longer forward horizons can still
  overlap across nearby events.
- The cost screen uses fixed bps assumptions and does not model queue position,
  partial fills, maker/taker fee schedules, or adverse selection.
- ETH and BNB validation used trade-price forward returns and fixed bps cost
  assumptions; quote-based entry and exit prices have not been applied to this
  rule.

## Remaining Optional Work

- If this line continues, focus on BTC or BNB signed-volume 30 minute regimes
  rather than a universal cross-instrument rule.
- Add explicit volatility, trade-density, and broader-market trend gates before
  considering any backtest.
- Use quote-based entry/exit prices if this rule is promoted beyond a filter
  candidate.
