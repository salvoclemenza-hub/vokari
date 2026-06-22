"""Impostazioni VOKARI: config non-segreto in JSON (userData) + API key in keyring."""

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

import keyring
from keyring.errors import PasswordDeleteError

from vokari.paths import app_dirs, ensure_dirs

_SERVICE = "vokari"
_KEY_NAME = "anthropic_api_key"


@dataclass
class Settings:
    brain: str = "claude"  # 'claude' | 'ollama'
    ollama_endpoint: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"  # qwen2.5:7b batte gemma2:9b su IT + JSON affidabile
    whisper_model: str = "large-v3-turbo"
    claude_model: str = "claude-sonnet-4-6"  # sonnet ≈ opus su analisi testo, ~5x meno costoso
    briefing_dir: str = ""
    obsidian_vault: str = ""
    default_mode: str = "solo"  # 'solo' | 'riunione'
    transcription_language: str = "it"  # IT fisso evita latenza language-detection
    live_preview: bool = True  # anteprima trascrizione durante la registrazione
    live_model: str = "base"  # modello piccolo per l'anteprima live


def _settings_path() -> Path:
    return app_dirs().config / "settings.json"


def load() -> Settings:
    p = _settings_path()
    if not p.exists():
        return Settings()
    raw = json.loads(p.read_text(encoding="utf-8"))
    known = {f.name for f in fields(Settings)}
    return Settings(**{k: v for k, v in raw.items() if k in known})


def save(s: Settings) -> None:
    ensure_dirs()
    _settings_path().write_text(json.dumps(asdict(s), indent=2, ensure_ascii=False), encoding="utf-8")


def get_api_key() -> str | None:
    return keyring.get_password(_SERVICE, _KEY_NAME)


def set_api_key(key: str) -> None:
    keyring.set_password(_SERVICE, _KEY_NAME, key)


def delete_api_key() -> None:
    """Rimuove la chiave API dal keyring (SET2). No-op se non era impostata."""
    try:
        keyring.delete_password(_SERVICE, _KEY_NAME)
    except PasswordDeleteError:
        pass  # chiave già assente: nulla da fare
