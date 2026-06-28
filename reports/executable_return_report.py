from __future__ import annotations

import argparse
import bisect
import csv
import html
import json
import statistics
from dataclasses import dataclass
from dataclasses import field
from datetime import UTC
from datetime import datetime
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
class ExecutableReturnPoint:
    ts_event: int
    timestamp: str
    alpha_value: float
    side: int
    horizon_seconds: int
    delay_seconds: int
    cost_bps: float
    entry_ts_event: int
    exit_ts_event: int
    entry_price: float
    exit_price: float
    entry_spread_bps: float
    gross_return: float
    net_return: float


@dataclass(frozen=True)
class ExecutableSummary:
    horizon_seconds: int
    delay_seconds: int
    cost_bps: float
    count: int
    mean_gross_return: float
    mean_net_return: float
    median_net_return: float
    hit_rate: float
    mean_entry_spread_bps: float


@dataclass(frozen=True)
class ExecutableReturnContext:
    alpha_source_path: Path
    quote_source_path: Path
    instrument_id: str
    alpha_name: str
    row_count: int
    horizons_seconds: list[int]
    delay_seconds: list[int]
    cost_bps: list[float]
    points: list[ExecutableReturnPoint]
    summaries: list[ExecutableSummary]


@dataclass
class _SummaryAccumulator:
    count: int = 0
    gross_sum: float = 0.0
    net_sum: float = 0.0
    hit_count: int = 0
    spread_sum: float = 0.0
    net_returns: list[float] = field(default_factory=list)


def build_executable_return_context(
    alpha_path: Path,
    quote_path: Path,
    horizons_seconds: list[int] | None = None,
    delay_seconds: list[int] | None = None,
    cost_bps: list[float] | None = None,
    max_points: int = 5000,
) -> ExecutableReturnContext:
    horizons = horizons_seconds or [10, 30, 60]
    delays = delay_seconds or [0]
    costs = cost_bps or [0]
    if not horizons:
        raise ValueError("horizons_seconds must not be empty")
    if not delays:
        raise ValueError("delay_seconds must not be empty")
    if not costs:
        raise ValueError("cost_bps must not be empty")
    if any(value < 0 for value in horizons):
        raise ValueError("horizons_seconds must be non-negative")
    if any(value < 0 for value in delays):
        raise ValueError("delay_seconds must be non-negative")
    if any(value < 0 for value in costs):
        raise ValueError("cost_bps must be non-negative")
    if max_points <= 0:
        raise ValueError("max_points must be positive")

    alpha_points = _read_alpha_points(alpha_path)
    if not alpha_points:
        raise RuntimeError(f"No alpha rows found in {alpha_path}")
    quote_points = _read_quote_points(quote_path)
    if not quote_points:
        raise RuntimeError(f"No quote rows found in {quote_path}")

    points, summaries = _points_and_summaries(
        alpha_points,
        quote_points,
        horizons,
        delays,
        costs,
        max_points,
    )
    return ExecutableReturnContext(
        alpha_source_path=alpha_path,
        quote_source_path=quote_path,
        instrument_id=_first_column_value(alpha_path, "instrument_id"),
        alpha_name=_first_column_value(alpha_path, "alpha_name"),
        row_count=len(alpha_points),
        horizons_seconds=horizons,
        delay_seconds=delays,
        cost_bps=costs,
        points=points,
        summaries=summaries,
    )


def write_executable_return_report_html(
    context: ExecutableReturnContext,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_executable_return_report_html(context), encoding="utf-8")


def render_executable_return_report_html(context: ExecutableReturnContext) -> str:
    title = "Executable Return Screen"
    payload = {"summaries": [_summary_payload(summary) for summary in context.summaries]}
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
    body {{
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #18212f;
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
      color: #667085;
      font-size: 14px;
      margin-bottom: 20px;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 10px;
      margin-bottom: 18px;
    }}
    .stat, .chart {{
      background: #f7f8fa;
      border: 1px solid #d7dce3;
      border-radius: 8px;
      padding: 10px 12px;
    }}
    .chart {{
      margin-top: 12px;
    }}
    .label {{
      color: #667085;
      font-size: 12px;
      margin-bottom: 4px;
    }}
    .value {{
      font-size: 16px;
      font-variant-numeric: tabular-nums;
      overflow-wrap: anywhere;
    }}
    .plot {{
      width: 100%;
      height: 380px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
      font-variant-numeric: tabular-nums;
    }}
    th, td {{
      border-bottom: 1px solid #d7dce3;
      padding: 6px 7px;
      text-align: right;
      white-space: nowrap;
    }}
    th:first-child, td:first-child {{
      text-align: left;
    }}
    th {{
      color: #667085;
      font-weight: 600;
    }}
  </style>
