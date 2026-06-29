from __future__ import annotations

import argparse
import csv
import statistics
from dataclasses import dataclass
from pathlib import Path

from common.time_series import NS_PER_SECOND
from reports.framework import render_plotly_page
from reports.framework import stat_card
from reports.framework import write_html_report


@dataclass(frozen=True)
class AlignedKbar:
    start_time: int
    end_time: int
    ts_event: int
    timestamp: str
    instrument_id: str
    close: float
    volume: float
    trade_count: int
    imbalance_value: float


@dataclass(frozen=True)
class ClusterEvent:
    ts_event: int
    timestamp: str
    trigger_index: int
    high_count: int
    lookback_mean_imbalance: float
    trigger_imbalance: float
    trigger_close: float
    future_close: float
    forward_return: float


@dataclass(frozen=True)
class ReturnSummary:
    group: str
    count: int
    mean_high_count: float
    mean_trigger_imbalance: float
    mean_forward_return: float
    median_forward_return: float
    positive_rate: float


@dataclass(frozen=True)
class ImbalanceClusterReturnContext:
    source_path: Path
    instrument_id: str
    row_count: int
    lookback_minutes: int
    min_high_count: int
    threshold: float
    imbalance_column: str
    horizon_minutes: int
    cooldown_minutes: int
    raw_events: list[ClusterEvent]
    cooldown_events: list[ClusterEvent]
    summaries: list[ReturnSummary]


def build_imbalance_cluster_return_context(
    source_path: Path,
    lookback_minutes: int = 15,
    min_high_count: int = 10,
    threshold: float = 0.95,
    imbalance_column: str = "orderbook_imbalance_mean",
    horizon_minutes: int = 15,
    cooldown_minutes: int = 15,
) -> ImbalanceClusterReturnContext:
    if lookback_minutes <= 0:
        raise ValueError("lookback_minutes must be positive")
    if min_high_count <= 0:
        raise ValueError("min_high_count must be positive")
    if horizon_minutes <= 0:
        raise ValueError("horizon_minutes must be positive")
    if cooldown_minutes < 0:
        raise ValueError("cooldown_minutes must be non-negative")

    rows = _read_aligned_kbars(source_path, imbalance_column)
    if not rows:
        raise RuntimeError(f"No aligned kbar rows found in {source_path}")

    interval_ns = _require_fixed_interval(rows)
    lookback_rows = _minutes_to_rows(lookback_minutes, interval_ns)
    horizon_rows = _minutes_to_rows(horizon_minutes, interval_ns)
    cooldown_ns = cooldown_minutes * 60 * NS_PER_SECOND
    if min_high_count > lookback_rows:
        raise ValueError("min_high_count cannot exceed lookback rows")

    segments = _continuous_segments(rows)
    raw_events = [
        event
        for segment in segments
        for event in _cluster_events(segment, lookback_rows, min_high_count, threshold, horizon_rows)
    ]
    baseline_events = [
        event
        for segment in segments
        for event in _baseline_events(segment, lookback_rows, threshold, horizon_rows)
    ]
    cooldown_events = _apply_cooldown(raw_events, cooldown_ns)

    return ImbalanceClusterReturnContext(
        source_path=source_path,
        instrument_id=rows[0].instrument_id,
        row_count=len(rows),
        lookback_minutes=lookback_minutes,
        min_high_count=min_high_count,
        threshold=threshold,
        imbalance_column=imbalance_column,
        horizon_minutes=horizon_minutes,
        cooldown_minutes=cooldown_minutes,
        raw_events=raw_events,
        cooldown_events=cooldown_events,
        summaries=[
            _summary("baseline_all_eligible", baseline_events),
            _summary("raw_cluster_events", raw_events),
            _summary(f"cooldown_{cooldown_minutes}m", cooldown_events),
        ],
    )


def write_imbalance_cluster_return_report_html(
    context: ImbalanceClusterReturnContext,
    output_path: Path,
) -> None:
    write_html_report(context, output_path, render_imbalance_cluster_return_report_html)


