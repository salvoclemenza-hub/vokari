from vokari.store.session import Session
from vokari.store.sessions_repo import SessionsRepo


def test_save_get_roundtrip(tmp_path):
    repo = SessionsRepo(tmp_path)
    s = Session.new(title="Riunione Q3", mode="riunione", model="large-v3-turbo")
    s.transcript = "discussione sul budget e il fornitore"
    repo.save(s)
    got = repo.get(s.id)
    assert got is not None
    assert got.title == "Riunione Q3" and got.mode == "riunione"
    assert got.transcript == "discussione sul budget e il fornitore"


def test_get_missing_returns_none(tmp_path):
    assert SessionsRepo(tmp_path).get("nope") is None


def test_list_all_sorted_by_date_desc(tmp_path):
    repo = SessionsRepo(tmp_path)
    a = Session.new(title="A")
    a.created_at = "2026-06-01T10:00:00+00:00"
    b = Session.new(title="B")
    b.created_at = "2026-06-05T10:00:00+00:00"
    repo.save(a)
    repo.save(b)
    assert [s.title for s in repo.list_all()] == ["B", "A"]


def test_search_fulltext_on_title_and_transcript(tmp_path):
    repo = SessionsRepo(tmp_path)
    a = Session.new(title="Riunione prodotto")
    a.transcript = "parliamo del fornitore acme"
    b = Session.new(title="Memo idee")
    b.transcript = "nuova app mobile offline"
    repo.save(a)
    repo.save(b)
    assert [s.title for s in repo.search("fornitore")] == ["Riunione prodotto"]
    assert [s.title for s in repo.search("app")] == ["Memo idee"]
    assert {s.title for s in repo.search("")} == {"Riunione prodotto", "Memo idee"}
