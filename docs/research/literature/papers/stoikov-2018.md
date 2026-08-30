# The micro-price: a high-frequency estimator of future prices

- **Author:** Sasha Stoikov
- **Year:** 2018
- **Canonical source ID:** `doi:10.1080/14697688.2018.1489139`
- **Source:** [Taylor & Francis](https://doi.org/10.1080/14697688.2018.1489139)
- **Evidence tier:** `primary_abstract`
- **Status:** `verified`

## Source-stated finding

The source abstract states that the micro-price estimated from high-frequency data
is empirically a better predictor of short-term prices than the mid-price or the
weighted mid-price.

## Evidence market, asset, and horizon

- **Market/venue:** The verified abstract and metadata used here do not establish
  the full asset or venue scope.
- **Assets:** Not recorded here beyond the source's high-frequency market-data
  setting.
- **Horizon:** Short-term prices; the abstract does not establish a numeric horizon.

## Caveats

The abstract does not establish a crypto result, a particular exchange, a numeric
cutoff, a forecast horizon for this repository, or profitability after costs. Do
not use the incorrect DOI `10.1080/14697688.2018.1432883`; it is not this paper.

## Repository mapping

`best_bid`, `best_ask`, `spread_bps`, `depth10_obi_last`, `depth10_obi_mean`, and
`close` provide related observable context. The repository does not currently
store a dedicated micro-price field. A derived micro-price would need a documented
formula and event-time construction before use.

## Extracted testable hypotheses

A repository feature candidate can test whether a depth-weighted price estimate
contains more short-horizon information than the mid-price baseline. The registry
marks `depth10_obi_last` as the primary proxy and spread/depth context as filters.
The proposed horizons are diagnostic design choices, not source-reported values.

## Unsupported extrapolations

- Treating `depth10_obi_last` as the paper's micro-price.
- Claiming that the feature works on this repository's crypto instruments.
- Choosing a weighting formula, threshold, horizon, or trading rule from the
  abstract.

## Status

Verified paper metadata and abstract finding. The repository mapping remains a
feature candidate for definition and diagnostic testing.
