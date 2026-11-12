"""Unit tests for config, OBS safety helpers, library naming and app kinds."""

import copy
import os

import pytest

from ghostrec.core import config as gcfg
from ghostrec.core import safe_apps
from ghostrec.core.library import human_size, unique_recording_name
from ghostrec.core.obs import (WINDOW_CAPTURE_WGC, capture_method_for,
                               check_scene_safety)
from ghostrec.core.recorder import sanitize_recording_name

from conftest import FakeObs


# --- config ------------------------------------------------------------------ #

def test_defaults_validate():
    cfg = gcfg.validate_config(copy.deepcopy(gcfg.DEFAULT_CONFIG))
    assert cfg["ui"] == {"appearance": "auto", "native_frame": False}


def test_missing_sections_get_defaults():
    cfg = gcfg.validate_config({"obs": {}, "output_folder": "./rec"})
    assert cfg["capture"]["method"] == 2
    assert cfg["audio"]["input_name"] == "Desktop Audio"
    assert cfg["ui"]["appearance"] == "auto"


def test_example_password_marker_is_cleared():
    cfg = gcfg.validate_config({"obs": {"password": "YOUR_OBS_WEBSOCKET_PASSWORD"},
                                "output_folder": "./rec"})
    assert cfg["obs"]["password"] == ""


@pytest.mark.parametrize("patch", [
    {"ui": {"appearance": "neon"}},
    {"capture": {"method": 5}},
    {"capture": {"source": "screen"}},
    {"obs": {"port": 70000}},
    {"poll_seconds": 0},
])
def test_invalid_values_are_rejected(patch):
    cfg = {"obs": {}, "output_folder": "./rec"}
    cfg.update(patch)
    with pytest.raises(ValueError):
        gcfg.validate_config(cfg)


def test_example_config_is_valid():
    import json
    with open(gcfg.EXAMPLE_PATH, encoding="utf-8") as f:
        gcfg.validate_config(json.load(f))


# --- OBS helpers --------------------------------------------------------------- #

def test_covered_mode_forces_wgc():
    assert capture_method_for("window", 1, covered=True) == WINDOW_CAPTURE_WGC
    assert capture_method_for("window", 1, covered=False) == 1


def test_safety_check_rejects_fallback_priority():
    req = FakeObs(program="S")
    win = {"title": "A", "cls": "C", "exe": "x.exe"}
    req.items = [{"sourceName": "Src", "inputKind": "window_capture"}]
    req.settings = {"window": "A:C:x.exe", "priority": 0}
    ok, reason = check_scene_safety(req, "S", "Src", win, "window")
    assert not ok and "priority" in reason
    req.settings["priority"] = 1
    assert check_scene_safety(req, "S", "Src", win, "window") == (True, "")


def test_safety_check_rejects_other_program_scene():
    req = FakeObs(program="Scene 2")
    req.items = [{"sourceName": "Src", "inputKind": "window_capture"}]
    ok, _ = check_scene_safety(req, "S", "Src")
    assert not ok


# --- names and library ------------------------------------------------------- #

def test_recording_name_is_sanitized():
    assert sanitize_recording_name("  my class: week 1! ") == "my_class_week_1"
    assert sanitize_recording_name("***") == "recording"


def test_unique_name_avoids_existing_files(tmp_path):
    assert unique_recording_name(str(tmp_path), "talk") == "talk"
    (tmp_path / "talk_2026-01-01_10-00-00.mkv").write_bytes(b"x")
    assert unique_recording_name(str(tmp_path), "talk") != "talk"


def test_human_size():
    assert human_size(0).startswith("0")
    assert "MB" in human_size(5 * 1024 * 1024)


# --- recording-safe apps ----------------------------------------------------- #

@pytest.mark.parametrize("exe,kind", [
    ("chrome.exe", "browser"), ("MSEDGE.EXE", "browser"),
    ("slack.exe", "electron"), ("code.exe", "electron"),
    ("ms-teams.exe", "webview2"), ("notepad.exe", None), ("", None),
])
def test_app_kind(exe, kind):
    assert safe_apps.app_kind(exe) == kind


def test_describe_restart_mentions_webview2_only_for_teams():
    _, detail = safe_apps.describe_restart({"exe": "ms-teams.exe"})
    assert safe_apps.WEBVIEW2_ENV in detail
    assert safe_apps.describe_restart({"exe": "chrome.exe"})[1] is None


@pytest.mark.skipif(os.name != "nt", reason="uses the Windows registry")
def test_webview2_setting_roundtrip():
    name = "GHOSTREC_PYTEST_WV2"
    try:
        safe_apps.set_webview2_setting(name)
        assert safe_apps.webview2_setting_active(name)
        safe_apps.clear_webview2_setting(name)
        assert not safe_apps.webview2_setting_active(name)
    finally:
        safe_apps.clear_webview2_setting(name)
