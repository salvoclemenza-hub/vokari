import shutil
import threading
import time

import numpy as np
import pytest

from vokari.audio import capture


def test_write_and_read_pcm16_roundtrip(tmp_path):
    p = tmp_path / "a.wav"
    capture.write_pcm16_wav(np.array([0, 100, -100, 32767], dtype=np.int16), p, samplerate=16000, channels=1)
    arr, rate, ch = capture._read_wav_int16(str(p))
    assert rate == 16000 and ch == 1
    assert list(arr) == [0, 100, -100, 32767]


def test_mix_wav_16k_mono_sums_samples(tmp_path):
    a, b, out = tmp_path / "a.wav", tmp_path / "b.wav", tmp_path / "m.wav"
    capture.write_pcm16_wav(np.full(10, 1000, dtype=np.int16), a, samplerate=16000, channels=1)
    capture.write_pcm16_wav(np.full(10, 2000, dtype=np.int16), b, samplerate=16000, channels=1)
    capture.mix_wav_16k_mono(str(a), str(b), str(out))
    arr, rate, ch = capture._read_wav_int16(str(out))
    assert rate == 16000 and ch == 1
    assert all(int(x) == 3000 for x in arr)


def test_mix_pads_shorter_and_clips(tmp_path):
    a, b, out = tmp_path / "a.wav", tmp_path / "b.wav", tmp_path / "m.wav"
    capture.write_pcm16_wav(np.full(5, 30000, dtype=np.int16), a, samplerate=16000, channels=1)
    capture.write_pcm16_wav(np.full(3, 10000, dtype=np.int16), b, samplerate=16000, channels=1)
    capture.mix_wav_16k_mono(str(a), str(b), str(out))
    arr, _, _ = capture._read_wav_int16(str(out))
    assert len(arr) == 5  # pad al più lungo
    assert int(arr[0]) == 32767  # 30000+10000 clip
    assert int(arr[4]) == 30000  # coda: solo a (b finito)


def test_mix_wav_stereo_input_folds_to_mono(tmp_path):
    a, b, out = tmp_path / "a.wav", tmp_path / "b.wav", tmp_path / "m.wav"
    stereo = np.array([[100, 200], [300, 400]], dtype=np.int16)  # mean -> [150, 350]
    capture.write_pcm16_wav(stereo, a, samplerate=16000, channels=2)
    capture.write_pcm16_wav(np.full(2, 50, dtype=np.int16), b, samplerate=16000, channels=1)
    capture.mix_wav_16k_mono(str(a), str(b), str(out))
    arr, _, ch = capture._read_wav_int16(str(out))
    assert ch == 1
    assert int(arr[0]) == 200 and int(arr[1]) == 400  # 150+50, 350+50


def test_mix_rejects_non_16k_input(tmp_path):
    a, b = tmp_path / "a.wav", tmp_path / "b.wav"
    capture.write_pcm16_wav(np.zeros(4, dtype=np.int16), a, samplerate=44100, channels=1)
    capture.write_pcm16_wav(np.zeros(4, dtype=np.int16), b, samplerate=16000, channels=1)
    with pytest.raises(ValueError, match="16000"):
        capture.mix_wav_16k_mono(str(a), str(b), str(tmp_path / "m.wav"))


def test_sweep_orphan_tempdirs_removes_old_keeps_recent(tmp_path, monkeypatch):
    """Rimuove le dir 'vokari-rec-*' vecchie ma NON quelle recenti (una cattura potrebbe
    essere in corso) né altre cartelle: il filtro per età è critico."""
    import os
    import tempfile

    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    old = tmp_path / "vokari-rec-OLD"
    fresh = tmp_path / "vokari-rec-NEW"
    other = tmp_path / "altro-progetto"
    for d in (old, fresh, other):
        d.mkdir()
    old_t = time.time() - 10000  # oltre 2h fa
    os.utime(old, (old_t, old_t))
    removed = capture.sweep_orphan_tempdirs(max_age_s=7200)
    assert removed == 1
    assert not old.exists()  # vecchia rimossa
    assert fresh.exists()  # recente preservata (forse in corso)
    assert other.exists()  # dir non-vokari intatta


