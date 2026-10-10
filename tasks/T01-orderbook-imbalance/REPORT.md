# T01: Order Book Imbalance Feature

## Status

`feature_candidate`

Raw order book imbalance ranks short-horizon returns and is stronger when book
pressure, signed trade flow, and dense trading agree. The edge is about 1 to 2
bps before costs and does not survive a 2 bps round-trip bid/ask screen on BTC,
ETH, or BNB. Use it as a feature, confirmation or veto, execution-timing input,
or regime filter, not as a standalone alpha.

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

## Findings

All returns are percentages. "Spread" in ranking tables means decile 10 minus
decile 1 mean forward return.

### 1. Decile ranking

Ranking is present after correcting the price source to 1 second trade prices.

| Horizon | Bucket 10 - Bucket 1 mean return |
| --- | ---: |
| 10s | `0.0169%` |
| 30s | `0.0185%` |
| 60s | `0.0183%` |

### 2. Quote-executable screen

Positive imbalance enters long at the ask and exits at the future bid; negative
imbalance enters short at the bid and exits at the future ask. Quotes are 1
second best bid/ask from `OrderBookDepth10` (`604,800` rows). Gross edge is far
below a 2 bps round trip, and a 5 to 10 second delay erodes most of it.

| Horizon | Delay | Gross avg | Net @ 2 bps | Net @ 5 bps | Net @ 10 bps |
| --- | ---: | ---: | ---: | ---: | ---: |
| 10s | 0s | `0.00393%` | `-0.01607%` | `-0.04607%` | `-0.09607%` |
| 30s | 0s | `0.00468%` | `-0.01532%` | `-0.04532%` | `-0.09532%` |
| 60s | 0s | `0.00480%` | `-0.01520%` | `-0.04520%` | `-0.09520%` |
| 10s | 1s | `0.00292%` | `-0.01708%` | `-0.04708%` | `-0.09708%` |
| 30s | 1s | `0.00357%` | `-0.01643%` | `-0.04643%` | `-0.09643%` |
| 60s | 1s | `0.00370%` | `-0.01630%` | `-0.04630%` | `-0.09630%` |
| 10s | 5s | `0.00131%` | `-0.01869%` | `-0.04869%` | `-0.09869%` |
| 30s | 5s | `0.00164%` | `-0.01836%` | `-0.04836%` | `-0.09836%` |
| 60s | 5s | `0.00180%` | `-0.01820%` | `-0.04820%` | `-0.09820%` |
| 10s | 10s | `0.00061%` | `-0.01939%` | `-0.04939%` | `-0.09939%` |
| 30s | 10s | `0.00073%` | `-0.01927%` | `-0.04927%` | `-0.09927%` |
| 60s | 10s | `0.00095%` | `-0.01906%` | `-0.04906%` | `-0.09906%` |

### 3. Spread regime

Same execution definition, `delay=0s`, `cost=2bps`. Entry-time spreads were very
tight:

| Spread threshold | Value |
| --- | ---: |
| median | `0.001573 bps` |
| p75 | `0.001594 bps` |
| p90 | `0.001603 bps` |

Wider-spread snapshots carry slightly more gross edge, but no regime clears cost.
Spread is execution context, not sufficient confirmation.

| Regime | 10s gross | 10s net @ 2 bps | 30s gross | 30s net @ 2 bps | 60s gross | 60s net @ 2 bps |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| low spread | `0.00367%` | `-0.01633%` | `0.00470%` | `-0.01530%` | `0.00501%` | `-0.01499%` |
| high spread | `0.00419%` | `-0.01581%` | `0.00467%` | `-0.01533%` | `0.00460%` | `-0.01540%` |
| top quartile spread | `0.00450%` | `-0.01550%` | `0.00466%` | `-0.01534%` | `0.00453%` | `-0.01547%` |
| top decile spread | `0.00531%` | `-0.01469%` | `0.00530%` | `-0.01470%` | `0.00524%` | `-0.01476%` |
| below top decile | `0.00377%` | `-0.01623%` | `0.00461%` | `-0.01539%` | `0.00475%` | `-0.01525%` |

### 4. Extreme imbalance events

Snapshot-level events have higher hit rates but small mean returns (trade
prices):

| Threshold | Side | 30s mean directional return | 30s directional hit rate | 60s mean directional return | 60s directional hit rate |
| --- | --- | ---: | ---: | ---: | ---: |
| `0.95` | positive | `0.00933%` | `63.65%` | `0.00914%` | `58.85%` |
| `0.95` | negative | `0.00984%` | `64.73%` | `0.00975%` | `59.76%` |
| `0.98` | positive | `0.01074%` | `64.42%` | `0.01035%` | `58.91%` |
| `0.98` | negative | `0.01101%` | `65.69%` | `0.01086%` | `60.27%` |

Collapsing consecutive same-side extremes into one event at the first timestamp
reduced `135,676` snapshot-threshold observations to `66,774` clustered events.
Quote-executable returns at `cost=2bps` still do not clear cost:

