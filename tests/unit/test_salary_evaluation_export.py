import hashlib
import json
from pathlib import Path

import pytest

from scripts.export_salary_evaluation import build_evidence, export_evidence


def _metadata() -> dict[str, object]:
    return {
        "status": "rejected",
        "failed_gates": ["mape", "data_readiness"],
        "metrics": {
            "test_mape": 0.3,
            "test_mae": 10_000_000,
            "test_r2": -0.1,
            "baseline_mape": 0.4,
            "interval_coverage": 0.4,
            "interval_radius": 3_000_000,
            "interval_calibration": "train_only_split_conformal:temporal:2026-05-01",
            "interval_calibration_size": 100,
            "train_size": 1000,
            "test_size": 200,
            "raw_train_size": 1200,
            "raw_test_size": 250,
            "train_segment_count": 20,
            "test_segment_count": 8,
            "minimum_segment_rows": 3,
            "holdout_cohort": "topcv-it-first-seen-2026-07-19",
            "holdout_manifest_sha256": "d" * 64,
            "split_strategy": "temporal:2026-06-01",
            "evaluation_unit": "individual_salary_midpoint",
            "train_period_start": "2025-01-01",
            "train_period_end": "2026-05-31",
            "test_period_start": "2026-06-01",
            "test_period_end": "2026-06-30",
            "trained_at": "2026-07-01T00:00:00+00:00",
        },
        "evaluation_diagnostics": {
            "within_15pct_rate": 0.2,
            "p90_absolute_percentage_error": 0.7,
            "median_percentage_bias": -0.2,
            "target_median": 30_000_000,
            "prediction_median": 24_000_000,
            "unseen_title_rate": 0.5,
            "unseen_location_rate": 0.1,
            "title_segments": [],
        },
        "data_readiness": {
            "ready": False,
            "sample_size": 1200,
            "distinct_months": 4,
            "canonical_technical_rows": 800,
            "final_month": "2026-06",
            "final_month_rows": 200,
            "duplicate_source_keys": 0,
            "non_vnd_rows": 0,
            "qualified_segments": 1,
            "segment_candidates": 3,
            "supported_segments": [{"role": "Backend"}],
            "underqualified_segments": [{"role": "Backend"}, {"role": "Frontend"}],
        },
    }


def test_build_evidence_compacts_and_hashes_candidate_metadata() -> None:
    metadata_bytes = json.dumps(_metadata()).encode()

    evidence = build_evidence(
        metadata_bytes,
        run_id="a" * 32,
        source_revision="local-test",
    )

    assert evidence["metadata_sha256"] == hashlib.sha256(metadata_bytes).hexdigest()
    assert evidence["data_readiness"]["underqualified_segments"] == 2
    assert evidence["data_readiness"]["supported_segments"] == 1
    assert "title_segments" not in evidence["evaluation_diagnostics"]


def test_export_evidence_replaces_the_output_atomically(tmp_path: Path) -> None:
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps(_metadata()), encoding="utf-8")
    output_path = tmp_path / "nested" / "evaluation.json"

    evidence = export_evidence(
        metadata_path,
        output_path,
        run_id="b" * 32,
        source_revision="c" * 40,
    )

    assert json.loads(output_path.read_text(encoding="utf-8")) == evidence
    assert not (output_path.parent / ".evaluation.json.tmp").exists()


@pytest.mark.parametrize("run_id", ["", "A" * 32, "a" * 31, "a" * 33])
def test_build_evidence_rejects_invalid_mlflow_run_ids(run_id: str) -> None:
    with pytest.raises(ValueError, match="run_id"):
        build_evidence(
            json.dumps(_metadata()).encode(),
            run_id=run_id,
            source_revision="local-test",
        )
