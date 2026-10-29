"""Configuration handling for GhostRec — shared by the CLI and the GUI.

The config file lives at the repo root (the same config.json the CLI has
always used). The schema is frozen; unknown keys are preserved on save so
future sections (see FUTURE.md) survive a round-trip through the app.
"""

import json
import os
import shutil
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
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def validate_config(cfg):
    """Fill in missing keys with defaults (unknown keys are kept as-is)."""
    required = ["obs", "output_folder"]
    for key in required:
        if key not in cfg:
            raise ValueError(f"Missing config key: {key}")
    cfg.setdefault("capture_scene_name", "ClassRecScene")
    cfg.setdefault("capture_source_name", "ClassCapture")
    cfg.setdefault("poll_seconds", 3)
    capture = cfg.setdefault("capture", {})
    capture.setdefault("method", 2)
    capture.setdefault("source", "window")
    capture.setdefault("auto", True)
    # removed feature: windows are never pinned above the user's work
    capture.pop("keep_on_top", None)
    audio = cfg.setdefault("audio", {})
    audio.setdefault("check", True)
    audio.setdefault("input_name", "Desktop Audio")
    audio.setdefault("silence_db", -55.0)
    audio.setdefault("silence_alert_seconds", 30)
    audio.setdefault("minimize_warn_seconds", 60)
    obs = cfg.get("obs", {})
    obs.setdefault("host", "127.0.0.1")
    obs.setdefault("port", 4455)
    obs.setdefault("password", "")
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
