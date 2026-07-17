from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator

JobLevel = Literal["intern", "fresher", "junior", "mid", "senior", "lead", "manager", "director"]


class RawJobValidator(BaseModel):
    platform: Literal["itviec", "topcv", "vietnamworks", "linkedin"]
    platform_job_id: str = Field(min_length=1, max_length=200)
    source_url: HttpUrl
    title: str = Field(min_length=3, max_length=300)
    company_name: str = Field(min_length=1, max_length=300)
    company_logo_url: HttpUrl | None = None
    description: str | None = None
    salary_text: str | None = None
    location: list[str] = Field(default_factory=list)
    job_type: str | None = None
    job_level: JobLevel | None = None
    skills: list[str] = Field(default_factory=list)
    posted_at: datetime
    expires_at: datetime | None = None
    experience_years_min: int | None = Field(default=None, ge=0, le=60)
    experience_years_max: int | None = Field(default=None, ge=0, le=60)
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_dates_and_description(self) -> "RawJobValidator":
        now = datetime.now(UTC)
        posted = self.posted_at
        if posted.tzinfo is None:
            posted = posted.replace(tzinfo=UTC)
        if posted > now + timedelta(hours=1):
            raise ValueError("posted_at cannot be in the future")
        if self.description is not None and len(self.description.strip()) < 20:
            self.description = None
        return self
