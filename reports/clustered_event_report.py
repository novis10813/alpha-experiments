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
class ClusterEvent:
    ts_event: int
    side: int
    threshold: float
    length: int
    max_abs_value: float


@dataclass(frozen=True)
class ClusterSummary:
    threshold: float
    side: str
    horizon_seconds: int
    count: int
    mean_cluster_length: float
    mean_abs_value: float
    mean_gross_return: float
    mean_net_return: float
    median_net_return: float
    hit_rate: float


@dataclass(frozen=True)
class ClusteredEventContext:
    alpha_source_path: Path
    quote_source_path: Path
    instrument_id: str
    alpha_name: str
    row_count: int
    raw_extreme_count: int
    cluster_count: int
    thresholds: list[float]
    horizons_seconds: list[int]
    cost_bps: float
    summaries: list[ClusterSummary]


def build_clustered_event_context(
    alpha_path: Path,
    quote_path: Path,
    thresholds: list[float] | None = None,
    horizons_seconds: list[int] | None = None,
    cost_bps: float = 2,
) -> ClusteredEventContext:
    active_thresholds = thresholds or [0.95, 0.98]
    horizons = horizons_seconds or [10, 30, 60]
    if not active_thresholds:
        raise ValueError("thresholds must not be empty")
    if not horizons:
        raise ValueError("horizons_seconds must not be empty")
    if cost_bps < 0:
        raise ValueError("cost_bps must be non-negative")

    alpha_points = _read_alpha_points(alpha_path)
    if not alpha_points:
        raise RuntimeError(f"No alpha rows found in {alpha_path}")
    quote_points = _read_quote_points(quote_path)
    if not quote_points:
        raise RuntimeError(f"No quote rows found in {quote_path}")

    clusters = [
        cluster
        for threshold in active_thresholds
        for cluster in _clusters_for_threshold(alpha_points, threshold)
    ]
    raw_extreme_count = sum(
        1
        for point in alpha_points
        for threshold in active_thresholds
        if abs(point.value) >= threshold
    )

    return ClusteredEventContext(
        alpha_source_path=alpha_path,
        quote_source_path=quote_path,
        instrument_id=_first_column_value(alpha_path, "instrument_id"),
        alpha_name=_first_column_value(alpha_path, "alpha_name"),
        row_count=len(alpha_points),
        raw_extreme_count=raw_extreme_count,
        cluster_count=len(clusters),
        thresholds=active_thresholds,
        horizons_seconds=horizons,
        cost_bps=cost_bps,
        summaries=_summaries(clusters, quote_points, horizons, cost_bps),
    )


def write_clustered_event_report_html(context: ClusteredEventContext, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_clustered_event_report_html(context), encoding="utf-8")


def render_clustered_event_report_html(context: ClusteredEventContext) -> str:
    title = "Clustered Extreme Imbalance Report"
    payload = {"clusterSummaries": [_summary_payload(summary) for summary in context.summaries]}
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
    <div class="subtitle">{html.escape(context.instrument_id)} · cost {context.cost_bps:g} bps</div>
    <section class="stats">
      {_stat("Alpha rows", f"{context.row_count:,}")}
      {_stat("Raw extreme rows", f"{context.raw_extreme_count:,}")}
      {_stat("Clustered events", f"{context.cluster_count:,}")}
      {_stat("Quote source", str(context.quote_source_path))}
    </section>
    <section class="chart">
      <div class="label">mean net executable return</div>
      <div id="cluster-net-return" class="plot"></div>
    </section>
    <section class="chart">
      <div class="label">summary table</div>
      <table>
        <thead>
          <tr>
            <th>threshold</th><th>side</th><th>horizon</th><th>count</th><th>cluster len</th><th>abs value</th><th>gross avg</th><th>net avg</th><th>net median</th><th>hit</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
    </section>
  </main>
  <script>
    const reportData = {payload_json};
    const rows = reportData.clusterSummaries;
    Plotly.newPlot("cluster-net-return", [{{
      name: "net executable return",
      type: "bar",
      x: rows.map(row => `${{row.threshold}} / ${{row.side}} / ${{row.horizonSeconds}}s`),
      y: rows.map(row => row.meanNetReturn),
      marker: {{ color: "#087f5b" }},
    }}], {{
      margin: {{ l: 58, r: 18, t: 18, b: 110 }},
      paper_bgcolor: "#ffffff",
      plot_bgcolor: "#ffffff",
      font: {{ family: "ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif", color: "#18212f" }},
      xaxis: {{ tickangle: -35, gridcolor: "#edf0f4", zerolinecolor: "#8a94a6" }},
      yaxis: {{ title: "mean net executable return", tickformat: ".3%", gridcolor: "#edf0f4", zerolinecolor: "#8a94a6" }},
    }}, {{ responsive: true, displaylogo: false }});
  </script>
