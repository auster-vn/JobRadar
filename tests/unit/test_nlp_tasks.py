import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any

import pytest

from workers import nlp_tasks


class FakeSession:
    def __init__(self, updated: bool) -> None:
        self.updated = updated
        self.statement: Any = None
        self.committed = False
        self.rolled_back = False

    async def get(self, *_: object) -> SimpleNamespace:
        return SimpleNamespace(has_cv=True, cv_text_encrypted=b"encrypted-cv")

    async def execute(self, statement: Any) -> SimpleNamespace:
        self.statement = statement
        return SimpleNamespace(scalar_one_or_none=lambda: uuid.uuid4() if self.updated else None)

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


def _patch_profile_dependencies(monkeypatch: pytest.MonkeyPatch, session: FakeSession) -> None:
    @asynccontextmanager
    async def fake_session_factory() -> AsyncIterator[FakeSession]:
        yield session

    async def no_op(*_: object) -> None:
        return None

    async def load_cv(*_: object) -> str:
        return "Python backend engineer"

    monkeypatch.setattr(nlp_tasks, "session_factory", fake_session_factory)
    monkeypatch.setattr(nlp_tasks, "set_profile_owner", no_op)
    monkeypatch.setattr(nlp_tasks, "load_cv_text", load_cv)
    monkeypatch.setattr(nlp_tasks, "encode_texts", lambda _: [[0.0] * 384])


@pytest.mark.asyncio
async def test_profile_embedding_skips_when_profile_or_cv_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession(updated=False)
    _patch_profile_dependencies(monkeypatch, session)
    user_id = uuid.uuid4()

    result = await nlp_tasks._embed_profile(user_id)

    assert result == {"status": "skipped", "reason": "profile_or_cv_changed"}
    assert "user_profiles.cv_text_encrypted" in str(session.statement)
    parameters = session.statement.compile().params
    assert user_id in parameters.values()
    assert b"encrypted-cv" in parameters.values()
    assert session.rolled_back
    assert not session.committed


@pytest.mark.asyncio
async def test_profile_embedding_commits_current_cv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession(updated=True)
    _patch_profile_dependencies(monkeypatch, session)
    user_id = uuid.uuid4()

    result = await nlp_tasks._embed_profile(user_id)

    assert result == {
        "status": "completed",
        "user_id": str(user_id),
        "model": nlp_tasks.MODEL_NAME,
    }
    assert session.committed
    assert not session.rolled_back