def test_capture_mic_native_writes_wav(tmp_path, monkeypatch):
    stop = threading.Event()

    class FakeStream:
        def __init__(self):
            self.n = 0

        def start(self):
            pass

        def stop(self):
            pass

        def close(self):
            pass

        def read(self, frames):
            self.n += 1
            if self.n >= 3:
                stop.set()  # ferma il loop dopo 3 blocchi
            return np.full((frames, 1), self.n, dtype=np.int16), False

    class FakeSd:
        @staticmethod
        def query_devices(device, kind):
            return {"default_samplerate": 48000.0, "max_input_channels": 2}

        @staticmethod
        def InputStream(**kwargs):
            return FakeStream()

    monkeypatch.setattr(capture, "_sd", lambda: FakeSd)
    out = tmp_path / "mic_native.wav"
    rate, ch = capture._capture_mic_native(str(out), stop_event=stop)
    assert rate == 48000 and ch == 1
    arr, r, c = capture._read_wav_int16(str(out))
    assert r == 48000 and c == 1
    assert len(arr) == 3 * capture._BLOCK  # 3 blocchi accumulati


def test_capture_system_native_writes_wav(tmp_path, monkeypatch):
    stop = threading.Event()

    class FakeStream:
        def __init__(self):
            self.n = 0

        def get_read_available(self):
            return capture._BLOCK  # sempre pronto: esercita il path read()

        def read(self, frames, exception_on_overflow=True):
            self.n += 1
            if self.n >= 2:
                stop.set()
            return np.zeros((frames, 2), dtype=np.int16).tobytes()

        def stop_stream(self):
            pass

        def close(self):
            pass

    class FakePyAudioInstance:
        def get_default_wasapi_loopback(self):
            return {"index": 7, "name": "Speakers (loopback)", "defaultSampleRate": 48000.0, "maxInputChannels": 2}

        def open(self, **kwargs):
            return FakeStream()

        def terminate(self):
            pass

    class FakePyAudioModule:
        paInt16 = 8

        @staticmethod
        def PyAudio():
            return FakePyAudioInstance()

    monkeypatch.setattr(capture, "_pyaudio", lambda: FakePyAudioModule)
    out = tmp_path / "sys_native.wav"
    rate, ch = capture._capture_system_native(str(out), stop_event=stop)
    assert rate == 48000 and ch == 2
    _, r, c = capture._read_wav_int16(str(out))
    assert r == 48000 and c == 2
    assert (tmp_path / "sys_native.wav").stat().st_size > 44  # > header WAV


def test_recorder_single_source_outputs_16k_mono(tmp_path, monkeypatch):
    def fake_mic(out_path, *, stop_event, device=None, pause_event=None):
        capture.write_pcm16_wav(np.zeros(16000, dtype=np.int16), out_path, samplerate=16000, channels=1)
        return 16000, 1

    monkeypatch.setattr(capture, "_capture_mic_native", fake_mic)
    monkeypatch.setattr(capture, "_normalize", lambda src, dst: shutil.copyfile(src, dst))
    out = tmp_path / "mic.wav"
    rec = capture.Recorder("mic", str(out))
    rec.start()
    res = rec.stop()
    assert res.source == "mic" and res.wav_path == str(out)
    _, rate, ch = capture._read_wav_int16(str(out))
    assert rate == 16000 and ch == 1
    assert abs(res.duration_s - 1.0) < 0.05


