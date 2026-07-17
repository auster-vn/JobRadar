import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class CompanySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    logo_url: str | None = None
    company_type: str | None = None


class JobSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    title_normalized: str | None
    company: CompanySummary
    platform: str
    source_url: str | None
    job_level: str | None
    job_type: str | None
    location: list[str]
    salary_min: Decimal | None
    salary_max: Decimal | None
    salary_currency: str
    salary_negotiable: bool
    skills_required: list[str]
    posted_at: datetime | None


class JobDetail(JobSummary):
    description: str | None = Field(validation_alias="description_cleaned")
    skills_nice_to_have: list[str]
    experience_years_min: int | None
    experience_years_max: int | None


class Pagination(BaseModel):
    limit: int
    next_cursor: str | None
    has_more: bool
    total_count: int


class JobPage(BaseModel):
    data: list[JobSummary]
    pagination: Pagination


class SalaryBand(BaseModel):
    title: str
    level: str | None
    location: str | None
    sample_size: int
    p25: int
    median: int
    p75: int
    currency: str = "VND"
    sources: list[str] = Field(default_factory=list)
    period_start: date | None = None
    period_end: date | None = None


class SkillDemand(BaseModel):
    skill: str
    job_count: int
    demand_rank: int
    mom_growth_pct: float | None