def render_imbalance_cluster_return_report_html(context: ImbalanceClusterReturnContext) -> str:
    title = "Imbalance Cluster Forward Return"
    subtitle = (
        f"{context.instrument_id} - past {context.lookback_minutes}m: "
        f"{context.min_high_count}+ {context.imbalance_column} bars > {context.threshold:g}; "
        f"forward {context.horizon_minutes}m return"
    )
    stats_html = "\n".join(
        [
            stat_card("Rows", f"{context.row_count:,}"),
            stat_card("Raw events", f"{len(context.raw_events):,}"),
            stat_card("Cooldown events", f"{len(context.cooldown_events):,}"),
            stat_card("Source", str(context.source_path)),
        ],
    )
    body_html = f"""
    <section class="chart">
      <div class="label">Forward return by group</div>
      <div id="summary" class="plot"></div>
    </section>
    <section class="chart">
      <div class="label">Event forward returns over time</div>
      <div id="events" class="plot"></div>
    </section>
    <section class="chart">
      <div class="label">Summary table</div>
      <table>
        <thead>
          <tr>
            <th>group</th><th>count</th><th>mean high count</th><th>mean trigger imb</th>
            <th>mean fwd return</th><th>median fwd return</th><th>positive</th>
          </tr>
        </thead>
        <tbody>
          {"".join(_summary_row(summary) for summary in context.summaries)}
        </tbody>
      </table>
    </section>
    """
    script_html = """
    const summaries = reportData.summaries;
    const events = reportData.cooldownEvents;
    const layout = {
      margin: { l: 58, r: 18, t: 18, b: 58 },
      paper_bgcolor: "#ffffff",
      plot_bgcolor: "#ffffff",
      font: { family: "ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif", color: "#18212f" },
      xaxis: { gridcolor: "#edf0f4", zerolinecolor: "#8a94a6" },
      yaxis: { gridcolor: "#edf0f4", zerolinecolor: "#8a94a6", tickformat: ".3%" },
    };
    const config = { responsive: true, displaylogo: false };
    Plotly.newPlot("summary", [{
      type: "bar",
      x: summaries.map(row => row.group),
      y: summaries.map(row => row.meanForwardReturn),
      customdata: summaries.map(row => [row.count, row.positiveRate]),
      hovertemplate: "%{x}<br>mean=%{y:.4%}<br>count=%{customdata[0]}<br>positive=%{customdata[1]:.2%}<extra></extra>",
      marker: { color: "#2563eb" },
    }], { ...layout, xaxis: { ...layout.xaxis, title: "group" }, yaxis: { ...layout.yaxis, title: "forward return" } }, config);
    Plotly.newPlot("events", [{
      type: "scattergl",
      mode: "markers",
      x: events.map(row => row.timestamp),
      y: events.map(row => row.forwardReturn),
      customdata: events.map(row => [row.highCount, row.triggerImbalance]),
      hovertemplate: "%{x}<br>return=%{y:.4%}<br>high count=%{customdata[0]}<br>trigger imb=%{customdata[1]:.4f}<extra></extra>",
      marker: { color: "#0f766e", size: 6, opacity: 0.7 },
    }], { ...layout, xaxis: { ...layout.xaxis, title: "trigger time" }, yaxis: { ...layout.yaxis, title: "forward return" } }, config);
    """
    payload = {
        "summaries": [_summary_payload(summary) for summary in context.summaries],
        "cooldownEvents": [_event_payload(event) for event in context.cooldown_events],
    }
    return render_plotly_page(title, subtitle, stats_html, body_html, script_html, payload)


def _read_aligned_kbars(source_path: Path, imbalance_column: str) -> list[AlignedKbar]:
    rows: list[AlignedKbar] = []
    with source_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None or imbalance_column not in reader.fieldnames:
            raise ValueError(f"Missing imbalance column: {imbalance_column}")
        for row in reader:
            rows.append(
                AlignedKbar(
                    start_time=int(row["start_time"]),
                    end_time=int(row["end_time"]),
                    ts_event=int(row["ts_event"]),
                    timestamp=row["timestamp"],
                    instrument_id=row["instrument_id"],
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                    trade_count=int(row["trade_count"]),
                    imbalance_value=float(row[imbalance_column]),
                ),
            )
    return sorted(rows, key=lambda row: (row.ts_event, row.instrument_id))


def _require_fixed_interval(rows: list[AlignedKbar]) -> int:
    interval_ns = rows[0].end_time - rows[0].start_time
    if interval_ns <= 0:
        raise ValueError("rows must have positive interval")
    for row in rows:
        if row.end_time - row.start_time != interval_ns:
            raise ValueError("rows must have a fixed interval")
    return interval_ns


def _continuous_segments(rows: list[AlignedKbar]) -> list[list[AlignedKbar]]:
    segments: list[list[AlignedKbar]] = []
    current: list[AlignedKbar] = []
    for row in rows:
        if current and current[-1].end_time != row.start_time:
            segments.append(current)
            current = []
        current.append(row)
    if current:
        segments.append(current)
    return segments


def _minutes_to_rows(minutes: int, interval_ns: int) -> int:
    duration_ns = minutes * 60 * NS_PER_SECOND
    if duration_ns % interval_ns != 0:
        raise ValueError("minutes must align with kbar interval")
    return duration_ns // interval_ns


def _cluster_events(
    rows: list[AlignedKbar],
    lookback_rows: int,
    min_high_count: int,
    threshold: float,
    horizon_rows: int,
) -> list[ClusterEvent]:
    events: list[ClusterEvent] = []
    high_flags = [row.imbalance_value > threshold for row in rows]
    for index in range(lookback_rows - 1, len(rows) - horizon_rows):
        start = index - lookback_rows + 1
        window = rows[start : index + 1]
        high_count = sum(1 for flag in high_flags[start : index + 1] if flag)
        if high_count < min_high_count:
            continue
        events.append(_event_for(rows, index, horizon_rows, high_count, window))
    return events


def _baseline_events(
    rows: list[AlignedKbar],
    lookback_rows: int,
    threshold: float,
    horizon_rows: int,
) -> list[ClusterEvent]:
    events: list[ClusterEvent] = []
    for index in range(lookback_rows - 1, len(rows) - horizon_rows):
        window = rows[index - lookback_rows + 1 : index + 1]
        high_count = sum(1 for row in window if row.imbalance_value > threshold)
        events.append(_event_for(rows, index, horizon_rows, high_count, window))
    return events


