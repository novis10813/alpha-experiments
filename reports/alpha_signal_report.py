from __future__ import annotations

import argparse
import csv
import html
import json
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class ReportPoint:
    ts_event: int
    timestamp: str
    value: float


@dataclass(frozen=True)
class ReportContext:
    source_path: Path
    price_source_path: Path | None
    row_count: int
    instrument_id: str
    alpha_name: str
    threshold: float
    min_value: float
    max_value: float
    mean_value: float
    first_timestamp: str
    last_timestamp: str
    series_points: list[ReportPoint]
    positive_events: list[ReportPoint]
    negative_events: list[ReportPoint]
    histogram: list[int]
    histogram_bins: list[float]
    price_points: list[ReportPoint]


def build_report_context(
    source_path: Path,
    price_path: Path | None = None,
    max_points: int = 5000,
    max_events: int = 500,
    threshold: float = 0.5,
    histogram_bins: int = 40,
) -> ReportContext:
    rows = _read_signal_rows(source_path)
    if not rows:
        raise RuntimeError(f"No signal rows found in {source_path}")

    values = [point.value for point in rows]
    first = rows[0]
    last = rows[-1]
    positive_events = [point for point in rows if point.value >= threshold][:max_events]
    negative_events = [point for point in rows if point.value <= -threshold][:max_events]
    price_points = _downsample(_read_price_rows(price_path), max_points) if price_path else []

    return ReportContext(
        source_path=source_path,
        price_source_path=price_path,
        row_count=len(rows),
        instrument_id=_first_column_value(source_path, "instrument_id"),
        alpha_name=_first_column_value(source_path, "alpha_name"),
        threshold=threshold,
        min_value=min(values),
        max_value=max(values),
        mean_value=sum(values) / len(values),
        first_timestamp=first.timestamp,
        last_timestamp=last.timestamp,
        series_points=_downsample(rows, max_points),
        positive_events=positive_events,
        negative_events=negative_events,
        histogram=_histogram(values, histogram_bins),
        histogram_bins=_histogram_bins(values, histogram_bins),
        price_points=price_points,
    )


def write_report_html(context: ReportContext, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_report_html(context), encoding="utf-8")


def render_report_html(context: ReportContext) -> str:
    title = _title_for(context.alpha_name)
    payload = {
        "seriesPoints": [_point_payload(point) for point in context.series_points],
        "positiveEvents": [_point_payload(point) for point in context.positive_events],
        "negativeEvents": [_point_payload(point) for point in context.negative_events],
        "pricePoints": [_point_payload(point) for point in context.price_points],
        "histogram": context.histogram,
        "histogramBins": context.histogram_bins,
        "minValue": context.min_value,
        "maxValue": context.max_value,
        "threshold": context.threshold,
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
      --positive: #087f5b;
      --negative: #c92a2a;
      --signal: #1c5fd4;
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
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
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
    #histogram {{
      height: 180px;
    }}
  </style>
