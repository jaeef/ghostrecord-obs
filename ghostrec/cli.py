"""
Window Recorder — manual, general-purpose, one exact window at a time.

You pick ANY window from a numbered list (a class, a meeting, a stream,
anything); the script points an OBS "Window Capture" source at that EXACT
window and starts recording. The lock is window-level (by HWND):

  - whenever the window's title changes (tab badge, meeting name, ...), the
    script re-aims the capture source at the SAME window under its new title,
    so OBS can never drift onto a different window of the same program;
  - recording runs until that exact window is closed — title changes never
    stop it and never switch what is captured;
  - anything you do in OTHER windows is never recorded.

Note: all tabs of one browser window share that one window. Switching tabs
INSIDE the recorded window changes what is recorded — do other work in other
windows.

While recording it:
  - confirms OBS says the recording output is still active,
  - watches the audio level and warns if the sound goes silent,
  - stops and files the finished video into your output folder when the
    recorded window closes,
  - then shows the window picker again for the next recording — no restart
    needed. Quit with 'q' at the picker or Ctrl+C.

This is the CLI front-end (run: python record.py, or the ghostrec-cli
command after `pip install .`). The same core powers the desktop app. Requires: OBS 28+ (WebSocket server enabled),
Python packages in requirements.txt.
"""

import argparse
import json
import os
import sys
import time

import obsws_python as obsws

from ghostrec.core import config as gcfg
from ghostrec import __version__
from ghostrec.core.obs import AudioWatcher, ObsError, connect, \
    ensure_scene_and_source
from ghostrec.core.recorder import RecorderSession, sanitize_recording_name
from ghostrec.core.windows import find_window_by_title, list_windows

# Windows consoles default to cp1252 and crash on emoji / non-latin window titles.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# --------------------------------------------------------------------------- #
# Picker + recording name                                                      #
# --------------------------------------------------------------------------- #

