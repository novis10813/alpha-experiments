from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Iterable


REJECTED_SCORE = -1_000_000.0


@dataclass(frozen=True)
class DiagnosticMetrics:
    gross_return: float
    fee_drag: float
    net_return: float
    gross_sharpe: float
    net_sharpe: float
    turnover: float
    average_holding_seconds: float | None
    median_holding_seconds: float | None
    average_gross_pnl_per_position: float | None
    average_fee_per_position: float | None
    best_daily_net_return: float | None
    worst_daily_net_return: float | None
    daily_gross_returns: tuple[float, ...] = ()
    holding_durations_seconds: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        numeric = (
            self.gross_return,
            self.fee_drag,
            self.net_return,
            self.gross_sharpe,
            self.net_sharpe,
            self.turnover,
            *self.daily_gross_returns,
            *self.holding_durations_seconds,
        )
        optional = (
            self.average_holding_seconds,
            self.median_holding_seconds,
            self.average_gross_pnl_per_position,
            self.average_fee_per_position,
            self.best_daily_net_return,
            self.worst_daily_net_return,
        )
        if not all(math.isfinite(value) for value in numeric):
            raise ValueError("diagnostic metrics must be finite")
        if not all(value is None or math.isfinite(value) for value in optional):
            raise ValueError("optional diagnostic metrics must be finite")
        if self.fee_drag < 0 or self.turnover < 0:
            raise ValueError("fee drag and turnover cannot be negative")


@dataclass(frozen=True)
class FoldMetrics:
    net_return: float
    max_drawdown: float
    profit_factor: float
    closed_positions: int
    orders: int
    exposure_ratio: float
    daily_returns: tuple[float, ...] = ()
    rejected: bool = False
    error: str | None = None

    def __post_init__(self) -> None:
        numeric = (
            self.net_return,
            self.max_drawdown,
            self.profit_factor,
            self.exposure_ratio,
            *self.daily_returns,
        )
        if not all(math.isfinite(value) for value in numeric):
            raise ValueError("fold metrics must be finite")
        if self.max_drawdown < 0 or not 0 <= self.exposure_ratio <= 1:
            raise ValueError("invalid drawdown or exposure")
        if self.closed_positions < 0 or self.orders < 0:
            raise ValueError("counts cannot be negative")


@dataclass(frozen=True)
class AggregateMetrics:
    combined_score: float
    median_return: float
    worst_return: float
    median_drawdown: float
    median_profit_factor: float
    closed_positions: int
    orders: int
    exposure_ratio: float
    active_folds: int

    def to_open_evolve(self) -> dict[str, float]:
        return {
            "combined_score": self.combined_score,
            "sharpe_ratio": self.combined_score,
            "median_return": self.median_return,
            "worst_return": self.worst_return,
            "median_drawdown": self.median_drawdown,
            "median_profit_factor": self.median_profit_factor,
            "closed_trades": float(self.closed_positions),
            "orders": float(self.orders),
            "exposure_ratio": self.exposure_ratio,
            "active_folds": float(self.active_folds),
        }


def aggregate_folds(folds: Iterable[FoldMetrics]) -> AggregateMetrics:
    values = tuple(folds)
    if not values:
        raise ValueError("at least one fold is required")
    returns = [fold.net_return for fold in values]
    drawdowns = [fold.max_drawdown for fold in values]
    active = sum(fold.closed_positions > 0 for fold in values)
    closed = sum(fold.closed_positions for fold in values)
    score = annualized_sharpe(value for fold in values for value in fold.daily_returns)
    if closed < 20 or active < 4 or any(fold.rejected for fold in values):
        score = REJECTED_SCORE
    return AggregateMetrics(
        combined_score=score,
        median_return=statistics.median(returns),
        worst_return=min(returns),
        median_drawdown=statistics.median(drawdowns),
        median_profit_factor=statistics.median(fold.profit_factor for fold in values),
        closed_positions=closed,
        orders=sum(fold.orders for fold in values),
        exposure_ratio=statistics.median(fold.exposure_ratio for fold in values),
        active_folds=active,
    )


def screen_passes(metrics: FoldMetrics) -> bool:
    return (
        not metrics.rejected
        and metrics.closed_positions > 0
        and metrics.net_return > -0.10
        and all(math.isfinite(value) for value in (metrics.net_return, metrics.max_drawdown))
    )


def annualized_sharpe(daily_returns: Iterable[float]) -> float:
    values = tuple(daily_returns)
    if len(values) < 2 or not all(math.isfinite(value) for value in values):
        return 0.0
    volatility = statistics.stdev(values)
    if volatility == 0:
        return 0.0
    return math.sqrt(365.0) * statistics.mean(values) / volatility


def max_drawdown(equity: Iterable[float]) -> float:
    peak: float | None = None
    worst = 0.0
    for value in equity:
        if not math.isfinite(value) or value <= 0:
            raise ValueError("equity must be finite and positive")
        peak = value if peak is None else max(peak, value)
        worst = max(worst, (peak - value) / peak)
    return worst


def profit_factor(pnls: Iterable[float]) -> float:
    values = tuple(pnls)
    gains = sum(value for value in values if value > 0)
    losses = -sum(value for value in values if value < 0)
    if losses == 0:
        return gains if gains else 0.0
    return gains / losses
