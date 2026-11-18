"""Manage only the current user's Sinnoh Lake startup entries."""
import csv
from http.client import HTTPConnection, HTTPException
import os
from pathlib import Path
import plistlib
import select
import signal
import socket
import subprocess
from time import monotonic, sleep, time_ns
from tempfile import TemporaryDirectory
import xml.etree.ElementTree as ET

from .panel import HOST, PANEL_PATH, panel_url
from .paths import atomic_write

MAC_PANEL = "local.t3code.sinnoh-lake-panel"
MAC_CLOCK = "local.t3code.sinnoh-lake-clock"
MAC_OVERLAY = "local.t3code.sinnoh-usage"
TASK = r"\T3 Sinnoh Lake"
TASK_XML = "{http://schemas.microsoft.com/windows/2004/02/mit/task}"


def panel_ready(port):
    connection = HTTPConnection(HOST, port, timeout=1)
    try:
        connection.request("GET", PANEL_PATH)
        response = connection.getresponse()
        return response.status == 200 and response.getheader("X-Sinnoh-Lake") == "poketch"
    except (OSError, HTTPException):
        return False
    finally:
        connection.close()


def check_port(port):
    try:
        with socket.create_connection((HOST, port), timeout=1):
            pass
    except ConnectionRefusedError:
        return
    except TimeoutError:
        # Windows can take longer than the probe timeout to refuse a connection
        # to an unused loopback port. Check whether the worker can bind there.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            if os.name == "nt":
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                probe.bind((HOST, port))
            except OSError:
                pass  # An occupied port still needs the panel identity check.
            else:
                return
    if not panel_ready(port):
        raise RuntimeError(f"Port {port} is already in use. Choose a different --port.")


def wait_for_panel(port, directory):
    until = monotonic() + 12
    while monotonic() < until:
        if panel_ready(port):
            return
        sleep(0.2)
    raise RuntimeError(f"Pokétch did not start at {panel_url(port)}. See {directory / 'monitor.log'}.")


def mac_job_path(label):
    return Path.home() / "Library" / "LaunchAgents" / (label + ".plist")


def mac_job_is_loaded(label):
    return subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/{label}"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def mac_job_owned(label, commands):
    path = mac_job_path(label)
    if path.is_file():
        definition = plistlib.loads(path.read_bytes())
        if definition.get("Label") == label and definition.get("ProgramArguments") in commands:
            return True
    elif not mac_job_is_loaded(label):
        return False
    raise RuntimeError(f"Startup entry {label} has an unrecognized definition. Inspect {path}.")


def mac_stop(label):
    if mac_job_is_loaded(label):
        subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{label}"], check=True)


def mac_start(directory, python, port):
    command = [str(python), str(directory / "launch.py")]
    if mac_job_owned(MAC_PANEL, [command]):
        mac_stop(MAC_PANEL)
    path = mac_job_path(MAC_PANEL)
    atomic_write(path, plistlib.dumps({
        "Label": MAC_PANEL, "RunAtLoad": True, "ProcessType": "Background",
        "ProgramArguments": command, "ThrottleInterval": 15,
        "KeepAlive": {"SuccessfulExit": False},
    }))
    subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(path)], check=True)
    wait_for_panel(port, directory)
    jobs = {
        MAC_OVERLAY: [[str(directory / "Poketch.app/Contents/MacOS/Poketch")]],
        MAC_CLOCK: [[str(python), "-m", "sinnoh.solar"], [str(python), str(directory / "sync.py")]],
    }
    for label, commands in jobs.items():
        if mac_job_owned(label, commands):
            mac_stop(label)
            backup = directory / "legacy" / str(time_ns())
            backup.mkdir(parents=True)
            path = mac_job_path(label)
            path.rename(backup / path.name)


def desktop_arg(value):
    # Desktop Entry Exec quoting has two layers. Percent escapes a field code.
    text = str(value).replace("%", "%%")
    quoted = "".join("\\" + ch if ch in '"\\$`' else ch for ch in text)
    return '"' + quoted.replace("\\", "\\\\") + '"'


def linux_stop(command):
    expected = [os.fsencode(arg) for arg in command]
    for process in Path("/proc").iterdir():
        if not process.name.isascii() or not process.name.isdecimal():
            continue
        try:
            if process.stat().st_uid != os.getuid():
                continue
            cmdline = process / "cmdline"
            if cmdline.read_bytes().rstrip(b"\0").split(b"\0")[:2] != expected:
                continue
            fd = os.pidfd_open(int(process.name))
            try:
                # Validate again after obtaining the handle so PID reuse cannot stop an unrelated process.
                if cmdline.read_bytes().rstrip(b"\0").split(b"\0")[:2] == expected:
                    signal.pidfd_send_signal(fd, signal.SIGTERM)
                    poller = select.poll()
                    poller.register(fd, select.POLLIN)
                    if not poller.poll(5000):
                        raise RuntimeError("The previous Sinnoh Lake process did not stop.")
            finally:
                os.close(fd)
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue


