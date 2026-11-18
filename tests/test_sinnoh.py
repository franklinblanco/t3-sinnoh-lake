from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zoneinfo import ZoneInfo

from PIL import Image, ImageChops

from sinnoh.follow import t3_name
from sinnoh.paths import ASSETS
from sinnoh.solar import PHASES, observer_for, phase_at, publish
from sinnoh.usage import Selection, filled_segments, percent_text, read_providers

NOW = datetime(2026, 3, 20, 12, tzinfo=timezone.utc)


def timestamp(minutes):
    return (NOW + timedelta(minutes=minutes)).isoformat()


def window(id_, used=None, reset=None):
    return {"id": id_, "label": id_.title(), "usedPercent": used, "resetsAt": reset}


def fixture(root):
    cache = root / "caches"
    cache.mkdir()
    settings = root / "userdata"
    settings.mkdir()
    (settings / "settings.json").write_text(json.dumps({"providerInstances": {
        "codex": {}, "failed": {}, "disabled": {"enabled": False}, "awaiting": {},
        "signed-out": {}, "cap": {}, "unsupported": {},
    }}))
    records = {
        "codex": {"windows": [window("expired", 100, timestamp(-1)),
                              window("day", 10, timestamp(60)),
                              window("week", 75, timestamp(1440)),
                              window("unreported", True)]},
        "failed": {"windows": [window("stale", 90)], "unavailable": {"reason": "probeFailed"}},
        "disabled": {"windows": [window("day", 20)]},
        "signed-out": {"windows": [window("stale", 90)]},
        "cap": {"zeroSpendCap": True},
        "unsupported": {"unavailable": {"reason": "unsupported"}},
        "enabled-default": {"windows": [window("empty", 100, timestamp(120))]},
    }
    for name, usage in records.items():
        data = {
            "instanceId": name, "enabled": True, "usageLimits": usage,
            "auth": {"status": "unauthenticated" if name == "signed-out" else "authenticated"},
        }
        (cache / f"{name}.json").write_text(json.dumps(data))


class UsageTest(unittest.TestCase):
    def test_only_valid_quota_has_remaining_and_meter(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            fixture(root)
            items = read_providers(root)
        pick = Selection()
        pick.refresh(items)
        _, _, _, quota = pick.current(NOW)
        self.assertEqual(quota.id, "week")
        self.assertEqual(percent_text(quota.remaining(NOW)), "25%")
        self.assertEqual(filled_segments(quota.remaining(NOW)), 3)
        seen = {}
        for _ in range(4):
            _, _, _, selected = pick.current(NOW)
            seen[selected.id] = selected.remaining(NOW)
            pick.step_window(NOW)
        self.assertEqual(seen, {"expired": None, "unreported": None, "day": 90, "week": 25})
        self.assertEqual(percent_text(None), "—")
        self.assertIsNone(filled_segments(None))
        self.assertEqual(percent_text(0), "0%")
        self.assertEqual(filled_segments(0), 0)
        self.assertEqual(filled_segments(100), 12)
        self.assertEqual({item.id: item.status for item in items if not item.windows}, {
            "awaiting": "Awaiting T3 data", "disabled": "Provider disabled",
            "failed": "Usage check failed", "signed-out": "Sign-in required",
            "cap": "Zero spend cap", "unsupported": "Quota not supported",
        })
        for _ in items:
            pick.step_provider(1)
        self.assertEqual(pick.provider_id, "codex")
        pick.step_provider(-1)
        pick.step_provider(1)
        self.assertEqual(pick.current(NOW)[3].id, "week")
        self.assertEqual(pick.current(NOW + timedelta(days=2))[3].id, "expired")

    def test_windows_process_and_x11_class_names(self):
        for name in ["T3 Code (Nightly).exe", "T3 Code", "t3code", "t3-code"]:
            self.assertTrue(t3_name(name))
        self.assertFalse(t3_name("Mozilla Firefox"))
        self.assertFalse(t3_name("Pokétch"))


class SolarTest(unittest.TestCase):
    def test_representative_cities_and_solar_directions(self):
        madrid = observer_for(ZoneInfo("Europe/Madrid"), NOW)
        eastern = observer_for(ZoneInfo("US/Eastern"), NOW)
        pacific = observer_for(ZoneInfo("America/Los_Angeles"), NOW)
        self.assertAlmostEqual(madrid.latitude, 40.4, places=2)
        self.assertAlmostEqual(eastern.longitude, -74.0, places=1)
        self.assertAlmostEqual(pacific.longitude, -118.25, places=1)
        self.assertEqual(phase_at(NOW, madrid), "day")
        self.assertEqual(phase_at(NOW.replace(hour=0), madrid), "night")
        self.assertTrue(phase_at(NOW.replace(hour=6, minute=15), madrid).startswith("rise"))
        self.assertTrue(phase_at(NOW.replace(hour=18, minute=15), madrid).startswith("set"))

    def test_publish_replaces_then_keeps_same_animation(self):
        with TemporaryDirectory() as directory:
            target = Path(directory) / "theme.webp"
            day = ASSETS / "phases" / "day.webp"
            night = ASSETS / "phases" / "night.webp"
            publish(day, target)
            written = target.stat()
            publish(day, target)
            self.assertEqual(written.st_mtime_ns, target.stat().st_mtime_ns)
            publish(night, target)
            self.assertEqual(target.read_bytes(), night.read_bytes())

    def test_all_phases_are_looping_with_motion_in_the_lake(self):
        paths = set((ASSETS / "phases").glob("*.webp"))
        self.assertEqual({path.stem for path in paths}, set(PHASES))
        for path in sorted(paths):
            with self.subTest(phase=path.stem), Image.open(path) as image:
                self.assertLess(path.stat().st_size, 16 * 1024 * 1024)
                self.assertEqual(image.n_frames, 240)
                self.assertEqual(image.info["loop"], 0)
                first = image.convert("RGB")
                image.seek(120)
                delta = ImageChops.difference(first, image.convert("RGB"))
                self.assertIsNotNone(delta.getbbox())
                x0, y0, x1, y1 = delta.getbbox()
                self.assertGreaterEqual(y0, round(image.height * 0.55))
                self.assertLessEqual(y1, round(image.height * 0.87))


if __name__ == "__main__":
    unittest.main()
