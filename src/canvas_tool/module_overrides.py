from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .api import CanvasApiError, CanvasClient


def _safe_override(override: dict[str, Any]) -> dict[str, Any]:
    student_ids = list(override.get("student_ids") or [])
    section_id = override.get("course_section_id")
    group_id = override.get("group_id")

    if student_ids:
        target_type = "specific_students"
        title = "Specific students"
    elif section_id is not None:
        target_type = "section"
        title = str(override.get("title") or "Course section")
    elif group_id is not None:
        target_type = "group"
        title = str(override.get("title") or "Group")
    else:
        target_type = "other"
        title = str(override.get("title") or "Override")

    return {
        "id": override.get("id"),
        "title": title,
        "target_type": target_type,
        "course_section_id": section_id,
        "group_id": group_id,
        "student_count": len(student_ids),
    }


def capture_module_overrides(client: CanvasClient, snapshot: Path) -> list[dict[str, Any]]:
    """Capture module Assign To settings without retaining student identifiers."""
    snapshot = snapshot.resolve()
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    modules = json.loads((snapshot / "modules.json").read_text(encoding="utf-8"))
    course_id = str(manifest["course_id"])

    print(f"  {'module-overrides':<28}", end="", file=sys.stderr)
    result: list[dict[str, Any]] = []
    error_count = 0
    override_count = 0
    for module in modules:
        if not isinstance(module, dict) or module.get("id") is None:
            continue
        module_id = str(module["id"])
        endpoint = f"/api/v1/courses/{course_id}/modules/{module_id}/assignment_overrides"
        available = True
        try:
            raw = client.paginate(endpoint)
        except CanvasApiError:
            error_count += 1
            available = False
            raw = []
        safe = [_safe_override(item) for item in raw if isinstance(item, dict)]
        override_count += len(safe)
        result.append({
            "source_id": module_id,
            "title": str(module.get("name") or ""),
            "source_position": module.get("position"),
            "available": available,
            "items": safe,
        })

    (snapshot / "module-overrides.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    suffix = f"{len(result)} groups, {override_count} overrides"
    if error_count:
        suffix += f", {error_count} unavailable"
    print(suffix, file=sys.stderr)
    return result
