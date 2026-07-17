from datetime import date

from pydantic import BaseModel, Field


class SalaryPredictionRequest(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    level: str
    location: str
    experience_years: float = Field(ge=0, le=60)
    skills: list[str] = Field(default_factory=list, max_length=100)


class SalaryPredictionResponse(BaseModel):
    salary_estimate: int
    salary_p25: int
    salary_p75: int
    sample_size: int
    currency: str = "VND"
    source: str
    sources: list[str] = Field(default_factory=list)
    period_start: date | None = None
    period_end: date | None = None
