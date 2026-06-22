import threading
import time
import wave

from vokari.audio import capture


class _FakeStream:
    """Loopback silenzioso: non c'è mai un blocco disponibile (sistema muto)."""

    def get_read_available(self):
        return 0

    def read(self, n, exception_on_overflow=False):
        time.sleep(10)
        return b"\x00\x00" * n

    def stop_stream(self):
        pass

    def close(self):
        pass


class _FakePyAudioInstance:
    def get_default_wasapi_loopback(self):
        return {"defaultSampleRate": 48000, "maxInputChannels": 2, "index": 0}

    def open(self, **kwargs):
        return _FakeStream()

    def terminate(self):
        pass


class _FakePyAudioModule:
    paInt16 = 8

    def PyAudio(self):
        return _FakePyAudioInstance()


def test_system_capture_stops_promptly_when_silent(tmp_path, monkeypatch):
    monkeypatch.setattr(capture, "_pyaudio", lambda: _FakePyAudioModule())
    stop = threading.Event()
    out = str(tmp_path / "sys.wav")

    done = threading.Event()

    def run():
        capture._capture_system_native(out, stop_event=stop)
        done.set()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    time.sleep(0.2)
    stop.set()
    assert done.wait(timeout=1.5), "la cattura di sistema non si è fermata in tempo a stream muto"
    with wave.open(out, "rb") as wf:
        assert wf.getframerate() == 48000
