import argparse
import asyncio
import csv
import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text

from api.core.database import session_factory
from nlp.location_normalizer import LOCATION_NORMALIZER_REVISION, normalize_primary_location
from nlp.title_normalizer import TITLE_NORMALIZER_REVISION, normalize_title

LICENSE = "NOASSERTION"
CATEGORY = "information_technology"
SUPPORTED_PLATFORMS = frozenset({"topcv", "vietnamworks"})
FIELDS = [
    "source",
    "source_record_id",
    "source_snapshot_date",
    "title",
    "title_normalized",
    "job_level",
    "location",
    "experience_years_min",
    "experience_years_max",
    "skills",
    "salary_min",
    "salary_max",
    "category",
    "source_metadata",
]

SNAPSHOT_SQL = """
SELECT jobs.platform_job_id, jobs.source_url, jobs.title, jobs.job_level,
  jobs.location, jobs.experience_years_min, jobs.experience_years_max,
  jobs.skills_required, jobs.salary_min, jobs.salary_max, jobs.posted_at,
  jobs.created_at, companies.name AS company_name, raw_jobs.raw_json,
  raw_jobs.scraped_at, first_batch.id AS first_seen_batch_id
FROM jobs
JOIN companies ON companies.id = jobs.company_id
JOIN raw_jobs ON raw_jobs.id = jobs.raw_job_id
JOIN LATERAL (
  SELECT scrape_batches.id
  FROM scrape_batches
  WHERE scrape_batches.platform = jobs.platform
    AND scrape_batches.status = 'completed'
    AND jobs.created_at BETWEEN scrape_batches.started_at AND scrape_batches.completed_at
  ORDER BY scrape_batches.started_at
  LIMIT 1
) AS first_batch ON true
WHERE jobs.platform = :platform
  AND jobs.created_at < :cutoff
  AND (jobs.salary_min IS NOT NULL OR jobs.salary_max IS NOT NULL)
ORDER BY jobs.platform_job_id
"""


def _prior_source_ids(paths: list[Path], platform: str) -> set[str]:
    source_ids: set[str] = set()
    for path in paths:
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if row["source"] == platform:
                    source_ids.add(row["source_record_id"])
    return source_ids


def _payload_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


async def _load_rows(platform: str, cutoff: datetime) -> list[dict[str, Any]]:
    async with session_factory() as session:
        result = await session.execute(
            text(SNAPSHOT_SQL),
            {"platform": platform, "cutoff": cutoff},
        )
        return [dict(row) for row in result.mappings()]


def _observed_on(value: object, source_record_id: str) -> date:
    if not isinstance(value, datetime):
        raise ValueError(f"{source_record_id} is missing its source posting timestamp")
    return value.date()


def export(
    target: Path,
    *,
    platform: str,
    cutoff: datetime,
    prior_snapshots: list[Path],
    expected_rows: int,
) -> int:
    if platform not in SUPPORTED_PLATFORMS:
        raise ValueError(f"unsupported operational salary platform: {platform}")
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("snapshot cutoff must include a timezone")

    prior_source_ids = _prior_source_ids(prior_snapshots, platform)
    records: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for row in asyncio.run(_load_rows(platform, cutoff)):
        source_record_id = str(row["platform_job_id"])
        if source_record_id in prior_source_ids:
            continue
        if source_record_id in seen_ids:
            raise ValueError(f"duplicate operational source record: {source_record_id}")
        seen_ids.add(source_record_id)

        raw_payload = row["raw_json"]
        location_values = row["location"]
        location = (
            normalize_primary_location(location_values[0])
            if isinstance(location_values, list) and location_values
            else None
        )
        skills = row["skills_required"]
        if not isinstance(raw_payload, dict) or not location:
            raise ValueError(f"{platform}:{source_record_id} lacks raw or location provenance")
        if not isinstance(skills, list) or not all(isinstance(skill, str) for skill in skills):
            raise ValueError(f"{platform}:{source_record_id} has invalid normalized skills")
        created_at = row["created_at"]
        scraped_at = row["scraped_at"]
        if not isinstance(created_at, datetime) or not isinstance(scraped_at, datetime):
            raise ValueError(f"{platform}:{source_record_id} lacks collection timestamps")

        title = str(row["title"])
        normalized = normalize_title(title)
        metadata = {
            "company_name": str(row["company_name"]),
            "dataset": f"jobradar/{platform}-operational-salary-snapshot",
            "dataset_commit": f"first-seen-before:{cutoff.isoformat()}",
            "dataset_url": str(row["source_url"]),
            "first_seen_at": created_at.isoformat(),
            "first_seen_batch_id": str(row["first_seen_batch_id"]),
            "license": LICENSE,
            "location_normalizer_revision": LOCATION_NORMALIZER_REVISION,
            "observation_semantics": "source posting date resolved by the JobRadar adapter",
            "platform": platform,
            "raw_payload_sha256": _payload_sha256(raw_payload),
            "scraped_at": scraped_at.isoformat(),
            "snapshot_cutoff": cutoff.isoformat(),
            "source_url": str(row["source_url"]),
            "title_normalizer_revision": TITLE_NORMALIZER_REVISION,
        }
        records.append(
            {
                "source": platform,
                "source_record_id": source_record_id,
                "source_snapshot_date": _observed_on(row["posted_at"], source_record_id),
                "title": title,
                "title_normalized": normalized.title,
                "job_level": row["job_level"] or normalized.level,
                "location": location,
                "experience_years_min": row["experience_years_min"],
                "experience_years_max": row["experience_years_max"],
                "skills": skills,
                "salary_min": row["salary_min"],
                "salary_max": row["salary_max"],
                "category": CATEGORY,
                "source_metadata": metadata,
            }
        )

    if len(records) != expected_rows:
        raise ValueError(
            f"expected {expected_rows} new {platform} salary rows, found {len(records)}"
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in records:
            serialized = row.copy()
            serialized["skills"] = json.dumps(
                serialized["skills"], ensure_ascii=False, separators=(",", ":")
            )
            serialized["source_metadata"] = json.dumps(
                serialized["source_metadata"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            writer.writerow(serialized)
    return len(records)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Freeze pre-holdout salary observations from an operational source"
    )
    parser.add_argument("target", type=Path)
    parser.add_argument("--platform", choices=sorted(SUPPORTED_PLATFORMS), required=True)
    parser.add_argument("--cutoff", type=datetime.fromisoformat, required=True)
    parser.add_argument("--prior-snapshot", action="append", type=Path, default=[])
    parser.add_argument("--expected-rows", type=int, required=True)
    args = parser.parse_args()
    exported = export(
        args.target,
        platform=args.platform,
        cutoff=args.cutoff,
        prior_snapshots=args.prior_snapshot,
        expected_rows=args.expected_rows,
    )
    print({"platform": args.platform, "exported": exported})


if __name__ == "__main__":
    main()
