"""Win32 window enumeration helpers (no UI, no prints).

Extracted from the original record.py — behavior is byte-compatible:
windows are listed by (title, class, exe) and the OBS window value is
``title:class:exe`` with OBS's own escaping rules.
"""

import ctypes
import ctypes.wintypes as wt
import os

import win32gui
import win32process

_QueryFullProcessImageName = ctypes.windll.kernel32.QueryFullProcessImageNameW
_OpenProcess = ctypes.windll.kernel32.OpenProcess
_CloseHandle = ctypes.windll.kernel32.CloseHandle
_pid_exe_cache = {}
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def _exe_info_for_pid(pid):
    """Return (exe_basename, full_path) for a pid, cached. ('', '') on failure."""
    if pid in _pid_exe_cache:
        return _pid_exe_cache[pid]
    h = _OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        _pid_exe_cache[pid] = ("", "")
        return _pid_exe_cache[pid]
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wt.DWORD(1024)
        if _QueryFullProcessImageName(h, 0, buf, ctypes.byref(size)):
            full = buf.value
            info = (os.path.basename(full), full)
            _pid_exe_cache[pid] = info
            return info
        _pid_exe_cache[pid] = ("", "")
        return _pid_exe_cache[pid]
    finally:
        _CloseHandle(h)


def list_windows():
    """Return list of dicts {hwnd, title, cls, exe, exe_path} for visible
    titled windows."""
    out = []

    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if not title.strip():
            return
        try:
            cls = win32gui.GetClassName(hwnd)
        except Exception:
            cls = ""
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        exe, exe_path = _exe_info_for_pid(pid)
        out.append({"hwnd": hwnd, "title": title, "cls": cls,
                    "exe": exe, "exe_path": exe_path, "pid": pid})

    win32gui.EnumWindows(cb, None)
    return out


def get_window_info(hwnd):
    """Return {hwnd, title, cls, exe, exe_path} for a live window handle, or None."""
    if not win32gui.IsWindow(hwnd):
        return None
    try:
        title = win32gui.GetWindowText(hwnd)
        cls = win32gui.GetClassName(hwnd)
    except Exception:
        return None
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    exe, exe_path = _exe_info_for_pid(pid)
    return {"hwnd": hwnd, "title": title, "cls": cls,
            "exe": exe, "exe_path": exe_path, "pid": pid}


def same_window_identity(expected, current):
    """Return whether two snapshots still identify the same native window.

    Titles are intentionally excluded because title changes are part of the
    recorder's normal re-lock behavior. HWND reuse, process changes, class
    changes, or executable changes are not accepted.
    """
    if not expected or not current:
        return False
    if expected.get("hwnd") != current.get("hwnd"):
        return False
    if expected.get("pid") and current.get("pid") != expected.get("pid"):
        return False
    if expected.get("cls") and current.get("cls") != expected.get("cls"):
        return False
    if expected.get("exe") and current.get("exe"):
        if current["exe"].lower() != expected["exe"].lower():
            return False
    if expected.get("exe_path") and current.get("exe_path"):
        if current["exe_path"].lower() != expected["exe_path"].lower():
            return False
    return True


def is_window_alive(hwnd):
    """True while the window handle still exists."""
    return bool(win32gui.IsWindow(hwnd))


def is_window_minimized(hwnd):
    """True when the window is minimized (WGC capture freezes then)."""
    return bool(win32gui.IsIconic(hwnd))


def _obs_escape(s):
    """Escape a component the way OBS stores window-capture strings."""
    return s.replace("#", "#22").replace(":", "#3A")


def obs_window_value(w):
    """Build the 'title:class:exe' value OBS window_capture expects."""
    return f"{_obs_escape(w['title'])}:{_obs_escape(w['cls'])}:{_obs_escape(w['exe'])}"


def find_window_by_title(target):
    """Return first window dict whose title contains target (case-insensitive)."""
    target_lower = target.lower()
    for w in list_windows():
        if target_lower in w["title"].lower():
            return w
    return None


# --------------------------------------------------------------------------- #
# Z-order control (keeps the recorded window unoccluded -> sharp capture)      #
# --------------------------------------------------------------------------- #

def is_window_covered(hwnd):
    """True when another (foreground) window overlaps the target window.

    A fully covered window is "occluded" by Windows: the app stops producing new
    frames, so a capture of it can go soft or freeze until it is visible again.
    Heuristic: the foreground window is not us and its rectangle overlaps ours.
    """
    try:
        fg = ctypes.windll.user32.GetForegroundWindow()
        if not fg or fg == hwnd:
            return False
        a = win32gui.GetWindowRect(hwnd)
        b = win32gui.GetWindowRect(fg)
    except Exception:
        return False
    return (a[0] < b[2] and b[0] < a[2]
            and a[1] < b[3] and b[1] < a[3])


# --------------------------------------------------------------------------- #
# Z-order (READ-ONLY)                                                                           #
# --------------------------------------------------------------------------- #
# GhostRec never raises windows above your work: pinning the recorded
# window was removed at the user's request because it blocked normal use
# of the desktop. Only a read-only check is kept, so the app can tell if
# a window was pinned by the user themselves.
GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
_user32.GetWindowLongPtrW.restype = ctypes.c_longlong


def is_window_on_top(hwnd):
    """Read-only: True when the window carries the TOPMOST flag."""
    style = int(_user32.GetWindowLongPtrW(ctypes.c_void_p(hwnd), GWL_EXSTYLE))
    return bool(style & WS_EX_TOPMOST)
