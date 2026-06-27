from __future__ import annotations

import argparse
import bisect
import csv
import html
import json
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
class PricePoint:
    ts_event: int
    price: float


@dataclass(frozen=True)
class ForwardReturnPoint:
    ts_event: int
    timestamp: str
    alpha_value: float
    horizon_seconds: int
    current_price: float
    future_price: float
    forward_return: float


@dataclass(frozen=True)
class BucketSummary:
    bucket: int
    min_alpha: float
    max_alpha: float
    count: int
    mean_alpha: float
    mean_forward_return: float
    median_forward_return: float
    positive_rate: float


@dataclass(frozen=True)
class RelationshipContext:
    alpha_source_path: Path
    price_source_path: Path
    instrument_id: str
    alpha_name: str
    horizons_seconds: list[int]
    row_count: int
    forward_return_points: list[ForwardReturnPoint]
    bucket_summaries: list[BucketSummary]


def build_relationship_context(
    alpha_path: Path,
    price_path: Path,
    horizons_seconds: list[int] | None = None,
    bucket_count: int = 10,
    max_points: int = 5000,
) -> RelationshipContext:
    horizons = horizons_seconds or [1, 5, 30, 60]
    if not horizons:
        raise ValueError("horizons_seconds must not be empty")
    if bucket_count <= 0:
        raise ValueError("bucket_count must be positive")

    alpha_points = _read_alpha_points(alpha_path)
    if not alpha_points:
        raise RuntimeError(f"No alpha rows found in {alpha_path}")

    price_points = _read_price_points(price_path)
    if not price_points:
        raise RuntimeError(f"No price rows found in {price_path}")
    _raise_if_price_data_too_sparse(price_points, min(horizons))

    joined_points = _forward_return_points(alpha_points, price_points, horizons)
    sampled_points = _downsample(joined_points, max_points)
    bucket_summaries = _bucket_summaries(
        [point for point in joined_points if point.horizon_seconds == horizons[0]],
        bucket_count,
    )

    return RelationshipContext(
        alpha_source_path=alpha_path,
        price_source_path=price_path,
        instrument_id=_first_column_value(alpha_path, "instrument_id"),
        alpha_name=_first_column_value(alpha_path, "alpha_name"),
        horizons_seconds=horizons,
        row_count=len(alpha_points),
        forward_return_points=sampled_points,
        bucket_summaries=bucket_summaries,
    )


def write_relationship_report_html(context: RelationshipContext, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_relationship_report_html(context), encoding="utf-8")


def render_relationship_report_html(context: RelationshipContext) -> str:
    title = f"{_title_for(context.alpha_name)} Relationship"
    payload = {
        "forwardReturnPoints": [_forward_return_payload(point) for point in context.forward_return_points],
        "bucketSummaries": [_bucket_payload(summary) for summary in context.bucket_summaries],
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
      height: 360px;
    }}
  </style>
