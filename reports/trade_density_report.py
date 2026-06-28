from __future__ import annotations

import argparse
import html
import json
import statistics
from dataclasses import dataclass
from pathlib import Path

from common.csv_io import AlphaPoint
from common.csv_io import TradeFeaturePoint as FeaturePoint
from common.csv_io import first_column_value
from common.csv_io import read_alpha_points
from common.csv_io import read_trade_feature_points
from common.time_series import NS_PER_SECOND
from common.time_series import index_at_or_after
from common.time_series import index_at_or_before
from reports.framework import write_html_report


@dataclass(frozen=True)
class JoinedPoint:
    ts_event: int
    alpha_value: float
    trade_count: int
    horizon_seconds: int
    forward_return: float


@dataclass(frozen=True)
class RegimeSummary:
    regime: str
    horizon_seconds: int
    count: int
    density_min: int
    density_max: int
    density_median: float
    bucket_count: int
    top_bottom_spread: float
    low_bucket_mean_return: float
    high_bucket_mean_return: float


@dataclass(frozen=True)
class DensityContext:
    alpha_source_path: Path
    feature_source_path: Path
    instrument_id: str
    alpha_name: str
    horizons_seconds: list[int]
    row_count: int
    joined_count: int
    density_threshold: float
    regime_summaries: list[RegimeSummary]


def build_density_context(
    alpha_path: Path,
    feature_path: Path,
    horizons_seconds: list[int] | None = None,
    bucket_count: int = 10,
) -> DensityContext:
    horizons = horizons_seconds or [10, 30, 60]
    if not horizons:
        raise ValueError("horizons_seconds must not be empty")
    if bucket_count <= 1:
        raise ValueError("bucket_count must be greater than one")

    alpha_points = read_alpha_points(alpha_path)
    if not alpha_points:
        raise RuntimeError(f"No alpha rows found in {alpha_path}")

    feature_points = read_trade_feature_points(feature_path)
    if not feature_points:
        raise RuntimeError(f"No feature rows found in {feature_path}")
    _raise_if_feature_data_too_sparse(feature_points, min(horizons))

    joined_points = _joined_points(alpha_points, feature_points, horizons)
    first_horizon_points = [point for point in joined_points if point.horizon_seconds == horizons[0]]
    density_threshold = statistics.median([point.trade_count for point in first_horizon_points])

    return DensityContext(
        alpha_source_path=alpha_path,
        feature_source_path=feature_path,
        instrument_id=first_column_value(alpha_path, "instrument_id"),
        alpha_name=first_column_value(alpha_path, "alpha_name"),
        horizons_seconds=horizons,
        row_count=len(alpha_points),
        joined_count=len(first_horizon_points),
        density_threshold=density_threshold,
        regime_summaries=_regime_summaries(joined_points, density_threshold, bucket_count),
    )


def write_density_report_html(context: DensityContext, output_path: Path) -> None:
    write_html_report(context, output_path, render_density_report_html)


def render_density_report_html(context: DensityContext) -> str:
    title = "Trade Density Regime Report"
    payload = {
        "regimeSummaries": [_summary_payload(summary) for summary in context.regime_summaries],
        "horizonsSeconds": context.horizons_seconds,
        "densityThreshold": context.density_threshold,
    }
    payload_json = json.dumps(payload, separators=(",", ":"))
    rows_html = "\n".join(_table_row(summary) for summary in context.regime_summaries)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    :root {{
      color-scheme: light;
      --ink: #18212f;
      --muted: #667085;
      --panel: #f7f8fa;
      --line: #d7dce3;
    }}
    body {{
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: #ffffff;
    }}
    main {{
      width: min(1180px, calc(100vw - 40px));
      margin: 24px auto 40px;
    }}
    h1 {{
      margin: 0 0 4px;
      font-size: 28px;
      line-height: 1.2;
      letter-spacing: 0;
    }}
    .subtitle {{
      color: var(--muted);
      font-size: 14px;
      margin-bottom: 20px;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 10px;
      margin-bottom: 18px;
    }}
    .stat {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px 12px;
    }}
    .label {{
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 4px;
    }}
    .value {{
      font-size: 16px;
      font-variant-numeric: tabular-nums;
      overflow-wrap: anywhere;
    }}
    .chart {{
      border: 1px solid var(--line);
      border-radius: 8px;
      margin-top: 12px;
      padding: 12px;
    }}
    .plot {{
      width: 100%;
      height: 380px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      font-variant-numeric: tabular-nums;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 7px 8px;
      text-align: right;
      white-space: nowrap;
    }}
    th:first-child, td:first-child {{
      text-align: left;
    }}
    th {{
      color: var(--muted);
      font-weight: 600;
    }}
  </style>
