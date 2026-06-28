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

from reports.kbar_return_report import Kbar
from reports.kbar_return_report import build_kbar_context


@dataclass(frozen=True)
class FeaturePoint:
    ts_event: int
    trade_count: int


@dataclass(frozen=True)
class Event:
    ts_event: int
    trigger_index: int
    direction: int
    pressure: float
    aligned_pressure: float
    three_bar_return: float
    full_run_return: float
    run_length: int
    trade_count: int
    realized_volatility: float
    recent_trend_return: float


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
class DownStreakContext:
    price_source_path: Path
    pressure_source_path: Path
    feature_source_path: Path
    instrument_id: str
    bar_count: int
    raw_event_count: int
    confirmed_event_count: int
    pressure_threshold: float
    cooldown_event_counts: dict[int, int]
    summaries: list[ScreenSummary]


def build_down_streak_context(
    price_path: Path,
    pressure_path: Path,
    feature_path: Path,
    horizons_minutes: list[int] | None = None,
    pressure_threshold: float = 0.2,
    cooldown_minutes: list[int] | None = None,
    cost_bps: list[float] | None = None,
    volatility_lookback_minutes: int = 15,
    trend_lookback_minutes: int = 30,
) -> DownStreakContext:
    horizons = horizons_minutes or [5, 10, 30]
    cooldowns = cooldown_minutes or [0, 5, 30]
    costs = cost_bps or [0, 2, 5, 10]
    if not horizons:
        raise ValueError("horizons_minutes must not be empty")
    if any(value < 0 for value in cooldowns):
        raise ValueError("cooldown_minutes must be non-negative")
    if any(value < 0 for value in costs):
        raise ValueError("cost_bps must be non-negative")

    kbar_context = build_kbar_context(price_path, interval_seconds=60)
    pressure_by_ts = _read_pressure_values(pressure_path)
    features_by_ts = _read_feature_points(feature_path)
    raw_events = _down_streak_events(
        kbar_context.bars,
        pressure_by_ts,
        features_by_ts,
        volatility_lookback_minutes,
        trend_lookback_minutes,
    )
    confirmed_events = [
        event for event in raw_events if event.aligned_pressure > pressure_threshold
    ]

    summaries: list[ScreenSummary] = []
    cooldown_event_counts: dict[int, int] = {}
    for cooldown in cooldowns:
        selected_events = _apply_cooldown(confirmed_events, cooldown)
        cooldown_event_counts[cooldown] = len(selected_events)
        for group_name, group_events in _regime_groups(selected_events).items():
            for horizon in horizons:
                gross_returns = _forward_returns(group_events, kbar_context.bars, horizon)
                for cost in costs:
                    summaries.append(
                        _screen_summary(
                            group_name,
                            horizon,
                            cooldown,
                            cost,
                            gross_returns,
                        ),
                    )

    return DownStreakContext(
        price_source_path=price_path,
        pressure_source_path=pressure_path,
        feature_source_path=feature_path,
        instrument_id=kbar_context.instrument_id,
        bar_count=len(kbar_context.bars),
        raw_event_count=len(raw_events),
        confirmed_event_count=len(confirmed_events),
        pressure_threshold=pressure_threshold,
        cooldown_event_counts=cooldown_event_counts,
        summaries=summaries,
    )


def write_down_streak_report_html(context: DownStreakContext, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_down_streak_report_html(context), encoding="utf-8")


