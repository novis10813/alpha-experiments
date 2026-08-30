from __future__ import annotations

from evolution.initial_program import EvolutionStrategyConfig
from nautilus_trader.trading.strategy import Strategy


class EvolvedStrategy(Strategy):
    def __init__(self, config: EvolutionStrategyConfig) -> None:
        super().__init__(config)

    def on_start(self) -> None:
        self.subscribe_data(self.config.state_data_type)

    def on_stop(self) -> None:
        self.unsubscribe_data(self.config.state_data_type)
