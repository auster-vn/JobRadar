from datetime import date
from types import SimpleNamespace

import pytest

from api.routers import admin


@pytest.mark.asyncio
async def test_admin_can_queue_bounded_topcv_scrape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, int]] = []

    class FakeTask:
        @staticmethod
        def delay(**kwargs: int) -> SimpleNamespace:
            calls.append(kwargs)
            return SimpleNamespace(id="topcv-task-id")

    monkeypatch.setattr(admin, "scrape_topcv", FakeTask())

    response = await admin.trigger_scrape("topcv", pages=50)

    assert response == {
        "status": "queued",
        "task_id": "topcv-task-id",
        "platform": "topcv",
    }
    assert calls == [{"max_pages": 10}]


@pytest.mark.asyncio
async def test_admin_salary_readiness_returns_live_assessment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def rows() -> list[dict[str, object]]:
        return [
            {
                "source_key": "source:1",
                "source_snapshot_date": date(2026, 1, 1),
                "title_normalized": "Backend Developer",
                "job_level": "mid",
                "location": "Ha Noi",
                "salary_currency": "VND",
            }
        ]

    monkeypatch.setattr(admin, "load_salary_rows", rows)

    report = await admin.salary_data_readiness()

    assert report["ready"] is False
    assert report["sample_size"] == 1
    requirements = report["requirements"]
    assert isinstance(requirements, list)
    assert len(requirements) == 6
