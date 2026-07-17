import argparse
import asyncio
import csv
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from api.services.salary_observation_import import import_salary_observations
from api.services.vietjobs_import import SOURCE
from nlp.title_normalizer import TITLE_NORMALIZER_REVISION, normalize_title


def read_snapshot(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["source"] != SOURCE:
                raise ValueError(f"unexpected salary source: {row['source']}")
            normalized = normalize_title(row["title"])
            source_metadata = json.loads(row["source_metadata"])
            source_metadata["title_normalizer_revision"] = TITLE_NORMALIZER_REVISION
            rows.append(
                {
                    **row,
                    "title_normalized": normalized.title,
                    "job_level": normalized.level,
                    "source_snapshot_date": date.fromisoformat(row["source_snapshot_date"]),
                    "experience_years_min": int(row["experience_years_min"])
                    if row["experience_years_min"]
                    else None,
                    "experience_years_max": int(row["experience_years_max"])
                    if row["experience_years_max"]
                    else None,
                    "skills": json.loads(row["skills"]),
                    "salary_min": Decimal(row["salary_min"]) if row["salary_min"] else None,
                    "salary_max": Decimal(row["salary_max"]) if row["salary_max"] else None,
                    "source_metadata": source_metadata,
                }
            )
    if len(rows) != 1115:
        raise ValueError(f"expected 1115 salary observations, found {len(rows)}")
    return rows


async def main(path: Path) -> None:
    rows = read_snapshot(path)
    imported = await import_salary_observations(rows)
    print({"snapshot_rows": len(rows), "imported": imported})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import the pinned compact salary snapshot")
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    asyncio.run(main(args.path))
