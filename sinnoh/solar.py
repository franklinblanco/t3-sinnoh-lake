"""Publish the lake animation for the current solar elevation."""
import filecmp
from datetime import datetime, timedelta, timezone
from importlib.resources import files
import re
from zoneinfo import ZoneInfo

from astral import Observer
from astral.sun import elevation
from tzlocal import reload_localzone

from .context_meter import sync as sync_context_meter
from .paths import ASSETS, THEME_ID, atomic_write, t3_home

LIMITS = (-10, -7.5, -5.5, -3.5, -1.6, 0.8, 3.5, 7, 12)
PHASES = ("night", "day", *(f"{direction}{level}" for direction in ("rise", "set")
                           for level in range(1, len(LIMITS))))


def degrees(compact, width):
    sign = -1 if compact[0] == "-" else 1
    digits = compact[1:]
    return sign * (int(digits[:width]) + int(digits[width:width + 2]) / 60
                   + int(digits[width + 2:] or "0") / 3600)


def observer_for(zone, now):
    zone_data = files("tzdata.zoneinfo")
    rows = (zone_data / "zone.tab").read_text(encoding="utf-8").splitlines()
    coords = {row.split("\t")[2]: row.split("\t")[1] for row in rows
              if row and not row.startswith("#")}
    links = {alias: target for _, target, alias in
             (row.split() for row in (zone_data / "tzdata.zi").read_text(encoding="utf-8").splitlines()
              if row.startswith("L "))}
    name = zone.key
    visited = set()
    while name not in coords and name in links and name not in visited:
        visited.add(name)
        name = links[name]
    if name in coords:
        lat, lon = re.fullmatch(r"([+-]\d+)([+-]\d+)", coords[name]).groups()
        return Observer(degrees(lat, 2), degrees(lon, 3))
    # A fixed-offset zone has no city. Use its central meridian on the equator.
    offset = now.astimezone(zone).utcoffset()
    return Observer(0, (offset.total_seconds() / 240 + 180) % 360 - 180)


def phase_at(now, observer):
    altitude = elevation(observer, now, with_refraction=False)
    level = sum(altitude >= boundary for boundary in LIMITS)
    if level == 0:
        return "night"
    if level == len(LIMITS):
        return "day"
    later = elevation(observer, now + timedelta(minutes=1), with_refraction=False)
    return ("rise" if later > altitude else "set") + str(level)


def publish(source, target, *, force=False):
    if not force and target.exists() and filecmp.cmp(source, target, shallow=False):
        return
    # Stage on the destination filesystem. T3's watcher sees a complete new inode.
    atomic_write(target, source.read_bytes())


def sync(root=None, *, status_only=False, force=False, now=None):
    root = t3_home() if root is None else root
    now = now or datetime.now(timezone.utc)
    zone = reload_localzone()
    observer = observer_for(zone, now)
    phase = phase_at(now, observer)
    target = root / "userdata" / "themes" / f"{THEME_ID}.webp"
    if not status_only and target.with_suffix(".json").is_file():
        publish(ASSETS / "phases" / f"{phase}.webp", target, force=force)
        sync_context_meter(root)
    return f"{zone.key} ({observer.latitude:.3f}, {observer.longitude:.3f}), {phase}"


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", action="store_true", help="Report the solar phase without publishing")
    parser.add_argument("--force", action="store_true", help="Replace the background even if its content matches")
    args = parser.parse_args()
    print(sync(status_only=args.status, force=args.force))
