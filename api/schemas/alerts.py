import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AlertCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=120)
    required_skills: list[str] = Field(default_factory=list, max_length=50)
    min_salary: Decimal | None = Field(default=None, ge=0)
    job_levels: list[str] = Field(default_factory=list, max_length=8)
    locations: list[str] = Field(default_factory=list, max_length=20)
    skill_match_min_pct: Decimal = Field(default=Decimal("60"), ge=0, le=100)
    channel: str = Field(default="email", pattern="^(email|telegram)$")
    is_active: bool = True

    @model_validator(mode="after")
    def require_filter(self) -> "AlertCreate":
        if not any(
            (
                self.required_skills,
                self.min_salary is not None,
                self.job_levels,
                self.locations,
            )
        ):
            raise ValueError("At least one alert criterion is required")
        return self


class AlertUpdate(AlertCreate):
    pass


class AlertResponse(AlertCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    last_triggered_at: datetime | None
    created_at: datetime


class AlertEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    alert_id: uuid.UUID
    job_id: uuid.UUID
    channel: str
    status: str
    error: str | None
    sent_at: datetime | None
    created_at: datetime
