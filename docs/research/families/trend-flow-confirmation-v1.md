# Trend Flow Confirmation v1

## Preregistration

- **Family:** `trend-flow-confirmation-v1`
- **Hypothesis:** medium-horizon upward price state predicts continuation only when signed trade flow and order-book pressure agree.
- **Allowed instruments:** `BTCUSDT.BINANCE`, `ETHUSDT.BINANCE`
- **Signal unit:** completed `EvolutionMarketState` rows at `ts_event`.
- **Observable roles:** OHLC fields define completed-bar trend; `trade_imbalance` and `volume_imbalance` measure signed flow; `depth10_obi_mean` and `depth10_obi_last` measure order-book pressure; `spread_bps`, `volume`, and `trade_count` may filter execution or activity.
- **Position constraint:** long or flat only.
- **Sizing:** the trusted fixed `position_notional` only.
- **Oral rule:** enter when `return_60m > 0`, `signed_flow_persistence_5m > 0`, and `depth10_obi_mean > 0`; exit when either `return_15m < 0` or `signed_flow_persistence_5m < 0`.
- **Field roles:** `return_60m` is trend, `signed_flow_persistence_5m` is signed-flow confirmation, and `depth10_obi_mean` is book confirmation; the exit fields are downside risk controls.
- **Seed controls:** two-bar entry confirmation, two-bar exit confirmation, any-mode exit, 15-bar minimum hold, five-bar cooldown, and complete reset of counters.
- **Failure to avoid:** Milestone 1 raw trend chasing and raw imbalance signals were cost-fragile or negative without confirmation and turnover control.

The seed tests one transparent rule. OpenEvolve may make focused changes inside the evolve block, but it must preserve the trusted skeleton and use only the current state fields. This preregistration does not authorize validation, holdout access, or promotion.
