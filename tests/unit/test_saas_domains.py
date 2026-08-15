import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from api.main import app
from api.models import Application, AuditLog, JobScore, Notification, PipelineRun, UserProfile
from api.schemas.applications import ApplicationCreate, ApplicationUpdate
from api.schemas.scoring import JobScoreResponse


def test_application_requests_forbid_tenant_injection_and_bad_timestamps() -> None:
    job_id = uuid.uuid4()
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ApplicationCreate.model_validate({"job_id": job_id, "user_id": uuid.uuid4()})
    with pytest.raises(ValidationError, match="timezone"):
        ApplicationCreate(job_id=job_id, applied_at=datetime(2026, 8, 15))

    payload = ApplicationCreate(
        job_id=job_id,
        status="applied",
        applied_at=datetime(2026, 8, 15, tzinfo=UTC),
    )
    assert payload.status == "applied"


def test_application_patch_requires_a_field_and_rejects_null_status() -> None:
    with pytest.raises(ValidationError, match="at least one field"):
        ApplicationUpdate()
    with pytest.raises(ValidationError, match="status cannot be null"):
        ApplicationUpdate(status=None)

    payload = ApplicationUpdate(notes=None)
    assert payload.model_dump(exclude_unset=True) == {"notes": None}


def test_score_response_enforces_bounds_and_sha256_hash() -> None:
    values = {
        "id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "job_id": uuid.uuid4(),
        "overall_score": Decimal("75.25"),
        "skill_score": Decimal("80"),
        "experience_score": Decimal("70"),
        "location_score": Decimal("65"),
        "matched_skills": ["python"],
        "missing_skills": ["fastapi"],
        "summary": "Deterministic result",
        "provider": "deterministic",
        "model_version": "jobradar-deterministic-v1",
        "input_hash": "a" * 64,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    assert JobScoreResponse.model_validate(values).cached is False

    with pytest.raises(ValidationError):
        JobScoreResponse.model_validate({**values, "overall_score": Decimal("100.01")})
    with pytest.raises(ValidationError):
        JobScoreResponse.model_validate({**values, "input_hash": "not-a-sha256"})


def test_saas_models_and_profile_storage_column_are_registered() -> None:
    assert Application.__tablename__ == "applications"
    assert JobScore.__tablename__ == "job_scores"
    assert PipelineRun.__tablename__ == "pipeline_runs"
    assert Notification.__tablename__ == "notifications"
    assert AuditLog.__tablename__ == "audit_logs"
    assert "cv_storage_path" in UserProfile.__table__.columns


def test_authenticated_saas_routes_are_in_openapi() -> None:
    paths = app.openapi()["paths"]

    assert set(paths["/api/applications"]) == {"get", "post"}
    assert {"200", "201"} <= set(paths["/api/applications"]["post"]["responses"])
    assert set(paths["/api/applications/{application_id}"]) == {"patch"}
    scoring = paths["/api/jobs/{job_id}/score"]["post"]
    assert scoring["security"] == [{"HTTPBearer": []}]
    assert "requestBody" not in scoring
    assert {"429", "503"} <= set(scoring["responses"])
