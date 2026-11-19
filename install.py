"""Install Sinnoh Lake Life and the in-window Pokétch for the current user."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv

from sinnoh.panel import DEFAULT_PORT, panel_url, parse_port
from sinnoh.paths import ASSETS, THEME_ID, atomic_write, t3_home
from sinnoh.startup import check_port, linux_start, mac_start, windows_start

REPO = Path(__file__).resolve().parent


def app_dir():
    if sys.platform == "win32":
        return Path(os.environ["LOCALAPPDATA"]) / "T3 Sinnoh Lake"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "T3 Sinnoh Lake"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "t3-sinnoh-lake"


def write_atomic(target, data):
    if not target.is_file() or target.read_bytes() != data:
        atomic_write(target, data)


def copy_tree(source, dest):
    expected = set()
    for path in source.rglob("*"):
        if path.is_file() and path.suffix != ".pyc" and not path.name.startswith("."):
            relative = path.relative_to(source)
            expected.add(relative)
            write_atomic(dest / relative, path.read_bytes())
    if not dest.is_dir():
        return
    for existing in sorted(dest.rglob("*"), reverse=True):
        relative = existing.relative_to(dest)
        if "__pycache__" in relative.parts and not existing.name.startswith("._"):
            continue
        if existing.is_file() and relative not in expected:
            try:
                existing.unlink()
            except OSError:
                pass
        elif existing.is_dir() and existing.name != "__pycache__":
            try:
                existing.rmdir()
            except OSError:
                pass


def install_theme(directory, root, python):
    themes = root / "userdata" / "themes"
    for pattern in ("sinnoh-rift.*", f"{THEME_ID}.json"):
        for source in ASSETS.glob(pattern):
            target = themes / source.name
            if not target.exists():
                write_atomic(target, source.read_bytes())
    subprocess.run([python, "-m", "sinnoh.solar"], cwd=directory, check=True)


def select_theme(root):
    binary = root / "bin" / ("t3.cmd" if sys.platform == "win32" else "t3")
    command = [str(binary)] if binary.is_file() else [shutil.which("t3") or ""]
    if command[0]:
        if sys.platform == "win32" and Path(command[0]).suffix.lower() in {".bat", ".cmd"}:
            # cmd.exe strips its outer quotes, keeping the quotes on the executable path.
            # Pass the path through one expansion so literal percent signs in it stay literal.
            quoted = f'""%SINNOH_T3_CLI%" theme set {THEME_ID}"'
            result = subprocess.run(f'cmd.exe /d /v:off /s /c {quoted}',
                                    env=os.environ | {"SINNOH_T3_CLI": command[0]})
        else:
            result = subprocess.run([*command, "theme", "set", THEME_ID])
        if result.returncode == 0:
            return True
    print("Select “Sinnoh Rift · Lake Life” in T3 Code Settings → Appearance to activate it.",
          file=sys.stderr)
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--t3-home", type=Path, default=t3_home(), help="Override the T3 data directory")
    parser.add_argument("--port", type=parse_port, help=f"Loopback port (default {DEFAULT_PORT})")
    parser.add_argument("--keep-theme", action="store_true", help="Keep the selected theme")
    args = parser.parse_args()
    start = {"darwin": mac_start, "win32": windows_start, "linux": linux_start}.get(sys.platform)
    if start is None:
        parser.error(f"Unsupported platform {sys.platform}")
    if sys.version_info < (3, 11):
        parser.error("Python 3.11 or newer is required")

    root = args.t3_home.expanduser().resolve()
    directory = app_dir().resolve()
    config = directory / "install.json"
    previous = json.loads(config.read_text(encoding="utf-8")) if config.is_file() else {}
    port = args.port or parse_port(previous.get("port", DEFAULT_PORT))
    check_port(port)
    os.environ["T3CODE_HOME"] = str(root)
    env = directory / ".venv"
    python = env / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not python.is_file():
        venv.EnvBuilder(with_pip=True).create(env)
    subprocess.run([python, "-m", "pip", "install", "--disable-pip-version-check",
                    "-r", REPO / "requirements.txt"], check=True)
    copy_tree(REPO / "sinnoh", directory / "sinnoh")
    copy_tree(ASSETS / "phases", directory / "assets" / "phases")
    copy_tree(ASSETS / "poketch", directory / "assets" / "poketch")
    launcher = directory / "launch.py"
    backup = directory / "legacy" / launcher.name
    if not config.exists() and launcher.is_file() and not backup.exists():
        atomic_write(backup, launcher.read_bytes())
    write_atomic(config, json.dumps({"t3_home": str(root), "port": port}).encode("utf-8"))
    write_atomic(launcher, (REPO / launcher.name).read_bytes())
    install_theme(directory, root, python)
    start(directory, python, port)
    activated = args.keep_theme or select_theme(root)
    print(f"Sinnoh Lake installed in {directory}")
    print("Pokétch appears automatically in chats using Sinnoh Rift · Lake Life.")
    print(f"The standalone panel is available at {panel_url(port)}")
    return 0 if activated else 2


if __name__ == "__main__":
    sys.exit(main())
