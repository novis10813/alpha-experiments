from __future__ import annotations

import argparse
import bisect
import csv
import html
import json
import math
import statistics
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class AlphaPoint:
    ts_event: int
    timestamp: str
    value: float


@dataclass(frozen=True)
class FeaturePoint:
    ts_event: int
    price: float
    volume: float


@dataclass(frozen=True)
class InteractionPoint:
    ts_event: int
    timestamp: str
    alpha_value: float
    volume: float
    volume_intensity: float
    volume_zscore: float
    interaction_value: float
    horizon_seconds: int
    forward_return: float


@dataclass(frozen=True)
class BucketSummary:
    bucket: int
    min_signal: float
    max_signal: float
    count: int
    mean_signal: float
    mean_forward_return: float
    median_forward_return: float
    positive_rate: float


@dataclass(frozen=True)
class VolumeInteractionContext:
    alpha_source_path: Path
    feature_source_path: Path
    instrument_id: str
    alpha_name: str
    horizons_seconds: list[int]
    row_count: int
    joined_count: int
    points: list[InteractionPoint]
    raw_bucket_summaries: list[BucketSummary]
    interaction_bucket_summaries: list[BucketSummary]


def build_volume_interaction_context(
    alpha_path: Path,
    feature_path: Path,
    horizons_seconds: list[int] | None = None,
    bucket_count: int = 10,
    max_points: int = 5000,
) -> VolumeInteractionContext:
    horizons = horizons_seconds or [10, 30, 60]
    if not horizons:
        raise ValueError("horizons_seconds must not be empty")
    if bucket_count <= 0:
        raise ValueError("bucket_count must be positive")

    alpha_points = _read_alpha_points(alpha_path)
    if not alpha_points:
        raise RuntimeError(f"No alpha rows found in {alpha_path}")

    feature_points = _read_feature_points(feature_path)
    if not feature_points:
        raise RuntimeError(f"No feature rows found in {feature_path}")
    _raise_if_feature_data_too_sparse(feature_points, min(horizons))

    points = _interaction_points(alpha_points, feature_points, horizons)
    first_horizon_points = [point for point in points if point.horizon_seconds == horizons[0]]

    return VolumeInteractionContext(
        alpha_source_path=alpha_path,
        feature_source_path=feature_path,
        instrument_id=_first_column_value(alpha_path, "instrument_id"),
        alpha_name=_first_column_value(alpha_path, "alpha_name"),
        horizons_seconds=horizons,
        row_count=len(alpha_points),
        joined_count=len(first_horizon_points),
        points=_downsample(points, max_points),
        raw_bucket_summaries=_bucket_summaries(
            first_horizon_points,
            bucket_count,
            signal_getter=lambda point: point.alpha_value,
        ),
        interaction_bucket_summaries=_bucket_summaries(
            first_horizon_points,
            bucket_count,
            signal_getter=lambda point: point.interaction_value,
        ),
    )


def write_volume_interaction_report_html(context: VolumeInteractionContext, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_volume_interaction_report_html(context), encoding="utf-8")


def render_volume_interaction_report_html(context: VolumeInteractionContext) -> str:
    title = "Volume Interaction Report"
    payload = {
        "points": [_point_payload(point) for point in context.points],
        "rawBucketSummaries": [_bucket_payload(summary) for summary in context.raw_bucket_summaries],
        "interactionBucketSummaries": [
            _bucket_payload(summary) for summary in context.interaction_bucket_summaries
        ],
        "horizonsSeconds": context.horizons_seconds,
    }
    payload_json = json.dumps(payload, separators=(",", ":"))
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
  </style>
