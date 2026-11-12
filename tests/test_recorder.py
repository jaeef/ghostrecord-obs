"""RecorderSession against a fake OBS: lock, re-aim, start race, scene restore."""

import tempfile
import time

from ghostrec.core.obs import WINDOW_PRIORITY_TITLE
from ghostrec.core.recorder import RecorderSession

from conftest import FakeObs


def _run(req, cfg, win, window_state, until, then=None, timeout=5):
    events = []
    sess = RecorderSession(req, cfg, win, "t", None, tempfile.gettempdir(),
                           events.append)
    sess.start()
    deadline = time.monotonic() + timeout
    while not any(e["type"] == until for e in events):
        assert time.monotonic() < deadline, f"no '{until}' event"
        time.sleep(0.02)
    if then:
        then(events)
    window_state["alive"] = False
    sess.join(timeout)
    assert not sess.is_running
    return sess, events


def test_source_uses_title_must_match(fake_window, window_state, base_cfg):
    req = FakeObs()
    sess, _ = _run(req, base_cfg, fake_window, window_state, "started")
    assert req.settings["priority"] == WINDOW_PRIORITY_TITLE
    assert sess.result == "done"


def test_rename_is_reaimed_quickly(fake_window, window_state, base_cfg):
    req = FakeObs()

    def rename(events):
        window_state["title"] = "Meeting - John"
        t0 = time.monotonic()
        while not any(e["type"] == "relocked" for e in events):
            assert time.monotonic() - t0 < 1.5, "re-aim slower than 1.5s"
            time.sleep(0.02)

    _run(req, base_cfg, fake_window, window_state, "started", rename)
    assert req.points[-1].startswith("Meeting - John:")
    assert req.settings["priority"] == WINDOW_PRIORITY_TITLE


def test_no_restart_while_obs_is_starting(fake_window, window_state, base_cfg):
    req = FakeObs(inactive_polls_after_start=2)
    _run(req, base_cfg, fake_window, window_state, "started")
    assert req.start_calls == 1


def test_previous_scene_is_restored(fake_window, window_state, base_cfg):
    req = FakeObs(program="Scene 2")
    seen = {}
    _run(req, base_cfg, fake_window, window_state, "started",
         lambda ev: seen.setdefault("during", req.program))
    assert seen["during"] == "S"
    assert req.program == "Scene 2"


def test_closing_the_window_stops_and_reports(fake_window, window_state,
                                              base_cfg):
    req = FakeObs()
    sess, events = _run(req, base_cfg, fake_window, window_state, "started")
    types = [e["type"] for e in events if e["type"] != "note"]
    assert types[0] == "started" and types[-1] == "finished"
    assert "stopped" in types
    assert not req.active
