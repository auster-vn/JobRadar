import hashlib
import json
import logging
import unicodedata
import uuid
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from api.core.cache import CacheUnavailable, cache
from api.core.config import get_settings
from api.models import AuditLog, Job, JobScore, UserProfile, UserSettings
from api.services.ai_providers import (
    PROMPT_VERSION,
    AIProvider,
    AIProviderError,
    ScoreInput,
    ScoreOutput,
    provider_for,
)
from api.services.profile_security import set_profile_owner

SCORE_QUANTUM = Decimal("0.01")
SCORER_VERSION = "jobradar-deterministic-v1"
DEFAULT_DAILY_REMOTE_AI_BUDGET = 20
MAX_DAILY_REMOTE_AI_BUDGET = 20
logger = logging.getLogger(__name__)


class ScoringBudgetExceeded(RuntimeError):
    def __init__(self, limit: int, retry_after_seconds: int) -> None:
        self.limit = limit
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"Daily AI scoring budget of {limit} calls has been exhausted")


class ScoringBudgetUnavailable(RuntimeError):
    """Raised when production cannot safely enforce the remote-AI budget."""


@dataclass(frozen=True, slots=True)
class ScoreInputs:
    """Sanitized, canonical scoring inputs safe to pass to a provider."""

    job_title: str
    required_skills: tuple[str, ...]
    experience_years_min: int | None
    job_locations: tuple[str, ...]
    current_title: str | None
    user_skills: tuple[str, ...]
    user_experience_years: int | None
    preferred_locations: tuple[str, ...]
    job_description: str = ""
    salary_min: str | None = None
    salary_max: str | None = None
    target_salary: str | None = None


@dataclass(frozen=True, slots=True)
class ScoreComputation:
    overall_score: Decimal
    skill_score: Decimal
    experience_score: Decimal
    location_score: Decimal
    matched_skills: tuple[str, ...]
    missing_skills: tuple[str, ...]
    summary: str


@dataclass(frozen=True, slots=True)
class ProviderExecution:
    result: ScoreComputation
    provider: "ScoringProvider"


class ScoringProvider(Protocol):
    """Extension point for a server-selected scoring implementation."""

    @property
    def name(self) -> str: ...

    @property
    def model_version(self) -> str: ...

    async def score(self, inputs: ScoreInputs) -> ScoreComputation: ...


def _canonical_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(normalized.split()).casefold()


def _canonical_items(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({item for value in values if (item := _canonical_text(value))}))


def _canonical_description(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(unicodedata.normalize("NFKC", value).split())[:8_000]


def _canonical_decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value.normalize(), "f")


def _bounded_years(value: int | None) -> int | None:
    if value is None:
        return None
    return max(0, min(80, value))


def build_score_inputs(job: Job, profile: UserProfile) -> ScoreInputs:
    return ScoreInputs(
        job_title=_canonical_text(job.title),
        required_skills=_canonical_items(job.skills_required or ())[:100],
        experience_years_min=_bounded_years(job.experience_years_min),
        job_locations=_canonical_items(job.location or ())[:20],
        current_title=_canonical_text(profile.current_title) if profile.current_title else None,
        user_skills=_canonical_items(profile.skills or ())[:100],
        user_experience_years=_bounded_years(profile.experience_years),
        preferred_locations=_canonical_items(profile.preferred_locations or ())[:20],
        job_description=_canonical_description(job.description_cleaned or job.description_raw),
        salary_min=_canonical_decimal(job.salary_min),
        salary_max=_canonical_decimal(job.salary_max),
        target_salary=_canonical_decimal(profile.target_salary),
    )


def score_input_hash(
    inputs: ScoreInputs,
    provider: str = "deterministic",
    model_version: str = SCORER_VERSION,
) -> str:
    payload = {
        "input_schema": 1,
        "scorer_version": SCORER_VERSION,
        "prompt_version": PROMPT_VERSION if provider != "deterministic" else None,
        "provider": provider,
        "model_version": model_version,
        "inputs": asdict(inputs),
    }
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(serialized).hexdigest()


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(SCORE_QUANTUM, rounding=ROUND_HALF_UP)


