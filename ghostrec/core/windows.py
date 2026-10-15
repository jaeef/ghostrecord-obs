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
                    "exe": exe, "exe_path": exe_path})

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
            "exe": exe, "exe_path": exe_path}


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
