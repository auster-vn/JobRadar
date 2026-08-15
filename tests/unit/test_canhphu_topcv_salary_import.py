from datetime import date
from decimal import Decimal

import pytest

from api.services.canhphu_topcv_salary_import import (
    DATASET,
    DATASET_REVISION,
    LICENSE,
    parse_canhphu_topcv_salary_row,
)

OBSERVED_ON = date(2026, 5, 18)


def _row(**overrides: str) -> dict[str, str]:
    row = {
        "job_title": "Senior Backend Developer (Python, FastAPI)",
        "company_name": "Example Technology JSC",
        "company_size": "100-499 employees",
        "location": "Hồ Chí Minh",
        "salary_min": "15.0",
        "salary_max": "30.0",
        "salary_currency": "VND",
        "experience_required": "3.0",
        "skills": "['Python', 'FastAPI', 'Việc làm IT']",
        "job_type": "Full-time",
        "job_level": "Staff",
        "posted_date": "2026-05-18",
        "deadline": "2026-06-18",
        "job_description": "Build backend services",
        "benefits": "",
        "source": "topcv",
    }
    row.update(overrides)
    return row


def _parse(**overrides: str) -> dict[str, object] | None:
    return parse_canhphu_topcv_salary_row(
        _row(**overrides),
        observed_on=OBSERVED_ON,
        raw_filename="topcv_2026-05-18.csv",
        raw_sha256="a" * 64,
    )


def test_parse_archive_row_normalizes_units_identity_and_provenance() -> None:
    parsed = _parse()

    assert parsed is not None
    assert parsed["source"] == "topcv_archive"
    assert str(parsed["source_record_id"]).startswith("canhphu-")
    assert len(str(parsed["source_record_id"])) == 56
    assert parsed["source_snapshot_date"] == OBSERVED_ON
    assert parsed["title_normalized"] == "Senior Backend Developer"
    assert parsed["job_level"] == "senior"
    assert parsed["location"] == "Ho Chi Minh"
    assert parsed["experience_years_min"] == 3
    assert parsed["skills"] == ["FastAPI", "Python"]
    assert parsed["salary_min"] == Decimal("15000000.0")
    assert parsed["salary_max"] == Decimal("30000000.0")
    metadata = parsed["source_metadata"]
    assert isinstance(metadata, dict)
    assert metadata["dataset"] == DATASET
    assert metadata["dataset_commit"] == DATASET_REVISION
    assert metadata["license"] == LICENSE
    assert metadata["company_name"] == "Example Technology JSC"
    assert metadata["observation_semantics"] == "crawler run date"


def test_parse_archive_row_accepts_full_vnd_and_converts_usd() -> None:
    full_vnd = _parse(salary_min="15000000", salary_max="30000000")
    usd = _parse(salary_min="1000", salary_max="2000", salary_currency="USD")

    assert full_vnd is not None
    assert full_vnd["salary_min"] == Decimal("15000000")
    assert usd is not None
    assert usd["salary_min"] == Decimal("25000000")
    assert usd["salary_max"] == Decimal("50000000")
    assert usd["source_metadata"]["usd_to_vnd"] == "25000"  # type: ignore[index]


def test_archive_identity_is_stable_when_salary_changes() -> None:
    first = _parse(salary_min="15", salary_max="30")
    second = _parse(salary_min="20", salary_max="35")

    assert first is not None and second is not None
    assert first["source_record_id"] == second["source_record_id"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source", "example"),
        ("posted_date", "2026-05-17"),
        ("company_name", ""),
        ("location", ""),
        ("salary_min", "0"),
        ("salary_min", "30"),
    ],
)
def test_parse_archive_row_rejects_invalid_contract_rows(field: str, value: str) -> None:
    overrides = {field: value}
    if field == "salary_min" and value == "0":
        overrides["salary_max"] = "0"
    if field == "salary_min" and value == "30":
        overrides["salary_max"] = "15"
    assert _parse(**overrides) is None
