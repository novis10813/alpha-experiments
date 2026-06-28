from __future__ import annotations

import argparse
import bisect
import csv
import html
import json
import statistics
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AlphaPoint:
    ts_event: int
    value: float


@dataclass(frozen=True)
class QuotePoint:
    ts_event: int
    bid: float
    ask: float
    mid: float
    spread_bps: float


@dataclass(frozen=True)
class JoinedPoint:
    horizon_seconds: int
    spread_bps: float
    gross_return: float
    net_return: float


@dataclass(frozen=True)
class SpreadSummary:
    regime: str
    horizon_seconds: int
    count: int
    spread_min_bps: float
    spread_max_bps: float
    spread_median_bps: float
    mean_gross_return: float
    mean_net_return: float
    median_net_return: float
    hit_rate: float


@dataclass(frozen=True)
class SpreadRegimeContext:
    alpha_source_path: Path
    quote_source_path: Path
    instrument_id: str
    alpha_name: str
    horizons_seconds: list[int]
    row_count: int
    joined_count: int
    delay_seconds: int
    cost_bps: float
    spread_median_bps: float
    spread_p75_bps: float
    spread_p90_bps: float
    summaries: list[SpreadSummary]


def build_spread_regime_context(
    alpha_path: Path,
    quote_path: Path,
    horizons_seconds: list[int] | None = None,
    delay_seconds: int = 0,
    cost_bps: float = 2,
) -> SpreadRegimeContext:
    horizons = horizons_seconds or [10, 30, 60]
    if not horizons:
        raise ValueError("horizons_seconds must not be empty")
    if delay_seconds < 0:
        raise ValueError("delay_seconds must be non-negative")
    if cost_bps < 0:
        raise ValueError("cost_bps must be non-negative")

    alpha_points = _read_alpha_points(alpha_path)
    if not alpha_points:
        raise RuntimeError(f"No alpha rows found in {alpha_path}")
    quote_points = _read_quote_points(quote_path)
    if not quote_points:
        raise RuntimeError(f"No quote rows found in {quote_path}")

    joined_points = _joined_points(alpha_points, quote_points, horizons, delay_seconds, cost_bps)
    first_horizon_points = [point for point in joined_points if point.horizon_seconds == horizons[0]]
    spreads = sorted(point.spread_bps for point in first_horizon_points)
    if not spreads:
        raise RuntimeError("No joined quote rows available for spread regime diagnostics")
    spread_median = statistics.median(spreads)
    spread_p75 = _percentile(spreads, 0.75)
    spread_p90 = _percentile(spreads, 0.90)

    return SpreadRegimeContext(
        alpha_source_path=alpha_path,
        quote_source_path=quote_path,
        instrument_id=_first_column_value(alpha_path, "instrument_id"),
        alpha_name=_first_column_value(alpha_path, "alpha_name"),
        horizons_seconds=horizons,
        row_count=len(alpha_points),
        joined_count=len(first_horizon_points),
        delay_seconds=delay_seconds,
        cost_bps=cost_bps,
        spread_median_bps=spread_median,
        spread_p75_bps=spread_p75,
        spread_p90_bps=spread_p90,
        summaries=_regime_summaries(joined_points, spread_median, spread_p75, spread_p90),
    )


def write_spread_regime_report_html(context: SpreadRegimeContext, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_spread_regime_report_html(context), encoding="utf-8")


