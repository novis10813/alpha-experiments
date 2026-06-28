from __future__ import annotations

import argparse
import html
import json
import statistics
from dataclasses import dataclass
from pathlib import Path

from common.csv_io import AlphaPoint
from common.csv_io import PricePoint
from common.csv_io import first_column_value
from common.csv_io import read_alpha_points
from common.csv_io import read_price_points
from common.time_series import NS_PER_SECOND
from common.time_series import index_at_or_after
from common.time_series import index_at_or_before
from reports.framework import write_html_report


@dataclass(frozen=True)
class ExtremeSummary:
    threshold: float
    side: str
    horizon_seconds: int
    count: int
    mean_alpha: float
    mean_forward_return: float
    median_forward_return: float
    mean_directional_return: float
    directional_hit_rate: float


@dataclass(frozen=True)
class ExtremeContext:
    alpha_source_path: Path
    price_source_path: Path
    instrument_id: str
    alpha_name: str
    thresholds: list[float]
    horizons_seconds: list[int]
    row_count: int
    summaries: list[ExtremeSummary]


def build_extreme_context(
    alpha_path: Path,
    price_path: Path,
    thresholds: list[float] | None = None,
    horizons_seconds: list[int] | None = None,
) -> ExtremeContext:
    threshold_values = thresholds or [0.95, 0.98]
    horizons = horizons_seconds or [1, 5, 10, 30, 60]
    if not threshold_values:
        raise ValueError("thresholds must not be empty")
    if not horizons:
        raise ValueError("horizons_seconds must not be empty")

    alpha_points = read_alpha_points(alpha_path)
    if not alpha_points:
        raise RuntimeError(f"No alpha rows found in {alpha_path}")

    price_points = read_price_points(price_path)
    if not price_points:
        raise RuntimeError(f"No price rows found in {price_path}")
    _raise_if_price_data_too_sparse(price_points, min(horizons))

    return ExtremeContext(
        alpha_source_path=alpha_path,
        price_source_path=price_path,
        instrument_id=first_column_value(alpha_path, "instrument_id"),
        alpha_name=first_column_value(alpha_path, "alpha_name"),
        thresholds=threshold_values,
        horizons_seconds=horizons,
        row_count=len(alpha_points),
        summaries=_extreme_summaries(alpha_points, price_points, threshold_values, horizons),
    )


def write_extreme_report_html(context: ExtremeContext, output_path: Path) -> None:
    write_html_report(context, output_path, render_extreme_report_html)