</head>
<body>
  <main>
    <h1>{html.escape(title)}</h1>
    <div class="subtitle">{html.escape(context.instrument_id)} · density split: trade_count median {context.density_threshold:g}</div>
    <section class="stats" aria-label="Trade density summary">
      {_stat("Alpha rows", f"{context.row_count:,}")}
      {_stat("Joined rows", f"{context.joined_count:,}")}
      {_stat("Density threshold", f"{context.density_threshold:g} trades/sec")}
      {_stat("Feature source", str(context.feature_source_path))}
    </section>
    <section class="chart">
      <div class="label">Top-bottom imbalance spread by trade density regime</div>
      <div id="spread" class="plot"></div>
    </section>
    <section class="chart">
      <div class="label">Regime summary</div>
      <table>
        <thead>
          <tr>
            <th>regime</th>
            <th>horizon</th>
            <th>count</th>
            <th>density min</th>
            <th>density max</th>
            <th>density median</th>
            <th>low bucket</th>
            <th>high bucket</th>
            <th>top-bottom spread</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
    </section>
  </main>
  <script>
    const reportData = {payload_json};
    const plotConfig = {{ responsive: true, displaylogo: false, scrollZoom: true }};
    const rows = reportData.regimeSummaries;
    Plotly.newPlot("spread", [
      {{
        name: "low density",
        type: "bar",
        x: rows.filter(row => row.regime === "low").map(row => row.horizonSeconds),
        y: rows.filter(row => row.regime === "low").map(row => row.topBottomSpread),
      }},
      {{
        name: "high density",
        type: "bar",
        x: rows.filter(row => row.regime === "high").map(row => row.horizonSeconds),
        y: rows.filter(row => row.regime === "high").map(row => row.topBottomSpread),
      }},
    ], {{
      barmode: "group",
      margin: {{ l: 58, r: 18, t: 18, b: 54 }},
      paper_bgcolor: "#ffffff",
      plot_bgcolor: "#ffffff",
      font: {{ family: "ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif", color: "#18212f" }},
      xaxis: {{ title: "horizon seconds", gridcolor: "#edf0f4", zerolinecolor: "#8a94a6" }},
      yaxis: {{ title: "top-bottom spread", tickformat: ".3%", gridcolor: "#edf0f4", zerolinecolor: "#8a94a6" }},
    }}, plotConfig);
  </script>
