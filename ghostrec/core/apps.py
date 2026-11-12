"""The "safe browser": a separate Chrome that keeps drawing while covered.

Chromium stops painting a covered window, so a capture of it freezes. The
switches below turn that off; they only apply when Chrome STARTS, so this
launches a dedicated instance. Restarting an app that is already running in
recording-safe mode lives in ``ghostrec.core.safe_apps``.
"""

import os
import subprocess
import tempfile

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

DEDICATED_PROFILE = os.path.join(
    os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(),
    "GhostRecChromeProfile")


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