def compute_deterministic_score(inputs: ScoreInputs) -> ScoreComputation:
    required = set(inputs.required_skills)
    available = set(inputs.user_skills)
    matched = tuple(sorted(required & available))
    missing = tuple(sorted(required - available))
    skill_score = (
        Decimal(len(matched) * 100) / Decimal(len(required)) if required else Decimal("50")
    )

    required_years = inputs.experience_years_min
    actual_years = inputs.user_experience_years
    if required_years is None or actual_years is None:
        experience_score = Decimal("50")
    elif actual_years >= required_years:
        experience_score = Decimal("100")
    else:
        experience_score = max(
            Decimal("0"),
            Decimal("100") - Decimal(required_years - actual_years) * Decimal("25"),
        )

    job_locations = set(inputs.job_locations)
    preferred_locations = set(inputs.preferred_locations)
    if not job_locations or not preferred_locations:
        location_score = Decimal("50")
    elif job_locations & preferred_locations:
        location_score = Decimal("100")
    else:
        location_score = Decimal("0")

    overall_score = (
        skill_score * Decimal("0.65")
        + experience_score * Decimal("0.20")
        + location_score * Decimal("0.15")
    )
    summary = (
        f"Matched {len(matched)} of {len(required)} required skills; "
        f"experience {int(experience_score)}%; location {int(location_score)}%."
    )
    return ScoreComputation(
        overall_score=_quantize(overall_score),
        skill_score=_quantize(skill_score),
        experience_score=_quantize(experience_score),
        location_score=_quantize(location_score),
        matched_skills=matched,
        missing_skills=missing,
        summary=summary,
    )


@dataclass(frozen=True, slots=True)
class DeterministicScoringProvider:
    name: str = "deterministic"
    model_version: str = SCORER_VERSION

    async def score(self, inputs: ScoreInputs) -> ScoreComputation:
        return compute_deterministic_score(inputs)


def _to_ai_score_input(inputs: ScoreInputs) -> ScoreInput:
    return ScoreInput(
        job_title=inputs.job_title,
        job_description=inputs.job_description,
        required_skills=list(inputs.required_skills),
        job_locations=list(inputs.job_locations),
        experience_years_min=inputs.experience_years_min,
        salary_min=float(inputs.salary_min) if inputs.salary_min is not None else None,
        salary_max=float(inputs.salary_max) if inputs.salary_max is not None else None,
        profile_title=inputs.current_title,
        profile_skills=list(inputs.user_skills),
        profile_locations=list(inputs.preferred_locations),
        profile_experience_years=inputs.user_experience_years,
        profile_target_salary=(
            float(inputs.target_salary) if inputs.target_salary is not None else None
        ),
    )


def _from_ai_score_output(output: ScoreOutput, inputs: ScoreInputs) -> ScoreComputation:
    required = set(inputs.required_skills)
    available = set(inputs.user_skills)
    return ScoreComputation(
        overall_score=Decimal(str(output.overall_score)),
        skill_score=Decimal(str(output.skill_score)),
        experience_score=Decimal(str(output.experience_score)),
        location_score=Decimal(str(output.location_score)),
        matched_skills=tuple(sorted(required & available)),
        missing_skills=tuple(sorted(required - available)),
        summary=output.explanation,
    )


@dataclass(frozen=True, slots=True)
class AIProviderScoringAdapter:
    backend: AIProvider

    @property
    def name(self) -> str:
        return self.backend.name

    @property
    def model_version(self) -> str:
        return self.backend.model

    async def score(self, inputs: ScoreInputs) -> ScoreComputation:
        output = await self.backend.score(_to_ai_score_input(inputs))
        return _from_ai_score_output(output, inputs)


_PROVIDERS: dict[str, ScoringProvider] = {
    "deterministic": DeterministicScoringProvider(),
}


