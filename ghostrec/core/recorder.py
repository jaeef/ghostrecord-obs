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

from ghostrec.core.safe_apps import app_kind, app_name, is_recording_safe
from ghostrec.core.obs import (WINDOW_CAPTURE_WGC, ObsError, RecordingLock,
                               capture_method_for, check_scene_safety,
                               ensure_scene_and_source, fit_source_to_canvas,
                               point_source_at, stop_and_finalize)
from ghostrec.core.windows import (get_window_info, identical_windows,
                                   is_window_alive, is_window_covered,
                                   is_window_minimized, obs_window_value,
                                   same_window_identity)

# How often the pinned window's title is checked between full status polls.
# OBS binds by exact title, so a rename must be followed quickly or the source
# goes blank until the next re-aim (it never jumps to another window).
PIN_WATCH_SECONDS = 0.25


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
    suffix = 2
    while os.path.exists(dst):
        dst = os.path.join(out_dir, f"{safe}_{stamp}_{suffix}{ext}")
        suffix += 1
    # Retry move with backoff
    for attempt in range(1, 4):
        try:
            shutil.move(src_path, dst)
            _log(f"✔ saved -> {dst}")
            return dst
        except Exception as e:
            if attempt < 3:
                if os.path.exists(dst):
                    dst = os.path.join(out_dir,
                                       f"{safe}_{stamp}_{suffix}{ext}")
                    suffix += 1
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
        self._recording_started = False
        self._finalizing = False
        self._finalized = False
        self._req = req
        self._scene = ""
        self._source = ""
        self._out_dir = out_dir
        self._rec_started_at = 0.0
        self._restart_attempts = 0
        self._recording_lock = None
        self._pinned = None
        self._last_pointed = ""
        self._method = 2
        self._kind = "window"
        self._previous_scene = ""  # user's Program scene, restored afterwards

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
        # A failing log sink (e.g. a console that cannot print a symbol) must
        # never break recording control or file handling.
        try:
            self.emit({"type": "note", "source": tag, "text": text})
        except Exception:
            pass

    def _finalize(self, trigger):
        """Stop and file the owned OBS output exactly once."""
        if (not self._recording_started or self._finalized
                or self._finalizing):
            return
        self._finalizing = True
        duration = max(0.0, time.time() - self._rec_started_at)
        src_path = ""
        final_path = ""
        timed_out = True
        try:
            self.emit({"type": "stopping", "duration": duration,
                       "trigger": trigger})
            try:
                src_path, timed_out = stop_and_finalize(
                    self._req, timeout=30, log=self._log)
            except Exception as e:
                self._log("rec", f"finalization failed: {e}")
            if not timed_out and src_path:
                try:
                    final_path = file_recording(
                        src_path, self._out_dir, self.name, log=self._log)
                except Exception as e:
                    self._log("file", f"could not move recording: {e}")
            self.emit({"type": "stopped", "src_path": src_path,
                       "final_path": final_path, "duration": duration,
                       "timed_out": timed_out, "trigger": trigger})
        finally:
            self._finalized = True
            self._finalizing = False

    def _run(self):
        status = "error"
        try:
            status = self._record()
        except Exception as e:
            self.error = str(e)
            if self._recording_started:
                self._finalize("error")
            self.emit({"type": "error", "text": str(e)})
        finally:
            self._restore_previous_scene()
            if self._recording_lock:
                self._recording_lock.release()
                self._recording_lock = None
            self._result = status
            self.emit({"type": "finished", "result": status})

    def _warn_identical(self, win):
        """Warn when OBS could confuse the target with an identical twin."""
        try:
            twins = identical_windows(win)
        except Exception:
            return
        if twins:
            text = (f"{len(twins)} other window(s) share the exact title "
                    f"'{win.get('title', '')[:50]}' - OBS cannot tell them "
                    "apart. Close or rename the twin so only your target is "
                    "captured.")
            self._log("pin", f"\u26a0 {text}")
            self.emit({"type": "warning", "kind": "duplicate", "text": text})

    def _watch_pin(self):
        """Re-aim OBS the moment the pinned window is renamed.

        Returns False when the pinned window is gone (recording should stop).
        """
        hwnd = self._pinned["hwnd"]
        if not is_window_alive(hwnd):
            return False
        fresh = get_window_info(hwnd)
        if not fresh:
            # The handle can disappear between IsWindow and this lookup.
            return False
        if not same_window_identity(self.window, fresh):
            raise ObsError("the selected HWND now belongs to a different window")
        value = obs_window_value(fresh)
        if value != self._last_pointed:
            self._log("pin", "window title changed - re-locking the SAME "
                             f"window: '{fresh['title'][:60]}'")
            point_source_at(self.req, self._source, fresh, method=self._method,
                            kind=self._kind)
            self._last_pointed = value
            self.emit({"type": "relocked", "title": fresh["title"]})
            self._warn_identical(fresh)
        self._pinned = fresh
        return True

    def _restore_previous_scene(self):
        """Put OBS back on the scene the user had before recording.

        Only when OBS is not recording anymore and Program is still our
        dedicated scene — if the user switched scenes meanwhile, leave it.
        """
        prev = self._previous_scene
        if not prev:
            return
        try:
            if self.req.get_record_status().output_active:
                return
            scenes = self.req.get_scene_list()
            names = [s["sceneName"] for s in scenes.scenes]
            if (scenes.current_program_scene_name == self._scene
                    and prev in names):
                self.req.set_current_program_scene(prev)
                self._log("obs", f"restored OBS scene '{prev}'")
        except Exception as e:
            self._log("obs", f"could not restore OBS scene '{prev}': {e}")

    def _log_closed(self):
        duration = _hms(time.time() - self._rec_started_at)
        self._log("rec", f"\u25a0 STOPPED  ({duration}) - recorded window "
                         "closed. Finalizing, do not close OBS...")

    def _detect_throttle_risk(self):
        """Does the target app stop painting itself when covered?

        Chrome/Electron apps do, unless they were started with the
        anti-throttle flags. When the app is safe we stop nagging about
        occlusion warnings (they would be noise).
        """
        win = self.window
        exe = (win.get("exe") or "").lower()
        kind = app_kind(exe)
        if kind is None:
            self._throttle_safe = True
            return
        friendly = is_recording_safe(win.get("pid"), exe)
        self._throttle_safe = bool(friendly)
        self.emit({"type": "capture_advice", "exe": exe, "friendly": friendly,
                   "kind": kind, "app": app_name(exe),
                   "window_title": win.get("title", "")})
        if not friendly:
            self._log("pin", f"{app_name(exe)} stops drawing when covered — "
                             "make it recording-safe for the next recording")

    def _record(self):
        cfg = self.cfg
        scene = cfg["capture_scene_name"]
        source = cfg["capture_source_name"]
        poll = float(cfg.get("poll_seconds", 3))
        audio_cfg = cfg.get("audio", {})
        capture_cfg = cfg.get("capture", {})
        method = capture_cfg.get("method", 2)
        kind = capture_cfg.get("source", "window")
        covered_mode = bool(capture_cfg.get("covered", True))
        req = self.req
        self._scene = scene
        self._source = source

        original = get_window_info(self.window.get("hwnd"))
        if not same_window_identity(self.window, original):
            reason = "selected window closed or changed before recording started"
            self.emit({"type": "aborted", "reason": reason})
            return "aborted"
        self.window = original

        selected_method = capture_method_for(kind, method, covered_mode)
        if selected_method != int(method):
            self._log("obs", "covered-window protection enabled — using Modern "
                     "Windows Graphics Capture")
        method = selected_method

        try:
            self._recording_lock = RecordingLock()
            if not self._recording_lock.acquire():
                self._recording_lock = None
                reason = "another GhostRec recording session is already running"
                self.emit({"type": "aborted", "reason": reason})
                return "aborted"
        except OSError as e:
            self._recording_lock = None
            raise ObsError(f"could not acquire recording lock: {e}") from e

        if cfg.get("capture", {}).get("auto", True):
            self._detect_throttle_risk()
        else:
            self._throttle_safe = True

        # (re)build the dedicated single-window scene, aim it, switch to it
        ensure_scene_and_source(req, scene, source, log=self._log,
                                method=method, kind=kind)
        point_source_at(req, source, self.window, method=method, kind=kind)
        fit_source_to_canvas(req, scene, source, log=self._log)
        try:
            current = req.get_scene_list().current_program_scene_name
            if current and current != scene:
                self._previous_scene = current
        except Exception:
            pass
        req.set_current_program_scene(scene)  # record ONLY this window

        # SAFETY: verify the switch actually happened, the scene contains only
        # our source, and the source still targets this exact window.
        ok, reason = check_scene_safety(
            req, scene, source_name=source, window=self.window, kind=kind)
        if not ok:
            self._log("rec", f"✋ ABORTED: {reason}")
            self.emit({"type": "aborted", "reason": reason})
            return "aborted"

        time.sleep(1)  # let the capture bind before recording
        try:
            req.start_record()
        except obsws.error.OBSSDKError:
            # Never stop a recording that this session did not create. It may
            # belong to OBS itself or another recorder instance.
            try:
                already = bool(req.get_record_status().output_active)
            except Exception:
                already = False
            if already:
                reason = ("OBS is already recording; GhostRec will not stop an "
                          "unowned recording")
                self.emit({"type": "aborted", "reason": reason})
                return "aborted"
            raise

        self._recording_started = True
        # StartRecord returns before the output is running. Polling status
        # right away reads "inactive" and used to trigger a needless restart
        # (an extra file segment), so wait for OBS to confirm first.
        start_deadline = time.monotonic() + 10
        while time.monotonic() < start_deadline:
            try:
                if req.get_record_status().output_active:
                    break
            except Exception:
                pass
            time.sleep(0.2)
        else:
            raise ObsError("OBS did not start recording within 10 seconds")
        self._rec_started_at = time.time()
        rec_started = self._rec_started_at
        pinned = get_window_info(self.window["hwnd"]) or dict(self.window)
        self._pinned = pinned
        self._last_pointed = obs_window_value(self.window)
        self._method = int(method)
        self._kind = kind
        self._warn_identical(pinned)
        min_warn_sec = audio_cfg.get("minimize_warn_seconds", 60)
        last_min_warn = 0.0
        last_occlusion_warn = 0.0
        last_audio_warn = 0.0
        if self.audio:
            self.audio.reset()
        self.emit({"type": "started", "name": self.name,
                   "window_title": pinned["title"], "hwnd": pinned["hwnd"],
                   "pid": pinned.get("pid", 0)})

        trigger = "window_closed"
        output_active = True
        status_failures = 0
        covered_wgc_applied = int(method) == WINDOW_CAPTURE_WGC
        while True:
            if self._stop.is_set():
                trigger = "user_stop"
                break

            # 1) confirm OBS still recording; restart if it dropped
            try:
                st = req.get_record_status()
                status_failures = 0
                output_active = bool(st.output_active)
                if not output_active:
                    if self._restart_attempts >= 2:
                        raise ObsError(
                            "OBS recording output stopped repeatedly; "
                            "session stopped to avoid losing more output")
                    self._restart_attempts += 1
                    self._log("rec", "output not active — restarting record "
                                     "(the earlier segment stays in OBS's "
                                     "own recording folder)")
                    req.start_record()
                    rec_started = time.time()
                    self._rec_started_at = rec_started
                    output_active = True
            except Exception as e:
                if isinstance(e, ObsError):
                    raise
                status_failures += 1
                if status_failures >= 3:
                    raise ObsError(
                        "OBS recording status could not be read repeatedly")
                self._log("rec", f"status check failed: {e}")

            # 2) PIN: still alive? re-aim OBS if the title changed
            if not self._watch_pin():
                self._log_closed()
                break
            pinned = self._pinned
            method = self._method

            # The user or another OBS integration may have changed Program
            # scene/source after the initial setup. Stop before another scene
            # can be recorded.
            ok, reason = check_scene_safety(
                req, scene, source_name=source, window=pinned, kind=kind)
            if not ok:
                raise ObsError(f"recording safety check failed: {reason}")

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
            if covered and kind == "window" and covered_mode:
                if not covered_wgc_applied:
                    # Automatic mode can resolve to BitBlt for unknown window
                    # classes. BitBlt reads the visible desktop and therefore
                    # cannot honor the covered-window contract. Upgrade the
                    # live source to WGC as soon as occlusion is observed.
                    self._log("obs", "window covered — switching capture to "
                             "Modern (WGC) so the selected window stays "
                             "isolated")
                    point_source_at(req, source, pinned,
                                    method=WINDOW_CAPTURE_WGC, kind=kind)
                    method = WINDOW_CAPTURE_WGC
                    self._method = method
                    covered_wgc_applied = True
                if (not self._throttle_safe
                        and time.time() - last_occlusion_warn > min_warn_sec):
                    text = ("target is covered; WGC is active. This app may "
                            "still throttle its own rendering while hidden. "
                            "Use the anti-occlusion launcher if frames stop.")
                    self._log("pin", f"⚠ {text}")
                    self.emit({"type": "warning", "kind": "occluded",
                               "text": text})
                    last_occlusion_warn = time.time()

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
                       "elapsed": time.time() - self._rec_started_at,
                       "pinned_title": pinned["title"],
                       "hwnd": pinned["hwnd"],
                       "pid": pinned.get("pid", 0),
                       "output_active": output_active,
                       "minimized": minimized,
                       "covered": covered,
                       "capture_method": int(method),
                       "capture_source": kind,
                       "audio_check": bool(self.audio and audio_cfg.get("check")),
                       "audio_db": self.audio.last_db() if self.audio else -100.0,
                       "silent_for": self.audio.silent_for() if self.audio else 0.0})

            # Between full polls, watch the title closely so OBS is re-aimed
            # within PIN_WATCH_SECONDS of a rename.
            deadline = time.monotonic() + poll
            closed = False
            while not self._stop.is_set():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                if self._stop.wait(min(PIN_WATCH_SECONDS, remaining)):
                    break
                if not self._watch_pin():
                    closed = True
                    break
            if closed:
                self._log_closed()
                break

        self._finalize(trigger)
        return "interrupted" if trigger == "user_stop" else "done"
