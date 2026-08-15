import re
from datetime import date
from decimal import Decimal
from urllib.parse import urlsplit

from nlp.experience_parser import parse_experience_years
from nlp.location_normalizer import LOCATION_NORMALIZER_REVISION, normalize_primary_location
from nlp.salary_parser import USD_TO_VND, parse_salary
from nlp.title_normalizer import TITLE_NORMALIZER_REVISION, normalize_title

SOURCE = "topcv"
DATASET = "baocgb/vietnam-it-jobs-raw-data-from-topcv-2026"
DATASET_URL = "https://www.kaggle.com/datasets/baocgb/vietnam-it-jobs-raw-data-from-topcv-2026"
DATASET_VERSION = "1"
RAW_SHA256 = "e78ff2b6ed521ad894a70271a3254fcf434813916fdade4f7d449bc4fdf34ef9"
DATASET_REVISION = f"kaggle-9263561-v{DATASET_VERSION}:{RAW_SHA256}"
LICENSE = "CC-BY-4.0"
CATEGORY = "information_technology"

_JOB_PATH = re.compile(
    r"^/(?:viec-lam/[^/]+/(?P<listing_id>[0-9]+)"
    r"|brand/[^/]+/tuyen-dung/[^/]+-j(?P<brand_id>[0-9]+))\.html$"
)
_MIN_SALARY = 1_000_000
_MAX_SALARY = 200_000_000


def _job_identity(value: str) -> tuple[str, str] | None:
    parsed = urlsplit(value.strip())
    hostname = (parsed.hostname or "").casefold()
    match = _JOB_PATH.fullmatch(parsed.path)
    if parsed.scheme != "https" or not (hostname == "topcv.vn" or hostname.endswith(".topcv.vn")):
        return None
    if match is None:
        return None
    job_id = match.group("listing_id") or match.group("brand_id")
    return job_id, f"https://www.topcv.vn{parsed.path}"


def parse_topcv_salary_row(row: dict[str, str]) -> dict[str, object] | None:
    identity = _job_identity(row.get("url", ""))
    if identity is None:
        return None
    source_record_id, source_url = identity

    title = re.sub(r"\s+", " ", row.get("title", "")).strip()
    if not title:
        return None
    try:
        observed_on = date.fromisoformat(row.get("date_posted", ""))
    except ValueError:
        return None

    parsed_salary = parse_salary(row.get("salary"))
    salary_values = [
        value for value in (parsed_salary.min_vnd, parsed_salary.max_vnd) if value is not None
    ]
    if not salary_values or any(
        value < _MIN_SALARY or value > _MAX_SALARY for value in salary_values
    ):
        return None

    normalized_title = normalize_title(title)
    experience_min, experience_max = parse_experience_years(row.get("experience"), allow_bare=True)
    metadata: dict[str, object] = {
        "dataset": DATASET,
        "dataset_commit": DATASET_REVISION,
        "dataset_url": DATASET_URL,
        "dataset_version": DATASET_VERSION,
        "license": LICENSE,
        "location_normalizer_revision": LOCATION_NORMALIZER_REVISION,
        "raw_sha256": RAW_SHA256,
        "salary_source_currency": parsed_salary.source_currency,
        "source_url": source_url,
        "title_normalizer_revision": TITLE_NORMALIZER_REVISION,
    }
    if parsed_salary.source_currency == "USD":
        metadata["usd_to_vnd"] = str(USD_TO_VND)

    return {
        "source": SOURCE,
        "source_record_id": source_record_id,
        "source_snapshot_date": observed_on,
        "title": title,
        "title_normalized": normalized_title.title,
        "job_level": normalized_title.level,
        "location": normalize_primary_location(row.get("location")),
        "experience_years_min": experience_min,
        "experience_years_max": experience_max,
        "skills": [],
        "salary_min": Decimal(parsed_salary.min_vnd) if parsed_salary.min_vnd is not None else None,
        "salary_max": Decimal(parsed_salary.max_vnd) if parsed_salary.max_vnd is not None else None,
        "category": CATEGORY,
        "source_metadata": metadata,
    }
