# The Price Impact of Order Book Events

- **Authors:** Rama Cont, Arseniy Kukanov, Sasha Stoikov
- **Year:** 2014
- **Canonical source ID:** `doi:10.1093/jjfinec/nbt003`
- **Source:** [Oxford Academic](https://doi.org/10.1093/jjfinec/nbt003) and [arXiv:1011.6402](https://arxiv.org/abs/1011.6402)
- **Evidence tier:** `primary_abstract`
- **Status:** `verified`

## Source-stated finding

The paper studies limit orders, market orders, and cancellations using NYSE TAQ
data. It reports that, over short time intervals, price changes are mainly driven
by order-flow imbalance at the best bid and ask. It describes a linear relation
between order-flow imbalance and price changes, with a slope inversely related to
market depth. The paper reports robustness across the studied time scales and
stocks, and says that volume-based impact is noisier and less robust than
order-flow imbalance.

## Evidence market, asset, and horizon

- **Market/venue:** NYSE, using TAQ data.
- **Assets:** 50 US stocks.
- **Horizon:** Short time intervals and multiple time scales; the abstract does not
  establish a repository-specific minute horizon.
- **Observed inputs:** Best-quote supply and demand changes, including limit orders,
  market orders, and cancellations; market depth.

## Caveats

The evidence concerns US equities and the paper's order-flow-imbalance definition,
not this repository's depth-10 snapshot imbalance. The source does not establish
crypto applicability, a threshold, a one-minute rule, a holding period, or
profitability after fees and execution costs.

## Repository mapping

Possible starting fields are `depth10_obi_mean`, `depth10_obi_last`,
`depth10_obi_min`, `depth10_obi_max`, `best_bid`, `best_ask`, `spread_bps`,
`volume_imbalance`, and `trade_imbalance`. These fields do not reproduce the
source's event-level best-quote order flow without additional event data.

## Extracted testable hypotheses

1. In this repository's data, stronger contemporaneous order-book or signed-flow
   pressure may sort short-horizon returns directionally. Treat this as a feature
   candidate first.
2. A depth or liquidity context may alter the relation between pressure and price
   change. Treat depth and spread as context, not as a source-established rule.

The exact proposed fields and horizons live in `registry.json`; horizons are
research design choices, not values claimed by the paper.

## Unsupported extrapolations

- Applying the reported relation directly to BTCUSDT, ETHUSDT, or BNBUSDT.
- Treating `depth10_obi_*` as identical to event-level best-quote OFI.
- Choosing a numeric threshold, a one-minute bar rule, or a profitable trading
  strategy from the paper.
- Treating the square-root volume relation as established for this repository's
  crypto catalog.

## Status

Verified source metadata and abstract-level findings. Repository mappings remain
unverified feature/filter ideas pending instrument-specific diagnostics.
