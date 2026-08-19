from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


def declared_week_number(name: str) -> int | None:
    match = re.match(r"^\s*(?:w|week)\s*0*(\d{1,2})(?=\b|\s*[-:])", str(name), flags=re.IGNORECASE)
    if not match:
        return None
    value = int(match.group(1))
    return value if value > 0 else None


def _issue(code: str, severity: str, message: str) -> dict[str, Any]:
    return {"code": code, "severity": severity, "message": message}


def audit_week_structure(snapshot: Path) -> dict[str, Any]:
    snapshot = snapshot.resolve()
    modules = json.loads((snapshot / "modules.json").read_text(encoding="utf-8"))
    module_items = json.loads((snapshot / "module-items.json").read_text(encoding="utf-8"))

    items_by_source_id = {
        str(record.get("source_id")): record
        for record in module_items
        if isinstance(record, dict) and record.get("source_id") is not None
    }

    week_modules: list[dict[str, Any]] = []
    by_week: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
    issues: list[dict[str, Any]] = []
    assignment_weeks: set[int] = set()

    for module in modules:
        if not isinstance(module, dict):
            continue
        name = str(module.get("name") or "")
        week_number = declared_week_number(name)
        if week_number is None:
            continue

        module_id = module.get("id")
        item_record = items_by_source_id.get(str(module_id), {})
        items = list(item_record.get("items") or []) if isinstance(item_record, dict) else []
        assignment_items = [
            item for item in items
            if isinstance(item, dict) and str(item.get("type") or "").casefold() == "assignment"
        ]

        row = {
            "module_id": module_id,
            "module_name": name,
            "week_number": week_number,
            "position": module.get("position"),
            "item_count": len(items),
            "assignment_count": len(assignment_items),
            "assignments": [],
        }

        if not items:
            issues.append(_issue(
                "empty_week_module",
                "review",
                f"Weekly module {name!r} (Week {week_number}) is empty.",
            ))

        for item in assignment_items:
            title = str(item.get("title") or "")
            assignment_week = declared_week_number(title)
            row["assignments"].append({
                "title": title,
                "week_number": assignment_week,
                "item_id": item.get("id"),
            })
            if assignment_week is None:
                continue
            assignment_weeks.add(assignment_week)
            if assignment_week != week_number:
                issues.append(_issue(
                    "assignment_module_week_mismatch",
                    "warning",
                    f"Module {name!r} declares Week {week_number}, but contains assignment {title!r}, which declares Week {assignment_week}.",
                ))

        week_modules.append(row)
        by_week[week_number].append(row)

    for week_number, members in sorted(by_week.items()):
        if len(members) > 1:
            names = ", ".join(repr(item["module_name"]) for item in members)
            issues.append(_issue(
                "duplicate_week_module",
                "warning",
                f"Week {week_number} appears in {len(members)} modules: {names}.",
            ))

    module_weeks = set(by_week)
    for week_number in sorted(assignment_weeks - module_weeks):
        issues.append(_issue(
            "missing_week_module",
            "warning",
            f"Assignments declare Week {week_number}, but no Week {week_number} module exists.",
        ))

    return {
        "schema_version": 1,
        "issues": issues,
        "week_modules": week_modules,
        "summary": {
            "week_modules": len(week_modules),
            "issues": len(issues),
            "empty_week_modules": sum(1 for item in issues if item["code"] == "empty_week_module"),
            "duplicate_week_modules": sum(1 for item in issues if item["code"] == "duplicate_week_module"),
            "assignment_module_mismatches": sum(1 for item in issues if item["code"] == "assignment_module_week_mismatch"),
            "missing_week_modules": sum(1 for item in issues if item["code"] == "missing_week_module"),
        },
    }