</head>
<body>
  <main>
    <h1>{html.escape(title)}</h1>
    <div class="subtitle">{html.escape(context.instrument_id)} · bid/ask execution by alpha sign</div>
    <section class="stats">
      {_stat("Alpha rows", f"{context.row_count:,}")}
      {_stat("Executable points", f"{len(context.points):,}")}
      {_stat("Horizons", ", ".join(str(value) + "s" for value in context.horizons_seconds))}
      {_stat("Delays", ", ".join(str(value) + "s" for value in context.delay_seconds))}
      {_stat("Costs", ", ".join(str(value) + " bps" for value in context.cost_bps))}
      {_stat("Quote source", str(context.quote_source_path))}
    </section>
    <section class="chart">
      <div class="label">mean net executable return</div>
      <div id="net-return" class="plot"></div>
    </section>
    <section class="chart">
      <div class="label">summary table</div>
      <table>
        <thead>
          <tr>
            <th>setting</th>
            <th>count</th>
            <th>gross avg</th>
            <th>net avg</th>
            <th>net median</th>
            <th>hit</th>
            <th>entry spread bps</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
    </section>
  </main>
  <script>
    const reportData = {payload_json};
    const rows = reportData.summaries;
    Plotly.newPlot("net-return", [{{
      name: "net executable return",
      type: "bar",
      x: rows.map(row => `${{row.horizonSeconds}}s / delay ${{row.delaySeconds}}s / ${{row.costBps}}bps`),
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


def _points_and_summaries(
    alpha_points: list[AlphaPoint],
    quote_points: list[QuotePoint],
    horizons_seconds: list[int],
    delay_seconds: list[int],
    cost_bps: list[float],
    max_points: int,
) -> tuple[list[ExecutableReturnPoint], list[ExecutableSummary]]:
    quote_times = [point.ts_event for point in quote_points]
    sampled_points: list[ExecutableReturnPoint] = []
    accumulators = {
        (horizon, delay, cost): _SummaryAccumulator()
        for horizon in horizons_seconds
        for delay in delay_seconds
        for cost in cost_bps
    }
    for alpha in alpha_points:
        side = _sign(alpha.value)
        for delay in delay_seconds:
            entry_time = alpha.ts_event + delay * 1_000_000_000
            entry_index = bisect.bisect_left(quote_times, entry_time)
            if entry_index >= len(quote_points):
                continue
            entry_quote = quote_points[entry_index]
            for horizon in horizons_seconds:
                exit_time = entry_quote.ts_event + horizon * 1_000_000_000
                exit_index = bisect.bisect_left(quote_times, exit_time)
                if exit_index >= len(quote_points):
                    continue
                exit_quote = quote_points[exit_index]
                entry_price, exit_price, gross_return = _trade_prices_and_return(
                    side,
                    entry_quote,
                    exit_quote,
                )
                if len(sampled_points) < max_points:
                    sampled_points.append(
                        ExecutableReturnPoint(
                            ts_event=alpha.ts_event,
                            timestamp=_format_utc(alpha.ts_event),
                            alpha_value=alpha.value,
                            side=side,
                            horizon_seconds=horizon,
                            delay_seconds=delay,
                            cost_bps=cost_bps[0],
                            entry_ts_event=entry_quote.ts_event,
                            exit_ts_event=exit_quote.ts_event,
                            entry_price=entry_price,
                            exit_price=exit_price,
                            entry_spread_bps=entry_quote.spread_bps,
                            gross_return=gross_return,
                            net_return=gross_return - cost_bps[0] / 10_000,
                        ),
                    )
                for cost in cost_bps:
                    _add_to_accumulator(
                        accumulators[(horizon, delay, cost)],
                        gross_return,
                        entry_quote.spread_bps,
                        cost,
                    )
    summaries = [
        _summary_from_accumulator(horizon, delay, cost, accumulators[(horizon, delay, cost)])
        for horizon in horizons_seconds
        for delay in delay_seconds
        for cost in cost_bps
    ]
    return sampled_points, summaries


def _add_to_accumulator(
    accumulator: _SummaryAccumulator,
    gross_return: float,
    entry_spread_bps: float,
    cost_bps: float,
) -> None:
    net_return = gross_return - cost_bps / 10_000
    accumulator.count += 1
    accumulator.gross_sum += gross_return
    accumulator.net_sum += net_return
    accumulator.spread_sum += entry_spread_bps
    accumulator.net_returns.append(net_return)
    if net_return > 0:
        accumulator.hit_count += 1


def _summary_from_accumulator(
    horizon_seconds: int,
    delay_seconds: int,
    cost_bps: float,
    accumulator: _SummaryAccumulator,
) -> ExecutableSummary:
    if accumulator.count == 0:
        return ExecutableSummary(
            horizon_seconds=horizon_seconds,
            delay_seconds=delay_seconds,
            cost_bps=cost_bps,
            count=0,
            mean_gross_return=0.0,
            mean_net_return=0.0,
            median_net_return=0.0,
            hit_rate=0.0,
            mean_entry_spread_bps=0.0,
        )
    return ExecutableSummary(
        horizon_seconds=horizon_seconds,
        delay_seconds=delay_seconds,
        cost_bps=cost_bps,
        count=accumulator.count,
        mean_gross_return=accumulator.gross_sum / accumulator.count,
        mean_net_return=accumulator.net_sum / accumulator.count,
        median_net_return=statistics.median(accumulator.net_returns),
        hit_rate=accumulator.hit_count / accumulator.count,
        mean_entry_spread_bps=accumulator.spread_sum / accumulator.count,
    )


def _trade_prices_and_return(
    side: int,
    entry_quote: QuotePoint,
    exit_quote: QuotePoint,
) -> tuple[float, float, float]:
    if side > 0:
        entry_price = entry_quote.ask
        exit_price = exit_quote.bid
        return entry_price, exit_price, (exit_price / entry_price) - 1
    if side < 0:
        entry_price = entry_quote.bid
        exit_price = exit_quote.ask
        return entry_price, exit_price, (entry_price / exit_price) - 1
    return entry_quote.mid, exit_quote.mid, 0.0


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


def _format_utc(ts_event: int) -> str:
    return datetime.fromtimestamp(ts_event / 1_000_000_000, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _summary_payload(summary: ExecutableSummary) -> dict[str, int | float]:
    return {
        "horizonSeconds": summary.horizon_seconds,
        "delaySeconds": summary.delay_seconds,
        "costBps": summary.cost_bps,
        "count": summary.count,
        "meanGrossReturn": summary.mean_gross_return,
        "meanNetReturn": summary.mean_net_return,
        "medianNetReturn": summary.median_net_return,
        "hitRate": summary.hit_rate,
        "meanEntrySpreadBps": summary.mean_entry_spread_bps,
    }


def _table_row(summary: ExecutableSummary) -> str:
    setting = (
        f"{summary.horizon_seconds}s / "
        f"delay {summary.delay_seconds}s / "
        f"{summary.cost_bps:g} bps"
    )
    return f"""<tr>
<td>{html.escape(setting)}</td>
<td>{summary.count:,}</td>
<td>{summary.mean_gross_return:.5%}</td>
<td>{summary.mean_net_return:.5%}</td>
<td>{summary.median_net_return:.5%}</td>
<td>{summary.hit_rate:.2%}</td>
<td>{summary.mean_entry_spread_bps:.3f}</td>
</tr>"""


def _stat(label: str, value: str) -> str:
    return f"""<div class="stat"><div class="label">{html.escape(label)}</div><div class="value">{html.escape(value)}</div></div>"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render quote-executable return diagnostics.")
    parser.add_argument("source", type=Path)
    parser.add_argument("--quote-source", type=Path, required=True)
    parser.add_argument("--horizons-seconds", type=int, nargs="+", default=[10, 30, 60])
    parser.add_argument("--delay-seconds", type=int, nargs="+", default=[0])
    parser.add_argument("--cost-bps", type=float, nargs="+", default=[0])
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/reports/executable_return_report.html"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    context = build_executable_return_context(
        args.source,
        args.quote_source,
        horizons_seconds=args.horizons_seconds,
        delay_seconds=args.delay_seconds,
        cost_bps=args.cost_bps,
    )
    write_executable_return_report_html(context, args.output)
    print(f"wrote executable return report to {args.output}")
    print(f"instrument_id={context.instrument_id}")
    print(f"alpha_rows={context.row_count}")
    for summary in context.summaries:
        print(
            "summary "
            f"horizon={summary.horizon_seconds}s "
            f"delay={summary.delay_seconds}s "
            f"cost={summary.cost_bps:g}bps "
            f"count={summary.count} "
            f"gross={summary.mean_gross_return:.8f} "
            f"net={summary.mean_net_return:.8f} "
            f"hit={summary.hit_rate:.6f}",
        )


if __name__ == "__main__":
    main()