def test_recorder_both_mixes_to_16k_mono(tmp_path, monkeypatch):
    def fake_mic(out_path, *, stop_event, device=None, pause_event=None):
        capture.write_pcm16_wav(np.full(8000, 1000, dtype=np.int16), out_path, samplerate=16000, channels=1)
        return 16000, 1

    def fake_sys(out_path, *, stop_event, device=None, pause_event=None):
        capture.write_pcm16_wav(np.full(8000, 2000, dtype=np.int16), out_path, samplerate=16000, channels=1)
        return 16000, 1

    monkeypatch.setattr(capture, "_capture_mic_native", fake_mic)
    monkeypatch.setattr(capture, "_capture_system_native", fake_sys)
    monkeypatch.setattr(capture, "_normalize", lambda src, dst: shutil.copyfile(src, dst))
    out = tmp_path / "mix.wav"
    rec = capture.Recorder("both", str(out))
    rec.start()
    m = rec.add_marker("intro")
    res = rec.stop()
    assert res.source == "both"
    arr, rate, ch = capture._read_wav_int16(str(out))
    assert rate == 16000 and ch == 1
    assert int(arr[0]) == 3000  # 1000 + 2000 mixati
    assert 0.45 < res.duration_s < 0.55
    assert m["label"] == "intro" and res.markers[0]["label"] == "intro"
    assert res.markers[0]["t_ms"] >= 0


def test_capture_mic_native_skips_frames_while_paused(tmp_path, monkeypatch):
    stop = threading.Event()
    pause = threading.Event()
    pause.set()  # parte in pausa

    class FakeStream:
        def __init__(self):
            self.n = 0

        def start(self):
            pass

        def stop(self):
            pass

        def close(self):
            pass

        def read(self, frames):
            self.n += 1
            if self.n == 2:
                pause.clear()  # esci dalla pausa dal 2° blocco
            if self.n >= 4:
                stop.set()
            return np.full((frames, 1), self.n, dtype=np.int16), False

    class FakeSd:
        @staticmethod
        def query_devices(device, kind):
            return {"default_samplerate": 16000.0, "max_input_channels": 1}

        @staticmethod
        def InputStream(**kwargs):
            return FakeStream()

    monkeypatch.setattr(capture, "_sd", lambda: FakeSd)
    out = tmp_path / "m.wav"
    capture._capture_mic_native(str(out), stop_event=stop, pause_event=pause)
    arr, _, _ = capture._read_wav_int16(str(out))
    assert len(arr) == 3 * capture._BLOCK  # blocco 1 (in pausa) scartato; 2,3,4 accumulati


def test_rms_db_levels():
    full = np.full(1000, 32767, dtype=np.int16)
    assert capture._rms_db(full) > -0.5  # ~0 dBFS a fondo scala
    assert capture._rms_db(np.zeros(1000, dtype=np.int16)) <= -100  # silenzio
    assert capture._rms_db(np.array([], dtype=np.int16)) == -120.0  # blocco vuoto
    half = np.full(1000, 16384, dtype=np.int16)  # ~ -6 dBFS
    assert -7 < capture._rms_db(half) < -5


def test_capture_mic_native_reports_level(tmp_path, monkeypatch):
    stop = threading.Event()

    class FakeStream:
        def __init__(self):
            self.n = 0

        def start(self):
            pass

        def stop(self):
            pass

        def close(self):
            pass

        def read(self, frames):
            self.n += 1
            if self.n >= 3:
                stop.set()
            return np.full((frames, 1), 10000, dtype=np.int16), False

    class FakeSd:
        @staticmethod
        def query_devices(device, kind):
            return {"default_samplerate": 16000.0, "max_input_channels": 1}

        @staticmethod
        def InputStream(**kwargs):
            return FakeStream()

    monkeypatch.setattr(capture, "_sd", lambda: FakeSd)
    levels: list[float] = []
    capture._capture_mic_native(str(tmp_path / "m.wav"), stop_event=stop, on_level=levels.append)
    assert levels  # almeno un livello emesso
    assert -40 < levels[0] < 0  # dBFS plausibile per ampiezza 10000