</head>
<body>
  <main>
    <h1>{html.escape(title)}</h1>
    <div class="subtitle">{html.escape(context.instrument_id)} · horizons: {html.escape(", ".join(str(value) + "s" for value in context.horizons_seconds))} · interaction: imbalance * log-volume intensity</div>
    <section class="stats" aria-label="Volume interaction summary">
      {_stat("Alpha rows", f"{context.row_count:,}")}
      {_stat("Joined rows", f"{context.joined_count:,}")}
      {_stat("Alpha source", str(context.alpha_source_path))}
      {_stat("Feature source", str(context.feature_source_path))}
    </section>
    <section class="chart">
      <div class="label">Bucket mean forward return comparison</div>
      <div id="bucket-comparison" class="plot"></div>
    </section>
    <section class="chart">
      <div class="label">Interaction value vs forward return</div>
      <div id="scatter" class="plot"></div>
    </section>
  </main>
  <script>
    const reportData = {payload_json};
    const plotConfig = {{ responsive: true, displaylogo: false, scrollZoom: true }};
    const commonLayout = {{
      margin: {{ l: 58, r: 18, t: 18, b: 54 }},
      paper_bgcolor: "#ffffff",
      plot_bgcolor: "#ffffff",
      font: {{ family: "ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif", color: "#18212f" }},
      xaxis: {{ gridcolor: "#edf0f4", zerolinecolor: "#8a94a6" }},
      yaxis: {{ gridcolor: "#edf0f4", zerolinecolor: "#8a94a6", tickformat: ".3%" }},
      hovermode: "closest",
    }};
    function drawBucketComparison() {{
      const x = reportData.rawBucketSummaries.map(row => row.bucket);
      Plotly.newPlot("bucket-comparison", [
        {{
          name: "raw imbalance",
          type: "bar",
          x,
          y: reportData.rawBucketSummaries.map(row => row.meanForwardReturn),
        }},
        {{
          name: "imbalance x volume",
          type: "bar",
          x,
          y: reportData.interactionBucketSummaries.map(row => row.meanForwardReturn),
        }},
      ], {{
        ...commonLayout,
        barmode: "group",
        xaxis: {{ ...commonLayout.xaxis, title: "bucket" }},
        yaxis: {{ ...commonLayout.yaxis, title: "mean forward return" }},
      }}, plotConfig);
    }}
    function drawScatter() {{
      const horizon = reportData.horizonsSeconds[0];
      const points = reportData.points.filter(point => point.horizonSeconds === horizon);
      Plotly.newPlot("scatter", [{{
        name: "interaction",
        type: "scattergl",
        mode: "markers",
        x: points.map(point => point.interactionValue),
        y: points.map(point => point.forwardReturn),
        marker: {{ color: "#1c5fd4", size: 5, opacity: 0.55 }},
      }}], {{
        ...commonLayout,
        xaxis: {{ ...commonLayout.xaxis, title: "imbalance x log-volume intensity" }},
        yaxis: {{ ...commonLayout.yaxis, title: `${{horizon}}s forward return` }},
      }}, plotConfig);
    }}
    drawBucketComparison();
    drawScatter();
  </script>
