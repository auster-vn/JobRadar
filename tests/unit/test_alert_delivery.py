import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlalchemy import Table

from api.models import AlertEvent, Job, JobAlert, Notification, User
from workers import alert_tasks


class _Rows:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows

    def all(self) -> list[Any]:
        return self.rows


class _AlertSession:
    def __init__(
        self,
        *,
        alert_rows: list[Any],
        jobs: list[Job],
        event_rows: list[Any],
        scalar_results: list[uuid.UUID | None],
    ) -> None:
        self.execute_results = [_Rows(alert_rows), _Rows(event_rows)]
        self.jobs = jobs
        self.scalar_results = scalar_results
        self.scalar_statements: list[Any] = []
        self.commit_calls = 0
        self.rollback_calls = 0

    async def execute(self, statement: object) -> _Rows:
        return self.execute_results.pop(0)

    async def scalars(self, statement: object) -> _Rows:
        return _Rows(self.jobs)

    async def scalar(self, statement: Any) -> uuid.UUID | None:
        self.scalar_statements.append(statement)
        return self.scalar_results.pop(0)

    async def commit(self) -> None:
        self.commit_calls += 1

    async def rollback(self) -> None:
        self.rollback_calls += 1


def _fixtures() -> tuple[JobAlert, User, Job]:
    user_id = uuid.uuid4()
    alert = JobAlert(
        id=uuid.uuid4(),
        user_id=user_id,
        name="Python roles",
        required_skills=["Python"],
        min_salary=None,
        job_levels=[],
        locations=[],
        skill_match_min_pct=Decimal("60"),
        channel="email",
        is_active=True,
    )
    user = User(
        id=user_id,
        email="candidate@example.com",
        is_active=True,
    )
    job = Job(
        id=uuid.uuid4(),
        platform="test",
        platform_job_id="retry-job",
        company_id=uuid.uuid4(),
        title="Python Engineer",
        location=[],
        skills_required=["Python"],
        salary_currency="VND",
        salary_negotiable=False,
        is_active=True,
        posted_at=datetime.now(UTC),
    )
    return alert, user, job


@pytest.mark.asyncio
async def test_failed_alert_event_is_atomically_reclaimed_and_delivered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alert, user, job = _fixtures()
    event_id = uuid.uuid4()
    session = _AlertSession(
        alert_rows=[(alert, user)],
        jobs=[job],
        event_rows=[(alert.id, job.id, "failed", datetime.now(UTC))],
        scalar_results=[event_id, event_id],
    )
    deliveries: list[uuid.UUID] = []

    @asynccontextmanager
    async def fake_session_factory() -> AsyncIterator[_AlertSession]:
        yield session

    async def deliver(delivery_alert: JobAlert, delivery_user: User, delivery_job: Job) -> None:
        assert delivery_alert.id == alert.id
        assert delivery_user.id == user.id
        deliveries.append(delivery_job.id)

    monkeypatch.setattr(alert_tasks, "session_factory", fake_session_factory)
    monkeypatch.setattr(alert_tasks, "_deliver", deliver)

    result = await alert_tasks.evaluate_alerts()

    assert result == {
        "status": "completed",
        "alerts_checked": 1,
        "alerts_sent": 1,
        "deliveries_failed": 0,
        "errors": [],
    }
    assert deliveries == [job.id]
    assert session.commit_calls == 2
    claim_sql = str(session.scalar_statements[0])
    assert "ON CONFLICT" in claim_sql
    assert "uq_alert_event_alert_job" in claim_sql


@pytest.mark.asyncio
async def test_failed_attempts_consume_the_per_alert_run_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alert, user, first_job = _fixtures()
    second_job = Job(
        id=uuid.uuid4(),
        platform="test",
        platform_job_id="second-job",
        company_id=uuid.uuid4(),
        title="Another Python Engineer",
        location=[],
        skills_required=["Python"],
        salary_currency="VND",
        salary_negotiable=False,
        is_active=True,
        posted_at=datetime.now(UTC),
    )
    event_id = uuid.uuid4()
    session = _AlertSession(
        alert_rows=[(alert, user)],
        jobs=[first_job, second_job],
        event_rows=[],
        scalar_results=[event_id, event_id],
    )
    deliveries: list[uuid.UUID] = []

    @asynccontextmanager
    async def fake_session_factory() -> AsyncIterator[_AlertSession]:
        yield session

    async def fail_delivery(alert: JobAlert, user: User, job: Job) -> None:
        deliveries.append(job.id)
        raise RuntimeError("smtp unavailable")

    monkeypatch.setattr(alert_tasks, "session_factory", fake_session_factory)
    monkeypatch.setattr(alert_tasks, "_deliver", fail_delivery)
    monkeypatch.setattr(
        alert_tasks,
        "get_settings",
        lambda: SimpleNamespace(max_alert_deliveries_per_run=1),
    )

    result = await alert_tasks.evaluate_alerts()

    assert deliveries == [first_job.id]
    assert result["status"] == "partial"
    assert result["deliveries_failed"] == 1
    assert result["errors"] == ["deliveries_failed:1"]


def test_direct_celery_alert_task_uses_the_bounded_wrapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def never_finishes() -> dict[str, Any]:
        await asyncio.Event().wait()
        return {"status": "completed"}

    monkeypatch.setattr(alert_tasks, "evaluate_alerts", never_finishes)
    monkeypatch.setattr(alert_tasks, "ALERT_EVALUATION_TIMEOUT_SECONDS", 0.001)

    result = alert_tasks.check_and_fire.run()

    assert result["status"] == "failed"
    assert result["errors"] == ["TimeoutError"]


def test_recommendation_notifications_have_database_uniqueness_metadata() -> None:
    notification_table = cast(Table, Notification.__table__)
    alert_event_table = cast(Table, AlertEvent.__table__)
    index = next(
        index
        for index in notification_table.indexes
        if index.name == "uq_notifications_user_job_recommendation"
    )

    assert index.unique
    predicate = str(index.dialect_options["postgresql"]["where"])
    assert "kind = 'job_recommendation'" in predicate
    assert "job_id IS NOT NULL" in predicate
    assert "attempt_count" in alert_event_table.columns
    assert "last_attempt_at" in alert_event_table.columns
