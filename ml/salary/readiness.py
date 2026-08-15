from collections import defaultdict
from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

from nlp.location_normalizer import normalize_location
from nlp.title_normalizer import canonical_role

MIN_DISTINCT_MONTHS = 6
MIN_CANONICAL_TECHNICAL_ROWS = 1_000
MIN_SEGMENT_ROWS = 30
MIN_SEGMENT_MONTHS = 3
MIN_SUPPORTED_SEGMENTS = 5
MIN_FINAL_MONTH_ROWS = 200
PRIMARY_CITIES = frozenset({"Ha Noi", "Ho Chi Minh", "Da Nang"})


def _date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise ValueError("salary row is missing a valid source_snapshot_date")


def _month(value: object) -> str:
    observed_on = _date(value)
    return f"{observed_on.year:04d}-{observed_on.month:02d}"


def assess_salary_data_readiness(
    rows: Sequence[dict[str, Any]],
    *,
    segment_rows: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    months = {_month(row.get("source_snapshot_date")) for row in rows}
    source_keys = [str(row.get("source_key") or "") for row in rows]
    duplicate_source_keys = len(source_keys) - len(set(source_keys))
    non_vnd_rows = sum(str(row.get("salary_currency") or "VND").upper() != "VND" for row in rows)

    canonical_rows = 0
    segments: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(
        lambda: {"row_count": 0, "months": set()}
    )
    for row in rows if segment_rows is None else segment_rows:
        role = canonical_role(row.get("title_normalized"))
        if role is None:
            continue
        canonical_rows += 1
        location = normalize_location(str(row.get("location") or "")) or ""
        if location not in PRIMARY_CITIES:
            continue
        key = (role, str(row.get("job_level") or "mid"), location)
        segments[key]["row_count"] += 1
        segments[key]["months"].add(_month(row.get("source_snapshot_date")))

    segment_details = [
        {
            "role": role,
            "level": level,
            "location": location,
            "row_count": values["row_count"],
            "distinct_months": len(values["months"]),
            "ready": values["row_count"] >= MIN_SEGMENT_ROWS
            and len(values["months"]) >= MIN_SEGMENT_MONTHS,
        }
        for (role, level, location), values in sorted(segments.items())
    ]
    supported_segments = [segment for segment in segment_details if segment["ready"]]
    underqualified_segments = [segment for segment in segment_details if not segment["ready"]]
    final_month = max(months) if months else None
    final_month_rows = (
        sum(_month(row.get("source_snapshot_date")) == final_month for row in rows)
        if final_month
        else 0
    )

    requirements = [
        {
            "id": "distinct_months",
            "actual": len(months),
            "target": MIN_DISTINCT_MONTHS,
            "passed": len(months) >= MIN_DISTINCT_MONTHS,
        },
        {
            "id": "canonical_technical_rows",
            "actual": canonical_rows,
            "target": MIN_CANONICAL_TECHNICAL_ROWS,
            "passed": canonical_rows >= MIN_CANONICAL_TECHNICAL_ROWS,
        },
        {
            "id": "supported_segments",
            "actual": len(supported_segments),
            "target": MIN_SUPPORTED_SEGMENTS,
            "passed": len(supported_segments) >= MIN_SUPPORTED_SEGMENTS,
        },
        {
            "id": "final_month_rows",
            "actual": final_month_rows,
            "target": MIN_FINAL_MONTH_ROWS,
            "passed": final_month_rows >= MIN_FINAL_MONTH_ROWS,
        },
        {
            "id": "duplicate_source_keys",
            "actual": duplicate_source_keys,
            "target": 0,
            "passed": duplicate_source_keys == 0,
        },
        {
            "id": "non_vnd_rows",
            "actual": non_vnd_rows,
            "target": 0,
            "passed": non_vnd_rows == 0,
        },
    ]
    return {
        "ready": all(requirement["passed"] for requirement in requirements),
        "sample_size": len(rows),
        "distinct_months": len(months),
        "canonical_technical_rows": canonical_rows,
        "final_month": final_month,
        "final_month_rows": final_month_rows,
        "duplicate_source_keys": duplicate_source_keys,
        "non_vnd_rows": non_vnd_rows,
        "qualified_segments": len(segment_details) - len(underqualified_segments),
        "segment_candidates": len(segment_details),
        "supported_segments": supported_segments,
        "underqualified_segments": underqualified_segments,
        "requirements": requirements,
    }
