import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import PipelineRun
from api.routers import cron
from flows import daily_ingestion
from scripts import run_daily_pipeline as pipeline_script
from workers import pipeline_tasks
from workers.scrape_tasks import ScrapeResult


def _scrape_result(source: str, jobs_found: int = 1) -> ScrapeResult:
    return {
        "source": source,
        "status": "completed",
        "jobs_found": jobs_found,
        "errors": [],
        "jobs_new": jobs_found,
        "jobs_updated": 0,
    }


@pytest.mark.asyncio
async def test_pipeline_defers_alerts_until_after_recommendations_and_isolates_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    async def ingest(*, evaluate_notifications: bool = True) -> dict[str, Any]:
        events.append(f"ingestion:{evaluate_notifications}")
        return {"status": "completed", "jobs_found": 3, "errors": []}

    async def recommend() -> dict[str, Any]:
        events.append("recommendations")
        raise RuntimeError("provider failed")

    async def evaluate_alerts() -> dict[str, Any]:
        events.append("alerts")
        return {
            "status": "completed",
            "alerts_checked": 2,
            "alerts_sent": 1,
            "deliveries_failed": 0,
            "errors": [],
        }

    async def maintain() -> dict[str, Any]:
        events.append("maintenance")
        return {"status": "completed", "expired_jobs": 4, "errors": []}

    monkeypatch.setattr(pipeline_tasks, "run_daily_ingestion", ingest)
    monkeypatch.setattr(pipeline_tasks, "generate_daily_recommendations", recommend)
    monkeypatch.setattr(pipeline_tasks, "run_alert_evaluation", evaluate_alerts)
    monkeypatch.setattr(pipeline_tasks, "_expire_stale_jobs", maintain)

    result = await pipeline_tasks._execute_pipeline_stages()

    assert events == ["ingestion:False", "recommendations", "alerts", "maintenance"]
    assert result["status"] == "partial"
    assert result["expired_jobs"] == 4
    assert result["recommendations"] == {
        "status": "failed",
        "users_considered": 0,
        "scores_created": 0,
        "recommendations_created": 0,
        "errors": ["recommendations:RuntimeError"],
    }
    assert result["alerts"] == {
        "status": "completed",
        "alerts_checked": 2,
        "alerts_sent": 1,
        "deliveries_failed": 0,
        "errors": [],
    }


def test_pipeline_errors_follow_execution_order_and_add_status_markers() -> None:
    result: dict[str, Any] = {
        "ingestion": {"status": "partial", "errors": []},
        "itviec": {"status": "failed", "errors": ["i" * 350]},
        "topcv": {"status": "completed", "errors": []},
        "vietnamworks": {"status": "partial", "errors": ["source-warning"]},
        "recommendations": {"status": "partial", "errors": ["ranking-warning"]},
        "alerts": {"status": "failed", "errors": []},
        "maintenance": {"status": "completed", "errors": []},
    }

    errors = pipeline_tasks._pipeline_errors(result)

    assert [error["stage"] for error in errors] == [
        "ingestion",
        "itviec",
        "vietnamworks",
        "recommendations",
        "alerts",
    ]
    assert errors[0]["error"] == "stage_status:partial"
    assert len(errors[1]["error"]) == 300
    assert errors[-1]["error"] == "stage_status:failed"


def test_pipeline_error_aggregation_is_bounded() -> None:
    errors = pipeline_tasks._pipeline_errors(
        {
            "ingestion": {
                "status": "failed",
                "errors": [f"failure-{index}" for index in range(150)],
            }
        }
    )

    assert len(errors) == 100
    assert errors[-1] == {"stage": "ingestion", "error": "failure-99"}


def test_redelivered_worker_task_reclaims_the_running_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = uuid.uuid4()
    calls: list[tuple[uuid.UUID, bool]] = []

    async def execute(
        requested_run_id: uuid.UUID,
        *,
        reclaim_running: bool = False,
    ) -> dict[str, Any]:
        calls.append((requested_run_id, reclaim_running))
        return {"status": "completed"}

    monkeypatch.setattr(pipeline_tasks, "execute_daily_pipeline", execute)
    task = pipeline_tasks.run_daily_pipeline
    task.push_request(delivery_info={"redelivered": True})
    try:
        result = task.run(str(run_id))
    finally:
        task.pop_request()

    assert result == {"status": "completed"}
    assert calls == [(run_id, True)]


