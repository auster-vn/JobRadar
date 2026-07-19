import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from statistics import median
from typing import Any

from sqlalchemy import text

from api.core.config import get_settings
from api.core.database import session_factory
from ml.features.salary_features import SalaryFeatureEncoder
from ml.salary.model import SalaryPredictor
from ml.salary.readiness import assess_salary_data_readiness
from nlp.location_normalizer import normalize_location
from nlp.title_normalizer import canonical_role

MIN_TRAINING_ROWS = 200
MIN_TEST_ROWS = 50
MIN_TEST_SEGMENTS = 5
MAPE_PUBLICATION_LIMIT = 0.15
CALIBRATION_FOLDS = 3
MIN_BENCHMARK_SEGMENT_ROWS = 3
EVALUATION_UNIT = "market_segment_median"
INTERVAL_COVERAGE_TARGET = 0.5
SALARY_ROWS_SQL = """
WITH historical_dates AS (
  SELECT source, source_record_id, min(source_snapshot_date) AS first_observed_on
  FROM salary_observations
  WHERE salary_min IS NOT NULL OR salary_max IS NOT NULL
  GROUP BY source, source_record_id
),
salary_rows AS (
  SELECT jobs.platform || ':' || jobs.platform_job_id AS source_key,
    jobs.platform AS source, true AS is_live,
    historical_dates.first_observed_on IS NOT NULL AS retained_history,
    jobs.title, jobs.title_normalized, jobs.job_level, jobs.location[1] AS location,
    coalesce(jobs.experience_years_min, 0) AS experience_years,
    jobs.skills_required,
    coalesce(
      least(jobs.posted_at::date, historical_dates.first_observed_on),
      jobs.posted_at::date,
      historical_dates.first_observed_on
    ) AS source_snapshot_date,
    jobs.salary_currency, jobs.salary_min, jobs.salary_max
  FROM jobs
  LEFT JOIN historical_dates
    ON historical_dates.source = jobs.platform
   AND historical_dates.source_record_id = jobs.platform_job_id
  WHERE jobs.salary_min IS NOT NULL OR jobs.salary_max IS NOT NULL
  UNION ALL
  SELECT source || ':' || source_record_id AS source_key,
    source, false AS is_live, true AS retained_history,
    title, title_normalized, job_level, location,
    coalesce(experience_years_min, 0) AS experience_years,
    skills AS skills_required, source_snapshot_date, 'VND' AS salary_currency,
    salary_min, salary_max
  FROM salary_observations AS observations
  WHERE (salary_min IS NOT NULL OR salary_max IS NOT NULL)
    AND NOT EXISTS (
      SELECT 1
      FROM jobs
      WHERE jobs.platform = observations.source
        AND jobs.platform_job_id = observations.source_record_id
        AND (jobs.salary_min IS NOT NULL OR jobs.salary_max IS NOT NULL)
    )
)
SELECT source_key, source, is_live, title, title_normalized, job_level,
  location, experience_years, skills_required, source_snapshot_date,
  salary_currency,
  CASE WHEN salary_min IS NOT NULL AND salary_max IS NOT NULL
    THEN (salary_min + salary_max) / 2
    ELSE coalesce(salary_min, salary_max)
  END AS salary_midpoint
FROM salary_rows
WHERE source_snapshot_date IS NOT NULL
  AND CASE WHEN salary_min IS NOT NULL AND salary_max IS NOT NULL
    THEN (salary_min + salary_max) / 2
    ELSE coalesce(salary_min, salary_max)
  END BETWEEN 1000000 AND 200000000
  AND (
    (
      is_live AND NOT retained_history
      AND source_snapshot_date >= current_date - interval '6 months'
    )
    OR (
      (NOT is_live OR retained_history)
      AND source_snapshot_date >= current_date - interval '24 months'
    )
  )
ORDER BY source_snapshot_date, source_key
"""


@dataclass(frozen=True, slots=True)
class FrozenHoldout:
    cohort_id: str
    first_seen_at: str
    source_keys: frozenset[str]
    manifest_sha256: str
    snapshot_sha256: str


