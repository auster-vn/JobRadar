import httpx
import pytest

from api.core.config import get_settings
from api.schemas.salary import SalaryPredictionRequest
from api.services.salary_model import request_published_salary_model


def _request() -> SalaryPredictionRequest:
    return SalaryPredictionRequest(
        title="Backend Developer",
        level="senior",
        location="Ha Noi",
        experience_years=5,
        skills=["Python"],
    )


@pytest.mark.parametrize("status_code", [503, 500])
async def test_salary_model_client_falls_back_on_service_failure(
    monkeypatch: pytest.MonkeyPatch, status_code: int
) -> None:
    monkeypatch.setenv("SALARY_MODEL_URL", "http://salary-model")
    get_settings.cache_clear()
    transport = httpx.MockTransport(lambda _: httpx.Response(status_code))
    async with httpx.AsyncClient(transport=transport) as client:
        assert await request_published_salary_model(_request(), client) is None
    get_settings.cache_clear()


async def test_salary_model_client_returns_valid_prediction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SALARY_MODEL_URL", "http://salary-model")
    get_settings.cache_clear()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "http://salary-model/predict"
        return httpx.Response(
            200,
            json={
                "salary_estimate": 40_000_000,
                "salary_p25": 32_000_000,
                "salary_p75": 50_000_000,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await request_published_salary_model(_request(), client)
    get_settings.cache_clear()

    assert result == {
        "salary_estimate": 40_000_000,
        "salary_p25": 32_000_000,
        "salary_p75": 50_000_000,
    }


@pytest.mark.parametrize(
    "body",
    [
        {"salary_estimate": -1, "salary_p25": 1, "salary_p75": 2},
        {"salary_estimate": 10, "salary_p25": 20, "salary_p75": 5},
        {"salary_estimate": 10, "salary_p25": 5},
    ],
)
async def test_salary_model_client_rejects_malformed_prediction(
    monkeypatch: pytest.MonkeyPatch, body: dict[str, int]
) -> None:
    monkeypatch.setenv("SALARY_MODEL_URL", "http://salary-model")
    get_settings.cache_clear()
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=body))
    async with httpx.AsyncClient(transport=transport) as client:
        assert await request_published_salary_model(_request(), client) is None
    get_settings.cache_clear()
