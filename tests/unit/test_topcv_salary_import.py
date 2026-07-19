from datetime import date
from decimal import Decimal

import pytest

from api.services.topcv_salary_import import (
    DATASET,
    DATASET_REVISION,
    LICENSE,
    parse_topcv_salary_row,
)


def _row(**overrides: str) -> dict[str, str]:
    row = {
        "title": "Senior Backend Developer",
        "company": "Example",
        "location": "Hồ Chí Minh (mới) & Hà Nội",
        "experience": "3 năm",
        "salary": "1,000 - 2,000 USD",
        "date_posted": "2026-01-14",
        "url": "https://www.topcv.vn/viec-lam/senior-backend-developer/2012486.html?tracking=x",
    }
    row.update(overrides)
    return row


def test_parse_topcv_salary_row_preserves_identity_date_and_provenance() -> None:
    parsed = parse_topcv_salary_row(_row())

    assert parsed is not None
    assert parsed["source"] == "topcv"
    assert parsed["source_record_id"] == "2012486"
    assert parsed["source_snapshot_date"] == date(2026, 1, 14)
    assert parsed["location"] == "Ho Chi Minh"
    assert parsed["experience_years_min"] == 3
    assert parsed["salary_min"] == Decimal("25000000")
    assert parsed["salary_max"] == Decimal("50000000")
    metadata = parsed["source_metadata"]
    assert isinstance(metadata, dict)
    assert metadata["dataset"] == DATASET
    assert metadata["dataset_commit"] == DATASET_REVISION
    assert metadata["license"] == LICENSE
    assert metadata["usd_to_vnd"] == "25000"
    assert metadata["source_url"] == (
        "https://www.topcv.vn/viec-lam/senior-backend-developer/2012486.html"
    )


def test_parse_topcv_salary_row_accepts_brand_job_urls() -> None:
    parsed = parse_topcv_salary_row(
        _row(
            url=(
                "https://www.topcv.vn/brand/example/tuyen-dung/"
                "backend-developer-j2004716.html?tracking=x"
            )
        )
    )

    assert parsed is not None
    assert parsed["source_record_id"] == "2004716"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("salary", "Thoả thuận"),
        ("salary", "80,000,000 - 90,000,000 USD"),
        ("salary", "Từ 0.5 triệu"),
        ("date_posted", "14/01/2026"),
        ("url", "https://example.com/viec-lam/backend/2012486.html"),
    ],
)
def test_parse_topcv_salary_row_rejects_invalid_contract_rows(field: str, value: str) -> None:
    assert parse_topcv_salary_row(_row(**{field: value})) is None
