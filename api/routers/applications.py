import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.core.database import get_session
from api.core.security import get_current_user
from api.models import Application, AuditLog, Job, User
from api.schemas.applications import (
    ApplicationCreate,
    ApplicationPage,
    ApplicationPagination,
    ApplicationResponse,
    ApplicationStatus,
    ApplicationUpdate,
)
from api.services.profile_security import set_profile_owner

router = APIRouter(prefix="/api/applications", tags=["applications"])
Session = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]
APPLIED_STATUSES = {"applied", "interviewing", "offer", "rejected", "withdrawn"}


def _constraint_name(exc: IntegrityError) -> str | None:
    candidates = (
        exc.orig,
        getattr(exc.orig, "orig", None),
        getattr(exc.orig, "__cause__", None),
    )
    for candidate in candidates:
        value = getattr(candidate, "constraint_name", None)
        if isinstance(value, str):
            return value
    return None


async def _owned_application(
    session: AsyncSession,
    user_id: uuid.UUID,
    application_id: uuid.UUID,
) -> Application:
    await set_profile_owner(session, user_id)
    application = await session.scalar(
        select(Application)
        .where(Application.id == application_id, Application.user_id == user_id)
        .options(selectinload(Application.job).selectinload(Job.company))
    )
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")
    return application


async def _application_for_job(
    session: AsyncSession,
    user_id: uuid.UUID,
    job_id: uuid.UUID,
) -> Application | None:
    application: Application | None = await session.scalar(
        select(Application)
        .where(Application.user_id == user_id, Application.job_id == job_id)
        .options(selectinload(Application.job).selectinload(Job.company))
    )
    return application


@router.get("", response_model=ApplicationPage)
async def list_applications(
    response: Response,
    user: CurrentUser,
    session: Session,
    application_status: Annotated[ApplicationStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ApplicationPage:
    await set_profile_owner(session, user.id)
    filters = [Application.user_id == user.id]
    if application_status is not None:
        filters.append(Application.status == application_status)
    statement = (
        select(Application)
        .where(*filters)
        .options(selectinload(Application.job).selectinload(Job.company))
        .order_by(Application.updated_at.desc(), Application.id.desc())
        .limit(limit)
        .offset(offset)
    )
    applications = list((await session.scalars(statement)).all())
    total = int(
        (await session.scalar(select(func.count()).select_from(Application).where(*filters))) or 0
    )
    response.headers["Cache-Control"] = "private, no-store"
    return ApplicationPage(
        data=[ApplicationResponse.model_validate(item) for item in applications],
        pagination=ApplicationPagination(
            limit=limit,
            offset=offset,
            total_count=total,
            has_more=offset + len(applications) < total,
        ),
    )


@router.post(
    "",
    response_model=ApplicationResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_200_OK: {
            "model": ApplicationResponse,
            "description": "Existing application returned without modification",
        }
    },
)
async def create_application(
    payload: ApplicationCreate,
    response: Response,
    user: CurrentUser,
    session: Session,
) -> ApplicationResponse:
    await set_profile_owner(session, user.id)
    existing = await _application_for_job(session, user.id, payload.job_id)
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        response.headers["Cache-Control"] = "private, no-store"
        return ApplicationResponse.model_validate(existing)
    job = await session.scalar(
        select(Job)
        .where(Job.id == payload.job_id, Job.is_active.is_(True))
        .options(selectinload(Job.company))
    )
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")

    values = payload.model_dump()
    if values["status"] in APPLIED_STATUSES and values["applied_at"] is None:
        values["applied_at"] = datetime.now(UTC)
    application_id = uuid.uuid4()
    application = Application(
        id=application_id,
        user_id=user.id,
        job=job,
        **values,
    )
    session.add(application)
    session.add(
        AuditLog(
            user_id=user.id,
            action="application.created",
            entity_type="application",
            entity_id=application_id,
            details={"job_id": str(payload.job_id), "status": payload.status},
        )
    )
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if _constraint_name(exc) != "uq_applications_user_job":
            raise
        await set_profile_owner(session, user.id)
        existing = await _application_for_job(session, user.id, payload.job_id)
        if existing is None:
            raise RuntimeError("application uniqueness conflict row was not readable") from exc
        response.status_code = status.HTTP_200_OK
        response.headers["Cache-Control"] = "private, no-store"
        return ApplicationResponse.model_validate(existing)
    response.headers["Cache-Control"] = "private, no-store"
    return ApplicationResponse.model_validate(application)


@router.patch("/{application_id}", response_model=ApplicationResponse)
async def update_application(
    application_id: uuid.UUID,
    payload: ApplicationUpdate,
    response: Response,
    user: CurrentUser,
    session: Session,
) -> ApplicationResponse:
    application = await _owned_application(session, user.id, application_id)
    changes = payload.model_dump(exclude_unset=True)
    next_status = changes.get("status", application.status)
    if (
        next_status in APPLIED_STATUSES
        and application.applied_at is None
        and "applied_at" not in changes
    ):
        changes["applied_at"] = datetime.now(UTC)
    for field, value in changes.items():
        setattr(application, field, value)
    session.add(
        AuditLog(
            user_id=user.id,
            action="application.updated",
            entity_type="application",
            entity_id=application.id,
            details={"fields": sorted(changes), "status": application.status},
        )
    )
    await session.commit()
    response.headers["Cache-Control"] = "private, no-store"
    return ApplicationResponse.model_validate(application)
