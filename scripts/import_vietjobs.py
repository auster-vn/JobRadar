import argparse
import asyncio
import csv
from pathlib import Path

from api.services.salary_observation_import import import_salary_observations
from api.services.vietjobs_import import parse_vietjobs_row


async def import_dataset(path: Path) -> dict[str, int]:
    parsed: list[dict[str, object]] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            observation = parse_vietjobs_row(row)
            if observation is not None:
                parsed.append(observation)

    imported = await import_salary_observations(parsed)
    return {"eligible": len(parsed), "imported": imported}


def main() -> None:
    parser = argparse.ArgumentParser(description="Import licensed VietJobs salary observations")
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    if not args.path.is_file():
        raise FileNotFoundError(args.path)
    print(asyncio.run(import_dataset(args.path)))


if __name__ == "__main__":
    main()
