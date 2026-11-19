from types import SimpleNamespace
import unittest
from unittest.mock import patch

from sinnoh.context_meter import MAX_THREADS, METER_BUDGET, meter_css
from sinnoh.remote_context import latest_records, raw_records, snapshot_percent


class LinkedContextTest(unittest.TestCase):
    def setUp(self):
        self.thread = "thread:subagent:one"
        self.projection = {
            "thread": {"id": self.thread, "activeProviderThreadId": "current"},
            "providerTurns": [],
            "providerThreads": [{"id": "current", "contextUsage": {"usedTokens": 12, "maxTokens": 100}}],
        }
        self.envelope = {"environmentId": "win", "threadId": self.thread,
                         "snapshot": {"projection": self.projection}}

    def test_active_thread_and_latest_provider_measurement(self):
        for provider, used, at in [("old", 90, "3"), ("current", 0, "2"), ("current", 24, "1")]:
            self.projection["providerTurns"].append({
                "providerThreadId": provider, "tokenUsage": {"usedTokens": used, "maxTokens": 100,
                                                           "updatedAt": at},
            })
        self.assertEqual(snapshot_percent(self.envelope, "win", self.thread), 0)
        self.assertIsNone(snapshot_percent(self.envelope, "mac", self.thread))
        self.assertIsNone(snapshot_percent(self.envelope, "win", "another"))

    def test_fallback_and_missing_capacity(self):
        self.assertEqual(snapshot_percent(self.envelope, "win", self.thread), 12)
        self.projection["providerThreads"][0]["contextUsage"]["maxTokens"] = 0
        self.assertIsNone(snapshot_percent(self.envelope, "win", self.thread))

    def test_newer_tombstone_wins(self):
        records = [SimpleNamespace(user_key=k, seq=n, value=v) for k, n, v in
                   [(b'tA', 3, b''), (b'tA', 2, b'old'), (b'tB', 1, b'live'), (b'x', 9, b'other')]]
        latest = latest_records(records, (b't',))
        self.assertEqual({k: v.value for k, v in latest.items()}, {b'tA': b'', b'tB': b'live'})

    def test_css_budget_shared_across_machines(self):
        rows = [(env, self.thread, percent) for env, percent in [('mac', 85), ('win', 12)]]
        budget = len(meter_css(rows, 100_000).encode()) + 1
        css = meter_css([rows[0], ('mac', 'older', 60), rows[1]], budget)
        for env, _, percent in rows:
            self.assertIn(f'[data-sidebar-row="{env}:{self.thread}"]', css)
            self.assertIn(f'[data-assistant-citation-environment="{env}"]', css)
            self.assertIn(f'"{percent}% of context used"', css)
        self.assertNotIn('older', css)
        self.assertLessEqual(len(css.encode()), budget)

    def test_context_meter_respects_max_threads_and_budget_cap(self):
        rows = [(env, f"thread-{i}", (i * 7) % 101)
                for env in ("mac", "win") for i in range(MAX_THREADS)]
        css = meter_css(rows, METER_BUDGET)
        self.assertLessEqual(len(css.encode()), METER_BUDGET)
        self.assertLessEqual(css.count("[data-sidebar-row="), MAX_THREADS)
        self.assertIn('[data-sidebar-row="mac:thread-0"]', css)
        self.assertIn('[data-sidebar-row="win:thread-0"]', css)
        self.assertNotIn(f'thread-{MAX_THREADS - 1}"', css)

    def test_raw_records_falls_back_to_public_raw_leveldb(self):
        sentinel = [SimpleNamespace(user_key=b"k", seq=1, value=b"v")]
        self.assertIs(raw_records(SimpleNamespace(_fetched_records=sentinel), "ignored"), sentinel)

        class FakeRawLevelDb:
            def __init__(self, path):
                self.path = path

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def iterate_records_raw(self):
                return iter(sentinel)

        fake_module = SimpleNamespace(RawLevelDb=FakeRawLevelDb)
        fake_pkg = SimpleNamespace(ccl_leveldb=fake_module)
        with patch.dict("sys.modules", {
            "ccl_chromium_reader": fake_pkg,
            "ccl_chromium_reader.ccl_leveldb": fake_module,
        }):
            self.assertEqual(raw_records(SimpleNamespace(), "store"), sentinel)
