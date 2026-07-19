import argparse
import json
import math
import re
import shutil
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from ml.salary.training import (
    EVALUATION_UNIT,
    MAPE_PUBLICATION_LIMIT,
    MIN_BENCHMARK_SEGMENT_ROWS,
    MIN_TEST_ROWS,
    MIN_TEST_SEGMENTS,
)

PROJECT_ROOT = Path(__file__).parents[2]


def _revision_is_reachable(source_revision: str) -> bool:
    git = shutil.which("git")
    if git is None:
        return False
    try:
        result = subprocess.run(  # noqa: S603 - revision is validated as a hexadecimal SHA
            [git, "merge-base", "--is-ancestor", source_revision, "HEAD"],
            cwd=PROJECT_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def evaluation_failures(
    payload: object,
    *,
    max_mape: float = MAPE_PUBLICATION_LIMIT,
    require_data_ready: bool = False,
    require_committed_revision: bool = False,
    revision_is_committed: Callable[[str], bool] | None = None,
) -> list[str]:
    if not math.isfinite(max_mape) or not 0 < max_mape <= 1:
        raise ValueError("max_mape must be finite and within (0, 1]")
    if not isinstance(payload, dict):
        return ["evaluation payload must be a JSON object"]

    raw_metrics = payload.get("metrics", payload)
    if not isinstance(raw_metrics, dict):
        return ["metrics must be a JSON object"]
    metrics: dict[str, Any] = raw_metrics
    failures: list[str] = []

    if payload.get("status") != "published":
        failures.append("status must be published")
    failed_gates = payload.get("failed_gates")
    if failed_gates != []:
        failures.append("failed_gates must be empty")

    numeric: dict[str, float] = {}
    for key in ("test_mape", "test_mae", "test_r2"):
        try:
            raw_value = metrics[key]
            if isinstance(raw_value, bool):
                raise TypeError
            value = float(raw_value)
        except (KeyError, TypeError, ValueError):
            failures.append(f"{key} must be numeric")
            continue
        if not math.isfinite(value):
            failures.append(f"{key} must be finite")
            continue
        numeric[key] = value

    if numeric.get("test_mape", 0) < 0:
        failures.append("test_mape must be non-negative")
    elif numeric.get("test_mape", 0) > max_mape:
        failures.append(f"test_mape exceeds {max_mape:.4f}")
    if numeric.get("test_mae", 0) < 0:
        failures.append("test_mae must be non-negative")

    test_size = metrics.get("test_size")
    if isinstance(test_size, bool) or not isinstance(test_size, int):
        failures.append("test_size must be an integer")
    elif test_size < MIN_TEST_ROWS:
        failures.append(f"test_size must be at least {MIN_TEST_ROWS}")

    test_segment_count = metrics.get("test_segment_count")
    if isinstance(test_segment_count, bool) or not isinstance(test_segment_count, int):
        failures.append("test_segment_count must be an integer")
    elif test_segment_count < MIN_TEST_SEGMENTS:
        failures.append(f"test_segment_count must be at least {MIN_TEST_SEGMENTS}")
    if metrics.get("minimum_segment_rows") != MIN_BENCHMARK_SEGMENT_ROWS:
        failures.append(f"minimum_segment_rows must be {MIN_BENCHMARK_SEGMENT_ROWS}")

    if metrics.get("evaluation_unit") != EVALUATION_UNIT:
        failures.append(f"evaluation_unit must be {EVALUATION_UNIT}")
    split_strategy = metrics.get("split_strategy")
    if not isinstance(split_strategy, str) or not split_strategy.startswith("temporal:"):
        failures.append("split_strategy must be a temporal holdout")
    holdout_cohort = metrics.get("holdout_cohort")
    if not isinstance(holdout_cohort, str) or not holdout_cohort:
        failures.append("holdout_cohort must be non-empty")
    manifest_sha256 = metrics.get("holdout_manifest_sha256")
    if (
        not isinstance(manifest_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", manifest_sha256) is None
    ):
        failures.append("holdout_manifest_sha256 must be a 64-character SHA256")

    if require_data_ready:
        readiness = payload.get("data_readiness")
        if not isinstance(readiness, dict) or readiness.get("ready") is not True:
            failures.append("data_readiness must pass")
    if require_committed_revision:
        source_revision = payload.get("source_revision")
        if (
            not isinstance(source_revision, str)
            or re.fullmatch(r"[0-9a-f]{40}", source_revision) is None
        ):
            failures.append("source_revision must be a 40-character Git commit SHA")
        else:
            revision_check = revision_is_committed or _revision_is_reachable
            if not revision_check(source_revision):
                failures.append("source_revision must identify a Git commit reachable from HEAD")
    return failures


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enforce the salary model MAPE gate")
    parser.add_argument("metrics", type=Path)
    parser.add_argument("--max-mape", type=float, default=MAPE_PUBLICATION_LIMIT)
    parser.add_argument("--require-data-ready", action="store_true")
    parser.add_argument("--require-committed-revision", action="store_true")
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.metrics.read_text(encoding="utf-8"))
        failures = evaluation_failures(
            payload,
            max_mape=args.max_mape,
            require_data_ready=args.require_data_ready,
            require_committed_revision=args.require_committed_revision,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        parser.error(str(exc))

    if isinstance(payload, dict) and isinstance(payload.get("metrics", payload), dict):
        mape = payload.get("metrics", payload).get("test_mape")
        print(f"MAPE={mape}; limit={args.max_mape:.4f}")
    for failure in failures:
        print(f"FAIL: {failure}")
    if not failures:
        print("PASS: salary evaluation meets every requested gate")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
