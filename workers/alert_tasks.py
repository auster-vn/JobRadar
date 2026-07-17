import asyncio
import smtplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Any

import httpx
from sqlalchemy import select

from api.core.config import get_settings
from api.core.database import session_factory
from api.models import AlertEvent, Job, JobAlert, User
from workers.async_runner import run_async
from workers.celery_app import app


def job_matches(alert: JobAlert, job: Job) -> bool:
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


async def evaluate_alerts() -> dict[str, Any]:
    checked = sent = failed = 0
    cutoff = datetime.now(UTC) - timedelta(days=2)
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
        existing = set(
            (
                await session.execute(
                    select(AlertEvent.alert_id, AlertEvent.job_id).where(
                        AlertEvent.alert_id.in_([alert.id for alert, _ in alerts])
                    )
                )
            ).all()
        )
        for alert, user in alerts:
            checked += 1
            for job in jobs:
                if (alert.id, job.id) in existing or not job_matches(alert, job):
                    continue
                event = AlertEvent(
                    alert_id=alert.id,
                    job_id=job.id,
                    channel=alert.channel,
                    status="pending",
                )
                session.add(event)
                try:
                    await _deliver(alert, user, job)
                    event.status = "sent"
                    event.sent_at = datetime.now(UTC)
                    alert.last_triggered_at = event.sent_at
                    sent += 1
                except Exception as exc:
                    event.status = "failed"
                    event.error = str(exc)[:1000]
                    failed += 1
                await session.commit()
    return {
        "status": "completed",
        "alerts_checked": checked,
        "alerts_sent": sent,
        "deliveries_failed": failed,
    }


@app.task(name="workers.alert_tasks.check_and_fire")
def check_and_fire() -> dict[str, Any]:
    return run_async(evaluate_alerts())
