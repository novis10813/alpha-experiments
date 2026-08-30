from __future__ import annotations

import argparse
import bisect
import html
import json
import statistics
from dataclasses import dataclass
from pathlib import Path

from reports.kbar_return_report import Kbar
from reports.kbar_return_report import build_kbar_context


NS_PER_MINUTE = 60 * 1_000_000_000


@dataclass(frozen=True)
class FiveGreenEvent:
    ts_event: int
    trigger_index: int
    streak_return: float
    fifth_bar_return: float


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
class FiveGreenStreakContext:
    price_source_path: Path
    instrument_id: str
    bar_count: int
    raw_event_count: int
    cooldown_event_counts: dict[int, int]
    events: list[FiveGreenEvent]
    summaries: list[ScreenSummary]


def build_five_green_streak_context(
    price_path: Path,
    horizons_minutes: list[int] | None = None,
    cooldown_minutes: list[int] | None = None,
    cost_bps: list[float] | None = None,
) -> FiveGreenStreakContext:
    horizons = horizons_minutes if horizons_minutes is not None else [1, 3, 5, 10, 30]
    cooldowns = cooldown_minutes if cooldown_minutes is not None else [0, 5, 30]
    costs = cost_bps if cost_bps is not None else [0, 2, 5, 10]
    if not horizons:
        raise ValueError("horizons_minutes must not be empty")
    if any(value <= 0 for value in horizons):
        raise ValueError("horizons_minutes must be positive")
    if any(value < 0 for value in cooldowns):
        raise ValueError("cooldown_minutes must be non-negative")
    if any(value < 0 for value in costs):
        raise ValueError("cost_bps must be non-negative")

    kbar_context = build_kbar_context(price_path, interval_seconds=60)
    events = _five_green_events(kbar_context.bars)

    summaries: list[ScreenSummary] = []
    cooldown_event_counts: dict[int, int] = {}
    for cooldown in cooldowns:
        selected_events = _apply_cooldown(events, cooldown)
        cooldown_event_counts[cooldown] = len(selected_events)
        for horizon in horizons:
            gross_returns = _forward_returns(selected_events, kbar_context.bars, horizon)
            for cost in costs:
                summaries.append(
                    _screen_summary(
                        "all_events",
                        horizon,
                        cooldown,
                        cost,
                        gross_returns,
                    ),
                )

    return FiveGreenStreakContext(
        price_source_path=price_path,
        instrument_id=kbar_context.instrument_id,
        bar_count=len(kbar_context.bars),
        raw_event_count=len(events),
        cooldown_event_counts=cooldown_event_counts,
        events=events,
        summaries=summaries,
    )


def write_five_green_streak_report_html(
    context: FiveGreenStreakContext,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_five_green_streak_report_html(context), encoding="utf-8")


def render_five_green_streak_report_html(context: FiveGreenStreakContext) -> str:
    title = "Five Green Streak Screen"
    payload = {
        "events": [_event_payload(event) for event in context.events],
        "summaryRows": [_summary_payload(summary) for summary in context.summaries],
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
    <div class="subtitle">{html.escape(context.instrument_id)} · five completed bullish 1m K-bars · source: {html.escape(str(context.price_source_path))}</div>
    <section class="stats">
      {_stat("Bars", f"{context.bar_count:,}")}
      {_stat("Raw events", f"{context.raw_event_count:,}")}
      {_stat("Cooldown events", _cooldown_text(context.cooldown_event_counts))}
      {_stat("Rule", "close > open for five bars")}
    </section>
    <section class="chart">
      <div class="label">Mean net long return by horizon and cost, no cooldown</div>
      <div id="net-return" class="plot"></div>
    </section>
    <section class="chart">
      <div class="label">Event summary</div>
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
    const rows = reportData.summaryRows.filter(row => row.group === "all_events" && row.cooldownMinutes === 0);
    const traces = [...new Set(rows.map(row => row.costBps))].map(cost => {{
      const costRows = rows.filter(row => row.costBps === cost);
      return {{
        name: `${{cost}} bps`,
        type: "bar",
        x: costRows.map(row => row.horizonMinutes),
        y: costRows.map(row => row.meanNetReturn),
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


def _five_green_events(bars: list[Kbar]) -> list[FiveGreenEvent]:
    events: list[FiveGreenEvent] = []
    bullish_run = 0
    for index, bar in enumerate(bars):
        if bar.close > bar.open:
            bullish_run += 1
        else:
            bullish_run = 0
        if bullish_run >= 5:
            first_index = index - 4
            first_open = bars[first_index].open
            streak_return = (bar.close / first_open) - 1 if first_open else 0.0
            events.append(
                FiveGreenEvent(
                    ts_event=bar.ts_event,
                    trigger_index=index,
                    streak_return=streak_return,
                    fifth_bar_return=bar.bar_return,
                ),
            )
    return events


def _apply_cooldown(events: list[FiveGreenEvent], cooldown_minutes: int) -> list[FiveGreenEvent]:
    if cooldown_minutes <= 0:
        return events
    selected: list[FiveGreenEvent] = []
    next_allowed_index = -1
    for event in events:
        if event.trigger_index < next_allowed_index:
            continue
        selected.append(event)
        next_allowed_index = event.trigger_index + cooldown_minutes
    return selected


def _forward_returns(
    events: list[FiveGreenEvent],
    bars: list[Kbar],
    horizon_minutes: int,
) -> list[float]:
    bar_times = [bar.ts_event for bar in bars]
    returns: list[float] = []
    for event in events:
        future_ts = event.ts_event + horizon_minutes * NS_PER_MINUTE
        future_index = bisect.bisect_left(bar_times, future_ts)
        if future_index >= len(bars):
            continue
        trigger_close = bars[event.trigger_index].close
        if trigger_close == 0:
            continue
        returns.append((bars[future_index].close / trigger_close) - 1)
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


def _event_payload(event: FiveGreenEvent) -> dict[str, int | float]:
    return {
        "tsEvent": event.ts_event,
        "triggerIndex": event.trigger_index,
        "streakReturn": event.streak_return,
        "fifthBarReturn": event.fifth_bar_return,
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


def _cooldown_text(counts: dict[int, int]) -> str:
    return ", ".join(f"{cooldown}m={count:,}" for cooldown, count in counts.items())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Screen five consecutive bullish 1m K-bars as a long continuation signal.",
    )
    parser.add_argument("--price-source", type=Path, required=True)
    parser.add_argument("--horizons-minutes", type=int, nargs="+", default=[1, 3, 5, 10, 30])
    parser.add_argument("--cooldown-minutes", type=int, nargs="+", default=[0, 5, 30])
    parser.add_argument("--cost-bps", type=float, nargs="+", default=[0, 2, 5, 10])
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/reports/five_green_streak_report.html"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    context = build_five_green_streak_context(
        args.price_source,
        horizons_minutes=args.horizons_minutes,
        cooldown_minutes=args.cooldown_minutes,
        cost_bps=args.cost_bps,
    )
    write_five_green_streak_report_html(context, args.output)
    print(f"wrote five green streak report to {args.output}")
    print(f"instrument_id={context.instrument_id}")
    print(f"bars={context.bar_count}")
    print(f"raw_events={context.raw_event_count}")
    for cooldown, count in context.cooldown_event_counts.items():
        print(f"cooldown_{cooldown}m_events={count}")
    for summary in context.summaries:
        print(
            "summary "
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
