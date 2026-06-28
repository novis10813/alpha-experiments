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
    alpha_value: float
    flow_value: float
    trade_count: int
    density_regime: str
    flow_regime: str
    interpretation: str
    horizon_seconds: int
    forward_return: float


@dataclass(frozen=True)
class DenseFlowSummary:
    density_regime: str
    flow_regime: str
    interpretation: str
    horizon_seconds: int
    count: int
    mean_trade_count: float
    mean_book_imbalance: float
    mean_flow_imbalance: float
    mean_forward_return: float
    mean_directional_return: float
    directional_hit_rate: float


@dataclass(frozen=True)
class DenseSignedFlowContext:
    alpha_source_path: Path
    feature_source_path: Path
    instrument_id: str
    alpha_name: str
    horizons_seconds: list[int]
    row_count: int
    joined_count: int
    density_threshold: float
    book_threshold: float
    flow_threshold: float
    flow_column: str
    summaries: list[DenseFlowSummary]


def build_dense_signed_flow_context(
    alpha_path: Path,
    feature_path: Path,
    horizons_seconds: list[int] | None = None,
    book_threshold: float = 0.0,
    flow_threshold: float = 0.0,
    flow_column: str = "trade_imbalance",
) -> DenseSignedFlowContext:
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
    first_horizon_points = [point for point in joined_points if point.horizon_seconds == horizons[0]]
    if not first_horizon_points:
        raise RuntimeError("No joined rows available for dense signed flow diagnostics")
    density_threshold = statistics.median([point.trade_count for point in first_horizon_points])
    joined_points = [
        JoinedPoint(
            alpha_value=point.alpha_value,
            flow_value=point.flow_value,
            trade_count=point.trade_count,
            density_regime=_density_regime(point.trade_count, density_threshold),
            flow_regime=point.flow_regime,
            interpretation=point.interpretation,
            horizon_seconds=point.horizon_seconds,
            forward_return=point.forward_return,
        )
        for point in joined_points
    ]

    return DenseSignedFlowContext(
        alpha_source_path=alpha_path,
        feature_source_path=feature_path,
        instrument_id=first_column_value(alpha_path, "instrument_id"),
        alpha_name=first_column_value(alpha_path, "alpha_name"),
        horizons_seconds=horizons,
        row_count=len(alpha_points),
        joined_count=len(first_horizon_points),
        density_threshold=density_threshold,
        book_threshold=book_threshold,
        flow_threshold=flow_threshold,
        flow_column=flow_column,
        summaries=_summaries(joined_points),
    )


def write_dense_signed_flow_report_html(
    context: DenseSignedFlowContext,
    output_path: Path,
) -> None:
    write_html_report(context, output_path, render_dense_signed_flow_report_html)


