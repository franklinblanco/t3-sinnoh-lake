"""Read T3 provider quota snapshots without querying providers or writing T3 state."""
from dataclasses import dataclass
from datetime import datetime, timezone
import json


def read_object(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return obj(value)


def obj(value):
    return value if isinstance(value, dict) else {}


def string(value, fallback):
    return value if isinstance(value, str) and value else fallback


def iso_date(value):
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is not None:
                return parsed.astimezone(timezone.utc)
        except (ValueError, OverflowError):
            pass
    return None


@dataclass(frozen=True)
class Window:
    id: str
    label: str
    used: float | None
    reset: datetime | None


@dataclass(frozen=True)
class Provider:
    id: str
    name: str
    windows: tuple[Window, ...]
    status: str
    checked: datetime | None


def provider(id_, config, cache):
    limits = obj(cache.get("usageLimits"))
    reason = obj(limits.get("unavailable")).get("reason")
    windows = {}
    reported = limits.get("windows")
    for raw in reported if isinstance(reported, list) else []:
        data = obj(raw)
        key = data.get("id")
        if not isinstance(key, str) or not key:
            continue
        used = data.get("usedPercent")
        if type(used) not in (int, float) or not 0 <= used <= 100:
            used = None
        reset = iso_date(data.get("resetsAt"))
        windows[key] = Window(key, string(data.get("label"), key), used, reset)

    eligible = False
    if config.get("enabled", cache.get("enabled")) is False:
        status = "Provider disabled"
    elif obj(cache.get("auth")).get("status") == "unauthenticated":
        status = "Sign-in required"
    elif limits.get("zeroSpendCap") is True:
        status = "Zero spend cap"
    elif reason == "probeFailed":
        status = "Usage check failed"
    elif reason == "unsupported":
        status = "Quota not supported"
    elif reason or limits.get("unavailable"):
        status = "Usage unavailable"
    elif not cache:
        status = "Awaiting T3 data"
    else:
        eligible = True
        status = "Quota not reported"

    name = string(config.get("displayName"), string(cache.get("displayName"), id_))
    return Provider(id_, name, tuple(windows.values()) if eligible else (), status,
                    iso_date(limits.get("checkedAt")))


def read_providers(root):
    settings = read_object(root / "userdata" / "settings.json")
    configured = obj(settings.get("providerInstances"))
    cached = {}
    for path in sorted((root / "caches").glob("*.json")):
        if path.name.startswith("acp-auth-") and path.stem not in configured:
            continue  # This is an ACP auth probe cache, not a provider status snapshot.
        record = read_object(path)
        id_ = record.get("instanceId")
        if not isinstance(id_, str) or not id_:
            continue
        if id_ in configured or record.get("enabled") is True:
            if id_ not in cached or path.stem == id_:
                cached[id_] = record
    items = [provider(id_, obj(configured.get(id_)), cached.get(id_, {}))
             for id_ in configured.keys() | cached.keys()]
    return sorted(items, key=lambda item: (item.id != "codex", item.name.casefold(), item.id))
