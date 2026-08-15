import uuid
from decimal import Decimal
from typing import cast

import pytest
from fastapi import HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.dml import Insert

from api.core.cache import CacheUnavailable
from api.core.cache import cache as score_cache
from api.core.config import Settings
from api.models import Job, JobScore, User, UserProfile
from api.services import scoring
from api.services.ai_providers import AIProviderError, ScoreInput, ScoreOutput
from api.services.scoring import (
    AIProviderScoringAdapter,
    ScoreComputation,
    ScoreInputs,
    ScoringBudgetExceeded,
    ScoringBudgetUnavailable,
    build_score_inputs,
    compute_deterministic_score,
    get_or_create_job_score,
    resolve_scoring_providers,
    score_input_hash,
    score_with_provider_fallback,
)


def _inputs(**overrides: object) -> ScoreInputs:
    values: dict[str, object] = {
        "job_title": "backend engineer",
        "required_skills": ("fastapi", "python"),
        "experience_years_min": 3,
        "job_locations": ("ho chi minh",),
        "current_title": "software engineer",
        "user_skills": ("python", "sql"),
        "user_experience_years": 4,
        "preferred_locations": ("ho chi minh",),
    }
    values.update(overrides)
    return ScoreInputs(**values)  # type: ignore[arg-type]


def test_deterministic_score_has_stable_component_arithmetic() -> None:
    result = compute_deterministic_score(_inputs())

    assert result.skill_score == Decimal("50.00")
    assert result.experience_score == Decimal("100.00")
    assert result.location_score == Decimal("100.00")
    assert result.overall_score == Decimal("67.50")
    assert result.matched_skills == ("python",)
    assert result.missing_skills == ("fastapi",)


def test_deterministic_score_uses_neutral_values_for_unknown_requirements() -> None:
    result = compute_deterministic_score(
        _inputs(
            required_skills=(),
            experience_years_min=None,
            job_locations=(),
            preferred_locations=(),
        )
    )

    assert result.skill_score == Decimal("50.00")
    assert result.experience_score == Decimal("50.00")
    assert result.location_score == Decimal("50.00")
    assert result.overall_score == Decimal("50.00")


def test_score_inputs_and_hash_are_case_order_and_unicode_stable() -> None:
    job_id = uuid.uuid4()
    job_a = Job(
        id=job_id,
        platform="test",
        platform_job_id="one",
        company_id=uuid.uuid4(),
        title=" Backend Engineer ",
        skills_required=[" PYTHON", "FastAPI", "Python"],
        location=["Hồ Chí Minh"],
        experience_years_min=2,
    )
    job_b = Job(
        id=job_id,
        platform="test",
        platform_job_id="one",
        company_id=job_a.company_id,
        title="backend engineer",
        skills_required=["fastapi", "python"],
        location=["HỒ CHÍ MINH"],
        experience_years_min=2,
    )
    profile_a = UserProfile(
        user_id=uuid.uuid4(),
        current_title=" Engineer ",
        experience_years=3,
        skills=["SQL", "Python", " sql "],
        preferred_locations=["Hồ Chí Minh"],
        preferred_job_types=[],
    )
    profile_b = UserProfile(
        user_id=profile_a.user_id,
        current_title="engineer",
        experience_years=3,
        skills=["python", "sql"],
        preferred_locations=["HỒ CHÍ MINH"],
        preferred_job_types=[],
    )

    inputs_a = build_score_inputs(job_a, profile_a)
    inputs_b = build_score_inputs(job_b, profile_b)

    assert inputs_a == inputs_b
    assert score_input_hash(inputs_a) == score_input_hash(inputs_b)
    assert score_input_hash(inputs_a) != score_input_hash(_inputs(user_experience_years=1))


class _NeverProvider:
    name = "deterministic"
    model_version = "jobradar-deterministic-v1"
    calls = 0

    async def score(self, inputs: ScoreInputs) -> ScoreComputation:
        self.calls += 1
        raise AssertionError(f"provider should not run for cached input: {inputs}")


class _CachedSession:
    def __init__(self, score: JobScore) -> None:
        self.score = score
        self.execute_calls = 0

    async def execute(self, statement: object, parameters: object = None) -> None:
        self.execute_calls += 1

    async def scalar(self, statement: object) -> JobScore:
        return self.score


@pytest.mark.asyncio
async def test_persisted_input_hash_skips_provider_execution() -> None:
    user_id = uuid.uuid4()
    job = Job(
        id=uuid.uuid4(),
        platform="test",
        platform_job_id="cached",
        company_id=uuid.uuid4(),
        title="Backend Engineer",
        skills_required=["Python"],
        location=[],
    )
    profile = UserProfile(
        user_id=user_id,
        skills=["Python"],
        preferred_locations=[],
        preferred_job_types=[],
    )
    cached_score = JobScore(
        id=uuid.uuid4(),
        user_id=user_id,
        job_id=job.id,
        provider="deterministic",
        model_version="jobradar-deterministic-v1",
        input_hash="a" * 64,
        overall_score=Decimal("82.50"),
        skill_score=Decimal("100"),
        experience_score=Decimal("50"),
        location_score=Decimal("50"),
        matched_skills=["python"],
        missing_skills=[],
        summary="cached",
    )
    fake_session = _CachedSession(cached_score)
    provider = _NeverProvider()

    result, cache_hit = await get_or_create_job_score(
        cast(AsyncSession, fake_session),
        user_id=user_id,
        job=job,
        profile=profile,
        provider=provider,
    )

    assert result is cached_score
    assert cache_hit is True
    assert provider.calls == 0
    assert fake_session.execute_calls == 1