def test_recorder_forwards_levels_with_lane(tmp_path, monkeypatch):
    seen: list[tuple[str, float]] = []

    def fake_mic(out_path, *, stop_event, device=None, pause_event=None, on_level=None):
        if on_level:
            on_level(-12.0)
        capture.write_pcm16_wav(np.zeros(1600, dtype=np.int16), out_path, samplerate=16000, channels=1)
        return 16000, 1

    monkeypatch.setattr(capture, "_capture_mic_native", fake_mic)
    monkeypatch.setattr(capture, "_normalize", lambda src, dst: shutil.copyfile(src, dst))
    rec = capture.Recorder("mic", str(tmp_path / "o.wav"), on_level=lambda lane, db: seen.append((lane, db)))
    rec.start()
    rec.stop()
    assert ("mic", -12.0) in seen  # la lane è correttamente legata dal Recorder


def test_recorder_both_warns_and_diagnoses_when_final_is_silent(tmp_path, monkeypatch):
    """A2: con 'both' se l'audio finale è praticamente silenzioso (qui entrambe le lane
    a zero) il Recorder lo segnala con un warning chiaro e popola `diagnostics` con il
    livello RMS per-lane + finale (così il debug log rivela la causa, es. una lane persa)."""

    def silent(out_path, *, stop_event, device=None, pause_event=None):
        capture.write_pcm16_wav(np.zeros(8000, dtype=np.int16), out_path, samplerate=16000, channels=1)
        return 16000, 1

    monkeypatch.setattr(capture, "_capture_mic_native", silent)
    monkeypatch.setattr(capture, "_capture_system_native", silent)
    monkeypatch.setattr(capture, "_normalize", lambda src, dst: shutil.copyfile(src, dst))
    rec = capture.Recorder("both", str(tmp_path / "silent.wav"))
    rec.start()
    res = rec.stop()
    assert res.source == "both"
    assert any("silenzios" in w.lower() or "basso" in w.lower() for w in res.warnings)
    assert "mic_dbfs" in res.diagnostics and "system_dbfs" in res.diagnostics
    assert "final_dbfs" in res.diagnostics
    assert res.diagnostics["final_dbfs"] <= -100  # silenzio


def test_recorder_both_no_silence_warning_when_audible(tmp_path, monkeypatch):
    """Audio udibile in 'both' → nessun warning di silenzio (il gate non è un falso allarme)."""

    def loud_mic(out_path, *, stop_event, device=None, pause_event=None):
        capture.write_pcm16_wav(np.full(8000, 8000, dtype=np.int16), out_path, samplerate=16000, channels=1)
        return 16000, 1

    def loud_sys(out_path, *, stop_event, device=None, pause_event=None):
        capture.write_pcm16_wav(np.full(8000, 6000, dtype=np.int16), out_path, samplerate=16000, channels=1)
        return 16000, 1

    monkeypatch.setattr(capture, "_capture_mic_native", loud_mic)
    monkeypatch.setattr(capture, "_capture_system_native", loud_sys)
    monkeypatch.setattr(capture, "_normalize", lambda src, dst: shutil.copyfile(src, dst))
    rec = capture.Recorder("both", str(tmp_path / "loud.wav"))
    rec.start()
    res = rec.stop()
    assert not any("silenzios" in w.lower() or "basso" in w.lower() for w in res.warnings)


def test_recorder_pause_resume_toggles():
    rec = capture.Recorder("mic", "x.wav")
    assert rec.is_paused() is False
    rec.pause()
    assert rec.is_paused() is True
    rec.resume()
    assert rec.is_paused() is False


def test_recorder_invalid_source():
    with pytest.raises(ValueError):
        capture.Recorder("foo", "x.wav")


def test_recorder_surfaces_capture_error(tmp_path, monkeypatch):
    def boom(out_path, *, stop_event, device=None, pause_event=None):
        raise RuntimeError("device occupato")

    monkeypatch.setattr(capture, "_capture_mic_native", boom)
    rec = capture.Recorder("mic", str(tmp_path / "x.wav"))
    rec.start()
    with pytest.raises(RuntimeError, match="device occupato"):
        rec.stop()