</body>
</html>
"""


def _interaction_points(
    alpha_points: list[AlphaPoint],
    feature_points: list[FeaturePoint],
    horizons_seconds: list[int],
) -> list[InteractionPoint]:
    feature_times = [point.ts_event for point in feature_points]
    log_volumes = [math.log1p(point.volume) for point in feature_points]
    mean_log_volume = sum(log_volumes) / len(log_volumes)
    stdev_log_volume = statistics.pstdev(log_volumes) or 1.0
    volume_zscores = [
        (value - mean_log_volume) / stdev_log_volume
        for value in log_volumes
    ]
    volume_intensities = [
        value / mean_log_volume if mean_log_volume else 1.0
        for value in log_volumes
    ]

    result: list[InteractionPoint] = []
    for alpha in alpha_points:
        current_index = bisect.bisect_right(feature_times, alpha.ts_event) - 1
        if current_index < 0:
            continue
        current_feature = feature_points[current_index]
        current_price = current_feature.price
        if current_price == 0:
            continue
        volume_intensity = volume_intensities[current_index]
        volume_zscore = volume_zscores[current_index]
        interaction_value = alpha.value * volume_intensity
        for horizon_seconds in horizons_seconds:
            future_index = bisect.bisect_left(
                feature_times,
                alpha.ts_event + horizon_seconds * 1_000_000_000,
            )
            if future_index >= len(feature_points):
                continue
            future_price = feature_points[future_index].price
            result.append(
                InteractionPoint(
                    ts_event=alpha.ts_event,
                    timestamp=alpha.timestamp,
                    alpha_value=alpha.value,
                    volume=current_feature.volume,
                    volume_intensity=volume_intensity,
                    volume_zscore=volume_zscore,
                    interaction_value=interaction_value,
                    horizon_seconds=horizon_seconds,
                    forward_return=(future_price / current_price) - 1,
                ),
            )
    return result


def _bucket_summaries(
    points: list[InteractionPoint],
    bucket_count: int,
    signal_getter: object,
) -> list[BucketSummary]:
    if not points:
        return []

    sorted_points = sorted(points, key=signal_getter)
    actual_bucket_count = min(bucket_count, len(sorted_points))
    summaries: list[BucketSummary] = []
    for bucket_index in range(actual_bucket_count):
        start = round(bucket_index * len(sorted_points) / actual_bucket_count)
        end = round((bucket_index + 1) * len(sorted_points) / actual_bucket_count)
        bucket_points = sorted_points[start:end]
        signals = [signal_getter(point) for point in bucket_points]
        returns = [point.forward_return for point in bucket_points]
        summaries.append(
            BucketSummary(
                bucket=bucket_index + 1,
                min_signal=min(signals),
                max_signal=max(signals),
                count=len(bucket_points),
                mean_signal=sum(signals) / len(signals),
                mean_forward_return=sum(returns) / len(returns),
                median_forward_return=statistics.median(returns),
                positive_rate=sum(1 for value in returns if value > 0) / len(returns),
            ),
        )
    return summaries


def _read_alpha_points(source_path: Path) -> list[AlphaPoint]:
    points: list[AlphaPoint] = []
    with source_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            ts_event = int(row["ts_event"])
            points.append(
                AlphaPoint(
                    ts_event=ts_event,
                    timestamp=_ts_event_to_iso(ts_event),
                    value=float(row["value"]),
                ),
            )
    return sorted(points, key=lambda point: point.ts_event)


def _read_feature_points(source_path: Path) -> list[FeaturePoint]:
    points: list[FeaturePoint] = []
    with source_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            points.append(
                FeaturePoint(
                    ts_event=int(row["ts_event"]),
                    price=float(row["price"]),
                    volume=float(row["volume"]),
                ),
            )
    return sorted(points, key=lambda point: point.ts_event)


def _raise_if_feature_data_too_sparse(feature_points: list[FeaturePoint], shortest_horizon_seconds: int) -> None:
    if len(feature_points) < 2:
        raise RuntimeError("Feature data is too sparse: at least two rows are required")

    gaps_seconds = [
        (current.ts_event - previous.ts_event) / 1_000_000_000
        for previous, current in zip(feature_points, feature_points[1:])
    ]
    median_gap_seconds = statistics.median(gaps_seconds)
    if median_gap_seconds > shortest_horizon_seconds * 2:
        raise RuntimeError(
            "Feature data is too sparse for volume interaction diagnostics: "
            f"median gap is {median_gap_seconds:.3f}s but shortest horizon is "
            f"{shortest_horizon_seconds}s.",
        )


def _downsample(points: list[InteractionPoint], max_points: int) -> list[InteractionPoint]:
    if max_points <= 0:
        raise ValueError("max_points must be positive")
    if len(points) <= max_points:
        return points
    if max_points == 1:
        return [points[0]]

    step = (len(points) - 1) / (max_points - 1)
    return [points[round(index * step)] for index in range(max_points)]


def _first_column_value(source_path: Path, column: str) -> str:
    with source_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        first = next(reader, None)
        if first is None:
            return ""
        return first[column]


def _ts_event_to_iso(ts_event: int) -> str:
    return datetime.fromtimestamp(ts_event / 1_000_000_000, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _point_payload(point: InteractionPoint) -> dict[str, int | str | float]:
    return {
        "tsEvent": point.ts_event,
        "timestamp": point.timestamp,
        "alphaValue": point.alpha_value,
        "volume": point.volume,
        "volumeIntensity": point.volume_intensity,
        "volumeZscore": point.volume_zscore,
        "interactionValue": point.interaction_value,
        "horizonSeconds": point.horizon_seconds,
        "forwardReturn": point.forward_return,
    }


def _bucket_payload(summary: BucketSummary) -> dict[str, int | float]:
    return {
        "bucket": summary.bucket,
        "minSignal": summary.min_signal,
        "maxSignal": summary.max_signal,
        "count": summary.count,
        "meanSignal": summary.mean_signal,
        "meanForwardReturn": summary.mean_forward_return,
        "medianForwardReturn": summary.median_forward_return,
        "positiveRate": summary.positive_rate,
    }


def _stat(label: str, value: str) -> str:
    return f"""<div class="stat"><div class="label">{html.escape(label)}</div><div class="value">{html.escape(value)}</div></div>"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render imbalance x trade volume diagnostics as HTML.")
    parser.add_argument("source", type=Path)
    parser.add_argument("--feature-source", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/reports/volume_interaction_report.html"),
    )
    parser.add_argument("--horizons-seconds", type=int, nargs="+", default=[10, 30, 60])
    parser.add_argument("--bucket-count", type=int, default=10)
    parser.add_argument("--max-points", type=int, default=5000)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    context = build_volume_interaction_context(
        args.source,
        args.feature_source,
        horizons_seconds=args.horizons_seconds,
        bucket_count=args.bucket_count,
        max_points=args.max_points,
    )
    write_volume_interaction_report_html(context, args.output)
    print(f"wrote volume interaction report to {args.output}")
    print(f"alpha_rows={context.row_count}")
    print(f"joined_rows={context.joined_count}")


if __name__ == "__main__":
    main()
