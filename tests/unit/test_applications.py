import uuid
from datetime import UTC, datetime
from typing import cast

import pytest
from fastapi import Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import Application, Company, Job, User
from api.routers.applications import create_application
from api.schemas.applications import ApplicationCreate


def _tracked_application() -> tuple[Application, Job]:
    company = Company(
        id=uuid.uuid4(),
        name="Example Co",
        name_normalized="example co",
        logo_url=None,
        company_type=None,
    )
    job = Job(
        id=uuid.uuid4(),
        platform="test",
        platform_job_id="job-1",
        company_id=company.id,
        company=company,
        title="Backend Engineer",
        title_normalized=None,
        source_url=None,
        job_level=None,
        job_type=None,
        location=[],
        salary_min=None,
        salary_max=None,
        salary_currency="VND",
        salary_negotiable=False,
        skills_required=[],
        posted_at=None,
        is_active=True,
    )
    now = datetime.now(UTC)
    return (
        Application(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            job_id=job.id,
            job=job,
            status="saved",
            notes=None,
            applied_at=None,
            created_at=now,
            updated_at=now,
        ),
        job,
    )


class _ExistingSession:
    def __init__(self, application: Application) -> None:
        self.application = application
        self.execute_calls = 0

    async def execute(self, statement: object, parameters: object = None) -> None:
        self.execute_calls += 1

    async def scalar(self, statement: object) -> Application:
        return self.application


@pytest.mark.asyncio
async def test_create_application_replay_returns_existing_resource_with_200() -> None:
    application, job = _tracked_application()
    user = User(
        id=application.user_id,
        email="person@example.com",
        is_active=True,
    )
    session = _ExistingSession(application)
    response = Response()

    result = await create_application(
        ApplicationCreate(job_id=job.id, status="offer", notes="ignored replay"),
        response,
        user,
        cast(AsyncSession, session),
    )

    assert response.status_code == status.HTTP_200_OK
    assert result.id == application.id
    assert result.status == "saved"
    assert result.notes is None
    assert session.execute_calls == 1


class _UniqueViolation(Exception):
    constraint_name = "uq_applications_user_job"


class _RacingSession:
    def __init__(self, job: Job, existing: Application) -> None:
        self.results: list[object] = [None, job, existing]
        self.added: list[object] = []
        self.execute_calls = 0
        self.rollback_calls = 0

    async def execute(self, statement: object, parameters: object = None) -> None:
        self.execute_calls += 1

    async def scalar(self, statement: object) -> object:
        return self.results.pop(0)

    def add(self, value: object) -> None:
        self.added.append(value)

    async def commit(self) -> None:
        raise IntegrityError("INSERT", {}, _UniqueViolation())

    async def rollback(self) -> None:
        self.rollback_calls += 1


@pytest.mark.asyncio
async def test_create_application_unique_race_returns_winning_row_with_200() -> None:
    existing, job = _tracked_application()
    user = User(
        id=existing.user_id,
        email="person@example.com",
        is_active=True,
    )
    session = _RacingSession(job, existing)
    response = Response()

    result = await create_application(
        ApplicationCreate(job_id=job.id),
        response,
        user,
        cast(AsyncSession, session),
    )

    assert response.status_code == status.HTTP_200_OK
    assert result.id == existing.id
    assert session.rollback_calls == 1
    assert session.execute_calls == 2
