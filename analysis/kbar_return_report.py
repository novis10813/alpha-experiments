from __future__ import annotations

import argparse
import csv
import html
import json
import statistics
from dataclasses import dataclass
from pathlib import Path

from common.kbars import aggregate_price_kbars
from common.time_series import ts_event_to_iso


@dataclass(frozen=True)
class PricePoint:
    ts_event: int
    instrument_id: str
    price: float


@dataclass(frozen=True)
class Kbar:
    start_time: int
    end_time: int
    instrument_id: str
    ts_event: int
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    bar_return: float
    close_to_close_return: float | None


@dataclass(frozen=True)
class ReturnStats:
    count: int
    mean: float
    median: float
    stdev: float
    min_value: float
    max_value: float
    p01: float
    p05: float
    p95: float
    p99: float
    positive_rate: float


@dataclass(frozen=True)
class KbarContext:
    price_source_path: Path
    instrument_id: str
    interval_seconds: int
    bars: list[Kbar]
    bar_return_stats: ReturnStats
    close_to_close_return_stats: ReturnStats


def build_kbar_context(price_path: Path, interval_seconds: int = 60) -> KbarContext:
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")
    price_points = _read_price_points(price_path)
    if not price_points:
        raise RuntimeError(f"No price rows found in {price_path}")
    instrument_ids = {point.instrument_id for point in price_points}
    if len(instrument_ids) != 1:
        raise ValueError("Kbar return report requires exactly one instrument_id")

    bars = _kbars(price_points, interval_seconds)
    if not bars:
        raise RuntimeError(f"No kbars could be built from {price_path}")
    return KbarContext(
        price_source_path=price_path,
        instrument_id=price_points[0].instrument_id,
        interval_seconds=interval_seconds,
        bars=bars,
        bar_return_stats=_return_stats([bar.bar_return for bar in bars]),
        close_to_close_return_stats=_return_stats(
            [
                bar.close_to_close_return
                for bar in bars
                if bar.close_to_close_return is not None
            ],
        ),
    )


def write_kbar_report_html(context: KbarContext, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_kbar_report_html(context), encoding="utf-8")


