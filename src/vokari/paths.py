"""Directory userData di VOKARI. Override con env VOKARI_HOME (usato nei test)."""

import os
from dataclasses import dataclass
from pathlib import Path

import platformdirs

APP_NAME = "vokari"
_ENV_HOME = "VOKARI_HOME"


@dataclass(frozen=True)
class AppDirs:
    config: Path
    data: Path
    cache: Path
    models: Path


def app_dirs() -> AppDirs:
    base = os.environ.get(_ENV_HOME)
    if base:
        root = Path(base)
        return AppDirs(root / "config", root / "data", root / "cache", root / "cache" / "models")
    cache = Path(platformdirs.user_cache_dir(APP_NAME, appauthor=False))
    return AppDirs(
        Path(platformdirs.user_config_dir(APP_NAME, appauthor=False)),
        Path(platformdirs.user_data_dir(APP_NAME, appauthor=False)),
        cache,
        cache / "models",
    )


def ensure_dirs() -> AppDirs:
    d = app_dirs()
    for p in (d.config, d.data, d.cache, d.models):
        p.mkdir(parents=True, exist_ok=True)
    return d
