import pytest

from vokari.llm import base
from vokari.llm.anthropic_provider import AnthropicProvider
from vokari.llm.base import LLMError, parse_json_lenient
from vokari.llm.ollama_provider import OllamaProvider


class _Block:
    def __init__(self, type_, text=None):
        self.type = type_
        self.text = text


class _Resp:
    def __init__(self, blocks):
        self.content = blocks


def test_anthropic_chat_json_extracts_text_block_and_strips_fences(monkeypatch):
    # risposta con un blocco thinking PRIMA del text (caso opus-4-8)
    resp = _Resp([_Block("thinking"), _Block("text", '```json\n{"a": 1}\n```')])

    class _Msgs:
        def create(self, **kw):
            return resp

    class _Client:
        messages = _Msgs()

    p = AnthropicProvider(api_key="sk-ant-x", model="claude-opus-4-8")
    monkeypatch.setattr(p, "_client", _Client())
    assert p.chat_json("sys", "user") == {"a": 1}


def test_anthropic_chat_text_returns_text_block(monkeypatch):
    resp = _Resp([_Block("thinking"), _Block("text", "  ciao  ")])

    class _Msgs:
        def create(self, **kw):
            return resp

    class _Client:
        messages = _Msgs()

    p = AnthropicProvider(api_key="sk-ant-x", model="claude-opus-4-8")
    monkeypatch.setattr(p, "_client", _Client())
    assert p.chat_text("sys", "user") == "ciao"


def test_anthropic_requires_api_key():
    with pytest.raises(base.LLMError, match="API key"):
        AnthropicProvider(api_key=None, model="claude-opus-4-8")


def test_ollama_chat_json_parses_response(monkeypatch):
    import vokari.llm.ollama_provider as om

    def _fake_post(url, json=None, timeout=None):
        class _R:
            def raise_for_status(self): ...
            def json(self_inner):
                return {"message": {"content": '{"b": 2}'}}

        return _R()

    monkeypatch.setattr(om.httpx, "post", _fake_post)
    p = OllamaProvider(endpoint="http://localhost:11434", model="gemma2:9b")
    assert p.chat_json("sys", "user") == {"b": 2}


def test_ollama_raises_llmerror_on_unexpected_shape(monkeypatch):
    import vokari.llm.ollama_provider as om

    def _fake_post(url, json=None, timeout=None):
        class _R:
            def raise_for_status(self): ...
            def json(self_inner):
                return {"unexpected": "shape"}  # niente message.content

        return _R()

    monkeypatch.setattr(om.httpx, "post", _fake_post)
    p = OllamaProvider(endpoint="http://localhost:11434", model="gemma2:9b")
    with pytest.raises(base.LLMError, match="risposta inattesa"):
        p.chat_text("sys", "user")


def test_anthropic_chat_json_does_not_pass_thinking(monkeypatch):
    """chat_json NON deve attivare thinking (overhead inutile su output JSON strutturato)."""
    captured = {}

    class _Msgs:
        def create(self, **kwargs):
            captured.update(kwargs)
            block = type("B", (), {"type": "text", "text": '{"meta": {}}', "thinking": None})()
            return type("R", (), {"content": [block]})()

    import anthropic

    import vokari.llm.anthropic_provider as ap

    monkeypatch.setattr(anthropic, "Anthropic", lambda api_key: type("C", (), {"messages": _Msgs()})())

    provider = ap.AnthropicProvider("sk-ant-fake", "claude-sonnet-4-6")
    provider.chat_json("system", "user")
    assert "thinking" not in captured, "chat_json non deve passare 'thinking' — overhead inutile su output JSON fisso"


def test_ollama_chat_json_passes_json_schema_to_format(monkeypatch):
    """chat_json con json_schema usa 'format': <schema_dict>, non 'format': 'json'."""
    import httpx

    import vokari.llm.ollama_provider as op

    posted = {}

    def _fake_post(url, *, json, timeout):
        posted.update(json)
        resp = type(
            "R",
            (),
            {
                "status_code": 200,
                "raise_for_status": lambda self: None,
                "json": lambda self: {"message": {"content": '{"meta": {}}'}},
            },
        )()
        return resp

    monkeypatch.setattr(httpx, "post", _fake_post)
    schema = {"type": "object", "properties": {"meta": {}}}
    provider = op.OllamaProvider("http://localhost:11434", "qwen2.5:7b")
    provider.chat_json("system", "user", json_schema=schema)

    assert posted.get("format") == schema, f"format deve essere il json_schema dict, non 'json': {posted.get('format')}"


