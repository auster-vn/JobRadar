import asyncio
import smtplib
import uuid
from collections.abc import Awaitable
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Any

import httpx
from sqlalchemy import and_, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.config import get_settings
from api.core.database import session_factory
from api.models import AlertEvent, Job, JobAlert, User
from workers.async_runner import run_async
from workers.celery_app import app

ALERT_EVALUATION_TIMEOUT_SECONDS = 110
ALERT_DELIVERY_LEASE = timedelta(minutes=5)


def job_matches(alert: JobAlert, job: Job) -> bool:
    if (
        not alert.required_skills
        and not alert.min_salary
        and not alert.job_levels
        and not alert.locations
    ):
        return False
    required = {skill.casefold() for skill in alert.required_skills}
    available = {skill.casefold() for skill in job.skills_required}
    skill_score = len(required & available) / max(1, len(required)) * 100 if required else 100
    if skill_score < float(alert.skill_match_min_pct):
        return False
    if alert.min_salary and (job.salary_max or job.salary_min or 0) < alert.min_salary:
        return False
    if alert.job_levels and job.job_level not in alert.job_levels:
        return False
    wanted_locations = {location.casefold() for location in alert.locations}
    job_locations = {location.casefold() for location in job.location}
    return not wanted_locations or bool(wanted_locations & job_locations)


def _send_email(recipient: str, subject: str, body: str) -> None:
    settings = get_settings()
    if not settings.smtp_host or not settings.smtp_user or not settings.smtp_password:
        raise RuntimeError("SMTP is not configured")
    message = EmailMessage()
    message["From"] = settings.smtp_user
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as client:
        client.starttls()
        client.login(settings.smtp_user, settings.smtp_password)
        client.send_message(message)


async def _send_telegram(chat_id: int, body: str) -> None:
    token = get_settings().telegram_bot_token
    if not token:
        raise RuntimeError("Telegram is not configured")
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": body, "disable_web_page_preview": True},
        )
        response.raise_for_status()


async def _deliver(alert: JobAlert, user: User, job: Job) -> None:
    body = f"{job.title}\n{job.source_url or 'Open JobRadar to view this job.'}"
    if alert.channel == "telegram":
        if user.telegram_id is None:
            raise RuntimeError("User has no Telegram chat ID")
        await _send_telegram(user.telegram_id, body)
    else:
        await asyncio.to_thread(_send_email, user.email, f"JobRadar: {job.title}", body)


