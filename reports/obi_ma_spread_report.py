from __future__ import annotations

import argparse
import bisect
import csv
import html
import json
import statistics
from dataclasses import dataclass
from pathlib import Path


NS_PER_MINUTE = 60 * 1_000_000_000
GROUPS = ("spread_positive", "spread_positive_short_positive")


@dataclass(frozen=True)
class KbarObiRow:
    ts_event: int
    instrument_id: str
    open: float
    high: float
    low: float
    close: float
    orderbook_imbalance_mean: float


@dataclass(frozen=True)
class ObiMaSignal:
    ts_event: int
    trigger_index: int
    short_mean: float
    long_mean: float
    spread: float
    close: float


@dataclass(frozen=True)
class ScreenSummary:
    group: str
    horizon_minutes: int
    cooldown_minutes: int
    cost_bps: float
    count: int
    mean_gross_return: float
    mean_net_return: float
    median_net_return: float
    hit_rate: float
    p05_net_return: float
    p95_net_return: float


@dataclass(frozen=True)
class ObiMaSpreadContext:
    source_path: Path
    instrument_id: str
    bar_count: int
    signal_count: int
    short_window: int
    long_window: int
    event_counts: dict[str, int]
    cooldown_event_counts: dict[str, dict[int, int]]
    signals: list[ObiMaSignal]
    summaries: list[ScreenSummary]


def build_obi_ma_spread_context(
    source_path: Path,
    short_window: int = 5,
    long_window: int = 15,
    horizons_minutes: list[int] | None = None,
    cooldown_minutes: list[int] | None = None,
    cost_bps: list[float] | None = None,
) -> ObiMaSpreadContext:
    horizons = horizons_minutes if horizons_minutes is not None else [1, 3, 5, 10, 15, 30]
    cooldowns = cooldown_minutes if cooldown_minutes is not None else [0, 5, 15]
    costs = cost_bps if cost_bps is not None else [0, 2, 5, 10]
    if short_window <= 0 or long_window <= 0:
        raise ValueError("short_window and long_window must be positive")
    if short_window >= long_window:
        raise ValueError("short_window must be less than long_window")
    if not horizons:
        raise ValueError("horizons_minutes must not be empty")
    if any(value <= 0 for value in horizons):
        raise ValueError("horizons_minutes must be positive")
    if any(value < 0 for value in cooldowns):
        raise ValueError("cooldown_minutes must be non-negative")
    if any(value < 0 for value in costs):
        raise ValueError("cost_bps must be non-negative")

    rows = _read_rows(source_path)
    if not rows:
        raise RuntimeError(f"No kbar order book imbalance rows found in {source_path}")
    instrument_ids = {row.instrument_id for row in rows}
    if len(instrument_ids) != 1:
        raise ValueError("OBI MA spread report requires exactly one instrument_id")

    signals = _obi_ma_signals(rows, short_window, long_window)
    events_by_group = _events_by_group(signals)
    summaries: list[ScreenSummary] = []
    cooldown_event_counts: dict[str, dict[int, int]] = {group: {} for group in GROUPS}
    for group in GROUPS:
        for cooldown in cooldowns:
            selected_events = _apply_cooldown(events_by_group[group], cooldown)
            cooldown_event_counts[group][cooldown] = len(selected_events)
            for horizon in horizons:
                gross_returns = _forward_returns(selected_events, rows, horizon)
                for cost in costs:
                    summaries.append(
                        _screen_summary(
                            group,
                            horizon,
                            cooldown,
                            cost,
                            gross_returns,
                        ),
                    )

    return ObiMaSpreadContext(
        source_path=source_path,
        instrument_id=rows[0].instrument_id,
        bar_count=len(rows),
        signal_count=len(signals),
        short_window=short_window,
        long_window=long_window,
        event_counts={group: len(events_by_group[group]) for group in GROUPS},
        cooldown_event_counts=cooldown_event_counts,
        signals=signals,
        summaries=summaries,
    )


def write_obi_ma_spread_report_html(context: ObiMaSpreadContext, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_obi_ma_spread_report_html(context), encoding="utf-8")


