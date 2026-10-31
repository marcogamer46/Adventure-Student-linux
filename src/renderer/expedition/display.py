"""GUI-only Windows awareness and measured display data; never change OS settings."""
import platform
import sys


class WindowsDisplay:
    """Narrow capability-checked Win32 adapter. Construct only on the GUI path."""
    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.c, self.w = ctypes, wintypes
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        try: self.shcore = ctypes.WinDLL("shcore", use_last_error=True)
        except OSError: self.shcore = None

    def function(self, dll, name, args, result):
        fn = getattr(dll, name, None) if dll else None
        if fn is not None: fn.argtypes, fn.restype = args, result
        return fn

    def awareness(self):
        c, w = self.c, self.w
        get = self.function(self.user, "GetThreadDpiAwarenessContext", [], c.c_void_p)
        read = self.function(self.user, "GetAwarenessFromDpiAwarenessContext", [c.c_void_p], c.c_int)
        if get and read:
            value = read(get())
            if value in (0, 1, 2): return value
        get = self.function(self.shcore, "GetProcessDpiAwareness", [w.HANDLE, c.POINTER(c.c_int)], c.c_long)
        if get:
            value = c.c_int(-1)
            if get(None, c.byref(value)) == 0 and value.value in (0, 1, 2): return value.value
        get = self.function(self.user, "IsProcessDPIAware", [], w.BOOL)
        return int(bool(get())) if get else None

    def enable(self, method):
        c, w = self.c, self.w
        if method == "per-monitor-v2":
            fn = self.function(self.user, "SetProcessDpiAwarenessContext", [c.c_void_p], w.BOOL)
            if fn is None: return dict(available=False, success=False, error=None)
            c.set_last_error(0); ok = bool(fn(c.c_void_p(-4)))
            return dict(available=True, success=ok, error=0 if ok else c.get_last_error())
        if method == "per-monitor-v1":
            fn = self.function(self.shcore, "SetProcessDpiAwareness", [c.c_int], c.c_long)
            if fn is None: return dict(available=False, success=False, error=None)
            result = fn(2); error = result & 0xffffffff
            return dict(available=True, success=result == 0, error=5 if error == 0x80070005 else error)
        fn = self.function(self.user, "SetProcessDPIAware", [], w.BOOL)
        if fn is None: return dict(available=False, success=False, error=None)
        c.set_last_error(0); ok = bool(fn())
        return dict(available=True, success=ok, error=0 if ok else c.get_last_error())

    def measurements(self, root):
        c, w = self.c, self.w
        ancestor = self.function(self.user, "GetAncestor", [w.HWND, w.UINT], w.HWND)
        hwnd = ancestor(root.winfo_id(), 2) if ancestor else root.winfo_id()
        result = dict(thread_awareness=self.awareness(), window_awareness=None, window_context=None, window_dpi=None,
                      process_awareness=None, monitors=[])
        process = self.function(self.shcore, "GetProcessDpiAwareness", [w.HANDLE, c.POINTER(c.c_int)], c.c_long)
        if process:
            value = c.c_int(-1); hr = process(None, c.byref(value))
            result["process_awareness"] = value.value if hr == 0 else None
            result["process_query_hresult"] = hr
        get = self.function(self.user, "GetWindowDpiAwarenessContext", [w.HWND], c.c_void_p)
        read = self.function(self.user, "GetAwarenessFromDpiAwarenessContext", [c.c_void_p], c.c_int)
        equal = self.function(self.user, "AreDpiAwarenessContextsEqual", [c.c_void_p, c.c_void_p], w.BOOL)
        if get and read:
            context = get(hwnd); result["window_awareness"] = read(context)
            if equal:
                for value, label in ((-4, "per-monitor-v2"), (-3, "per-monitor-v1"), (-2, "system-aware"), (-1, "unaware"), (-5, "unaware-gdi-scaled")):
                    if equal(context, c.c_void_p(value)): result["window_context"] = label; break
        dpi = self.function(self.user, "GetDpiForWindow", [w.HWND], w.UINT)
        if dpi: result["window_dpi"] = dpi(hwnd) or None
        class MonitorInfo(c.Structure):
            _fields_ = [("size", w.DWORD), ("monitor", w.RECT), ("work", w.RECT), ("flags", w.DWORD)]
        info = self.function(self.user, "GetMonitorInfoW", [w.HANDLE, c.POINTER(MonitorInfo)], w.BOOL)
        scale = self.function(self.shcore, "GetScaleFactorForMonitor", [w.HANDLE, c.POINTER(c.c_int)], c.c_long)
        callback_type = c.WINFUNCTYPE(w.BOOL, w.HANDLE, w.HDC, c.POINTER(w.RECT), w.LPARAM)
        monitor_from_window = self.function(self.user, "MonitorFromWindow", [w.HWND, w.DWORD], w.HANDLE)
        active = monitor_from_window(hwnd, 2) if monitor_from_window else None
        def collect(handle, _dc, _rect, _data):
            value = MonitorInfo(); value.size = c.sizeof(value)
            if info and info(handle, c.byref(value)):
                factor = c.c_int(); hr = scale(handle, c.byref(factor)) if scale else None
                def rect(r): return [r.left, r.top, r.right, r.bottom]
                result["monitors"].append(dict(primary=bool(value.flags & 1), active=handle == active,
                    bounds=rect(value.monitor), work_area=rect(value.work),
                    scale_percent=factor.value if hr == 0 else None, scale_hresult=hr))
            return True
        enumerate_monitors = self.function(self.user, "EnumDisplayMonitors", [w.HDC, c.c_void_p, callback_type, w.LPARAM], w.BOOL)
        if enumerate_monitors: enumerate_monitors(None, None, callback_type(collect), 0)
        return result


