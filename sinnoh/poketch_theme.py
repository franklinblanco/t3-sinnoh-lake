"""Render quota snapshots as a 1D SVG sprite with auto-cycling CSS keyframes."""
from datetime import datetime, timedelta, timezone
import json
import math
import re
from urllib.parse import quote
from xml.sax.saxutils import escape

from .paths import ASSETS
from .usage import read_providers

CHAT = ':root:has([data-chat-canvas]:not([data-slot="sidebar-inset"][inert] *))'
SECONDS_PER_FACE = 5
ASSET_DIR = ASSETS / "poketch"
SPEC = json.loads((ASSET_DIR / "spec.json").read_text(encoding="utf-8"))
LCD_WIDTH = SPEC["lcd"]["width"]
LCD_HEIGHT = SPEC["lcd"]["height"]
METER_BARS = SPEC["meterBars"]
STALE_MINUTES = SPEC["staleMinutes"]
SEGMENTS = tuple(tuple(segment) for segment in SPEC["segments"])
DIGITS = tuple(SPEC["digitMasks"])
CONTROL = re.compile(r"[\x00-\x1f\ud800-\udfff\ufffe\uffff]")


def image(svg):
    return 'url("data:image/svg+xml,' + quote(svg, safe="/:;,=-_' .") + '")'


def text(label, x, y, size, length, *, end=False):
    clean = " ".join(CONTROL.sub(" ", label).split())
    if len(clean) > length:
        clean = clean[:length - 1] + "…"
    anchor = " text-anchor='end'" if end else ""
    return f"<text x='{x}' y='{y}' font-size='{size}'{anchor}>{escape(clean)}</text>"


def ordered_windows(provider, now):
    windows = provider.windows
    if not windows:
        return (None,)

    def tightness(window):
        return window.used if (window.used is not None
                               and (window.reset is None or window.reset > now)) else -1

    first = max(range(len(windows)), key=lambda index: tightness(windows[index]))
    return windows[first:] + windows[:first]


def face(provider, window, index, count, page, pages, face_index, now):
    name = provider.name if provider else "Providers"
    label = window.label if window else "No quota window"
    stale = window and window.reset and window.reset <= now
    used = window.used if window and not stale else None
    if stale:
        reset = "Awaiting reset update"
    elif window and window.reset:
        local = window.reset.astimezone()
        fmt = "%H:%M" if local.date() == now.astimezone().date() else "%x %H:%M"
        reset = f"Reset {local.strftime(fmt)}"
    elif window:
        reset = "Reset not reported"
    else:
        reset = provider.status if provider else "Awaiting T3 data"

    parts = [text(name, 7, 17, 12, 20), "<path fill='#6d9364' d='M7 24h175v1H7z'/>",
             text("LEFT", 109, 39, 9, 4), text(label, 7, 73, 10, 22 if pages > 1 else 28),
             text(reset, 7, 91, 11, 26)]
    if provider:
        parts.append(text(f"{index + 1}/{count}", 182, 15, 10, 9, end=True))
    if pages > 1:
        parts.append(text(f"{page + 1}/{pages}", 181, 72, 9, 9, end=True))
    old = used is not None and provider.checked and now - provider.checked > timedelta(minutes=STALE_MINUTES)
    if used is None:
        parts.append("<path d='M11 43h25v3H11z'/>")
        quota = "Quota remaining unknown"
    else:
        left = 100 - used
        digits = str(math.floor(left + 0.5))
        quota = f"{digits}% remaining"
        for offset, digit in enumerate(digits):
            parts.append(f"<use href='#d{digit}' x='{9 + 19 * offset}' y='32'/>")
        parts.append(text("%", 9 + len(digits) * 19, 51, 14, 1))
        filled = math.ceil(left * METER_BARS / 100)
        parts.append("<path fill='#749d6b' d='" +
                     "".join(f"M{109 + 6 * offset} 46h4v9h-4z" for offset in range(METER_BARS)) + "'/>")
        if filled:
            parts.append("<path d='" +
                         "".join(f"M{109 + 6 * offset} 46h4v9h-4z" for offset in range(filled)) + "'/>")
        if old:
            parts.append(text("OLD", 180, 39, 9, 3, end=True))
    description = ", ".join((name, label, quota, reset, *(["Cached more than 30 minutes ago"] if old else [])))
    # T3 rejects backslashes in theme values. Use typographic quotes for the text
    # alternative, while the XML display preserves the original characters.
    description = CONTROL.sub(" ", description).replace('"', "”").replace("\\", "∖")
    description = " ".join(description.split())
    return (
        f"<g transform='translate({face_index * LCD_WIDTH} 0)' clip-path='url(#lcd)'>"
        + "".join(parts) + "</g>",
        f'"{description}"',
    )


