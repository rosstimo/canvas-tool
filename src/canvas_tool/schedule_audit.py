from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .calendar_config import find_calendar
from .semester import render_week_table, semester_bounds, week_for_date, week_to_dict, weeks_from_calendar


@dataclass(frozen=True)
class DateAuditResult:
    markdown_path: Path
    json_path: Path
    calendar_name: str | None
    assignment_count: int
    dated_count: int
    undated_count: int
    issue_count: int


def _parse_datetime(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _local(value: Any, zone: ZoneInfo) -> datetime | None:
    parsed = _parse_datetime(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=zone)
    return parsed.astimezone(zone)


def _format_local(value: datetime | None) -> str:
    if value is None:
        return ""
    time_text = value.strftime("%I:%M %p").lstrip("0")
    return f"{value:%A, %B} {value.day}, {value.year} {time_text} {value.tzname() or ''}".strip()


def _format_date(value: datetime | None) -> str:
    if value is None:
        return ""
    return f"{value:%B} {value.day}, {value.year}"


def _format_time(value: datetime | None) -> str:
    if value is None:
        return ""
    return f"{value.strftime('%I:%M %p').lstrip('0')} {value.tzname() or ''}".strip()


def _date_range_contains(period: dict[str, Any], day: date) -> bool:
    try:
        start = date.fromisoformat(str(period["start"]))
        end = date.fromisoformat(str(period.get("end") or period["start"]))
    except (KeyError, ValueError):
        return False
    return start <= day <= end


def _issue(
    code: str,
    severity: str,
    message: str,
    assignment: str | None = None,
    assignment_id: Any = None,
    module: str | None = None,
    module_id: Any = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {"code": code, "severity": severity, "message": message}
    if assignment is not None:
        result["assignment"] = assignment
    if assignment_id is not None:
        result["assignment_id"] = assignment_id
    if module is not None:
        result["module"] = module
    if module_id is not None:
        result["module_id"] = module_id
    return result


def _week_fields(weeks: list[Any], day: date) -> tuple[int | None, str, str]:
    week = week_for_date(weeks, day) if weeks else None
    if week is None:
        return None, "", ""
    return week.week_number, week.label, week.kind


def audit_dates(snapshot: Path, root: Path, calendar_path: Path | None = None) -> DateAuditResult:
    """Audit structured Canvas dates without interpreting arbitrary names or titles."""
    snapshot = snapshot.resolve()
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    course = json.loads((snapshot / "course.json").read_text(encoding="utf-8"))
    assignments = json.loads((snapshot / "assignments.json").read_text(encoding="utf-8"))
    groups = json.loads((snapshot / "assignment-groups.json").read_text(encoding="utf-8"))
    modules = json.loads((snapshot / "modules.json").read_text(encoding="utf-8"))

    calendar = find_calendar(root, manifest, course, calendar_path)
    time_zone_name = str((calendar or {}).get("time_zone") or course.get("time_zone") or "UTC")
    zone = _zone(time_zone_name)
    group_names = {str(item.get("id")): item.get("name") for item in groups if isinstance(item, dict)}

    start_date: date | None = None
    end_date: date | None = None
    semester_weeks: list[Any] = []
    holiday_periods: list[dict[str, Any]] = []
    special_periods: list[dict[str, Any]] = []
    if calendar:
        start_date, end_date = semester_bounds(calendar)
        semester_weeks = weeks_from_calendar(calendar)
        holiday_periods = list(calendar.get("holidays") or calendar.get("no_class_periods") or [])
        special_periods = list(calendar.get("special_periods") or [])

    rows: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    dated_days: defaultdict[date, list[dict[str, Any]]] = defaultdict(list)
    due_times: Counter[str] = Counter()
    weekdays: Counter[str] = Counter()

    for assignment in assignments:
        if not isinstance(assignment, dict):
            continue
        assignment_id = assignment.get("id")
        name = str(assignment.get("name") or f"Assignment {assignment_id or '?'}")
        due = _local(assignment.get("due_at"), zone)
        unlock = _local(assignment.get("unlock_at"), zone)
        lock = _local(assignment.get("lock_at"), zone)
        row_issues: list[str] = []
        notes: list[str] = []
        week_number: int | None = None
        week_label = ""

        if due is None:
            issues.append(_issue("missing_due_date", "review", "No due date is set.", name, assignment_id))
            row_issues.append("missing due date")
        else:
            day = due.date()
            dated_days[day].append(assignment)
            due_times[due.strftime("%H:%M")] += 1
            weekdays[due.strftime("%A")] += 1
            week_number, week_label, week_kind = _week_fields(semester_weeks, day)

            if start_date and day < start_date:
                issues.append(_issue("before_term", "warning", f"Due {_format_local(due)}, before the first class day on {start_date.isoformat()}.", name, assignment_id))
                row_issues.append("before first class")
            if end_date and day > end_date:
                issues.append(_issue("after_term", "warning", f"Due {_format_local(due)}, after the last class day on {end_date.isoformat()}.", name, assignment_id))
                row_issues.append("after last class")

            if week_kind == "break":
                issues.append(_issue("break_week", "warning", f"Due {_format_local(due)} during the unnumbered {week_label} week.", name, assignment_id))
                row_issues.append(week_label)

            for period in holiday_periods:
                if _date_range_contains(period, day):
                    period_name = str(period.get("name") or "no-class day")
                    issues.append(_issue("no_class_day", "warning", f"Due {_format_local(due)} during {period_name}.", name, assignment_id))
                    row_issues.append(period_name)
            for period in special_periods:
                if _date_range_contains(period, day):
                    notes.append(str(period.get("name") or "special period"))

        if unlock and due and unlock > due:
            issues.append(_issue("unlock_after_due", "warning", f"Unlocks {_format_local(unlock)}, after its due date {_format_local(due)}.", name, assignment_id))
            row_issues.append("unlock after due")
        if lock and due and lock < due:
            issues.append(_issue("lock_before_due", "warning", f"Locks {_format_local(lock)}, before its due date {_format_local(due)}.", name, assignment_id))
            row_issues.append("lock before due")
        if unlock and lock and unlock > lock:
            issues.append(_issue("unlock_after_lock", "warning", f"Unlocks {_format_local(unlock)}, after it locks {_format_local(lock)}.", name, assignment_id))
            row_issues.append("unlock after lock")
        if assignment.get("has_overrides"):
            issues.append(_issue("has_overrides", "review", "Differentiated assignment dates are present; review the assignment's Assign To settings.", name, assignment_id))
            row_issues.append("has overrides")

        rows.append({
            "id": assignment_id,
            "name": name,
            "assignment_group": group_names.get(str(assignment.get("assignment_group_id"))) or "",
            "points_possible": assignment.get("points_possible"),
            "published": assignment.get("published"),
            "week_number": week_number,
            "week_label": week_label,
            "weekday": due.strftime("%A") if due else "",
            "date_local": _format_date(due),
            "time_local": _format_time(due),
            "due_at": assignment.get("due_at"),
            "due_local": _format_local(due),
            "unlock_at": assignment.get("unlock_at"),
            "unlock_local": _format_local(unlock),
            "lock_at": assignment.get("lock_at"),
            "lock_local": _format_local(lock),
            "has_overrides": bool(assignment.get("has_overrides")),
            "notes": notes,
            "issues": row_issues,
            "_due": due,
        })

    for day, members in sorted(dated_days.items()):
        if len(members) >= 3:
            names = ", ".join(str(item.get("name") or item.get("id")) for item in members)
            issues.append(_issue("date_clump", "review", f"{len(members)} graded items are due on {day.isoformat()}: {names}."))

    common_time: str | None = None
    common_time_count = 0
    if due_times:
        common_time, common_time_count = due_times.most_common(1)[0]
        dated_count_for_time = sum(due_times.values())
        if common_time_count >= 3 and common_time_count / dated_count_for_time >= 0.60:
            common_display = datetime.strptime(common_time, "%H:%M").strftime("%I:%M %p").lstrip("0")
            for row in rows:
                due = row.get("_due")
                if isinstance(due, datetime) and due.strftime("%H:%M") != common_time:
                    issues.append(_issue("due_time_outlier", "review", f"Due at {due.strftime('%I:%M %p').lstrip('0')}; most dated graded items are due at {common_display}.", row["name"], row["id"]))
                    row["issues"].append("due-time outlier")

    module_rows: list[dict[str, Any]] = []
    for module in modules:
        if not isinstance(module, dict):
            continue
        module_id = module.get("id")
        module_name = str(module.get("name") or f"Module {module_id or '?'}")
        unlock = _local(module.get("unlock_at"), zone)
        module_issues: list[str] = []
        week_number: int | None = None
        week_label = ""
        if unlock is not None:
            day = unlock.date()
            week_number, week_label, week_kind = _week_fields(semester_weeks, day)
            if start_date and day < start_date:
                issues.append(_issue("module_unlock_before_term", "warning", f"Unlocks {_format_local(unlock)}, before the first class day on {start_date.isoformat()}.", module=module_name, module_id=module_id))
                module_issues.append("before first class")
            if end_date and day > end_date:
                issues.append(_issue("module_unlock_after_term", "warning", f"Unlocks {_format_local(unlock)}, after the last class day on {end_date.isoformat()}.", module=module_name, module_id=module_id))
                module_issues.append("after last class")
            if week_kind == "break":
                issues.append(_issue("module_unlock_break_week", "warning", f"Unlocks {_format_local(unlock)} during the unnumbered {week_label} week.", module=module_name, module_id=module_id))
                module_issues.append(week_label)
            for period in holiday_periods:
                if _date_range_contains(period, day):
                    period_name = str(period.get("name") or "no-class day")
                    issues.append(_issue("module_unlock_no_class_day", "warning", f"Unlocks {_format_local(unlock)} during {period_name}.", module=module_name, module_id=module_id))
                    module_issues.append(period_name)

        module_rows.append({
            "id": module_id,
            "name": module_name,
            "published": module.get("published"),
            "week_number": week_number,
            "week_label": week_label,
            "weekday": unlock.strftime("%A") if unlock else "",
            "date_local": _format_date(unlock),
            "time_local": _format_time(unlock),
            "unlock_at": module.get("unlock_at"),
            "unlock_local": _format_local(unlock),
            "issues": module_issues,
        })

    rows.sort(key=lambda row: (row.get("_due") is None, row.get("_due") or datetime.max.replace(tzinfo=zone), str(row.get("name"))))
    for row in rows:
        row.pop("_due", None)

    dated_rows = [row for row in rows if row.get("due_at")]
    due_dates = sorted({(_local(row.get("due_at"), zone) or datetime.min.replace(tzinfo=zone)).date() for row in dated_rows})
    largest_gap: dict[str, Any] | None = None
    if len(due_dates) >= 2:
        gaps = [(right - left).days for left, right in zip(due_dates, due_dates[1:])]
        index = max(range(len(gaps)), key=gaps.__getitem__)
        largest_gap = {"days": gaps[index], "from": due_dates[index].isoformat(), "to": due_dates[index + 1].isoformat()}

    instructional_weeks = max((week.week_number or 0 for week in semester_weeks), default=0)
    summary = {
        "assignments": len(rows),
        "dated": len(dated_rows),
        "missing_due_date": len(rows) - len(dated_rows),
        "instructional_weeks": instructional_weeks,
        "issue_count": len(issues),
        "warnings": sum(1 for item in issues if item.get("severity") == "warning"),
        "reviews": sum(1 for item in issues if item.get("severity") == "review"),
        "due_weekdays": dict(sorted(weekdays.items())),
        "common_due_time": common_time,
        "common_due_time_count": common_time_count,
        "largest_due_date_gap": largest_gap,
    }

    report = {
        "schema_version": 5,
        "course_id": manifest.get("course_id"),
        "course_name": manifest.get("course_name"),
        "course_code": manifest.get("course_code"),
        "read_only": True,
        "logic": "structured_fields_only",
        "calendar": calendar,
        "semester_weeks": [week_to_dict(week) for week in semester_weeks],
        "summary": summary,
        "issues": issues,
        "assignments": rows,
        "module_unlocks": module_rows,
    }
    json_path = snapshot / "date-audit.json"
    markdown_path = snapshot / "date-audit.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "# Canvas date audit",
        "",
        f"- Course: **{manifest.get('course_name', 'unnamed course')}**",
        f"- Course code: `{manifest.get('course_code', '')}`",
        f"- Canvas course ID: `{manifest.get('course_id', '')}`",
        f"- Time zone: `{time_zone_name}`",
        "- Mode: **read-only**. Names and titles are not interpreted; checks use structured Canvas/calendar fields only.",
    ]
    if calendar:
        lines.extend([
            f"- Calendar: **{calendar.get('name', 'unnamed calendar')}**",
            f"- First day of class: **{start_date:%A, %B} {start_date.day}, {start_date.year}**" if start_date else "",
            f"- Last day of class: **{end_date:%A, %B} {end_date.day}, {end_date.year}**" if end_date else "",
            "",
            "## Semester week reference",
            "",
            render_week_table(semester_weeks),
        ])
    else:
        lines.append("- Calendar: **none matched**")

    lines.extend(["", "## Attention needed", ""])
    if issues:
        for item in issues:
            label = item.get("assignment") or item.get("module")
            prefix = f" **{label}**:" if label else ""
            lines.append(f"- **{str(item.get('severity', 'review')).upper()}**{prefix} {item.get('message', '')}")
    else:
        lines.append("None found.")

    lines.extend([
        "",
        "## Graded item schedule",
        "",
        "| Week | Day | Date | Time | Item | Group | Points | Published | Notes |",
        "|---:|---|---|---|---|---|---:|---|---|",
    ])
    for row in rows:
        week = "" if row.get("week_number") is None else str(row.get("week_number"))
        if row.get("week_number") is None and row.get("week_label"):
            week = str(row.get("week_label"))
        if not row.get("due_at"):
            lines.append(f"|  |  | **NO DUE DATE** |  | {row['name']} | {row['assignment_group']} | {row.get('points_possible') if row.get('points_possible') is not None else ''} | {row.get('published')} | {'; '.join(row.get('issues') or [])} |")
        else:
            lines.append(f"| {week} | {row['weekday']} | {row['date_local']} | {row['time_local']} | {row['name']} | {row['assignment_group']} | {row.get('points_possible') if row.get('points_possible') is not None else ''} | {row.get('published')} | {'; '.join(row.get('issues') or [])} |")

    lines.extend(["", "## Module unlock dates", ""])
    dated_modules = [row for row in module_rows if row.get("unlock_at")]
    if not dated_modules:
        lines.append("No module unlock dates are set.")
    else:
        lines.extend([
            "| Week | Day | Date | Time | Module | Published | Notes |",
            "|---:|---|---|---|---|---|---|",
        ])
        for row in dated_modules:
            week = "" if row.get("week_number") is None else str(row.get("week_number"))
            if row.get("week_number") is None and row.get("week_label"):
                week = str(row.get("week_label"))
            lines.append(f"| {week} | {row['weekday']} | {row['date_local']} | {row['time_local']} | {row['name']} | {row.get('published')} | {'; '.join(row.get('issues') or [])} |")

    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return DateAuditResult(
        markdown_path=markdown_path,
        json_path=json_path,
        calendar_name=str(calendar.get("name")) if calendar else None,
        assignment_count=len(rows),
        dated_count=len(dated_rows),
        undated_count=len(rows) - len(dated_rows),
        issue_count=len(issues),
    )
