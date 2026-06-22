"""Test di chat_json_stream sui due provider (Anthropic, Ollama).

Verificano il contratto dello streaming: on_delta riceve il testo grezzo ACCUMULATO
(cumulativo crescente), il dict finale è uguale a quello che darebbe chat_json, e
should_cancel interrompe la generazione ritornando un oggetto vuoto.
Nessuna rete reale: httpx e il client Anthropic sono mockati.
"""

import json

import httpx
import pytest

from vokari.llm.anthropic_provider import AnthropicProvider
from vokari.llm.ollama_provider import OllamaProvider


@pytest.fixture(autouse=True)
def _stub_api_show(monkeypatch):
    """OllamaProvider._payload interroga /api/show (httpx.post) per il num_ctx: lo stubbiamo
    offline così i test streaming (che mockano solo httpx.stream) restano deterministici."""

    def _fake_post(url, *, json=None, timeout=None):
        return type(
            "R",
            (),
            {
                "status_code": 200,
                "raise_for_status": lambda self: None,
                "json": lambda self: {"model_info": {"qwen2.context_length": 32768}},
            },
        )()

    monkeypatch.setattr(httpx, "post", _fake_post)

# ── Ollama: httpx.stream mockato con NDJSON ──────────────────────────────────


class _FakeStreamResponse:
    def __init__(self, lines):
        self._lines = lines

    def raise_for_status(self):
        return None

    def iter_lines(self):
        return iter(self._lines)


class _FakeStreamCtx:
    def __init__(self, lines, captured):
        self._lines = lines
        self._captured = captured

    def __enter__(self):
        return _FakeStreamResponse(self._lines)

    def __exit__(self, *a):
        return False


def _ndjson(*chunks, done_last=True):
    lines = []
    for i, c in enumerate(chunks):
        last = i == len(chunks) - 1
        lines.append(json.dumps({"message": {"content": c}, "done": last and done_last}))
    return lines


def test_ollama_stream_accumulates_and_parses(monkeypatch):
    lines = _ndjson('{"purpose":"Dec', 'idere"}')
    captured = {}

    def fake_stream(method, url, **kw):
        captured["payload"] = kw.get("json")
        return _FakeStreamCtx(lines, captured)

    monkeypatch.setattr(httpx, "stream", fake_stream)
    p = OllamaProvider("http://localhost:11434", "qwen2.5:7b")
    deltas = []
    out = p.chat_json_stream("sys", "usr", on_delta=deltas.append)

    assert out == {"purpose": "Decidere"}
    # delta cumulativi crescenti
    assert deltas == ['{"purpose":"Dec', '{"purpose":"Decidere"}']
    # streaming attivo + json mode nel payload
    assert captured["payload"]["stream"] is True
    assert "format" in captured["payload"]


def test_ollama_stream_cancel_returns_empty(monkeypatch):
    lines = _ndjson('{"purpose":"Dec', 'idere"}', done_last=False)
    monkeypatch.setattr(httpx, "stream", lambda *a, **k: _FakeStreamCtx(lines, {}))
    p = OllamaProvider("http://localhost:11434", "m")
    out = p.chat_json_stream("sys", "usr", should_cancel=lambda: True)
    assert out == {}


def test_ollama_stream_skips_malformed_lines(monkeypatch):
    lines = ["non-json", json.dumps({"message": {"content": '{"a":1}'}, "done": True})]
    monkeypatch.setattr(httpx, "stream", lambda *a, **k: _FakeStreamCtx(lines, {}))
    p = OllamaProvider("http://localhost:11434", "m")
    assert p.chat_json_stream("sys", "usr") == {"a": 1}


# ── Anthropic: client mockato con stream context manager ─────────────────────


class _FakeStream:
    def __init__(self, chunks):
        self.text_stream = list(chunks)
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def close(self):
        self.closed = True


class _FakeMessages:
    def __init__(self, chunks, sink):
        self._chunks = chunks
        self._sink = sink

    def stream(self, **kw):
        s = _FakeStream(self._chunks)
        self._sink.append(s)
        return s


class _FakeClient:
    def __init__(self, chunks, sink):
        self.messages = _FakeMessages(chunks, sink)


def _anthropic_with(chunks, sink):
    p = AnthropicProvider(api_key="sk-test", model="claude-sonnet-4-6")
    p._client = _FakeClient(chunks, sink)
    return p


def test_anthropic_stream_accumulates_and_parses():
    sink = []
    p = _anthropic_with(['{"purpose":"Dec', 'idere"}'], sink)
    deltas = []
    out = p.chat_json_stream("sys", "usr", on_delta=deltas.append)
    assert out == {"purpose": "Decidere"}
    assert deltas == ['{"purpose":"Dec', '{"purpose":"Decidere"}']


def test_anthropic_stream_cancel_closes_and_returns_empty():
    sink = []
    p = _anthropic_with(['{"purpose":"Dec', 'idere"}'], sink)
    out = p.chat_json_stream("sys", "usr", should_cancel=lambda: True)
    assert out == {}
    assert sink[0].closed is True  # lo stream è stato chiuso sul cancel


def test_both_providers_expose_chat_json_stream():
    # contratto: il fallback nell'analyzer si basa su hasattr → i provider reali devono averlo
    assert hasattr(OllamaProvider("http://x", "m"), "chat_json_stream")
    assert callable(AnthropicProvider(api_key="sk-x", model="m").chat_json_stream)


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
