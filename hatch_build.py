"""Build hook hatchling: include il frontend buildato nel wheel solo se esiste.

`app/main._find_dist` cerca il frontend in `app/_webdist/` quando VOKARI è
installato da wheel. Va quindi copiato lì al momento del build del wheel/sdist.
Ma un build **editable** (`uv sync --dev`) o un clone fresco NON hanno ancora
`frontend/dist` → un force-include *statico* fa fallire `uv sync` (e la CI, che
non builda il frontend nel job motore) con `FileNotFoundError`.

Questo hook aggiunge il force-include **dinamicamente**, solo quando
`frontend/dist` è realmente presente: sviluppo/CI restano verdi senza aver
buildato il frontend, mentre la distribuzione (wheel per Homebrew) resta
identica a prima quando `frontend/dist` c'è.
"""

from __future__ import annotations

import os

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version: str, build_data: dict) -> None:
        dist = os.path.join(self.root, "frontend", "dist")
        if os.path.isfile(os.path.join(dist, "index.html")):
            build_data.setdefault("force_include", {})[dist] = "app/_webdist"
