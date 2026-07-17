import json
from pathlib import Path

from scripts.validate_monitoring import validate_all_dashboards, validate_dashboard

PROJECT_ROOT = Path(__file__).parents[2]


def test_provisioned_grafana_dashboards_are_valid() -> None:
    assert validate_all_dashboards() == []


def test_dashboard_validator_rejects_overlapping_panels(tmp_path: Path) -> None:
    dashboard = {
        "uid": "overlap-test",
        "title": "Overlap Test",
        "schemaVersion": 41,
        "panels": [
            {
                "id": panel_id,
                "title": f"Panel {panel_id}",
                "type": "stat",
                "gridPos": {"x": panel_id - 1, "y": 0, "w": 12, "h": 8},
                "targets": [{"expr": "up"}],
            }
            for panel_id in (1, 2)
        ],
    }
    path = tmp_path / "dashboard.json"
    path.write_text(json.dumps(dashboard), encoding="utf-8")

    _, errors = validate_dashboard(path)

    assert any("panels 1 and 2 overlap" in error for error in errors)


def test_load_test_requires_an_explicit_isolated_api() -> None:
    load_test = (PROJECT_ROOT / "tests/load/jobs.js").read_text(encoding="utf-8")

    assert "const baseUrl = __ENV.BASE_URL" in load_test
    assert "BASE_URL is required" in load_test
    assert '"http://localhost:8000"' not in load_test