def _provider_identity(provider: ScoringProvider) -> tuple[str, str]:
    name = provider.name.strip().casefold()
    model_version = provider.model_version.strip()
    if not name or len(name) > 32:
        raise ValueError("provider name must contain 1 to 32 characters")
    if not model_version or len(model_version) > 128:
        raise ValueError("provider model version must contain 1 to 128 characters")
    return name, model_version


def register_scoring_provider(provider: ScoringProvider, *, replace: bool = False) -> None:
    """Register a provider; callers must opt in before replacing an existing name."""

    name, _ = _provider_identity(provider)
    if name in _PROVIDERS and not replace:
        raise ValueError(f"scoring provider already registered: {name}")
    _PROVIDERS[name] = provider


def resolve_scoring_providers() -> tuple[ScoringProvider, ...]:
    settings = get_settings()
    candidates = [settings.ai_provider, *settings.ai_fallback_providers, "deterministic"]
    resolved: list[ScoringProvider] = []
    attempted: set[str] = set()
    for name in candidates:
        normalized = name.strip().casefold()
        if not normalized or normalized in attempted:
            continue
        attempted.add(normalized)
        provider = _PROVIDERS.get(normalized)
        if provider is None:
            if normalized not in {"deterministic", "ollama"} and not settings.ai_api_key(
                normalized
            ):
                continue
            try:
                provider = AIProviderScoringAdapter(provider_for(normalized, settings))
            except AIProviderError:
                continue
        try:
            _provider_identity(provider)
        except ValueError:
            continue
        resolved.append(provider)
    if not any(_provider_identity(provider)[0] == "deterministic" for provider in resolved):
        resolved.append(_PROVIDERS["deterministic"])
    return tuple(resolved)


def resolve_scoring_provider() -> ScoringProvider:
    return resolve_scoring_providers()[0]


def _validated_result(result: ScoreComputation) -> ScoreComputation:
    scores = (
        result.overall_score,
        result.skill_score,
        result.experience_score,
        result.location_score,
    )
    if any(not score.is_finite() or score < 0 or score > 100 for score in scores):
        raise ValueError("scoring provider returned a score outside the 0-100 range")
    summary = " ".join(result.summary.split())
    if not summary or len(summary) > 2000:
        raise ValueError("scoring provider returned an invalid summary")
    return ScoreComputation(
        overall_score=_quantize(result.overall_score),
        skill_score=_quantize(result.skill_score),
        experience_score=_quantize(result.experience_score),
        location_score=_quantize(result.location_score),
        matched_skills=_canonical_items(result.matched_skills),
        missing_skills=_canonical_items(result.missing_skills),
        summary=summary,
    )


async def score_with_provider_fallback(
    inputs: ScoreInputs,
    providers: Iterable[ScoringProvider],
    before_score: Callable[[ScoringProvider], Awaitable[None]] | None = None,
) -> ProviderExecution:
    for provider in providers:
        try:
            _provider_identity(provider)
            if before_score is not None:
                await before_score(provider)
            result = _validated_result(await provider.score(inputs))
        except (AIProviderError, ArithmeticError, TypeError, ValueError):
            continue
        return ProviderExecution(result=result, provider=provider)
    raise AIProviderError("No scoring provider succeeded")


def _budget_window() -> tuple[str, int]:
    now = datetime.now(UTC)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return now.date().isoformat(), max(1, int((tomorrow - now).total_seconds()))