async def bounded_alert_evaluation(
    operation: Awaitable[dict[str, Any]],
    *,
    timeout_seconds: float = ALERT_EVALUATION_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Run alert evaluation within a wall-time bound and normalize its status."""

    try:
        result = await asyncio.wait_for(operation, timeout=timeout_seconds)
        if not isinstance(result, dict):
            raise TypeError("alert evaluation did not return an object")
        raw_errors = result.get("errors")
        errors = raw_errors if isinstance(raw_errors, list) else []
        result["errors"] = errors
        delivery_failures = int(result.get("deliveries_failed", 0))
        if delivery_failures > 0:
            result["status"] = "partial"
            marker = f"deliveries_failed:{delivery_failures}"
            if marker not in errors:
                errors.append(marker)
        return result
    except Exception as exc:
        return {
            "status": "failed",
            "alerts_checked": 0,
            "alerts_sent": 0,
            "deliveries_failed": 0,
            "errors": [type(exc).__name__],
        }


async def _claim_alert_delivery(
    session: AsyncSession,
    *,
    alert: JobAlert,
    job: Job,
    attempted_at: datetime,
) -> uuid.UUID | None:
    event_id = uuid.uuid4()
    claimed_id = await session.scalar(
        insert(AlertEvent)
        .values(
            id=event_id,
            alert_id=alert.id,
            job_id=job.id,
            channel=alert.channel,
            status="pending",
            error=None,
            attempt_count=1,
            last_attempt_at=attempted_at,
        )
        .on_conflict_do_update(
            constraint="uq_alert_event_alert_job",
            set_={
                "channel": alert.channel,
                "status": "pending",
                "error": None,
                "sent_at": None,
                "attempt_count": AlertEvent.attempt_count + 1,
                "last_attempt_at": attempted_at,
            },
            where=or_(
                AlertEvent.status == "failed",
                and_(
                    AlertEvent.status == "pending",
                    or_(
                        AlertEvent.last_attempt_at.is_(None),
                        AlertEvent.last_attempt_at < attempted_at - ALERT_DELIVERY_LEASE,
                    ),
                ),
            ),
        )
        .returning(AlertEvent.id)
    )
    await session.commit()
    return claimed_id


async def _finish_alert_delivery(
    session: AsyncSession,
    *,
    event_id: uuid.UUID,
    alert: JobAlert,
    attempted_at: datetime,
    error: str | None,
) -> None:
    completed_at = datetime.now(UTC)
    delivery_status = "failed" if error is not None else "sent"
    if error is None:
        alert.last_triggered_at = completed_at
    finalized_id = await session.scalar(
        update(AlertEvent)
        .where(
            AlertEvent.id == event_id,
            AlertEvent.status == "pending",
            AlertEvent.last_attempt_at == attempted_at,
        )
        .values(
            status=delivery_status,
            error=error,
            sent_at=completed_at if error is None else None,
        )
        .returning(AlertEvent.id)
    )
    if finalized_id is None:
        await session.rollback()
        raise RuntimeError("alert delivery lease was lost before finalization")
    await session.commit()


async def evaluate_alerts() -> dict[str, Any]:
    checked = sent = failed = 0
    cutoff = datetime.now(UTC) - timedelta(days=2)
    settings = get_settings()
    async with session_factory() as session:
        alerts = list(
            (
                await session.execute(
                    select(JobAlert, User)
                    .join(User, User.id == JobAlert.user_id)
                    .where(JobAlert.is_active.is_(True), User.is_active.is_(True))
                )
            ).all()
        )
        jobs = list(
            (
                await session.scalars(
                    select(Job)
                    .where(Job.is_active.is_(True), Job.posted_at >= cutoff)
                    .order_by(Job.posted_at.desc())
                    .limit(500)
                )
            ).all()
        )
        existing = {
            (alert_id, job_id): (event_status, last_attempt_at)
            for alert_id, job_id, event_status, last_attempt_at in (
                await session.execute(
                    select(
                        AlertEvent.alert_id,
                        AlertEvent.job_id,
                        AlertEvent.status,
                        AlertEvent.last_attempt_at,
                    ).where(AlertEvent.alert_id.in_([alert.id for alert, _ in alerts]))
                )
            ).all()
        }
        for alert, user in alerts:
            checked += 1
            attempted_for_alert = 0
            for job in jobs:
                if attempted_for_alert >= settings.max_alert_deliveries_per_run:
                    break
                event_key = (alert.id, job.id)
                event_state = existing.get(event_key)
                if event_state is not None:
                    event_status, last_attempt_at = event_state
                    if event_status == "sent" or (
                        event_status == "pending"
                        and last_attempt_at is not None
                        and last_attempt_at >= datetime.now(UTC) - ALERT_DELIVERY_LEASE
                    ):
                        continue
                if not job_matches(alert, job):
                    continue
                attempted_at = datetime.now(UTC)
                event_id = await _claim_alert_delivery(
                    session,
                    alert=alert,
                    job=job,
                    attempted_at=attempted_at,
                )
                if event_id is None:
                    continue
                attempted_for_alert += 1
                existing[event_key] = ("pending", attempted_at)
                try:
                    await _deliver(alert, user, job)
                except Exception as exc:
                    error = f"delivery_failed:{type(exc).__name__}"
                    await _finish_alert_delivery(
                        session,
                        event_id=event_id,
                        alert=alert,
                        attempted_at=attempted_at,
                        error=error,
                    )
                    existing[event_key] = ("failed", attempted_at)
                    failed += 1
                else:
                    await _finish_alert_delivery(
                        session,
                        event_id=event_id,
                        alert=alert,
                        attempted_at=attempted_at,
                        error=None,
                    )
                    existing[event_key] = ("sent", attempted_at)
                    sent += 1
    return {
        "status": "partial" if failed else "completed",
        "alerts_checked": checked,
        "alerts_sent": sent,
        "deliveries_failed": failed,
        "errors": [f"deliveries_failed:{failed}"] if failed else [],
    }


@app.task(name="workers.alert_tasks.check_and_fire")
def check_and_fire() -> dict[str, Any]:
    return run_async(
        bounded_alert_evaluation(
            evaluate_alerts(),
            timeout_seconds=ALERT_EVALUATION_TIMEOUT_SECONDS,
        )
    )