def render_kbar_report_html(context: KbarContext) -> str:
    title = "Kbar Return Distribution"
    payload = {
        "bars": [_bar_payload(bar) for bar in context.bars],
        "intervalSeconds": context.interval_seconds,
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
    <div class="subtitle">{html.escape(context.instrument_id)} · {context.interval_seconds}s trade-price bars · source: {html.escape(str(context.price_source_path))}</div>
    <section class="stats" aria-label="Kbar return summary">
      {_stat("Bars", f"{len(context.bars):,}")}
      {_stat("Bar return mean", _pct(context.bar_return_stats.mean))}
      {_stat("Bar return stdev", _pct(context.bar_return_stats.stdev))}
      {_stat("Bar return p01 / p99", f"{_pct(context.bar_return_stats.p01)} / {_pct(context.bar_return_stats.p99)}")}
      {_stat("Bar return positive", f"{context.bar_return_stats.positive_rate:.2%}")}
      {_stat("Close-close mean", _pct(context.close_to_close_return_stats.mean))}
    </section>
    <section class="chart">
      <div class="label">Bar return over time: close / open - 1</div>
      <div id="scatter" class="plot"></div>
    </section>
    <section class="chart">
      <div class="label">Return distribution</div>
      <div id="violin" class="plot"></div>
    </section>
  </main>
  <script>
    const reportData = {payload_json};
    const bars = reportData.bars;
    const plotConfig = {{ responsive: true, displaylogo: false, scrollZoom: true }};
    const commonLayout = {{
      margin: {{ l: 58, r: 18, t: 18, b: 54 }},
      paper_bgcolor: "#ffffff",
      plot_bgcolor: "#ffffff",
      font: {{ family: "ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif", color: "#18212f" }},
      xaxis: {{ gridcolor: "#edf0f4", zerolinecolor: "#8a94a6" }},
      yaxis: {{ gridcolor: "#edf0f4", zerolinecolor: "#8a94a6", tickformat: ".3%" }},
    }};
    Plotly.newPlot("scatter", [{{
      name: "bar return",
      type: "scattergl",
      mode: "markers",
      x: bars.map(bar => bar.timestamp),
      y: bars.map(bar => bar.barReturn),
      marker: {{ color: "#1c5fd4", size: 5, opacity: 0.6 }},
      hovertemplate: "%{{x}}<br>return=%{{y:.4%}}<extra></extra>",
    }}], {{
      ...commonLayout,
      xaxis: {{ ...commonLayout.xaxis, title: "bar close time" }},
      yaxis: {{ ...commonLayout.yaxis, title: "close / open - 1" }},
    }}, plotConfig);
    Plotly.newPlot("violin", [
      {{
        name: "close/open",
        type: "violin",
        y: bars.map(bar => bar.barReturn),
        box: {{ visible: true }},
        meanline: {{ visible: true }},
        points: "outliers",
      }},
      {{
        name: "close/prev close",
        type: "violin",
        y: bars.map(bar => bar.closeToCloseReturn).filter(value => value !== null),
        box: {{ visible: true }},
        meanline: {{ visible: true }},
        points: "outliers",
      }},
    ], {{
      ...commonLayout,
      xaxis: {{ ...commonLayout.xaxis, title: "return definition" }},
      yaxis: {{ ...commonLayout.yaxis, title: "return" }},
    }}, plotConfig);
  </script>
</body>
</html>
"""


def _kbars(price_points: list[PricePoint], interval_seconds: int) -> list[Kbar]:
    price_bars = aggregate_price_kbars(
        price_points,
        interval_seconds,
        lambda point: point.ts_event,
        lambda point: point.instrument_id,
        lambda point: point.price,
    )
    bars: list[Kbar] = []
    previous_close: float | None = None

    for price_bar in price_bars:
        bars.append(
            Kbar(
                start_time=price_bar.start_time,
                end_time=price_bar.end_time,
                instrument_id=price_bar.instrument_id,
                ts_event=price_bar.end_time,
                timestamp=ts_event_to_iso(price_bar.end_time),
                open=price_bar.open,
                high=price_bar.high,
                low=price_bar.low,
                close=price_bar.close,
                bar_return=(price_bar.close / price_bar.open) - 1 if price_bar.open else 0.0,
                close_to_close_return=(price_bar.close / previous_close) - 1
                if previous_close not in {None, 0.0}
                else None,
            ),
        )
        previous_close = price_bar.close
    return bars


def _read_price_points(source_path: Path) -> list[PricePoint]:
    points: list[PricePoint] = []
    with source_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            points.append(
                PricePoint(
                    ts_event=int(row["ts_event"]),
                    instrument_id=row["instrument_id"],
                    price=float(row["price"]),
                ),
            )
    return sorted(points, key=lambda point: point.ts_event)


def _return_stats(values: list[float]) -> ReturnStats:
    if not values:
        return ReturnStats(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    sorted_values = sorted(values)
    return ReturnStats(
        count=len(values),
        mean=sum(values) / len(values),
        median=statistics.median(values),
        stdev=statistics.pstdev(values),
        min_value=min(values),
        max_value=max(values),
        p01=_percentile(sorted_values, 0.01),
        p05=_percentile(sorted_values, 0.05),
        p95=_percentile(sorted_values, 0.95),
        p99=_percentile(sorted_values, 0.99),
        positive_rate=sum(1 for value in values if value > 0) / len(values),
    )


def _percentile(sorted_values: list[float], percentile: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    index = percentile * (len(sorted_values) - 1)
    lower = int(index)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = index - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def _bar_payload(bar: Kbar) -> dict[str, int | str | float | None]:
    return {
        "startTime": bar.start_time,
        "endTime": bar.end_time,
        "instrumentId": bar.instrument_id,
        "tsEvent": bar.ts_event,
        "timestamp": bar.timestamp,
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "barReturn": bar.bar_return,
        "closeToCloseReturn": bar.close_to_close_return,
    }


def _pct(value: float) -> str:
    return f"{value:.5%}"


def _stat(label: str, value: str) -> str:
    return f"""<div class="stat"><div class="label">{html.escape(label)}</div><div class="value">{html.escape(value)}</div></div>"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render kbar return distribution from trade price CSV.")
    parser.add_argument("source", type=Path)
    parser.add_argument("--interval-seconds", type=int, default=60)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/reports/kbar_return_report.html"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    context = build_kbar_context(args.source, interval_seconds=args.interval_seconds)
    write_kbar_report_html(context, args.output)
    print(f"wrote kbar return report to {args.output}")
    print(f"instrument_id={context.instrument_id}")
    print(f"interval_seconds={context.interval_seconds}")
    print(f"bars={len(context.bars)}")
    print(f"bar_return_mean={context.bar_return_stats.mean:.8f}")
    print(f"bar_return_stdev={context.bar_return_stats.stdev:.8f}")
    print(f"bar_return_p01={context.bar_return_stats.p01:.8f}")
    print(f"bar_return_p99={context.bar_return_stats.p99:.8f}")


if __name__ == "__main__":
    main()
