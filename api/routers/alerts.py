import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_session
from api.core.security import get_current_user
from api.models import AlertEvent, JobAlert, User
from api.schemas.alerts import AlertCreate, AlertEventResponse, AlertResponse, AlertUpdate

router = APIRouter(prefix="/api/alerts", tags=["alerts"])
Session = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]


async def _owned_alert(session: AsyncSession, user_id: uuid.UUID, alert_id: uuid.UUID) -> JobAlert:
    alert = await session.scalar(
        select(JobAlert).where(JobAlert.id == alert_id, JobAlert.user_id == user_id)
    )
    if not alert:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")
    return alert


@router.post("", response_model=AlertResponse, status_code=status.HTTP_201_CREATED)
async def create_alert(payload: AlertCreate, user: CurrentUser, session: Session) -> AlertResponse:
    alert = JobAlert(user_id=user.id, **payload.model_dump())
    session.add(alert)
    await session.commit()
    await session.refresh(alert)
    return AlertResponse.model_validate(alert)


@router.get("", response_model=list[AlertResponse])
async def list_alerts(user: CurrentUser, session: Session) -> list[AlertResponse]:
    alerts = list(
        (await session.scalars(select(JobAlert).where(JobAlert.user_id == user.id))).all()
    )
    return [AlertResponse.model_validate(alert) for alert in alerts]


@router.get("/{alert_id}/history", response_model=list[AlertEventResponse])
async def alert_history(
    alert_id: uuid.UUID, user: CurrentUser, session: Session
) -> list[AlertEventResponse]:
    await _owned_alert(session, user.id, alert_id)
    events = list(
        (
            await session.scalars(
                select(AlertEvent)
                .where(AlertEvent.alert_id == alert_id)
                .order_by(AlertEvent.created_at.desc())
                .limit(100)
            )
        ).all()
    )
    return [AlertEventResponse.model_validate(event) for event in events]


@router.put("/{alert_id}", response_model=AlertResponse)
async def update_alert(
    alert_id: uuid.UUID,
    payload: AlertUpdate,
    user: CurrentUser,
    session: Session,
) -> AlertResponse:
    alert = await _owned_alert(session, user.id, alert_id)
    for field, value in payload.model_dump().items():
        setattr(alert, field, value)
    await session.commit()
    await session.refresh(alert)
    return AlertResponse.model_validate(alert)


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(
    alert_id: uuid.UUID, user: CurrentUser, session: Session, response: Response
) -> None:
    alert = await _owned_alert(session, user.id, alert_id)
    await session.delete(alert)
    await session.commit()
