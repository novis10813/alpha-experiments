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
    flow_value: float
    trade_count: int
    horizon_seconds: int
    forward_return: float
    regime: str
    interpretation: str


@dataclass(frozen=True)
class RegimeSummary:
    regime: str
    interpretation: str
    horizon_seconds: int
    count: int
    mean_book_imbalance: float
    mean_flow_imbalance: float
    mean_forward_return: float
    median_forward_return: float
    positive_rate: float
    mean_directional_return: float
    directional_hit_rate: float


@dataclass(frozen=True)
class AbsorptionContext:
    alpha_source_path: Path
    feature_source_path: Path
    instrument_id: str
    alpha_name: str
    horizons_seconds: list[int]
    row_count: int
    joined_count: int
    book_threshold: float
    flow_threshold: float
    flow_column: str
    regime_summaries: list[RegimeSummary]


def build_absorption_context(
    alpha_path: Path,
    feature_path: Path,
    horizons_seconds: list[int] | None = None,
    book_threshold: float = 0.0,
    flow_threshold: float = 0.0,
    flow_column: str = "trade_imbalance",
) -> AbsorptionContext:
    horizons = horizons_seconds or [10, 30, 60]
    if not horizons:
        raise ValueError("horizons_seconds must not be empty")
    if flow_column not in {"trade_imbalance", "volume_imbalance"}:
        raise ValueError("flow_column must be trade_imbalance or volume_imbalance")

    alpha_points = read_alpha_points(alpha_path)
    if not alpha_points:
        raise RuntimeError(f"No alpha rows found in {alpha_path}")
    feature_points = read_trade_feature_points(feature_path, flow_column)
    if not feature_points:
        raise RuntimeError(f"No feature rows found in {feature_path}")
    _raise_if_feature_data_too_sparse(feature_points, min(horizons))

    joined_points = _joined_points(
        alpha_points,
        feature_points,
        horizons,
        book_threshold,
        flow_threshold,
    )
    first_horizon_count = sum(1 for point in joined_points if point.horizon_seconds == horizons[0])

    return AbsorptionContext(
        alpha_source_path=alpha_path,
        feature_source_path=feature_path,
        instrument_id=first_column_value(alpha_path, "instrument_id"),
        alpha_name=first_column_value(alpha_path, "alpha_name"),
        horizons_seconds=horizons,
        row_count=len(alpha_points),
        joined_count=first_horizon_count,
        book_threshold=book_threshold,
        flow_threshold=flow_threshold,
        flow_column=flow_column,
        regime_summaries=_regime_summaries(joined_points),
    )


def write_absorption_report_html(context: AbsorptionContext, output_path: Path) -> None:
    write_html_report(context, output_path, render_absorption_report_html)


