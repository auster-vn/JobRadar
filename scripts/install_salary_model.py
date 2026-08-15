import argparse
import json
import math
import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from ml.salary.training import MAPE_PUBLICATION_LIMIT
from ml.serving import REQUIRED_ARTIFACTS


def _metadata(bundle: Path, expected_revision: str) -> dict[str, Any]:
    missing = sorted(name for name in REQUIRED_ARTIFACTS if not (bundle / name).is_file())
    if missing:
        raise ValueError(f"salary model bundle is missing: {', '.join(missing)}")
    payload = json.loads((bundle / "metadata.json").read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("salary model metadata must be a JSON object")
    if payload.get("status") != "published" or payload.get("failed_gates") != []:
        raise ValueError("salary model bundle is not published")
    if payload.get("source_revision") != expected_revision:
        raise ValueError("salary model source revision does not match the runtime image")
    metrics = payload.get("metrics")
    if not isinstance(metrics, dict):
        raise ValueError("salary model metrics are missing")
    try:
        mape = float(metrics["test_mape"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("salary model MAPE is invalid") from exc
    if not math.isfinite(mape) or not 0 <= mape <= MAPE_PUBLICATION_LIMIT:
        raise ValueError("salary model MAPE does not pass publication")
    readiness = payload.get("data_readiness")
    if not isinstance(readiness, dict) or readiness.get("ready") is not True:
        raise ValueError("salary model data readiness does not pass publication")
    return payload


def install(seed: Path, target: Path, *, expected_revision: str, required: bool) -> bool:
    if re.fullmatch(r"[0-9a-f]{40}", expected_revision) is None:
        if required:
            raise ValueError("SOURCE_REVISION must be a 40-character Git SHA")
        print("No release-bound salary model requested for this development image")
        return False
    if not seed.is_dir():
        if required:
            raise ValueError(f"required salary model seed is missing: {seed}")
        print(f"No salary model seed found at {seed}")
        return False

    _metadata(seed, expected_revision)
    if target.is_dir():
        _metadata(target, expected_revision)
        print(f"Salary model for {expected_revision} is already installed at {target}")
        return True

    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.parent / f".{target.name}.{uuid.uuid4().hex}.tmp"
    try:
        shutil.copytree(seed, staging)
        _metadata(staging, expected_revision)
        staging.replace(target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    print(f"Installed salary model for {expected_revision} at {target}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Install an immutable release salary model")
    parser.add_argument("seed", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    required = os.getenv("REQUIRE_SALARY_MODEL", "false").casefold() == "true"
    install(
        args.seed,
        args.target,
        expected_revision=os.getenv("SOURCE_REVISION", "local"),
        required=required,
    )


if __name__ == "__main__":
    main()
