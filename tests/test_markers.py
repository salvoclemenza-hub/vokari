from vokari import markers as m


def test_fmt_ts_minutes_seconds():
    assert m.fmt_ts(0) == "00:00"
    assert m.fmt_ts(90_000) == "01:30"  # 90 s
    assert m.fmt_ts(5_000) == "00:05"


def test_fmt_ts_hours():
    assert m.fmt_ts(3_600_000) == "1:00:00"  # 1 h
    assert m.fmt_ts(5_400_000) == "1:30:00"  # 1 h 30 m


def test_fmt_ts_clamps_negative():
    assert m.fmt_ts(-1000) == "00:00"


def test_marker_lines_formats_and_sorts():
    out = m.marker_lines([{"t_ms": 90_000, "label": "Lotto X"}, {"t_ms": 5_000, "label": "Intro"}])
    assert out == ["- 00:05 — Intro", "- 01:30 — Lotto X"]  # ordinati per tempo


def test_marker_lines_empty_label_shows_only_time():
    assert m.marker_lines([{"t_ms": 5_000, "label": "  "}]) == ["- 00:05"]
    assert m.marker_lines([{"t_ms": 5_000}]) == ["- 00:05"]


def test_marker_lines_none_and_garbage():
    assert m.marker_lines(None) == []
    assert m.marker_lines([]) == []
    assert m.marker_lines(["non-dict", 42]) == []  # voci non-dict saltate
