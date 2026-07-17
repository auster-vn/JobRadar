import json
import math
import os
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import FastAPI, HTTPException, status

from api.schemas.salary import SalaryPredictionRequest
from ml.features.salary_features import SalaryFeatureEncoder
from ml.salary.model import SalaryPredictor
from ml.salary.training import MAPE_PUBLICATION_LIMIT

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

    def __init__(self, artifact_dir: Path) -> None:
        self.artifact_dir = artifact_dir
        self._signature: tuple[tuple[str, int, int], ...] | None = None
        self._encoder: SalaryFeatureEncoder | None = None
        self._predictor: SalaryPredictor | None = None
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
            if not math.isfinite(test_mape) or not 0 <= test_mape <= MAPE_PUBLICATION_LIMIT:
                return False
            if metadata.get("data_readiness", {}).get("ready") is not True:
                return False
            encoder = SalaryFeatureEncoder.load(self.artifact_dir / "encoder.joblib")
            predictor = SalaryPredictor.load(self.artifact_dir)
            self._encoder = encoder
            self._predictor = predictor
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
        row: dict[str, Any] = {
            "title": payload.title,
            "job_level": payload.level,
            "location": payload.location,
            "experience_years": payload.experience_years,
            "skills_required": payload.skills,
        }
        result = self._predictor.predict(self._encoder.transform([row]))
        return result


model = PublishedSalaryModel(
    Path(os.getenv("SALARY_MODEL_ARTIFACT_DIR", "artifacts/salary/current"))
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
