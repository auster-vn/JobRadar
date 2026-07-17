import hashlib
import json
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text

from api.core.config import get_settings
from api.core.database import session_factory
from ml.features.salary_features import SalaryFeatureEncoder
from ml.salary.model import SalaryPredictor
from ml.salary.readiness import assess_salary_data_readiness

MIN_TRAINING_ROWS = 200
MIN_TEST_ROWS = 50
MAPE_PUBLICATION_LIMIT = 0.15
CALIBRATION_FOLDS = 3
SALARY_ROWS_SQL = """
WITH salary_rows AS (
  SELECT platform || ':' || platform_job_id AS source_key,
    platform AS source, true AS is_live, title, title_normalized,
    job_level, location[1] AS location,
    coalesce(experience_years_min, 0) AS experience_years,
    skills_required, posted_at::date AS source_snapshot_date,
    salary_currency, salary_min, salary_max
  FROM jobs
  WHERE salary_min IS NOT NULL OR salary_max IS NOT NULL
  UNION ALL
  SELECT source || ':' || source_record_id AS source_key,
    source, false AS is_live, title, title_normalized, job_level, location,
    coalesce(experience_years_min, 0) AS experience_years,
    skills AS skills_required, source_snapshot_date, 'VND' AS salary_currency,
    salary_min, salary_max
  FROM salary_observations
  WHERE salary_min IS NOT NULL OR salary_max IS NOT NULL
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
    (is_live AND source_snapshot_date >= current_date - interval '6 months')
    OR (
      NOT is_live
      AND source_snapshot_date >= current_date - interval '24 months'
    )
  )
ORDER BY source_snapshot_date, source_key
"""


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
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    ordered = sorted(
        rows,
        key=lambda row: (_observation_date(row), str(row["source_key"])),
    )
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
    rows: Sequence[dict[str, Any]], output_dir: Path = Path("artifacts/salary")
) -> dict[str, Any]:
    data_readiness = assess_salary_data_readiness(rows)
    if len(rows) < MIN_TRAINING_ROWS + MIN_TEST_ROWS:
        return {
            "status": "skipped",
            "reason": "not_enough_real_salary_rows",
            "sample_size": len(rows),
            "minimum": MIN_TRAINING_ROWS + MIN_TEST_ROWS,
            "data_readiness": data_readiness,
        }

    import numpy as np
    from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error, r2_score

    train_rows, test_rows, split_strategy = split_salary_rows(rows)
    if len(train_rows) < MIN_TRAINING_ROWS or len(test_rows) < MIN_TEST_ROWS:
        return {
            "status": "skipped",
            "reason": "split_does_not_meet_minimums",
            "sample_size": len(rows),
            "train_size": len(train_rows),
            "test_size": len(test_rows),
            "data_readiness": data_readiness,
        }

    q25_offset, q75_offset = calibrate_quantile_offsets(train_rows)
    encoder = SalaryFeatureEncoder()
    train_features = encoder.fit_transform(train_rows)
    test_features = encoder.transform(test_rows)
    target_train = _targets(train_rows)
    target_test = _targets(test_rows)

    predictor = SalaryPredictor()
    predictor.fit(train_features, target_train)
    predictor.calibrate(q25_offset, q75_offset)
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
        "interval_calibration": f"train_only_{CALIBRATION_FOLDS}_fold_oof",
        "train_size": len(train_rows),
        "test_size": len(test_rows),
        "split_strategy": split_strategy,
        "evaluation_unit": "individual_salary_midpoint",
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
    return train_and_evaluate(await load_salary_rows())
