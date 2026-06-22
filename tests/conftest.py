"""Fixture condivise per l'intera suite VOKARI.

BLINDATURA KEYRING (bug "pytest cancella la API key reale"):
VOKARI salva la API key Anthropic nel keyring OS (`vokari.settings`,
servizio/entry = 'vokari'/'anthropic_api_key'). Senza isolamento un test che
chiama `keyring.set_password`/`delete_password` — direttamente o via
`vokari.settings` — tocca l'entry di PRODUZIONE e può CANCELLARE la chiave reale
dell'utente (capitava con `test_api.py::test_set_api_key_stores_in_keyring_not_json`).

Questa fixture `autouse` sostituisce le funzioni del modulo `keyring` con uno
store in-memory per OGNI test della suite: nessun test — presente o futuro — può
più toccare il secret store reale. `settings.py` fa `import keyring` e chiama
`keyring.set_password(...)`, quindi patchare gli attributi del modulo intercetta
sia le chiamate via settings sia quelle didirette (`import keyring as kr`)."""

import keyring
import pytest


@pytest.fixture(autouse=True)
def _isolate_keyring(monkeypatch):
    store: dict[tuple[str, str], str] = {}
    monkeypatch.setattr(keyring, "set_password", lambda service, name, value: store.__setitem__((service, name), value))
    monkeypatch.setattr(keyring, "get_password", lambda service, name: store.get((service, name)))
    monkeypatch.setattr(keyring, "delete_password", lambda service, name: store.pop((service, name), None))
    return store


@pytest.fixture(autouse=True)
def _no_github_network():
    """`get_app_info()` recupera le stelle reali del repo via httpx (con cache di processo):
    pre-seedo la cache a 0 così NESSUN test colpisce la rete (suite veloce e deterministica)."""
    import app.api as _api

    prev = _api._stars_cache["value"]
    _api._stars_cache["value"] = 0
    yield
    _api._stars_cache["value"] = prev
