# Discovery Cost and Delay Sensitivity

## Status

Milestone 1.3 complete. Discovery data only.

No validation or holdout dataset was read. The three smoke-run champions fail discovery
qualification under the registered execution profile.

## Method

Each executable discovery champion ran on one-second quotes under twelve scenarios:

- fees: 0, 5, 10, and 15 bps
- execution delays: 0, 1, and 5 seconds

The official profile remains 10 bps and one second. Alternative scenarios diagnose cost
and delay fragility and do not affect candidate generation or ranking.

Each scenario uses the same five discovery folds, minute states, position sizing, and
strategy code. The 10 bps/one-second scenario must match the executable rerank exactly;
all three instruments passed this consistency check.

## Net Sharpe matrix

| Instrument | Delay | 0 bps | 5 bps | 10 bps | 15 bps |
|---|---:|---:|---:|---:|---:|
| BTCUSDT | 0 sec | 3.467 | -1.428 | -6.870 | -12.540 |
| BTCUSDT | 1 sec | 3.497 | -1.407 | -6.865 | -12.554 |
| BTCUSDT | 5 sec | 3.466 | -1.443 | -6.899 | -12.579 |
| ETHUSDT | 0 sec | 0.858 | -2.827 | -6.360 | -9.659 |
| ETHUSDT | 1 sec | 0.987 | -2.823 | -6.446 | -9.796 |
| ETHUSDT | 5 sec | 0.961 | -2.824 | -6.426 | -9.759 |
| BNBUSDT | 0 sec | -1.252 | -5.124 | -8.352 | -11.006 |
| BNBUSDT | 1 sec | -0.554 | -5.072 | -8.842 | -11.917 |
| BNBUSDT | 5 sec | -0.524 | -5.057 | -8.834 | -11.913 |

## Mean fold net-return matrix

| Instrument | Delay | 0 bps | 5 bps | 10 bps | 15 bps |
|---|---:|---:|---:|---:|---:|
| BTCUSDT | 0 sec | 0.1654% | -0.0639% | -0.2932% | -0.5226% |
| BTCUSDT | 1 sec | 0.1671% | -0.0630% | -0.2931% | -0.5232% |
| BTCUSDT | 5 sec | 0.1655% | -0.0646% | -0.2947% | -0.5248% |
| ETHUSDT | 0 sec | 0.0509% | -0.1709% | -0.3928% | -0.6146% |
| ETHUSDT | 1 sec | 0.0597% | -0.1743% | -0.4083% | -0.6424% |
| ETHUSDT | 5 sec | 0.0586% | -0.1754% | -0.4095% | -0.6435% |
| BNBUSDT | 0 sec | -0.0392% | -0.1737% | -0.3083% | -0.4428% |
| BNBUSDT | 1 sec | -0.0218% | -0.2158% | -0.4098% | -0.6038% |
| BNBUSDT | 5 sec | -0.0206% | -0.2146% | -0.4086% | -0.6025% |

## Findings

### BTCUSDT

BTC has positive gross performance at zero fees, but turns negative by 5 bps. Delay from
zero to five seconds changes little. The candidate is `cost_fragile`: its edge is too
small for the registered 10 bps model. The additional `delay_sensitive` label records a
small deterioration from one to five seconds while the official result is already
negative.

### ETHUSDT

ETH also has positive gross performance at zero fees and turns negative by 5 bps. Delay
has little effect relative to fee drag. The candidate is `cost_fragile` and cannot cover
the registered trading cost.

### BNBUSDT

BNB remains negative even at zero fees under all delays. It is
`economically_rejected`; costs amplify a strategy that lacks positive gross edge.

## Accounting checks

Within each delay, gross behavior and turnover remain fixed while fee drag increases with
the configured instrument fee. Net return declines in line with turnover. Zero-fee runs
report zero fee drag.

The official sensitivity scenario reproduced each `rerank.json` executable aggregate
exactly. A mismatch would invalidate the sensitivity report.

## Decision

None of the current smoke champions may access validation:

- BTC: cost-fragile
- ETH: cost-fragile
- BNB: negative before fees

Future candidates must first have positive official executable Sharpe. Cost and delay
labels then act as promotion evidence under the registered protocol in
[`promotion-protocol.md`](promotion-protocol.md).