def load_frozen_holdout(path: Path) -> FrozenHoldout:
    manifest_bytes = path.read_bytes()
    try:
        payload = json.loads(manifest_bytes)
    except json.JSONDecodeError as exc:
        raise ValueError(f"holdout manifest is not valid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("holdout manifest must use schema_version 1")
    source_keys = payload.get("source_keys")
    if (
        not isinstance(source_keys, list)
        or not source_keys
        or not all(isinstance(key, str) and ":" in key for key in source_keys)
    ):
        raise ValueError("holdout manifest source_keys must be a non-empty string list")
    if len(source_keys) != len(set(source_keys)):
        raise ValueError("holdout manifest contains duplicate source keys")
    if payload.get("source_key_count") != len(source_keys):
        raise ValueError("holdout manifest source_key_count does not match source_keys")
    cohort_id = payload.get("cohort_id")
    first_seen_at = payload.get("first_seen_at")
    if not isinstance(cohort_id, str) or not cohort_id:
        raise ValueError("holdout manifest cohort_id must be non-empty")
    if not isinstance(first_seen_at, str):
        raise ValueError("holdout manifest first_seen_at must be an ISO timestamp")
    try:
        observed_at = datetime.fromisoformat(first_seen_at)
    except ValueError as exc:
        raise ValueError("holdout manifest first_seen_at must be an ISO timestamp") from exc
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("holdout manifest first_seen_at must include a timezone")

    snapshot_name = payload.get("snapshot")
    expected_snapshot_sha256 = payload.get("snapshot_sha256")
    if (
        not isinstance(snapshot_name, str)
        or Path(snapshot_name).name != snapshot_name
        or not isinstance(expected_snapshot_sha256, str)
    ):
        raise ValueError("holdout manifest snapshot contract is invalid")
    snapshot_path = path.parent / snapshot_name
    actual_snapshot_sha256 = hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
    if actual_snapshot_sha256 != expected_snapshot_sha256:
        raise ValueError("holdout snapshot SHA256 does not match its manifest")
    return FrozenHoldout(
        cohort_id=cohort_id,
        first_seen_at=observed_at.isoformat(),
        source_keys=frozenset(source_keys),
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        snapshot_sha256=expected_snapshot_sha256,
    )


def _log_run(metrics: dict[str, float | int | str], status: str, artifact_dir: Path) -> str:
    import mlflow

    settings = get_settings()
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    mlflow.set_experiment(settings.mlflow_experiment)
    with mlflow.start_run(run_name=f"salary-{status}") as run:
        mlflow.log_params(
            {
                "algorithm": "XGBoost quantile ensemble with TF-IDF",
                "split": metrics["split_strategy"],
                "mape_gate": MAPE_PUBLICATION_LIMIT,
                "train_size": metrics["train_size"],
                "test_size": metrics["test_size"],
                "data_ready": metrics["data_ready"],
            }
        )
        mlflow.log_metrics(
            {
                key: float(value)
                for key, value in metrics.items()
                if key
                in {
                    "test_mape",
                    "test_mae",
                    "test_r2",
                    "baseline_mape",
                    "interval_coverage",
                    "data_ready",
                    "distinct_months",
                    "canonical_technical_rows",
                    "final_month_rows",
                }
            }
        )
        mlflow.set_tags(
            {
                "publication_status": status,
                "source_revision": settings.source_revision,
            }
        )
        mlflow.log_artifacts(str(artifact_dir), artifact_path="candidate")
        return str(run.info.run_id)


async def load_salary_rows() -> list[dict[str, Any]]:
    async with session_factory() as session:
        result = await session.execute(text(SALARY_ROWS_SQL))
        return [dict(row) for row in result.mappings()]


def _observation_date(row: dict[str, Any]) -> date:
    value = row.get("source_snapshot_date")
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise ValueError("salary row is missing a valid source_snapshot_date")


def split_salary_rows(
    rows: Sequence[dict[str, Any]],
    frozen_holdout: FrozenHoldout | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    ordered = sorted(
        rows,
        key=lambda row: (_observation_date(row), str(row["source_key"])),
    )
    if frozen_holdout is not None:
        available_keys = {str(row["source_key"]) for row in ordered}
        missing_keys = frozen_holdout.source_keys - available_keys
        if missing_keys:
            raise ValueError(
                f"frozen holdout is missing {len(missing_keys)} source keys from salary data"
            )
        train = [row for row in ordered if str(row["source_key"]) not in frozen_holdout.source_keys]
        test_rows = [row for row in ordered if str(row["source_key"]) in frozen_holdout.source_keys]
        return train, test_rows, f"temporal:first_seen_at={frozen_holdout.first_seen_at}"
    dates = sorted({_observation_date(row) for row in ordered})
    temporal_candidates: list[tuple[int, date]] = []
    target_test_size = max(MIN_TEST_ROWS, round(len(ordered) * 0.2))
    for cutoff in dates[1:]:
        test_size = sum(_observation_date(row) >= cutoff for row in ordered)
        train_size = len(ordered) - test_size
        if train_size >= MIN_TRAINING_ROWS and test_size >= MIN_TEST_ROWS:
            temporal_candidates.append((abs(test_size - target_test_size), cutoff))
    if temporal_candidates:
        cutoff = min(temporal_candidates)[1]
        train = [row for row in ordered if _observation_date(row) < cutoff]
        test_rows = [row for row in ordered if _observation_date(row) >= cutoff]
        return train, test_rows, f"temporal:{cutoff.isoformat()}"

    train, test_rows = [], []
    for row in ordered:
        digest = hashlib.sha256(str(row["source_key"]).encode()).digest()
        (test_rows if int.from_bytes(digest[:4]) % 5 == 0 else train).append(row)
    return train, test_rows, "stable_source_hash_80_20"


def _benchmark_segment(row: dict[str, Any]) -> tuple[str, str, str] | None:
    normalized_title = str(row.get("title_normalized") or "").strip()
    role = canonical_role(normalized_title) or normalized_title
    location = normalize_location(str(row.get("location") or "")) or "unknown"
    if not role:
        return None
    return role, str(row.get("job_level") or "mid"), location


def build_market_benchmark_rows(
    rows: Sequence[dict[str, Any]],
    minimum_segment_rows: int = MIN_BENCHMARK_SEGMENT_ROWS,
) -> tuple[list[dict[str, Any]], int]:
    """Replace noisy offer labels with partition-local market segment medians."""
    if minimum_segment_rows < 1:
        raise ValueError("minimum_segment_rows must be positive")
    grouped_targets: dict[tuple[str, str, str], list[float]] = {}
    for row in rows:
        segment = _benchmark_segment(row)
        if segment is None:
            continue
        grouped_targets.setdefault(segment, []).append(float(row["salary_midpoint"]))
    medians = {
        segment: float(median(targets))
        for segment, targets in grouped_targets.items()
        if len(targets) >= minimum_segment_rows
    }
    benchmark_rows = []
    for row in rows:
        segment = _benchmark_segment(row)
        if segment is None or segment not in medians:
            continue
        benchmark_rows.append(
            {
                **row,
                "salary_midpoint": medians[segment],
                "benchmark_segment": "|".join(segment),
            }
        )
    return benchmark_rows, len(medians)


def _targets(rows: Sequence[dict[str, Any]]) -> Any:
    import numpy as np

    return np.asarray([float(row["salary_midpoint"]) for row in rows])


def evaluation_diagnostics(
    train_rows: Sequence[dict[str, Any]],
    test_rows: Sequence[dict[str, Any]],
    targets: Any,
    predictions: Any,
) -> dict[str, Any]:
    """Describe holdout drift after prediction without influencing model fitting."""
    import numpy as np

    target_values = np.asarray(targets, dtype=float)
    prediction_values = np.asarray(predictions, dtype=float)
    absolute_percentage_errors = np.abs(target_values - prediction_values) / target_values

    def unseen_rate(field: str) -> float:
        known = {str(row.get(field) or "").strip().casefold() for row in train_rows}
        return float(
            np.mean(
                [str(row.get(field) or "").strip().casefold() not in known for row in test_rows]
            )
        )

    indices_by_title: dict[str, list[int]] = {}
    for index, row in enumerate(test_rows):
        title = str(row.get("title_normalized") or row.get("title") or "unknown").strip()
        indices_by_title.setdefault(title, []).append(index)
    title_segments: list[dict[str, Any]] = []
    for title, indices in indices_by_title.items():
        if len(indices) < 3:
            continue
        segment_targets = target_values[indices]
        segment_predictions = prediction_values[indices]
        title_segments.append(
            {
                "title": title,
                "sample_size": len(indices),
                "mape": float(
                    np.mean(np.abs(segment_targets - segment_predictions) / segment_targets)
                ),
                "mae": float(np.mean(np.abs(segment_targets - segment_predictions))),
                "target_median": float(np.median(segment_targets)),
                "prediction_median": float(np.median(segment_predictions)),
            }
        )
    title_segments.sort(key=lambda row: (-int(row["sample_size"]), str(row["title"])))

    return {
        "within_15pct_rate": float(np.mean(absolute_percentage_errors <= 0.15)),
        "p90_absolute_percentage_error": float(np.quantile(absolute_percentage_errors, 0.90)),
        "median_percentage_bias": float(
            np.median((prediction_values - target_values) / target_values)
        ),
        "target_median": float(np.median(target_values)),
        "prediction_median": float(np.median(prediction_values)),
        "unseen_title_rate": unseen_rate("title_normalized"),
        "unseen_location_rate": unseen_rate("location"),
        "title_segments": title_segments[:20],
    }


def publication_gate_failures(test_mape: float, data_readiness: dict[str, Any]) -> list[str]:
    failures = []
    if test_mape > MAPE_PUBLICATION_LIMIT:
        failures.append("mape")
    if not data_readiness.get("ready"):
        failures.append("data_readiness")
    return failures


def _calibration_fold(row: dict[str, Any]) -> int:
    digest = hashlib.sha256(str(row["source_key"]).encode()).digest()
    return int.from_bytes(digest[4:8]) % CALIBRATION_FOLDS


def calibrate_quantile_offsets(rows: Sequence[dict[str, Any]]) -> tuple[float, float]:
    """Estimate interval corrections from train-only out-of-fold residuals."""
    import numpy as np

    lower_residuals: list[float] = []
    upper_residuals: list[float] = []
    for fold in range(CALIBRATION_FOLDS):
        fold_train = [row for row in rows if _calibration_fold(row) != fold]
        fold_validation = [row for row in rows if _calibration_fold(row) == fold]
        if not fold_train or not fold_validation:
            continue
        encoder = SalaryFeatureEncoder()
        train_features = encoder.fit_transform(fold_train)
        validation_features = encoder.transform(fold_validation)
        predictor = SalaryPredictor()
        predictor.fit_quantiles(train_features, _targets(fold_train))
        predictions = predictor.predict_quantiles(validation_features)
        targets = _targets(fold_validation)
        lower_residuals.extend((targets - predictions["salary_p25"]).tolist())
        upper_residuals.extend((targets - predictions["salary_p75"]).tolist())
    if len(lower_residuals) != len(rows) or len(upper_residuals) != len(rows):
        raise RuntimeError("out-of-fold salary calibration did not cover every training row")
    return (
        float(np.quantile(lower_residuals, 0.25)),
        float(np.quantile(upper_residuals, 0.75)),
    )


def calibrate_interval_radius(
    rows: Sequence[dict[str, Any]],
) -> tuple[float, str, int]:
    """Estimate a train-only conformal radius on the latest temporal partition."""
    development_raw, calibration_raw, strategy = split_salary_rows(rows)
    if not strategy.startswith("temporal:"):
        raise ValueError("interval calibration requires a temporal training partition")
    development, _ = build_market_benchmark_rows(development_raw)
    calibration, _ = build_market_benchmark_rows(calibration_raw)
    if len(development) < MIN_TRAINING_ROWS or len(calibration) < MIN_TEST_ROWS:
        raise ValueError("interval calibration partitions do not meet minimum row counts")

    import numpy as np

    encoder = SalaryFeatureEncoder()
    development_features = encoder.fit_transform(development)
    calibration_features = encoder.transform(calibration)
    predictor = SalaryPredictor()
    predictor.fit_mean(development_features, _targets(development))
    predictions = np.expm1(predictor.model_mean.predict(calibration_features))
    absolute_residuals = np.abs(_targets(calibration) - predictions)
    quantile = min(
        1.0,
        np.ceil((len(absolute_residuals) + 1) * INTERVAL_COVERAGE_TARGET) / len(absolute_residuals),
    )
    radius = float(np.quantile(absolute_residuals, quantile, method="higher"))
    return radius, strategy, len(calibration)


def _verify_artifacts(
    artifact_dir: Path,
    rows: list[dict[str, Any]],
    expected_predictions: dict[str, Any],
) -> None:
    import numpy as np

    restored_encoder = SalaryFeatureEncoder.load(artifact_dir / "encoder.joblib")
    restored_predictor = SalaryPredictor.load(artifact_dir)
    restored = restored_predictor.predict_many(restored_encoder.transform(rows))
    for key in ("salary_estimate", "salary_p25", "salary_p75"):
        if not np.allclose(expected_predictions[key], restored[key], rtol=1e-5, atol=1.0):
            raise RuntimeError(f"salary artifact round-trip changed {key}")


def train_and_evaluate(
    rows: Sequence[dict[str, Any]],
    output_dir: Path = Path("artifacts/salary"),
    frozen_holdout: FrozenHoldout | None = None,
) -> dict[str, Any]:
    if len(rows) < MIN_TRAINING_ROWS + MIN_TEST_ROWS:
        return {
            "status": "skipped",
            "reason": "not_enough_real_salary_rows",
            "sample_size": len(rows),
            "minimum": MIN_TRAINING_ROWS + MIN_TEST_ROWS,
            "data_readiness": assess_salary_data_readiness(rows),
        }

    import numpy as np
    from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error, r2_score

    source_revision = get_settings().source_revision
    raw_train_rows, raw_test_rows, split_strategy = split_salary_rows(rows, frozen_holdout)
    data_readiness = assess_salary_data_readiness(rows, segment_rows=raw_train_rows)
    train_rows, train_segment_count = build_market_benchmark_rows(raw_train_rows)
    test_rows, test_segment_count = build_market_benchmark_rows(raw_test_rows)
    if (
        len(train_rows) < MIN_TRAINING_ROWS
        or len(test_rows) < MIN_TEST_ROWS
        or test_segment_count < MIN_TEST_SEGMENTS
    ):
        return {
            "status": "skipped",
            "reason": "benchmark_split_does_not_meet_minimums",
            "sample_size": len(rows),
            "train_size": len(train_rows),
            "test_size": len(test_rows),
            "raw_train_size": len(raw_train_rows),
            "raw_test_size": len(raw_test_rows),
            "train_segment_count": train_segment_count,
            "test_segment_count": test_segment_count,
            "data_readiness": data_readiness,
        }

    q25_offset, q75_offset = calibrate_quantile_offsets(train_rows)
    interval_radius, interval_strategy, interval_calibration_size = calibrate_interval_radius(
        raw_train_rows
    )
    encoder = SalaryFeatureEncoder()
    train_features = encoder.fit_transform(train_rows)
    test_features = encoder.transform(test_rows)
    target_train = _targets(train_rows)
    target_test = _targets(test_rows)

    predictor = SalaryPredictor()
    predictor.fit(train_features, target_train)
    predictor.calibrate(q25_offset, q75_offset, interval_radius)
    predictions = predictor.predict_many(test_features)
    mean_predictions = predictions["salary_estimate"]
    diagnostics = evaluation_diagnostics(train_rows, test_rows, target_test, mean_predictions)
    baseline = np.full(len(test_rows), np.median(target_train))
    metrics: dict[str, float | int | str] = {
        "test_mape": float(mean_absolute_percentage_error(target_test, mean_predictions)),
        "test_mae": float(mean_absolute_error(target_test, mean_predictions)),
        "test_r2": float(r2_score(target_test, mean_predictions)),
        "baseline_mape": float(mean_absolute_percentage_error(target_test, baseline)),
        "interval_coverage": float(
            np.mean(
                (target_test >= predictions["salary_p25"])
                & (target_test <= predictions["salary_p75"])
            )
        ),
        "q25_calibration_offset": q25_offset,
        "q75_calibration_offset": q75_offset,
        "interval_radius": interval_radius,
        "interval_calibration": f"train_only_split_conformal:{interval_strategy}",
        "interval_calibration_size": interval_calibration_size,
        "train_size": len(train_rows),
        "test_size": len(test_rows),
        "raw_train_size": len(raw_train_rows),
        "raw_test_size": len(raw_test_rows),
        "train_segment_count": train_segment_count,
        "test_segment_count": test_segment_count,
        "minimum_segment_rows": MIN_BENCHMARK_SEGMENT_ROWS,
        "holdout_cohort": frozen_holdout.cohort_id if frozen_holdout else "automatic_temporal",
        "holdout_manifest_sha256": frozen_holdout.manifest_sha256 if frozen_holdout else "",
        "split_strategy": split_strategy,
        "evaluation_unit": EVALUATION_UNIT,
        "train_period_start": str(min(_observation_date(row) for row in train_rows)),
        "train_period_end": str(max(_observation_date(row) for row in train_rows)),
        "test_period_start": str(min(_observation_date(row) for row in test_rows)),
        "test_period_end": str(max(_observation_date(row) for row in test_rows)),
        "trained_at": datetime.now().astimezone().isoformat(),
        "data_ready": int(data_readiness["ready"]),
        "distinct_months": data_readiness["distinct_months"],
        "canonical_technical_rows": data_readiness["canonical_technical_rows"],
        "final_month_rows": data_readiness["final_month_rows"],
    }
    candidate_dir = output_dir / "candidate"
    predictor.save(candidate_dir)
    encoder.save(candidate_dir / "encoder.joblib")
    verification_rows = test_rows[: min(10, len(test_rows))]
    _verify_artifacts(
        candidate_dir,
        verification_rows,
        predictor.predict_many(encoder.transform(verification_rows)),
    )
    (candidate_dir / "metadata.json").write_text(
        json.dumps(
            {
                "status": "candidate",
                "source_revision": source_revision,
                "metrics": metrics,
                "evaluation_diagnostics": diagnostics,
                "data_readiness": data_readiness,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    failed_gates = publication_gate_failures(float(metrics["test_mape"]), data_readiness)
    if failed_gates:
        (candidate_dir / "metadata.json").write_text(
            json.dumps(
                {
                    "status": "rejected",
                    "source_revision": source_revision,
                    "failed_gates": failed_gates,
                    "metrics": metrics,
                    "evaluation_diagnostics": diagnostics,
                    "data_readiness": data_readiness,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        run_id = _log_run(metrics, "rejected", candidate_dir)
        reason = (
            f"{failed_gates[0]}_gate_failed"
            if len(failed_gates) == 1
            else "publication_gates_failed"
        )
        return {
            "status": "rejected",
            "reason": reason,
            "failed_gates": failed_gates,
            "run_id": run_id,
            "data_readiness": data_readiness,
            "evaluation_diagnostics": diagnostics,
            **metrics,
        }
    current_dir = output_dir / "current"
    predictor.save(current_dir)
    encoder.save(current_dir / "encoder.joblib")
    (current_dir / "metadata.json").write_text(
        json.dumps(
            {
                "status": "published",
                "source_revision": source_revision,
                "failed_gates": [],
                "metrics": metrics,
                "evaluation_diagnostics": diagnostics,
                "data_readiness": data_readiness,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    run_id = _log_run(metrics, "published", candidate_dir)
    return {
        "status": "published",
        "run_id": run_id,
        "data_readiness": data_readiness,
        "evaluation_diagnostics": diagnostics,
        **metrics,
    }


async def train_from_database() -> dict[str, Any]:
    manifest = get_settings().salary_holdout_manifest
    frozen_holdout = load_frozen_holdout(Path(manifest)) if manifest else None
    return train_and_evaluate(await load_salary_rows(), frozen_holdout=frozen_holdout)
