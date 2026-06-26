import pytest

from vokari import settings as st


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("VOKARI_HOME", str(tmp_path))
    # keyring in-memory: niente accesso al secret store reale
    store = {}
    monkeypatch.setattr(st.keyring, "set_password", lambda s, k, v: store.__setitem__((s, k), v))
    monkeypatch.setattr(st.keyring, "get_password", lambda s, k: store.get((s, k)))

    def _del(s, k):
        if (s, k) in store:
            del store[(s, k)]
        else:
            raise st.PasswordDeleteError("not found")

    monkeypatch.setattr(st.keyring, "delete_password", _del)


def test_defaults_when_no_file():
    s = st.load()
    assert s.whisper_model == "large-v3-turbo"
    assert s.brain == "claude"
    assert s.default_mode == "solo"


def test_save_load_roundtrip():
    s = st.load()
    s.whisper_model = "large-v3"
    s.obsidian_vault = r"C:\Vault"
    st.save(s)
    s2 = st.load()
    assert s2.whisper_model == "large-v3"
    assert s2.obsidian_vault == r"C:\Vault"


def test_load_ignores_unknown_keys(tmp_path):
    from vokari.paths import ensure_dirs

    p = ensure_dirs().config / "settings.json"
    p.write_text('{"whisper_model": "small", "_legacy": 1}', encoding="utf-8")
    s = st.load()
    assert s.whisper_model == "small"  # niente crash su chiavi sconosciute


def test_api_key_via_keyring():
    assert st.get_api_key() is None
    st.set_api_key("sk-ant-test")
    assert st.get_api_key() == "sk-ant-test"


def test_delete_api_key():
    """SET2: delete_api_key rimuove la chiave; idempotente (no-op se già assente)."""
    st.set_api_key("sk-ant-test")
    assert st.get_api_key() == "sk-ant-test"
    st.delete_api_key()
    assert st.get_api_key() is None
    st.delete_api_key()  # secondo delete: PasswordDeleteError gestito, nessuna eccezione


def test_claude_model_default():
    s = st.load()
    assert s.claude_model == "claude-sonnet-4-6"


def test_live_preview_defaults():
    s = st.load()
    assert s.live_preview is True
    assert s.live_model == "base"


def test_live_preview_roundtrip():
    s = st.load()
    s.live_preview = False
    s.live_model = "small"
    st.save(s)
    s2 = st.load()
    assert s2.live_preview is False
    assert s2.live_model == "small"


def test_onboarded_defaults_false():
    # primo avvio: il wizard di onboarding non è ancora stato completato
    assert st.load().onboarded is False


def test_onboarded_roundtrip():
    s = st.load()
    s.onboarded = True
    st.save(s)
    assert st.load().onboarded is True


def test_last_seen_version_defaults_empty():
    # prima volta: nessuna versione di novità ancora vista → il popup mostrerà tutte le voci
    assert st.load().last_seen_version == ""


def test_last_seen_version_roundtrip():
    s = st.load()
    s.last_seen_version = "0.1.2"
    st.save(s)
    assert st.load().last_seen_version == "0.1.2"


def test_app_language_defaults_it():
    assert st.load().app_language == "it"


def test_app_language_roundtrip():
    s = st.load()
    s.app_language = "en"
    st.save(s)
    assert st.load().app_language == "en"
