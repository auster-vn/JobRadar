import hashlib
from pathlib import Path

from nlp.title_normalizer import TITLE_NORMALIZER_REVISION
from scripts.import_salary_snapshot import read_snapshot

SNAPSHOT_SHA256 = "f823fdb009c69ff9a2e8a367497936fcd7001adcfa60bc4dc0784d6c55ff357c"


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
