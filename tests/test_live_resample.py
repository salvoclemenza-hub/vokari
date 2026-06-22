import numpy as np

from vokari.transcribe.live import resample_to_16k_f32


def test_resample_passthrough_16k():
    x = np.arange(16000, dtype=np.int16)
    out = resample_to_16k_f32(x, 16000)
    assert out.dtype == np.float32
    assert len(out) == 16000
    assert out.max() <= 1.0 and out.min() >= -1.0


def test_resample_downsample_length():
    x = np.zeros(48000, dtype=np.int16)  # 1 s a 48k
    out = resample_to_16k_f32(x, 48000)
    assert abs(len(out) - 16000) <= 1  # ~1 s a 16k


def test_resample_empty():
    out = resample_to_16k_f32(np.zeros(0, dtype=np.int16), 48000)
    assert len(out) == 0 and out.dtype == np.float32
