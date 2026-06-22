import threading
import time

import numpy as np

from vokari.audio import capture


class _FakeSdStream:
    def __init__(self):
        self.calls = 0

    def start(self):
        pass

    def read(self, n):
        self.calls += 1
        return np.zeros((n, 1), dtype=np.int16), False

    def stop(self):
        pass

    def close(self):
        pass


class _FakeSd:
    def query_devices(self, device, kind):
        return {"default_samplerate": 16000}

    def InputStream(self, **kwargs):
        return _FakeSdStream()


def test_mic_capture_calls_on_audio(tmp_path, monkeypatch):
    monkeypatch.setattr(capture, "_sd", lambda: _FakeSd())
    stop = threading.Event()
    got = []

    def run():
        capture._capture_mic_native(
            str(tmp_path / "m.wav"),
            stop_event=stop,
            on_audio=lambda block, rate: got.append((block.shape, rate)),
        )

    t = threading.Thread(target=run, daemon=True)
    t.start()
    time.sleep(0.1)
    stop.set()
    t.join(timeout=1)
    assert got, "on_audio non chiamata"
    assert got[0][1] == 16000
