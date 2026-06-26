"""Rilevamento dell'ambiente di runtime di VOKARI.

`is_packaged()`: True se l'app gira come **pacchetto MSIX** (build Microsoft Store), False se
gira da sorgente o dallo ZIP. Determina i comportamenti vincolati dalle policy Store — in
particolare: l'app **non deve scaricare+eseguire binari di terze parti** (Ollama, LHM) da sé
(policy 10.2.2/10.2.3). In MSIX si **guida** l'utente a installarli; non si auto-installano.
**Avviare/usare** un binario che l'utente ha già installato resta consentito.

Vedi ADR-046 (distribuzione Store) e ollama_manager.can_auto_install.
"""

from __future__ import annotations

import ctypes
import sys
from functools import lru_cache

# Codici Win32 di GetCurrentPackageFullName:
_ERROR_INSUFFICIENT_BUFFER = 122  # ha identità di pacchetto (buffer nullo/troppo piccolo)
_APPMODEL_ERROR_NO_PACKAGE = 15700  # nessuna identità di pacchetto → non pacchettizzato


@lru_cache(maxsize=1)
def is_packaged() -> bool:
    """True se il processo ha un'identità di pacchetto MSIX/AppX (build Store).

    Usa l'API Win32 `GetCurrentPackageFullName`: chiamata con buffer nullo, ritorna
    `ERROR_INSUFFICIENT_BUFFER` se pacchettizzato, `APPMODEL_ERROR_NO_PACKAGE` altrimenti.
    Fail-safe: in caso di dubbio (eccezione, altri codici) ritorna False (= non Store).
    """
    if not sys.platform.startswith("win"):
        return False
    try:
        length = ctypes.c_uint32(0)
        rc = ctypes.windll.kernel32.GetCurrentPackageFullName(ctypes.byref(length), None)
    except (OSError, AttributeError):
        return False
    return rc == _ERROR_INSUFFICIENT_BUFFER
