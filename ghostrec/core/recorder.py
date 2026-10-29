"""RecorderSession — record ONE window (locked by HWND) until it closes.

Framework-agnostic state machine extracted from record.py. It runs the poll
loop in a worker thread and reports everything through an ``emit(event)``
callback. Event types (the contract with the CLI and the GUI):

  {"type": "note",     "source": tag, "text": str}      log line ("rec", "pin", ...)
  {"type": "started",  "name", "window_title", "hwnd"}
  {"type": "relocked", "title"}
  {"type": "warning",  "kind": "silence"|"minimized", "text"}
  {"type": "tick",     "elapsed", "pinned_title", "hwnd", "output_active",
                       "minimized", "audio_check", "audio_db", "silent_for"}
  {"type": "stopping", "duration", "trigger": "window_closed"|"user_stop"}
  {"type": "stopped",  "src_path", "final_path", "duration", "timed_out",
                       "trigger"}
  {"type": "aborted",  "reason"}
  {"type": "error",    "text"}
  {"type": "finished", "result": "done"|"interrupted"|"aborted"|"error"}
"""

import os
import shutil
import threading
import time
from datetime import datetime

import obsws_python as obsws

from ghostrec.core.apps import is_record_friendly, is_throttle_prone
from ghostrec.core.obs import (check_scene_safety, ensure_scene_and_source,
                               fit_source_to_canvas, point_source_at,
                               stop_and_finalize)
from ghostrec.core.windows import (get_window_info, is_window_alive,
                                   is_window_covered, is_window_minimized,
                                   obs_window_value)


def sanitize_recording_name(raw):
    """Same rule as the CLI: keep alnum + -_ + space; spaces become _."""
    safe = "".join(c for c in raw if c.isalnum() or c in "-_ ").strip()
    return safe.replace(" ", "_") or "recording"


def _hms(sec):
    sec = int(sec)
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def file_recording(src_path, out_dir, name, log=None):
    """Move OBS's output file into out_dir as '<name>_YYYY-MM-DD_HH-MM-SS.<ext>'.

    Returns the final path on success, "" on failure.
    """

    def _log(text):
        if log:
            log("file", text)

    if not src_path or not os.path.exists(src_path):
        _log(f"OBS output path missing ('{src_path}'); check OBS recording folder")
        return ""
    # Ensure file is not locked by trying to open it read-only
    try:
        with open(src_path, "rb"):
            pass
    except Exception as e:
        _log(f"File still locked or inaccessible: {e}. Skipping move.")
        return ""
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    ext = os.path.splitext(src_path)[1] or ".mkv"
    safe = "".join(c for c in name if c.isalnum() or c in "-_") or "recording"
    dst = os.path.join(out_dir, f"{safe}_{stamp}{ext}")
    # Retry move with backoff
    for attempt in range(1, 4):
        try:
            shutil.move(src_path, dst)
            _log(f"✔ saved -> {dst}")
            return dst
        except Exception as e:
            if attempt < 3:
                _log(f"move attempt {attempt} failed: {e}, retrying in 1s...")
                time.sleep(1)
            else:
                _log(f"move failed after retries ({e}); left at {src_path}")
    return ""


