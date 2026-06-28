from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Callable


def write_html_report(context: object, output_path: Path, render_fn: Callable[[object], str]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_fn(context), encoding="utf-8")


def stat_card(label: str, value: str) -> str:
    return f"""<div class="stat"><div class="label">{html.escape(label)}</div><div class="value">{html.escape(value)}</div></div>"""


def render_plotly_page(
    title: str,
    subtitle: str,
    stats_html: str,
    body_html: str,
    script_html: str,
    payload: dict[str, object],
) -> str:
    payload_json = json.dumps(payload, separators=(",", ":"))
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
    th:first-child, td:first-child {{ text-align: left; }}
    th {{ color: #667085; font-weight: 600; }}
  </style>
</head>
<body>
  <main>
    <h1>{html.escape(title)}</h1>
    <div class="subtitle">{html.escape(subtitle)}</div>
    <section class="stats">
      {stats_html}
    </section>
    {body_html}
  </main>
  <script>
    const reportData = {payload_json};
    {script_html}
  </script>
</body>
</html>
"""
