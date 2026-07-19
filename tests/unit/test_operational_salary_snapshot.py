import csv
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from scripts import export_operational_salary_snapshot as snapshot


def _row(source_record_id: str) -> dict[str, Any]:
    observed_at = datetime(2026, 7, 18, 17, 2, tzinfo=UTC)
    return {
        "platform_job_id": source_record_id,
        "source_url": f"https://www.topcv.vn/viec-lam/example/{source_record_id}.html",
        "title": "Senior Backend Developer",
        "job_level": "senior",
        "location": ["Ha Noi"],
        "experience_years_min": 4,
        "experience_years_max": 5,
        "skills_required": ["Python"],
        "salary_min": Decimal("30000000"),
        "salary_max": Decimal("45000000"),
        "posted_at": observed_at,
        "created_at": observed_at,
        "company_name": "Example Co",
        "raw_json": {"platform_job_id": source_record_id, "salary_text": "30 - 45 triệu"},
        "scraped_at": observed_at,
        "first_seen_batch_id": uuid.UUID("42c0cbd6-0939-4304-ba41-2bf2766aef6a"),
    }


def test_export_operational_snapshot_excludes_existing_source_ids(
    tmp_path: Path, monkeypatch: Any
) -> None:
    prior = tmp_path / "prior.csv"
    prior.write_text("source,source_record_id\ntopcv,1\n", encoding="utf-8")
    target = tmp_path / "operational.csv"
    cutoff = datetime(2026, 7, 19, 4, 36, tzinfo=UTC)

    async def fake_load_rows(platform: str, requested_cutoff: datetime) -> list[dict[str, Any]]:
        assert platform == "topcv"
        assert requested_cutoff == cutoff
        return [_row("1"), _row("2")]

    monkeypatch.setattr(snapshot, "_load_rows", fake_load_rows)

    exported = snapshot.export(
        target,
        platform="topcv",
        cutoff=cutoff,
        prior_snapshots=[prior],
        expected_rows=1,
    )

    rows = list(csv.DictReader(target.open(encoding="utf-8", newline="")))
    metadata = json.loads(rows[0]["source_metadata"])
    assert exported == 1
    assert rows[0]["source_record_id"] == "2"
    assert metadata["first_seen_batch_id"] == "42c0cbd6-0939-4304-ba41-2bf2766aef6a"
    assert metadata["snapshot_cutoff"] == cutoff.isoformat()
    assert len(metadata["raw_payload_sha256"]) == 64


def test_export_operational_snapshot_rejects_unsupported_platform(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsupported"):
        snapshot.export(
            tmp_path / "invalid.csv",
            platform="linkedin",
            cutoff=datetime(2026, 7, 19, tzinfo=UTC),
            prior_snapshots=[],
            expected_rows=0,
        )
