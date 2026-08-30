# Discovery Harness Diagnostic

## Status

Milestone 1.1 baseline diagnostic, discovery data only.

No validation or holdout dataset was read. These results diagnose the backtest harness
and do not qualify a strategy for promotion.

## Method

The diagnostic runs four fixed strategies independently on each of the five discovery
folds:

- flat
- buy-and-hold
- SMA 3/8
- the current SMA 60/240 initial program

Each fold starts with 100,000 USDT and resets the engine, strategy state, and position.
The backtest closes open positions when the fold stops. Aggregate return, fee drag, and
turnover are means across folds because each fold uses a separate starting account.
Trade and order counts are totals. Aggregate Sharpe uses the concatenated daily return
series.

Gross return equals net return plus reported commissions. Daily gross equity removes
commissions from the existing mark-to-market daily equity calculation while preserving
fill prices and bid-side marking for an open long position.

Run the report with:

```bash
uv run python -m evolution diagnose \
  --instrument-id BTCUSDT.BINANCE \
  --run-id milestone-1-1-v1
```

The command reads only the five split names registered in `DISCOVERY_FOLDS`. It rejects
validation, holdout, and unknown split names.

## Baseline results

Returns, fee drag, and turnover below are mean values per discovery fold. Closed
positions are totals across five folds.

| Instrument | Baseline | Gross return | Fee drag | Net return | Gross Sharpe | Net Sharpe | Closed positions | Turnover |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| BTCUSDT | Buy-and-hold | 0.0129% | 0.0200% | -0.0071% | 0.23 | -0.12 | 5 | 0.20x |
| BTCUSDT | Initial program | -0.0997% | 0.4444% | -0.5441% | -2.49 | -11.52 | 113 | 4.44x |
| BTCUSDT | SMA 3/8 | -0.0648% | 11.8043% | -11.8691% | -1.64 | -39.94 | 2,972 | 118.04x |
| ETHUSDT | Buy-and-hold | 0.1564% | 0.0202% | 0.1362% | 1.88 | 1.63 | 5 | 0.20x |
| ETHUSDT | Initial program | 0.0509% | 0.4437% | -0.3928% | 0.86 | -6.36 | 117 | 4.44x |
| ETHUSDT | SMA 3/8 | -0.0712% | 11.4657% | -11.5369% | -1.21 | -39.26 | 2,967 | 114.66x |
| BNBUSDT | Buy-and-hold | -0.1531% | 0.0158% | -0.1690% | -3.64 | -4.04 | 5 | 0.16x |
| BNBUSDT | Initial program | -0.0381% | 0.2658% | -0.3039% | -1.40 | -9.79 | 97 | 2.66x |
| BNBUSDT | SMA 3/8 | -0.2191% | 7.2230% | -7.4421% | -7.69 | -37.05 | 2,950 | 72.23x |

The flat strategy produced no orders, exposure, fees, turnover, or return for all three
instruments.

## Findings

The harness produces the expected accounting controls:

- flat stays at zero
- buy-and-hold opens and closes one position per fold
- gross return minus fee drag reconciles to net return
- forced fold-end exits appear in position counts and holding durations
- every fold uses an independent account and strategy instance

The initial program has two different failure modes. BTC and BNB lose money before fees,
then pay additional turnover costs. ETH has a small positive gross result, but 44 bps of
mean fee drag per fold turns it negative. The ETH result is diagnostic evidence of
turnover sensitivity, not alpha evidence.

SMA 3/8 trades close to once every several minutes while exposed and generates thousands
of round trips. Fees dominate its result on all three instruments. This baseline confirms
that the 10 bps fee model strongly penalizes noisy threshold switching.

Buy-and-hold confirms that discovery regimes differ by instrument. ETH rises over these
folds, BTC stays close to flat after fold resets, and BNB falls. A strategy comparison
must therefore retain per-fold and per-instrument results rather than infer one shared
market regime.

## Limits

This diagnostic still uses the current discovery execution model. It does not test the
one-second quote stream or execution delay used during promotion. It also covers fixed
baselines only; the smoke-run discovery candidates have not been loaded into this report.

The next step is Milestone 1.2: rerun these baselines on discovery data under coarse and
promotion-like execution assumptions, then measure the difference in fills, costs, and
net daily Sharpe.