class RecorderSession:
    """Runs one recording in a worker thread; see module docstring for events."""

    def __init__(self, req, cfg, window, name, audio, out_dir, emit):
        self.req = req
        self.cfg = cfg
        self.window = dict(window)
        self.name = name
        self.audio = audio
        self.out_dir = out_dir
        self.emit = emit
        self.error = None
        self._stop = threading.Event()
        self._thread = None
        self._result = None
        self._throttle_safe = False  # target keeps rendering when covered

    # -- control ---------------------------------------------------------- #

    def start(self):
        self._thread = threading.Thread(target=self._run,
                                        name="ghostrec-session", daemon=True)
        self._thread.start()

    def request_stop(self):
        """Ask the session to stop; it still finalizes and saves the file."""
        self._stop.set()

    @property
    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    @property
    def result(self):
        """One of "done" | "interrupted" | "aborted" | "error", or None."""
        return self._result

    def join(self, timeout=None):
        if self._thread:
            self._thread.join(timeout)

    # -- internals --------------------------------------------------------- #

    def _log(self, tag, text):
        self.emit({"type": "note", "source": tag, "text": text})

    def _run(self):
        status = "error"
        try:
            status = self._record()
        except Exception as e:
            self.error = str(e)
            self.emit({"type": "error", "text": str(e)})
        finally:
            self._result = status
            self.emit({"type": "finished", "result": status})

    def _detect_throttle_risk(self):
        """Does the target app stop painting itself when covered?

        Chrome/Electron apps do, unless they were started with the
        anti-throttle flags. When the app is safe we stop nagging about
        occlusion warnings (they would be noise).
        """
        win = self.window
        exe = (win.get("exe") or "").lower()
        if not is_throttle_prone(exe):
            self._throttle_safe = True
            return
        friendly = is_record_friendly(win.get("pid"))
        self._throttle_safe = bool(friendly)
        self.emit({"type": "capture_advice", "exe": exe, "friendly": friendly,
                   "window_title": win.get("title", "")})
        if not friendly:
            self._log("pin", "this app stops rendering when covered — open the "
                             "recording-friendly Chrome for a sharp video")

    def _record(self):
        cfg = self.cfg
        scene = cfg["capture_scene_name"]
        source = cfg["capture_source_name"]
        poll = float(cfg.get("poll_seconds", 3))
        audio_cfg = cfg.get("audio", {})
        capture_cfg = cfg.get("capture", {})
        method = capture_cfg.get("method", 2)
        kind = capture_cfg.get("source", "window")
        req = self.req

        if cfg.get("capture", {}).get("auto", True):
            self._detect_throttle_risk()
        else:
            self._throttle_safe = True

        # (re)build the dedicated single-window scene, aim it, switch to it
        ensure_scene_and_source(req, scene, source, log=self._log,
                                method=method, kind=kind)
        point_source_at(req, source, self.window, method=method, kind=kind)
        fit_source_to_canvas(req, scene, source, log=self._log)
        req.set_current_program_scene(scene)  # record ONLY this window

        # SAFETY: verify the switch actually happened AND the scene holds
        # nothing but our window source. Otherwise we'd silently record the
        # whole screen.
        ok, reason = check_scene_safety(req, scene)
        if not ok:
            self._log("rec", f"✋ ABORTED: {reason}")
            self.emit({"type": "aborted", "reason": reason})
            return "aborted"

        time.sleep(1)  # let the capture bind before recording
        try:
            req.start_record()
        except obsws.error.OBSSDKError:
            # Most common cause: OBS is ALREADY recording (e.g. a previous run
            # of this script was killed before it could stop). Stop that
            # recording, wait for OBS to settle, then start ours.
            try:
                already = bool(req.get_record_status().output_active)
            except Exception:
                already = False
            if not already:
                raise
            self._log("rec", "OBS was already recording — stopping that first "
                             "(its file stays in OBS's recording folder)")
            try:
                old = req.stop_record()
                self._log("rec", f"previous output: "
                                 f"{getattr(old, 'output_path', '?')}")
            except Exception:
                pass
            deadline = time.time() + 15
            while time.time() < deadline:
                try:
                    if not req.get_record_status().output_active:
                        break
                except Exception:
                    break
                time.sleep(0.5)
            req.start_record()

        rec_started = time.time()
        pinned = get_window_info(self.window["hwnd"]) or dict(self.window)
        last_pointed = obs_window_value(pinned)
        min_warn_sec = audio_cfg.get("minimize_warn_seconds", 60)
        last_min_warn = 0.0
        last_audio_warn = 0.0
        if self.audio:
            self.audio.reset()
        self.emit({"type": "started", "name": self.name,
                   "window_title": pinned["title"], "hwnd": pinned["hwnd"],
                   "pid": pinned.get("pid", 0)})

        trigger = "window_closed"
        output_active = True
        while True:
            if self._stop.is_set():
                trigger = "user_stop"
                break

            # 1) confirm OBS still recording; restart if it dropped
            try:
                st = req.get_record_status()
                output_active = bool(st.output_active)
                if not output_active:
                    self._log("rec", "output not active — restarting record")
                    req.start_record()
                    rec_started = time.time()
                    output_active = True
            except Exception as e:
                self._log("rec", f"status check failed: {e}")

            # 2) PIN: the recorded window itself still alive?
            if not is_window_alive(pinned["hwnd"]):
                duration = _hms(time.time() - rec_started)
                self._log("rec", f"■ STOPPED  ({duration}) — recorded window "
                                 f"closed. Finalizing, do not close OBS...")
                break

            # 2a) refresh pinned info; re-lock OBS if the window identity changed
            fresh = get_window_info(pinned["hwnd"])
            if fresh:
                if obs_window_value(fresh) != last_pointed:
                    self._log("pin", "window title changed — re-locking the "
                                     f"SAME window: '{fresh['title'][:60]}'")
                    self.emit({"type": "relocked", "title": fresh["title"]})
                    point_source_at(req, source, fresh, method=method,
                                    kind=kind)
                    last_pointed = obs_window_value(fresh)
                pinned = fresh

            # 2b) minimized? WGC freezes minimized windows
            minimized = is_window_minimized(pinned["hwnd"])
            if (minimized
                    and time.time() - last_min_warn > min_warn_sec):
                text = ("window is MINIMIZED — recording is frozen. Restore it "
                        "(behind other windows is fine).")
                self._log("pin", f"⚠ {text}")
                self.emit({"type": "warning", "kind": "minimized", "text": text})
                last_min_warn = time.time()

            # 2b2) covered? Windows stops rendering occluded windows, so the
            # capture can go soft/frozen until the window is visible again
            covered = False if minimized else is_window_covered(pinned["hwnd"])
            if (covered and kind != "game" and not self._throttle_safe
                    and time.time() - last_min_warn > min_warn_sec):
                text = ("window is COVERED by another window — Windows stops "
                        "rendering hidden windows, so the video may look "
                        "soft/frozen. Click it once, or switch Settings → "
                        "Capture source to Game Capture.")
                self._log("pin", f"⚠ {text}")
                self.emit({"type": "warning", "kind": "occluded", "text": text})
                last_min_warn = time.time()

            # 2c) audio-alive check
            if self.audio and audio_cfg.get("check"):
                silent = self.audio.silent_for()
                limit = audio_cfg.get("silence_alert_seconds", 30)
                if silent > limit and time.time() - last_audio_warn > limit:
                    db = self.audio.last_db()
                    self._log("audio", f"⚠ WARNING: no sound for {int(silent)}s "
                                       f"(last {db:.1f} dB). Check mic/speaker output.")
                    self.emit({"type": "warning", "kind": "silence",
                               "text": f"no sound for {int(silent)}s "
                                       f"(last {db:.1f} dB). Check mic/speaker output."})
                    last_audio_warn = time.time()

            self.emit({"type": "tick",
                       "elapsed": time.time() - rec_started,
                       "pinned_title": pinned["title"],
                       "hwnd": pinned["hwnd"],
                       "pid": pinned.get("pid", 0),
                       "output_active": output_active,
                       "minimized": minimized,
                       "covered": covered,
                       "audio_check": bool(self.audio and audio_cfg.get("check")),
                       "audio_db": self.audio.last_db() if self.audio else -100.0,
                       "silent_for": self.audio.silent_for() if self.audio else 0.0})
            time.sleep(poll)

        duration = time.time() - rec_started
        self.emit({"type": "stopping", "duration": duration, "trigger": trigger})
        src_path, timed_out = stop_and_finalize(req, timeout=30, log=self._log)
        final_path = ""
        if not timed_out:
            # Do not move an incomplete file; leave it in OBS's output folder.
            final_path = file_recording(src_path, self.out_dir, self.name,
                                        log=self._log)
        self.emit({"type": "stopped", "src_path": src_path,
                   "final_path": final_path, "duration": duration,
                   "timed_out": timed_out, "trigger": trigger})
        return "interrupted" if trigger == "user_stop" else "done"
