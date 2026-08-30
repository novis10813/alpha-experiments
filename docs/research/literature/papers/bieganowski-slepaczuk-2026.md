# Explainable Patterns in Cryptocurrency Microstructure

- **Authors:** Bartosz Bieganowski, Robert Ślepaczuk
- **Year:** 2026
- **Canonical source IDs:** `arxiv:2602.00776`, `doi:10.48550/arXiv.2602.00776`
- **Source:** [arXiv abstract](https://arxiv.org/abs/2602.00776) and [HTML](https://arxiv.org/html/2602.00776)
- **Evidence tier:** `primary_full_text`
- **Status:** `verified`

## Source-stated finding

The paper reports stable cross-asset patterns in cryptocurrency limit-order-book
microstructure. It studies engineered order-book and trade features with a unified
CatBoost pipeline and reports similar predictive importance and SHAP dependence
shapes across BTC, LTC, ETC, ENJ, and ROSE. The paper describes monotone, concave
order-flow-imbalance effects at extremes, wider spreads associated with reduced
predictive effects, and VWAP-to-mid deviations with short-horizon asymmetric
patterns. It also reports taker and fixed-depth maker backtests under its own
assumptions.

## Evidence market, asset, and horizon

- **Market/venue:** Binance Futures perpetual contracts.
- **Assets:** BTC, LTC, ETC, ENJ, and ROSE.
- **Data:** Order books and trades sampled at 1-second frequency, from 2022-01-01
  through 2025-10-12.
- **Prediction horizon:** Three-second mid-price log return in the described model.
- **Execution evidence:** The paper describes its own conservative top-of-book taker
  and fixed-depth maker backtests. Those results do not transfer to this repository.

## Caveats

The paper's feature engineering, model, sample, exchange, and execution assumptions
differ from this repository. Its results do not establish that the same features
work on BNBUSDT or on the repository's one-minute state rows. They do not establish
universal profitability, a repository threshold, or a particular cost/delay result.

## Repository mapping

Potential primary fields include `depth10_obi_last`, `depth10_obi_mean`,
`volume_imbalance`, `trade_imbalance`, `spread_bps`, `close_location`,
`realized_volatility_15m`, `relative_volume_15m`, and
`relative_trade_density_15m`. Context fields include `relative_spread_15m`,
`signed_flow_persistence_5m`, and `obi_change_5m`. The repository's state rows are
minute-end observations, so they do not reproduce the paper's 1-second feature
library.

## Extracted testable hypotheses

1. Across the repository's instruments, relative order-book and signed-flow
   features may show comparable short-horizon ordering. This is a feature idea,
   not a claim of transfer.
2. Wider relative spread may weaken the usefulness of pressure features and can be
   tested as a filter or context state.
3. A depth-weighted or imbalance-informed price feature may add information beyond
   a mid-price baseline, but the repository must define that feature first.

The registry stores these as feature/filter/rule ideas with positive diagnostic
horizons selected for repository diagnostics. It does not store the paper's
validation, holdout, backtest, PnL, threshold, or drawdown results.

## Unsupported extrapolations

- Treating the paper's 3-second result as a result for minute-end rows.
- Claiming applicability to BNBUSDT or to this local catalog without testing it.
- Copying the paper's model thresholds, costs, or execution behavior.
- Treating SHAP importance or the reported backtests as causal proof.

## Status

Verified full-text arXiv source. Repository hypotheses remain untested research
ideas, with no promotion implied.
