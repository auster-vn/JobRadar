from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BLOCKING_SEVERITIES = frozenset({"HIGH", "CRITICAL"})
ACCEPTED_UNFIXED_STATUSES = frozenset({"affected", "fix_deferred"})
IMAGE_ID_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class Evaluation:
    artifact_name: str
    secret_count: int
    blocking_count: int
    accepted_unfixed_count: int
    accepted_by_severity: Counter[str]
    accepted_by_status: Counter[str]
    failures: tuple[str, ...]


def _finding_label(finding: dict[str, Any], identifier_key: str) -> str:
    identifier = str(finding.get(identifier_key) or "unknown")
    package = str(finding.get("PkgName") or finding.get("RuleID") or "unknown package")
    return f"{identifier} ({package})"


def evaluate_report(report: dict[str, Any], *, expected_artifact: str | None = None) -> Evaluation:
    failures: list[str] = []
    artifact_name = str(report.get("ArtifactName") or "unknown image")
    metadata = report.get("Metadata")
    image_id = metadata.get("ImageID") if isinstance(metadata, dict) else None

    if report.get("SchemaVersion") != 2:
        failures.append("unsupported or missing Trivy schema version")
    if report.get("ArtifactType") != "container_image":
        failures.append("report does not describe a container image")
    if expected_artifact is not None and artifact_name != expected_artifact:
        failures.append(
            f"report artifact {artifact_name} does not match expected image {expected_artifact}"
        )
    if not isinstance(image_id, str) or IMAGE_ID_PATTERN.fullmatch(image_id) is None:
        failures.append("report does not contain a valid scanned image digest")

    results = report.get("Results")
    if not isinstance(results, list):
        return Evaluation(
            artifact_name=artifact_name,
            secret_count=0,
            blocking_count=0,
            accepted_unfixed_count=0,
            accepted_by_severity=Counter(),
            accepted_by_status=Counter(),
            failures=tuple([*failures, "report does not contain a results list"]),
        )
    if not results:
        failures.append("report contains no scanned targets")

    secret_count = 0
    blocking_count = 0
    accepted_by_severity: Counter[str] = Counter()
    accepted_by_status: Counter[str] = Counter()

    for result in results:
        if not isinstance(result, dict):
            failures.append("report contains an invalid result entry")
            continue

        secrets = result.get("Secrets") or []
        if not isinstance(secrets, list):
            failures.append("report contains an invalid secrets entry")
        else:
            secret_count += len(secrets)
            for secret in secrets:
                if isinstance(secret, dict):
                    failures.append(f"secret detected: {_finding_label(secret, 'RuleID')}")
                else:
                    failures.append("report contains an invalid secret finding")

        vulnerabilities = result.get("Vulnerabilities") or []
        if not isinstance(vulnerabilities, list):
            failures.append("report contains an invalid vulnerabilities entry")
            continue

        for vulnerability in vulnerabilities:
            if not isinstance(vulnerability, dict):
                failures.append("report contains an invalid vulnerability entry")
                continue
            severity = str(vulnerability.get("Severity") or "").upper()
            if severity not in BLOCKING_SEVERITIES:
                continue

            blocking_count += 1
            label = _finding_label(vulnerability, "VulnerabilityID")
            fixed_version = str(vulnerability.get("FixedVersion") or "").strip()
            status = str(vulnerability.get("Status") or "").strip().lower()
            if fixed_version:
                failures.append(f"{label}: upgrade to fixed version {fixed_version}")
                continue
            if status not in ACCEPTED_UNFIXED_STATUSES:
                status_label = status or "missing"
                failures.append(
                    f"{label}: no fixed version and unaccepted upstream status {status_label}"
                )
                continue
            accepted_by_severity[severity] += 1
            accepted_by_status[status] += 1

    return Evaluation(
        artifact_name=artifact_name,
        secret_count=secret_count,
        blocking_count=blocking_count,
        accepted_unfixed_count=sum(accepted_by_severity.values()),
        accepted_by_severity=accepted_by_severity,
        accepted_by_status=accepted_by_status,
        failures=tuple(failures),
    )


def render_summary(evaluation: Evaluation) -> str:
    severity = ", ".join(
        f"{name.lower()}={count}" for name, count in sorted(evaluation.accepted_by_severity.items())
    )
    status = ", ".join(
        f"{name}={count}" for name, count in sorted(evaluation.accepted_by_status.items())
    )
    details = "; ".join(part for part in (severity, status) if part) or "none"
    outcome = "passed" if not evaluation.failures else "failed"
    return (
        f"Container security gate {outcome} for {evaluation.artifact_name}: "
        f"secrets={evaluation.secret_count}, "
        f"high/critical={evaluation.blocking_count}, "
        f"upstream-unfixed={evaluation.accepted_unfixed_count} ({details})"
    )


def load_report(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Trivy report root must be a JSON object")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enforce JobRadar's fail-closed container vulnerability policy."
    )
    parser.add_argument("report", type=Path, help="Trivy JSON report")
    parser.add_argument(
        "--expected-image",
        required=True,
        help="Exact immutable image reference that Trivy was asked to scan",
    )
    parser.add_argument(
        "--summary-file",
        type=Path,
        help="Optional GitHub step summary file to append to",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        evaluation = evaluate_report(
            load_report(args.report),
            expected_artifact=args.expected_image,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Container security gate failed: invalid Trivy report ({exc})", file=sys.stderr)
        return 1

    summary = render_summary(evaluation)
    print(summary)
    if args.summary_file is not None:
        with args.summary_file.open("a", encoding="utf-8") as summary_file:
            summary_file.write(
                f"### Container security: `{evaluation.artifact_name}`\n\n{summary}\n"
            )

    if evaluation.failures:
        for failure in evaluation.failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
