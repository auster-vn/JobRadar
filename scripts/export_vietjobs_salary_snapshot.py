import argparse
import csv
import json
from pathlib import Path

from api.services.vietjobs_import import parse_vietjobs_row

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


def export(source: Path, target: Path) -> int:
    observations: dict[str, dict[str, object]] = {}
    with source.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            parsed = parse_vietjobs_row(row)
            if parsed is not None:
                observations[str(parsed["source_record_id"])] = parsed

    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
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
    parser = argparse.ArgumentParser(description="Build the licensed compact salary snapshot")
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    print({"exported": export(args.source, args.target)})


if __name__ == "__main__":
    main()
