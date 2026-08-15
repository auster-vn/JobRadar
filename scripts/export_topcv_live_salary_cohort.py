import argparse
import asyncio
import csv
import hashlib
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text

from api.core.database import session_factory
from api.services.topcv_salary_import import SOURCE
from nlp.location_normalizer import LOCATION_NORMALIZER_REVISION, normalize_primary_location
from nlp.title_normalizer import TITLE_NORMALIZER_REVISION, normalize_title

DATASET = "jobradar/topcv-live-card-cohort"
DATASET_URL = "https://www.topcv.vn/tim-viec-lam-cong-nghe-thong-tin"
LICENSE = "NOASSERTION"
CATEGORY = "information_technology"
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

COHORT_SQL = """
SELECT jobs.platform_job_id, jobs.source_url, jobs.title, jobs.job_level,
  jobs.location, jobs.experience_years_min, jobs.experience_years_max,
  jobs.skills_required, jobs.salary_min, jobs.salary_max, jobs.posted_at,
  jobs.created_at, companies.name AS company_name, raw_jobs.raw_json,
  raw_jobs.scraped_at
FROM jobs
JOIN companies ON companies.id = jobs.company_id
JOIN raw_jobs ON raw_jobs.id = jobs.raw_job_id
WHERE jobs.platform = 'topcv'
  AND jobs.created_at >= :cutoff
  AND (jobs.salary_min IS NOT NULL OR jobs.salary_max IS NOT NULL)
ORDER BY jobs.platform_job_id
"""


def _prior_source_ids(paths: list[Path]) -> set[str]:
    source_ids: set[str] = set()
    for path in paths:
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if row["source"] == SOURCE:
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


async def _load_rows(cutoff: datetime, batch_id: uuid.UUID) -> tuple[list[dict[str, Any]], str]:
    async with session_factory() as session:
        batch = (
            (
                await session.execute(
                    text(
                        """
                    SELECT status, platform, completed_at
                    FROM scrape_batches WHERE id = :batch_id
                    """
                    ),
                    {"batch_id": batch_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if batch is None or batch["platform"] != "topcv" or batch["status"] != "completed":
            raise ValueError("cohort batch must be a completed TopCV scrape")
        result = await session.execute(text(COHORT_SQL), {"cutoff": cutoff})
        return [dict(row) for row in result.mappings()], batch["completed_at"].isoformat()


def export(
    target: Path,
    manifest: Path,
    *,
    cutoff: datetime,
    batch_id: uuid.UUID,
    prior_snapshots: list[Path],
    expected_rows: int,
) -> int:
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("cohort cutoff must include a timezone")
    prior_source_ids = _prior_source_ids(prior_snapshots)
    raw_rows, completed_at = asyncio.run(_load_rows(cutoff, batch_id))
    records: list[dict[str, object]] = []
    for row in raw_rows:
        source_record_id = str(row["platform_job_id"])
        if source_record_id in prior_source_ids:
            continue
        raw_payload = row["raw_json"]
        if not isinstance(raw_payload, dict) or row["posted_at"] is None:
            raise ValueError(f"TopCV cohort row {source_record_id} lacks raw provenance")
        normalized = normalize_title(str(row["title"]))
        raw_sha256 = _payload_sha256(raw_payload)
        metadata = {
            "company_name": row["company_name"],
            "dataset": DATASET,
            "dataset_commit": f"scrape-batch:{batch_id}",
            "dataset_url": DATASET_URL,
            "first_seen_cutoff": cutoff.isoformat(),
            "license": LICENSE,
            "location_normalizer_revision": LOCATION_NORMALIZER_REVISION,
            "observation_semantics": "TopCV relative posting age resolved at collection time",
            "raw_payload_sha256": raw_sha256,
            "scrape_batch_id": str(batch_id),
            "scraped_at": row["scraped_at"].isoformat(),
            "source_url": row["source_url"],
            "title_normalizer_revision": TITLE_NORMALIZER_REVISION,
        }
        records.append(
            {
                "source": SOURCE,
                "source_record_id": source_record_id,
                "source_snapshot_date": row["posted_at"].date(),
                "title": row["title"],
                "title_normalized": normalized.title,
                "job_level": row["job_level"] or normalized.level,
                "location": normalize_primary_location((row["location"] or [""])[0]),
                "experience_years_min": row["experience_years_min"],
                "experience_years_max": row["experience_years_max"],
                "skills": row["skills_required"] or [],
                "salary_min": row["salary_min"],
                "salary_max": row["salary_max"],
                "category": CATEGORY,
                "source_metadata": metadata,
            }
        )
    if len(records) != expected_rows:
        raise ValueError(f"expected {expected_rows} new TopCV salary rows, found {len(records)}")

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

    snapshot_sha256 = hashlib.sha256(target.read_bytes()).hexdigest()
    source_keys = [f"{SOURCE}:{row['source_record_id']}" for row in records]
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        f"{
            json.dumps(
                {
                    'schema_version': 1,
                    'cohort_id': 'topcv-it-first-seen-2026-07-19',
                    'platform': SOURCE,
                    'dataset_url': DATASET_URL,
                    'first_seen_at': cutoff.isoformat(),
                    'collection_completed_at': completed_at,
                    'scrape_batch_id': str(batch_id),
                    'snapshot': target.name,
                    'snapshot_sha256': snapshot_sha256,
                    'source_key_count': len(source_keys),
                    'source_keys': source_keys,
                },
                ensure_ascii=False,
                indent=2,
            )
        }\n",
        encoding="utf-8",
    )
    return len(records)


def main() -> None:
    parser = argparse.ArgumentParser(description="Freeze a first-seen TopCV salary cohort")
    parser.add_argument("target", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--cutoff", type=datetime.fromisoformat, required=True)
    parser.add_argument("--batch-id", type=uuid.UUID, required=True)
    parser.add_argument("--prior-snapshot", action="append", type=Path, default=[])
    parser.add_argument("--expected-rows", type=int, required=True)
    args = parser.parse_args()
    exported = export(
        args.target,
        args.manifest,
        cutoff=args.cutoff,
        batch_id=args.batch_id,
        prior_snapshots=args.prior_snapshot,
        expected_rows=args.expected_rows,
    )
    print({"exported": exported})


if __name__ == "__main__":
    main()
