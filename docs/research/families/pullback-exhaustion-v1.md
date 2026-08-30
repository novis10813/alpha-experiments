# Pullback Exhaustion v1

## Preregistration

- **Family:** `pullback-exhaustion-v1`
- **Hypothesis:** inside a positive broad trend, waiting for a short pullback and weakening sell pressure improves long entry and exit timing.
- **Allowed instruments:** `BTCUSDT.BINANCE`, `ETHUSDT.BINANCE`
- **Signal unit:** completed `EvolutionMarketState` rows at `ts_event`.
- **Observable roles:** OHLC fields define broad trend, short pullback, and recovery; `trade_imbalance` and `volume_imbalance` measure weakening sell pressure; `depth10_obi_mean` and `depth10_obi_last` confirm pressure; `volume`, `trade_count`, and `spread_bps` provide activity or execution context.
- **Position constraint:** long or flat only.
- **Sizing:** the trusted fixed `position_notional` only.
- **Oral rule:** enter when `return_60m > 0`, `return_5m < 0`, `close_location >= 0.5`, and `signed_flow_persistence_5m >= 0`; exit when either `return_15m < 0` or `signed_flow_persistence_5m < 0`.
- **Field roles:** `return_60m` is broad trend; `return_5m` is pullback; `close_location` and `signed_flow_persistence_5m` are recovery confirmation. The exit fields are downside timing controls.
- **Seed controls:** two-bar entry confirmation, two-bar exit confirmation, any-mode exit, ten-bar minimum hold, five-bar cooldown, and complete reset of counters.
- **Failure to avoid:** Milestone 1 five-green chasing and unfiltered trend or imbalance rules produced weak continuation and fee-heavy switching.

The seed waits for a short pullback and a recovery signal inside a broad positive state. OpenEvolve may make focused changes inside the evolve block, but it must preserve the trusted skeleton and use only the current state fields. This preregistration does not authorize validation, holdout access, or promotion.
