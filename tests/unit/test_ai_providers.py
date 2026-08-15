import pytest
from pydantic import ValidationError

from api.services.ai_providers import (
    DeterministicProvider,
    ScoreInput,
    ScoreOutput,
    _decode_json,
    score_batch,
)


def _input() -> ScoreInput:
    return ScoreInput(
        job_title="Senior Backend Engineer",
        required_skills=["Python", "FastAPI"],
        job_locations=["Ho Chi Minh"],
        experience_years_min=4,
        salary_max=50_000_000,
        profile_skills=[" python "],
        profile_locations=["ho chi minh"],
        profile_experience_years=4,
        profile_target_salary=40_000_000,
    )


@pytest.mark.asyncio
async def test_deterministic_provider_scores_canonical_inputs() -> None:
    result = await DeterministicProvider().score(_input())

    assert result.overall_score == 70
    assert result.skill_score == 50
    assert result.experience_score == 100
    assert result.location_score == 100
    assert result.salary_score == 100
    assert result.strengths[0] == "Matched skill: Python"
    assert result.gaps[0] == "Missing skill: FastAPI"


def test_provider_json_schema_rejects_out_of_range_scores() -> None:
    with pytest.raises(ValidationError):
        ScoreOutput(
            overall_score=101,
            skill_score=50,
            experience_score=50,
            location_score=50,
            salary_score=50,
            explanation="invalid",
        )


def test_provider_json_decoder_accepts_json_fence_only() -> None:
    assert _decode_json('```json\n{"overall_score": 80}\n```') == {"overall_score": 80}


@pytest.mark.asyncio
async def test_batching_preserves_input_order_with_free_fallback() -> None:
    inputs = [_input(), _input().model_copy(update={"required_skills": ["Go"]})]

    results = await score_batch(inputs, batch_size=1)

    assert [result.skill_score for result in results] == [50, 0]