def _capture_ollama_payload(monkeypatch, max_ctx=32768):
    """Monkeypatcha httpx.post (gestendo anche /api/show) e ritorna un dict col payload /api/chat."""
    import httpx

    posted: dict = {}
    monkeypatch.setattr(httpx, "post", _ollama_post_with_api_show(max_ctx=max_ctx, posted=posted))
    return posted


def test_ollama_sets_num_ctx_scaled_to_prompt_length(monkeypatch):
    """num_ctx dimensionato sul prompt: il default Ollama (2048) tronca i prompt lunghi e
    fa collassare le liste dell'analisi a vuoto. Prompt corto → ctx minimo; lungo → ctx maggiore."""
    from vokari.llm.ollama_provider import _CTX_MIN, OllamaProvider

    p = OllamaProvider("http://localhost:11434", "qwen2.5:7b")

    posted = _capture_ollama_payload(monkeypatch)
    p.chat_json("sys", "user breve")
    assert posted["options"]["num_ctx"] == _CTX_MIN, "prompt corto → num_ctx minimo (non 2048 di default)"

    posted_long = _capture_ollama_payload(monkeypatch)
    p.chat_json("sys", "x" * 40000)  # ~13k token stimati → deve superare il minimo
    assert posted_long["options"]["num_ctx"] > _CTX_MIN, "prompt lungo → num_ctx ampliato per non troncare"


def test_ollama_chat_text_also_sets_num_ctx(monkeypatch):
    """Anche chat_text (riepilogo a chunk) deve dimensionare num_ctx: chunk da 2000 parole > 2048 token."""
    from vokari.llm.ollama_provider import OllamaProvider

    posted = _capture_ollama_payload(monkeypatch)
    OllamaProvider("http://localhost:11434", "m").chat_text("sys", "user")
    assert "num_ctx" in posted["options"]


def _ollama_post_with_api_show(chat_content="{}", max_ctx=32768, posted=None):
    """Mock httpx.post che distingue /api/show (model_info) da /api/chat (message). Se `posted`
    è passato, registra il payload delle chiamate /api/chat (non quelle /api/show)."""
    def _fake_post(url, *, json, timeout):
        if url.endswith("/api/show"):
            body = {"model_info": {"qwen2.context_length": max_ctx}}
        else:
            if posted is not None:
                posted.update(json)
            body = {"message": {"content": chat_content}}
        return type(
            "R",
            (),
            {"status_code": 200, "raise_for_status": lambda self: None, "json": lambda self, b=body: b},
        )()

    return _fake_post


def test_ollama_model_max_ctx_reads_api_show(monkeypatch):
    """Legge il massimo contesto del modello da /api/show (chiave <arch>.context_length)."""
    import httpx

    from vokari.llm.ollama_provider import _CTX_OUTPUT_HEADROOM, OllamaProvider

    monkeypatch.setattr(httpx, "post", _ollama_post_with_api_show(max_ctx=32768))
    p = OllamaProvider("http://localhost:11434", "qwen2.5:7b")
    assert p.model_max_ctx() == 32768
    assert p.context_budget_tokens() == 32768 - _CTX_OUTPUT_HEADROOM


def test_ollama_model_max_ctx_falls_back_when_api_show_unavailable(monkeypatch):
    """Se /api/show non risponde (errore rete), num_ctx usa un fallback prudente, non crasha."""
    import httpx

    from vokari.llm.ollama_provider import _CTX_FALLBACK_MAX, OllamaProvider

    def _boom(url, *, json, timeout):
        raise httpx.ConnectError("giù")

    monkeypatch.setattr(httpx, "post", _boom)
    p = OllamaProvider("http://localhost:11434", "qwen2.5:7b")
    assert p.model_max_ctx() == _CTX_FALLBACK_MAX


def test_ollama_model_max_ctx_does_not_cache_fallback_then_retries(monkeypatch):
    """Check B: se /api/show fallisce (Ollama in avvio) model_max_ctx NON cacha il fallback —
    ritenta la volta dopo e legge il valore reale. Prima restava bloccato a 8192 per sempre,
    facendo riassumere inutilmente anche su qwen (32k)."""
    import httpx

    from vokari.llm.ollama_provider import _CTX_FALLBACK_MAX, OllamaProvider

    state = {"calls": 0}

    def _post(url, *, json, timeout):
        state["calls"] += 1
        if state["calls"] == 1:
            raise httpx.ConnectError("Ollama in avvio")
        body = {"model_info": {"qwen2.context_length": 32768}}
        return type(
            "R", (), {"status_code": 200, "raise_for_status": lambda self: None, "json": lambda self: body}
        )()

    monkeypatch.setattr(httpx, "post", _post)
    p = OllamaProvider("http://localhost:11434", "qwen2.5:7b")
    assert p.model_max_ctx() == _CTX_FALLBACK_MAX  # 1ª volta: fallback (non cachato)
    assert p._ctx_is_fallback is True
    assert p.model_max_ctx() == 32768  # 2ª volta: ritenta e legge il reale
    assert p._ctx_is_fallback is False
    assert p.model_max_ctx() == 32768  # ora è cachato: niente 3ª /api/show
    assert state["calls"] == 2, "dopo aver letto il valore reale non deve più interrogare /api/show"


