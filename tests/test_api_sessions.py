"""Tests for session title localization (#1).

A job saved with an empty title and app_language='en' must produce
a Session with title 'Untitled session' (via i18n.t('api.untitled_session')).
"""

import pytest
from app.api import Api
from app.jobs import Job, JobStore

from vokari import settings as S
from vokari.store.sessions_repo import SessionsRepo


class FakeWindow:
    def evaluate_js(self, js: str) -> None:
        pass


@pytest.fixture
def api_en(tmp_path, monkeypatch):
    monkeypatch.setenv("VOKARI_HOME", str(tmp_path))
    store = JobStore(jobs_dir=tmp_path / "jobs")
    sessions = SessionsRepo(sessions_dir=tmp_path / "sessions")
    a = Api(store=store, sessions=sessions)
    a._window = FakeWindow()
    s = S.load()
    s.app_language = "en"
    S.save(s)
    return a


def test_untitled_session_title_localized(api_en):
    """_save_session with empty job.title and app_language='en' → 'Untitled session'."""
    job = Job(
        id="t1",
        audio_path="",
        title="",
        transcript="hello world",
        duration_s=5.0,
        status="ready",
    )
    api_en._save_session(job)
    saved = api_en._sessions.get("t1")
    assert saved is not None, "session was not saved"
    assert saved.title == "Untitled session"
