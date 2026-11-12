"""Shared fixtures: a fake OBS WebSocket client and a fake target window."""

import os
import types

import pytest

# Qt widgets in tests never open real windows on the user's screen.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class NS(types.SimpleNamespace):
    pass


class FakeObs:
    """Just enough of obsws_python.ReqClient for RecorderSession."""

    def __init__(self, program="Scene 2", inactive_polls_after_start=0):
        self.scenes = ["Scene 2", "S"]
        self.program = program
        self.items = []
        self.settings = {}
        self.active = False
        self.start_calls = 0
        self.points = []
        self._inactive_polls = inactive_polls_after_start

    # scenes / sources
    def get_scene_list(self):
        return NS(scenes=[{"sceneName": s} for s in self.scenes],
                  current_program_scene_name=self.program)

    def create_scene(self, name):
        self.scenes.append(name)

    def get_scene_item_list(self, name):
        return NS(scene_items=self.items if name == "S" else [])

    def get_input_list(self):
        return NS(inputs=[])

    def create_input(self, scene, name, kind, settings, enabled):
        self.items = [{"sourceName": name, "inputKind": kind}]
        self.settings = dict(settings)

    def set_input_settings(self, name, settings, overlay):
        self.settings.update(settings)
        self.points.append(settings["window"])

    def get_input_settings(self, name):
        return NS(input_settings=dict(self.settings))

    def get_video_settings(self):
        return NS(base_width=1920, base_height=1080)

    def get_scene_item_id(self, *a):
        return NS(scene_item_id=1)

    def set_scene_item_transform(self, *a):
        pass

    def set_current_program_scene(self, name):
        self.program = name

    # recording
    def start_record(self):
        self.start_calls += 1
        self.active = True

    def get_record_status(self):
        if self._inactive_polls > 0:      # OBS still spinning up
            self._inactive_polls -= 1
            return NS(output_active=False)
        return NS(output_active=self.active)

    def stop_record(self):
        self.active = False
        return NS(output_path="")


@pytest.fixture
def window_state():
    return {"title": "Meeting", "alive": True}


@pytest.fixture
def fake_window(monkeypatch, window_state):
    """Patch the recorder's window helpers to a controllable fake window."""
    import ghostrec.core.recorder as rec

    win = {"hwnd": 42, "title": "Meeting", "cls": "Chrome_WidgetWin_1",
           "exe": "chrome.exe", "exe_path": "c:/chrome.exe", "pid": 7}

    def info(_hwnd):
        return dict(win, title=window_state["title"]) \
            if window_state["alive"] else None

    monkeypatch.setattr(rec, "get_window_info", info)
    monkeypatch.setattr(rec, "is_window_alive", lambda h: window_state["alive"])
    monkeypatch.setattr(rec, "is_window_minimized", lambda h: False)
    monkeypatch.setattr(rec, "is_window_covered", lambda h: False)
    monkeypatch.setattr(rec, "identical_windows", lambda w: [])
    monkeypatch.setattr(rec, "stop_and_finalize",
                        lambda req, timeout=30, log=None:
                        (req.stop_record().output_path, False))
    monkeypatch.setattr(rec.time, "sleep", lambda s: None)
    return win


@pytest.fixture
def base_cfg():
    return {"capture_scene_name": "S", "capture_source_name": "Src",
            "poll_seconds": 3,
            "capture": {"method": 2, "source": "window", "covered": True,
                        "auto": False},
            "audio": {"check": False}}