| Threshold | Side | Events | Mean cluster length | 10s gross | 10s net @ 2 bps | 30s gross | 30s net @ 2 bps | 60s gross | 60s net @ 2 bps |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `0.95` | positive | `20,494` | `2.25` | `0.00939%` | `-0.01061%` | `0.00961%` | `-0.01039%` | `0.00947%` | `-0.01053%` |
| `0.95` | negative | `20,891` | `2.22` | `0.00973%` | `-0.01027%` | `0.01066%` | `-0.00935%` | `0.01096%` | `-0.00904%` |
| `0.98` | positive | `12,539` | `1.72` | `0.01084%` | `-0.00916%` | `0.01123%` | `-0.00878%` | `0.01072%` | `-0.00928%` |
| `0.98` | negative | `12,848` | `1.69` | `0.01082%` | `-0.00918%` | `0.01160%` | `-0.00840%` | `0.01192%` | `-0.00808%` |

### 5. Trade volume and density

Interaction signal `imbalance * (log1p(volume) / mean(log1p(volume)))` on 1
second buckets did not improve ranking:

| Horizon | Raw imbalance spread | Volume interaction spread |
| --- | ---: | ---: |
| 10s | `0.01685%` | `0.01318%` |
| 30s | `0.01853%` | `0.01392%` |
| 60s | `0.01834%` | `0.01350%` |

Volume works better as a regime split (log-volume intensity above or below
`1.0`):

| Horizon | High-volume spread | Low-volume spread |
| --- | ---: | ---: |
| 10s | `0.02061%` | `0.01531%` |
| 30s | `0.02080%` | `0.01746%` |
| 60s | `0.02132%` | `0.01710%` |

Trade density (trade ticks per 1 second bucket) is highly skewed:

| Metric | Trades per second |
| --- | ---: |
| min | `1` |
| median | `4` |
| mean | `44.17` |
| p90 | `148` |
| p99 | `440` |
| max | `9,188` |

Imbalance is more informative when trading is dense. Median split, then top
decile versus the rest:

| Horizon | Low-density spread | High-density spread |
| --- | ---: | ---: |
| 10s | `0.01256%` | `0.01862%` |
| 30s | `0.01491%` | `0.01989%` |
| 60s | `0.01522%` | `0.01955%` |

| Horizon | Top-decile density spread | Rest-of-sample spread |
| --- | ---: | ---: |
| 10s | `0.02331%` | `0.01569%` |
| 30s | `0.02360%` | `0.01769%` |
| 60s | `0.02477%` | `0.01745%` |

Density measures marketable order arrival, not participant type. It needs signed
flow to separate pressure continuation from passive absorption.

### 6. Signed flow quadrants

Trade direction comes from a tick rule: price up from the previous trade is
buy-initiated, price down is sell-initiated, and an unchanged price carries the
previous sign. Rows with zero signed flow are excluded. Directional hit rates
were above 53% in all quadrants. Confirmed pressure (book and flow agree) beats
absorption (book and flow disagree), so imbalance behaves as a pressure
continuation feature.

`trade_imbalance`:

| Regime | 10s directional return | 30s directional return | 60s directional return |
| --- | ---: | ---: | ---: |
| bid-heavy + buy flow | `0.00470%` | `0.00518%` | `0.00501%` |
| ask-heavy + sell flow | `0.00490%` | `0.00571%` | `0.00593%` |
| bid-heavy + sell flow | `0.00277%` | `0.00313%` | `0.00302%` |
| ask-heavy + buy flow | `0.00299%` | `0.00382%` | `0.00446%` |

`volume_imbalance`:

| Regime | 10s directional return | 30s directional return | 60s directional return |
| --- | ---: | ---: | ---: |
| bid-heavy + buy volume | `0.00459%` | `0.00509%` | `0.00495%` |
| ask-heavy + sell volume | `0.00468%` | `0.00547%` | `0.00577%` |
| bid-heavy + sell volume | `0.00308%` | `0.00347%` | `0.00329%` |
| ask-heavy + buy volume | `0.00323%` | `0.00406%` | `0.00460%` |

### 7. Dense signed flow

Quadrants split at the median joined trade count: `4` trades/sec for
`trade_imbalance`, `3` trades/sec for `volume_imbalance`. High-density confirmed
pressure is strongest, especially ask-heavy book with sell flow. These are trade
price returns, not quote-executable.

`trade_imbalance`:

| Density | Regime | 10s | 30s | 60s |
| --- | --- | ---: | ---: | ---: |
| low | bid-heavy + buy flow | `0.00332%` | `0.00419%` | `0.00455%` |
| low | ask-heavy + sell flow | `0.00340%` | `0.00438%` | `0.00446%` |
| low | bid-heavy + sell flow | `0.00268%` | `0.00318%` | `0.00327%` |
| low | ask-heavy + buy flow | `0.00284%` | `0.00380%` | `0.00457%` |
| high | bid-heavy + buy flow | `0.00554%` | `0.00577%` | `0.00529%` |
| high | ask-heavy + sell flow | `0.00581%` | `0.00653%` | `0.00683%` |
| high | bid-heavy + sell flow | `0.00298%` | `0.00301%` | `0.00244%` |
| high | ask-heavy + buy flow | `0.00331%` | `0.00388%` | `0.00424%` |

