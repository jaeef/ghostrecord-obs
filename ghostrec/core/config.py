"""Configuration handling for GhostRec — shared by the CLI and the GUI.

The config file lives at the repo root (the same config.json the CLI has
always used). The schema is frozen; unknown keys are preserved on save so
future sections (see FUTURE.md) survive a round-trip through the app.
"""

import json
import math
import os
import shutil
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config.json"
EXAMPLE_PATH = REPO_ROOT / "config.example.json"

DEFAULT_CONFIG = {
    "obs": {"host": "127.0.0.1", "port": 4455, "password": ""},
    "capture_scene_name": "ClassRecScene",
    "capture_source_name": "ClassCapture",
    "output_folder": "./recordings",
    "poll_seconds": 3,
    "capture": {
        # 0 = Automatic (OBS picks), 1 = BitBlt, 2 = Windows Graphics Capture
        "method": 2,
        # source kind: "window" = Window Capture (WGC/BitBlt),
        #              "game"  = Game Capture (renders offscreen -> stays sharp
        #                        even when the window is fully covered)
        "source": "window",
        # keep the selected restored window isolated when another window covers
        # it; Modern Windows Graphics Capture is required for this contract
        "covered": True,
        # auto-detect apps that stop rendering when covered (Chrome etc.) and
        # offer the recording-friendly launcher instead of nagging
        "auto": True,
    },
    "audio": {
        "check": True,
        "input_name": "Desktop Audio",
        "silence_db": -55.0,
        "silence_alert_seconds": 30,
        "minimize_warn_seconds": 60,
    },
    "ui": {
        # "auto" follows the OS light/dark setting
        "appearance": "auto",
        # true = keep the Windows title bar instead of macOS traffic lights
        "native_frame": False,
    },
}


