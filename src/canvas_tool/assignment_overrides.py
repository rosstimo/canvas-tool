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
        "due_at": override.get("due_at"),
        "unlock_at": override.get("unlock_at"),
        "lock_at": override.get("lock_at"),
    }


def capture_assignment_overrides(client: CanvasClient, snapshot: Path) -> list[dict[str, Any]]:
    """Capture assignment Assign To overrides without retaining student identifiers."""
    snapshot = snapshot.resolve()
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    assignments = json.loads((snapshot / "assignments.json").read_text(encoding="utf-8"))
    course_id = str(manifest["course_id"])

    print(f"  {'assignment-overrides':<28}", end="", file=sys.stderr)
    result: list[dict[str, Any]] = []
    error_count = 0
    override_count = 0

    for assignment in assignments:
        if not isinstance(assignment, dict) or assignment.get("id") is None:
            continue
        assignment_id = str(assignment["id"])
        available = True
        raw: list[Any] = []
        if assignment.get("has_overrides"):
            endpoint = f"/api/v1/courses/{course_id}/assignments/{assignment_id}/overrides"
            try:
                raw = client.paginate(endpoint)
            except CanvasApiError:
                error_count += 1
                available = False

        safe = [_safe_override(item) for item in raw if isinstance(item, dict)]
        override_count += len(safe)
        result.append({
            "source_id": assignment_id,
            "title": str(assignment.get("name") or ""),
            "available": available,
            "has_overrides": bool(assignment.get("has_overrides")),
            "only_visible_to_overrides": bool(assignment.get("only_visible_to_overrides")),
            "items": safe,
        })

    (snapshot / "assignment-overrides.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    suffix = f"{len(result)} groups, {override_count} overrides"
    if error_count:
        suffix += f", {error_count} unavailable"
    print(suffix, file=sys.stderr)
    return result
