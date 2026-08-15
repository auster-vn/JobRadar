import subprocess

import pytest

from workers.analytics_tasks import build_analytics, run_dbt_command


def test_build_analytics_checks_freshness_before_build(monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[list[str]] = []

    def fake_run(command: list[str]) -> dict[str, str]:
        commands.append(command)
        return {"command": " ".join(command), "status": "success", "output": "PASS"}

    monkeypatch.setattr("workers.analytics_tasks.run_dbt_command", fake_run)

    result = build_analytics()

    assert commands == [["source", "freshness"], ["build"]]
    assert result["status"] == "success"


def test_dbt_failure_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "workers.analytics_tasks.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, "", "stale source"),
    )

    with pytest.raises(RuntimeError, match="stale source"):
        run_dbt_command(["source", "freshness"])
