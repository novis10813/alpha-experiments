# Down Streak Risk Off BTC v1

## Preregistration

- **Family:** `down-streak-risk-off-btc-v1`
- **Hypothesis:** persistent downside price and signed-flow pressure identifies periods when a long strategy should remain flat or exit.
- **Allowed instruments:** `BTCUSDT.BINANCE` only.
- **Signal unit:** completed `EvolutionMarketState` rows at `ts_event`.
- **Observable roles:** OHLC fields define downside streaks and broad trend; `trade_imbalance` and `volume_imbalance` measure signed sell pressure; `depth10_obi_mean` and `depth10_obi_last` provide book weakness; `volume`, `trade_count`, and `spread_bps` may provide activity or execution context.
- **Position constraint:** long or flat only.
- **Sizing:** the trusted fixed `position_notional` only.
- **Seed controls:** two-bar entry confirmation, separate two-bar risk-off exit confirmation, five-bar minimum hold, three-bar cooldown, and complete reset of histories and counters.
- **Failure to avoid:** Milestone 1 down-streak pressure was small after costs and did not generalize to ETH or BNB. The seed must not become a universal continuation rule or fee-heavy switcher.

The seed treats the family as a BTC risk filter. OpenEvolve may make focused changes inside the evolve block, but it must preserve the trusted skeleton and use only the current state fields. This preregistration does not authorize validation, holdout access, or promotion.
