from __future__ import annotations

import json
import re
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from typing import Any, TypedDict, cast

import httpx

OSV_QUERY_URL = "https://api.osv.dev/v1/query"
LOCAL_PROJECT = "jobradarvn"


class Vulnerability(TypedDict, total=False):
    id: str
    aliases: list[str]
    fix_versions: list[str]


class Dependency(TypedDict, total=False):
    name: str
    version: str
    vulns: list[Vulnerability]
    skip_reason: str


class AuditReport(TypedDict):
    dependencies: list[Dependency]
    fixes: list[dict[str, Any]]


def normalized_public_version(package_version: str) -> str:
    public_version = package_version.split("+", maxsplit=1)[0]
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)+(?:[A-Za-z0-9.-]+)?", public_version) is None:
        raise ValueError(f"unsupported package version: {package_version}")
    return public_version


def report_failures(report: AuditReport) -> list[str]:
    failures: list[str] = []
    for dependency in report["dependencies"]:
        name = dependency.get("name", "unknown")
        for vulnerability in dependency.get("vulns", []):
            failures.append(f"{name}: {vulnerability.get('id', 'unknown vulnerability')}")

        skip_reason = dependency.get("skip_reason")
        if skip_reason is None:
            continue
        expected_editable = (
            name == LOCAL_PROJECT and skip_reason == "distribution marked as editable"
        )
        expected_torch_wheel = name == "torch" and "Dependency not found on PyPI" in skip_reason
        if not expected_editable and not expected_torch_wheel:
            failures.append(f"{name}: unaudited dependency ({skip_reason})")
    return failures


def osv_ids(payload: dict[str, Any]) -> list[str]:
    vulnerabilities = payload.get("vulns", [])
    if not isinstance(vulnerabilities, list):
        raise ValueError("OSV returned an invalid vulnerability list")
    return sorted(
        str(item.get("id", "unknown vulnerability"))
        for item in vulnerabilities
        if isinstance(item, dict)
    )


def audit_torch() -> tuple[str, list[str]]:
    try:
        installed_version = version("torch")
    except PackageNotFoundError as exc:
        raise ValueError("torch is not installed") from exc
    public_version = normalized_public_version(installed_version)
    with httpx.Client(timeout=20.0, follow_redirects=False) as client:
        response = client.post(
            OSV_QUERY_URL,
            json={"package": {"name": "torch", "ecosystem": "PyPI"}, "version": public_version},
        )
        response.raise_for_status()
        payload = cast(dict[str, Any], response.json())
    return installed_version, osv_ids(payload)


def main() -> int:
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "pip_audit",
            "--local",
            "--skip-editable",
            "--progress-spinner",
            "off",
            "--format",
            "json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    try:
        report = cast(AuditReport, json.loads(result.stdout))
        dependencies = report["dependencies"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        print(result.stderr.strip() or "pip-audit did not return a valid report", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 1

    failures = report_failures(report)
    if result.returncode not in (0, 1):
        failures.append(result.stderr.strip() or f"pip-audit exited {result.returncode}")

    try:
        torch_version, torch_vulnerabilities = audit_torch()
    except (httpx.HTTPError, ValueError) as exc:
        failures.append(f"torch: OSV audit failed ({exc})")
        torch_version, torch_vulnerabilities = "unknown", []
    failures.extend(f"torch: {vulnerability}" for vulnerability in torch_vulnerabilities)

    if failures:
        print("Python dependency audit failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    audited = sum(1 for dependency in dependencies if dependency.get("version"))
    print(
        "Python dependency audit passed: "
        f"{audited} PyPI distributions and torch {torch_version}; 0 known vulnerabilities"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
