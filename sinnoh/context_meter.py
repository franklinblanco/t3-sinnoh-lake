"""Publish per-thread context percentages in the Sinnoh composer's theme CSS."""
from collections import defaultdict
import json
from pathlib import Path
import sqlite3

from .paths import THEME_ID, atomic_write, t3_home

START = "/* Sinnoh context meter */"
END = "/* End Sinnoh context meter */"
LIMIT = 100_000  # T3's maximum theme CSS size.
BASE = """
[data-chat-composer-form] [data-chat-provider-model-picker] {
  position: relative;
  overflow: visible;
  margin-inline-start: 1.4rem;
}
[data-chat-composer-form] [data-chat-provider-model-picker] [data-chat-provider-model-picker-label] {
  position: static;
  pointer-events: none;
}
[data-chat-composer-form] [data-chat-provider-model-picker] [data-chat-provider-model-picker-label]::before {
  content: "";
  position: absolute;
  inset-inline-start: -1.35rem;
  top: 50%;
  transform: translateY(-50%);
  width: .9rem;
  height: .9rem;
  border-radius: 50%;
  background: conic-gradient(from 0deg, currentColor var(--sinnoh-fill, 0%), color-mix(in srgb, currentColor 28%, transparent) 0);
  mask: radial-gradient(closest-side, transparent 61%, black 68%);
  pointer-events: auto;
  cursor: help;
}
[data-chat-composer-form] [data-chat-provider-model-picker] [data-chat-provider-model-picker-label]:hover::after,
[data-chat-composer-form] [data-chat-provider-model-picker]:focus-visible [data-chat-provider-model-picker-label]::after {
  content: var(--sinnoh-tip, "Context usage unavailable");
  position: absolute;
  bottom: calc(100% + .25rem);
  inset-inline-end: calc(100% - 2rem);
  white-space: nowrap;
  border: 1px solid #50546b;
  border-radius: .4rem;
  padding: .35rem .55rem;
  background: #202335;
  color: #f5f2ff;
  font: 500 .75rem/1.3 system-ui, sans-serif;
  z-index: 30;
  pointer-events: none;
}
"""


def css_string(value):
    return '"' + ''.join(f'\\{ord(c):x} ' if ord(c) < 32 or c in '"\\' else c for c in value) + '"'


def readings(root):
    database = root / "userdata" / "statev2.sqlite"
    env = (root / "userdata" / "environment-id").read_text().strip()
    sql = """
        SELECT t.thread_id, json_extract(p.payload_json, '$.contextUsage.usedTokens'),
               json_extract(p.payload_json, '$.contextUsage.maxTokens')
          FROM orchestration_v2_projection_threads t
          JOIN orchestration_v2_projection_provider_threads p
            ON t.active_provider_thread_id = p.provider_thread_id
         WHERE t.deleted_at IS NULL AND t.archived_at IS NULL
           AND json_type(p.payload_json, '$.contextUsage') = 'object'
         ORDER BY t.updated_at DESC
    """
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)
    try:
        return env, [(thread, min(100, (200 * used + maximum) // (2 * maximum)))
                     for thread, used, maximum in connection.execute(sql)
                     if type(used) is int and type(maximum) is int and used >= 0 and maximum > 0]
    finally:
        connection.close()


def meter_css(env, rows, budget):
    # Group equal readings so each percentage needs only one pair of declarations.
    # Match the sidebar's route-active row, or the conversation's own citation markup
    # when the sidebar is collapsed. Environment IDs distinguish transferred threads.
    groups = defaultdict(list)
    total = len(BASE) + len(START) + len(END) + 8
    for thread, percent in rows:
        sidebar = f'[data-sidebar-row={css_string(env + ":" + thread)}]'
        citation = f'[data-assistant-citation-thread={css_string(thread)}]'
        pair = (sidebar, citation)
        cost = sum(len(s.encode()) + 1 for s in pair) + (260 if percent not in groups else 0)
        if total + cost > budget:
            break
        total += cost
        groups[percent].append(pair)
    blocks = [START, BASE]
    for percent, selectors in sorted(groups.items()):
        sidebar, citations = (','.join(column) for column in zip(*sorted(selectors)))
        blocks.append(f':root:has([aria-current]:not([aria-current="false"]):is({sidebar})),'
                      f'[data-chat-workspace-drop-target]:has([data-assistant-citation-environment={css_string(env)}]:is({citations}))'
                      f'{{--sinnoh-fill:{percent}%;--sinnoh-tip:"{percent}% of context used";}}')
    return '\n'.join([*blocks, END])


def sync(root=None):
    root = t3_home() if root is None else Path(root)
    path = root / "userdata" / "themes" / f"{THEME_ID}.json"
    if not path.is_file():
        return
    theme = json.loads(path.read_text(encoding="utf-8"))
    css = theme.get("css", "")
    before, marker, tail = css.partition(START)
    if marker and END not in tail:
        return
    base = (before + (tail.partition(END)[2] if marker else "")).rstrip()
    try:
        env, rows = readings(root)
    except (OSError, sqlite3.Error):
        return  # A busy or temporarily unavailable database should not clear the last reading.
    result = base + "\n" + meter_css(env, rows, LIMIT - len(base.encode()) - 1)
    if result != css and len(result.encode()) <= LIMIT:
        theme["css"] = result
        atomic_write(path, (json.dumps(theme, ensure_ascii=False, indent=2) + "\n").encode())


if __name__ == "__main__":
    sync()
