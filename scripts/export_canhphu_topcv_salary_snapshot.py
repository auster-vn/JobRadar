import argparse
import csv
import hashlib
import json
from datetime import date
from pathlib import Path

from api.services.canhphu_topcv_salary_import import (
    RAW_SNAPSHOT_SHA256,
    parse_canhphu_topcv_salary_row,
)

csv.field_size_limit(20_000_000)

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


def _verify_raw_source(path: Path, expected_sha256: str) -> None:
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected_sha256:
        raise ValueError(
            f"TopCV archive SHA256 mismatch for {path.name}: "
            f"expected {expected_sha256}, found {actual}"
        )


def _snapshot_date(filename: str) -> date:
    return date.fromisoformat(filename.removeprefix("topcv_").removesuffix(".csv"))


def _observation_date(record: dict[str, object]) -> date:
    value = record.get("source_snapshot_date")
    if not isinstance(value, date):
        raise ValueError("parsed TopCV archive row is missing its observation date")
    return value


def export(source_directory: Path, target: Path) -> int:
    observations: dict[str, dict[str, object]] = {}
    for filename, raw_sha256 in sorted(RAW_SNAPSHOT_SHA256.items()):
        source = source_directory / filename
        if not source.is_file():
            raise ValueError(f"missing pinned TopCV archive: {source}")
        _verify_raw_source(source, raw_sha256)
        observed_on = _snapshot_date(filename)
        with source.open(encoding="utf-8-sig", newline="") as handle:
            for raw_row in csv.DictReader(handle):
                parsed = parse_canhphu_topcv_salary_row(
                    raw_row,
                    observed_on=observed_on,
                    raw_filename=filename,
                    raw_sha256=raw_sha256,
                )
                if parsed is None:
                    continue
                record_id = str(parsed["source_record_id"])
                current = observations.get(record_id)
                if current is None or _observation_date(parsed) < _observation_date(current):
                    observations[record_id] = parsed

    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        for record_id in sorted(observations):
            row = observations[record_id].copy()
            row["skills"] = json.dumps(row["skills"], ensure_ascii=False, separators=(",", ":"))
            row["source_metadata"] = json.dumps(
                row["source_metadata"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            writer.writerow(row)
    return len(observations)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the pinned TopCV archive salary snapshot")
    parser.add_argument("source_directory", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    print({"exported": export(args.source_directory, args.target)})


if __name__ == "__main__":
    main()
