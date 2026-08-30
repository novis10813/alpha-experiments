from evolution.market_state import EvolutionMarketState
from evolution.rules import RuleInterpreterStrategy
from evolution.strategy_base import EvolutionStrategyConfig


class EvolvedStrategy(RuleInterpreterStrategy):
# EVOLVE-BLOCK-START
    RULE_SPEC = {
        "family_id": "trend-flow-confirmation-v1",
        "entry": {
            "conditions": [
                {"feature": "return_60m", "op": "gt", "value": 0.0},
                {"feature": "signed_flow_persistence_5m", "op": "gt", "value": 0.0},
                {"feature": "depth10_obi_mean", "op": "gt", "value": 0.0},
            ],
            "confirmations": 2,
        },
        "exit": {
            "conditions": [
                {"feature": "return_15m", "op": "lt", "value": 0.0},
                {"feature": "signed_flow_persistence_5m", "op": "lt", "value": 0.0},
            ],
            "confirmations": 2,
            "min_hold_bars": 15,
            "mode": "any",
        },
        "cooldown_bars": 5,
    }
# EVOLVE-BLOCK-END