def render_down_streak_report_html(context: DownStreakContext) -> str:
    title = "Down Streak Pressure Screen"
    payload = {
        "summaries": [_summary_payload(summary) for summary in context.summaries],
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
    <div class="subtitle">{html.escape(context.instrument_id)} · threshold: aligned pressure &gt; {context.pressure_threshold:g}</div>
    <section class="stats">
      {_stat("Bars", f"{context.bar_count:,}")}
      {_stat("Raw down3 events", f"{context.raw_event_count:,}")}
      {_stat("Confirmed events", f"{context.confirmed_event_count:,}")}
      {_stat("Price source", str(context.price_source_path))}
    </section>
    <section class="chart">
      <div class="label">Net return by horizon and cost for all confirmed events</div>
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
    const rows = reportData.summaries.filter(row => row.group === "all_confirmed");
    const traces = [...new Set(rows.map(row => row.costBps))].map(cost => {{
      const costRows = rows.filter(row => row.costBps === cost && row.cooldownMinutes === 0);
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
      yaxis: {{ title: "mean net directional return", tickformat: ".3%", gridcolor: "#edf0f4", zerolinecolor: "#8a94a6" }},
    }}, {{ responsive: true, displaylogo: false }});
  </script>
</body>
</html>
"""


def _down_streak_events(
    bars: list[Kbar],
    pressure_by_ts: dict[int, float],
    features_by_ts: dict[int, FeaturePoint],
    volatility_lookback_minutes: int,
    trend_lookback_minutes: int,
) -> list[Event]:
    events: list[Event] = []
    index = 0
    feature_times = sorted(features_by_ts)
    while index < len(bars):
        direction = _sign(bars[index].bar_return)
        if direction >= 0:
            index += 1
            continue
        start = index
        while index + 1 < len(bars) and _sign(bars[index + 1].bar_return) == direction:
            index += 1
        end = index
        if end - start + 1 >= 3:
            trigger = start + 2
            trigger_bar = bars[trigger]
            pressure = pressure_by_ts.get(trigger_bar.ts_event)
            feature = _feature_at_or_before(trigger_bar.ts_event, features_by_ts, feature_times)
            if pressure is not None and feature is not None:
                events.append(
                    Event(
                        ts_event=trigger_bar.ts_event,
                        trigger_index=trigger,
                        direction=direction,
                        pressure=pressure,
                        aligned_pressure=direction * pressure,
                        three_bar_return=(trigger_bar.close / bars[start].open) - 1,
                        full_run_return=(bars[end].close / bars[start].open) - 1,
                        run_length=end - start + 1,
                        trade_count=feature.trade_count,
                        realized_volatility=_realized_volatility(
                            bars,
                            trigger,
                            volatility_lookback_minutes,
                        ),
                        recent_trend_return=_recent_trend_return(
                            bars,
                            trigger,
                            trend_lookback_minutes,
                        ),
                    ),
                )
        index += 1
    return events


def _feature_at_or_before(
    ts_event: int,
    features_by_ts: dict[int, FeaturePoint],
    feature_times: list[int],
) -> FeaturePoint | None:
    index = bisect.bisect_right(feature_times, ts_event) - 1
    if index < 0:
        return None
    return features_by_ts[feature_times[index]]


def _apply_cooldown(events: list[Event], cooldown_minutes: int) -> list[Event]:
    if cooldown_minutes <= 0:
        return events
    selected: list[Event] = []
    next_allowed_index = -1
    for event in events:
        if event.trigger_index < next_allowed_index:
            continue
        selected.append(event)
        next_allowed_index = event.trigger_index + cooldown_minutes
    return selected


def _regime_groups(events: list[Event]) -> dict[str, list[Event]]:
    if not events:
        return {
            "all_confirmed": [],
            "density_low": [],
            "density_high": [],
            "volatility_low": [],
            "volatility_high": [],
            "trend_down": [],
            "trend_not_down": [],
        }
    density_threshold = statistics.median([event.trade_count for event in events])
    volatility_threshold = statistics.median([event.realized_volatility for event in events])
    return {
        "all_confirmed": events,
        "density_low": [event for event in events if event.trade_count < density_threshold],
        "density_high": [event for event in events if event.trade_count >= density_threshold],
        "volatility_low": [
            event for event in events if event.realized_volatility < volatility_threshold
        ],
        "volatility_high": [
            event for event in events if event.realized_volatility >= volatility_threshold
        ],
        "trend_down": [event for event in events if event.recent_trend_return < 0],
        "trend_not_down": [event for event in events if event.recent_trend_return >= 0],
    }


def _forward_returns(events: list[Event], bars: list[Kbar], horizon_minutes: int) -> list[float]:
    bar_times = [bar.ts_event for bar in bars]
    returns: list[float] = []
    for event in events:
        future_ts = event.ts_event + horizon_minutes * 60 * 1_000_000_000
        future_index = bisect.bisect_left(bar_times, future_ts)
        if future_index >= len(bars):
            continue
        if bars[event.trigger_index].close == 0:
            continue
        forward_return = (bars[future_index].close / bars[event.trigger_index].close) - 1
        returns.append(event.direction * forward_return)
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


def _realized_volatility(bars: list[Kbar], trigger_index: int, lookback_minutes: int) -> float:
    start = max(0, trigger_index - lookback_minutes + 1)
    values = [bar.bar_return for bar in bars[start : trigger_index + 1]]
    if len(values) < 2:
        return 0.0
    return statistics.pstdev(values)


def _recent_trend_return(bars: list[Kbar], trigger_index: int, lookback_minutes: int) -> float:
    start = max(0, trigger_index - lookback_minutes + 1)
    if bars[start].open == 0:
        return 0.0
    return (bars[trigger_index].close / bars[start].open) - 1


def _read_pressure_values(source_path: Path) -> dict[int, float]:
    values: dict[int, float] = {}
    with source_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            values[int(row["ts_event"])] = float(row["value"])
    return values


def _read_feature_points(source_path: Path) -> dict[int, FeaturePoint]:
    points: dict[int, FeaturePoint] = {}
    with source_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            ts_event = int(row["ts_event"])
            points[ts_event] = FeaturePoint(
                ts_event=ts_event,
                trade_count=int(row["trade_count"]),
            )
    return points


def _sign(value: float) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _percentile(sorted_values: list[float], percentile: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    index = percentile * (len(sorted_values) - 1)
    lower = int(index)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = index - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


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


def _format_utc(ts_event: int) -> str:
    return datetime.fromtimestamp(ts_event / 1_000_000_000, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Screen down-down-down kbar events with confirmed sell pressure.",
    )
    parser.add_argument("--price-source", type=Path, required=True)
    parser.add_argument("--pressure-source", type=Path, required=True)
    parser.add_argument("--feature-source", type=Path, required=True)
    parser.add_argument("--horizons-minutes", type=int, nargs="+", default=[5, 10, 30])
    parser.add_argument("--pressure-threshold", type=float, default=0.2)
    parser.add_argument("--cooldown-minutes", type=int, nargs="+", default=[0, 5, 30])
    parser.add_argument("--cost-bps", type=float, nargs="+", default=[0, 2, 5, 10])
    parser.add_argument("--volatility-lookback-minutes", type=int, default=15)
    parser.add_argument("--trend-lookback-minutes", type=int, default=30)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/reports/down_streak_pressure_report.html"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    context = build_down_streak_context(
        args.price_source,
        args.pressure_source,
        args.feature_source,
        horizons_minutes=args.horizons_minutes,
        pressure_threshold=args.pressure_threshold,
        cooldown_minutes=args.cooldown_minutes,
        cost_bps=args.cost_bps,
        volatility_lookback_minutes=args.volatility_lookback_minutes,
        trend_lookback_minutes=args.trend_lookback_minutes,
    )
    write_down_streak_report_html(context, args.output)
    print(f"wrote down streak pressure report to {args.output}")
    print(f"instrument_id={context.instrument_id}")
    print(f"bars={context.bar_count}")
    print(f"raw_events={context.raw_event_count}")
    print(f"confirmed_events={context.confirmed_event_count}")
    for cooldown, count in context.cooldown_event_counts.items():
        print(f"cooldown_{cooldown}m_events={count}")
    for summary in context.summaries:
        if summary.group == "all_confirmed":
            print(
                "summary "
                f"horizon={summary.horizon_minutes}m "
                f"cooldown={summary.cooldown_minutes}m "
                f"cost={summary.cost_bps:g}bps "
                f"count={summary.count} "
                f"gross={summary.mean_gross_return:.8f} "
                f"net={summary.mean_net_return:.8f} "
                f"hit={summary.hit_rate:.6f}"
            )


if __name__ == "__main__":
    main()
