from __future__ import annotations

from common.time_series import sign


def quote_execution_return(side: int, entry_quote: object, exit_quote: object) -> float:
    if side > 0:
        return (float(getattr(exit_quote, "bid")) / float(getattr(entry_quote, "ask"))) - 1
    if side < 0:
        return (float(getattr(entry_quote, "bid")) / float(getattr(exit_quote, "ask"))) - 1
    return 0.0


def net_return(gross_return: float, cost_bps: float) -> float:
    return gross_return - cost_bps / 10_000


def side_from_alpha(value: float) -> int:
    return sign(value)

