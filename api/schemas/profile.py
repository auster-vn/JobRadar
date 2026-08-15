import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.jobs import JobSummary


class ProfileUpdate(BaseModel):
    current_title: str | None = Field(default=None, max_length=300)
    experience_years: int | None = Field(default=None, ge=0, le=60)
    skills: list[str] = Field(default_factory=list, max_length=100)
    current_salary: Decimal | None = Field(default=None, ge=0)
    target_salary: Decimal | None = Field(default=None, ge=0)
    preferred_locations: list[str] = Field(default_factory=list, max_length=20)
    preferred_job_types: list[str] = Field(default_factory=list, max_length=10)


class ProfileResponse(ProfileUpdate):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    has_cv: bool


class SkillGapResponse(BaseModel):
    target_title: str
    target_level: str
    current_skills: list[str]
    missing_skills: list[str]
    coverage_pct: float


class MatchedJob(BaseModel):
    job: JobSummary
    skill_match_pct: float
    semantic_match_pct: float | None = None
    match_score: float
    matched_skills: list[str]
