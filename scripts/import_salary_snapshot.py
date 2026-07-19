import argparse
import asyncio
import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from api.services.salary_observation_import import import_salary_observations
from api.services.topcv_salary_import import SOURCE as TOPCV_SOURCE
from api.services.vietjobs_import import SOURCE as VIETJOBS_SOURCE
from nlp.location_normalizer import LOCATION_NORMALIZER_REVISION, normalize_primary_location
from nlp.title_normalizer import TITLE_NORMALIZER_REVISION, normalize_title


@dataclass(frozen=True, slots=True)
class SnapshotContract:
    source: str
    rows: int
    sha256: str


SNAPSHOT_CONTRACTS = {
    "topcv_2026_it_salary_observations.csv": SnapshotContract(
        source=TOPCV_SOURCE,
        rows=818,
        sha256="977b7da686d78e507b8424a28210d7746bfb3bb20acec1e0920cc1165de1be4e",
    ),
    "vietjobs_it_salary_observations.csv": SnapshotContract(
        source=VIETJOBS_SOURCE,
        rows=1115,
        sha256="f823fdb009c69ff9a2e8a367497936fcd7001adcfa60bc4dc0784d6c55ff357c",
    ),
}


def _contract(path: Path) -> SnapshotContract:
    try:
        contract = SNAPSHOT_CONTRACTS[path.name]
    except KeyError as exc:
        raise ValueError(f"unapproved salary snapshot: {path.name}") from exc
    actual_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual_sha256 != contract.sha256:
        raise ValueError(
            f"salary snapshot SHA256 mismatch for {path.name}: "
            f"expected {contract.sha256}, found {actual_sha256}"
        )
    return contract


def _optional_int(value: str) -> int | None:
    return int(value) if value else None


def _optional_decimal(value: str) -> Decimal | None:
    return Decimal(value) if value else None


def read_snapshot(path: Path) -> list[dict[str, object]]:
    contract = _contract(path)
    rows: list[dict[str, object]] = []
    source_ids: set[str] = set()
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["source"] != contract.source:
                raise ValueError(f"unexpected salary source: {row['source']}")
            source_record_id = row["source_record_id"]
            if source_record_id in source_ids:
                raise ValueError(f"duplicate salary source record: {source_record_id}")
            source_ids.add(source_record_id)

            normalized = normalize_title(row["title"])
            source_metadata = json.loads(row["source_metadata"])
            if not isinstance(source_metadata, dict):
                raise ValueError(f"invalid source metadata for {source_record_id}")
            source_metadata["location_normalizer_revision"] = LOCATION_NORMALIZER_REVISION
            source_metadata["title_normalizer_revision"] = TITLE_NORMALIZER_REVISION
            salary_min = _optional_decimal(row["salary_min"])
            salary_max = _optional_decimal(row["salary_max"])
            salary_values = [value for value in (salary_min, salary_max) if value is not None]
            if not salary_values or any(
                value < 1_000_000 or value > 200_000_000 for value in salary_values
            ):
                raise ValueError(f"salary outside the model contract for {source_record_id}")
            rows.append(
                {
                    **row,
                    "title_normalized": normalized.title,
                    "job_level": normalized.level,
                    "location": normalize_primary_location(row["location"]),
                    "source_snapshot_date": date.fromisoformat(row["source_snapshot_date"]),
                    "experience_years_min": _optional_int(row["experience_years_min"]),
                    "experience_years_max": _optional_int(row["experience_years_max"]),
                    "skills": json.loads(row["skills"]),
                    "salary_min": salary_min,
                    "salary_max": salary_max,
                    "source_metadata": source_metadata,
                }
            )
    if len(rows) != contract.rows:
        raise ValueError(
            f"expected {contract.rows} salary observations in {path.name}, found {len(rows)}"
        )
    return rows


async def main(paths: list[Path]) -> None:
    rows = [row for path in paths for row in read_snapshot(path)]
    source_keys = [(str(row["source"]), str(row["source_record_id"])) for row in rows]
    if len(source_keys) != len(set(source_keys)):
        raise ValueError("salary snapshots contain duplicate source keys")
    imported = await import_salary_observations(rows)
    print({"snapshots": len(paths), "snapshot_rows": len(rows), "imported": imported})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import provenance-pinned salary snapshots")
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    asyncio.run(main(args.paths))
