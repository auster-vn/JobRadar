import hashlib
from pathlib import Path

from nlp.title_normalizer import TITLE_NORMALIZER_REVISION
from scripts.import_salary_snapshot import read_snapshot

SNAPSHOT_SHA256 = "f823fdb009c69ff9a2e8a367497936fcd7001adcfa60bc4dc0784d6c55ff357c"
TOPCV_SNAPSHOT_SHA256 = "977b7da686d78e507b8424a28210d7746bfb3bb20acec1e0920cc1165de1be4e"


def test_compact_salary_snapshot_is_valid() -> None:
    path = Path("data/vietjobs_it_salary_observations.csv")
    rows = read_snapshot(path)

    assert hashlib.sha256(path.read_bytes()).hexdigest() == SNAPSHOT_SHA256
    assert len(rows) == 1115
    assert len({row["source_record_id"] for row in rows}) == 1115
    assert all(row["salary_min"] is not None or row["salary_max"] is not None for row in rows)
    assert all(
        value is None or 0 <= value <= 15
        for row in rows
        for value in (row["experience_years_min"], row["experience_years_max"])
    )
    business_analysts = [row for row in rows if row["title"] == "BUSINESS ANALYST"]
    assert business_analysts
    assert all(row["title_normalized"] == "Business Analyst" for row in business_analysts)
    assert all(
        isinstance(row["source_metadata"], dict)
        and row["source_metadata"]["title_normalizer_revision"] == TITLE_NORMALIZER_REVISION
        for row in rows
    )


def test_compact_topcv_salary_snapshot_is_valid() -> None:
    path = Path("data/topcv_2026_it_salary_observations.csv")
    rows = read_snapshot(path)

    assert hashlib.sha256(path.read_bytes()).hexdigest() == TOPCV_SNAPSHOT_SHA256
    assert len(rows) == 818
    assert len({row["source_record_id"] for row in rows}) == 818
    assert {row["source_snapshot_date"].isoformat()[:7] for row in rows} == {
        "2025-12",
        "2026-01",
    }
    assert all(row["source"] == "topcv" for row in rows)
    assert all(row["location"] != "Hồ Chí Minh (mới)" for row in rows)
    usd_rows = [
        row
        for row in rows
        if isinstance(row["source_metadata"], dict)
        and row["source_metadata"].get("salary_source_currency") == "USD"
    ]
    assert len(usd_rows) == 30
    assert all(row["source_metadata"].get("usd_to_vnd") == "25000" for row in usd_rows)