def render_dense_signed_flow_report_html(context: DenseSignedFlowContext) -> str:
    title = "Dense Signed Flow Report"
    payload = {"denseFlowSummaries": [_summary_payload(summary) for summary in context.summaries]}
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
    th:first-child, td:first-child, th:nth-child(2), td:nth-child(2), th:nth-child(3), td:nth-child(3) {{ text-align: left; }}
    th {{ color: #667085; font-weight: 600; }}
  </style>
</head>
<body>
  <main>
    <h1>{html.escape(title)}</h1>
    <div class="subtitle">{html.escape(context.instrument_id)} · flow: {html.escape(context.flow_column)} · density threshold {context.density_threshold:g} trades/sec</div>
    <section class="stats">
      {_stat("Alpha rows", f"{context.row_count:,}")}
      {_stat("Joined rows", f"{context.joined_count:,}")}
      {_stat("Density threshold", f"{context.density_threshold:g}")}
      {_stat("Book threshold", f"{context.book_threshold:g}")}
      {_stat("Flow threshold", f"{context.flow_threshold:g}")}
    </section>
    <section class="chart">
      <div class="label">directional return by density and flow regime</div>
      <div id="dense-flow-return" class="plot"></div>
    </section>
    <section class="chart">
      <div class="label">summary table</div>
      <table>
        <thead>
          <tr>
            <th>density</th><th>flow regime</th><th>interpretation</th><th>horizon</th><th>count</th><th>trade count</th><th>book</th><th>flow</th><th>mean return</th><th>directional return</th><th>directional hit</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
    </section>
  </main>
  <script>
    const reportData = {payload_json};
    const rows = reportData.denseFlowSummaries;
    const groups = [...new Set(rows.map(row => `${{row.densityRegime}} / ${{row.flowRegime}}`))];
    Plotly.newPlot("dense-flow-return", groups.map(group => {{
      const groupRows = rows.filter(row => `${{row.densityRegime}} / ${{row.flowRegime}}` === group);
      return {{
        name: group,
        type: "bar",
        x: groupRows.map(row => row.horizonSeconds),
        y: groupRows.map(row => row.meanDirectionalReturn),
      }};
    }}), {{
      barmode: "group",
      margin: {{ l: 58, r: 18, t: 18, b: 54 }},
      paper_bgcolor: "#ffffff",
      plot_bgcolor: "#ffffff",
      font: {{ family: "ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif", color: "#18212f" }},
      xaxis: {{ title: "horizon seconds", gridcolor: "#edf0f4", zerolinecolor: "#8a94a6" }},
      yaxis: {{ title: "mean directional return", tickformat: ".3%", gridcolor: "#edf0f4", zerolinecolor: "#8a94a6" }},
    }}, {{ responsive: true, displaylogo: false }});
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
        flow_regime = _flow_regime_for(alpha.value, flow_value, book_threshold, flow_threshold)
        if flow_regime is None:
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
                    alpha_value=alpha.value,
                    flow_value=flow_value,
                    trade_count=feature.trade_count,
                    density_regime="",
                    flow_regime=flow_regime,
                    interpretation=_interpretation_for(flow_regime),
                    horizon_seconds=horizon_seconds,
                    forward_return=(feature_points[future_index].price / feature.price) - 1,
                ),
            )
    return result


