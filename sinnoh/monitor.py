"""Float Pokétch by T3 Code on Windows and X11, or as a movable Wayland window."""
import argparse
from datetime import datetime, timedelta, timezone
import logging
import os
import re
from pathlib import Path
import sys

from PySide6.QtCore import QCoreApplication, QDateTime, QLocale, QLockFile, QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPolygon
from PySide6.QtWidgets import QApplication, QPushButton, QWidget

from .follow import WindowsFollower, X11Follower
from .paths import t3_home
from .solar import sync
from .usage import Selection, filled_segments, percent_text, read_providers

INK = "#26422b"
SEGMENTS = [(2, 0, 12, 3), (13, 2, 3, 10), (13, 14, 3, 10), (2, 23, 12, 3),
            (0, 14, 3, 10), (0, 2, 3, 10), (2, 12, 12, 3)]
DIGITS = [0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07, 0x7F, 0x6F]


def shape(painter, points, fill):
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(fill))
    painter.drawPolygon(QPolygon([QPoint(x, y) for x, y in points]))


def bar(painter, x, y, width, height, fill):
    painter.fillRect(x, y, width, height, QColor(fill))


def text(painter, value, x, y, width, height, size, *, bold=False, right=False):
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    font.setPixelSize(size)
    font.setWeight(QFont.Weight.Bold if bold else QFont.Weight.Normal)
    painter.setFont(font)
    painter.setPen(QColor(INK))
    fit = painter.fontMetrics().elidedText(value, Qt.TextElideMode.ElideRight, width)
    align = Qt.AlignmentFlag.AlignRight if right else Qt.AlignmentFlag.AlignLeft
    painter.drawText(QRect(x, y, width, height), align | Qt.AlignmentFlag.AlignVCenter, fit)


def localized_reset(reset, now):
    value = QDateTime.fromMSecsSinceEpoch(int(reset.timestamp() * 1000))
    today = QDateTime.fromMSecsSinceEpoch(int(now.timestamp() * 1000))
    loc = QLocale.system()
    short = QLocale.FormatType.ShortFormat
    pattern = re.sub(r"([:. ]s{1,2})(?![A-Za-z])", "", loc.timeFormat(short))
    time = loc.toString(value.time(), pattern)
    if value.date() == today.date():
        return time
    return loc.toString(value.date(), short) + " " + time


class Rocker(QPushButton):
    def __init__(self, parent, upper):
        super().__init__(parent)
        self.upper = upper
        self.setGeometry(207, 18 if upper else 63, 30, 44)
        label = "Previous provider" if upper else "Next provider"
        self.setAccessibleName(label)
        self.setToolTip(label)

    def paintEvent(self, event):
        with QPainter(self) as p:
            if self.upper:
                border = [(0, 0), (17, 0), (26, 4), (29, 12), (29, 44), (0, 44)]
                face = [(3, 3), (16, 3), (23, 6), (27, 13), (27, 41), (3, 41)]
            else:
                border = [(0, 0), (29, 0), (29, 32), (26, 40), (17, 44), (0, 44)]
                face = [(3, 3), (27, 3), (27, 31), (23, 38), (16, 41), (3, 41)]
            shape(p, border, "#241f29")
            shape(p, face, "#c73142" if self.isDown() else "#ef4753")
            bar(p, 3, 3, 13 if self.upper else 24, 2, "#ff8a88")
            tip, base = (18, 25) if self.upper else (26, 19)
            shape(p, [(9, base), (15, tip), (21, base)], "#852938")


class Face(QPushButton):
    def __init__(self, parent):
        super().__init__(parent)
        self.setGeometry(13, 15, 186, 96)

    def refresh(self, selection, now):
        index, provider, order, window = selection.current(now)
        self.name = provider.name if provider else "Providers"
        self.position = f"{index + 1}/{len(selection.items)}" if provider else ""
        self.remaining = window.remaining(now) if window else None
        self.percent = percent_text(self.remaining)
        self.count = len(provider.windows) if provider else 0
        self.window = window.label if window else "No quota window"
        self.pager = f"{order + 1}/{self.count} ›" if self.count > 1 else ""
        self.old = bool(provider and provider.checked and self.remaining is not None and
                        now - provider.checked > timedelta(minutes=30))
        if window is None:
            self.reset = provider.status if provider else "Awaiting T3 data"
        elif window.expired(now):
            self.reset = "Awaiting reset update"
        elif window.reset:
            self.reset = "Reset " + localized_reset(window.reset, now)
        else:
            self.reset = "Reset not reported"
        quota = f"{self.percent} remaining" if self.remaining is not None else "Quota remaining unknown"
        description = ", ".join((self.name, self.window, quota, self.reset))
        if self.old:
            description += ", cached more than 30 minutes ago"
        instruction = "Click the LCD for the next quota window." if self.count > 1 else ""
        self.setAccessibleName(description)
        self.setAccessibleDescription(instruction)
        self.setToolTip("\n".join(filter(None, (description, instruction))))
        self.update()

    def paintEvent(self, event):
        with QPainter(self) as p:
            bar(p, 0, 0, self.width(), self.height(), "#87ba7d")
            bar(p, 0, 0, self.width(), 2, "#759a68")
            text(p, self.name, 7, 5, 141, 17, 12, bold=True)
            text(p, self.position, 149, 6, 34, 15, 10, right=True)
            bar(p, 7, 24, 175, 1, "#6d9364")
            if self.remaining is None:
                bar(p, 11, 43, 25, 3, INK)
            else:
                digits = self.percent[:-1]
                for i, digit in enumerate(digits):
                    for j, (x, y, w, h) in enumerate(SEGMENTS):
                        if DIGITS[int(digit)] & (1 << j):
                            bar(p, x + 9 + i * 19, y + 32, w, h, INK)
                text(p, "%", 11 + len(digits) * 19, 39, 16, 18, 14, bold=True)
                fill = filled_segments(self.remaining)
                for i in range(12):
                    bar(p, 109 + i * 6, 46, 4, 9, INK if i < fill else "#749d6b")
            text(p, "LEFT", 109, 29, 68, 14, 9, bold=True)
            if self.old:
                text(p, "OLD", 143, 29, 37, 14, 9, right=True)
            text(p, self.window, 7, 63, 140 if self.pager else 173, 15, 10, bold=True)
            text(p, self.pager, 148, 63, 35, 14, 9, right=True)
            text(p, self.reset, 7, 81, 179, 16, 11, bold=True)


