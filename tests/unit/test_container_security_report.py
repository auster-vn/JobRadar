from pathlib import Path
from typing import Any

import pytest

from scripts.enforce_container_security_report import (
    evaluate_report,
    load_report,
    render_summary,
)

IMAGE_ID = f"sha256:{'a' * 64}"


def _report(
    *,
    vulnerabilities: list[dict[str, Any]] | None = None,
    secrets: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "SchemaVersion": 2,
        "ArtifactName": "ghcr.io/auster-vn/jobradarvn-backend:revision",
        "ArtifactType": "container_image",
        "Metadata": {"ImageID": IMAGE_ID},
        "Results": [
            {
                "Target": "image (debian 13)",
                "Vulnerabilities": vulnerabilities or [],
                "Secrets": secrets or [],
            }
        ],
    }


def test_accepts_only_explicitly_upstream_unfixed_vulnerabilities() -> None:
    evaluation = evaluate_report(
        _report(
            vulnerabilities=[
                {
                    "VulnerabilityID": "CVE-2026-0001",
                    "PkgName": "libexample",
                    "Severity": "CRITICAL",
                    "Status": "affected",
                },
                {
                    "VulnerabilityID": "CVE-2026-0002",
                    "PkgName": "libdeferred",
                    "Severity": "HIGH",
                    "Status": "fix_deferred",
                },
            ]
        )
    )

    assert evaluation.failures == ()
    assert evaluation.blocking_count == 2
    assert evaluation.accepted_unfixed_count == 2
    assert evaluation.accepted_by_severity == {"CRITICAL": 1, "HIGH": 1}
    assert "upstream-unfixed=2" in render_summary(evaluation)


def test_rejects_remediable_high_or_critical_vulnerability() -> None:
    evaluation = evaluate_report(
        _report(
            vulnerabilities=[
                {
                    "VulnerabilityID": "CVE-2026-0003",
                    "PkgName": "libfixable",
                    "Severity": "HIGH",
                    "Status": "fixed",
                    "FixedVersion": "2.0",
                }
            ]
        )
    )

    assert evaluation.accepted_unfixed_count == 0
    assert evaluation.failures == ("CVE-2026-0003 (libfixable): upgrade to fixed version 2.0",)


@pytest.mark.parametrize("status", ["", "unknown", "will_not_fix", "end_of_life"])
def test_rejects_unfixed_vulnerability_without_accepted_status(status: str) -> None:
    evaluation = evaluate_report(
        _report(
            vulnerabilities=[
                {
                    "VulnerabilityID": "CVE-2026-0004",
                    "PkgName": "libunknown",
                    "Severity": "CRITICAL",
                    "Status": status,
                }
            ]
        )
    )

    assert len(evaluation.failures) == 1
    assert "unaccepted upstream status" in evaluation.failures[0]


def test_rejects_every_detected_secret() -> None:
    evaluation = evaluate_report(
        _report(secrets=[{"RuleID": "private-key", "Category": "AsymmetricPrivateKey"}])
    )

    assert evaluation.secret_count == 1
    assert evaluation.failures == ("secret detected: private-key (private-key)",)


def test_rejects_empty_results() -> None:
    report = _report()
    report["Results"] = []

    evaluation = evaluate_report(report)

    assert "report contains no scanned targets" in evaluation.failures


def test_rejects_invalid_secret_finding() -> None:
    evaluation = evaluate_report(_report(secrets=["not-an-object"]))  # type: ignore[list-item]

    assert evaluation.secret_count == 1
    assert "report contains an invalid secret finding" in evaluation.failures


def test_rejects_report_without_a_real_image_digest() -> None:
    report = _report()
    report["Metadata"] = {"ImageID": "latest"}

    evaluation = evaluate_report(report)

    assert "report does not contain a valid scanned image digest" in evaluation.failures


def test_rejects_report_for_a_different_image() -> None:
    evaluation = evaluate_report(
        _report(),
        expected_artifact="ghcr.io/auster-vn/jobradarvn-backend:other-revision",
    )

    assert "does not match expected image" in evaluation.failures[0]


def test_load_report_rejects_non_object_root(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    report.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="root must be a JSON object"):
        load_report(report)