def render_obi_ma_spread_report_html(context: ObiMaSpreadContext) -> str:
    title = "OBI MA Spread Screen"
    payload = {
        "signals": [_signal_payload(signal) for signal in context.signals],
        "summaryRows": [_summary_payload(summary) for summary in context.summaries],
        "eventCounts": context.event_counts,
        "cooldownEventCounts": context.cooldown_event_counts,
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
      font-size: 12px;
      font-variant-numeric: tabular-nums;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 6px 7px;
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
    <div class="subtitle">{html.escape(context.instrument_id)} · OBI {context.short_window}m mean - {context.long_window}m mean · source: {html.escape(str(context.source_path))}</div>
    <section class="stats">
      {_stat("Bars", f"{context.bar_count:,}")}
      {_stat("Signals", f"{context.signal_count:,}")}
      {_stat("Spread > 0", f"{context.event_counts['spread_positive']:,}")}
      {_stat("Spread > 0 and 5m > 0", f"{context.event_counts['spread_positive_short_positive']:,}")}
    </section>
    <section class="chart">
      <div class="label">Mean net long return by group and horizon, no cooldown and no cost</div>
      <div id="net-return" class="plot"></div>
    </section>
    <section class="chart">
      <div class="label">Screen summary</div>
      <table>
        <thead>
          <tr>
            <th>group</th>
            <th>horizon</th>
            <th>cooldown</th>
            <th>cost bps</th>
            <th>count</th>
            <th>gross avg</th>
            <th>net avg</th>
            <th>net median</th>
            <th>hit</th>
            <th>p05 net</th>
            <th>p95 net</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
    </section>
  </main>
  <script>
    const reportData = {payload_json};
    const rows = reportData.summaryRows.filter(row => row.cooldownMinutes === 0 && row.costBps === 0);
    const traces = [...new Set(rows.map(row => row.group))].map(group => {{
      const groupRows = rows.filter(row => row.group === group);
      return {{
        name: group,
        type: "bar",
        x: groupRows.map(row => row.horizonMinutes),
        y: groupRows.map(row => row.meanNetReturn),
      }};
    }});
    Plotly.newPlot("net-return", traces, {{
      barmode: "group",
      margin: {{ l: 58, r: 18, t: 18, b: 54 }},
      paper_bgcolor: "#ffffff",
      plot_bgcolor: "#ffffff",
      font: {{ family: "ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif", color: "#18212f" }},
      xaxis: {{ title: "horizon minutes", gridcolor: "#edf0f4", zerolinecolor: "#8a94a6" }},
      yaxis: {{ title: "mean net long return", tickformat: ".3%", gridcolor: "#edf0f4", zerolinecolor: "#8a94a6" }},
    }}, {{ responsive: true, displaylogo: false }});
  </script>
</body>
</html>
"""


def _read_rows(source_path: Path) -> list[KbarObiRow]:
    rows: list[KbarObiRow] = []
    with source_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            rows.append(
                KbarObiRow(
                    ts_event=int(row["ts_event"]),
                    instrument_id=row["instrument_id"],
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    orderbook_imbalance_mean=float(row["orderbook_imbalance_mean"]),
                ),
            )
    return sorted(rows, key=lambda row: (row.ts_event, row.instrument_id))


def _obi_ma_signals(
    rows: list[KbarObiRow],
    short_window: int,
    long_window: int,
) -> list[ObiMaSignal]:
    values = [row.orderbook_imbalance_mean for row in rows]
    signals: list[ObiMaSignal] = []
    for index in range(long_window - 1, len(rows)):
        short_values = values[index - short_window + 1 : index + 1]
        long_values = values[index - long_window + 1 : index + 1]
        short_mean = sum(short_values) / short_window
        long_mean = sum(long_values) / long_window
        signals.append(
            ObiMaSignal(
                ts_event=rows[index].ts_event,
                trigger_index=index,
                short_mean=short_mean,
                long_mean=long_mean,
                spread=short_mean - long_mean,
                close=rows[index].close,
            ),
        )
    return signals


def _events_by_group(signals: list[ObiMaSignal]) -> dict[str, list[ObiMaSignal]]:
    return {
        "spread_positive": [signal for signal in signals if signal.spread > 0],
        "spread_positive_short_positive": [
            signal for signal in signals if signal.spread > 0 and signal.short_mean > 0
        ],
    }


def _apply_cooldown(events: list[ObiMaSignal], cooldown_minutes: int) -> list[ObiMaSignal]:
    if cooldown_minutes <= 0:
        return events
    selected: list[ObiMaSignal] = []
    next_allowed_index = -1
    for event in events:
        if event.trigger_index < next_allowed_index:
            continue
        selected.append(event)
        next_allowed_index = event.trigger_index + cooldown_minutes
    return selected


def _forward_returns(
    events: list[ObiMaSignal],
    rows: list[KbarObiRow],
    horizon_minutes: int,
) -> list[float]:
    bar_times = [row.ts_event for row in rows]
    returns: list[float] = []
    for event in events:
        future_ts = event.ts_event + horizon_minutes * NS_PER_MINUTE
        future_index = bisect.bisect_left(bar_times, future_ts)
        if future_index >= len(rows):
            continue
        if rows[event.trigger_index].close == 0:
            continue
        returns.append((rows[future_index].close / rows[event.trigger_index].close) - 1)
    return returns


def _screen_summary(
    group: str,
    horizon_minutes: int,
    cooldown_minutes: int,
    cost_bps: float,
    gross_returns: list[float],
) -> ScreenSummary:
    net_returns = [value - cost_bps / 10_000 for value in gross_returns]
    if not gross_returns:
        return ScreenSummary(
            group=group,
            horizon_minutes=horizon_minutes,
            cooldown_minutes=cooldown_minutes,
            cost_bps=cost_bps,
            count=0,
            mean_gross_return=0.0,
            mean_net_return=0.0,
            median_net_return=0.0,
            hit_rate=0.0,
            p05_net_return=0.0,
            p95_net_return=0.0,
        )
    sorted_net = sorted(net_returns)
    return ScreenSummary(
        group=group,
        horizon_minutes=horizon_minutes,
        cooldown_minutes=cooldown_minutes,
        cost_bps=cost_bps,
        count=len(gross_returns),
        mean_gross_return=sum(gross_returns) / len(gross_returns),
        mean_net_return=sum(net_returns) / len(net_returns),
        median_net_return=statistics.median(net_returns),
        hit_rate=sum(1 for value in net_returns if value > 0) / len(net_returns),
        p05_net_return=_percentile(sorted_net, 0.05),
        p95_net_return=_percentile(sorted_net, 0.95),
    )


def _percentile(sorted_values: list[float], percentile: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    index = percentile * (len(sorted_values) - 1)
    lower = int(index)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = index - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def _signal_payload(signal: ObiMaSignal) -> dict[str, int | float]:
    return {
        "tsEvent": signal.ts_event,
        "triggerIndex": signal.trigger_index,
        "shortMean": signal.short_mean,
        "longMean": signal.long_mean,
        "spread": signal.spread,
        "close": signal.close,
    }


def _summary_payload(summary: ScreenSummary) -> dict[str, int | float | str]:
    return {
        "group": summary.group,
        "horizonMinutes": summary.horizon_minutes,
        "cooldownMinutes": summary.cooldown_minutes,
        "costBps": summary.cost_bps,
        "count": summary.count,
        "meanGrossReturn": summary.mean_gross_return,
        "meanNetReturn": summary.mean_net_return,
        "medianNetReturn": summary.median_net_return,
        "hitRate": summary.hit_rate,
        "p05NetReturn": summary.p05_net_return,
        "p95NetReturn": summary.p95_net_return,
    }


def _table_row(summary: ScreenSummary) -> str:
    return f"""<tr>
<td>{html.escape(summary.group)}</td>
<td>{summary.horizon_minutes}m</td>
<td>{summary.cooldown_minutes}m</td>
<td>{summary.cost_bps:g}</td>
<td>{summary.count:,}</td>
<td>{summary.mean_gross_return:.5%}</td>
<td>{summary.mean_net_return:.5%}</td>
<td>{summary.median_net_return:.5%}</td>
<td>{summary.hit_rate:.2%}</td>
<td>{summary.p05_net_return:.5%}</td>
<td>{summary.p95_net_return:.5%}</td>
</tr>"""


def _stat(label: str, value: str) -> str:
    return f"""<div class="stat"><div class="label">{html.escape(label)}</div><div class="value">{html.escape(value)}</div></div>"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Screen 5m-vs-15m order book imbalance moving-average spread.",
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--short-window", type=int, default=5)
    parser.add_argument("--long-window", type=int, default=15)
    parser.add_argument("--horizons-minutes", type=int, nargs="+", default=[1, 3, 5, 10, 15, 30])
    parser.add_argument("--cooldown-minutes", type=int, nargs="+", default=[0, 5, 15])
    parser.add_argument("--cost-bps", type=float, nargs="+", default=[0, 2, 5, 10])
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/reports/obi_ma_spread_report.html"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    context = build_obi_ma_spread_context(
        args.source,
        short_window=args.short_window,
        long_window=args.long_window,
        horizons_minutes=args.horizons_minutes,
        cooldown_minutes=args.cooldown_minutes,
        cost_bps=args.cost_bps,
    )
    write_obi_ma_spread_report_html(context, args.output)
    print(f"wrote OBI MA spread report to {args.output}")
    print(f"instrument_id={context.instrument_id}")
    print(f"bars={context.bar_count}")
    print(f"signals={context.signal_count}")
    for group, count in context.event_counts.items():
        print(f"{group}_events={count}")
        for cooldown, cooldown_count in context.cooldown_event_counts[group].items():
            print(f"{group}_cooldown_{cooldown}m_events={cooldown_count}")
    for summary in context.summaries:
        print(
            "summary "
            f"group={summary.group} "
            f"horizon={summary.horizon_minutes}m "
            f"cooldown={summary.cooldown_minutes}m "
            f"cost={summary.cost_bps:g}bps "
            f"count={summary.count} "
            f"gross={summary.mean_gross_return:.8f} "
            f"net={summary.mean_net_return:.8f} "
            f"hit={summary.hit_rate:.6f}",
        )


if __name__ == "__main__":
    main()
