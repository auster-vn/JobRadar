import subprocess

from workers.celery_app import app

DBT_BASE_COMMAND = ["dbt", "--no-use-colors"]
DBT_PROJECT_ARGS = ["--project-dir", "analytics", "--profiles-dir", "analytics"]


def run_dbt_command(command: list[str]) -> dict[str, str]:
    result = subprocess.run(  # noqa: S603,S607 - fixed executable and controlled arguments.
        [*DBT_BASE_COMMAND, *command, *DBT_PROJECT_ARGS],
        check=False,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    output = (result.stdout + result.stderr).strip()
    if result.returncode != 0:
        raise RuntimeError(f"dbt {' '.join(command)} failed: {output[-4000:]}")
    return {"command": " ".join(command), "status": "success", "output": output[-4000:]}


@app.task(name="workers.analytics_tasks.build_analytics")
def build_analytics() -> dict[str, object]:
    freshness = run_dbt_command(["source", "freshness"])
    build = run_dbt_command(["build"])
    return {"status": "success", "freshness": freshness, "build": build}