def initialize_display(*, api=None, platform_name=None):
    """Call before importing/creating Tk. Respect an existing launcher decision."""
    result = dict(policy="gui-startup-v1", before=None, after=None, attempts=[], outcome="not-windows",
                  windows_settings_changed=False, tk_scaling_forced=False)
    if (platform_name or sys.platform) != "win32": return result
    try:
        api = api or WindowsDisplay()
        result["before"] = api.awareness()
        if result["before"] in (1, 2): result["outcome"] = "existing-awareness-preserved"
        elif result["before"] is None: result["outcome"] = "query-unavailable-left-unchanged"
        else:
            result["outcome"] = "awareness-unavailable"
            for method in ("per-monitor-v2", "per-monitor-v1", "system"):
                attempt = api.enable(method); result["attempts"].append(dict(method=method, **attempt))
                if attempt["success"]: result["outcome"] = "initialized-" + method; break
                if attempt["error"] == 5: result["outcome"] = "launcher-policy-locked"; break
        result["after"] = api.awareness()
    except (OSError, AttributeError, ValueError): result["outcome"] = "query-unavailable-left-unchanged"
    return result


def inspect_display(root, fonts=None, *, startup=None):
    """Read actual window/Tk state. A caller-created root is explicitly identified."""
    result = dict(python=platform.python_version(), platform=platform.platform(), tk=str(root.tk.call("info", "patchlevel")),
        tk_scaling=float(root.tk.call("tk", "scaling")), tk_pixels_per_inch=float(root.winfo_fpixels("1i")),
        client=[root.winfo_width(), root.winfo_height()], screen=[root.winfo_screenwidth(), root.winfo_screenheight()],
        startup=startup or {"outcome": "external-root-already-created; awareness not reconfigured"},
        fonts={key: value.actual() for key, value in (fonts or {}).items()})
    if sys.platform == "win32":
        try: result.update(WindowsDisplay().measurements(root))
        except (OSError, AttributeError, ValueError): result["windows_query"] = "unavailable"
    return result


def named_fonts(root):
    from tkinter import font
    specs = {"body": (10, "normal"), "small": (9, "normal"), "strong": (11, "bold"),
             "heading": (13, "bold"), "title": (17, "bold"), "value": (15, "bold"), "technical": (10, "normal")}
    return {key: font.Font(root=root, name="Expedition" + key.title(), exists=False,
            family="Consolas" if key == "technical" else "Segoe UI", size=size, weight=weight)
            for key, (size, weight) in specs.items()}
