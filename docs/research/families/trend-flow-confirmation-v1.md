# Trend Flow Confirmation v1

## Preregistration

- **Family:** `trend-flow-confirmation-v1`
- **Hypothesis:** medium-horizon upward price state predicts continuation only when signed trade flow and order-book pressure agree.
- **Allowed instruments:** `BTCUSDT.BINANCE`, `ETHUSDT.BINANCE`
- **Signal unit:** completed `EvolutionMarketState` rows at `ts_event`.
- **Observable roles:** OHLC fields define completed-bar trend; `trade_imbalance` and `volume_imbalance` measure signed flow; `depth10_obi_mean` and `depth10_obi_last` measure order-book pressure; `spread_bps`, `volume`, and `trade_count` may filter execution or activity.
- **Position constraint:** long or flat only.
- **Sizing:** the trusted fixed `position_notional` only.
- **Seed controls:** two-bar entry confirmation, separate two-bar exit confirmation, five-bar minimum hold, three-bar cooldown, and complete reset of histories and counters.
- **Failure to avoid:** Milestone 1 raw trend chasing and raw imbalance signals were cost-fragile or negative without confirmation and turnover control.

The seed tests one transparent rule. OpenEvolve may make focused changes inside the evolve block, but it must preserve the trusted skeleton and use only the current state fields. This preregistration does not authorize validation, holdout access, or promotion.