</body>
</html>
"""


def _clusters_for_threshold(alpha_points: list[AlphaPoint], threshold: float) -> list[ClusterEvent]:
    clusters: list[ClusterEvent] = []
    current_side = 0
    current_start_ts = 0
    current_length = 0
    current_max_abs = 0.0

    for point in alpha_points:
        side = _extreme_side(point.value, threshold)
        if side == 0:
            if current_side != 0:
                clusters.append(ClusterEvent(current_start_ts, current_side, threshold, current_length, current_max_abs))
            current_side = 0
            current_length = 0
            current_max_abs = 0.0
            continue
        if side != current_side:
            if current_side != 0:
                clusters.append(ClusterEvent(current_start_ts, current_side, threshold, current_length, current_max_abs))
            current_side = side
            current_start_ts = point.ts_event
            current_length = 1
            current_max_abs = abs(point.value)
        else:
            current_length += 1
            current_max_abs = max(current_max_abs, abs(point.value))

    if current_side != 0:
        clusters.append(ClusterEvent(current_start_ts, current_side, threshold, current_length, current_max_abs))
    return clusters


def _summaries(
    clusters: list[ClusterEvent],
    quote_points: list[QuotePoint],
    horizons_seconds: list[int],
    cost_bps: float,
) -> list[ClusterSummary]:
    summaries: list[ClusterSummary] = []
    for threshold in sorted({cluster.threshold for cluster in clusters}):
        for side, side_name in [(1, "positive"), (-1, "negative")]:
            side_clusters = [
                cluster for cluster in clusters if cluster.threshold == threshold and cluster.side == side
            ]
            for horizon in horizons_seconds:
                summaries.append(
                    _summary_for(threshold, side_name, horizon, side_clusters, quote_points, cost_bps),
                )
    return summaries


def _summary_for(
    threshold: float,
    side_name: str,
    horizon_seconds: int,
    clusters: list[ClusterEvent],
    quote_points: list[QuotePoint],
    cost_bps: float,
) -> ClusterSummary:
    quote_times = [point.ts_event for point in quote_points]
    gross_returns: list[float] = []
    cluster_lengths: list[int] = []
    abs_values: list[float] = []
    side = 1 if side_name == "positive" else -1
    for cluster in clusters:
        entry_index = bisect.bisect_left(quote_times, cluster.ts_event)
        if entry_index >= len(quote_points):
            continue
        exit_time = quote_points[entry_index].ts_event + horizon_seconds * 1_000_000_000
        exit_index = bisect.bisect_left(quote_times, exit_time)
        if exit_index >= len(quote_points):
            continue
        gross_returns.append(_gross_return(side, quote_points[entry_index], quote_points[exit_index]))
        cluster_lengths.append(cluster.length)
        abs_values.append(cluster.max_abs_value)
    if not gross_returns:
        return ClusterSummary(threshold, side_name, horizon_seconds, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    net_returns = [value - cost_bps / 10_000 for value in gross_returns]
    return ClusterSummary(
        threshold=threshold,
        side=side_name,
        horizon_seconds=horizon_seconds,
        count=len(gross_returns),
        mean_cluster_length=sum(cluster_lengths) / len(cluster_lengths),
        mean_abs_value=sum(abs_values) / len(abs_values),
        mean_gross_return=sum(gross_returns) / len(gross_returns),
        mean_net_return=sum(net_returns) / len(net_returns),
        median_net_return=statistics.median(net_returns),
        hit_rate=sum(1 for value in net_returns if value > 0) / len(net_returns),
    )


def _gross_return(side: int, entry_quote: QuotePoint, exit_quote: QuotePoint) -> float:
    if side > 0:
        return (exit_quote.bid / entry_quote.ask) - 1
    return (entry_quote.bid / exit_quote.ask) - 1


def _extreme_side(value: float, threshold: float) -> int:
    if value >= threshold:
        return 1
    if value <= -threshold:
        return -1
    return 0


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


def _summary_payload(summary: ClusterSummary) -> dict[str, int | float | str]:
    return {
        "threshold": summary.threshold,
        "side": summary.side,
        "horizonSeconds": summary.horizon_seconds,
        "count": summary.count,
        "meanClusterLength": summary.mean_cluster_length,
        "meanAbsValue": summary.mean_abs_value,
        "meanGrossReturn": summary.mean_gross_return,
        "meanNetReturn": summary.mean_net_return,
        "medianNetReturn": summary.median_net_return,
        "hitRate": summary.hit_rate,
    }


def _table_row(summary: ClusterSummary) -> str:
    return f"""<tr>