async def _consume_remote_ai_budget(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
) -> None:
    configured_limit = await session.scalar(
        select(UserSettings.daily_score_budget).where(UserSettings.user_id == user_id)
    )
    limit = min(
        MAX_DAILY_REMOTE_AI_BUDGET,
        max(
            0,
            configured_limit if configured_limit is not None else DEFAULT_DAILY_REMOTE_AI_BUDGET,
        ),
    )
    day, ttl_seconds = _budget_window()
    if limit == 0:
        raise ScoringBudgetExceeded(limit, ttl_seconds)
    try:
        used = await cache.increment(f"ai-score-budget:v1:{user_id}:{day}", ttl_seconds)
    except CacheUnavailable as exc:
        if get_settings().app_env == "production":
            raise ScoringBudgetUnavailable(
                "Remote AI scoring is unavailable while budget enforcement is offline"
            ) from exc
        logger.warning("AI budget cache unavailable; allowing non-production request")
        return
    if used > limit:
        raise ScoringBudgetExceeded(limit, ttl_seconds)


class _CachedProviderResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1]
    user_id: str
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider: str = Field(min_length=1, max_length=32)
    model_version: str = Field(min_length=1, max_length=128)
    overall_score: str
    skill_score: str
    experience_score: str
    location_score: str
    matched_skills: list[str] = Field(max_length=100)
    missing_skills: list[str] = Field(max_length=100)
    summary: str = Field(min_length=1, max_length=2000)


def _temporary_cache_key(user_id: uuid.UUID, input_hash: str) -> str:
    return f"job-score:v1:{user_id}:{input_hash}"


async def _load_temporary_result(
    *,
    user_id: uuid.UUID,
    input_hash: str,
    provider: str,
    model_version: str,
    inputs: ScoreInputs,
) -> ScoreComputation | None:
    key = _temporary_cache_key(user_id, input_hash)
    try:
        payload = await cache.get_json(key)
    except CacheUnavailable:
        logger.debug("Temporary score cache unavailable", exc_info=True)
        return None
    if payload is None:
        return None
    try:
        cached = _CachedProviderResult.model_validate(payload)
        if (
            cached.user_id != str(user_id)
            or cached.input_hash != input_hash
            or cached.provider != provider
            or cached.model_version != model_version
        ):
            raise ValueError("temporary score cache attribution mismatch")
        required = set(inputs.required_skills)
        available = set(inputs.user_skills)
        result = _validated_result(
            ScoreComputation(
                overall_score=Decimal(cached.overall_score),
                skill_score=Decimal(cached.skill_score),
                experience_score=Decimal(cached.experience_score),
                location_score=Decimal(cached.location_score),
                matched_skills=tuple(cached.matched_skills),
                missing_skills=tuple(cached.missing_skills),
                summary=cached.summary,
            )
        )
        if result.matched_skills != tuple(sorted(required & available)) or (
            result.missing_skills != tuple(sorted(required - available))
        ):
            raise ValueError("temporary score cache skill attribution mismatch")
        return result
    except (ArithmeticError, TypeError, ValidationError, ValueError):
        logger.warning("Discarding invalid temporary score cache entry")
        try:
            await cache.delete(key)
        except CacheUnavailable:
            logger.debug("Temporary score cache unavailable during eviction", exc_info=True)
        return None


async def _store_temporary_result(
    *,
    user_id: uuid.UUID,
    input_hash: str,
    provider: str,
    model_version: str,
    result: ScoreComputation,
) -> None:
    payload = _CachedProviderResult(
        schema_version=1,
        user_id=str(user_id),
        input_hash=input_hash,
        provider=provider,
        model_version=model_version,
        overall_score=str(result.overall_score),
        skill_score=str(result.skill_score),
        experience_score=str(result.experience_score),
        location_score=str(result.location_score),
        matched_skills=list(result.matched_skills),
        missing_skills=list(result.missing_skills),
        summary=result.summary,
    )
    try:
        await cache.set_json(
            _temporary_cache_key(user_id, input_hash),
            payload.model_dump(mode="json"),
            get_settings().cache_ttl_seconds,
        )
    except CacheUnavailable:
        logger.debug("Temporary score cache unavailable", exc_info=True)


def _score_lookup(
    *,
    user_id: uuid.UUID,
    job_id: uuid.UUID,
    provider: str,
    model_version: str,
    input_hash: str,
) -> Select[tuple[JobScore]]:
    return select(JobScore).where(
        JobScore.user_id == user_id,
        JobScore.job_id == job_id,
        JobScore.provider == provider,
        JobScore.model_version == model_version,
        JobScore.input_hash == input_hash,
    )