def render_absorption_report_html(context: AbsorptionContext) -> str:
    title = "Signed Flow Absorption Report"
    payload = {
        "regimeSummaries": [_summary_payload(summary) for summary in context.regime_summaries],
        "horizonsSeconds": context.horizons_seconds,
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
    <div class="subtitle">{html.escape(context.instrument_id)} · flow: {html.escape(context.flow_column)} · horizons: {html.escape(", ".join(str(value) + "s" for value in context.horizons_seconds))}</div>
    <section class="stats" aria-label="Signed flow absorption summary">
      {_stat("Alpha rows", f"{context.row_count:,}")}
      {_stat("Joined rows", f"{context.joined_count:,}")}
      {_stat("Book threshold", f"{context.book_threshold:g}")}
      {_stat("Flow threshold", f"{context.flow_threshold:g}")}
      {_stat("Feature source", str(context.feature_source_path))}
    </section>
    <section class="chart">
      <div class="label">Mean directional return by regime</div>
      <div id="directional-return" class="plot"></div>
    </section>
    <section class="chart">
      <div class="label">Regime summary</div>
      <table>
        <thead>
          <tr>
            <th>regime</th>
            <th>interpretation</th>
            <th>horizon</th>
            <th>count</th>
            <th>mean book</th>
            <th>mean flow</th>
            <th>mean return</th>
            <th>positive</th>
            <th>directional return</th>
            <th>directional hit</th>
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
    const regimes = [...new Set(rows.map(row => row.regime))];
    Plotly.newPlot("directional-return", regimes.map(regime => {{
      const regimeRows = rows.filter(row => row.regime === regime);
      return {{
        name: regime,
        type: "bar",
        x: regimeRows.map(row => row.horizonSeconds),
        y: regimeRows.map(row => row.meanDirectionalReturn),
      }};
    }}), {{
      barmode: "group",
      margin: {{ l: 58, r: 18, t: 18, b: 54 }},
      paper_bgcolor: "#ffffff",
      plot_bgcolor: "#ffffff",
      font: {{ family: "ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif", color: "#18212f" }},
      xaxis: {{ title: "horizon seconds", gridcolor: "#edf0f4", zerolinecolor: "#8a94a6" }},
      yaxis: {{ title: "mean directional return", tickformat: ".3%", gridcolor: "#edf0f4", zerolinecolor: "#8a94a6" }},
    }}, plotConfig);
  </script>
</body>
</html>
"""


def _joined_points(
    alpha_points: list[AlphaPoint],
    feature_points: list[FeaturePoint],
    horizons_seconds: list[int],
    book_threshold: float,
    flow_threshold: float,
) -> list[JoinedPoint]:
    feature_times = [point.ts_event for point in feature_points]
    result: list[JoinedPoint] = []
    for alpha in alpha_points:
        current_index = index_at_or_before(feature_times, alpha.ts_event)
        if current_index < 0:
            continue
        feature = feature_points[current_index]
        if feature.price == 0:
            continue
        flow_value = feature.flow_value if feature.flow_value is not None else feature.trade_imbalance
        regime = _regime_for(alpha.value, flow_value, book_threshold, flow_threshold)
        if regime is None:
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
                    flow_value=flow_value,
                    trade_count=feature.trade_count,
                    horizon_seconds=horizon_seconds,
                    forward_return=(feature_points[future_index].price / feature.price) - 1,
                    regime=regime,
                    interpretation=_interpretation_for(regime),
                ),
            )
    return result


def _regime_for(
    book_value: float,
    flow_value: float,
    book_threshold: float,
    flow_threshold: float,
) -> str | None:
    if book_value >= book_threshold and flow_value > flow_threshold:
        return "bid_heavy_buy_flow"
    if book_value <= -book_threshold and flow_value < -flow_threshold:
        return "ask_heavy_sell_flow"
    if book_value >= book_threshold and flow_value < -flow_threshold:
        return "bid_heavy_sell_flow"
    if book_value <= -book_threshold and flow_value > flow_threshold:
        return "ask_heavy_buy_flow"
    return None


def _interpretation_for(regime: str) -> str:
    return {
        "bid_heavy_buy_flow": "confirmed_demand_pressure",
        "ask_heavy_sell_flow": "confirmed_supply_pressure",
        "bid_heavy_sell_flow": "bid_absorption",
        "ask_heavy_buy_flow": "ask_absorption",
    }[regime]


def _regime_summaries(points: list[JoinedPoint]) -> list[RegimeSummary]:
    summaries: list[RegimeSummary] = []
    horizons = sorted({point.horizon_seconds for point in points})
    regimes = [
        "bid_heavy_buy_flow",
        "ask_heavy_sell_flow",
        "bid_heavy_sell_flow",
        "ask_heavy_buy_flow",
    ]
    for horizon in horizons:
        horizon_points = [point for point in points if point.horizon_seconds == horizon]
        for regime in regimes:
            summaries.append(
                _summary_for(
                    regime,
                    horizon,
                    [point for point in horizon_points if point.regime == regime],
                ),
            )
    return summaries


def _summary_for(regime: str, horizon_seconds: int, points: list[JoinedPoint]) -> RegimeSummary:
    interpretation = _interpretation_for(regime)
    if not points:
        return RegimeSummary(
            regime=regime,
            interpretation=interpretation,
            horizon_seconds=horizon_seconds,
            count=0,
            mean_book_imbalance=0.0,
            mean_flow_imbalance=0.0,
            mean_forward_return=0.0,
            median_forward_return=0.0,
            positive_rate=0.0,
            mean_directional_return=0.0,
            directional_hit_rate=0.0,
        )

    returns = [point.forward_return for point in points]
    directional_returns = [_directional_return(point) for point in points]
    return RegimeSummary(
        regime=regime,
        interpretation=interpretation,
        horizon_seconds=horizon_seconds,
        count=len(points),
        mean_book_imbalance=sum(point.alpha_value for point in points) / len(points),
        mean_flow_imbalance=sum(point.flow_value for point in points) / len(points),
        mean_forward_return=sum(returns) / len(returns),
        median_forward_return=statistics.median(returns),
        positive_rate=sum(1 for value in returns if value > 0) / len(returns),
        mean_directional_return=sum(directional_returns) / len(directional_returns),
        directional_hit_rate=sum(1 for value in directional_returns if value > 0) / len(directional_returns),
    )


def _directional_return(point: JoinedPoint) -> float:
    if point.regime in {"bid_heavy_buy_flow", "bid_heavy_sell_flow"}:
        return point.forward_return
    return -point.forward_return


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
            "Feature data is too sparse for signed flow absorption diagnostics: "
            f"median gap is {median_gap_seconds:.3f}s but shortest horizon is "
            f"{shortest_horizon_seconds}s.",
        )


def _summary_payload(summary: RegimeSummary) -> dict[str, int | str | float]:
    return {
        "regime": summary.regime,
        "interpretation": summary.interpretation,
        "horizonSeconds": summary.horizon_seconds,
        "count": summary.count,
        "meanBookImbalance": summary.mean_book_imbalance,
        "meanFlowImbalance": summary.mean_flow_imbalance,
        "meanForwardReturn": summary.mean_forward_return,
        "medianForwardReturn": summary.median_forward_return,
        "positiveRate": summary.positive_rate,
        "meanDirectionalReturn": summary.mean_directional_return,
        "directionalHitRate": summary.directional_hit_rate,
    }


def _table_row(summary: RegimeSummary) -> str:
    return f"""<tr>
<td>{html.escape(summary.regime)}</td>
<td>{html.escape(summary.interpretation)}</td>
<td>{summary.horizon_seconds}s</td>
<td>{summary.count:,}</td>
<td>{summary.mean_book_imbalance:.4f}</td>
<td>{summary.mean_flow_imbalance:.4f}</td>
<td>{summary.mean_forward_return:.5%}</td>
<td>{summary.positive_rate:.2%}</td>
<td>{summary.mean_directional_return:.5%}</td>
<td>{summary.directional_hit_rate:.2%}</td>
</tr>"""


def _stat(label: str, value: str) -> str:
    return f"""<div class="stat"><div class="label">{html.escape(label)}</div><div class="value">{html.escape(value)}</div></div>"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render order book imbalance x signed flow diagnostics.")
    parser.add_argument("source", type=Path)
    parser.add_argument("--feature-source", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/reports/signed_flow_absorption_report.html"),
    )
    parser.add_argument("--horizons-seconds", type=int, nargs="+", default=[10, 30, 60])
    parser.add_argument("--book-threshold", type=float, default=0.0)
    parser.add_argument("--flow-threshold", type=float, default=0.0)
    parser.add_argument(
        "--flow-column",
        choices=["trade_imbalance", "volume_imbalance"],
        default="trade_imbalance",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    context = build_absorption_context(
        args.source,
        args.feature_source,
        horizons_seconds=args.horizons_seconds,
        book_threshold=args.book_threshold,
        flow_threshold=args.flow_threshold,
        flow_column=args.flow_column,
    )
    write_absorption_report_html(context, args.output)
    print(f"wrote signed flow absorption report to {args.output}")
    print(f"alpha_rows={context.row_count}")
    print(f"joined_rows={context.joined_count}")
    print(f"book_threshold={context.book_threshold:g}")
    print(f"flow_threshold={context.flow_threshold:g}")


if __name__ == "__main__":
    main()
