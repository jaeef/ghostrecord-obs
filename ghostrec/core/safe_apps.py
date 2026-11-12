"""Make any supported app "recording-safe" (keeps drawing while covered).

Chromium-based apps stop painting when another window covers them, so a
capture of them freezes. The fix is a set of Chromium switches that must be
present when the app STARTS — so the app has to be restarted once:

  browser   Chrome / Edge / Brave / Opera / Vivaldi
            -> restart with the switches + --restore-last-session (tabs back)
  electron  Slack / Discord / VS Code / classic Teams / ...
            -> restart with the switches (Electron passes them to Chromium)
  webview2  new Teams and other apps that host Microsoft Edge WebView2
            -> WebView2 reads extra switches from the user environment
               variable WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS; set it, then
               restart the app. Undo with clear_webview2_setting().

Nothing is ever killed silently: windows are asked to close (WM_CLOSE) first;
only when windowless background processes remain does the caller get
"needs_force" and must ask the user before calling again with force=True.
"""

import ctypes
import os
import subprocess
import time
import winreg
from ctypes import wintypes

from ghostrec.core.apps import FLAG_MARKER, RECORD_FRIENDLY_FLAGS

# Only the rendering-related switches; browser-only niceties are not needed
# (and not understood) by Electron apps.
OCCLUSION_FLAGS = [
    "--disable-features=CalculateNativeWinOcclusion",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--disable-background-timer-throttling",
]

BROWSERS = {
    "chrome.exe": "Chrome", "msedge.exe": "Microsoft Edge",
    "brave.exe": "Brave", "opera.exe": "Opera", "vivaldi.exe": "Vivaldi",
}
ELECTRON = {
    "code.exe": "VS Code", "slack.exe": "Slack", "discord.exe": "Discord",
    "teams.exe": "Microsoft Teams (classic)", "element.exe": "Element",
    "notion.exe": "Notion", "obsidian.exe": "Obsidian",
    "electron.exe": "Electron app",
}
WEBVIEW2 = {
    "ms-teams.exe": "Microsoft Teams",
}

WEBVIEW2_ENV = "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_psapi = ctypes.WinDLL("psapi", use_last_error=True)
_user32 = ctypes.WinDLL("user32", use_last_error=True)
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


# --------------------------------------------------------------------------- #
# Detection                                                                    #
# --------------------------------------------------------------------------- #

def app_kind(exe):
    """'browser' | 'electron' | 'webview2' | None for an executable name."""
    exe = (exe or "").lower()
    if exe in BROWSERS:
        return "browser"
    if exe in ELECTRON:
        return "electron"
    if exe in WEBVIEW2:
        return "webview2"
    return None


def app_name(exe):
    exe = (exe or "").lower()
    return (BROWSERS.get(exe) or ELECTRON.get(exe) or WEBVIEW2.get(exe)
            or exe.replace(".exe", "") or "this app")


def _powershell(script, timeout=10):
    try:
        return subprocess.check_output(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            text=True, stderr=subprocess.DEVNULL, timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).strip()
    except Exception:
        return ""


_cmdline_cache = {}


def _command_line(pid):
    pid = int(pid or 0)
    if pid <= 0:
        return ""
    if pid not in _cmdline_cache:
        _cmdline_cache[pid] = _powershell(
            "(Get-CimInstance Win32_Process -Filter 'ProcessId=%d')"
            ".CommandLine" % pid)
    return _cmdline_cache[pid]


_webview_cache = {}


def _webview2_children_flagged(pid):
    """True when the WebView2 browser process under ``pid`` has the switches."""
    pid = int(pid or 0)
    if pid <= 0:
        return False
    if pid not in _webview_cache:
        out = _powershell(
            "Get-CimInstance Win32_Process -Filter \"ParentProcessId=%d and "
            "Name='msedgewebview2.exe'\" | ForEach-Object { $_.CommandLine }"
            % pid)
        _webview_cache[pid] = FLAG_MARKER in out
    return _webview_cache[pid]


def is_recording_safe(pid, exe):
    """Was this app process started with the anti-occlusion switches?"""
    kind = app_kind(exe)
    if kind in ("browser", "electron"):
        return FLAG_MARKER in _command_line(pid)
    if kind == "webview2":
        return _webview2_children_flagged(pid)
    return False


def forget(pid=None):
    """Drop cached detection results (after a restart, pids change)."""
    if pid is None:
        _cmdline_cache.clear()
        _webview_cache.clear()
    else:
        _cmdline_cache.pop(int(pid), None)
        _webview_cache.pop(int(pid), None)


# --------------------------------------------------------------------------- #
# Process helpers                                                              #
# --------------------------------------------------------------------------- #

def _image_path(pid):
    h = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if _kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        _kernel32.CloseHandle(h)


def pids_for_path(path):
    """Live process ids whose image is exactly ``path`` (case-insensitive)."""
    arr = (wintypes.DWORD * 8192)()
    needed = wintypes.DWORD()
    if not _psapi.EnumProcesses(ctypes.byref(arr), ctypes.sizeof(arr),
                                ctypes.byref(needed)):
        return []
    count = needed.value // ctypes.sizeof(wintypes.DWORD)
    want = os.path.normcase(path or "")
    return [arr[i] for i in range(count)
            if arr[i] and os.path.normcase(_image_path(arr[i])) == want]


def package_app_id(pid):
    """AppUserModelID of a Store (MSIX) app process, or '' when unpackaged."""
    h = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        length = wintypes.UINT(512)
        buf = ctypes.create_unicode_buffer(512)
        rc = _kernel32.GetApplicationUserModelId(h, ctypes.byref(length), buf)
        return buf.value if rc == 0 else ""
    finally:
        _kernel32.CloseHandle(h)


