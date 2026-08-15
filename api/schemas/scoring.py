import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class JobScoreResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    job_id: uuid.UUID
    overall_score: float = Field(ge=0, le=100)
    skill_score: float = Field(ge=0, le=100)
    experience_score: float = Field(ge=0, le=100)
    location_score: float = Field(ge=0, le=100)
    matched_skills: list[str]
    missing_skills: list[str]
    summary: str
    provider: str
    model_version: str
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    cached: bool = False
    created_at: datetime
    updated_at: datetime