def test_recorder_both_falls_back_to_mic_when_system_fails(tmp_path, monkeypatch):
    def fake_mic(out_path, *, stop_event, device=None, pause_event=None):
        capture.write_pcm16_wav(np.full(8000, 1500, dtype=np.int16), out_path, samplerate=16000, channels=1)
        return 16000, 1

    def boom_sys(out_path, *, stop_event, device=None, pause_event=None):
        raise RuntimeError("loopback non disponibile")

    monkeypatch.setattr(capture, "_capture_mic_native", fake_mic)
    monkeypatch.setattr(capture, "_capture_system_native", boom_sys)
    monkeypatch.setattr(capture, "_normalize", lambda src, dst: shutil.copyfile(src, dst))
    out = tmp_path / "fallback.wav"
    rec = capture.Recorder("both", str(out))
    rec.start()
    res = rec.stop()
    assert res.source == "mic"  # degradato a microfono, niente crash
    assert any("sistema" in w or "system" in w for w in res.warnings)
    arr, rate, ch = capture._read_wav_int16(str(out))
    assert rate == 16000 and ch == 1
    assert int(arr[0]) == 1500  # solo mic, nessun mix


def test_recorder_stop_does_not_hang_on_stuck_source(tmp_path, monkeypatch):
    """Se un thread di cattura si blocca (es. loopback WASAPI silenzioso che non ritorna da
    read()), stop() NON deve appendere all'infinito: timeout sul join → fallback alla
    sorgente terminata (qui mic). È la causa probabile di 'Stop non funziona' in 'both'."""
    monkeypatch.setattr(capture, "_STOP_JOIN_TIMEOUT", 0.3)
    block = threading.Event()

    def stuck_sys(out_path, *, stop_event, device=None, pause_event=None):
        block.wait(5)  # simula un read() bloccato che ignora lo stop_event

    def fake_mic(out_path, *, stop_event, device=None, pause_event=None):
        capture.write_pcm16_wav(np.full(8000, 1500, dtype=np.int16), out_path, samplerate=16000, channels=1)
        return 16000, 1

    monkeypatch.setattr(capture, "_capture_mic_native", fake_mic)
    monkeypatch.setattr(capture, "_capture_system_native", stuck_sys)
    monkeypatch.setattr(capture, "_normalize", lambda src, dst: shutil.copyfile(src, dst))
    rec = capture.Recorder("both", str(tmp_path / "o.wav"))
    rec.start()
    res = rec.stop()  # deve ritornare entro ~timeout, non bloccare
    block.set()
    assert res.source == "mic"  # fallback alla sorgente terminata
    assert any("non terminata" in w or "system" in w for w in res.warnings)


def test_recorder_raises_when_all_sources_fail(tmp_path, monkeypatch):
    def boom(out_path, *, stop_event, device=None, pause_event=None):
        raise RuntimeError("device occupato")

    monkeypatch.setattr(capture, "_capture_mic_native", boom)
    monkeypatch.setattr(capture, "_capture_system_native", boom)
    rec = capture.Recorder("both", str(tmp_path / "x.wav"))
    rec.start()
    with pytest.raises(RuntimeError, match="Cattura fallita"):
        rec.stop()


def test_recorder_stop_without_start_raises():
    rec = capture.Recorder("mic", "x.wav")
    with pytest.raises(RuntimeError, match="start"):
        rec.stop()


def test_list_input_devices_filters_zero_input(monkeypatch):
    class FakeSd:
        @staticmethod
        def query_devices():
            return [
                {"name": "Mic A", "max_input_channels": 1, "default_samplerate": 44100.0},
                {"name": "Speakers", "max_input_channels": 0, "default_samplerate": 48000.0},
                {"name": "Mic B", "max_input_channels": 2, "default_samplerate": 48000.0},
            ]

    monkeypatch.setattr(capture, "_sd", lambda: FakeSd)
    devs = capture.list_input_devices()
    assert [d["name"] for d in devs] == ["Mic A", "Mic B"]  # esclude 0-input
    assert devs[0]["index"] == 0 and devs[1]["index"] == 2
    assert devs[1]["samplerate"] == 48000


