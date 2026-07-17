import logging
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError, model_validator

from api.core.config import get_settings
from api.schemas.salary import SalaryPredictionRequest

logger = logging.getLogger(__name__)


class PublishedSalaryPrediction(BaseModel):
    salary_estimate: int = Field(ge=0)
    salary_p25: int = Field(ge=0)
    salary_p75: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_interval(self) -> "PublishedSalaryPrediction":
        if self.salary_p25 > self.salary_p75:
            raise ValueError("salary_p25 must not exceed salary_p75")
        return self


async def request_published_salary_model(
    payload: SalaryPredictionRequest,
    client: httpx.AsyncClient | None = None,
) -> dict[str, int] | None:
    settings = get_settings()
    if not settings.salary_model_url:
        return None
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=settings.salary_model_timeout_seconds)
    try:
        response = await client.post(
            f"{settings.salary_model_url.rstrip('/')}/predict",
            json=payload.model_dump(),
        )
        if response.status_code == 503:
            return None
        response.raise_for_status()
        body: Any = response.json()
        prediction = PublishedSalaryPrediction.model_validate(body)
        return prediction.model_dump()
    except (httpx.HTTPError, TypeError, ValueError, ValidationError) as exc:
        logger.warning("published salary model unavailable: %s", exc)
        return None
    finally:
        if owns_client:
            await client.aclose()