def choose_window_interactively(windows):
    """Print a numbered list of windows and let the user pick one to record.

    Returns the chosen window dict, or None to quit ('q', Ctrl+C, or a closed
    stdin). 'r' re-lists the windows (they may have changed since the list
    was drawn).
    """
    while True:
        print("\n  Open windows:")
        print(f"  {'#':>4}  {'exe':<22}  title")
        for i, w in enumerate(windows, 1):
            print(f"  {i:>4}  {w['exe']:<22}  {w['title'][:58]}")
        try:
            raw = input("\n  Enter the # of the window to record "
                        "(r = refresh list, q = quit): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if raw == "q":
            return None
        if raw == "r":
            windows = list_windows()
            continue
        if raw.isdigit() and 1 <= int(raw) <= len(windows):
            return windows[int(raw) - 1]
        print("  Invalid choice, try again.")


def ask_recording_name():
    """Ask for a short label for this recording.

    Empty answer -> 'recording'. A timestamp is appended when the file is
    saved, so the default lands as recording_YYYY-MM-DD_HH-MM-SS.<ext>.
    Returns None if stdin closed / Ctrl+C (cancel this recording).
    """
    try:
        raw = input("  Name for this recording [recording]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    return sanitize_recording_name(raw)


def prompt_password():
    print("\nOBS WebSocket password not set.")
    print("To get it: OBS -> Tools -> WebSocket Server Settings -> copy password.")
    pwd = input("Enter password (or leave empty to skip): ").strip()
    return pwd


# --------------------------------------------------------------------------- #
# CLI reporter: prints RecorderSession events in the original log format       #
# --------------------------------------------------------------------------- #

def _hms(sec):
    sec = int(sec)
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


class CliReporter:
    """Formats session events exactly like the original record.py console."""

    def __init__(self, name, audio_enabled, audio_cfg):
        self.name = name
        self.audio_enabled = audio_enabled
        self.audio_cfg = audio_cfg
        self.status_active = False

    def _end_status(self):
        if self.status_active:
            sys.stdout.write("\n")
            self.status_active = False

    def note(self, source, text):
        self._end_status()
        print(f"[{source}] {text}")

    def event(self, ev):
        t = ev["type"]
        if t == "note":
            self.note(ev["source"], ev["text"])
        elif t == "started":
            self._end_status()
            print(f"\n[rec] ● STARTED  '{self.name}'  "
                  f"window='{ev['window_title']}'")
            print(f"[rec]   LOCKED on this exact window (hwnd {ev['hwnd']}). "
                  "Title changes re-lock it; other windows are never recorded. "
                  "Close this window to stop.\n")
        elif t == "tick":
            self._status(ev)
        elif t == "stopped":
            if ev["timed_out"]:
                self.note("rec", "WARNING: recording file may be incomplete. "
                                 f"Check {ev['src_path']}")
        # relocked / warning / stopping: covered by "note" events; the GUI
        # consumes them directly.

    def _status(self, ev):
        db = ev["audio_db"]
        if self.audio_enabled:
            limit = self.audio_cfg.get("silence_alert_seconds", 30)
            snd = f"audio {db:+5.1f}dB " \
                  f"{'OK    ' if ev['silent_for'] <= limit else 'SILENT'}"
        else:
            snd = "audio  --  "
        title = ev["pinned_title"]
        t = title if len(title) <= 32 else title[:31] + "..."
        line = f"● REC  {self.name:<20} {_hms(ev['elapsed'])}  {snd}  '{t}'"
        sys.stdout.write("\r" + line.ljust(110))
        sys.stdout.flush()
        self.status_active = True


def run_session(req, win, name, cfg, out_dir, audio):
    """Record one window to completion. Returns "done"/"interrupted"/"aborted"."""
    reporter = CliReporter(
        name,
        audio_enabled=bool(audio and cfg["audio"].get("check")),
        audio_cfg=cfg["audio"],
    )
    session = RecorderSession(req, cfg, win, name, audio, out_dir,
                              emit=reporter.event)
    session.start()
    try:
        while session.is_running:
            session.join(0.5)
    except KeyboardInterrupt:
        print(f"\n[quit] Ctrl+C — stopping & saving '{name}', "
              "do not close yet...")
        session.request_stop()
        while session.is_running:
            try:
                session.join(0.5)
            except KeyboardInterrupt:
                pass
    if session.error:
        print(f"[obs] ERROR: {session.error}\nIs OBS running with WebSocket "
              "enabled and the password in config.json correct?")
        sys.exit(1)
    return session.result


def print_banner(audio_cfg, ver, scene_name, source_name, out_dir):
    a = audio_cfg
    print("=" * 64)
    print("  WINDOW RECORDER — manual pick, one exact window per recording")
    print("=" * 64)
    print(f"  OBS            : {ver.obs_version}  "
          f"(websocket {ver.obs_web_socket_version})")
    print(f"  record scene   : {scene_name}   "
          f"(only the picked window is recorded)")
    print(f"  capture source : {source_name}")
    print(f"  save folder    : {out_dir}")
    print(f"  audio check    : "
          f"{'on, input=' + a.get('input_name', '?') if a.get('check') else 'off'}"
          f"   (warn below {a.get('silence_db', '?')}dB for "
          f"{a.get('silence_alert_seconds', '?')}s)")
    print("  window lock    : exact window (HWND) — survives title changes,")
    print("                   never drifts to other windows, stops when it closes")
    print("  loop           : after each recording the picker returns; q quits")
    print("=" * 64)


# --------------------------------------------------------------------------- #
# Main                                                                         #
# --------------------------------------------------------------------------- #

def main():
    parser = argparse.ArgumentParser(
        description="Record ONE exact window with OBS — you pick the window "
                    "from a list; other windows are never recorded.")
    parser.add_argument("--list", action="store_true",
                        help="print every open window (exe | title) and exit")
    parser.add_argument("--version", action="store_true",
                        help="print version and exit")
    parser.add_argument("--auto", action="store_true",
                        help="skip picker and record the first window matching --target")
    parser.add_argument("--target", type=str,
                        help="window title substring to match (used with --auto)")
    args = parser.parse_args()

    if args.list:
        for w in list_windows():
            print(f"{w['exe']:<26} | {w['title']}")
        return
    if args.version:
        print(f"GhostRec OBS v{__version__}")
        return

    msg = gcfg.ensure_config()  # Create default config if missing
    if msg:
        print(f"[config] {msg}")
    try:
        cfg = gcfg.validate_config(gcfg.load_config())
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"[config] ERROR: {e}")
        sys.exit(1)
    if not cfg.get("obs", {}).get("password"):
        pwd = prompt_password()
        if pwd:
            cfg["obs"]["password"] = pwd
            gcfg.save_config(cfg)
            print("[config] password saved")
        else:
            print("[obs] ERROR: password required.")
            sys.exit(1)

    out_dir = gcfg.resolve_output_folder(cfg)
    os.makedirs(out_dir, exist_ok=True)

    print("[obs] connecting...")
    try:
        req = connect(cfg)
    except ObsError as e:
        print(f"[obs] ERROR: {e}\nIs OBS running with WebSocket enabled and "
              "the password in config.json correct?")
        sys.exit(1)
    ver = req.get_version()
    print(f"[obs] connected. OBS {ver.obs_version}, "
          f"ws {ver.obs_web_socket_version}")

    def disconnect_req():
        disconnect = getattr(req, "disconnect", None)
        if disconnect:
            try:
                disconnect()
            except Exception:
                pass

    try:
        ensure_scene_and_source(
            req, cfg["capture_scene_name"], cfg["capture_source_name"],
            log=lambda tag, text: print(f"[{tag}] {text}"),
            method=cfg.get("capture", {}).get("method", 2),
            kind=cfg.get("capture", {}).get("source", "window"))
    except (ObsError, obsws.error.OBSSDKError) as e:
        print(f"[obs] ERROR: {e}")
        disconnect_req()
        sys.exit(1)

    audio = None
    if cfg["audio"].get("check"):
        audio = AudioWatcher(cfg)
        ok, err = audio.start(cfg["obs"]["host"], cfg["obs"]["port"],
                              cfg["obs"]["password"])
        if not ok:
            print(f"[audio] {err}")

    print_banner(cfg["audio"], ver, cfg["capture_scene_name"],
                 cfg["capture_source_name"], cfg["output_folder"])

    if args.auto:
        if not args.target:
            print("[auto] ERROR: --target required with --auto")
            sys.exit(1)
        win = find_window_by_title(args.target)
        if not win:
            print(f"[auto] No window found with title containing '{args.target}'")
            sys.exit(1)
        print(f"[auto] Found window: {win['exe']} | {win['title']}")
        name = args.target.replace(" ", "_")[:30] or "auto_recording"
        result = run_session(req, win, name, cfg, out_dir, audio)
        if result == "interrupted":
            print("[quit] bye.")
        elif result == "aborted":
            print("[auto] Recording aborted.")
        else:
            print("[auto] Recording saved.")
        if audio:
            audio.stop()
        disconnect_req()
        return

    try:
        while True:
            win = choose_window_interactively(list_windows())
            if win is None:
                print("[quit] bye.")
                break
            name = ask_recording_name()
            if name is None:
                print("[quit] no name given — back to the picker.\n")
                continue
            result = run_session(req, win, name, cfg, out_dir, audio)
            if result == "interrupted":
                print("[quit] bye.")
                break
            if result == "aborted":
                print("[loop] nothing recorded — picker again (q quits).\n")
            else:
                print("[loop] recording saved — picker again, pick the next "
                      "window (q quits).\n")
    except KeyboardInterrupt:
        print("\n[quit] Ctrl+C — bye.")
    finally:
        if audio:
            audio.stop()
        disconnect_req()


def run():
    """Console entry point: run the CLI and turn OBS errors into exit code 1."""
    try:
        main()
    except obsws.error.OBSSDKError as e:
        print(f"[obs] ERROR: {e}\nIs OBS running with WebSocket enabled and "
              "the password in config.json correct?")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run())