def render_spread_regime_report_html(context: SpreadRegimeContext) -> str:
    title = "Spread Regime Report"
    payload = {
        "spreadSummaries": [_summary_payload(summary) for summary in context.summaries],
        "horizonsSeconds": context.horizons_seconds,
    }
    payload_json = json.dumps(payload, separators=(",", ":"))
    rows_html = "\n".join(_table_row(summary) for summary in context.summaries)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    body {{ margin: 0; font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #18212f; background: #ffffff; }}
    main {{ width: min(1180px, calc(100vw - 40px)); margin: 24px auto 40px; }}
    h1 {{ margin: 0 0 4px; font-size: 28px; line-height: 1.2; letter-spacing: 0; }}
    .subtitle {{ color: #667085; font-size: 14px; margin-bottom: 20px; }}
    .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 10px; margin-bottom: 18px; }}
    .stat, .chart {{ background: #f7f8fa; border: 1px solid #d7dce3; border-radius: 8px; padding: 10px 12px; }}
    .chart {{ margin-top: 12px; }}
    .label {{ color: #667085; font-size: 12px; margin-bottom: 4px; }}
    .value {{ font-size: 16px; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }}
    .plot {{ width: 100%; height: 380px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 12px; font-variant-numeric: tabular-nums; }}
    th, td {{ border-bottom: 1px solid #d7dce3; padding: 6px 7px; text-align: right; white-space: nowrap; }}
    th:first-child, td:first-child {{ text-align: left; }}
    th {{ color: #667085; font-weight: 600; }}
  </style>
</head>
<body>
  <main>
    <h1>{html.escape(title)}</h1>
    <div class="subtitle">{html.escape(context.instrument_id)} · delay {context.delay_seconds}s · cost {context.cost_bps:g} bps</div>
    <section class="stats">
      {_stat("Alpha rows", f"{context.row_count:,}")}
      {_stat("Joined rows", f"{context.joined_count:,}")}
      {_stat("Median spread", f"{context.spread_median_bps:.3f} bps")}
      {_stat("p75 spread", f"{context.spread_p75_bps:.3f} bps")}
      {_stat("p90 spread", f"{context.spread_p90_bps:.3f} bps")}
    </section>
    <section class="chart">
      <div class="label">mean net executable return</div>
      <div id="spread-net-return" class="plot"></div>
    </section>
    <section class="chart">
      <div class="label">summary table</div>
      <table>
        <thead>
          <tr>
            <th>regime</th><th>horizon</th><th>count</th><th>spread min</th><th>spread max</th><th>spread median</th><th>gross avg</th><th>net avg</th><th>net median</th><th>hit</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
    </section>
  </main>
  <script>
    const reportData = {payload_json};
    const rows = reportData.spreadSummaries;
    Plotly.newPlot("spread-net-return", reportData.horizonsSeconds.map(horizon => {{
      const horizonRows = rows.filter(row => row.horizonSeconds === horizon);
      return {{
        name: `${{horizon}}s`,
        type: "bar",
        x: horizonRows.map(row => row.regime),
        y: horizonRows.map(row => row.meanNetReturn),
      }};
    }}), {{
      barmode: "group",
      margin: {{ l: 58, r: 18, t: 18, b: 90 }},
      paper_bgcolor: "#ffffff",
      plot_bgcolor: "#ffffff",
      font: {{ family: "ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif", color: "#18212f" }},
      xaxis: {{ tickangle: -25, gridcolor: "#edf0f4", zerolinecolor: "#8a94a6" }},
      yaxis: {{ title: "mean net executable return", tickformat: ".3%", gridcolor: "#edf0f4", zerolinecolor: "#8a94a6" }},
    }}, {{ responsive: true, displaylogo: false }});
  </script>
</body>
</html>
"""


def _joined_points(
    alpha_points: list[AlphaPoint],
    quote_points: list[QuotePoint],
    horizons_seconds: list[int],
    delay_seconds: int,
    cost_bps: float,
) -> list[JoinedPoint]:
    quote_times = [point.ts_event for point in quote_points]
    result: list[JoinedPoint] = []
    for alpha in alpha_points:
        side = _sign(alpha.value)
        entry_time = alpha.ts_event + delay_seconds * 1_000_000_000
        entry_index = bisect.bisect_left(quote_times, entry_time)
        if entry_index >= len(quote_points):
            continue
        entry_quote = quote_points[entry_index]
        for horizon in horizons_seconds:
            exit_time = entry_quote.ts_event + horizon * 1_000_000_000
            exit_index = bisect.bisect_left(quote_times, exit_time)
            if exit_index >= len(quote_points):
                continue
            gross_return = _gross_return(side, entry_quote, quote_points[exit_index])
            result.append(
                JoinedPoint(
                    horizon_seconds=horizon,
                    spread_bps=entry_quote.spread_bps,
                    gross_return=gross_return,
                    net_return=gross_return - cost_bps / 10_000,
                ),
            )
    return result


def _regime_summaries(
    points: list[JoinedPoint],
    median_bps: float,
    p75_bps: float,
    p90_bps: float,
) -> list[SpreadSummary]:
    summaries: list[SpreadSummary] = []
    horizons = sorted({point.horizon_seconds for point in points})
    regimes = [
        ("spread_low", lambda point: point.spread_bps < median_bps),
        ("spread_high", lambda point: point.spread_bps >= median_bps),
        ("spread_top_quartile", lambda point: point.spread_bps >= p75_bps),
        ("spread_top_decile", lambda point: point.spread_bps >= p90_bps),
        ("spread_below_top_decile", lambda point: point.spread_bps < p90_bps),
    ]
    for horizon in horizons:
        horizon_points = [point for point in points if point.horizon_seconds == horizon]
        for regime, predicate in regimes:
            summaries.append(_summary_for(regime, horizon, [point for point in horizon_points if predicate(point)]))
    return summaries


def _summary_for(regime: str, horizon_seconds: int, points: list[JoinedPoint]) -> SpreadSummary:
    if not points:
        return SpreadSummary(regime, horizon_seconds, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    spreads = [point.spread_bps for point in points]
    gross_returns = [point.gross_return for point in points]
    net_returns = [point.net_return for point in points]
    return SpreadSummary(
        regime=regime,
        horizon_seconds=horizon_seconds,
        count=len(points),
        spread_min_bps=min(spreads),
        spread_max_bps=max(spreads),
        spread_median_bps=statistics.median(spreads),
        mean_gross_return=sum(gross_returns) / len(gross_returns),
        mean_net_return=sum(net_returns) / len(net_returns),
        median_net_return=statistics.median(net_returns),
        hit_rate=sum(1 for value in net_returns if value > 0) / len(net_returns),
    )


def _gross_return(side: int, entry_quote: QuotePoint, exit_quote: QuotePoint) -> float:
    if side > 0:
        return (exit_quote.bid / entry_quote.ask) - 1
    if side < 0:
        return (entry_quote.bid / exit_quote.ask) - 1
    return 0.0


def _read_alpha_points(source_path: Path) -> list[AlphaPoint]:
    points: list[AlphaPoint] = []
    with source_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            points.append(AlphaPoint(ts_event=int(row["ts_event"]), value=float(row["value"])))
    return sorted(points, key=lambda point: point.ts_event)


def _read_quote_points(source_path: Path) -> list[QuotePoint]:
    points: list[QuotePoint] = []
    with source_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            points.append(
                QuotePoint(
                    ts_event=int(row["ts_event"]),
                    bid=float(row["bid"]),
                    ask=float(row["ask"]),
                    mid=float(row["mid"]),
                    spread_bps=float(row["spread_bps"]),
                ),
            )
    return sorted(points, key=lambda point: point.ts_event)


def _first_column_value(source_path: Path, column: str) -> str:
    with source_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        first = next(reader, None)
        if first is None:
            return ""
        return first[column]


def _sign(value: float) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _percentile(sorted_values: list[float], percentile: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    index = percentile * (len(sorted_values) - 1)
    lower = int(index)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = index - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def _summary_payload(summary: SpreadSummary) -> dict[str, int | float | str]:
    return {
        "regime": summary.regime,
        "horizonSeconds": summary.horizon_seconds,
        "count": summary.count,
        "spreadMinBps": summary.spread_min_bps,
        "spreadMaxBps": summary.spread_max_bps,
        "spreadMedianBps": summary.spread_median_bps,
        "meanGrossReturn": summary.mean_gross_return,
        "meanNetReturn": summary.mean_net_return,
        "medianNetReturn": summary.median_net_return,
        "hitRate": summary.hit_rate,
    }


def _table_row(summary: SpreadSummary) -> str:
    return f"""<tr>
<td>{html.escape(summary.regime)}</td>
<td>{summary.horizon_seconds}s</td>
<td>{summary.count:,}</td>
<td>{summary.spread_min_bps:.3f}</td>
<td>{summary.spread_max_bps:.3f}</td>
<td>{summary.spread_median_bps:.3f}</td>
<td>{summary.mean_gross_return:.5%}</td>
<td>{summary.mean_net_return:.5%}</td>
<td>{summary.median_net_return:.5%}</td>
<td>{summary.hit_rate:.2%}</td>
</tr>"""


def _stat(label: str, value: str) -> str:
    return f"""<div class="stat"><div class="label">{html.escape(label)}</div><div class="value">{html.escape(value)}</div></div>"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render executable return diagnostics split by spread regime.")
    parser.add_argument("source", type=Path)
    parser.add_argument("--quote-source", type=Path, required=True)
    parser.add_argument("--horizons-seconds", type=int, nargs="+", default=[10, 30, 60])
    parser.add_argument("--delay-seconds", type=int, default=0)
    parser.add_argument("--cost-bps", type=float, default=2)
    parser.add_argument("--output", type=Path, default=Path("outputs/reports/spread_regime_report.html"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    context = build_spread_regime_context(
        args.source,
        args.quote_source,
        horizons_seconds=args.horizons_seconds,
        delay_seconds=args.delay_seconds,
        cost_bps=args.cost_bps,
    )
    write_spread_regime_report_html(context, args.output)
    print(f"wrote spread regime report to {args.output}")
    print(f"instrument_id={context.instrument_id}")
    print(f"alpha_rows={context.row_count}")
    print(f"spread_median_bps={context.spread_median_bps:.6f}")
    print(f"spread_p75_bps={context.spread_p75_bps:.6f}")
    print(f"spread_p90_bps={context.spread_p90_bps:.6f}")
    for summary in context.summaries:
        print(
            "summary "
            f"regime={summary.regime} "
            f"horizon={summary.horizon_seconds}s "
            f"count={summary.count} "
            f"gross={summary.mean_gross_return:.8f} "
            f"net={summary.mean_net_return:.8f} "
            f"hit={summary.hit_rate:.6f}",
        )


if __name__ == "__main__":
    main()