</head>
<body>
  <main>
    <h1>{html.escape(title)}</h1>
    <div class="subtitle">{html.escape(context.instrument_id)} · horizons: {html.escape(", ".join(str(value) + "s" for value in context.horizons_seconds))}</div>
    <section class="stats" aria-label="Relationship summary">
      {_stat("Alpha rows", f"{context.row_count:,}")}
      {_stat("Forward-return points", f"{len(context.forward_return_points):,}")}
      {_stat("Buckets", f"{len(context.bucket_summaries):,}")}
      {_stat("Alpha source", str(context.alpha_source_path))}
      {_stat("Price source", str(context.price_source_path))}
    </section>
    <section class="chart">
      <div class="label">Alpha value vs forward return</div>
      <div id="scatter" class="plot"></div>
    </section>
    <section class="chart">
      <div class="label">Mean forward return by alpha bucket</div>
      <div id="buckets" class="plot"></div>
    </section>
  </main>
  <script>
    const reportData = {payload_json};
    const plotConfig = {{
      responsive: true,
      displaylogo: false,
      scrollZoom: true,
      modeBarButtonsToRemove: ["select2d", "lasso2d"],
    }};
    const commonLayout = {{
      margin: {{ l: 58, r: 18, t: 18, b: 54 }},
      paper_bgcolor: "#ffffff",
      plot_bgcolor: "#ffffff",
      font: {{ family: "ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif", color: "#18212f" }},
      xaxis: {{ gridcolor: "#edf0f4", zerolinecolor: "#8a94a6" }},
      yaxis: {{ gridcolor: "#edf0f4", zerolinecolor: "#8a94a6", tickformat: ".2%" }},
      hovermode: "closest",
    }};
    function drawScatter() {{
      const horizon = reportData.horizonsSeconds[0];
      const points = reportData.forwardReturnPoints.filter(point => point.horizonSeconds === horizon);
      Plotly.newPlot("scatter", [{{
        name: "forward return",
        type: "scattergl",
        mode: "markers",
        x: points.map(point => point.alphaValue),
        y: points.map(point => point.forwardReturn),
        text: points.map(point => point.timestamp),
        marker: {{ color: "#1c5fd4", size: 5, opacity: 0.55 }},
      }}], {{
        ...commonLayout,
        xaxis: {{ ...commonLayout.xaxis, title: "alpha value" }},
        yaxis: {{ ...commonLayout.yaxis, title: `${{horizon}}s forward return` }},
      }}, plotConfig);
    }}
    function drawBuckets() {{
      const buckets = reportData.bucketSummaries;
      Plotly.newPlot("buckets", [{{
        name: "bucket mean",
        type: "bar",
        x: buckets.map(bucket => `${{bucket.minAlpha.toFixed(3)}} to ${{bucket.maxAlpha.toFixed(3)}}`),
        y: buckets.map(bucket => bucket.meanForwardReturn),
        customdata: buckets.map(bucket => [bucket.count, bucket.positiveRate]),
        marker: {{ color: "#087f5b" }},
        hovertemplate: "bucket=%{{x}}<br>mean=%{{y:.4%}}<br>count=%{{customdata[0]}}<br>positive=%{{customdata[1]:.2%}}<extra></extra>",
      }}], {{
        ...commonLayout,
        xaxis: {{ ...commonLayout.xaxis, title: "alpha bucket", tickangle: -30 }},
        yaxis: {{ ...commonLayout.yaxis, title: "mean forward return" }},
      }}, plotConfig);
    }}
    drawScatter();
    drawBuckets();
  </script>
