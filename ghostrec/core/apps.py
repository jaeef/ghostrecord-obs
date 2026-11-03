"""External apps that GhostRec records well, plus detection helpers.

Chrome (and other Chromium/Electron apps) stop painting themselves when their
window is covered by other windows. The OS then has no new pixels to capture,
so the recording freezes / looks soft. Starting those apps with the
occlusion-throttling disabled fixes it.

The app launcher here always uses the flags, and GhostRec can detect whether a
window you picked is already running with them.
"""

import os
import subprocess
import tempfile
import time

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]

RECORD_FRIENDLY_FLAGS = [
    # stops Windows/DWM from marking the window occluded
    "--disable-features=CalculateNativeWinOcclusion",
    # stops Chrome throttling its renderer while hidden/covered
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--disable-background-timer-throttling",
    # no first-run / "restore pages" / update infobars covering the page
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-session-crashed-bubble",
    "--disable-infobars",
    # let a test page start playing video without a click
    "--autoplay-policy=no-user-gesture-required",
]

# marker used to recognize a recording-friendly process
FLAG_MARKER = "CalculateNativeWinOcclusion"

# apps known to throttle themselves when occluded/unfocused
THROTTLE_PRONE = {
    "chrome.exe", "msedge.exe", "brave.exe", "opera.exe", "vivaldi.exe",
    "code.exe", "slack.exe", "discord.exe", "teams.exe", "ms-teams.exe",
    "zoom.exe", "whatsapp.exe", "element.exe", "electron.exe",
}

DEDICATED_PROFILE = os.path.join(
    os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(),
    "GhostRecChromeProfile")
_command_line_cache = {}


def find_chrome():
    for p in CHROME_PATHS:
        if os.path.exists(p):
            return p
    return ""


def chrome_is_running():
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq chrome.exe"],
            text=True, stderr=subprocess.DEVNULL)
        return "chrome.exe" in out
    except Exception:
        return False


def is_throttle_prone(exe):
    """True for apps that stop rendering themselves when covered."""
    return (exe or "").lower() in THROTTLE_PRONE


def process_command_line(pid):
    """Full command line of a process, or '' when unavailable."""
    if not pid or int(pid) <= 0:
        return ""
    pid = int(pid)
    if pid in _command_line_cache:
        return _command_line_cache[pid]
    ps = ("(Get-CimInstance Win32_Process -Filter 'ProcessId=%d').CommandLine"
          % pid)
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            text=True, stderr=subprocess.DEVNULL, timeout=8)
        value = out.strip()
        _command_line_cache[pid] = value
        return value
    except Exception:
        _command_line_cache[pid] = ""
        return ""


def is_record_friendly(pid):
    """True when that process was started with the anti-throttle flags."""
    return FLAG_MARKER in process_command_line(pid)


def chrome_command(url=None):
    """Build the launch command; returns (args, note)."""
    chrome = find_chrome()
    if not chrome:
        return None, "Chrome not found"
    args = [chrome, "--new-window", *RECORD_FRIENDLY_FLAGS]
    if chrome_is_running():
        # Flags are ignored by an ALREADY running browser, so start a separate
        # instance with its own profile to guarantee they take effect.
        args.insert(1, f"--user-data-dir={DEDICATED_PROFILE}")
        note = ("separate profile (sign in once in that window) because "
                "Chrome was already running")
    else:
        note = "normal profile"
    if url:
        args.append(url)
    return args, note


def launch_record_chrome(url=None):
    """Open Chrome with recording-friendly flags. Returns (ok, message)."""
    args, note = chrome_command(url)
    if args is None:
        return False, ("Chrome not found in the default locations — open "
                       "chrome://version to find its path.")
    try:
        subprocess.Popen(args, close_fds=True)
    except Exception as e:
        return False, f"could not start Chrome ({e})"
    return True, ("Chrome started with occlusion throttling disabled — "
                  f"record THAT window. [{note}]")


def close_chrome(timeout=12):
    """Ask every Chrome window to close and wait for the process to exit."""
    import time

    import win32gui

    from ghostrec.core.windows import list_windows
    for w in list_windows():
        if (w.get("exe") or "").lower() == "chrome.exe":
            try:
                win32gui.PostMessage(w["hwnd"], 0x0010, 0, 0)  # WM_CLOSE
            except Exception:
                pass
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not chrome_is_running():
            return True
        time.sleep(0.5)
    return not chrome_is_running()


def relaunch_chrome_with_flags():
    """Restart YOUR Chrome (same profile) with the anti-throttle flags.

    Flags only apply at process start, so Chrome has to be restarted. Tabs are
    restored via --restore-last-session, so no work is lost.
    """
    chrome = find_chrome()
    if not chrome:
        return False, ("Chrome not found in the default locations — open "
                       "chrome://version to find its path.")
    if chrome_is_running():
        if not close_chrome():
            return False, ("Chrome did not close (a tab may be asking for "
                           "confirmation). Close Chrome and click again.")
        time.sleep(1.0)
    args = [chrome, "--restore-last-session", *RECORD_FRIENDLY_FLAGS]
    try:
        subprocess.Popen(args, close_fds=True)
    except Exception as e:
        return False, f"could not start Chrome ({e})"
    return True, ("Chrome restarted with anti-throttle flags — same profile, "
                  "tabs restored. It now keeps recording sharply even when "
                  "other windows cover it.")
