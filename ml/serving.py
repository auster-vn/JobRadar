import json
import math
import os
import re
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import FastAPI, HTTPException, status

from api.schemas.salary import SalaryPredictionRequest
from ml.features.salary_features import SalaryFeatureEncoder
from ml.salary.model import SalaryPredictor
from ml.salary.training import MAPE_PUBLICATION_LIMIT
from nlp.location_normalizer import normalize_location
from nlp.title_normalizer import canonical_role, normalize_title

REQUIRED_ARTIFACTS = {
    "encoder.joblib",
    "mean.json",
    "q25.json",
    "q75.json",
    "calibration.json",
    "metadata.json",
}


class PublishedSalaryModel:
    """Lazy, fail-closed loader for the model bundle selected by training."""

    def __init__(self, artifact_dir: Path, expected_source_revision: str | None = None) -> None:
        self.artifact_dir = artifact_dir
        self.expected_source_revision = expected_source_revision
        self._signature: tuple[tuple[str, int, int], ...] | None = None
        self._encoder: SalaryFeatureEncoder | None = None
        self._predictor: SalaryPredictor | None = None
        self._supported_segments: frozenset[tuple[str, str, str]] = frozenset()
        self._lock = Lock()

    def _artifact_signature(self) -> tuple[tuple[str, int, int], ...] | None:
        if not self.artifact_dir.is_dir():
            return None
        paths = [self.artifact_dir / name for name in sorted(REQUIRED_ARTIFACTS)]
        if not all(path.is_file() for path in paths):
            return None
        return tuple((path.name, path.stat().st_mtime_ns, path.stat().st_size) for path in paths)

    def _load(self) -> bool:
        signature = self._artifact_signature()
        if signature is None:
            return False
        if (
            signature == self._signature
            and self._encoder is not None
            and self._predictor is not None
        ):
            return True
        with self._lock:
            if signature == self._signature and self._encoder is not None:
                return True
            metadata = json.loads((self.artifact_dir / "metadata.json").read_text(encoding="utf-8"))
            metrics = metadata.get("metrics", {})
            test_mape = float(metrics.get("test_mape", 1.0))
            if metadata.get("status") != "published":
                return False
            if (
                self.expected_source_revision is not None
                and metadata.get("source_revision") != self.expected_source_revision
            ):
                return False
            if not math.isfinite(test_mape) or not 0 <= test_mape <= MAPE_PUBLICATION_LIMIT:
                return False
            if metadata.get("data_readiness", {}).get("ready") is not True:
                return False
            raw_segments = metadata.get("data_readiness", {}).get("supported_segments")
            if (
                not isinstance(raw_segments, list)
                or not raw_segments
                or not all(
                    isinstance(item, dict)
                    and all(key in item for key in ("role", "level", "location"))
                    for item in raw_segments
                )
            ):
                return False
            try:
                supported_segments = frozenset(
                    (str(item["role"]), str(item["level"]), str(item["location"]))
                    for item in raw_segments
                )
            except KeyError:
                return False
            if not supported_segments:
                return False
            encoder = SalaryFeatureEncoder.load(self.artifact_dir / "encoder.joblib")
            predictor = SalaryPredictor.load(self.artifact_dir)
            self._encoder = encoder
            self._predictor = predictor
            self._supported_segments = supported_segments
            self._signature = signature
        return True

    @property
    def available(self) -> bool:
        try:
            return self._load()
        except (OSError, ValueError, TypeError, KeyError):
            return False

    def predict(self, payload: SalaryPredictionRequest) -> dict[str, int | str]:
        if not self.available or self._encoder is None or self._predictor is None:
            raise RuntimeError("no published salary model is available")
        normalized = normalize_title(payload.title)
        segment = (
            canonical_role(normalized.title) or normalized.title,
            payload.level,
            normalize_location(payload.location) or "unknown",
        )
        if segment not in self._supported_segments:
            raise RuntimeError("salary model does not support this market segment")
        row: dict[str, Any] = {
            "title": payload.title,
            "title_normalized": normalized.title,
            "job_level": payload.level,
            "location": payload.location,
            "experience_years": payload.experience_years,
            "skills_required": payload.skills,
        }
        result = self._predictor.predict(self._encoder.transform([row]))
        return result


runtime_revision = os.getenv("SOURCE_REVISION", "")
expected_revision = runtime_revision if re.fullmatch(r"[0-9a-f]{40}", runtime_revision) else None
model = PublishedSalaryModel(
    Path(os.getenv("SALARY_MODEL_ARTIFACT_DIR", "artifacts/salary/current")),
    expected_source_revision=expected_revision,
)
app = FastAPI(title="JobRadar VN Salary Model", version="0.1.0")


@app.get("/health")
def health() -> dict[str, bool | str]:
    return {"status": "ok", "model_available": model.available}


@app.post("/predict")
def predict(payload: SalaryPredictionRequest) -> dict[str, int | str]:
    try:
        return model.predict(payload)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
