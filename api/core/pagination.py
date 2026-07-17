import base64
import json
import uuid
from dataclasses import dataclass
from datetime import datetime

from fastapi import HTTPException, status


@dataclass(frozen=True, slots=True)
class JobCursor:
    posted_at: datetime
    job_id: uuid.UUID


def encode_cursor(posted_at: datetime, job_id: uuid.UUID) -> str:
    payload = json.dumps(
        {"posted_at": posted_at.isoformat(), "id": str(job_id)}, separators=(",", ":")
    )
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def decode_cursor(value: str) -> JobCursor:
    try:
        padded = value + "=" * (-len(value) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
        return JobCursor(datetime.fromisoformat(payload["posted_at"]), uuid.UUID(payload["id"]))
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid pagination cursor") from exc
