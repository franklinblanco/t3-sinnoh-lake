"""Verify the loopback worker, its limited read-only API, and safe migration."""
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Thread
from time import monotonic, sleep
import unittest
from unittest.mock import patch

from sinnoh import context_meter, poketch_theme
from sinnoh.panel import HOST, PANEL_PATH, USAGE_PATH, PanelServer
from sinnoh.startup import check_port, linux_stop, panel_ready, windows_task, windows_task_owned
from test_sinnoh import fixture


class PanelTest(unittest.TestCase):
    def test_floating_styles_refresh_without_losing_theme_or_context(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            theme = root / "userdata/themes/sinnoh-lake-life.json"
            theme.parent.mkdir(parents=True)
            user_css = "body { color: rebeccapurple; }"
            theme.write_text(json.dumps({"css": user_css}), encoding="utf-8")
            first = "http://127.0.0.1:47985/poketch/"
            second = "http://127.0.0.1:47986/poketch/"
            with patch.object(context_meter, "readings", return_value=("local", [])), patch.object(
                context_meter, "linked_readings", return_value=[("remote", "thread", 72)],
            ):
                context_meter.sync(root, poketch_css=poketch_theme.styles(root, 47985))
                context_meter.sync(root, poketch_css=poketch_theme.styles(root, 47986))
            css = json.loads(theme.read_bytes())["css"]
            self.assertIn(user_css, css)
            self.assertIn("72% of context used", css)
            self.assertIn(second, css)
            self.assertNotIn(first, css)
            self.assertIn("--sinnoh-faces", css)
            self.assertNotIn("\\", css)
            self.assertEqual(css.count(context_meter.PANEL_START), 1)

    def test_theme_css_avoids_crashing_scroll_pseudo_elements(self):
        forbidden = (
            "scroll-marker",
            "scroll-marker-group",
            "scroll-button",
            "scroll-state",
            "if(style(",
        )
        with TemporaryDirectory() as temp:
            root = Path(temp)
            single_css = poketch_theme.styles(root, 47984)
            self.assertIn("--sinnoh-faces: 1;", single_css)
            self.assertIn("display: none !important;", single_css)
            self.assertIn("animation: none;", single_css)
            self.assertNotIn("@keyframes sinnoh-readout", single_css)
            for token in forbidden:
                self.assertNotIn(token, single_css)

            fixture(root)
            multi_css = poketch_theme.styles(root, 47984)
            self.assertIn("@keyframes sinnoh-readout", multi_css)
            self.assertIn("scroll-timeline: --sinnoh-face-y y !important;", multi_css)
            self.assertIn("::-webkit-scrollbar-button:vertical:start:decrement", multi_css)
            self.assertIn("::-webkit-scrollbar-button:vertical:end:increment", multi_css)
            self.assertIn("pointer-events: none;", multi_css)
            self.assertNotIn("\\", multi_css)
            for token in forbidden:
                self.assertNotIn(token, multi_css)

    def test_copy_tree_prunes_stale_files_and_appledouble_artifacts(self):
        import install
        from sinnoh.paths import ASSETS

        with TemporaryDirectory() as temp:
            source = Path(temp) / "src"
            dest = Path(temp) / "dst"
            (source / "sub").mkdir(parents=True)
            (source / "keep.py").write_text("print('ok')\n", encoding="utf-8")
            (source / "sub" / "asset.json").write_text("{}", encoding="utf-8")
            (dest / "old_dir").mkdir(parents=True)
            (dest / "__pycache__").mkdir(parents=True)
            (dest / "follow.py").write_text("legacy", encoding="utf-8")
            (dest / "._keep.py").write_bytes(b"appledouble")
            (dest / "old_dir" / "stale.txt").write_text("old", encoding="utf-8")
            (dest / "__pycache__" / "keep.cpython-313.pyc").write_bytes(b"pyc")
            install.copy_tree(source, dest)
            self.assertTrue((dest / "keep.py").is_file())
            self.assertTrue((dest / "sub" / "asset.json").is_file())
            self.assertFalse((dest / "follow.py").exists())
            self.assertFalse((dest / "._keep.py").exists())
            self.assertFalse((dest / "old_dir").exists())
            self.assertTrue((dest / "__pycache__" / "keep.cpython-313.pyc").is_file())

            poketch_dest = Path(temp) / "poketch"
            poketch_dest.mkdir()
            (poketch_dest / "stale.svg").write_text("<svg/>", encoding="utf-8")
            install.copy_tree(ASSETS / "poketch", poketch_dest)
            self.assertTrue((poketch_dest / "mini.svg").is_file())
            self.assertFalse((poketch_dest / "stale.svg").exists())

    def test_only_same_origin_requests_get_quota_fields(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            fixture(root)
            file = root / "caches/codex.json"
            record = json.loads(file.read_bytes())
            record["auth"]["private"] = "SENSITIVE_FIXTURE"
            file.write_text(json.dumps(record), encoding="utf-8")
            (root / "caches/acp-auth-test.json").write_text(
                '{"instanceId":"probe","enabled":true}', encoding="utf-8",
            )
            with PanelServer(root, 0) as server:
                worker = Thread(target=server.serve_forever)
                worker.start()
                connection = HTTPConnection(HOST, server.server_port, timeout=2)
                try:
                    self.assertTrue(panel_ready(server.server_port))
                    connection.request("GET", PANEL_PATH)
                    page = connection.getresponse()
                    self.assertIn("frame-ancestors 'none'", page.getheader("Content-Security-Policy"))
                    self.assertIn(b"Previous provider", page.read())
                    connection.request("GET", PANEL_PATH + "spec.json")
                    spec_response = connection.getresponse()
                    self.assertEqual(spec_response.status, 200)
                    self.assertEqual(json.loads(spec_response.read()), poketch_theme.SPEC)
                    connection.request("GET", USAGE_PATH)
                    self.assertEqual(connection.getresponse().status, 403)
                    connection.close()
                    headers = {"X-Sinnoh-Panel": "1", "Sec-Fetch-Site": "cross-site"}
                    connection.request("GET", USAGE_PATH, headers=headers)
                    self.assertEqual(connection.getresponse().status, 403)
                    connection.close()
                    headers["Sec-Fetch-Site"] = "same-origin"
                    connection.request("GET", USAGE_PATH, headers=headers | {"Host": "elsewhere"})
                    self.assertEqual(connection.getresponse().status, 400)
                    connection.close()
                    connection.request("GET", USAGE_PATH, headers=headers)
                    response = connection.getresponse()
                    self.assertEqual(response.status, 200)
                    self.assertIsNone(response.getheader("Access-Control-Allow-Origin"))
                    data = response.read()
                    self.assertNotIn(b"SENSITIVE_FIXTURE", data)
                    providers = json.loads(data)
                    self.assertEqual(providers[0]["id"], "codex")
                    self.assertEqual(providers[0]["windows"][2]["used"], 75)
                    self.assertNotIn("probe", [provider["id"] for provider in providers])
                    connection.request("GET", "/userdata/settings.json")
                    self.assertEqual(connection.getresponse().status, 404)
                finally:
                    connection.close()
                    server.shutdown()
                    worker.join()

    def test_installed_worker_publishes_the_lake_and_stays_available(self):
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            themes = directory / "userdata/themes"
            themes.mkdir(parents=True)
            (themes / "sinnoh-lake-life.json").write_text("{}", encoding="utf-8")
            with PanelServer(directory, 0) as reservation:
                port = reservation.server_port
            launch = Path(__file__).resolve().parents[1] / "launch.py"
            (directory / launch.name).write_bytes(launch.read_bytes())
            (directory / "install.json").write_text(
                json.dumps({"t3_home": temp, "port": port}), encoding="utf-8",
            )
            env = {"PYTHONPATH": str(launch.parent)}
            command = [sys.executable, str(directory / launch.name)]
            with subprocess.Popen(command, env=os.environ | env, stderr=subprocess.PIPE) as worker:
                try:
                    until = monotonic() + 12
                    css = ""
                    while monotonic() < until and worker.poll() is None:
                        css = json.loads((themes / "sinnoh-lake-life.json").read_text()).get("css", "")
                        if "--sinnoh-faces" in css and panel_ready(port):
                            break
                        sleep(0.1)
                    self.assertIn("--sinnoh-faces", css)
                    self.assertTrue((themes / "sinnoh-lake-life.webp").is_file())
                    self.assertTrue(panel_ready(port))
                    self.assertIsNone(worker.poll())
                finally:
                    if worker.poll() is None:
                        worker.terminate()


class WindowsMigrationTest(unittest.TestCase):
    def test_port_probe_timeout_distinguishes_free_and_occupied(self):
        with socket.socket() as listener:
            listener.bind((HOST, 0))
            listener.listen()
            port = listener.getsockname()[1]
            with patch("socket.create_connection", side_effect=TimeoutError), self.assertRaises(RuntimeError):
                check_port(port)
        with patch("socket.create_connection", side_effect=TimeoutError):
            check_port(port)

    def test_task_is_owned_only_by_current_user_and_installed_launcher(self):
        directory = Path("Local AppData/T3 Sinnoh Lake")
        pythonw = directory / ".venv/Scripts/pythonw.exe"
        launcher = directory / "launch.py"
        sid = "S-1-5-21-42"
        with TemporaryDirectory() as temp:
            path = Path(temp) / "test.xml"
            windows_task(pythonw, launcher, sid).write(path, encoding="utf-16")
            xml = path.read_bytes()
        self.assertTrue(windows_task_owned(xml, pythonw, launcher, sid))
        self.assertFalse(windows_task_owned(xml, pythonw, launcher, "S-1-5-21-91"))
        self.assertFalse(windows_task_owned(xml, pythonw, launcher.with_name("other.py"), sid))


@unittest.skipUnless(sys.platform == "linux", "requires Linux process handles")
class LinuxMigrationTest(unittest.TestCase):
    def test_stops_only_the_installed_launcher(self):
        with TemporaryDirectory() as temp:
            installed = Path(temp) / "launch.py"
            other = installed.with_name("other.py")
            for script in (installed, other):
                script.write_text("from time import sleep\nsleep(60)\n", encoding="utf-8")
            command = [sys.executable, str(installed)]
            with subprocess.Popen(command) as legacy, subprocess.Popen(
                [sys.executable, str(other)]
            ) as unrelated:
                try:
                    linux_stop(command)
                    self.assertIsNotNone(legacy.poll())
                    self.assertIsNone(unrelated.poll())
                finally:
                    for worker in (legacy, unrelated):
                        if worker.poll() is None:
                            worker.terminate()
