import ast
import hashlib
import json
from datetime import date
from decimal import Decimal, InvalidOperation

from nlp.experience_parser import parse_experience_years
from nlp.location_normalizer import LOCATION_NORMALIZER_REVISION, normalize_primary_location
from nlp.title_normalizer import TITLE_NORMALIZER_REVISION, normalize_title

IT_CATEGORY = "công_nghệ_thông_tin_kỹ_thuật_số"
SOURCE = "vietjobs_vinuniversity"
SOURCE_SNAPSHOT_DATE = date(2025, 10, 31)


def _list_field(value: str) -> list[str]:
    if not value.strip():
        return []
    try:
        parsed = ast.literal_eval(value)
    except (SyntaxError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]


def _salary(value: str) -> Decimal | None:
    try:
        amount = Decimal(value) * 1_000_000
    except (InvalidOperation, ValueError):
        return None
    return amount if 1_000_000 <= amount <= 200_000_000 else None


def parse_vietjobs_row(row: dict[str, str]) -> dict[str, object] | None:
    if row.get("category") != IT_CATEGORY:
        return None
    salary_min = _salary(row.get("salary_min", ""))
    salary_max = _salary(row.get("salary_max", ""))
    if salary_min is None and salary_max is None:
        return None
    title = row.get("job_title", "").strip()
    if not title:
        return None
    normalized = normalize_title(title)
    experience_min, experience_max = parse_experience_years(
        row.get("experience_required", ""), allow_bare=True
    )
    skills = _list_field(row.get("technical_skills", ""))
    identity = json.dumps(
        {
            "title": title,
            "location": row.get("location", ""),
            "experience": row.get("experience_required", ""),
            "salary_min": row.get("salary_min", ""),
            "salary_max": row.get("salary_max", ""),
            "description": row.get("description", ""),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return {
        "source": SOURCE,
        "source_record_id": hashlib.sha256(identity.encode()).hexdigest(),
        "source_snapshot_date": SOURCE_SNAPSHOT_DATE,
        "title": title,
        "title_normalized": normalized.title,
        "job_level": normalized.level,
        "location": normalize_primary_location(row.get("location", "")),
        "experience_years_min": experience_min,
        "experience_years_max": experience_max,
        "skills": skills,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "category": IT_CATEGORY,
        "source_metadata": {
            "dataset": "dinhieufam/VietJobs",
            "dataset_commit": "ea140511b77935704e93d21c2973b72f46d48902",
            "license": "MIT",
            "location_normalizer_revision": LOCATION_NORMALIZER_REVISION,
            "title_normalizer_revision": TITLE_NORMALIZER_REVISION,
        },
    }
