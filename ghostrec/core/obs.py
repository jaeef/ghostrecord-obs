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

import obsws_python as obsws


class ObsError(Exception):
    """Human-readable OBS connection/operation error."""


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
    try:
        req = obsws.ReqClient(host=host, port=int(port), password=password,
                              timeout=timeout)
        return req.get_version().obs_version
    except Exception as e:
        raise ObsError(_friendly_connect_error(e, host, port)) from e


# --------------------------------------------------------------------------- #
# OBS process helpers (from setup.py)                                          #
# --------------------------------------------------------------------------- #

OBS_PATHS = [
    r"C:\Program Files\obs-studio\bin\64bit\obs64.exe",
    r"C:\Program Files (x86)\obs-studio\bin\64bit\obs64.exe",
]


def is_obs_running():
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq obs64.exe"],
            text=True, stderr=subprocess.DEVNULL)
        return "obs64.exe" in out
    except Exception:
        return False


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

def ensure_scene_and_source(req, scene_name, source_name, log=None):
    """Make a DEDICATED scene that contains ONLY the window-capture source.

    Recording captures whatever scene is on Program. If we recorded your normal
    scene it would also grab any Display/Screen Capture sitting in it (= your
    whole screen). So we use our own scene with just the one window in it —
    nothing else you do on screen is recorded.
    """

    def _log(msg):
        if log:
            log("obs", msg)

    scenes = [s["sceneName"] for s in req.get_scene_list().scenes]
    if scene_name not in scenes:
        _log(f"creating dedicated scene '{scene_name}'")
        req.create_scene(scene_name)

    # Remove all existing items from the scene to keep it clean
    items = req.get_scene_item_list(scene_name).scene_items
    for item in items:
        try:
            req.remove_scene_item(scene_name, item["sceneItemId"])
        except Exception:
            pass

    # OBS input names are GLOBAL. If the source exists (e.g. left in another
    # scene from a previous run) we add it to this scene instead of recreating.
    existing = [i["inputName"] for i in req.get_input_list().inputs]
    if source_name in existing:
        _log(f"adding existing source '{source_name}' to '{scene_name}'")
        req.create_scene_item(scene_name, source_name, True)
    else:
        _log(f"creating source '{source_name}' in '{scene_name}'")
        req.create_input(
            scene_name, source_name, "window_capture",
            {"method": 2, "cursor": True},  # method 2 = Windows Graphics Capture
            True,
        )
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


def point_source_at(req, source_name, window):
    """Aim the window_capture source at ONE exact window — never anything else.

    We always pass the full 'title:class:exe' of the selected window and use
    priority 0 (match by window title). The caller re-points the source whenever
    the pinned window's title changes, so OBS can only ever bind to the window
    we selected — never to another window of the same program.
    """
    from ghostrec.core.windows import obs_window_value
    req.set_input_settings(
        source_name,
        {"window": obs_window_value(window), "priority": 0,
         "method": 2, "cursor": True},
        True,
    )


def check_scene_safety(req, scene_name):
    """Verify the program scene is clean before recording.

    Returns (ok, reason). ok=False means we must NOT start recording,
    otherwise the whole screen could be captured.
    """
    cur = req.get_scene_list().current_program_scene_name
    items = req.get_scene_item_list(scene_name).scene_items
    kinds = [i.get("inputKind", "") for i in items]
    bad = [k for k in kinds if "monitor_capture" in k or "display" in k
           or "game_capture" in k]
    if cur != scene_name or bad or len(items) != 1:
        names = [i.get("sourceName", "?") for i in items]
        return (False,
                f"scene not clean (program='{cur}', items={names}). "
                f"Not recording — would capture whole screen.")
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

    timed_out = True
    # 1) wait until OBS reports the recording output is no longer active
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if not req.get_record_status().output_active:
                timed_out = False
                break
        except Exception:
            break
        time.sleep(0.5)

    # 2) wait until the file exists and its size is stable across two reads
    last = -1
    stable_deadline = time.time() + timeout
    while time.time() < stable_deadline:
        if src_path and os.path.exists(src_path):
            size = os.path.getsize(src_path)
            if size == last and size > 0:
                timed_out = False
                break
            last = size
        time.sleep(0.7)
    if timed_out:
        _log("WARNING: file finalization timed out; file may be incomplete.")
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
