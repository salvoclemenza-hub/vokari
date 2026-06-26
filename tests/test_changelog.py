"""Test del modulo changelog (novità della versione, Tema 2).

Cuore logico: `entries_since(entries, since, current)` — funzione PURA che seleziona le
voci di versione da mostrare in un popup "Novità" dopo un aggiornamento (versione > quella
vista l'ultima volta e <= versione corrente), ordinate dalla più recente. Più il giro
end-to-end via `Api.get_changelog`.
"""

import json

import pytest
from app import changelog as cl

# Voci di esempio (ordine sparso di proposito: la funzione deve ordinare lei).
_ENTRIES = [
    {"version": "0.1.0", "date": "2026-06-01", "title": "Primo rilascio", "highlights": []},
    {"version": "0.1.2", "date": "2026-06-25", "title": "Onboarding", "highlights": []},
    {"version": "0.1.1", "date": "2026-06-20", "title": "Fix", "highlights": []},
]


class TestEntriesSince:
    def test_solo_versioni_piu_recenti_di_since(self):
        out = cl.entries_since(_ENTRIES, since="0.1.0", current="0.1.2")
        assert [e["version"] for e in out] == ["0.1.2", "0.1.1"]

    def test_ordina_dalla_piu_recente(self):
        out = cl.entries_since(_ENTRIES, since="", current="0.1.2")
        assert [e["version"] for e in out] == ["0.1.2", "0.1.1", "0.1.0"]

    def test_since_vuoto_include_tutte_fino_a_current(self):
        out = cl.entries_since(_ENTRIES, since="", current="0.1.1")
        assert [e["version"] for e in out] == ["0.1.1", "0.1.0"]

    def test_since_uguale_current_nessuna_voce(self):
        assert cl.entries_since(_ENTRIES, since="0.1.2", current="0.1.2") == []

    def test_esclude_versioni_oltre_current(self):
        # Una voce futura nel file (per errore) non deve comparire prima del suo rilascio.
        future = [*_ENTRIES, {"version": "0.2.0", "date": "x", "title": "futuro", "highlights": []}]
        out = cl.entries_since(future, since="0.1.1", current="0.1.2")
        assert [e["version"] for e in out] == ["0.1.2"]

    def test_versione_non_numerica_non_esplode(self):
        # current 'dev' (build di sviluppo) → nessuna voce numerica la supera "verso il basso".
        out = cl.entries_since(_ENTRIES, since="", current="dev")
        assert out == []

    @pytest.mark.parametrize("since", ["", "0.0.9", "0.1.0"])
    def test_mostra_almeno_la_corrente_per_chi_e_indietro(self, since):
        out = cl.entries_since(_ENTRIES, since=since, current="0.1.2")
        assert "0.1.2" in [e["version"] for e in out]


class TestLoad:
    def test_legge_il_changelog_versionato(self):
        # Il file reale del progetto deve esistere ed avere almeno la voce corrente.
        entries = cl.load()
        assert isinstance(entries, list)
        assert any(e.get("version") == "0.1.2" for e in entries)
        for e in entries:
            assert "version" in e and "title" in e and "highlights" in e

    def test_file_assente_torna_lista_vuota(self, tmp_path):
        assert cl.load(tmp_path / "non-esiste.json") == []

    def test_json_malformato_torna_lista_vuota(self, tmp_path):
        bad = tmp_path / "changelog.json"
        bad.write_text("{ non json", encoding="utf-8")
        assert cl.load(bad) == []

    def test_struttura_versioni_chiave(self, tmp_path):
        f = tmp_path / "changelog.json"
        f.write_text(json.dumps({"versions": [{"version": "1.0.0", "title": "x", "highlights": []}]}), encoding="utf-8")
        assert cl.load(f) == [{"version": "1.0.0", "title": "x", "highlights": []}]


class TestApiGetChangelog:
    def _api(self, tmp_path):
        from app.api import Api
        from app.jobs import JobStore

        from vokari.store.sessions_repo import SessionsRepo

        return Api(
            store=JobStore(jobs_dir=str(tmp_path / "jobs")),
            sessions=SessionsRepo(sessions_dir=str(tmp_path / "sessions")),
        )

    def test_ritorna_current_version_e_entries(self, tmp_path, monkeypatch):
        monkeypatch.setenv("VOKARI_HOME", str(tmp_path))
        api = self._api(tmp_path)
        res = api.get_changelog(since="0.0.1")
        assert "currentVersion" in res and "entries" in res
        assert isinstance(res["entries"], list)

    def test_since_uguale_corrente_nessuna_voce(self, tmp_path, monkeypatch):
        monkeypatch.setenv("VOKARI_HOME", str(tmp_path))
        api = self._api(tmp_path)
        current = api.get_changelog(since="")["currentVersion"]
        res = api.get_changelog(since=current)
        assert res["entries"] == []
