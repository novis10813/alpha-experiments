from evolution.market_state import EvolutionMarketState
from evolution.rules import RuleInterpreterStrategy
from evolution.strategy_base import EvolutionStrategyConfig


class EvolvedStrategy(RuleInterpreterStrategy):
# EVOLVE-BLOCK-START
    RULE_SPEC = {
        "family_id": "down-streak-risk-off-btc-v1",
        "entry": {
            "conditions": [
                {"feature": "return_15m", "op": "gte", "value": 0.0},
                {"feature": "signed_flow_persistence_5m", "op": "gte", "value": 0.0},
            ],
            "confirmations": 3,
        },
        "exit": {
            "conditions": [
                {"feature": "return_5m", "op": "lt", "value": 0.0},
                {"feature": "signed_flow_persistence_5m", "op": "lt", "value": 0.0},
            ],
            "confirmations": 1,
            "min_hold_bars": 1,
            "mode": "any",
        },
        "cooldown_bars": 10,
    }
# EVOLVE-BLOCK-END
