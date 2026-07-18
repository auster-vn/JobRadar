import json
from pathlib import Path

import pytest

from ml.salary.evaluate import evaluation_failures, main

PROJECT_ROOT = Path(__file__).parents[2]


def _passing_payload() -> dict[str, object]:
    return {
        "status": "candidate",
        "metrics": {
            "test_mape": 0.12,
            "test_mae": 2_000_000,
            "test_r2": 0.7,
            "test_size": 200,
            "split_strategy": "temporal:2026-06-01",
            "evaluation_unit": "individual_salary_midpoint",
        },
        "data_readiness": {"ready": True},
    }


def test_salary_evaluator_accepts_a_complete_temporal_evaluation() -> None:
    assert evaluation_failures(_passing_payload(), require_data_ready=True) == []


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_salary_evaluator_rejects_non_finite_mape(value: float) -> None:
    payload = _passing_payload()
    metrics = payload["metrics"]
    assert isinstance(metrics, dict)
    metrics["test_mape"] = value

    failures = evaluation_failures(payload)

    assert "test_mape must be finite" in failures


def test_salary_evaluator_rejects_aggregate_or_non_temporal_metrics() -> None:
    payload = _passing_payload()
    metrics = payload["metrics"]
    assert isinstance(metrics, dict)
    metrics["evaluation_unit"] = "title_segment_average"
    metrics["split_strategy"] = "stable_source_hash_80_20"
    metrics["test_size"] = 49

    failures = evaluation_failures(payload)

    assert "evaluation_unit must be individual_salary_midpoint" in failures
    assert "split_strategy must be a temporal holdout" in failures
    assert "test_size must be at least 50" in failures


def test_salary_evaluator_optionally_enforces_data_readiness() -> None:
    payload = _passing_payload()
    payload["data_readiness"] = {"ready": False}

    assert evaluation_failures(payload) == []
    assert evaluation_failures(payload, require_data_ready=True) == ["data_readiness must pass"]


def test_salary_evaluator_requires_committed_provenance_when_requested() -> None:
    payload = _passing_payload()
    payload["source_revision"] = "local"

    assert evaluation_failures(payload) == []
    assert evaluation_failures(payload, require_committed_revision=True) == [
        "source_revision must be a 40-character Git commit SHA"
    ]

    payload["source_revision"] = "a" * 40
    assert evaluation_failures(
        payload,
        require_committed_revision=True,
        revision_is_committed=lambda _: False,
    ) == ["source_revision must identify a Git commit reachable from HEAD"]
    assert (
        evaluation_failures(
            payload,
            require_committed_revision=True,
            revision_is_committed=lambda _: True,
        )
        == []
    )


def test_checked_in_evidence_matches_the_open_publication_gates() -> None:
    evidence_path = PROJECT_ROOT / "docs/evidence/salary_evaluation.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))

    assert evidence["run_id"] == "c946348c8fea4834a295c3dfdc5e028c"
    failures = evaluation_failures(
        evidence,
        require_data_ready=True,
        require_committed_revision=True,
    )
    assert failures == [
        "test_mape exceeds 0.1500",
        "data_readiness must pass",
        "source_revision must be a 40-character Git commit SHA",
    ]
    assert (
        main(
            [
                str(evidence_path),
                "--require-data-ready",
                "--require-committed-revision",
            ]
        )
        == 1
    )


def test_salary_evaluator_rejects_an_invalid_limit() -> None:
    with pytest.raises(ValueError, match="max_mape"):
        evaluation_failures(_passing_payload(), max_mape=float("nan"))