</head>
<body>
  <main>
    <h1>{html.escape(title)}</h1>
    <div class="subtitle">{html.escape(context.instrument_id)} · {html.escape(context.first_timestamp)} to {html.escape(context.last_timestamp)} · threshold: {context.threshold:g}</div>
    <section class="stats" aria-label="Signal summary">
      {_stat("Rows", f"{context.row_count:,}")}
      {_stat("Sampled points", f"{len(context.series_points):,}")}
      {_stat("Positive events", f"{len(context.positive_events):,}")}
      {_stat("Negative events", f"{len(context.negative_events):,}")}
      {_stat("Min", f"{context.min_value:.6f}")}
      {_stat("Max", f"{context.max_value:.6f}")}
      {_stat("Mean", f"{context.mean_value:.6f}")}
      {_stat("Source", str(context.source_path))}
      {_stat("Price source", str(context.price_source_path) if context.price_source_path else "none")}
    </section>
    <section class="chart">
      <div class="label">Signal over time</div>
      <div id="series" class="plot"></div>
    </section>
    <section class="chart">
      <div class="label">Value distribution</div>
      <div id="histogram" class="plot"></div>
    </section>
  </main>
  <script>
    const reportData = {payload_json};
    const plotConfig = {{
      responsive: true,
      displaylogo: false,
      scrollZoom: true,
      modeBarButtonsToRemove: ["zoom2d", "select2d", "lasso2d", "autoScale2d"],
    }};
    const commonLayout = {{
      margin: {{ l: 48, r: 18, t: 18, b: 44 }},
      paper_bgcolor: "#ffffff",
      plot_bgcolor: "#ffffff",
      font: {{ family: "ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif", color: "#18212f" }},
      xaxis: {{ gridcolor: "#edf0f4", zerolinecolor: "#8a94a6" }},
      yaxis: {{ gridcolor: "#edf0f4", zerolinecolor: "#8a94a6" }},
      hovermode: "x unified",
    }};
    function drawSeries() {{
      const points = reportData.seriesPoints;
      const x = points.map(point => point.timestamp);
      const y = points.map(point => point.value);
      const positive = points.filter(point => point.value >= reportData.threshold);
      const negative = points.filter(point => point.value <= -reportData.threshold);
      const pricePoints = reportData.pricePoints;
      const traces = [
        {{
          name: "signal",
          type: "scatter",
          mode: "lines",
          x,
          y,
          line: {{ color: "#1c5fd4", width: 1.4 }},
        }},
        {{
          name: "positive threshold event",
          type: "scatter",
          mode: "markers",
          x: positive.map(point => point.timestamp),
          y: positive.map(point => point.value),
          marker: {{ color: "#087f5b", size: 5 }},
        }},
        {{
          name: "negative threshold event",
          type: "scatter",
          mode: "markers",
          x: negative.map(point => point.timestamp),
          y: negative.map(point => point.value),
          marker: {{ color: "#c92a2a", size: 5 }},
        }},
      ];
      if (pricePoints.length > 0) {{
        traces.push({{
          name: "trade price",
          type: "scatter",
          mode: "lines",
          x: pricePoints.map(point => point.timestamp),
          y: pricePoints.map(point => point.value),
          yaxis: "y2",
          line: {{ color: "#6f42c1", width: 1.3 }},
        }});
      }}
      const minY = Math.min(reportData.minValue, -reportData.threshold);
      const maxY = Math.max(reportData.maxValue, reportData.threshold);
      Plotly.newPlot("series", traces, {{
        ...commonLayout,
        dragmode: "pan",
        margin: {{ l: 52, r: pricePoints.length > 0 ? 64 : 18, t: 18, b: 70 }},
        xaxis: {{
          ...commonLayout.xaxis,
          rangeslider: {{ visible: true, thickness: 0.12 }},
          rangeselector: {{
            buttons: [
              {{ count: 6, label: "6h", step: "hour", stepmode: "backward" }},
              {{ count: 1, label: "1d", step: "day", stepmode: "backward" }},
              {{ count: 3, label: "3d", step: "day", stepmode: "backward" }},
              {{ step: "all", label: "all" }},
            ],
          }},
        }},
        yaxis: {{ ...commonLayout.yaxis, title: "alpha value", range: [minY, maxY] }},
        yaxis2: {{
          title: "trade price",
          overlaying: "y",
          side: "right",
          showgrid: false,
          zeroline: false,
        }},
        shapes: [
          thresholdLine(reportData.threshold, "#087f5b"),
          thresholdLine(-reportData.threshold, "#c92a2a"),
          thresholdLine(0, "#8a94a6"),
        ],
      }}, plotConfig);
    }}
    function drawHistogram() {{
      Plotly.newPlot("histogram", [{{
        name: "count",
        type: "bar",
        x: reportData.histogramBins,
        y: reportData.histogram,
        marker: {{ color: "#385f8f" }},
      }}], {{
        ...commonLayout,
        margin: {{ l: 48, r: 18, t: 12, b: 36 }},
        xaxis: {{ ...commonLayout.xaxis, title: "alpha value bin", type: "linear" }},
        yaxis: {{ ...commonLayout.yaxis, title: "count" }},
        hovermode: "closest",
      }}, plotConfig);
    }}
    function thresholdLine(value, color) {{
      return {{
        type: "line",
        xref: "paper",
        x0: 0,
        x1: 1,
        y0: value,
        y1: value,
        line: {{ color, width: 1, dash: "dash" }},
      }};
    }}
    drawSeries();
    drawHistogram();
  </script>
