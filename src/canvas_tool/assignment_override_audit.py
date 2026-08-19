from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .semester import semester_bounds, week_for_date, weeks_from_calendar


@dataclass(frozen=True)
class AssignmentOverrideAuditResult:
    markdown_path: Path
    json_path: Path
    finding_count: int
    warning_count: int
    review_count: int


def _load(snapshot: Path, name: str, default: Any) -> Any:
    try:
        return json.loads((snapshot / name).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _md(value: Any) -> str:
    return str(value if value is not None else "").replace("\n", " ").replace("\r", " ").replace("|", "\\|")


def _zone(name: Any) -> ZoneInfo:
    try:
        return ZoneInfo(str(name or "UTC"))
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _local(value: Any, zone: ZoneInfo) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=zone)
    return parsed.astimezone(zone)


def _format(value: datetime | None) -> str:
    if value is None:
        return "—"
    return f"{value:%b} {value.day}, {value.year} {value.strftime('%I:%M %p').lstrip('0')} {value.tzname() or ''}".strip()


def _finding(severity: str, area: str, message: str, item: str = "") -> dict[str, str]:
    return {"severity": severity, "area": area, "item": item, "message": message}


def audit_assignment_overrides(snapshot: Path) -> AssignmentOverrideAuditResult:
    snapshot = snapshot.resolve()
    manifest = _load(snapshot, "manifest.json", {})
    assignments = _load(snapshot, "assignments.json", [])
    groups = _load(snapshot, "assignment-overrides.json", [])
    sections = _load(snapshot, "sections.json", [])
    course_groups = _load(snapshot, "groups.json", [])
    date_report = _load(snapshot, "date-audit.json", {})

    assignments_by_id = {
        str(item.get("id")): item
        for item in assignments
        if isinstance(item, dict) and item.get("id") is not None
    }
    section_names = {
        str(item.get("id")): str(item.get("name") or f"Section {item.get('id')}")
        for item in sections
        if isinstance(item, dict) and item.get("id") is not None
    }
    group_names = {
        str(item.get("id")): str(item.get("name") or f"Group {item.get('id')}")
        for item in course_groups
        if isinstance(item, dict) and item.get("id") is not None
    }

    calendar = date_report.get("calendar") if isinstance(date_report.get("calendar"), dict) else {}
    zone = _zone((calendar or {}).get("time_zone") or "UTC")
    weeks = weeks_from_calendar(calendar) if calendar else []
    start: date | None = None
    end: date | None = None
    if calendar:
        start, end = semester_bounds(calendar)

    findings: list[dict[str, str]] = []
    rows: list[dict[str, Any]] = []
    target_counts: Counter[str] = Counter()

    for record in groups if isinstance(groups, list) else []:
        if not isinstance(record, dict):
            continue
        assignment_id = str(record.get("source_id") or "")
        assignment = assignments_by_id.get(assignment_id, {})
        name = str(record.get("title") or assignment.get("name") or assignment_id or "unnamed assignment")
        available = record.get("available") is not False
        overrides = [item for item in (record.get("items") or []) if isinstance(item, dict)]
        has_overrides = bool(record.get("has_overrides") or assignment.get("has_overrides"))
        only_visible = bool(record.get("only_visible_to_overrides") or assignment.get("only_visible_to_overrides"))

        if has_overrides and not available:
            findings.append(_finding("review", "Assign To", "Canvas reported overrides, but the override list could not be retrieved.", name))
        elif has_overrides and not overrides:
            findings.append(_finding("review", "Assign To", "Canvas reports that overrides exist, but no override records were returned.", name))
        if only_visible and available and not overrides:
            findings.append(_finding("warning", "assignment visibility", "Assignment is only visible to overrides, but no overrides were captured.", name))

        seen_targets: Counter[tuple[str, str]] = Counter()
        for override in overrides:
            target_type = str(override.get("target_type") or "other")
            target_counts[target_type] += 1
            if target_type == "specific_students":
                target = f"Specific students ({int(override.get('student_count') or 0)})"
                target_key = str(override.get("id") or target)
            elif target_type == "section":
                sid = str(override.get("course_section_id") or "")
                target = section_names.get(sid) or str(override.get("title") or f"Section {sid}")
                target_key = sid
            elif target_type == "group":
                gid = str(override.get("group_id") or "")
                target = group_names.get(gid) or str(override.get("title") or f"Group {gid}")
                target_key = gid
            else:
                target = str(override.get("title") or "Override")
                target_key = str(override.get("id") or target)
            seen_targets[(target_type, target_key)] += 1

            due = _local(override.get("due_at"), zone)
            unlock = _local(override.get("unlock_at"), zone)
            lock = _local(override.get("lock_at"), zone)

            if unlock and due and unlock > due:
                findings.append(_finding("warning", "override dates", f"Unlocks {_format(unlock)}, after override due date {_format(due)}.", f"{name} → {target}"))
            if lock and due and lock < due:
                findings.append(_finding("warning", "override dates", f"Locks {_format(lock)}, before override due date {_format(due)}.", f"{name} → {target}"))
            if unlock and lock and unlock > lock:
                findings.append(_finding("warning", "override dates", f"Unlocks {_format(unlock)}, after override lock date {_format(lock)}.", f"{name} → {target}"))

            week_label = ""
            if due is not None:
                day = due.date()
                if start and day < start:
                    findings.append(_finding("warning", "override due date", f"Override due date {_format(due)} is before the first class day on {start.isoformat()}.", f"{name} → {target}"))
                if end and day > end:
                    findings.append(_finding("warning", "override due date", f"Override due date {_format(due)} is after the last class day on {end.isoformat()}.", f"{name} → {target}"))
                week = week_for_date(weeks, day) if weeks else None
                if week is not None:
                    week_label = week.label
                    if week.kind == "break":
                        findings.append(_finding("warning", "override due date", f"Override due date {_format(due)} falls during the unnumbered {week.label} week.", f"{name} → {target}"))

            rows.append({
                "assignment_id": assignment_id,
                "assignment": name,
                "target_type": target_type,
                "target": target,
                "student_count": int(override.get("student_count") or 0),
                "due_at": override.get("due_at"),
                "unlock_at": override.get("unlock_at"),
                "lock_at": override.get("lock_at"),
                "due_local": _format(due),
                "unlock_local": _format(unlock),
                "lock_local": _format(lock),
                "week": week_label,
                "only_visible_to_overrides": only_visible,
            })

        for (target_type, target_key), count in seen_targets.items():
            if count > 1:
                findings.append(_finding("review", "Assign To", f"The same {target_type.replace('_', ' ')} target ({target_key}) appears {count} times for this assignment.", name))

    summary = {
        "assignments": len(assignments_by_id),
        "assignments_with_overrides": sum(1 for item in groups if isinstance(item, dict) and item.get("has_overrides")) if isinstance(groups, list) else 0,
        "override_records": len(rows),
        "section_overrides": target_counts.get("section", 0),
        "group_overrides": target_counts.get("group", 0),
        "specific_student_overrides": target_counts.get("specific_students", 0),
        "assignments_only_visible_to_overrides": sum(1 for item in groups if isinstance(item, dict) and item.get("only_visible_to_overrides")) if isinstance(groups, list) else 0,
        "unavailable_override_lists": sum(1 for item in groups if isinstance(item, dict) and item.get("available") is False) if isinstance(groups, list) else 0,
    }

    payload = {
        "schema_version": 1,
        "course_id": manifest.get("course_id"),
        "course_name": manifest.get("course_name"),
        "read_only": True,
        "student_identifiers_included": False,
        "summary": summary,
        "findings": findings,
        "overrides": rows,
    }
    json_path = snapshot / "assignment-override-audit.json"
    markdown_path = snapshot / "assignment-override-audit.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "# Assignment Assign To and override audit",
        "",
        f"- Course: **{manifest.get('course_name', 'unnamed course')}**",
        f"- Course code: `{manifest.get('course_code', '')}`",
        f"- Canvas course ID: `{manifest.get('course_id', '')}`",
        "- Mode: **read-only**. No Canvas content is changed.",
        "- Student identifiers: **not stored**. Specific-student overrides are shown only as counts.",
        "",
        "## Summary",
        "",
    ]
    for key, value in summary.items():
        lines.append(f"- {key.replace('_', ' ').title()}: **{value}**")

    lines.extend(["", "## Attention / review", ""])
    actionable = [item for item in findings if item["severity"] in {"warning", "review"}]
    if actionable:
        for item in actionable:
            label = f" **{_md(item['item'])}**:" if item.get("item") else ""
            lines.append(f"- **{item['severity'].upper()} · {_md(item['area'])}**{label} {_md(item['message'])}")
    else:
        lines.append("None found.")

    lines.extend([
        "",
        "## Assignment overrides",
        "",
        "| Assignment | Target type | Target | Week | Due | Unlock | Lock | Only visible to overrides |",
        "|---|---|---|---|---|---|---|---|",
    ])
    if rows:
        for row in rows:
            lines.append(
                f"| {_md(row['assignment'])} | {_md(row['target_type'].replace('_', ' '))} | {_md(row['target'])} | {_md(row['week'] or '—')} | "
                f"{_md(row['due_local'])} | {_md(row['unlock_local'])} | {_md(row['lock_local'])} | {'Yes' if row['only_visible_to_overrides'] else 'No'} |"
            )
    else:
        lines.append("| — | — | No assignment overrides captured | — | — | — | — | — |")
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    counts = Counter(item["severity"] for item in findings)
    return AssignmentOverrideAuditResult(
        markdown_path=markdown_path,
        json_path=json_path,
        finding_count=len(findings),
        warning_count=counts.get("warning", 0),
        review_count=counts.get("review", 0),
    )
