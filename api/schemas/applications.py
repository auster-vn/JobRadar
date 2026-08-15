import uuid
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from api.schemas.jobs import JobSummary

ApplicationStatus = Literal[
    "saved",
    "applied",
    "interviewing",
    "offer",
    "rejected",
    "withdrawn",
]
ApplicationNotes = Annotated[str, Field(max_length=4000)]


def _require_timezone(value: datetime | None) -> datetime | None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError("datetime must include a timezone")
    return value


class ApplicationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: uuid.UUID
    status: ApplicationStatus = "saved"
    notes: ApplicationNotes | None = None
    applied_at: datetime | None = None

    _validate_applied_at = field_validator("applied_at")(_require_timezone)


class ApplicationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ApplicationStatus | None = None
    notes: ApplicationNotes | None = None
    applied_at: datetime | None = None

    _validate_applied_at = field_validator("applied_at")(_require_timezone)

    @model_validator(mode="after")
    def require_update(self) -> Self:
        fields = self.model_fields_set
        if not fields:
            raise ValueError("at least one field must be provided")
        if "status" in fields and self.status is None:
            raise ValueError("status cannot be null")
        return self


class ApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    job_id: uuid.UUID
    status: ApplicationStatus
    notes: str | None
    applied_at: datetime | None
    created_at: datetime
    updated_at: datetime
    job: JobSummary


class ApplicationPagination(BaseModel):
    limit: int
    offset: int
    total_count: int
    has_more: bool


class ApplicationPage(BaseModel):
    data: list[ApplicationResponse]
    pagination: ApplicationPagination