<td>{summary.threshold:g}</td>
<td>{html.escape(summary.side)}</td>
<td>{summary.horizon_seconds}s</td>
<td>{summary.count:,}</td>
<td>{summary.mean_cluster_length:.2f}</td>
<td>{summary.mean_abs_value:.4f}</td>
<td>{summary.mean_gross_return:.5%}</td>
<td>{summary.mean_net_return:.5%}</td>
<td>{summary.median_net_return:.5%}</td>
<td>{summary.hit_rate:.2%}</td>
</tr>"""


def _stat(label: str, value: str) -> str:
    return f"""<div class="stat"><div class="label">{html.escape(label)}</div><div class="value">{html.escape(value)}</div></div>"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render clustered extreme imbalance diagnostics.")
    parser.add_argument("source", type=Path)
    parser.add_argument("--quote-source", type=Path, required=True)
    parser.add_argument("--thresholds", type=float, nargs="+", default=[0.95, 0.98])
    parser.add_argument("--horizons-seconds", type=int, nargs="+", default=[10, 30, 60])
    parser.add_argument("--cost-bps", type=float, default=2)
    parser.add_argument("--output", type=Path, default=Path("outputs/reports/clustered_event_report.html"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    context = build_clustered_event_context(
        args.source,
        args.quote_source,
        thresholds=args.thresholds,
        horizons_seconds=args.horizons_seconds,
        cost_bps=args.cost_bps,
    )
    write_clustered_event_report_html(context, args.output)
    print(f"wrote clustered event report to {args.output}")
    print(f"instrument_id={context.instrument_id}")
    print(f"alpha_rows={context.row_count}")
    print(f"raw_extreme_rows={context.raw_extreme_count}")
    print(f"clustered_events={context.cluster_count}")
    for summary in context.summaries:
        print(
            "summary "
            f"threshold={summary.threshold:g} "
            f"side={summary.side} "
            f"horizon={summary.horizon_seconds}s "
            f"count={summary.count} "
            f"cluster_len={summary.mean_cluster_length:.4f} "
            f"gross={summary.mean_gross_return:.8f} "
            f"net={summary.mean_net_return:.8f} "
            f"hit={summary.hit_rate:.6f}",
        )


if __name__ == "__main__":
    main()
