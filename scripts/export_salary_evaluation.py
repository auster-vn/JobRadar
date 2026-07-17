import argparse
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

METRIC_KEYS = (
    "test_mape",
    "test_mae",
    "test_r2",
    "baseline_mape",
    "interval_coverage",
    "train_size",
    "test_size",
    "split_strategy",
    "evaluation_unit",
    "train_period_start",
    "train_period_end",
    "test_period_start",
    "test_period_end",
    "trained_at",
)
DIAGNOSTIC_KEYS = (
    "within_15pct_rate",
    "p90_absolute_percentage_error",
    "median_percentage_bias",
    "target_median",
    "prediction_median",
    "unseen_title_rate",
    "unseen_location_rate",
)
READINESS_KEYS = (
    "ready",
    "sample_size",
    "distinct_months",
    "canonical_technical_rows",
    "final_month",
    "final_month_rows",
    "duplicate_source_keys",
    "non_vnd_rows",
    "qualified_segments",
    "segment_candidates",
)


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")
    return value


def _select(source: Mapping[str, Any], keys: Sequence[str], name: str) -> dict[str, Any]:
    missing = [key for key in keys if key not in source]
    if missing:
        raise ValueError(f"{name} is missing: {', '.join(missing)}")
    return {key: source[key] for key in keys}


def build_evidence(metadata_bytes: bytes, *, run_id: str, source_revision: str) -> dict[str, Any]:
    if re.fullmatch(r"[0-9a-f]{32}", run_id) is None:
        raise ValueError("run_id must be a 32-character lowercase MLflow ID")
    if re.fullmatch(r"[A-Za-z0-9._-]+", source_revision) is None:
        raise ValueError("source_revision contains unsupported characters")

    try:
        metadata = _mapping(json.loads(metadata_bytes), "metadata")
    except json.JSONDecodeError as exc:
        raise ValueError(f"metadata is not valid JSON: {exc.msg}") from exc
    metrics = _select(_mapping(metadata.get("metrics"), "metrics"), METRIC_KEYS, "metrics")
    diagnostics = _select(
        _mapping(metadata.get("evaluation_diagnostics"), "evaluation_diagnostics"),
        DIAGNOSTIC_KEYS,
        "evaluation_diagnostics",
    )
    readiness_source = _mapping(metadata.get("data_readiness"), "data_readiness")
    readiness = _select(readiness_source, READINESS_KEYS, "data_readiness")
    underqualified = readiness_source.get("underqualified_segments")
    if isinstance(underqualified, list):
        readiness["underqualified_segments"] = len(underqualified)
    elif isinstance(underqualified, int) and not isinstance(underqualified, bool):
        readiness["underqualified_segments"] = underqualified
    else:
        raise ValueError("data_readiness.underqualified_segments must be a list or integer")

    status = metadata.get("status")
    failed_gates = metadata.get("failed_gates", [])
    if status not in {"published", "rejected"}:
        raise ValueError("metadata.status must be published or rejected")
    if not isinstance(failed_gates, list) or not all(
        isinstance(gate, str) for gate in failed_gates
    ):
        raise ValueError("metadata.failed_gates must be a string list")

    return {
        "schema_version": 1,
        "run_id": run_id,
        "source_revision": source_revision,
        "metadata_sha256": hashlib.sha256(metadata_bytes).hexdigest(),
        "status": status,
        "failed_gates": failed_gates,
        "metrics": metrics,
        "evaluation_diagnostics": diagnostics,
        "data_readiness": readiness,
    }


def export_evidence(
    metadata_path: Path,
    output_path: Path,
    *,
    run_id: str,
    source_revision: str,
) -> dict[str, Any]:
    evidence = build_evidence(
        metadata_path.read_bytes(),
        run_id=run_id,
        source_revision=source_revision,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.name}.tmp")
    temporary.write_text(f"{json.dumps(evidence, indent=2)}\n", encoding="utf-8")
    temporary.replace(output_path)
    return evidence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export compact salary evaluation evidence")
    parser.add_argument("metadata", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source-revision", required=True)
    args = parser.parse_args(argv)
    try:
        evidence = export_evidence(
            args.metadata,
            args.output,
            run_id=args.run_id,
            source_revision=args.source_revision,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(
        f"Exported {evidence['status']} evaluation from run {evidence['run_id']} to {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
