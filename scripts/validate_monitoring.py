import json
import re
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parents[1]
DASHBOARD_DIR = PROJECT_ROOT / "infra" / "grafana" / "dashboards"
UID_PATTERN = re.compile(r"^[a-z0-9-]+$")


def _overlap(first: dict[str, int], second: dict[str, int]) -> bool:
    return (
        first["x"] < second["x"] + second["w"]
        and second["x"] < first["x"] + first["w"]
        and first["y"] < second["y"] + second["h"]
        and second["y"] < first["y"] + first["h"]
    )


def validate_dashboard(path: Path) -> tuple[str | None, list[str]]:
    errors: list[str] = []
    try:
        dashboard: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"{path}: invalid JSON: {exc}"]

    uid = dashboard.get("uid")
    if not isinstance(uid, str) or not UID_PATTERN.fullmatch(uid):
        errors.append(f"{path}: uid must contain lowercase letters, numbers or hyphens")
        uid = None
    if not isinstance(dashboard.get("title"), str) or not dashboard["title"].strip():
        errors.append(f"{path}: dashboard title is required")
    if not isinstance(dashboard.get("schemaVersion"), int):
        errors.append(f"{path}: schemaVersion must be an integer")
    panels = dashboard.get("panels")
    if not isinstance(panels, list) or not panels:
        return uid, [*errors, f"{path}: at least one panel is required"]

    panel_ids: set[int] = set()
    rectangles: list[tuple[int, dict[str, int]]] = []
    for panel in panels:
        if not isinstance(panel, dict):
            errors.append(f"{path}: every panel must be an object")
            continue
        panel_id = panel.get("id")
        if not isinstance(panel_id, int) or panel_id <= 0:
            errors.append(f"{path}: panel id must be a positive integer")
            continue
        if panel_id in panel_ids:
            errors.append(f"{path}: duplicate panel id {panel_id}")
        panel_ids.add(panel_id)
        if not isinstance(panel.get("title"), str) or not panel["title"].strip():
            errors.append(f"{path}: panel {panel_id} requires a title")
        if not isinstance(panel.get("type"), str) or not panel["type"].strip():
            errors.append(f"{path}: panel {panel_id} requires a type")

        grid = panel.get("gridPos")
        if not isinstance(grid, dict) or not all(
            isinstance(grid.get(key), int) for key in ("x", "y", "w", "h")
        ):
            errors.append(f"{path}: panel {panel_id} has an invalid gridPos")
        else:
            rectangle = {key: grid[key] for key in ("x", "y", "w", "h")}
            if (
                rectangle["x"] < 0
                or rectangle["y"] < 0
                or rectangle["w"] <= 0
                or rectangle["h"] <= 0
                or rectangle["x"] + rectangle["w"] > 24
            ):
                errors.append(f"{path}: panel {panel_id} is outside the 24-column grid")
            rectangles.append((panel_id, rectangle))

        targets = panel.get("targets")
        if not isinstance(targets, list) or not targets:
            errors.append(f"{path}: panel {panel_id} requires at least one target")
        elif any(
            not isinstance(target, dict)
            or not isinstance(target.get("expr"), str)
            or not target["expr"].strip()
            for target in targets
        ):
            errors.append(f"{path}: panel {panel_id} has an empty Prometheus expression")

    for index, (first_id, first) in enumerate(rectangles):
        for second_id, second in rectangles[index + 1 :]:
            if _overlap(first, second):
                errors.append(f"{path}: panels {first_id} and {second_id} overlap")
    return uid, errors


def validate_all_dashboards(directory: Path = DASHBOARD_DIR) -> list[str]:
    errors: list[str] = []
    seen_uids: set[str] = set()
    paths = sorted(directory.glob("*.json"))
    if not paths:
        return [f"{directory}: no dashboard JSON files found"]
    for path in paths:
        uid, dashboard_errors = validate_dashboard(path)
        errors.extend(dashboard_errors)
        if uid:
            if uid in seen_uids:
                errors.append(f"{path}: duplicate dashboard uid {uid}")
            seen_uids.add(uid)
    return errors


def main() -> None:
    errors = validate_all_dashboards()
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"Validated {len(list(DASHBOARD_DIR.glob('*.json')))} Grafana dashboards")


if __name__ == "__main__":
    main()