def test_configured_ai_provider_chain_registers_all_supported_backends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        _env_file=None,
        ai_provider="openai",
        ai_fallback_providers=["deepseek", "openrouter", "gemini", "ollama"],
        openai_api_key="test-openai-key",
        deepseek_api_key="test-deepseek-key",
        openrouter_api_key="test-openrouter-key",
        gemini_api_key="test-gemini-key",
    )
    monkeypatch.setattr(scoring, "get_settings", lambda: settings)

    providers = resolve_scoring_providers()

    assert [provider.name for provider in providers] == [
        "openai",
        "deepseek",
        "openrouter",
        "gemini",
        "ollama",
        "deterministic",
    ]


class _FakeAIBackend:
    def __init__(self, name: str, model: str, *, fails: bool = False) -> None:
        self.name = name
        self.model = model
        self.fails = fails
        self.calls = 0

    async def score(self, score_input: ScoreInput) -> ScoreOutput:
        self.calls += 1
        if self.fails:
            raise AIProviderError(f"{self.name} unavailable")
        return ScoreOutput(
            overall_score=84,
            skill_score=80,
            experience_score=90,
            location_score=70,
            salary_score=75,
            strengths=["Strong fit"],
            gaps=["One gap"],
            explanation=f"Scored by {self.name}.",
        )


@pytest.mark.asyncio
async def test_runtime_fallback_attributes_the_provider_and_model_actually_used() -> None:
    primary = _FakeAIBackend("openai", "primary-model", fails=True)
    fallback = _FakeAIBackend("gemini", "fallback-model")

    execution = await score_with_provider_fallback(
        _inputs(),
        [AIProviderScoringAdapter(primary), AIProviderScoringAdapter(fallback)],
    )

    assert execution.provider.name == "gemini"
    assert execution.provider.model_version == "fallback-model"
    assert execution.result.overall_score == Decimal("84.00")
    assert execution.result.matched_skills == ("python",)
    assert execution.result.missing_skills == ("fastapi",)
    assert primary.calls == 1
    assert fallback.calls == 1


class _TemporaryCache:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}
        self.read_keys: list[str] = []

    async def get_json(self, key: str) -> object | None:
        self.read_keys.append(key)
        return self.values.get(key)

    async def set_json(self, key: str, value: object, ttl_seconds: int) -> None:
        self.values[key] = value

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)


class _PersistingSession:
    def __init__(self, persisted: JobScore) -> None:
        self.persisted = persisted
        self.scalar_calls = 0
        self.insert_params: dict[str, object] = {}
        self.added: list[object] = []

    async def execute(self, statement: object, parameters: object = None) -> None:
        return None

    async def scalar(self, statement: object) -> JobScore | None:
        self.scalar_calls += 1
        if isinstance(statement, Insert):
            self.insert_params = dict(statement.compile().params)
            return self.persisted
        return None

    def add(self, value: object) -> None:
        self.added.append(value)

    async def commit(self) -> None:
        return None


class _CountingProvider:
    name = "gemini"
    model_version = "gemini-test-model"

    def __init__(self) -> None:
        self.calls = 0

    async def score(self, inputs: ScoreInputs) -> ScoreComputation:
        self.calls += 1
        return compute_deterministic_score(inputs)


