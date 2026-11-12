"""OBS WebSocket operations — connect, scene/source setup, recording control.

Extracted from record.py. Functions take an optional ``log(tag, text)``
callback instead of printing; callers (CLI / GUI) format or route the text.

Tags used: "obs" (scene/source setup), "rec" (recording control),
"file" (output file handling, see recorder.file_recording).
"""

import math
import os
import socket
import subprocess
import threading
import time
import ctypes

import obsws_python as obsws


class ObsError(Exception):
    """Human-readable OBS connection/operation error."""


class RecordingLock:
    """Cross-process Windows mutex for GhostRec's single-recording rule."""

    _NAME = "Local\\GhostRecOBSRecording"

    def __init__(self):
        self._handle = None
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32.CreateMutexW.argtypes = [
            ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        self._kernel32.CreateMutexW.restype = ctypes.c_void_p
        self._kernel32.ReleaseMutex.argtypes = [ctypes.c_void_p]
        self._kernel32.ReleaseMutex.restype = ctypes.c_bool
        self._kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        self._kernel32.CloseHandle.restype = ctypes.c_bool

    def acquire(self):
        """Acquire the named mutex; return False if another owner has it."""
        ctypes.set_last_error(0)
        handle = self._kernel32.CreateMutexW(None, True, self._NAME)
        if not handle:
            raise OSError(ctypes.get_last_error(), "could not create recording lock")
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            self._kernel32.CloseHandle(handle)
            return False
        self._handle = handle
        return True

    def release(self):
        if self._handle:
            self._kernel32.ReleaseMutex(self._handle)
            self._kernel32.CloseHandle(self._handle)
            self._handle = None


def _friendly_connect_error(e, host, port):
    msg = str(e)
    low = msg.lower()
    if "10061" in msg or "refused" in low:
        return (f"could not connect to {host}:{port} — is OBS running with "
                f"the WebSocket server enabled?")
    if "authentication" in low or "password" in low or "401" in msg:
        return "authentication failed — check the WebSocket password in Settings."
    return msg or type(e).__name__


def connect(cfg, timeout=5):
    """Connect to OBS and return a ReqClient, or raise ObsError."""
    obs = cfg.get("obs", {})
    host = obs.get("host", "127.0.0.1")
    port = int(obs.get("port", 4455))
    password = obs.get("password", "")
    try:
        return obsws.ReqClient(host=host, port=port, password=password,
                               timeout=timeout)
    except Exception as e:
        raise ObsError(_friendly_connect_error(e, host, port)) from e


def test_connection(host, port, password, timeout=4):
    """Try to connect; returns the OBS version string or raises ObsError."""
    req = None
    try:
        req = obsws.ReqClient(host=host, port=int(port), password=password,
                              timeout=timeout)
        return req.get_version().obs_version
    except Exception as e:
        raise ObsError(_friendly_connect_error(e, host, port)) from e
    finally:
        if req:
            disconnect = getattr(req, "disconnect", None)
            if disconnect:
                try:
                    disconnect()
                except Exception:
                    pass


# --------------------------------------------------------------------------- #
# OBS process helpers                                                          #
# --------------------------------------------------------------------------- #

OBS_PATHS = [
    r"C:\Program Files\obs-studio\bin\64bit\obs64.exe",
    r"C:\Program Files (x86)\obs-studio\bin\64bit\obs64.exe",
]

WINDOW_CAPTURE_WGC = 2

# OBS ``priority`` values (libobs window-helpers.h ``enum window_priority``):
#   0 = CLASS  "Match title, otherwise find window of same type"
#   1 = TITLE  "Window title must match"
#   2 = EXE    "Match title, otherwise find window of same executable"
# CLASS/EXE fall back to ANOTHER window of the same app when the title does not
# match — e.g. a different Chrome window during a title change. That breaks the
# "only this window" contract, so GhostRec always uses TITLE and re-aims the
# source itself the moment the pinned window is renamed.
WINDOW_PRIORITY_TITLE = 1


def is_port_listening(port, host="127.0.0.1", timeout=0.4):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex((host, int(port))) == 0
    except Exception:
        return False


def wait_for_port(port, timeout=30):
    start = time.time()
    while time.time() - start < timeout:
        if is_port_listening(port):
            return True
        time.sleep(1)
    return False


def launch_obs():
    """Start OBS minimized from the default install location. True on success."""
    for p in OBS_PATHS:
        if os.path.exists(p):
            subprocess.Popen([p, "--startminimized", "--locale", "en-US"],
                             cwd=os.path.dirname(p), shell=False)
            return True
    return False


# --------------------------------------------------------------------------- #
# Scene / source setup                                                         #
# --------------------------------------------------------------------------- #

def source_kind_name(kind):
    """'window' | 'game' -> OBS input kind."""
    if kind == "window":
        return "window_capture"
    if kind == "game":
        return "game_capture"
    raise ValueError(f"unsupported capture source: {kind!r}")


def capture_method_for(kind, method, covered=True):
    """Choose the OBS window method for the configured capture contract."""
    selected = int(method)
    if kind == "window" and covered:
        # BitBlt can read whatever is visibly painted on the desktop. It cannot
        # guarantee that a browser placed above the target stays out of the
        # recording, so covered-window mode always uses Modern WGC.
        return WINDOW_CAPTURE_WGC
    return selected


def ensure_scene_and_source(req, scene_name, source_name, log=None,
                            method=2, kind="window"):
    """Make a DEDICATED scene that contains ONLY the capture source.

    Recording captures whatever scene is on Program. If we recorded your normal
    scene it would also grab any Display/Screen Capture sitting in it (= your
    whole screen). So we use our own scene with just the one window in it —
    nothing else you do on screen is recorded.

    ``kind``:
      "window" -> window_capture. ``method``: 0 = automatic, 1 = BitBlt (sharp
                  but shows occluding content), 2 = Windows Graphics Capture
                  (captures covered windows; can look soft while fully covered
                  because Windows stops rendering occluded windows).
      "game"   -> game_capture. Renders the app offscreen, so it stays sharp
                  even when the window is completely covered by other apps.
    """

    def _log(msg):
        if log:
            log("obs", msg)

    want_kind = source_kind_name(kind)
    scenes = [s["sceneName"] for s in req.get_scene_list().scenes]
    if scene_name not in scenes:
        _log(f"creating dedicated scene '{scene_name}'")
        req.create_scene(scene_name)

    # Never delete arbitrary user scene items. A configured scene must be empty,
    # or already contain exactly the configured GhostRec source.
    items = req.get_scene_item_list(scene_name).scene_items
    if items and not (len(items) == 1
                      and items[0].get("sourceName") == source_name):
        names = [item.get("sourceName", "?") for item in items]
        raise ObsError(
            f"dedicated scene '{scene_name}' contains other sources: {names}; "
            "clear it or choose another scene name")

    # OBS input names are GLOBAL. If the source exists (e.g. left in another
    # scene from a previous run), do not repoint it behind the owner's back.
    existing = {i["inputName"]: i.get("inputKind", "")
                for i in req.get_input_list().inputs}
    if source_name in existing:
        if existing[source_name] and existing[source_name] != want_kind:
            raise ObsError(
                f"source '{source_name}' already exists as "
                f"'{existing[source_name]}'; choose another source name")

        for other_scene in scenes:
            if other_scene == scene_name:
                continue
            other_items = req.get_scene_item_list(other_scene).scene_items
            if any(item.get("sourceName") == source_name
                   for item in other_items):
                raise ObsError(
                    f"source '{source_name}' is used by OBS scene "
                    f"'{other_scene}'; choose another source name")

    if source_name in existing:
        if not items:
            _log(f"adding existing source '{source_name}' to '{scene_name}'")
            req.create_scene_item(scene_name, source_name, True)
    else:
        _log(f"creating source '{source_name}' in '{scene_name}'")
        settings = ({"capture_mode": "window", "capture_cursor": True,
                     "priority": WINDOW_PRIORITY_TITLE}
                    if want_kind == "game_capture"
                    else {"method": int(method), "cursor": True,
                          "client_area": True})
        req.create_input(scene_name, source_name, want_kind, settings, True)
    return scene_name


def fit_source_to_canvas(req, scene_name, source_name, log=None):
    """Scale/position the window source to fill the recording canvas."""
    try:
        vs = req.get_video_settings()
        cw, ch = vs.base_width, vs.base_height
        item_id = req.get_scene_item_id(scene_name, source_name).scene_item_id
        req.set_scene_item_transform(scene_name, item_id, {
            "boundsType": "OBS_BOUNDS_SCALE_INNER",
            "boundsWidth": cw, "boundsHeight": ch,
            "boundsAlignment": 0, "positionX": 0, "positionY": 0,
            "alignment": 5,  # top-left
        })
    except Exception as e:
        if log:
            log("obs", f"fit-to-canvas skipped: {e}")


def point_source_at(req, source_name, window, method=2, kind="window"):
    """Aim the capture source at ONE exact window — never anything else.

    We pass the full 'title:class:exe' of the selected window with the
    "title must match" priority, so OBS never falls back to another window of
    the same program. The caller re-points the source as soon as the pinned
    window's title changes (see RecorderSession's fast pin watch).
    """
    from ghostrec.core.windows import obs_window_value
    value = obs_window_value(window)
    if source_kind_name(kind) == "game_capture":
        settings = {"capture_mode": "window", "window": value,
                    "capture_cursor": True, "priority": WINDOW_PRIORITY_TITLE}
    else:
        settings = {"window": value, "priority": WINDOW_PRIORITY_TITLE,
                    "method": int(method), "cursor": True,
                    # Client-area WGC avoids recording the outer frame while
                    # still reading the compositor surface when covered.
                    "client_area": True}
    req.set_input_settings(source_name, settings, True)


def check_scene_safety(req, scene_name, source_name=None, window=None,
                       kind="window"):
    """Verify the program scene is clean before recording.

    Returns (ok, reason). ok=False means we must NOT start recording,
    otherwise the whole screen could be captured.
    """
    try:
        expected_kind = source_kind_name(kind)
    except ValueError as e:
        return False, str(e)
    cur = req.get_scene_list().current_program_scene_name
    items = req.get_scene_item_list(scene_name).scene_items
    if cur != scene_name or len(items) != 1:
        names = [i.get("sourceName", "?") for i in items]
        return (False,
                f"scene not clean (program='{cur}', items={names}). "
                f"Not recording — would capture whole screen.")

    item = items[0]
    item_name = item.get("sourceName") or item.get("inputName")
    item_kind = item.get("inputKind", "")
    if source_name and item_name != source_name:
        return False, (f"scene item '{item_name}' is not GhostRec source "
                       f"'{source_name}'")
    if item_kind != expected_kind:
        return False, (f"scene source '{item_name}' has kind '{item_kind}', "
                       f"expected '{expected_kind}'")

    if window is not None and source_name:
        try:
            settings_resp = req.get_input_settings(source_name)
            settings = getattr(settings_resp, "input_settings", None)
            if settings is None and isinstance(settings_resp, dict):
                settings = settings_resp.get("inputSettings", {})
            settings = settings or {}
        except Exception as e:
            return False, f"cannot verify capture target: {e}"
        from ghostrec.core.windows import obs_window_value
        if settings.get("window") != obs_window_value(window):
            return False, "capture source no longer targets the selected window"
        if int(settings.get("priority", -1)) !=                 WINDOW_PRIORITY_TITLE:
            return False, ("capture source may fall back to another window "
                           "(OBS match priority is not 'title must match')")
    return True, ""


# --------------------------------------------------------------------------- #
# Recording control                                                            #
# --------------------------------------------------------------------------- #

def stop_and_finalize(req, timeout=30, log=None):
    """Stop recording and WAIT until OBS finishes writing the file.

    OBS finalizes the container (e.g. the mp4 moov atom) asynchronously after
    stop_record() returns. Moving the file before that finishes yields a corrupt
    video that won't open. So we wait for the output to go inactive and for the
    file size to stop growing before returning the path.
    """

    def _log(msg):
        if log:
            log("rec", msg)

    try:
        res = req.stop_record()
    except Exception as e:
        _log(f"stop_record failed: {e}")
        return "", True
    src_path = getattr(res, "output_path", "") or ""

    output_inactive = False
    # 1) wait until OBS reports the recording output is no longer active
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if not req.get_record_status().output_active:
                output_inactive = True
                break
        except Exception:
            break
        time.sleep(0.5)

    # 2) wait until the file exists and its size is stable across two reads
    file_stable = False
    last = -1
    stable_deadline = time.monotonic() + timeout
    while time.monotonic() < stable_deadline:
        if src_path and os.path.exists(src_path):
            try:
                size = os.path.getsize(src_path)
            except OSError:
                size = -1
            if size == last and size > 0:
                file_stable = True
                break
            last = size
        time.sleep(0.7)
    timed_out = not (output_inactive and file_stable)
    if timed_out:
        _log("WARNING: OBS/file finalization did not complete; file may be "
             "incomplete.")
    return src_path, timed_out


# --------------------------------------------------------------------------- #
# Audio level watcher (OBS high-volume InputVolumeMeters event)               #
# --------------------------------------------------------------------------- #

class AudioWatcher:
    def __init__(self, cfg):
        self.input_name = cfg["audio"]["input_name"]
        self.silence_db = float(cfg["audio"]["silence_db"])
        self._lock = threading.Lock()
        self._last_loud = time.time()
        self._last_db = -100.0
        self._client = None

    def start(self, host, port, password):
        """Returns (ok, error_message). Never raises."""
        try:
            self._client = obsws.EventClient(
                host=host, port=port, password=password,
                subs=obsws.Subs.INPUTVOLUMEMETERS,
            )
            self._client.callback.register(self.on_input_volume_meters)
            return True, ""
        except Exception as e:
            return False, (f"level watch unavailable ({e}); "
                           f"recording continues without it")

    def on_input_volume_meters(self, data):
        peak = 0.0
        # OBS may pass inputs as attribute or dict key
        inputs = getattr(data, "inputs", None)
        if inputs is None:
            inputs = data.get("inputs", []) if isinstance(data, dict) else []
        for inp in inputs:
            if inp.get("inputName") != self.input_name:
                continue
            for ch in inp.get("inputLevelsMul", []):
                if ch:
                    peak = max(peak, ch[0])  # magnitude (linear)
        db = 20 * math.log10(peak) if peak > 0 else -100.0
        with self._lock:
            self._last_db = db
            if db > self.silence_db:
                self._last_loud = time.time()

    def silent_for(self):
        with self._lock:
            return time.time() - self._last_loud

    def last_db(self):
        with self._lock:
            return self._last_db

    def reset(self):
        with self._lock:
            self._last_loud = time.time()

    def stop(self):
        try:
            if self._client:
                self._client.disconnect()
        except Exception:
            pass
