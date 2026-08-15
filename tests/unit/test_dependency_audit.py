from importlib.metadata import PackageNotFoundError

import pytest

from scripts import audit_python_dependencies
from scripts.audit_python_dependencies import (
    AuditReport,
    normalized_public_version,
    osv_ids,
    report_failures,
)


def test_dependency_report_accepts_only_expected_local_skips() -> None:
    report: AuditReport = {
        "dependencies": [
            {"name": "fastapi", "version": "1.0.0", "vulns": []},
            {"name": "jobradarvn", "skip_reason": "distribution marked as editable"},
            {
                "name": "torch",
                "skip_reason": (
                    "Dependency not found on PyPI and could not be audited: torch (2.13.0+cpu)"
                ),
            },
        ],
        "fixes": [],
    }

    assert report_failures(report) == []


def test_dependency_report_rejects_vulnerabilities_and_unknown_skips() -> None:
    report: AuditReport = {
        "dependencies": [
            {"name": "unsafe", "version": "1.0.0", "vulns": [{"id": "CVE-1"}]},
            {"name": "unresolved", "skip_reason": "resolver failed"},
        ],
        "fixes": [],
    }

    assert report_failures(report) == [
        "unsafe: CVE-1",
        "unresolved: unaudited dependency (resolver failed)",
    ]


def test_torch_version_and_osv_response_are_fail_closed() -> None:
    assert normalized_public_version("2.13.0+cpu") == "2.13.0"
    assert osv_ids({"vulns": [{"id": "GHSA-b"}, {"id": "GHSA-a"}]}) == [
        "GHSA-a",
        "GHSA-b",
    ]


def test_torch_audit_rejects_a_missing_custom_wheel(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing_version(_: str) -> str:
        raise PackageNotFoundError

    monkeypatch.setattr(audit_python_dependencies, "version", missing_version)

    with pytest.raises(ValueError, match="torch is not installed"):
        audit_python_dependencies.audit_torch()
