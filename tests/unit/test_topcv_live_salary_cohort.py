import csv
import hashlib
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from scripts import export_topcv_live_salary_cohort as cohort


def _row(source_record_id: str) -> dict[str, Any]:
    observed_at = datetime(2026, 7, 19, 4, 40, tzinfo=UTC)
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
    }


def test_export_topcv_live_cohort_excludes_prior_ids_and_pins_manifest(
    tmp_path: Path, monkeypatch: Any
) -> None:
    prior = tmp_path / "prior.csv"
    prior.write_text("source,source_record_id\ntopcv,1\n", encoding="utf-8")
    target = tmp_path / "cohort.csv"
    manifest = tmp_path / "holdout.json"
    batch_id = uuid.UUID("eb00da89-c02b-49d1-be3e-68d7a3946c50")

    async def fake_load_rows(
        cutoff: datetime, requested_batch_id: uuid.UUID
    ) -> tuple[list[dict[str, Any]], str]:
        assert cutoff.tzinfo is not None
        assert requested_batch_id == batch_id
        return [_row("1"), _row("2")], "2026-07-19T04:41:12+00:00"

    monkeypatch.setattr(cohort, "_load_rows", fake_load_rows)

    exported = cohort.export(
        target,
        manifest,
        cutoff=datetime(2026, 7, 19, 4, 36, tzinfo=UTC),
        batch_id=batch_id,
        prior_snapshots=[prior],
        expected_rows=1,
    )

    rows = list(csv.DictReader(target.open(encoding="utf-8", newline="")))
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    metadata = json.loads(rows[0]["source_metadata"])
    assert exported == 1
    assert rows[0]["source_record_id"] == "2"
    assert metadata["scrape_batch_id"] == str(batch_id)
    assert len(metadata["raw_payload_sha256"]) == 64
    assert payload["source_keys"] == ["topcv:2"]
    assert payload["snapshot_sha256"] == hashlib.sha256(target.read_bytes()).hexdigest()
