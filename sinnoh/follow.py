"""Find the foreground T3 Code desktop window using native window-system APIs."""
import re


def t3_name(name):
    return re.fullmatch(r"t3[ -]?code(?:[ -]nightly| \(nightly\))?(?:\.exe)?", name,
                        re.IGNORECASE) is not None


class WindowsFollower:
    def __init__(self):
        import ctypes as c
        from ctypes import wintypes as w

        self.c, self.w = c, w
        user = c.WinDLL("user32", use_last_error=True)
        kernel = c.WinDLL("kernel32", use_last_error=True)

        def bind(lib, name, result, *args):
            function = getattr(lib, name)
            function.argtypes, function.restype = args, result
            return function

        self.foreground = bind(user, "GetForegroundWindow", w.HWND)
        self.window_pid = bind(user, "GetWindowThreadProcessId", w.DWORD, w.HWND, c.POINTER(w.DWORD))
        self.bounds = bind(user, "GetWindowRect", w.BOOL, w.HWND, c.POINTER(w.RECT))
        self.dpi = bind(user, "GetDpiForWindow", w.UINT, w.HWND)
        self.position = bind(user, "SetWindowPos", w.BOOL, w.HWND, w.HWND, c.c_int, c.c_int,
                             c.c_int, c.c_int, w.UINT)
        self.open_process = bind(kernel, "OpenProcess", w.HANDLE, w.DWORD, w.BOOL, w.DWORD)
        self.image_name = bind(kernel, "QueryFullProcessImageNameW", w.BOOL, w.HANDLE, w.DWORD,
                               w.LPWSTR, c.POINTER(w.DWORD))
        self.close = bind(kernel, "CloseHandle", w.BOOL, w.HANDLE)
        self.last_pid = None
        self.last_process = ""

    def process(self, handle):
        from pathlib import PureWindowsPath

        pid = self.w.DWORD()
        if not self.window_pid(handle, self.c.byref(pid)):
            return ""
        if pid.value == self.last_pid:
            return self.last_process
        self.last_pid, self.last_process = None, ""
        process = self.open_process(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
        if process:
            try:
                size = self.w.DWORD(32768)
                name = self.c.create_unicode_buffer(size.value)
                if self.image_name(process, 0, name, self.c.byref(size)):
                    self.last_pid = pid.value
                    self.last_process = PureWindowsPath(name.value).name
            finally:
                self.close(process)
        return self.last_process

    def place(self, panel):
        handle = self.foreground()
        if not handle:
            return False
        own = int(panel.winId())
        if handle == own:
            return panel.isVisible()
        if not t3_name(self.process(handle)):
            return False
        rect = self.w.RECT()
        if not self.bounds(handle, self.c.byref(rect)):
            return False
        scale = (self.dpi(handle) or 96) / 96
        if rect.right - rect.left < 410 * scale or rect.bottom - rect.top < 300 * scale:
            return False
        x = rect.right - round((panel.width() + 14) * scale)
        y = rect.bottom - round((panel.height() + 90) * scale)
        # Place using the native virtual-desktop coordinates, including mixed-DPI displays.
        self.position(own, -1, x, y, 0, 0, 0x0001 | 0x0010)  # TOPMOST, NOSIZE, NOACTIVATE
        return True


class X11Follower:
    def __init__(self):
        from Xlib import X, display, error

        self.connection = display.Display()
        self.root = self.connection.screen().root
        self.active = self.connection.intern_atom("_NET_ACTIVE_WINDOW")
        self.window_type = X.AnyPropertyType
        self.error = error.XError
        self.connection_error = error.ConnectionClosedError

    def place(self, panel):
        # Window switches can race any of these X11 queries with window destruction.
        try:
            prop = self.root.get_full_property(self.active, self.window_type)
            if prop is None or not len(prop.value) or not prop.value[0]:
                return False
            active_id = int(prop.value[0])
            if active_id == int(panel.winId()):
                return panel.isVisible()
            window = self.connection.create_resource_object("window", active_id)
            if not any(t3_name(name) for name in window.get_wm_class() or ()):
                return False
            rect = window.get_geometry()
            origin = self.root.translate_coords(window, 0, 0)
        except (self.error, self.connection_error):
            return False
        scale = panel.devicePixelRatioF()
        if rect.width < 410 * scale or rect.height < 300 * scale:
            return False
        panel.move(round((origin.x + rect.width) / scale) - panel.width() - 14,
                   round((origin.y + rect.height) / scale) - panel.height() - 90)
        return True