def linux_start(directory, python, port):
    conf = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    launcher = directory / "launch.py"
    command = [str(python), str(launcher)]
    exec_line = "Exec=" + " ".join(map(desktop_arg, command))
    path = conf / "autostart" / "t3-sinnoh-lake.desktop"
    if path.is_file():
        if exec_line not in path.read_text(encoding="utf-8").splitlines():
            raise RuntimeError(f"Unrecognized startup entry at {path}. Inspect its Exec command.")
    else:
        desktop = "[Desktop Entry]\nType=Application\nName=T3 Sinnoh Lake\n" + exec_line + "\n"
        atomic_write(path, desktop.encode())
    linux_stop(command)
    subprocess.Popen(command, start_new_session=True, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    wait_for_panel(port, directory)


def windows_task(pythonw, launcher, sid):
    task = ET.Element("Task", version="1.2", xmlns=TASK_XML[1:-1])
    trigger = ET.SubElement(ET.SubElement(task, "Triggers"), "LogonTrigger")
    ET.SubElement(trigger, "UserId").text = sid
    principal = ET.SubElement(ET.SubElement(task, "Principals"), "Principal", id="User")
    ET.SubElement(principal, "UserId").text = sid
    ET.SubElement(principal, "LogonType").text = "InteractiveToken"
    ET.SubElement(principal, "RunLevel").text = "LeastPrivilege"
    settings = ET.SubElement(task, "Settings")
    for key, value in {
        "MultipleInstancesPolicy": "IgnoreNew", "DisallowStartIfOnBatteries": "false",
        "StopIfGoingOnBatteries": "false", "ExecutionTimeLimit": "PT0S",
    }.items():
        ET.SubElement(settings, key).text = value
    action = ET.SubElement(ET.SubElement(task, "Actions", Context="User"), "Exec")
    ET.SubElement(action, "Command").text = str(pythonw)
    ET.SubElement(action, "Arguments").text = f'"{launcher}"'
    ET.SubElement(action, "WorkingDirectory").text = str(launcher.parent)
    return ET.ElementTree(task)


def windows_task_owned(xml, pythonw, launcher, sid):
    # schtasks may emit UTF-16 XML through a pipe or convert it to the console code page.
    if xml.startswith(b"\xff\xfe") or xml.startswith(b"<\x00"):
        text = xml.decode("utf-16" if xml.startswith(b"\xff\xfe") else "utf-16-le")
    else:
        try:
            text = xml.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = xml.decode("oem")
    task = ET.fromstring(text)
    ns = {"t": TASK_XML[1:-1]}
    principals = task.findall("t:Principals/t:Principal", ns)
    actions = task.find("t:Actions", ns)
    if len(principals) != 1 or actions is None or len(actions) != 1:
        return False
    principal, action = principals[0], actions[0]
    return (principal.findtext("t:UserId", namespaces=ns) == sid
            and action.tag == TASK_XML + "Exec"
            and os.path.normcase(action.findtext("t:Command", "", ns)) == os.path.normcase(str(pythonw))
            and os.path.normcase(action.findtext("t:Arguments", "", ns).strip('"')) == os.path.normcase(str(launcher)))


def windows_start(directory, python, port):
    pythonw = python.with_name("pythonw.exe")
    launcher = directory / "launch.py"
    identity = subprocess.check_output(["whoami.exe", "/user", "/fo", "csv", "/nh"])
    sid = next(csv.reader(identity.decode("oem").splitlines()))[1]
    scheduler = ["schtasks.exe"]
    existing = subprocess.run([*scheduler, "/Query", "/TN", TASK, "/XML"], capture_output=True)
    if existing.returncode == 0:
        if not windows_task_owned(existing.stdout, pythonw, launcher, sid):
            raise RuntimeError(f"Scheduled task {TASK} has an unrecognized owner or action.")
        # The new launcher uses the same task action as the Qt installer.
        subprocess.run([*scheduler, "/End", "/TN", TASK], check=True)
    else:
        with TemporaryDirectory() as temp:
            definition = Path(temp) / "sinnoh.xml"
            windows_task(pythonw, launcher, sid).write(definition, encoding="utf-16")
            subprocess.run([*scheduler, "/Create", "/TN", TASK, "/XML", definition],
                           stdin=subprocess.DEVNULL, check=True)
    subprocess.run([*scheduler, "/Run", "/TN", TASK], check=True)
    wait_for_panel(port, directory)
