import ast
import hashlib
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from nlp.location_normalizer import LOCATION_NORMALIZER_REVISION, normalize_primary_location
from nlp.salary_parser import USD_TO_VND
from nlp.skill_extractor import extract_skills
from nlp.title_normalizer import TITLE_NORMALIZER_REVISION, normalize_title

SOURCE = "topcv_archive"
DATASET = "canhphu/job_prediction"
DATASET_URL = "https://github.com/canhphu/job_prediction"
DATASET_REVISION = "5cce1ddf501ae3e8ddfce046f3b82a1990570eeb"
LICENSE = "NOASSERTION"
CATEGORY = "information_technology"

RAW_SNAPSHOT_SHA256 = {
    "topcv_2026-05-18.csv": "659194c031721802bda0953b8e7377909f54e1a02f0a23714e4039754c5b03ee",
    "topcv_2026-05-22.csv": "f55b1d097d0cc2a0e0e361001311c5b85a1769b6e2cf79b74529d10bf3af6d93",
    "topcv_2026-05-28.csv": "0fdb0e2227adc7fff7a9a86f9b35617cd1b49f517e43626fbc8a225db9128ae4",
    "topcv_2026-06-02.csv": "626911361e49e313006db93e323739136de1edeeef2da643e1ad80115a793208",
    "topcv_2026-06-08.csv": "c6b186acdfd85f77ebeb6b04b2258c8e956309363794c943b4b2cfaba5500394",
    "topcv_2026-06-15.csv": "b280a7d9b2cd4b4a50f18313f72b2256c6153eaeb3c6f1e0befa46554255d866",
    "topcv_2026-06-21.csv": "442f1c359e6bf920f19637258629194e73f0986828629cffb10a9e9c5b98e9b7",
}

_MIN_SALARY = Decimal("1000000")
_MAX_SALARY = Decimal("200000000")
_MAX_USD_SALARY = Decimal("8000")
_MIN_USD_SALARY = Decimal("40")


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _natural_identity(title: str, company: str, location: str) -> tuple[str, str]:
    normalized_location = normalize_primary_location(location) or ""
    payload = json.dumps(
        {
            "company": _clean(company).casefold(),
            "location": normalized_location.casefold(),
            "title": _clean(title).casefold(),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode()).hexdigest()
    return f"canhphu-{digest[:48]}", digest


def _amount(value: object, currency: str) -> Decimal | None:
    if value is None or not str(value).strip():
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None

    if currency == "VND":
        if Decimal("1") <= amount <= Decimal("200"):
            amount *= Decimal("1000000")
        elif not (_MIN_SALARY <= amount <= _MAX_SALARY):
            return None
    elif currency == "USD":
        if not (_MIN_USD_SALARY <= amount <= _MAX_USD_SALARY):
            return None
        amount *= USD_TO_VND
    else:
        return None
    return amount if _MIN_SALARY <= amount <= _MAX_SALARY else None


def _experience(value: object) -> int | None:
    if value is None or not str(value).strip():
        return None
    try:
        years = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if years != years.to_integral_value() or not (0 <= years <= 60):
        return None
    return int(years)


def _skill_text(value: object) -> str:
    try:
        parsed = ast.literal_eval(str(value or "[]"))
    except (SyntaxError, ValueError):
        return ""
    if not isinstance(parsed, list):
        return ""
    return " | ".join(_clean(item) for item in parsed if _clean(item))


def parse_canhphu_topcv_salary_row(
    row: dict[str, str],
    *,
    observed_on: date,
    raw_filename: str,
    raw_sha256: str,
) -> dict[str, object] | None:
    if _clean(row.get("source")).casefold() != "topcv":
        return None
    if row.get("posted_date") != observed_on.isoformat():
        return None

    title = _clean(row.get("job_title"))
    company = _clean(row.get("company_name"))
    location = normalize_primary_location(row.get("location"))
    if not title or not company or not location:
        return None

    currency = _clean(row.get("salary_currency")).upper()
    salary_min = _amount(row.get("salary_min"), currency)
    salary_max = _amount(row.get("salary_max"), currency)
    if salary_min is None and salary_max is None:
        return None
    if salary_min is not None and salary_max is not None and salary_min > salary_max:
        return None

    source_record_id, identity_sha256 = _natural_identity(title, company, location)
    normalized = normalize_title(title)
    experience = _experience(row.get("experience_required"))
    skill_text = " | ".join(filter(None, (title, _skill_text(row.get("skills")))))
    metadata: dict[str, object] = {
        "company_name": company,
        "dataset": DATASET,
        "dataset_commit": DATASET_REVISION,
        "dataset_url": DATASET_URL,
        "identity_method": "sha256(casefolded title, company, primary location)",
        "identity_sha256": identity_sha256,
        "license": LICENSE,
        "location_normalizer_revision": LOCATION_NORMALIZER_REVISION,
        "observation_semantics": "crawler run date",
        "platform": "topcv",
        "raw_filename": raw_filename,
        "raw_sha256": raw_sha256,
        "salary_source_currency": currency,
        "title_normalizer_revision": TITLE_NORMALIZER_REVISION,
    }
    if currency == "USD":
        metadata["usd_to_vnd"] = str(USD_TO_VND)

    return {
        "source": SOURCE,
        "source_record_id": source_record_id,
        "source_snapshot_date": observed_on,
        "title": title,
        "title_normalized": normalized.title,
        "job_level": normalized.level,
        "location": location,
        "experience_years_min": experience,
        "experience_years_max": experience,
        "skills": extract_skills(skill_text).required,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "category": CATEGORY,
        "source_metadata": metadata,
    }