@pytest.mark.asyncio
async def test_daily_ingestion_bounds_pages_and_can_defer_alerts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received_pages: list[int] = []

    async def ingest_itviec(pages: int) -> ScrapeResult:
        received_pages.append(pages)
        return _scrape_result("itviec")

    async def ingest_topcv() -> ScrapeResult:
        return _scrape_result("topcv")

    async def ingest_vietnamworks() -> ScrapeResult:
        return _scrape_result("vietnamworks")

    async def unexpected_alert_evaluation() -> dict[str, Any]:
        raise AssertionError("alerts must remain deferred")

    monkeypatch.setattr(daily_ingestion, "ingest_itviec", ingest_itviec)
    monkeypatch.setattr(daily_ingestion, "ingest_topcv", ingest_topcv)
    monkeypatch.setattr(daily_ingestion, "ingest_vietnamworks", ingest_vietnamworks)
    monkeypatch.setattr(
        daily_ingestion,
        "run_alert_evaluation",
        unexpected_alert_evaluation,
    )

    result = await daily_ingestion.run_daily_ingestion(
        pages=10_000,
        evaluate_notifications=False,
    )

    assert received_pages == [daily_ingestion.MAX_DAILY_ITVIEC_PAGES]
    assert result["status"] == "completed"
    assert result["alerts"] == {"status": "deferred", "errors": []}


@pytest.mark.asyncio
async def test_alert_delivery_failures_make_the_stage_partial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def evaluate_alerts() -> dict[str, Any]:
        return {
            "status": "completed",
            "alerts_checked": 2,
            "alerts_sent": 1,
            "deliveries_failed": 1,
        }

    monkeypatch.setattr(daily_ingestion, "evaluate_alerts", evaluate_alerts)

    result = await daily_ingestion.run_alert_evaluation()

    assert result["status"] == "partial"
    assert result["errors"] == ["deliveries_failed:1"]


@pytest.mark.asyncio
async def test_alert_evaluation_has_a_standalone_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def evaluate_alerts() -> dict[str, Any]:
        await asyncio.Event().wait()
        return {"status": "completed"}

    monkeypatch.setattr(daily_ingestion, "evaluate_alerts", evaluate_alerts)
    monkeypatch.setattr(daily_ingestion, "ALERT_EVALUATION_TIMEOUT_SECONDS", 0.001)

    result = await daily_ingestion.run_alert_evaluation()

    assert result["status"] == "failed"
    assert result["errors"] == ["TimeoutError"]


class _CronSession:
    def __init__(self, scalar_results: list[object | None]) -> None:
        self.scalar_results = scalar_results
        self.commit_calls = 0
        self.rollback_calls = 0

    async def scalar(self, statement: object) -> object | None:
        return self.scalar_results.pop(0)

    async def execute(self, statement: object) -> SimpleNamespace:
        return SimpleNamespace(rowcount=1)

    async def commit(self) -> None:
        self.commit_calls += 1

    async def rollback(self) -> None:
        self.rollback_calls += 1


class _TaskDispatcher:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def delay(self, run_id: str) -> SimpleNamespace:
        self.calls.append(run_id)
        return SimpleNamespace(id="celery-task-id")


def _pipeline_run(*, kind: str, status: str, key: str) -> PipelineRun:
    return PipelineRun(
        id=uuid.uuid4(),
        kind=kind,
        status=status,
        idempotency_key=key,
        records_processed=0,
        errors=[],
        details={},
    )


@pytest.mark.asyncio
async def test_cron_retries_a_failed_idempotent_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = "daily-retry-key"
    existing = _pipeline_run(kind="daily_ingestion", status="failed", key=key)
    session = _CronSession([None, existing, existing.id])
    dispatcher = _TaskDispatcher()
    monkeypatch.setattr(cron, "run_daily_pipeline", dispatcher)

    result = await cron.enqueue_daily_pipeline(
        cast(AsyncSession, session),
        key,
    )

    assert result == {
        "status": "queued",
        "run_id": str(existing.id),
        "task_id": "celery-task-id",
        "idempotency_key": key,
    }
    assert session.commit_calls == 1
    assert dispatcher.calls == [str(existing.id)]


@pytest.mark.asyncio
async def test_cron_rejects_an_idempotency_key_owned_by_another_pipeline() -> None:
    key = "shared-kind-key"
    existing = _pipeline_run(kind="salary_training", status="completed", key=key)
    session = _CronSession([None, existing])

    with pytest.raises(HTTPException) as exc_info:
        await cron.enqueue_daily_pipeline(cast(AsyncSession, session), key)

    assert exc_info.value.status_code == 409
    assert session.commit_calls == 0


@pytest.mark.asyncio
async def test_script_treats_a_running_replay_as_an_idempotent_success(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    key = "daily-script-replay"
    existing = _pipeline_run(kind="daily_ingestion", status="running", key=key)
    existing.started_at = datetime.now(UTC)
    existing.details = {"jobs_found": 7, "status": "outdated-detail-status"}
    session = _CronSession([None, existing])

    @asynccontextmanager
    async def fake_session_factory() -> AsyncIterator[_CronSession]:
        yield session

    async def unexpected_execution(run_id: uuid.UUID) -> dict[str, Any]:
        raise AssertionError(f"pipeline replay should not execute: {run_id}")

    monkeypatch.setenv("PIPELINE_IDEMPOTENCY_KEY", key)
    monkeypatch.setattr(pipeline_script, "session_factory", fake_session_factory)
    monkeypatch.setattr(pipeline_script, "execute_daily_pipeline", unexpected_execution)

    exit_code = await pipeline_script.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload == {
        "run_id": str(existing.id),
        "jobs_found": 7,
        "status": "running",
    }