def test_list_loopback_devices(monkeypatch):
    class FakePyAudioInstance:
        def get_loopback_device_info_generator(self):
            yield {"index": 5, "name": "Speakers (loopback)", "maxInputChannels": 2, "defaultSampleRate": 48000.0}

        def terminate(self):
            pass

    class FakeMod:
        @staticmethod
        def PyAudio():
            return FakePyAudioInstance()

    monkeypatch.setattr(capture, "_pyaudio", lambda: FakeMod)
    devs = capture.list_loopback_devices()
    assert devs[0]["index"] == 5 and devs[0]["channels"] == 2
    assert devs[0]["samplerate"] == 48000


def test_add_marker_excludes_paused_time(monkeypatch):
    """Il t_ms del marker deve riflettere l'audio EFFETTIVO (le pause scartano i frame),
    non il wall-clock: registra 10s, pausa 30s, riprende, marca a 45s wall → 15s audio."""
    rec = capture.Recorder("mic", "x.wav")
    clock = {"t": 0.0}
    monkeypatch.setattr(capture.time, "monotonic", lambda: clock["t"])
    clock["t"] = 0.0
    rec._start_monotonic = 0.0  # simula start() senza avviare i thread reali
    clock["t"] = 10.0
    rec.pause()
    clock["t"] = 40.0
    rec.resume()  # 30 s in pausa
    clock["t"] = 45.0
    mk = rec.add_marker("X")
    assert mk["t_ms"] == 15_000  # 45 - 30 = 15 s


def test_add_marker_during_active_pause_counts_pause_in_progress(monkeypatch):
    """Marker inserito MENTRE è in pausa: conta anche la pausa in corso (t_ms congelato)."""
    rec = capture.Recorder("mic", "x.wav")
    clock = {"t": 0.0}
    monkeypatch.setattr(capture.time, "monotonic", lambda: clock["t"])
    rec._start_monotonic = 0.0
    clock["t"] = 8.0
    rec.pause()
    clock["t"] = 20.0  # 12 s di pausa in corso
    mk = rec.add_marker("in pausa")
    assert mk["t_ms"] == 8_000  # solo gli 8 s pre-pausa


def test_update_marker_changes_label():
    rec = capture.Recorder("mic", "x.wav")
    rec._start_monotonic = 0.0
    rec.add_marker("Segnalibro 1")
    updated = rec.update_marker(0, "Lotto X")
    assert updated is not None and updated["label"] == "Lotto X"
    assert rec._markers[0]["label"] == "Lotto X"


def test_update_marker_out_of_range_returns_none():
    rec = capture.Recorder("mic", "x.wav")
    assert rec.update_marker(0, "x") is None  # nessun marker
    rec._start_monotonic = 0.0
    rec.add_marker("a")
    assert rec.update_marker(5, "y") is None


@pytest.mark.slow
def test_real_mic_capture_produces_16k_mono(tmp_path):
    sd = pytest.importorskip("sounddevice")
    from vokari.audio import convert

    try:
        convert.check_ffmpeg()
    except RuntimeError:
        pytest.skip("ffmpeg non disponibile")
    try:
        sd.check_input_settings(channels=1, dtype="int16")
    except Exception:
        pytest.skip("nessun dispositivo di input disponibile")

    out = tmp_path / "real.wav"
    rec = capture.Recorder("mic", str(out))
    rec.start()
    time.sleep(1.0)  # registra ~1 secondo reale
    res = rec.stop()
    _, rate, ch = capture._read_wav_int16(str(out))
    assert rate == 16000 and ch == 1
    assert 0.5 < res.duration_s < 2.0
