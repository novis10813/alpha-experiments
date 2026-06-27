# Order Book Imbalance

## Status

`feature_candidate`

Order book imbalance has measurable short-horizon directional information, but
the observed edge is small. Treat it as a microstructure feature, confirmation
signal, execution-timing input, or regime-specific filter rather than a
standalone tradable alpha.

## Definition

- Alpha name: `orderbook_imbalance_depth10`
- Formula: `(bid_size - ask_size) / (bid_size + ask_size)`
- Nautilus data type: `OrderBookDepth10`
- Instrument: `BTCUSDT.BINANCE`
- Timestamp: `ts_event`, the event time when the depth snapshot makes the signal
  knowable.
- Canonical row shape: `ts_event, instrument_id, alpha_name, value`

## Data Window

- Start: `2026-06-18T00:00:00Z`
- End: `2026-06-25T00:00:00Z`
- Alpha rows: `604,792`
- Full trade price rows exported for validation: `22,499,242`
- Research price source: 1 second last trade price, `509,353` rows
- Research price median gap: `1.054s`

The first relationship reports used an 8,000 row visualization price overlay.
That file was too sparse for 10s, 30s, and 60s forward-return diagnostics. The
results below use the corrected 1 second last trade price source.

## Commands

Generate the alpha:

```bash
uv run python -m alphas.orderbook_imbalance \
  --instrument-id BTCUSDT.BINANCE \
  --start 2026-06-18T00:00:00Z \
  --end 2026-06-25T00:00:00Z \
  --output outputs/alphas/orderbook_imbalance_BTCUSDT_2026-06-18_2026-06-25.csv
```

Generate 1 second last trade prices:

```bash
uv run python -m data.trade_prices \
  --instrument-id BTCUSDT.BINANCE \
  --start 2026-06-18T00:00:00Z \
  --end 2026-06-25T00:00:00Z \
  --resample-seconds 1 \
  --output outputs/market/trade_prices_BTCUSDT_2026-06-18_2026-06-25_1s.csv
```

Generate relationship reports:

```bash
uv run python -m reports.alpha_relationship_report \
  outputs/alphas/orderbook_imbalance_BTCUSDT_2026-06-18_2026-06-25.csv \
  --price-source outputs/market/trade_prices_BTCUSDT_2026-06-18_2026-06-25_1s.csv \
  --output outputs/reports/orderbook_imbalance_relationship_BTCUSDT_2026-06-18_2026-06-25_10s_1s_prices.html \
  --horizons-seconds 10 \
  --bucket-count 10 \
  --max-points 8000
```

Repeat with `--horizons-seconds 30` and `--horizons-seconds 60` for the other
relationship reports.

Generate the extreme imbalance event study:

```bash
uv run python -m reports.extreme_imbalance_report \
  outputs/alphas/orderbook_imbalance_BTCUSDT_2026-06-18_2026-06-25.csv \
  --price-source outputs/market/trade_prices_BTCUSDT_2026-06-18_2026-06-25_1s.csv \
  --output outputs/reports/orderbook_imbalance_extreme_BTCUSDT_2026-06-18_2026-06-25.html \
  --thresholds 0.95 0.98 \
  --horizons-seconds 1 5 10 30 60
```

Generate 1 second trade price and volume features:

```bash
uv run python -m data.trade_features \
  --instrument-id BTCUSDT.BINANCE \
  --start 2026-06-18T00:00:00Z \
  --end 2026-06-25T00:00:00Z \
  --resample-seconds 1 \
  --output outputs/market/trade_features_BTCUSDT_2026-06-18_2026-06-25_1s.csv
```

Generate the volume interaction report:

```bash
uv run python -m reports.volume_interaction_report \
  outputs/alphas/orderbook_imbalance_BTCUSDT_2026-06-18_2026-06-25.csv \
  --feature-source outputs/market/trade_features_BTCUSDT_2026-06-18_2026-06-25_1s.csv \
  --output outputs/reports/orderbook_imbalance_volume_interaction_BTCUSDT_2026-06-18_2026-06-25_30s.html \
  --horizons-seconds 30 \
  --bucket-count 10 \
  --max-points 8000
```

Generate the trade density regime report:

```bash
uv run python -m reports.trade_density_report \
  outputs/alphas/orderbook_imbalance_BTCUSDT_2026-06-18_2026-06-25.csv \
  --feature-source outputs/market/trade_features_BTCUSDT_2026-06-18_2026-06-25_1s_with_count.csv \
  --output outputs/reports/orderbook_imbalance_trade_density_BTCUSDT_2026-06-18_2026-06-25.html \
  --horizons-seconds 10 30 60 \
  --bucket-count 10
```