def _flow_regime_for(
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


def _density_regime(trade_count: int, threshold: float) -> str:
    if trade_count < threshold:
        return "density_low"
    return "density_high"


def _summaries(points: list[JoinedPoint]) -> list[DenseFlowSummary]:
    summaries: list[DenseFlowSummary] = []
    horizons = sorted({point.horizon_seconds for point in points})
    density_regimes = ["density_low", "density_high"]
    flow_regimes = [
        "bid_heavy_buy_flow",
        "ask_heavy_sell_flow",
        "bid_heavy_sell_flow",
        "ask_heavy_buy_flow",
    ]
    for horizon in horizons:
        horizon_points = [point for point in points if point.horizon_seconds == horizon]
        for density_regime in density_regimes:
            density_points = [
                point for point in horizon_points if point.density_regime == density_regime
            ]
            for flow_regime in flow_regimes:
                summaries.append(
                    _summary_for(
                        density_regime,
                        flow_regime,
                        horizon,
                        [point for point in density_points if point.flow_regime == flow_regime],
                    ),
                )
    return summaries


def _summary_for(
    density_regime: str,
    flow_regime: str,
    horizon_seconds: int,
    points: list[JoinedPoint],
) -> DenseFlowSummary:
    interpretation = _interpretation_for(flow_regime)
    if not points:
        return DenseFlowSummary(
            density_regime=density_regime,
            flow_regime=flow_regime,
            interpretation=interpretation,
            horizon_seconds=horizon_seconds,
            count=0,
            mean_trade_count=0.0,
            mean_book_imbalance=0.0,
            mean_flow_imbalance=0.0,
            mean_forward_return=0.0,
            mean_directional_return=0.0,
            directional_hit_rate=0.0,
        )
    directional_returns = [_directional_return(point) for point in points]
    return DenseFlowSummary(
        density_regime=density_regime,
        flow_regime=flow_regime,
        interpretation=interpretation,
        horizon_seconds=horizon_seconds,
        count=len(points),
        mean_trade_count=sum(point.trade_count for point in points) / len(points),
        mean_book_imbalance=sum(point.alpha_value for point in points) / len(points),
        mean_flow_imbalance=sum(point.flow_value for point in points) / len(points),
        mean_forward_return=sum(point.forward_return for point in points) / len(points),
        mean_directional_return=sum(directional_returns) / len(directional_returns),
        directional_hit_rate=sum(1 for value in directional_returns if value > 0)
        / len(directional_returns),
    )


def _directional_return(point: JoinedPoint) -> float:
    if point.flow_regime in {"bid_heavy_buy_flow", "bid_heavy_sell_flow"}:
        return point.forward_return
    return -point.forward_return


def _raise_if_feature_data_too_sparse(
    feature_points: list[FeaturePoint],
    shortest_horizon_seconds: int,
) -> None:
    if len(feature_points) < 2:
        raise RuntimeError("Feature data is too sparse: at least two rows are required")
    gaps_seconds = [
        (current.ts_event - previous.ts_event) / NS_PER_SECOND
        for previous, current in zip(feature_points, feature_points[1:])
    ]
    median_gap_seconds = statistics.median(gaps_seconds)
    if median_gap_seconds > shortest_horizon_seconds * 2:
        raise RuntimeError(
            "Feature data is too sparse for dense signed flow diagnostics: "
            f"median gap is {median_gap_seconds:.3f}s but shortest horizon is "
            f"{shortest_horizon_seconds}s.",
        )


def _summary_payload(summary: DenseFlowSummary) -> dict[str, int | str | float]:
    return {
        "densityRegime": summary.density_regime,
        "flowRegime": summary.flow_regime,
        "interpretation": summary.interpretation,
        "horizonSeconds": summary.horizon_seconds,
        "count": summary.count,
        "meanTradeCount": summary.mean_trade_count,
        "meanBookImbalance": summary.mean_book_imbalance,
        "meanFlowImbalance": summary.mean_flow_imbalance,
        "meanForwardReturn": summary.mean_forward_return,
        "meanDirectionalReturn": summary.mean_directional_return,
        "directionalHitRate": summary.directional_hit_rate,
    }


def _table_row(summary: DenseFlowSummary) -> str:
    return f"""<tr>
<td>{html.escape(summary.density_regime)}</td>
<td>{html.escape(summary.flow_regime)}</td>
<td>{html.escape(summary.interpretation)}</td>
<td>{summary.horizon_seconds}s</td>
<td>{summary.count:,}</td>
<td>{summary.mean_trade_count:.2f}</td>
<td>{summary.mean_book_imbalance:.4f}</td>
<td>{summary.mean_flow_imbalance:.4f}</td>
<td>{summary.mean_forward_return:.5%}</td>
<td>{summary.mean_directional_return:.5%}</td>
<td>{summary.directional_hit_rate:.2%}</td>
</tr>"""


def _stat(label: str, value: str) -> str:
    return f"""<div class="stat"><div class="label">{html.escape(label)}</div><div class="value">{html.escape(value)}</div></div>"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render signed flow diagnostics split by trade density.")
    parser.add_argument("source", type=Path)
    parser.add_argument("--feature-source", type=Path, required=True)
    parser.add_argument("--horizons-seconds", type=int, nargs="+", default=[10, 30, 60])
    parser.add_argument("--book-threshold", type=float, default=0.0)
    parser.add_argument("--flow-threshold", type=float, default=0.0)
    parser.add_argument(
        "--flow-column",
        choices=["trade_imbalance", "volume_imbalance"],
        default="trade_imbalance",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/reports/dense_signed_flow_report.html"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    context = build_dense_signed_flow_context(
        args.source,
        args.feature_source,
        horizons_seconds=args.horizons_seconds,
        book_threshold=args.book_threshold,
        flow_threshold=args.flow_threshold,
        flow_column=args.flow_column,
    )
    write_dense_signed_flow_report_html(context, args.output)
    print(f"wrote dense signed flow report to {args.output}")
    print(f"instrument_id={context.instrument_id}")
    print(f"alpha_rows={context.row_count}")
    print(f"joined_rows={context.joined_count}")
    print(f"density_threshold={context.density_threshold:g}")
    print(f"flow_column={context.flow_column}")
    for summary in context.summaries:
        print(
            "summary "
            f"density={summary.density_regime} "
            f"flow={summary.flow_regime} "
            f"horizon={summary.horizon_seconds}s "
            f"count={summary.count} "
            f"directional={summary.mean_directional_return:.8f} "
            f"hit={summary.directional_hit_rate:.6f}",
        )


if __name__ == "__main__":
    main()