def test_ollama_ctx_diagnostics_reports_real_max_and_planned_num_ctx(monkeypatch):
    """Check B: ctx_diagnostics espone il max reale, se è fallback, e il num_ctx pianificato —
    che su prompt grande deve raggiungere davvero il max reale del modello (hard_max)."""
    import httpx

    from vokari.llm.ollama_provider import OllamaProvider, _num_ctx_for

    monkeypatch.setattr(httpx, "post", _ollama_post_with_api_show(max_ctx=32768))
    p = OllamaProvider("http://localhost:11434", "qwen2.5:7b")
    big = "x" * 500_000  # ~166k token stimati >> 32768
    diag = p.ctx_diagnostics("sys", big)
    assert diag["model"] == "qwen2.5:7b"
    assert diag["ctx_max"] == 32768
    assert diag["ctx_is_fallback"] is False
    assert diag["num_ctx_planned"] == 32768, "num_ctx pianificato deve raggiungere il max reale"
    assert diag["num_ctx_planned"] == _num_ctx_for("sys", big, 32768)


def test_ollama_num_ctx_clamps_to_model_max(monkeypatch):
    """num_ctx non supera mai il massimo reale del modello, anche con prompt enorme."""
    import httpx

    posted: dict = {}
    monkeypatch.setattr(httpx, "post", _ollama_post_with_api_show(max_ctx=32768, posted=posted))
    p = OllamaProvider("http://localhost:11434", "qwen2.5:7b")
    p.chat_json("sys", "x" * 500_000)  # ~166k token stimati >> 32768 → deve clampare al max modello
    assert posted["options"]["num_ctx"] == 32768


def test_ollama_distinguishes_connect_vs_read_timeout(monkeypatch):
    """P3: messaggio onesto. ConnectError → 'non raggiungibile' (server giù); ReadTimeout →
    'Ollama è attivo ma … lento' (modello vivo che genera, non morto — caso ECO 5.0)."""
    import httpx

    from vokari.llm.ollama_provider import OllamaProvider

    p = OllamaProvider("http://localhost:11434", "qwen2.5:7b")

    def _connect_boom(url, *, json, timeout):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "post", _connect_boom)
    with pytest.raises(LLMError, match="non raggiungibile"):
        p.chat_text("s", "u")

    def _read_boom(url, *, json, timeout):
        raise httpx.ReadTimeout("too slow")

    monkeypatch.setattr(httpx, "post", _read_boom)
    with pytest.raises(LLMError, match=r"attivo ma|lento"):
        p.chat_text("s", "u")


def test_ollama_stream_read_timeout_message_is_honest(monkeypatch):
    """P3 anche sullo streaming: un read-timeout durante chat_json_stream dà il messaggio
    'attivo ma lento', non 'non raggiungibile'."""
    import httpx

    from vokari.llm.ollama_provider import OllamaProvider

    monkeypatch.setattr(
        httpx,
        "post",
        _ollama_post_with_api_show(max_ctx=32768),  # /api/show ok (per _payload)
    )

    def _stream_boom(method, url, **kw):
        raise httpx.ReadTimeout("too slow")

    monkeypatch.setattr(httpx, "stream", _stream_boom)
    p = OllamaProvider("http://localhost:11434", "qwen2.5:7b")
    with pytest.raises(LLMError, match=r"attivo ma|lento"):
        p.chat_json_stream("s", "u")


def test_parse_json_lenient_handles_fence_with_language():
    """Gestisce ```json\\n e ``` json\\n (con spazio dopo lingua)."""
    text = '```json\n{"a": 1}\n```'
    assert parse_json_lenient(text) == {"a": 1}


def test_parse_json_lenient_handles_text_before_fence():
    """Gestisce testo esplicativo prima della fence."""
    text = 'Ecco il JSON:\n```json\n{"b": 2}\n```'
    assert parse_json_lenient(text) == {"b": 2}


def test_parse_json_lenient_plain_json_still_works():
    assert parse_json_lenient('{"c": 3}') == {"c": 3}


def test_parse_json_lenient_raises_on_invalid():
    with pytest.raises(LLMError):
        parse_json_lenient("questo non è json")
