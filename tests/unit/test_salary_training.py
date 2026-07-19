import hashlib
import importlib
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from ml.salary.training import (
    EVALUATION_UNIT,
    MIN_TEST_ROWS,
    MIN_TRAINING_ROWS,
    SALARY_ROWS_SQL,
    FrozenHoldout,
    build_market_benchmark_rows,
    evaluation_diagnostics,
    load_frozen_holdout,
    publication_gate_failures,
    split_salary_rows,
    train_and_evaluate,
)


def test_training_requires_real_dataset() -> None:
    result = train_and_evaluate([])

    assert result["status"] == "skipped"
    assert result["reason"] == "not_enough_real_salary_rows"
    assert result["sample_size"] == 0
    assert result["minimum"] == MIN_TRAINING_ROWS + MIN_TEST_ROWS
    assert result["data_readiness"]["ready"] is False


def test_publication_requires_accuracy_and_data_readiness() -> None:
    assert publication_gate_failures(0.10, {"ready": True}) == []
    assert publication_gate_failures(0.20, {"ready": True}) == ["mape"]
    assert publication_gate_failures(0.10, {"ready": False}) == ["data_readiness"]
    assert publication_gate_failures(0.20, {"ready": False}) == ["mape", "data_readiness"]


def test_market_benchmark_targets_use_partition_local_segment_medians() -> None:
    rows = [
        {
            "source_key": f"source:{index}",
            "title_normalized": "Backend Developer",
            "job_level": "mid",
            "location": "Ha Noi",
            "salary_midpoint": salary,
        }
        for index, salary in enumerate((10_000_000, 20_000_000, 60_000_000))
    ]

    benchmark_rows, segment_count = build_market_benchmark_rows(rows)

    assert EVALUATION_UNIT == "market_segment_median"
    assert segment_count == 1
    assert {row["salary_midpoint"] for row in benchmark_rows} == {20_000_000.0}


def test_market_benchmark_excludes_sparse_segments() -> None:
    rows = [
        {
            "source_key": f"source:{index}",
            "title_normalized": "Backend Developer",
            "job_level": "mid",
            "location": "Ha Noi",
            "salary_midpoint": 20_000_000,
        }
        for index in range(2)
    ]

    assert build_market_benchmark_rows(rows) == ([], 0)


def test_live_salary_query_keeps_one_observation_per_job() -> None:
    assert "location[1] AS location" in SALARY_ROWS_SQL
    assert "unnest(location)" not in SALARY_ROWS_SQL
    assert "END BETWEEN 1000000 AND 200000000" in SALARY_ROWS_SQL
    assert "WHERE is_active" not in SALARY_ROWS_SQL
    assert "min(source_snapshot_date) AS first_observed_on" in SALARY_ROWS_SQL
    assert "historical_dates.source_record_id = jobs.platform_job_id" in SALARY_ROWS_SQL
    assert "NOT EXISTS" in SALARY_ROWS_SQL
    assert "NOT is_live OR retained_history" in SALARY_ROWS_SQL


def test_salary_view_applies_historical_retention_to_linked_live_rows() -> None:
    migration = importlib.import_module("migrations.versions.007_dedupe_salary_sources")

    assert "historical_dates.first_observed_on IS NULL AS is_live" in (migration.DEDUPLICATED_VIEW)


def _row(index: int, observed_on: date) -> dict[str, object]:
    return {"source_key": f"source:{index}", "source_snapshot_date": observed_on}


def test_split_uses_complete_dates_for_temporal_holdout() -> None:
    start = date(2025, 1, 1)
    rows = [_row(index, start + timedelta(days=index // 50)) for index in range(300)]

    train, test, strategy = split_salary_rows(rows)

    assert strategy.startswith("temporal:")
    assert len(train) >= MIN_TRAINING_ROWS
    assert len(test) >= MIN_TEST_ROWS
    assert max(row["source_snapshot_date"] for row in train) < min(
        row["source_snapshot_date"] for row in test
    )


def test_split_falls_back_to_stable_source_hash_for_single_snapshot() -> None:
    rows = [_row(index, date(2025, 10, 31)) for index in range(300)]

    first = split_salary_rows(rows)
    second = split_salary_rows(list(reversed(rows)))

    assert first[2] == "stable_source_hash_80_20"
    assert [row["source_key"] for row in first[0]] == [row["source_key"] for row in second[0]]
    assert [row["source_key"] for row in first[1]] == [row["source_key"] for row in second[1]]
    assert set(row["source_key"] for row in first[0]).isdisjoint(
        row["source_key"] for row in first[1]
    )


def test_frozen_holdout_split_uses_only_manifest_source_keys() -> None:
    rows = [_row(index, date(2026, 7, 1)) for index in range(300)]
    holdout_keys = frozenset(f"source:{index}" for index in range(250, 300))
    holdout = FrozenHoldout(
        cohort_id="cohort-1",
        first_seen_at="2026-07-19T04:36:28+00:00",
        source_keys=holdout_keys,
        manifest_sha256="a" * 64,
        snapshot_sha256="b" * 64,
    )

    train, test, strategy = split_salary_rows(rows, holdout)

    assert len(train) == 250
    assert len(test) == 50
    assert {str(row["source_key"]) for row in test} == holdout_keys
    assert strategy == "temporal:first_seen_at=2026-07-19T04:36:28+00:00"

    with pytest.raises(ValueError, match="missing 1 source keys"):
        split_salary_rows(rows[:-1], holdout)


def test_frozen_holdout_loader_verifies_snapshot_contract(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot.csv"
    snapshot.write_bytes(b"source,source_record_id\ntopcv,1\n")
    snapshot_sha256 = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    manifest = tmp_path / "holdout.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "cohort_id": "cohort-1",
                "first_seen_at": "2026-07-19T04:36:28+00:00",
                "snapshot": snapshot.name,
                "snapshot_sha256": snapshot_sha256,
                "source_key_count": 1,
                "source_keys": ["topcv:1"],
            }
        ),
        encoding="utf-8",
    )

    holdout = load_frozen_holdout(manifest)

    assert holdout.source_keys == frozenset({"topcv:1"})
    assert holdout.snapshot_sha256 == snapshot_sha256

    snapshot.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="SHA256"):
        load_frozen_holdout(manifest)


def test_evaluation_diagnostics_reports_unseen_features_and_title_segments() -> None:
    train = [{"title_normalized": "Backend Developer", "location": "Ha Noi"}]
    test = [
        {"title_normalized": "Frontend Developer", "location": location}
        for location in ("Ha Noi", "Da Nang", "Da Nang")
    ]

    diagnostics = evaluation_diagnostics(train, test, [10.0, 20.0, 30.0], [11.0, 18.0, 45.0])

    assert diagnostics["within_15pct_rate"] == 2 / 3
    assert diagnostics["unseen_title_rate"] == 1
    assert diagnostics["unseen_location_rate"] == 2 / 3
    assert diagnostics["target_median"] == 20
    assert diagnostics["prediction_median"] == 18
    assert diagnostics["title_segments"][0]["title"] == "Frontend Developer"
    assert diagnostics["title_segments"][0]["sample_size"] == 3
