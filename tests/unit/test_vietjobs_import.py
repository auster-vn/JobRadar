from decimal import Decimal

import pytest

from api.services.vietjobs_import import IT_CATEGORY, parse_vietjobs_row
from nlp.title_normalizer import TITLE_NORMALIZER_REVISION


def test_parse_vietjobs_salary_observation() -> None:
    result = parse_vietjobs_row(
        {
            "category": IT_CATEGORY,
            "job_title": "Senior Backend Developer",
            "location": "hồ chí minh",
            "technical_skills": "['Python', 'PostgreSQL']",
            "experience_required": "3 - 5 năm",
            "salary_min": "30",
            "salary_max": "50",
            "description": "Build APIs",
        }
    )

    assert result is not None
    assert result["title_normalized"] == "Senior Backend Developer"
    assert result["job_level"] == "senior"
    assert result["location"] == "Ho Chi Minh"
    assert result["salary_min"] == Decimal("30000000")
    assert result["experience_years_min"] == 3
    assert result["experience_years_max"] == 5
    metadata = result["source_metadata"]
    assert isinstance(metadata, dict)
    assert metadata["title_normalizer_revision"] == TITLE_NORMALIZER_REVISION


def test_parse_vietjobs_rejects_negotiable_and_non_it_rows() -> None:
    base = {
        "category": IT_CATEGORY,
        "job_title": "Developer",
        "salary_min": "0",
        "salary_max": "0",
    }
    assert parse_vietjobs_row(base) is None
    assert parse_vietjobs_row({**base, "category": "marketing"}) is None


@pytest.mark.parametrize(
    ("raw_experience", "expected"),
    [
        ("6 tháng", (0, 0)),
        ("18 tháng", (1, 1)),
        ("30 months", (2, 2)),
        ("2 - 4 năm", (2, 4)),
        ("Không yêu cầu", (0, 0)),
        ("No experience required", (0, 0)),
        ("Trao đổi khi phỏng vấn", (None, None)),
    ],
)
def test_parse_vietjobs_normalizes_experience_units(
    raw_experience: str, expected: tuple[int | None, int | None]
) -> None:
    result = parse_vietjobs_row(
        {
            "category": IT_CATEGORY,
            "job_title": "Backend Developer",
            "location": "hà nội",
            "technical_skills": "['Python']",
            "experience_required": raw_experience,
            "salary_min": "20",
            "salary_max": "30",
            "description": "Build APIs",
        }
    )

    assert result is not None
    assert (result["experience_years_min"], result["experience_years_max"]) == expected