</body>
</html>
"""


def _joined_points(
    alpha_points: list[AlphaPoint],
    feature_points: list[FeaturePoint],
    horizons_seconds: list[int],
) -> list[JoinedPoint]:
    feature_times = [point.ts_event for point in feature_points]
    result: list[JoinedPoint] = []
    for alpha in alpha_points:
        current_index = index_at_or_before(feature_times, alpha.ts_event)
        if current_index < 0:
            continue
        current_feature = feature_points[current_index]
        if current_feature.price == 0:
            continue
        for horizon_seconds in horizons_seconds:
            future_index = index_at_or_after(
                feature_times,
                alpha.ts_event + horizon_seconds * NS_PER_SECOND,
            )
            if future_index >= len(feature_points):
                continue
            result.append(
                JoinedPoint(
                    ts_event=alpha.ts_event,
                    alpha_value=alpha.value,
                    trade_count=current_feature.trade_count,
                    horizon_seconds=horizon_seconds,
                    forward_return=(feature_points[future_index].price / current_feature.price) - 1,
                ),
            )
    return result


def _regime_summaries(
    points: list[JoinedPoint],
    density_threshold: float,
    bucket_count: int,
) -> list[RegimeSummary]:
    summaries: list[RegimeSummary] = []
    horizons = sorted({point.horizon_seconds for point in points})
    for horizon in horizons:
        horizon_points = [point for point in points if point.horizon_seconds == horizon]
        for regime in ["low", "high"]:
            if regime == "low":
                regime_points = [point for point in horizon_points if point.trade_count < density_threshold]
            else:
                regime_points = [point for point in horizon_points if point.trade_count >= density_threshold]
            summaries.append(_summary_for(regime, horizon, regime_points, bucket_count))
    return summaries


def _summary_for(
    regime: str,
    horizon_seconds: int,
    points: list[JoinedPoint],
    bucket_count: int,
) -> RegimeSummary:
    if not points:
        return RegimeSummary(
            regime=regime,
            horizon_seconds=horizon_seconds,
            count=0,
            density_min=0,
            density_max=0,
            density_median=0.0,
            bucket_count=0,
            top_bottom_spread=0.0,
            low_bucket_mean_return=0.0,
            high_bucket_mean_return=0.0,
        )

    buckets = _bucket_returns(points, bucket_count)
    low_bucket = buckets[0]
    high_bucket = buckets[-1]
    densities = [point.trade_count for point in points]
    return RegimeSummary(
        regime=regime,
        horizon_seconds=horizon_seconds,
        count=len(points),
        density_min=min(densities),
        density_max=max(densities),
        density_median=statistics.median(densities),
        bucket_count=len(buckets),
        top_bottom_spread=high_bucket - low_bucket,
        low_bucket_mean_return=low_bucket,
        high_bucket_mean_return=high_bucket,
    )


def _bucket_returns(points: list[JoinedPoint], bucket_count: int) -> list[float]:
    sorted_points = sorted(points, key=lambda point: point.alpha_value)
    actual_bucket_count = min(bucket_count, len(sorted_points))
    result: list[float] = []
    for bucket_index in range(actual_bucket_count):
        start = round(bucket_index * len(sorted_points) / actual_bucket_count)
        end = round((bucket_index + 1) * len(sorted_points) / actual_bucket_count)
        bucket_points = sorted_points[start:end]
        returns = [point.forward_return for point in bucket_points]
        result.append(sum(returns) / len(returns))
    return result


def _raise_if_feature_data_too_sparse(feature_points: list[FeaturePoint], shortest_horizon_seconds: int) -> None:
    if len(feature_points) < 2:
        raise RuntimeError("Feature data is too sparse: at least two rows are required")

    gaps_seconds = [
        (current.ts_event - previous.ts_event) / NS_PER_SECOND
        for previous, current in zip(feature_points, feature_points[1:])
    ]
    median_gap_seconds = statistics.median(gaps_seconds)
    if median_gap_seconds > shortest_horizon_seconds * 2:
        raise RuntimeError(
            "Feature data is too sparse for trade density diagnostics: "
            f"median gap is {median_gap_seconds:.3f}s but shortest horizon is "
            f"{shortest_horizon_seconds}s.",
        )


def _summary_payload(summary: RegimeSummary) -> dict[str, int | str | float]:
    return {
        "regime": summary.regime,
        "horizonSeconds": summary.horizon_seconds,
        "count": summary.count,
        "densityMin": summary.density_min,
        "densityMax": summary.density_max,
        "densityMedian": summary.density_median,
        "bucketCount": summary.bucket_count,
        "topBottomSpread": summary.top_bottom_spread,
        "lowBucketMeanReturn": summary.low_bucket_mean_return,
        "highBucketMeanReturn": summary.high_bucket_mean_return,
    }


def _table_row(summary: RegimeSummary) -> str:
    return f"""<tr>
<td>{html.escape(summary.regime)}</td>
<td>{summary.horizon_seconds}s</td>
<td>{summary.count:,}</td>
<td>{summary.density_min}</td>
<td>{summary.density_max}</td>
<td>{summary.density_median:g}</td>
<td>{summary.low_bucket_mean_return:.5%}</td>
<td>{summary.high_bucket_mean_return:.5%}</td>
<td>{summary.top_bottom_spread:.5%}</td>
</tr>"""


def _stat(label: str, value: str) -> str:
    return f"""<div class="stat"><div class="label">{html.escape(label)}</div><div class="value">{html.escape(value)}</div></div>"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render imbalance diagnostics split by trade density.")
    parser.add_argument("source", type=Path)
    parser.add_argument("--feature-source", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/reports/trade_density_report.html"),
    )
    parser.add_argument("--horizons-seconds", type=int, nargs="+", default=[10, 30, 60])
    parser.add_argument("--bucket-count", type=int, default=10)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    context = build_density_context(
        args.source,
        args.feature_source,
        horizons_seconds=args.horizons_seconds,
        bucket_count=args.bucket_count,
    )
    write_density_report_html(context, args.output)
    print(f"wrote trade density report to {args.output}")
    print(f"alpha_rows={context.row_count}")
    print(f"joined_rows={context.joined_count}")
    print(f"density_threshold={context.density_threshold:g}")


if __name__ == "__main__":
    main()