def _event_for(
    rows: list[AlignedKbar],
    index: int,
    horizon_rows: int,
    high_count: int,
    window: list[AlignedKbar],
) -> ClusterEvent:
    row = rows[index]
    future = rows[index + horizon_rows]
    forward_return = (future.close / row.close) - 1 if row.close else 0.0
    return ClusterEvent(
        ts_event=row.ts_event,
        timestamp=row.timestamp,
        trigger_index=index,
        high_count=high_count,
        lookback_mean_imbalance=sum(item.imbalance_value for item in window) / len(window),
        trigger_imbalance=row.imbalance_value,
        trigger_close=row.close,
        future_close=future.close,
        forward_return=forward_return,
    )


def _apply_cooldown(events: list[ClusterEvent], cooldown_ns: int) -> list[ClusterEvent]:
    if cooldown_ns <= 0:
        return events
    filtered: list[ClusterEvent] = []
    next_allowed_ts = -1
    for event in events:
        if event.ts_event < next_allowed_ts:
            continue
        filtered.append(event)
        next_allowed_ts = event.ts_event + cooldown_ns
    return filtered


def _summary(group: str, events: list[ClusterEvent]) -> ReturnSummary:
    if not events:
        return ReturnSummary(group, 0, 0.0, 0.0, 0.0, 0.0, 0.0)
    returns = [event.forward_return for event in events]
    return ReturnSummary(
        group=group,
        count=len(events),
        mean_high_count=sum(event.high_count for event in events) / len(events),
        mean_trigger_imbalance=sum(event.trigger_imbalance for event in events) / len(events),
        mean_forward_return=sum(returns) / len(returns),
        median_forward_return=statistics.median(returns),
        positive_rate=sum(1 for value in returns if value > 0) / len(returns),
    )


def _summary_row(summary: ReturnSummary) -> str:
    return (
        f"<tr><td>{summary.group}</td><td>{summary.count:,}</td>"
        f"<td>{summary.mean_high_count:.2f}</td><td>{summary.mean_trigger_imbalance:.4f}</td>"
        f"<td>{summary.mean_forward_return:.5%}</td><td>{summary.median_forward_return:.5%}</td>"
        f"<td>{summary.positive_rate:.2%}</td></tr>"
    )


def _summary_payload(summary: ReturnSummary) -> dict[str, int | str | float]:
    return {
        "group": summary.group,
        "count": summary.count,
        "meanHighCount": summary.mean_high_count,
        "meanTriggerImbalance": summary.mean_trigger_imbalance,
        "meanForwardReturn": summary.mean_forward_return,
        "medianForwardReturn": summary.median_forward_return,
        "positiveRate": summary.positive_rate,
    }


def _event_payload(event: ClusterEvent) -> dict[str, int | str | float]:
    return {
        "tsEvent": event.ts_event,
        "timestamp": event.timestamp,
        "highCount": event.high_count,
        "lookbackMeanImbalance": event.lookback_mean_imbalance,
        "triggerImbalance": event.trigger_imbalance,
        "triggerClose": event.trigger_close,
        "futureClose": event.future_close,
        "forwardReturn": event.forward_return,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diagnose clustered 1m orderbook imbalance forward returns.")
    parser.add_argument("source", type=Path)
    parser.add_argument("--lookback-minutes", type=int, default=15)
    parser.add_argument("--min-high-count", type=int, default=10)
    parser.add_argument("--threshold", type=float, default=0.95)
    parser.add_argument(
        "--imbalance-column",
        choices=[
            "orderbook_imbalance_mean",
            "orderbook_imbalance_last",
            "orderbook_imbalance_max",
            "imbalance_value",
        ],
        default="orderbook_imbalance_mean",
    )
    parser.add_argument("--horizon-minutes", type=int, default=15)
    parser.add_argument("--cooldown-minutes", type=int, default=15)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/reports/imbalance_cluster_return_report.html"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    context = build_imbalance_cluster_return_context(
        args.source,
        lookback_minutes=args.lookback_minutes,
        min_high_count=args.min_high_count,
        threshold=args.threshold,
        imbalance_column=args.imbalance_column,
        horizon_minutes=args.horizon_minutes,
        cooldown_minutes=args.cooldown_minutes,
    )
    write_imbalance_cluster_return_report_html(context, args.output)
    print(f"wrote imbalance cluster return report to {args.output}")
    print(f"instrument_id={context.instrument_id}")
    print(f"rows={context.row_count}")
    print(f"raw_events={len(context.raw_events)}")
    print(f"cooldown_events={len(context.cooldown_events)}")
    print(f"imbalance_column={context.imbalance_column}")
    for summary in context.summaries:
        print(
            f"{summary.group}: count={summary.count} "
            f"mean_forward_return={summary.mean_forward_return:.8f} "
            f"positive_rate={summary.positive_rate:.4f}",
        )


if __name__ == "__main__":
    main()