def render_extreme_report_html(context: ExtremeContext) -> str:
    title = "Extreme Imbalance Event Study"
    payload = {
        "summaryRows": [_summary_payload(summary) for summary in context.summaries],
        "thresholds": context.thresholds,
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
    th:first-child, td:first-child, th:nth-child(2), td:nth-child(2) {{
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
    <div class="subtitle">{html.escape(context.instrument_id)} · thresholds: {html.escape(", ".join(str(value) for value in context.thresholds))} · horizons: {html.escape(", ".join(str(value) + "s" for value in context.horizons_seconds))}</div>
    <section class="stats" aria-label="Extreme imbalance summary">
      {_stat("Alpha rows", f"{context.row_count:,}")}
      {_stat("Summary rows", f"{len(context.summaries):,}")}
      {_stat("Alpha source", str(context.alpha_source_path))}
      {_stat("Price source", str(context.price_source_path))}
    </section>
    <section class="chart">
      <div class="label">Mean directional return path</div>
      <div id="directional-path" class="plot"></div>
    </section>
    <section class="chart">
      <div class="label">Event summary</div>
      <table>
        <thead>
          <tr>
            <th>side</th>
            <th>threshold</th>
            <th>horizon</th>
            <th>count</th>
            <th>mean alpha</th>
            <th>mean return</th>
            <th>median return</th>
            <th>mean directional return</th>
            <th>directional hit rate</th>
          </tr>
        </thead>
        <tbody>
          {rows_html}
        </tbody>
      </table>
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
      xaxis: {{ gridcolor: "#edf0f4", zerolinecolor: "#8a94a6", title: "horizon seconds" }},
      yaxis: {{ gridcolor: "#edf0f4", zerolinecolor: "#8a94a6", title: "mean directional return", tickformat: ".3%" }},
      hovermode: "x unified",
    }};
    function drawDirectionalPath() {{
      const traces = [];
      for (const threshold of reportData.thresholds) {{
        for (const side of ["positive", "negative"]) {{
          const rows = reportData.summaryRows.filter(row => row.threshold === threshold && row.side === side);
          traces.push({{
            name: `${{side}} >= ${{threshold}}`,
            type: "scatter",
            mode: "lines+markers",
            x: rows.map(row => row.horizonSeconds),
            y: rows.map(row => row.meanDirectionalReturn),
            customdata: rows.map(row => [row.count, row.directionalHitRate]),
            hovertemplate: "horizon=%{{x}}s<br>mean directional=%{{y:.4%}}<br>count=%{{customdata[0]}}<br>hit=%{{customdata[1]:.2%}}<extra></extra>",
          }});
        }}
      }}
      Plotly.newPlot("directional-path", traces, commonLayout, plotConfig);
    }}
    drawDirectionalPath();
  </script>
</body>
</html>
"""


def _extreme_summaries(
    alpha_points: list[AlphaPoint],
    price_points: list[PricePoint],
    thresholds: list[float],
    horizons_seconds: list[int],
) -> list[ExtremeSummary]:
    price_times = [point.ts_event for point in price_points]
    summaries: list[ExtremeSummary] = []
    for threshold in thresholds:
        for side in ["positive", "negative"]:
            events = [
                point
                for point in alpha_points
                if (point.value >= threshold if side == "positive" else point.value <= -threshold)
            ]
            for horizon_seconds in horizons_seconds:
                returns = _event_returns(events, price_points, price_times, horizon_seconds)
                summaries.append(
                    _summary_for(
                        threshold=threshold,
                        side=side,
                        horizon_seconds=horizon_seconds,
                        events=events,
                        returns=returns,
                    ),
                )
    return summaries


def _event_returns(
    events: list[AlphaPoint],
    price_points: list[PricePoint],
    price_times: list[int],
    horizon_seconds: int,
) -> list[float]:
    returns: list[float] = []
    for event in events:
        current_price = _price_at_or_before(event.ts_event, price_points, price_times)
        future_price = _price_at_or_after(
            event.ts_event + horizon_seconds * NS_PER_SECOND,
            price_points,
            price_times,
        )
        if current_price is None or future_price is None or current_price == 0:
            continue
        returns.append((future_price / current_price) - 1)
    return returns


def _summary_for(
    threshold: float,
    side: str,
    horizon_seconds: int,
    events: list[AlphaPoint],
    returns: list[float],
) -> ExtremeSummary:
    if not returns:
        return ExtremeSummary(
            threshold=threshold,
            side=side,
            horizon_seconds=horizon_seconds,
            count=0,
            mean_alpha=0.0,
            mean_forward_return=0.0,
            median_forward_return=0.0,
            mean_directional_return=0.0,
            directional_hit_rate=0.0,
        )

    sign = 1 if side == "positive" else -1
    directional_returns = [sign * value for value in returns]
    return ExtremeSummary(
        threshold=threshold,
        side=side,
        horizon_seconds=horizon_seconds,
        count=len(returns),
        mean_alpha=sum(event.value for event in events) / len(events),
        mean_forward_return=sum(returns) / len(returns),
        median_forward_return=statistics.median(returns),
        mean_directional_return=sum(directional_returns) / len(directional_returns),
        directional_hit_rate=sum(1 for value in directional_returns if value > 0) / len(directional_returns),
    )


def _price_at_or_before(
    ts_event: int,
    price_points: list[PricePoint],
    price_times: list[int],
) -> float | None:
    index = index_at_or_before(price_times, ts_event)
    if index < 0:
        return None
    return price_points[index].price


def _price_at_or_after(
    ts_event: int,
    price_points: list[PricePoint],
    price_times: list[int],
) -> float | None:
    index = index_at_or_after(price_times, ts_event)
    if index >= len(price_points):
        return None
    return price_points[index].price


def _raise_if_price_data_too_sparse(price_points: list[PricePoint], shortest_horizon_seconds: int) -> None:
    if len(price_points) < 2:
        raise RuntimeError("Price data is too sparse: at least two price rows are required")

    gaps_seconds = [
        (current.ts_event - previous.ts_event) / NS_PER_SECOND
        for previous, current in zip(price_points, price_points[1:])
    ]
    median_gap_seconds = statistics.median(gaps_seconds)
    if median_gap_seconds > shortest_horizon_seconds * 2:
        raise RuntimeError(
            "Price data is too sparse for extreme imbalance diagnostics: "
            f"median price gap is {median_gap_seconds:.3f}s but shortest horizon is "
            f"{shortest_horizon_seconds}s.",
        )


def _summary_payload(summary: ExtremeSummary) -> dict[str, int | str | float]:
    return {
        "threshold": summary.threshold,
        "side": summary.side,
        "horizonSeconds": summary.horizon_seconds,
        "count": summary.count,
        "meanAlpha": summary.mean_alpha,
        "meanForwardReturn": summary.mean_forward_return,
        "medianForwardReturn": summary.median_forward_return,
        "meanDirectionalReturn": summary.mean_directional_return,
        "directionalHitRate": summary.directional_hit_rate,
    }


def _table_row(summary: ExtremeSummary) -> str:
    return f"""<tr>
<td>{html.escape(summary.side)}</td>
<td>{summary.threshold:.3f}</td>
<td>{summary.horizon_seconds}s</td>
<td>{summary.count:,}</td>
<td>{summary.mean_alpha:.6f}</td>
<td>{summary.mean_forward_return:.5%}</td>
<td>{summary.median_forward_return:.5%}</td>
<td>{summary.mean_directional_return:.5%}</td>
<td>{summary.directional_hit_rate:.2%}</td>
</tr>"""


def _stat(label: str, value: str) -> str:
    return f"""<div class="stat"><div class="label">{html.escape(label)}</div><div class="value">{html.escape(value)}</div></div>"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render extreme imbalance event-study diagnostics as HTML.")
    parser.add_argument("source", type=Path)
    parser.add_argument("--price-source", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/reports/extreme_imbalance_report.html"),
    )
    parser.add_argument("--thresholds", type=float, nargs="+", default=[0.95, 0.98])
    parser.add_argument("--horizons-seconds", type=int, nargs="+", default=[1, 5, 10, 30, 60])
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    context = build_extreme_context(
        args.source,
        args.price_source,
        thresholds=args.thresholds,
        horizons_seconds=args.horizons_seconds,
    )
    write_extreme_report_html(context, args.output)
    print(f"wrote extreme imbalance report to {args.output}")
    print(f"alpha_rows={context.row_count}")
    print(f"summary_rows={len(context.summaries)}")


if __name__ == "__main__":
    main()