Generate 1 second signed trade features:

```bash
uv run python -m data.trade_features \
  --instrument-id BTCUSDT.BINANCE \
  --start 2026-06-18T00:00:00Z \
  --end 2026-06-25T00:00:00Z \
  --resample-seconds 1 \
  --output outputs/market/trade_features_BTCUSDT_2026-06-18_2026-06-25_1s_signed.csv
```

Generate signed flow absorption reports:

```bash
uv run python -m reports.signed_flow_absorption_report \
  outputs/alphas/orderbook_imbalance_BTCUSDT_2026-06-18_2026-06-25.csv \
  --feature-source outputs/market/trade_features_BTCUSDT_2026-06-18_2026-06-25_1s_signed.csv \
  --output outputs/reports/orderbook_imbalance_signed_flow_absorption_BTCUSDT_2026-06-18_2026-06-25.html \
  --horizons-seconds 10 30 60
```

Repeat with `--flow-column volume_imbalance` and output
`outputs/reports/orderbook_imbalance_signed_volume_absorption_BTCUSDT_2026-06-18_2026-06-25.html`
for signed volume flow.

Generate 1 minute confirmed pressure persistence:

```bash
uv run python -m alphas.pressure_persistence \
  outputs/alphas/orderbook_imbalance_BTCUSDT_2026-06-18_2026-06-25.csv \
  --feature-source outputs/market/trade_features_BTCUSDT_2026-06-18_2026-06-25_1s_signed.csv \
  --bucket-seconds 60 \
  --output outputs/alphas/confirmed_pressure_persistence_BTCUSDT_2026-06-18_2026-06-25_1m.csv
```

Generate the 1m/3m/5m relationship report:

```bash
uv run python -m reports.alpha_relationship_report \
  outputs/alphas/confirmed_pressure_persistence_BTCUSDT_2026-06-18_2026-06-25_1m.csv \
  --price-source outputs/market/trade_prices_BTCUSDT_2026-06-18_2026-06-25_1s.csv \
  --output outputs/reports/confirmed_pressure_persistence_relationship_BTCUSDT_2026-06-18_2026-06-25_1m_3m_5m.html \
  --horizons-seconds 60 180 300 \
  --bucket-count 10 \
  --max-points 8000
```

Repeat with `--flow-column volume_imbalance`,
`--alpha-name confirmed_volume_pressure_persistence_1m`, and output
`outputs/alphas/confirmed_volume_pressure_persistence_BTCUSDT_2026-06-18_2026-06-25_1m.csv`
for the signed volume version.

## Reports

- 10s relationship: `outputs/reports/orderbook_imbalance_relationship_BTCUSDT_2026-06-18_2026-06-25_10s_1s_prices.html`
- 30s relationship: `outputs/reports/orderbook_imbalance_relationship_BTCUSDT_2026-06-18_2026-06-25_30s_1s_prices.html`
- 60s relationship: `outputs/reports/orderbook_imbalance_relationship_BTCUSDT_2026-06-18_2026-06-25_60s_1s_prices.html`
- Extreme event study: `outputs/reports/orderbook_imbalance_extreme_BTCUSDT_2026-06-18_2026-06-25.html`
- Volume interaction 10s: `outputs/reports/orderbook_imbalance_volume_interaction_BTCUSDT_2026-06-18_2026-06-25_10s.html`
- Volume interaction 30s: `outputs/reports/orderbook_imbalance_volume_interaction_BTCUSDT_2026-06-18_2026-06-25_30s.html`
- Volume interaction 60s: `outputs/reports/orderbook_imbalance_volume_interaction_BTCUSDT_2026-06-18_2026-06-25_60s.html`
- Trade density regime: `outputs/reports/orderbook_imbalance_trade_density_BTCUSDT_2026-06-18_2026-06-25.html`
- Signed trade-count flow absorption: `outputs/reports/orderbook_imbalance_signed_flow_absorption_BTCUSDT_2026-06-18_2026-06-25.html`
- Signed volume flow absorption: `outputs/reports/orderbook_imbalance_signed_volume_absorption_BTCUSDT_2026-06-18_2026-06-25.html`
- Confirmed pressure persistence 1m relationship: `outputs/reports/confirmed_pressure_persistence_relationship_BTCUSDT_2026-06-18_2026-06-25_1m_3m_5m.html`
- Confirmed volume pressure persistence 1m relationship: `outputs/reports/confirmed_volume_pressure_persistence_relationship_BTCUSDT_2026-06-18_2026-06-25_1m_3m_5m.html`

## Key Findings

Decile bucket ranking is present after correcting the price source:

| Horizon | Bucket 10 - Bucket 1 mean return |
| --- | ---: |
| 10s | `0.0169%` |
| 30s | `0.0185%` |
| 60s | `0.0183%` |

Extreme imbalance events have higher directional hit rates, but the average
directional return remains small:

| Threshold | Side | 30s mean directional return | 30s directional hit rate | 60s mean directional return | 60s directional hit rate |
| --- | --- | ---: | ---: | ---: | ---: |
| `0.95` | positive | `0.00933%` | `63.65%` | `0.00914%` | `58.85%` |
| `0.95` | negative | `0.00984%` | `64.73%` | `0.00975%` | `59.76%` |
| `0.98` | positive | `0.01074%` | `64.42%` | `0.01035%` | `58.91%` |
| `0.98` | negative | `0.01101%` | `65.69%` | `0.01086%` | `60.27%` |

Trade volume interaction was tested with 1 second trade features:

- `price`: last trade price in the 1 second bucket
- `volume`: summed trade size in the 1 second bucket
- interaction signal: `imbalance * (log1p(volume) / mean(log1p(volume)))`

The multiplicative interaction did not improve the decile spread:

| Horizon | Raw imbalance spread | Volume interaction spread |
| --- | ---: | ---: |
| 10s | `0.01685%` | `0.01318%` |
| 30s | `0.01853%` | `0.01392%` |
| 60s | `0.01834%` | `0.01350%` |

Volume looked more useful as a regime filter. Splitting by log-volume intensity
above or below `1.0` gave:

| Horizon | High-volume spread | Low-volume spread |
| --- | ---: | ---: |
| 10s | `0.02061%` | `0.01531%` |
| 30s | `0.02080%` | `0.01746%` |
| 60s | `0.02132%` | `0.01710%` |

Trade density was tested as the number of trade ticks in the 1 second feature
bucket. Density is distinct from trade volume: it measures how many trades
occurred, not how much size traded.

The 1 second trade count distribution was highly skewed:

| Metric | Trades per second |
| --- | ---: |
| min | `1` |
| median | `4` |
| mean | `44.17` |
| p90 | `148` |
| p99 | `440` |
| max | `9,188` |

Median-split density regimes showed higher imbalance value in denser periods:

| Horizon | Low-density spread | High-density spread |
| --- | ---: | ---: |
| 10s | `0.01256%` | `0.01862%` |
| 30s | `0.01491%` | `0.01989%` |
| 60s | `0.01522%` | `0.01955%` |

The top decile density regime was stronger:

| Horizon | Top-decile density spread | Rest-of-sample spread |
| --- | ---: | ---: |
| 10s | `0.02331%` | `0.01569%` |
| 30s | `0.02360%` | `0.01769%` |
| 60s | `0.02477%` | `0.01745%` |

This supports the interpretation that order book imbalance is more informative
when trading is dense. The effect is still modest, but trade density is a better
regime variable than the direct multiplicative volume interaction tested above.

## Trade Density Interpretation

High trade density means the short-horizon marketable order arrival rate is high.
It should not be interpreted directly as "more retail flow" or "more institutional
flow." With the current data, trade count alone does not identify participant
type.

More defensible interpretations:

- New information or cross-market pressure may be getting incorporated.
- Liquidity taking is active, with many marketable orders hitting the book.
- A large parent order may be split into many child trades.
- Market makers, liquidations, arbitrage, and execution algorithms may all be
  contributing to the observed trade count.

The useful research question is therefore not "are these retail traders?" but:

```text
Who is taking liquidity, on which side, and is passive liquidity absorbing or
being consumed by that flow?
```

Trade density alone says activity is high. To infer whether order book imbalance
is pressure continuation or absorption, it needs to be combined with signed trade
flow.

## Next Hypothesis: Signed Flow And Absorption

The next experiment should estimate trade direction and compare it with order
book imbalance. If the catalog does not expose aggressor side, start with a tick
rule:

```text
price up from previous trade   => buy-initiated
price down from previous trade => sell-initiated
same price                     => carry forward previous sign
```

From that, build 1 second signed trade features:

```text
buy_trade_count
sell_trade_count
buy_volume
sell_volume
signed_trade_count = buy_trade_count - sell_trade_count
signed_volume = buy_volume - sell_volume
trade_imbalance = (buy_trade_count - sell_trade_count) / (buy_trade_count + sell_trade_count)
volume_imbalance = (buy_volume - sell_volume) / (buy_volume + sell_volume)
```

Then test four regimes:

| Book state | Trade flow state | Interpretation to test |
| --- | --- | --- |
| bid-heavy | buy-initiated flow | Demand pressure confirmed; possible continuation. |
| ask-heavy | sell-initiated flow | Supply pressure confirmed; possible continuation. |
| bid-heavy | sell-initiated flow | Bids absorbing sells; possible support or absorption. |
| ask-heavy | buy-initiated flow | Asks absorbing buys; possible resistance or absorption. |

This reframes the factor from a simple directional state variable into a
microstructure framework:

```text
order book imbalance + trade density + signed trade flow
=> pressure continuation vs passive liquidity absorption
```

## Signed Flow Absorption Results

Signed flow was estimated from trade ticks using a tick rule:

```text
price up from previous trade   => buy-initiated
price down from previous trade => sell-initiated
same price                     => carry forward previous sign
```

Rows with zero signed flow were excluded from the four-quadrant report. The
first pass used `trade_imbalance`:

| Regime | 10s directional return | 30s directional return | 60s directional return |
| --- | ---: | ---: | ---: |
| bid-heavy + buy flow | `0.00470%` | `0.00518%` | `0.00501%` |
| ask-heavy + sell flow | `0.00490%` | `0.00571%` | `0.00593%` |
| bid-heavy + sell flow | `0.00277%` | `0.00313%` | `0.00302%` |
| ask-heavy + buy flow | `0.00299%` | `0.00382%` | `0.00446%` |

Directional hit rates were above 53% in all four regimes. Confirmed pressure
regimes were stronger than absorption regimes, especially at 10s and 30s.

The same report using `volume_imbalance` showed the same ordering:

| Regime | 10s directional return | 30s directional return | 60s directional return |
| --- | ---: | ---: | ---: |
| bid-heavy + buy volume | `0.00459%` | `0.00509%` | `0.00495%` |
| ask-heavy + sell volume | `0.00468%` | `0.00547%` | `0.00577%` |
| bid-heavy + sell volume | `0.00308%` | `0.00347%` | `0.00329%` |
| ask-heavy + buy volume | `0.00323%` | `0.00406%` | `0.00460%` |

Interpretation: signed flow confirms that imbalance behaves more like a
short-horizon pressure continuation feature than a pure absorption/reversal
feature. Absorption states still have positive directional returns in the book
direction, but the edge is smaller than when book imbalance and active flow agree.

## 1 Minute Confirmed Pressure Persistence

The next test aggregated the 1 second signed-flow confirmation into 1 minute
canonical alpha rows. For each imbalance event, the latest known signed trade
feature was joined. Confirmed bid pressure contributed `+1`, confirmed ask
pressure contributed `-1`, and disagreement or zero flow contributed `0`.

```text
value = mean(confirmed_pressure_contribution) over the completed 1 minute bucket
```

The alpha timestamp is the end of the 1 minute bucket, because the full bucket is
only knowable after the minute completes.

The trade-count flow version produced `10,080` rows, one row for each minute in
the 7 day window. Decile 10 minus decile 1 mean forward-return spread:

| Horizon | Low bucket mean return | High bucket mean return | High - low spread |
| --- | ---: | ---: | ---: |
| 60s | `-0.00346%` | `0.00509%` | `0.00855%` |
| 180s | `-0.00448%` | `0.00092%` | `0.00540%` |
| 300s | `-0.00187%` | `0.00232%` | `0.00419%` |

The signed-volume flow version showed the same direction:

| Horizon | Low bucket mean return | High bucket mean return | High - low spread |
| --- | ---: | ---: | ---: |
| 60s | `-0.00302%` | `0.00474%` | `0.00775%` |
| 180s | `-0.00339%` | `0.00144%` | `0.00483%` |
| 300s | `-0.00264%` | `0.00395%` | `0.00659%` |

Interpretation: aggregating microstructure confirmation to 1 minute improves the
research shape. The top-minus-bottom spread remains positive at 1m, 3m, and 5m
horizons, with the clearest effect at 1m. The relationship is not perfectly
monotonic across all middle deciles, so this is still better treated as a
feature/regime input than a standalone trading rule.

## Three-Bar Kbar Streaks And Pressure

The next diagnostic asked whether three consecutive 1 minute kbars in the same
direction provide a better trading structure than raw 1 second imbalance events.
The kbars were built from the 1 second last trade price CSV:

```text
1m kbar return = close / open - 1
```

To avoid counting the same long streak many times, events were clustered: each
same-direction run contributed one event when it first reached three bars. On
the original 7 day window, `10,080` 1 minute kbars produced `1,235` clustered
three-bar events:

| Event | Count | 3-bar mean return | 3-bar median return |
| --- | ---: | ---: | ---: |
| up-up-up | `579` | `0.1080%` | `0.0837%` |
| down-down-down | `656` | `-0.1096%` | `-0.0870%` |

Three same-direction kbars therefore identify a realized short-horizon move of
roughly 8 to 11 basis points. However, simply following the third bar did not
show broad continuation edge. Up-up-up events leaned toward short-term pullback,
while down-down-down events showed only a small continuation bias.

Combining the three-bar structure with 1 minute pressure persistence produced a
more specific candidate. Define:

```text
aligned_pressure = kbar_direction * confirmed_pressure_persistence_1m
```

where `kbar_direction` is `+1` for up-up-up and `-1` for down-down-down.
Using `aligned_pressure > 0.2` as a confirmation threshold, the 7 day result was:

| Event | Pressure filter | Count | +5m directional return | +5m directional hit rate |
| --- | --- | ---: | ---: | ---: |
| up-up-up | trade-count pressure confirm | `256` | `-0.00975%` | `44.92%` |
| up-up-up | trade-count pressure neutral | `275` | `-0.02320%` | `42.55%` |
| down-down-down | trade-count pressure confirm | `257` | `0.00763%` | `50.58%` |
| down-down-down | trade-count pressure neutral | `353` | `-0.00026%` | `45.33%` |

This suggested an asymmetric structure: up-up-up remained poor for chasing even
with confirming pressure, while down-down-down plus confirming sell pressure had
a modest downside continuation bias.

To check sample stability, the same analysis was requested over a one month
window:

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

The catalog query only returned data from `2026-06-11T00:00:00Z` through
`2026-06-24T23:59:59Z`, so this is a 14 day stability check rather than a full
month. It produced `18,718` 1 minute kbars and `2,223` clustered three-bar
events:

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

The current candidate structure is therefore:

```text
down-down-down 1m kbar streak
+ confirmed orderbook sell pressure
=> possible downside continuation filter
```

This is not yet a standalone trading alpha. It is a more focused structure for
transaction-cost screening, de-overlapped event testing, and regime splits.

## Transaction Cost, De-Overlap, And Regime Screen

A first screen was added for the down-down-down plus confirmed sell pressure
structure:

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

The screen computes:

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

## Interpretation

The signal captures short-horizon order-flow pressure. It has stable directional
ranking and clear extreme-event behavior, but the edge is about 1 to 2 basis
points before transaction costs. It is unlikely to be enough as a standalone
trading alpha without a very strong execution model.

More appropriate uses:

- Input feature in a multi-factor model.
- Confirmation or veto for another alpha.
- Execution timing signal.
- Position sizing or aggressiveness adjustment.
- Regime-specific filter when combined with spread, volatility, volume, or book
  depth.

## Caveats

- Returns use trade prices, not executable quote or fill prices.
- Fees, spread, slippage, latency, queue position, and adverse selection are not
  modeled.
- Findings are for one instrument. Most diagnostics use one week; the three-bar
  pressure stability check requested one month but the catalog returned only
  `2026-06-11T00:00:00Z` through `2026-06-24T23:59:59Z`.
- The 8,000 row visualization price CSV is not valid for short-horizon return
  diagnostics.
- Extreme events are not de-duplicated into independent event clusters; adjacent
  snapshots may be highly correlated.
- The three-bar kbar analysis clusters same-direction runs, but longer forward
  horizons can still overlap across nearby events.

## Next Experiments

- `imbalance x spread`: check whether edge survives wider or tighter spread
  regimes.
- `imbalance x realized volatility`: test whether high-volatility windows amplify
  or degrade the signal.
- `imbalance x trade volume`: separate active flow regimes from quiet book states.
- `imbalance x trade density`: refine density buckets beyond median and top
  decile splits.
- Signed trade flow: estimate buy-initiated and sell-initiated trades using tick
  rule or catalog aggressor side if available.
- Four-quadrant event study: compare confirmed pressure and absorption regimes.
- Cluster dense trading periods into events so adjacent 1 second observations do
  not dominate sample counts.
- `imbalance x recent return`: distinguish continuation from short-term reversal.
- Event clustering: collapse consecutive extreme snapshots into one event and
  recompute the path.
- Transaction cost screen: estimate whether any threshold and horizon survives a
  realistic cost assumption.
- Dense signed flow: combine trade density with the signed flow quadrants to see
  whether pressure confirmation strengthens specifically during dense trading.
- Downside continuation screen: test down-down-down plus confirmed sell pressure
  against fees, spread, slippage, and a realistic execution delay.
- Regime split: check whether the down-down-down pressure structure works only
  during high volatility, high trade density, or broad market downtrend regimes.