class Panel(QWidget):
    def __init__(self, root, follower=None):
        flags = Qt.WindowType.WindowStaysOnTopHint
        if follower is not None:
            flags |= (Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                      Qt.WindowType.WindowDoesNotAcceptFocus)
        super().__init__(None, flags)
        self.root = root
        self.follower = follower
        self.setWindowTitle("Pokétch")
        self.setFixedSize(240, 126)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        if follower is not None:
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.selection = Selection()
        self.face = Face(self)
        self.previous = Rocker(self, True)
        self.next = Rocker(self, False)
        self.previous.clicked.connect(lambda: self.step(-1))
        self.next.clicked.connect(lambda: self.step(1))
        self.face.clicked.connect(self.step_window)
        self.load()

    def start(self):
        if self.follower is None:
            self.show()
        else:
            self.tracking = QTimer(self, interval=600)
            self.tracking.timeout.connect(self.follow)
            self.tracking.start()
            self.follow()
        self.refreshing = QTimer(self, interval=10_000)
        self.refreshing.timeout.connect(self.load)
        self.refreshing.start()

    def follow(self):
        self.setVisible(self.follower.place(self))

    def load(self):
        self.selection.refresh(read_providers(self.root))
        self.render_selection()

    def render_selection(self):
        self.face.refresh(self.selection, datetime.now(timezone.utc))

    def step(self, delta):
        self.selection.step_provider(delta)
        self.render_selection()

    def step_window(self):
        self.selection.step_window(datetime.now(timezone.utc))
        self.render_selection()

    def paintEvent(self, event):
        with QPainter(self) as p:
            if self.follower is None:
                bar(p, 0, 0, self.width(), self.height(), "#252834")
            shape(p, [(30, 0), (173, 0), (180, 6), (218, 6), (232, 18), (232, 104),
                      (221, 119), (180, 119), (173, 126), (30, 126), (25, 120),
                      (8, 120), (1, 112), (1, 14), (9, 6), (25, 6)], "#252834")
            bar(p, 33, 1, 136, 6, "#454451")
            bar(p, 33, 119, 136, 6, "#383b46")
            shape(p, [(9, 9), (218, 9), (229, 20), (229, 102), (219, 116), (9, 116),
                      (4, 110), (4, 15)], "#a6a9b2")
            shape(p, [(11, 10), (215, 10), (224, 17), (205, 17), (205, 109),
                      (9, 109), (6, 106), (6, 16)], "#e3e2de")
            bar(p, 10, 12, 192, 102, "#343b3e")
            bar(p, 12, 14, 188, 98, "#a4b99a")
            bar(p, 7, 112, 4, 2, "#f7f5ef")


def choose_follower(app):
    if sys.platform == "win32":
        return WindowsFollower()
    if app.platformName() == "xcb" and os.environ.get("XDG_SESSION_TYPE") != "wayland":
        return X11Follower()
    return None


def clock_tick():
    try:
        sync()
    except Exception:
        logging.exception("Could not update the lake phase. Retrying in one minute.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--standalone", action="store_true", help="Show a movable Pokétch window")
    parser.add_argument("--clock-only", action="store_true", help="Update the theme without a display")
    parser.add_argument("--log", type=Path)
    args = parser.parse_args()
    logging.basicConfig(filename=args.log, level=logging.INFO, format="%(asctime)s %(message)s")
    root = t3_home().resolve()
    lock_dir = root / "userdata"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(lock_dir / "sinnoh-lake.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        logging.info("A Sinnoh Lake clock is already running for this T3 data directory.")
        return
    app = QCoreApplication([sys.argv[0]]) if args.clock_only else QApplication([sys.argv[0]])
    if not args.clock_only:
        app.setQuitOnLastWindowClosed(True)
        follower = None if args.standalone else choose_follower(app)
        mode = "standalone" if follower is None else type(follower).__name__
        logging.info("Pokétch mode: %s (%s)", mode, app.platformName())
        panel = Panel(root, follower)
        panel.start()
    clock_tick()
    timer = QTimer(app, interval=60_000)
    timer.timeout.connect(clock_tick)
    timer.start()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