def _close_windows_of(path):
    """Politely ask every top-level window of that executable to close."""
    from ghostrec.core.windows import list_windows
    want = os.path.normcase(path)
    for w in list_windows():
        if os.path.normcase(w.get("exe_path") or "") == want:
            _user32.PostMessageW(wintypes.HWND(w["hwnd"]), 0x0010, 0, 0)


def _wait_gone(path, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not pids_for_path(path):
            return True
        time.sleep(0.5)
    return not pids_for_path(path)


# --------------------------------------------------------------------------- #
# WebView2 user setting                                                        #
# --------------------------------------------------------------------------- #

def _broadcast_env_change():
    result = wintypes.DWORD()
    _user32.SendMessageTimeoutW(wintypes.HWND(0xFFFF), 0x001A, 0,
                                "Environment", 0x0002, 3000,
                                ctypes.byref(result))


def _read_user_env(name):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return ""


def webview2_setting_active(name=WEBVIEW2_ENV):
    return FLAG_MARKER in _read_user_env(name)


def set_webview2_setting(name=WEBVIEW2_ENV):
    """Add the switches to the user's WebView2 environment variable."""
    current = _read_user_env(name)
    parts = current.split()
    for flag in OCCLUSION_FLAGS:
        if flag not in parts:
            parts.append(flag)
    value = " ".join(parts)
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0,
                        winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
    os.environ[name] = value
    _broadcast_env_change()


def clear_webview2_setting(name=WEBVIEW2_ENV):
    """Remove only GhostRec's switches; keep anything else the user set."""
    parts = [p for p in _read_user_env(name).split()
             if p not in OCCLUSION_FLAGS]
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0,
                        winreg.KEY_SET_VALUE) as k:
        if parts:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, " ".join(parts))
        else:
            try:
                winreg.DeleteValue(k, name)
            except OSError:
                pass
    if parts:
        os.environ[name] = " ".join(parts)
    else:
        os.environ.pop(name, None)
    _broadcast_env_change()


# --------------------------------------------------------------------------- #
# Restart                                                                      #
# --------------------------------------------------------------------------- #

def describe_restart(win):
    """(message, detail) for the confirmation dialog; detail may be None."""
    exe = win.get("exe", "")
    kind = app_kind(exe)
    name = app_name(exe)
    if kind == "browser":
        return (f"{name} will close and reopen with your tabs restored "
                "(same profile). Unsaved text typed into web pages may be "
                "lost.", None)
    if kind == "electron":
        return (f"{name} will close and reopen. Save your work in it first.",
                None)
    if kind == "webview2":
        return (f"{name} will close and reopen. If you are in a call, you "
                "will need to rejoin.",
                f"This turns on the Windows user setting {WEBVIEW2_ENV} for "
                "apps built on Microsoft Edge WebView2. They may use a little "
                "more battery while covered. Remove it any time in "
                "Settings → Capture.")
    return f"{name} has no recording-safe mode.", None


def make_recording_safe(win, force=False, close_timeout=15):
    """Restart the app owning ``win`` with the anti-occlusion switches.

    Returns (status, message):
      "done"         restarted; pick the window again in the list
      "needs_force"  windows closed but background processes remain; ask
                     the user, then call again with force=True
      "error"        not possible (message says why)
    """
    exe = (win.get("exe") or "").lower()
    path = win.get("exe_path") or ""
    pid = int(win.get("pid") or 0)
    kind = app_kind(exe)
    name = app_name(exe)
    if kind is None:
        return "error", f"{name} has no recording-safe mode."
    if not path or not os.path.exists(path):
        return "error", f"Could not find where {name} is installed."

    aumid = package_app_id(pid) if pid else ""
    if aumid and kind != "webview2":
        return "error", (f"This is the Microsoft Store version of {name}, "
                         "which cannot be started with extra switches. "
                         "Install the regular desktop version, or use the "
                         "app in the safe browser.")

    if kind == "webview2":
        try:
            set_webview2_setting()
        except OSError as e:
            return "error", f"Could not save the WebView2 setting: {e}"

    if not force:
        _close_windows_of(path)
        if not _wait_gone(path, close_timeout):
            return "needs_force", (
                f"{name} closed its windows but is still running in the "
                "background (system tray). Quit it completely and restart "
                "it now?")
    else:
        for p in pids_for_path(path):
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p)],
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL,
                           creationflags=getattr(subprocess,
                                                 "CREATE_NO_WINDOW", 0))
        if not _wait_gone(path, 10):
            return "error", f"{name} could not be stopped."

    time.sleep(1.0)
    forget()
    try:
        if aumid:  # packaged WebView2 app (new Teams): shell activation
            subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{aumid}"])
        elif kind == "browser":
            subprocess.Popen([path, "--restore-last-session",
                              *RECORD_FRIENDLY_FLAGS], close_fds=True)
        elif kind == "electron":
            subprocess.Popen([path, *OCCLUSION_FLAGS], close_fds=True,
                             cwd=os.path.dirname(path))
        else:
            env = dict(os.environ)
            env[WEBVIEW2_ENV] = _read_user_env(WEBVIEW2_ENV)
            subprocess.Popen([path], close_fds=True, env=env,
                             cwd=os.path.dirname(path))
    except Exception as e:
        return "error", f"Could not start {name} again: {e}"
    return "done", (f"{name} restarted in recording-safe mode. Select its "
                    "window again in the list (it shows “recording-safe”).")
