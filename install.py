"""Install Sinnoh Lake Life and Pokétch for the current desktop user."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import venv

from sinnoh.paths import ASSETS, THEME_ID, atomic_write, t3_home

REPO = Path(__file__).resolve().parent


def app_dir():
    if sys.platform == "win32":
        return Path(os.environ["LOCALAPPDATA"]) / "T3 Sinnoh Lake"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "T3 Sinnoh Lake"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "t3-sinnoh-lake"


def write_atomic(target, data):
    if sys.platform != "win32" and target.is_file() and target.read_bytes() == data:
        return
    atomic_write(target, data)


def copy_tree(source, dest):
    for path in source.rglob("*"):
        if path.is_file() and path.suffix != ".pyc" and not path.name.startswith("."):
            write_atomic(dest / path.relative_to(source), path.read_bytes())


def install_theme(directory, root, python):
    themes = root / "userdata" / "themes"
    for path in ASSETS.glob("sinnoh-rift.*"):
        write_atomic(themes / path.name, path.read_bytes())
    write_atomic(themes / f"{THEME_ID}.json", (ASSETS / f"{THEME_ID}.json").read_bytes())
    command = [python, "-m", "sinnoh.solar"]
    if sys.platform == "win32":
        command.append("--force")
    subprocess.run(command, cwd=directory, check=True)


def select_theme(root):
    binary = root / "bin" / ("t3.cmd" if sys.platform == "win32" else "t3")
    command = [str(binary)] if binary.is_file() else [shutil.which("t3") or ""]
    if command[0]:
        if sys.platform == "win32" and Path(command[0]).suffix.lower() in {".bat", ".cmd"}:
            # cmd.exe strips its outer quotes, keeping the quotes on the executable path.
            quoted = f'""{command[0]}" theme set {THEME_ID}"'
            result = subprocess.run(f'cmd.exe /d /s /c {quoted}')
        else:
            result = subprocess.run([*command, "theme", "set", THEME_ID])
        if result.returncode == 0:
            return True
    print("Select “Sinnoh Rift · Lake Life” in T3 Code Settings → Appearance to activate it.",
          file=sys.stderr)
    return False


def windows_start(directory, python):
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-File", str(REPO / "install-windows.ps1"), "-Pythonw", str(python.with_name("pythonw.exe")),
         "-Launcher", str(directory / "launch.py")],
        check=True,
    )


def desktop_arg(value):
    # Desktop Entry Exec quoting has two layers. Escape literal percent as a field code.
    text = str(value).replace("%", "%%")
    quoted = "".join("\\" + ch if ch in '"\\$`' else ch for ch in text)
    return '"' + quoted.replace("\\", "\\\\") + '"'


def linux_start(directory, python):
    conf = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    launcher = directory / "launch.py"
    command = " ".join(map(desktop_arg, (python, launcher)))
    desktop = "[Desktop Entry]\nType=Application\nName=T3 Sinnoh Lake\n" + f"Exec={command}\n"
    write_atomic(conf / "autostart" / "t3-sinnoh-lake.desktop", desktop.encode("utf-8"))
    if os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"):
        subprocess.Popen([python, launcher], start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        print("Pokétch will start at the next graphical login. Run the installer from the current graphical session to start it now.")


def mac_start(directory, root, python):
    bundle = directory / "Poketch.app" / "Contents"
    binary = bundle / "MacOS" / "Poketch"
    binary.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=binary.parent) as temp:
        staged = Path(temp) / binary.name
        subprocess.run(["swiftc", "-O", str(REPO / "Poketch.swift"), "-o", staged], check=True)
        os.replace(staged, binary)
    write_atomic(bundle / "Info.plist", plistlib.dumps({
        "CFBundleExecutable": "Poketch", "CFBundleIdentifier": "local.t3code.sinnoh-usage",
        "CFBundleName": "Pokétch", "CFBundlePackageType": "APPL", "LSUIElement": True,
    }))
    jobs = {
        "local.t3code.sinnoh-lake-clock": {
            "ProgramArguments": [str(python), "-m", "sinnoh.solar"],
            "WorkingDirectory": str(directory), "StartInterval": 60,
        },
        "local.t3code.sinnoh-usage": {
            "ProgramArguments": [str(binary)], "ThrottleInterval": 15,
            "KeepAlive": {"SuccessfulExit": False},
        },
    }
    domain = f"gui/{os.getuid()}"
    for label, job in jobs.items():
        path = Path.home() / "Library" / "LaunchAgents" / (label + ".plist")
        subprocess.run(["launchctl", "bootout", f"{domain}/{label}"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        write_atomic(path, plistlib.dumps({
            "Label": label, "RunAtLoad": True, "EnvironmentVariables": {"T3CODE_HOME": str(root)},
            **job,
        }))
        subprocess.run(["launchctl", "bootstrap", domain, str(path)], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--t3-home", type=Path, default=t3_home(), help="Override the T3 data directory")
    parser.add_argument("--keep-theme", action="store_true", help="Install without changing the selected theme")
    args = parser.parse_args()
    if sys.platform not in {"darwin", "win32", "linux"}:
        parser.error(f"Unsupported platform {sys.platform}")
    if sys.version_info < (3, 11):
        parser.error("Python 3.11 or newer is required")
    root = args.t3_home.expanduser().resolve()
    os.environ["T3CODE_HOME"] = str(root)
    directory = app_dir()
    env = directory / ".venv"
    python = env / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not python.is_file():
        venv.EnvBuilder(with_pip=True).create(env)
    subprocess.run([python, "-m", "pip", "install", "--disable-pip-version-check",
                    "-r", REPO / "requirements.txt"], check=True)
    copy_tree(REPO / "sinnoh", directory / "sinnoh")
    copy_tree(ASSETS / "phases", directory / "assets" / "phases")
    write_atomic(directory / "launch.py", (REPO / "launch.py").read_bytes())
    write_atomic(directory / "t3-home.json", json.dumps(str(root)).encode("utf-8"))
    install_theme(directory, root, python)
    if sys.platform == "win32":
        windows_start(directory, python)
    elif sys.platform == "linux":
        linux_start(directory, python)
    else:
        mac_start(directory, root, python)
    activated = args.keep_theme or select_theme(root)
    print(f"Sinnoh Lake installed in {directory}")
    return 0 if activated else 2


if __name__ == "__main__":
    sys.exit(main())