</body>
</html>
"""


def _read_signal_rows(source_path: Path) -> list[ReportPoint]:
    points: list[ReportPoint] = []
    with source_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            ts_event = int(row["ts_event"])
            points.append(
                ReportPoint(
                    ts_event=ts_event,
                    timestamp=_ts_event_to_iso(ts_event),
                    value=float(row["value"]),
                ),
            )
    return points


def _read_price_rows(source_path: Path) -> list[ReportPoint]:
    points: list[ReportPoint] = []
    with source_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            ts_event = int(row["ts_event"])
            points.append(
                ReportPoint(
                    ts_event=ts_event,
                    timestamp=_ts_event_to_iso(ts_event),
                    value=float(row["price"]),
                ),
            )
    return points


def _first_column_value(source_path: Path, column: str) -> str:
    with source_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        first = next(reader, None)
        if first is None:
            return ""
        return first[column]


def _downsample(points: list[ReportPoint], max_points: int) -> list[ReportPoint]:
    if len(points) <= max_points:
        return points
    step = (len(points) - 1) / (max_points - 1)
    return [points[round(index * step)] for index in range(max_points)]


def _histogram(values: list[float], bins: int) -> list[int]:
    min_value = min(values)
    max_value = max(values)
    if min_value == max_value:
        result = [0] * bins
        result[0] = len(values)
        return result

    result = [0] * bins
    width = (max_value - min_value) / bins
    for value in values:
        index = min(int((value - min_value) / width), bins - 1)
        result[index] += 1
    return result


def _histogram_bins(values: list[float], bins: int) -> list[float]:
    min_value = min(values)
    max_value = max(values)
    if min_value == max_value:
        return [min_value for _ in range(bins)]

    width = (max_value - min_value) / bins
    return [min_value + index * width + width / 2 for index in range(bins)]


def _ts_event_to_iso(ts_event: int) -> str:
    return datetime.fromtimestamp(ts_event / 1_000_000_000, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _point_payload(point: ReportPoint) -> dict[str, int | str | float]:
    return {
        "ts_event": point.ts_event,
        "timestamp": point.timestamp,
        "value": point.value,
    }


def _title_for(alpha_name: str) -> str:
    if alpha_name == "orderbook_imbalance_depth10":
        return "Order Book Imbalance"
    return alpha_name.replace("_", " ").title()


def _stat(label: str, value: str) -> str:
    return f"""<div class="stat"><div class="label">{html.escape(label)}</div><div class="value">{html.escape(value)}</div></div>"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render an alpha signal CSV as a standalone HTML report.")
    parser.add_argument("source", type=Path)
    parser.add_argument("--price-source", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/reports/alpha_signal_report.html"),
    )
    parser.add_argument("--max-points", type=int, default=5000)
    parser.add_argument("--max-events", type=int, default=500)
    parser.add_argument("--threshold", type=float, default=0.5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    context = build_report_context(
        args.source,
        price_path=args.price_source,
        max_points=args.max_points,
        max_events=args.max_events,
        threshold=args.threshold,
    )
    write_report_html(context, args.output)
    print(f"wrote alpha signal report to {args.output}")
    print(f"rows={context.row_count}")
    print(f"sampled_points={len(context.series_points)}")
    print(f"positive_events={len(context.positive_events)}")
    print(f"negative_events={len(context.negative_events)}")


if __name__ == "__main__":
    main()
