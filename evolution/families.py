from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from evolution.ledger import validate_family_id
from evolution.spec import INSTRUMENT_IDS


@dataclass(frozen=True)
class EvolutionFamily:
    family_id: str
    hypothesis: str
    allowed_instruments: tuple[str, ...]
    seed_program: Path
    preregistration: Path
    prompt_context: str


_FAMILY_ROOT = Path(__file__).parent / "families"

FAMILY_REGISTRY: dict[str, EvolutionFamily] = {
    "trend-flow-confirmation-v1": EvolutionFamily(
        family_id="trend-flow-confirmation-v1",
        hypothesis=(
            "medium-horizon upward price state predicts continuation only when signed trade "
            "flow and order-book pressure agree"
        ),
        allowed_instruments=("BTCUSDT.BINANCE", "ETHUSDT.BINANCE"),
        seed_program=_FAMILY_ROOT / "trend-flow-confirmation-v1" / "initial_program.py",
        preregistration=Path("docs/research/families/trend-flow-confirmation-v1.md"),
        prompt_context=(
            "Family: trend-flow-confirmation-v1\n"
            "Hypothesis: medium-horizon upward price state predicts continuation only when "
            "signed trade flow and order-book pressure agree.\n"
            "Validator feature allowlist: return_15m, return_60m, "
            "signed_flow_persistence_5m, trade_imbalance, volume_imbalance, "
            "depth10_obi_mean, depth10_obi_last, obi_change_5m, relative_spread_15m, "
            "relative_volume_15m, realized_volatility_15m.\n"
            "Validator entry roles: trend = return_15m or return_60m; flow = "
            "signed_flow_persistence_5m, trade_imbalance, or volume_imbalance; book = "
            "depth10_obi_mean, depth10_obi_last, or obi_change_5m.\n"
            "Constraint: long or flat only. Use the fixed position_notional supplied by the "
            "trusted config; do not change sizing.\n"
            "Rule grammar: RULE_SPEC is a flat mapping with family_id, entry and exit mappings, "
            "and cooldown_bars; conditions contain only feature/op/value, with entry/exit "
            "confirmations, exit min_hold_bars, and exit mode all/any. Each mutation changes "
            "one oralizable rule component only. No unrestricted LLM feedback.\n"
            "Known Milestone 1 failure to avoid: raw trend chasing and raw order-book imbalance "
            "produced cost-fragile or negative results without confirmation and turnover control."
        ),
    ),
    "down-streak-risk-off-btc-v1": EvolutionFamily(
        family_id="down-streak-risk-off-btc-v1",
        hypothesis=(
            "persistent downside price and signed-flow pressure identifies periods when a "
            "long strategy should remain flat or exit"
        ),
        allowed_instruments=("BTCUSDT.BINANCE",),
        seed_program=_FAMILY_ROOT / "down-streak-risk-off-btc-v1" / "initial_program.py",
        preregistration=Path("docs/research/families/down-streak-risk-off-btc-v1.md"),
        prompt_context=(
            "Family: down-streak-risk-off-btc-v1\n"
            "Hypothesis: persistent downside price and signed-flow pressure identifies periods "
            "when a long strategy should remain flat or exit.\n"
            "Validator feature allowlist: return_5m, return_15m, signed_flow_persistence_5m, "
            "trade_imbalance, volume_imbalance, depth10_obi_mean, depth10_obi_last, "
            "relative_trade_density_15m, relative_spread_15m.\n"
            "Validator exit role: downside = return_5m, return_15m, "
            "signed_flow_persistence_5m, trade_imbalance, or volume_imbalance.\n"
            "Constraint: long or flat only. Use the fixed position_notional supplied by the "
            "trusted config; do not change sizing.\n"
            "Rule grammar: RULE_SPEC is a flat mapping with family_id, entry and exit mappings, "
            "and cooldown_bars; conditions contain only feature/op/value, with entry/exit "
            "confirmations, exit min_hold_bars, and exit mode all/any. Each mutation changes "
            "one oralizable rule component only. No unrestricted LLM feedback.\n"
            "Known Milestone 1 failure to avoid: the BTC down-streak effect was small after "
            "costs and did not generalize to ETH or BNB, so do not make a universal or fee-heavy "
            "continuation rule."
        ),
    ),
    "pullback-exhaustion-v1": EvolutionFamily(
        family_id="pullback-exhaustion-v1",
        hypothesis=(
            "inside a positive broad trend, waiting for a short pullback and weakening sell "
            "pressure improves long entry and exit timing"
        ),
        allowed_instruments=("BTCUSDT.BINANCE", "ETHUSDT.BINANCE"),
        seed_program=_FAMILY_ROOT / "pullback-exhaustion-v1" / "initial_program.py",
        preregistration=Path("docs/research/families/pullback-exhaustion-v1.md"),
        prompt_context=(
            "Family: pullback-exhaustion-v1\n"
            "Hypothesis: inside a positive broad trend, waiting for a short pullback and "
            "weakening sell pressure improves long entry and exit timing.\n"
            "Validator feature allowlist: return_15m, return_60m, return_5m, close_location, "
            "signed_flow_persistence_5m, depth10_obi_mean, depth10_obi_last, obi_change_5m, "
            "relative_spread_15m, realized_volatility_15m, relative_volume_15m.\n"
            "Validator entry roles: broad-trend = return_15m or return_60m; pullback/recovery = "
            "return_5m, close_location, or signed_flow_persistence_5m.\n"
            "Constraint: long or flat only. Use the fixed position_notional supplied by the "
            "trusted config; do not change sizing.\n"
            "Rule grammar: RULE_SPEC is a flat mapping with family_id, entry and exit mappings, "
            "and cooldown_bars; conditions contain only feature/op/value, with entry/exit "
            "confirmations, exit min_hold_bars, and exit mode all/any. Each mutation changes "
            "one oralizable rule component only. No unrestricted LLM feedback.\n"
            "Known Milestone 1 failure to avoid: chasing five-green moves and unfiltered trend "
            "or imbalance signals led to weak continuation and fee-heavy switching."
        ),
    ),
}

if len(FAMILY_REGISTRY) != 3:
    raise RuntimeError("lineage registry must contain exactly three families")


def get_family(family_id: str) -> EvolutionFamily:
    validate_family_id(family_id)
    try:
        return FAMILY_REGISTRY[family_id]
    except KeyError as exc:
        raise ValueError(f"unsupported evolution family: {family_id}") from exc


def validate_family_instrument(family_id: str, instrument_id: str) -> EvolutionFamily:
    family = get_family(family_id)
    if instrument_id not in INSTRUMENT_IDS:
        raise ValueError(f"unsupported instrument: {instrument_id}")
    if instrument_id not in family.allowed_instruments:
        raise ValueError(f"instrument {instrument_id} is not allowed for family {family_id}")
    return family


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def composed_prompt_sha256(system_prompt: str, diff_prompt: str) -> str:
    composed = system_prompt + "\n\n" + diff_prompt
    return hashlib.sha256(composed.encode("utf-8")).hexdigest()