@pytest.mark.asyncio
async def test_tenant_temporary_cache_hit_skips_provider_and_persists_attribution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    temporary_cache = _TemporaryCache()
    monkeypatch.setattr(score_cache, "get_json", temporary_cache.get_json)
    monkeypatch.setattr(score_cache, "set_json", temporary_cache.set_json)
    monkeypatch.setattr(score_cache, "delete", temporary_cache.delete)

    async def unexpected_increment(key: str, ttl_seconds: int) -> int:
        raise AssertionError(f"budget must not be consumed for cache hit: {key} {ttl_seconds}")

    monkeypatch.setattr(score_cache, "increment", unexpected_increment)
    user_id = uuid.uuid4()
    job = Job(
        id=uuid.uuid4(),
        platform="test",
        platform_job_id="temporary-cache",
        company_id=uuid.uuid4(),
        title="Backend Engineer",
        skills_required=["Python"],
        location=[],
    )
    profile = UserProfile(
        user_id=user_id,
        skills=["Python"],
        preferred_locations=[],
        preferred_job_types=[],
    )
    provider = _CountingProvider()
    inputs = build_score_inputs(job, profile)
    input_hash = score_input_hash(inputs, provider.name, provider.model_version)
    cached_result = compute_deterministic_score(inputs)
    await scoring._store_temporary_result(
        user_id=user_id,
        input_hash=input_hash,
        provider=provider.name,
        model_version=provider.model_version,
        result=cached_result,
    )
    persisted = JobScore(
        id=uuid.uuid4(),
        user_id=user_id,
        job_id=job.id,
        provider=provider.name,
        model_version=provider.model_version,
        input_hash=input_hash,
        overall_score=cached_result.overall_score,
        skill_score=cached_result.skill_score,
        experience_score=cached_result.experience_score,
        location_score=cached_result.location_score,
        matched_skills=list(cached_result.matched_skills),
        missing_skills=list(cached_result.missing_skills),
        summary=cached_result.summary,
    )
    session = _PersistingSession(persisted)

    result, cache_hit = await get_or_create_job_score(
        cast(AsyncSession, session),
        user_id=user_id,
        job=job,
        profile=profile,
        provider=provider,
    )

    assert result is persisted
    assert cache_hit is True
    assert provider.calls == 0
    assert session.insert_params["provider"] == "gemini"
    assert session.insert_params["model_version"] == "gemini-test-model"
    assert all(str(user_id) in key for key in temporary_cache.read_keys)

    foreign_user = uuid.uuid4()
    foreign_key = scoring._temporary_cache_key(foreign_user, input_hash)
    temporary_cache.values[foreign_key] = next(iter(temporary_cache.values.values()))
    assert (
        await scoring._load_temporary_result(
            user_id=foreign_user,
            input_hash=input_hash,
            provider=provider.name,
            model_version=provider.model_version,
            inputs=inputs,
        )
        is None
    )
    assert foreign_key not in temporary_cache.values


class _BudgetSession:
    def __init__(self, limit: int | None) -> None:
        self.limit = limit

    async def scalar(self, statement: object) -> int | None:
        return self.limit


@pytest.mark.asyncio
async def test_daily_remote_ai_budget_raises_typed_exception_before_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_keys: list[str] = []

    async def exhausted_increment(key: str, ttl_seconds: int) -> int:
        seen_keys.append(key)
        assert ttl_seconds > 0
        return 21

    monkeypatch.setattr(score_cache, "increment", exhausted_increment)
    user_id = uuid.uuid4()

    with pytest.raises(ScoringBudgetExceeded) as exc_info:
        await scoring._consume_remote_ai_budget(
            cast(AsyncSession, _BudgetSession(20)),
            user_id=user_id,
        )

    assert exc_info.value.limit == 20
    assert str(user_id) in seen_keys[0]


@pytest.mark.asyncio
async def test_production_remote_ai_fails_closed_when_budget_cache_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unavailable_increment(key: str, ttl_seconds: int) -> int:
        raise CacheUnavailable(f"offline: {key} {ttl_seconds}")

    settings = Settings(
        _env_file=None,
        app_env="production",
        jwt_secret_key="j" * 32,
        admin_api_key="a" * 24,
        cv_encryption_key="c" * 32,
        cron_secret="s" * 32,
    )
    monkeypatch.setattr(scoring, "get_settings", lambda: settings)
    monkeypatch.setattr(score_cache, "increment", unavailable_increment)

    with pytest.raises(ScoringBudgetUnavailable):
        await scoring._consume_remote_ai_budget(
            cast(AsyncSession, _BudgetSession(None)),
            user_id=uuid.uuid4(),
        )


class _ScoringRouterSession:
    def __init__(self, job: Job, profile: UserProfile) -> None:
        self.results: list[object] = [job, profile]

    async def scalar(self, statement: object) -> object:
        return self.results.pop(0)

    async def execute(self, statement: object, parameters: object = None) -> None:
        return None


@pytest.mark.asyncio
async def test_scoring_router_maps_budget_exhaustion_to_429(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from api.routers import scoring as scoring_router

    user = User(id=uuid.uuid4(), email="person@example.com", is_active=True)
    job = Job(
        id=uuid.uuid4(),
        platform="test",
        platform_job_id="budget",
        company_id=uuid.uuid4(),
        title="Backend Engineer",
        skills_required=[],
        location=[],
        is_active=True,
    )
    profile = UserProfile(
        user_id=user.id,
        skills=[],
        preferred_locations=[],
        preferred_job_types=[],
    )

    async def exhausted(*args: object, **kwargs: object) -> tuple[JobScore, bool]:
        raise ScoringBudgetExceeded(20, 120)

    monkeypatch.setattr(scoring_router, "get_or_create_job_score", exhausted)

    with pytest.raises(HTTPException) as exc_info:
        await scoring_router.score_job(
            job.id,
            Response(),
            user,
            cast(AsyncSession, _ScoringRouterSession(job, profile)),
        )

    assert exc_info.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert exc_info.value.headers == {"Retry-After": "120"}