`volume_imbalance`:

| Density | Regime | 10s | 30s | 60s |
| --- | --- | ---: | ---: | ---: |
| low | bid-heavy + buy volume | `0.00318%` | `0.00405%` | `0.00439%` |
| low | ask-heavy + sell volume | `0.00323%` | `0.00414%` | `0.00433%` |
| low | bid-heavy + sell volume | `0.00269%` | `0.00333%` | `0.00345%` |
| low | ask-heavy + buy volume | `0.00283%` | `0.00370%` | `0.00436%` |
| high | bid-heavy + buy volume | `0.00529%` | `0.00560%` | `0.00523%` |
| high | ask-heavy + sell volume | `0.00540%` | `0.00613%` | `0.00648%` |
| high | bid-heavy + sell volume | `0.00348%` | `0.00361%` | `0.00311%` |
| high | ask-heavy + buy volume | `0.00371%` | `0.00449%` | `0.00487%` |

### 8. 1 minute confirmed pressure persistence

Each imbalance event joins the latest known signed trade feature: confirmed bid
pressure `+1`, confirmed ask pressure `-1`, disagreement or zero flow `0`.
`value = mean(contribution)` over the completed minute, timestamped at the
minute end. BTC produced `10,080` rows. The top-minus-bottom spread stays
positive at 1m, 3m, and 5m, clearest at 1m, but middle deciles are not
monotonic.

Trade-count flow:

| Horizon | Low bucket mean return | High bucket mean return | High - low spread |
| --- | ---: | ---: | ---: |
| 60s | `-0.00346%` | `0.00509%` | `0.00855%` |
| 180s | `-0.00448%` | `0.00092%` | `0.00540%` |
| 300s | `-0.00187%` | `0.00232%` | `0.00419%` |

Signed-volume flow:

| Horizon | Low bucket mean return | High bucket mean return | High - low spread |
| --- | ---: | ---: | ---: |
| 60s | `-0.00302%` | `0.00474%` | `0.00775%` |
| 180s | `-0.00339%` | `0.00144%` | `0.00483%` |
| 300s | `-0.00264%` | `0.00395%` | `0.00659%` |

### 9. Multi-instrument check

Same window, same quote-executable screen at 0 delay. The effect is weaker on
ETH and materially weaker on BNB. None clears 2 bps.

| Instrument | Horizon | Gross avg | Net @ 2 bps |
| --- | ---: | ---: | ---: |
| BTCUSDT | 10s | `0.00393%` | `-0.01607%` |
| BTCUSDT | 30s | `0.00468%` | `-0.01532%` |
| BTCUSDT | 60s | `0.00480%` | `-0.01520%` |
| ETHUSDT | 10s | `0.00361%` | `-0.01639%` |
| ETHUSDT | 30s | `0.00399%` | `-0.01601%` |
| ETHUSDT | 60s | `0.00380%` | `-0.01620%` |
| BNBUSDT | 10s | `0.00197%` | `-0.01803%` |
| BNBUSDT | 30s | `0.00216%` | `-0.01784%` |
| BNBUSDT | 60s | `0.00194%` | `-0.01806%` |

Pressure persistence spread by instrument. It generalizes to ETH but not BNB,
so the feature is instrument- and regime-dependent.

| Instrument | Flow | 60s | 180s | 300s |
| --- | --- | ---: | ---: | ---: |
| BTCUSDT | trade-count | `0.00855%` | `0.00540%` | `0.00419%` |
| BTCUSDT | volume | `0.00775%` | `0.00483%` | `0.00659%` |
| ETHUSDT | trade-count | `0.00126%` | `0.00623%` | `0.00778%` |
| ETHUSDT | volume | `0.00343%` | `0.00431%` | `0.00490%` |
| BNBUSDT | trade-count | `-0.00068%` | `-0.00230%` | `-0.00430%` |
| BNBUSDT | volume | `0.00089%` | `0.00132%` | `-0.00040%` |

## Uses

- Input feature in a multi-factor model.
- Confirmation or veto for another alpha.
- Execution timing, position sizing, or aggressiveness adjustment.
- Regime filter combined with spread, volatility, volume, or depth.

The rule-focused follow-up is [Down-Streak Pressure](../T02-down-streak-pressure/REPORT.md).

## Caveats

- Ranking, event-study, and interaction diagnostics use trade prices.
  Executable screens use bid/ask quotes but do not model queue position,
  partial fills, maker/taker fee schedules, or adverse selection.
- Most diagnostics cover one week of BTC. Only the executable and
  pressure-persistence checks were repeated for ETH and BNB.
- The 8,000 row visualization price CSV is not valid for short-horizon returns.
- Snapshot diagnostics contain adjacent, highly correlated observations.
  Clustering fixes this only for the extreme-event definition.

## Next work

No more broad raw imbalance reports. Targeted options:

- Realized-volatility and recent-return regime splits, if a model uses
  imbalance as one feature among several.
- Catalog aggressor-side data in place of the tick rule, if it becomes
  available.
- Imbalance inside a multi-factor model or execution policy as confirmation,
  veto, sizing, or aggressiveness.
