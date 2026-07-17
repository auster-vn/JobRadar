import argparse
import json
import math
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ml.salary.training import MAPE_PUBLICATION_LIMIT, MIN_TEST_ROWS


def evaluation_failures(
    payload: object,
    *,
    max_mape: float = MAPE_PUBLICATION_LIMIT,
    require_data_ready: bool = False,
    require_committed_revision: bool = False,
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

    if metrics.get("evaluation_unit") != "individual_salary_midpoint":
        failures.append("evaluation_unit must be individual_salary_midpoint")
    split_strategy = metrics.get("split_strategy")
    if not isinstance(split_strategy, str) or not split_strategy.startswith("temporal:"):
        failures.append("split_strategy must be a temporal holdout")

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
