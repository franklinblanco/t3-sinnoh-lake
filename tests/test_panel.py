"""Exercise the real Qt buttons and, on X11, EWMH foreground tracking."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from sinnoh.monitor import Panel, choose_follower


class PanelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_clicks_tooltips_and_zero_remaining(self):
        import json
        import re

        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "userdata").mkdir()
            (root / "caches").mkdir()
            (root / "userdata" / "settings.json").write_text(json.dumps({
                "providerInstances": {"codex": {}, "awaiting": {}},
            }))
            (root / "caches" / "codex.json").write_text(json.dumps({
                "instanceId": "codex", "enabled": True, "usageLimits": {"windows": [
                    {"id": "day", "label": "Day", "usedPercent": 75},
                    {"id": "week", "label": "Week", "usedPercent": 100},
                    {"id": "unknown", "label": "Unknown", "usedPercent": None},
                ]},
            }))
            panel = Panel(root)
            panel.show()
            self.app.processEvents()
            self.assertIn("Week, 0% remaining", panel.face.accessibleName())
            self.assertIn("next quota window", panel.face.toolTip())
            self.assertEqual(panel.face.grab().toImage().pixelColor(109, 46).name(), "#749d6b")
            QTest.mouseClick(panel.face, Qt.MouseButton.LeftButton)
            self.assertIn("Quota remaining unknown", panel.face.accessibleName())
            self.assertEqual(panel.face.grab().toImage().pixelColor(109, 46).name(), "#87ba7d")
            QTest.mouseClick(panel.face, Qt.MouseButton.LeftButton)
            self.assertIn("Day, 25% remaining", panel.face.toolTip())
            meter = panel.face.grab().toImage()
            self.assertEqual(meter.pixelColor(121, 46).name(), "#26422b")
            self.assertEqual(meter.pixelColor(127, 46).name(), "#749d6b")
            QTest.mouseClick(panel.next, Qt.MouseButton.LeftButton)
            self.assertIn("Awaiting T3 data", panel.face.accessibleName())
            QTest.mouseClick(panel.previous, Qt.MouseButton.LeftButton)
            self.assertRegex(panel.face.accessibleName(), re.compile(r"Week, 0% remaining"))
            panel.close()

    @unittest.skipUnless(os.environ.get("SINNOH_TEST_X11"), "requires an X11 display")
    def test_x11_foreground_position_and_visibility(self):
        from Xlib import Xatom

        with TemporaryDirectory() as temp:
            target = QWidget()
            target.setGeometry(30, 40, 800, 600)
            target.show()
            self.app.processEvents()
            follower = choose_follower(self.app)
            self.assertIsNotNone(follower)
            # Synthesize EWMH focus and WM_CLASS on a real X11 window.
            window = follower.connection.create_resource_object("window", int(target.winId()))
            prior = follower.root.get_full_property(follower.active, Xatom.WINDOW)
            try:
                window.set_wm_class("t3code", "T3 Code")
                follower.root.change_property(follower.active, Xatom.WINDOW, 32, [window.id])
                follower.connection.sync()
                panel = Panel(Path(temp), follower)
                panel.follow()
                self.assertTrue(panel.isVisible())
                self.assertEqual((panel.x(), panel.y()), (576, 424))
                window.set_wm_class("other", "Other")
                follower.connection.sync()
                panel.follow()
                self.assertFalse(panel.isVisible())
                panel.close()
            finally:
                follower.root.change_property(follower.active, Xatom.WINDOW, 32,
                                              [] if prior is None else prior.value)
                follower.connection.flush()
                target.close()

    @unittest.skipUnless(os.environ.get("SINNOH_TEST_WAYLAND"), "requires a Wayland display")
    def test_wayland_uses_movable_standalone(self):
        self.assertIn("wayland", self.app.platformName())
        self.assertIsNone(choose_follower(self.app))


if __name__ == "__main__":
    unittest.main()