</body>
</html>
"""


def _forward_return_points(
    alpha_points: list[AlphaPoint],
    price_points: list[PricePoint],
    horizons_seconds: list[int],
) -> list[ForwardReturnPoint]:
    price_times = [point.ts_event for point in price_points]
    result: list[ForwardReturnPoint] = []
    for alpha in alpha_points:
        current_price = _price_at_or_before(alpha.ts_event, price_points, price_times)
        if current_price is None or current_price == 0:
            continue
        for horizon_seconds in horizons_seconds:
            future_ts = alpha.ts_event + horizon_seconds * 1_000_000_000
            future_price = _price_at_or_after(future_ts, price_points, price_times)
            if future_price is None:
                continue
            result.append(
                ForwardReturnPoint(
                    ts_event=alpha.ts_event,
                    timestamp=alpha.timestamp,
                    alpha_value=alpha.value,
                    horizon_seconds=horizon_seconds,
                    current_price=current_price,
                    future_price=future_price,
                    forward_return=(future_price / current_price) - 1,
                ),
            )
    return result


def _price_at_or_before(
    ts_event: int,
    price_points: list[PricePoint],
    price_times: list[int],
) -> float | None:
    index = bisect.bisect_right(price_times, ts_event) - 1
    if index < 0:
        return None
    return price_points[index].price


def _price_at_or_after(
    ts_event: int,
    price_points: list[PricePoint],
    price_times: list[int],
) -> float | None:
    index = bisect.bisect_left(price_times, ts_event)
    if index >= len(price_points):
        return None
    return price_points[index].price


def _bucket_summaries(points: list[ForwardReturnPoint], bucket_count: int) -> list[BucketSummary]:
    if not points:
        return []

    sorted_points = sorted(points, key=lambda point: point.alpha_value)
    buckets: list[BucketSummary] = []
    actual_bucket_count = min(bucket_count, len(sorted_points))
    for bucket_index in range(actual_bucket_count):
        start = round(bucket_index * len(sorted_points) / actual_bucket_count)
        end = round((bucket_index + 1) * len(sorted_points) / actual_bucket_count)
        bucket_points = sorted_points[start:end]
        alpha_values = [point.alpha_value for point in bucket_points]
        returns = [point.forward_return for point in bucket_points]
        buckets.append(
            BucketSummary(
                bucket=bucket_index + 1,
                min_alpha=min(alpha_values),
                max_alpha=max(alpha_values),
                count=len(bucket_points),
                mean_alpha=sum(alpha_values) / len(alpha_values),
                mean_forward_return=sum(returns) / len(returns),
                median_forward_return=statistics.median(returns),
                positive_rate=sum(1 for value in returns if value > 0) / len(returns),
            ),
        )
    return buckets


def _raise_if_price_data_too_sparse(price_points: list[PricePoint], shortest_horizon_seconds: int) -> None:
    if len(price_points) < 2:
        raise RuntimeError("Price data is too sparse: at least two price rows are required")

    gaps_seconds = [
        (current.ts_event - previous.ts_event) / 1_000_000_000
        for previous, current in zip(price_points, price_points[1:])
    ]
    median_gap_seconds = statistics.median(gaps_seconds)
    if median_gap_seconds > shortest_horizon_seconds * 2:
        raise RuntimeError(
            "Price data is too sparse for forward-return diagnostics: "
            f"median price gap is {median_gap_seconds:.3f}s but shortest horizon is "
            f"{shortest_horizon_seconds}s. Export trade prices with --no-downsample.",
        )


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


def _read_price_points(source_path: Path) -> list[PricePoint]:
    points: list[PricePoint] = []
    with source_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            points.append(
                PricePoint(
                    ts_event=int(row["ts_event"]),
                    price=float(row["price"]),
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


def _downsample(points: list[ForwardReturnPoint], max_points: int) -> list[ForwardReturnPoint]:
    if max_points <= 0:
        raise ValueError("max_points must be positive")
    if len(points) <= max_points:
        return points
    if max_points == 1:
        return [points[0]]

    step = (len(points) - 1) / (max_points - 1)
    return [points[round(index * step)] for index in range(max_points)]


def _ts_event_to_iso(ts_event: int) -> str:
    return datetime.fromtimestamp(ts_event / 1_000_000_000, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _title_for(alpha_name: str) -> str:
    if alpha_name == "orderbook_imbalance_depth10":
        return "Order Book Imbalance"
    return alpha_name.replace("_", " ").title()


def _forward_return_payload(point: ForwardReturnPoint) -> dict[str, int | str | float]:
    return {
        "ts_event": point.ts_event,
        "timestamp": point.timestamp,
        "alphaValue": point.alpha_value,
        "horizonSeconds": point.horizon_seconds,
        "currentPrice": point.current_price,
        "futurePrice": point.future_price,
        "forwardReturn": point.forward_return,
    }


def _bucket_payload(summary: BucketSummary) -> dict[str, int | float]:
    return {
        "bucket": summary.bucket,
        "minAlpha": summary.min_alpha,
        "maxAlpha": summary.max_alpha,
        "count": summary.count,
        "meanAlpha": summary.mean_alpha,
        "meanForwardReturn": summary.mean_forward_return,
        "medianForwardReturn": summary.median_forward_return,
        "positiveRate": summary.positive_rate,
    }


def _stat(label: str, value: str) -> str:
    return f"""<div class="stat"><div class="label">{html.escape(label)}</div><div class="value">{html.escape(value)}</div></div>"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render alpha vs forward-return diagnostics as HTML.")
    parser.add_argument("source", type=Path)
    parser.add_argument("--price-source", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/reports/alpha_relationship_report.html"),
    )
    parser.add_argument("--horizons-seconds", type=int, nargs="+", default=[1, 5, 30, 60])
    parser.add_argument("--bucket-count", type=int, default=10)
    parser.add_argument("--max-points", type=int, default=5000)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    context = build_relationship_context(
        args.source,
        args.price_source,
        horizons_seconds=args.horizons_seconds,
        bucket_count=args.bucket_count,
        max_points=args.max_points,
    )
    write_relationship_report_html(context, args.output)
    print(f"wrote alpha relationship report to {args.output}")
    print(f"alpha_rows={context.row_count}")
    print(f"forward_return_points={len(context.forward_return_points)}")
    print(f"buckets={len(context.bucket_summaries)}")


if __name__ == "__main__":
    main()