async def get_or_create_job_score(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    job: Job,
    profile: UserProfile,
    provider: ScoringProvider | None = None,
) -> tuple[JobScore, bool]:
    """Return a tenant-owned persisted score and whether it was a cache hit."""

    inputs = build_score_inputs(job, profile)
    providers = (provider,) if provider is not None else resolve_scoring_providers()
    identities = [(*_provider_identity(candidate), candidate) for candidate in providers]
    await set_profile_owner(session, user_id)
    temporary_execution: ProviderExecution | None = None
    input_hash = ""
    lookup: Select[tuple[JobScore]] | None = None
    for provider_name, model_version, candidate in identities:
        candidate_hash = score_input_hash(
            inputs,
            provider=provider_name,
            model_version=model_version,
        )
        candidate_lookup = _score_lookup(
            user_id=user_id,
            job_id=job.id,
            provider=provider_name,
            model_version=model_version,
            input_hash=candidate_hash,
        )
        cached = await session.scalar(candidate_lookup)
        if cached is not None:
            return cached, True
        temporary = None
        if provider_name != "deterministic":
            temporary = await _load_temporary_result(
                user_id=user_id,
                input_hash=candidate_hash,
                provider=provider_name,
                model_version=model_version,
                inputs=inputs,
            )
        if temporary is not None:
            temporary_execution = ProviderExecution(result=temporary, provider=candidate)
            input_hash = candidate_hash
            lookup = candidate_lookup
            break

    temporary_hit = temporary_execution is not None
    if temporary_execution is None:

        async def enforce_budget(candidate: ScoringProvider) -> None:
            provider_name, _ = _provider_identity(candidate)
            if provider_name != "deterministic":
                await _consume_remote_ai_budget(session, user_id=user_id)

        execution = await score_with_provider_fallback(
            inputs,
            providers,
            before_score=enforce_budget,
        )
    else:
        execution = temporary_execution
    provider_name, model_version = _provider_identity(execution.provider)
    if not input_hash:
        input_hash = score_input_hash(
            inputs,
            provider=provider_name,
            model_version=model_version,
        )
        lookup = _score_lookup(
            user_id=user_id,
            job_id=job.id,
            provider=provider_name,
            model_version=model_version,
            input_hash=input_hash,
        )
        if provider_name != "deterministic":
            await _store_temporary_result(
                user_id=user_id,
                input_hash=input_hash,
                provider=provider_name,
                model_version=model_version,
                result=execution.result,
            )
    if lookup is None:
        raise RuntimeError("score cache lookup was not initialized")

    result = execution.result
    score_id = uuid.uuid4()
    statement = (
        insert(JobScore)
        .values(
            id=score_id,
            user_id=user_id,
            job_id=job.id,
            provider=provider_name,
            model_version=model_version,
            input_hash=input_hash,
            overall_score=result.overall_score,
            skill_score=result.skill_score,
            experience_score=result.experience_score,
            location_score=result.location_score,
            matched_skills=list(result.matched_skills),
            missing_skills=list(result.missing_skills),
            summary=result.summary,
        )
        .on_conflict_do_nothing(constraint="uq_job_scores_cache_key")
        .returning(JobScore)
    )
    persisted = await session.scalar(statement)
    if persisted is None:
        persisted = await session.scalar(lookup)
        if persisted is None:
            raise RuntimeError("score cache conflict did not produce a readable row")
        await session.commit()
        return persisted, True

    session.add(
        AuditLog(
            user_id=user_id,
            action="job.score.created",
            entity_type="job_score",
            entity_id=score_id,
            details={
                "job_id": str(job.id),
                "provider": provider_name,
                "model_version": model_version,
            },
        )
    )
    await session.commit()
    return persisted, temporary_hit