def ensure_config():
    """Create config.json if missing. Returns a status message, or None."""
    if CONFIG_PATH.exists():
        return None
    if EXAMPLE_PATH.exists():
        shutil.copy(EXAMPLE_PATH, CONFIG_PATH)
        return f"created {CONFIG_PATH} from example"
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(DEFAULT_CONFIG, f, indent=2)
    return f"created default {CONFIG_PATH}"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg):
    """Atomically write configuration without exposing partial JSON."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f"{CONFIG_PATH.stem}.", suffix=".tmp",
        dir=str(CONFIG_PATH.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_name, CONFIG_PATH)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def validate_config(cfg):
    """Fill in missing keys with defaults (unknown keys are kept as-is)."""
    if not isinstance(cfg, dict):
        raise ValueError("Configuration must be a JSON object")
    required = ["obs", "output_folder"]
    for key in required:
        if key not in cfg:
            raise ValueError(f"Missing config key: {key}")
    if not isinstance(cfg["obs"], dict):
        raise ValueError("Config key 'obs' must be an object")
    if not isinstance(cfg["output_folder"], str):
        raise ValueError("Config key 'output_folder' must be a string")
    if not cfg["output_folder"].strip():
        raise ValueError("Config key 'output_folder' cannot be empty")

    cfg.setdefault("capture_scene_name", "ClassRecScene")
    cfg.setdefault("capture_source_name", "ClassCapture")
    cfg.setdefault("poll_seconds", 3)
    for key in ("capture_scene_name", "capture_source_name"):
        if not isinstance(cfg[key], str) or not cfg[key].strip():
            raise ValueError(f"Config key '{key}' must be a non-empty string")
    if isinstance(cfg["poll_seconds"], bool) or not isinstance(
            cfg["poll_seconds"], (int, float)):
        raise ValueError("Config key 'poll_seconds' must be a number")
    if not math.isfinite(float(cfg["poll_seconds"])) or cfg["poll_seconds"] <= 0:
        raise ValueError("Config key 'poll_seconds' must be greater than zero")

    capture = cfg.setdefault("capture", {})
    if not isinstance(capture, dict):
        raise ValueError("Config key 'capture' must be an object")
    capture.setdefault("method", 2)
    capture.setdefault("source", "window")
    capture.setdefault("covered", True)
    capture.setdefault("auto", True)
    if isinstance(capture["method"], bool) or capture["method"] not in (0, 1, 2):
        raise ValueError("Config key 'capture.method' must be 0, 1, or 2")
    if capture["source"] not in ("window", "game"):
        raise ValueError("Config key 'capture.source' must be 'window' or 'game'")
    if not isinstance(capture["covered"], bool):
        raise ValueError("Config key 'capture.covered' must be boolean")
    if not isinstance(capture["auto"], bool):
        raise ValueError("Config key 'capture.auto' must be boolean")
    # removed feature: windows are never pinned above the user's work
    capture.pop("keep_on_top", None)

    audio = cfg.setdefault("audio", {})
    if not isinstance(audio, dict):
        raise ValueError("Config key 'audio' must be an object")
    audio.setdefault("check", True)
    audio.setdefault("input_name", "Desktop Audio")
    audio.setdefault("silence_db", -55.0)
    audio.setdefault("silence_alert_seconds", 30)
    audio.setdefault("minimize_warn_seconds", 60)
    if not isinstance(audio["check"], bool):
        raise ValueError("Config key 'audio.check' must be boolean")
    if not isinstance(audio["input_name"], str) or not audio["input_name"].strip():
        raise ValueError("Config key 'audio.input_name' must be non-empty")
    if (isinstance(audio["silence_db"], bool)
            or not isinstance(audio["silence_db"], (int, float))
            or not math.isfinite(float(audio["silence_db"]))
            or not -100 <= float(audio["silence_db"]) <= 0):
        raise ValueError("Config key 'audio.silence_db' must be between -100 and 0")
    for key in ("silence_alert_seconds", "minimize_warn_seconds"):
        if (isinstance(audio[key], bool)
                or not isinstance(audio[key], (int, float))
                or not math.isfinite(float(audio[key]))
                or audio[key] <= 0):
            raise ValueError(f"Config key 'audio.{key}' must be greater than zero")

    ui = cfg.setdefault("ui", {})
    if not isinstance(ui, dict):
        raise ValueError("Config key 'ui' must be an object")
    ui.setdefault("appearance", "auto")
    ui.setdefault("native_frame", False)
    if ui["appearance"] not in ("auto", "light", "dark"):
        raise ValueError("Config key 'ui.appearance' must be auto, light or dark")
    if not isinstance(ui["native_frame"], bool):
        raise ValueError("Config key 'ui.native_frame' must be boolean")

    obs = cfg.get("obs", {})
    obs.setdefault("host", "127.0.0.1")
    obs.setdefault("port", 4455)
    obs.setdefault("password", "")
    if not isinstance(obs["host"], str) or not obs["host"].strip():
        raise ValueError("Config key 'obs.host' must be a non-empty string")
    if (isinstance(obs["port"], bool) or not isinstance(obs["port"], int)
            or not 1 <= obs["port"] <= 65535):
        raise ValueError("Config key 'obs.port' must be between 1 and 65535")
    if not isinstance(obs["password"], str):
        raise ValueError("Config key 'obs.password' must be a string")
    if obs["password"] == "YOUR_OBS_WEBSOCKET_PASSWORD":
        # The example file is intentionally copyable. Treat its marker as an
        # unset password so a fresh install does not try to authenticate with it.
        obs["password"] = ""
    return cfg


def resolve_output_folder(cfg, base=None):
    """Absolute path of the output folder.

    Relative paths resolve against ``base`` (default: current working
    directory, which keeps the CLI's historical behavior). The GUI passes the
    repo root so the folder does not depend on where the app was launched.
    """
    folder = cfg.get("output_folder", "./recordings")
    if os.path.isabs(folder):
        return os.path.normpath(folder)
    root = str(base) if base is not None else os.getcwd()
    return os.path.normpath(os.path.join(root, folder))
