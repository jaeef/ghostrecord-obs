"""Background preview fetcher for the Live page.

Runs its own OBS WebSocket connection (the session's ReqClient is used by the
recorder thread, and a websocket must not be driven from two threads at once).
Frames are pushed to the GUI through the main event queue:
  ("preview", jpeg_bytes)  |  ("preview_error", message)
"""

import base64
import threading
import time

import obsws_python as obsws


class PreviewWorker(threading.Thread):
    def __init__(self, cfg, scene_name, emit, interval=2.0):
        super().__init__(name="ghostrec-preview", daemon=True)
        obs = cfg.get("obs", {})
        self._host = obs.get("host", "127.0.0.1")
        self._port = int(obs.get("port", 4455))
        self._password = obs.get("password", "")
        self._scene = scene_name
        self._emit = emit
        self._interval = interval
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        try:
            req = obsws.ReqClient(host=self._host, port=self._port,
                                  password=self._password, timeout=5)
        except Exception as e:
            self._emit(("preview_error", f"Live preview unavailable ({e})"))
            return
        fails = 0
        while not self._stop_event.is_set():
            try:
                # 720x405 is ~2x what the preview label renders at, so frames
                # look sharp without wasting bandwidth on a huge JPEG
                resp = req.get_source_screenshot(self._scene, "jpg",
                                                 720, 405, 80)
                data = getattr(resp, "image_data", "") or ""
                if data:
                    if data.startswith("data:"):
                        data = data.split(",", 1)[1]
                    self._emit(("preview", base64.b64decode(data)))
                    fails = 0
            except Exception:
                fails += 1
                if fails >= 5:
                    self._emit(("preview_error",
                                "Live preview stopped (screenshot failed)"))
                    return
            if self._stop_event.wait(self._interval):
                break
        # Give OBS a moment to close the socket cleanly on the way out.
        time.sleep(0)