def sprite(faces):
    definitions = [f"<clipPath id='lcd'><path d='M0 0h{LCD_WIDTH}v{LCD_HEIGHT}H0z'/></clipPath>"]
    for digit, mask in enumerate(DIGITS):
        path = "".join(f"M{x} {y}h{width}v{height}h-{width}z"
                       for index, (x, y, width, height) in enumerate(SEGMENTS) if mask & (1 << index))
        definitions.append(f"<path id='d{digit}' d='{path}'/>")
    width, height = LCD_WIDTH * len(faces), LCD_HEIGHT
    return image(f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}'>"
                 "<defs>" + "".join(definitions) + "</defs>"
                 "<g fill='#26422b' font-family='ui-monospace,monospace' font-weight='700'>"
                 + "".join(faces) + "</g></svg>")


def cycle_keyframes(descriptions):
    if len(descriptions) < 2:
        return ""
    total = len(descriptions)
    lines = ["@keyframes sinnoh-cycle {"]
    for index, label in enumerate(descriptions):
        pct = "0%, 100%" if index == 0 else f"{index * 100 / total:.4f}%"
        pos = "0 0" if index == 0 else f"calc(-{index} * var(--sinnoh-lcd-w)) 0"
        lines.append(f'  {pct} {{ background-position: {pos}; content: "" / {label}; }}')
    lines.append("}")
    return "\n".join(lines) + "\n\n"


def styles(root, port, now=None):
    now = now or datetime.now(timezone.utc)
    providers = read_providers(root) or [None]
    windows = [ordered_windows(provider, now) if provider else (None,) for provider in providers]
    count = len(providers)
    faces = []
    descriptions = []
    for index, (provider, pages) in enumerate(zip(providers, windows)):
        for page, window in enumerate(pages):
            fragment, label = face(provider, window, index, count, page, len(pages), len(faces), now)
            faces.append(fragment)
            descriptions.append(label)
    face_count = len(faces)
    url = f"http://127.0.0.1:{port}/poketch/"
    urls = {url, "http://127.0.0.1:47984/poketch/"}
    legacy = ', '.join(f'[src="{u}"]' for u in sorted(urls))
    viewport = '[data-preview-viewport][style*="z-index: 48;"]'
    animation = f"sinnoh-cycle {face_count * SECONDS_PER_FACE}s steps(1, end) infinite" if face_count > 1 else "none"
    substitutions = {
        "KEYFRAMES": cycle_keyframes(descriptions),
        "CHAT": CHAT,
        "FACE_COUNT": str(face_count),
        "HOUSING": image((ASSET_DIR / "housing.svg").read_text(encoding="utf-8")),
        "INITIAL_DESCRIPTION": descriptions[0],
        "FACES": sprite(faces),
        "ANIMATION": animation,
        "FLOAT": viewport,
        "LEGACY_GUEST": f'webview:is({legacy}):not([aria-hidden="true"])',
    }
    global_css = (ASSET_DIR / "global.css").read_text(encoding="utf-8")
    return re.sub(r"__([A-Z_]+)__", lambda match: substitutions[match[1]], global_css)
