from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .semester import (
    day_to_dict,
    days_from_calendar,
    format_day,
    render_week_table,
    semester_bounds,
    week_for_date,
    week_to_dict,
    weeks_from_calendar,
)


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
    hour = value.strftime("%I:%M %p").lstrip("0")
    return f"{value:%A, %B} {value.day}, {value.year} {hour} {value.tzname() or ''}".strip()


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


def _load_calendar_file(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Calendar must contain a JSON object: {path}")
    data["_path"] = str(path)
    return data


def find_calendar(
    root: Path,
    manifest: dict[str, Any],
    course: dict[str, Any],
    explicit: Path | None = None,
) -> dict[str, Any] | None:
    if explicit is not None:
        return _load_calendar_file(explicit.expanduser().resolve())

    host = (urlparse(str(manifest.get("base_url") or "")).hostname or "").casefold()
    term_name = str((course.get("term") or {}).get("name") or "").casefold()
    calendar_dir = root / "calendars"
    if not calendar_dir.is_dir():
        return None

    for path in sorted(calendar_dir.glob("*.json")):
        try:
            data = _load_calendar_file(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        calendar_host = str(data.get("canvas_host") or "").casefold()
        calendar_term = str(data.get("term_name") or "").casefold()
        if calendar_host == host and calendar_term == term_name:
            return data
    return None


def _issue(
    code: str,
    severity: str,
    message: str,
    assignment: str | None = None,
    assignment_id: Any = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {"code": code, "severity": severity, "message": message}
    if assignment is not None:
        result["assignment"] = assignment
    if assignment_id is not None:
        result["assignment_id"] = assignment_id
    return result


def audit_dates(snapshot: Path, root: Path, calendar_path: Path | None = None) -> DateAuditResult:
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
    semester_weeks = []
    semester_days = []
    break_periods: list[dict[str, Any]] = []
    holiday_periods: list[dict[str, Any]] = []
    special_periods: list[dict[str, Any]] = []

    if calendar:
        start_date, end_date = semester_bounds(calendar)
        semester_weeks = weeks_from_calendar(calendar)
        semester_days = days_from_calendar(calendar)
        break_periods = list(calendar.get("break_weeks") or [])
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
        notes: list[str] = []
        row_issues: list[str] = []
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

            semester_week = week_for_date(semester_weeks, day) if semester_weeks else None
            if semester_week is not None:
                week_number = semester_week.week_number
                week_label = semester_week.label

            if start_date and day < start_date:
                message = f"Due {_format_local(due)}, before the first class day on {start_date.isoformat()}."
                issues.append(_issue("before_term", "warning", message, name, assignment_id))
                row_issues.append("before first class")
            if end_date and day > end_date:
                message = f"Due {_format_local(due)}, after the last class day on {end_date.isoformat()}."
                issues.append(_issue("after_term", "warning", message, name, assignment_id))
                row_issues.append("after last class")

            for period in break_periods + holiday_periods:
                if _date_range_contains(period, day):
                    period_name = str(period.get("name") or "no-class period")
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
            issues.append(_issue("has_overrides", "review", "Differentiated assignment dates are present; review overrides separately.", name, assignment_id))
            row_issues.append("has overrides")

        rows.append({
            "id": assignment_id,
            "name": name,
            "assignment_group": group_names.get(str(assignment.get("assignment_group_id"))) or "",
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
            issues.append(_issue("date_clump", "review", f"{len(members)} assignments are due on {day.isoformat()}: {names}."))

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
                    issues.append(_issue("due_time_outlier", "review", f"Due at {due.strftime('%I:%M %p').lstrip('0')}; most dated assignments are due at {common_display}.", row["name"], row["id"]))
                    row["issues"].append("due-time outlier")

    distinct_days = sorted(dated_days)
    largest_gap: dict[str, Any] | None = None
    if len(distinct_days) >= 2:
        gap_start, gap_end = max(zip(distinct_days, distinct_days[1:]), key=lambda pair: (pair[1] - pair[0]).days)
        largest_gap = {"from": gap_start.isoformat(), "to": gap_end.isoformat(), "days": (gap_end - gap_start).days}

    module_rows: list[dict[str, Any]] = []
    for module in modules:
        if not isinstance(module, dict) or not module.get("unlock_at"):
            continue
        unlock = _local(module.get("unlock_at"), zone)
        unlock_week = week_for_date(semester_weeks, unlock.date()) if unlock and semester_weeks else None
        module_rows.append({
            "id": module.get("id"),
            "name": module.get("name") or "",
            "week_number": unlock_week.week_number if unlock_week else None,
            "week_label": unlock_week.label if unlock_week else "",
            "weekday": unlock.strftime("%A") if unlock else "",
            "date_local": _format_date(unlock),
            "time_local": _format_time(unlock),
            "unlock_at": module.get("unlock_at"),
            "unlock_local": _format_local(unlock),
        })

    dated_count = sum(1 for row in rows if row.get("due_at"))
    undated_count = len(rows) - dated_count
    instructional_weeks = max((item.week_number or 0 for item in semester_weeks), default=0)
    report = {
        "schema_version": 3,
        "course_id": manifest.get("course_id"),
        "course_name": manifest.get("course_name"),
        "course_code": manifest.get("course_code"),
        "read_only": True,
        "time_zone": time_zone_name,
        "calendar": None if calendar is None else {key: value for key, value in calendar.items() if key != "_path"},
        "semester_weeks": [week_to_dict(item) for item in semester_weeks],
        "semester_days": [day_to_dict(item) for item in semester_days],
        "summary": {
            "assignments": len(rows),
            "dated": dated_count,
            "undated": undated_count,
            "issues": len(issues),
            "instructional_weeks": instructional_weeks,
            "due_weekdays": dict(weekdays),
            "due_times": dict(due_times),
            "common_due_time": common_time,
            "common_due_time_count": common_time_count,
            "largest_due_date_gap": largest_gap,
        },
        "issues": issues,
        "assignments": [{key: value for key, value in row.items() if key != "_due"} for row in rows],
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
        "- Mode: **read-only**. No Canvas dates were modified.",
    ]
    if calendar:
        lines.append(f"- Calendar: **{calendar.get('name', 'matched calendar')}**")
        if calendar.get("source_name"):
            lines.append(f"- Calendar source: {calendar['source_name']}")
        if start_date and end_date:
            lines.append(f"- First day of class: **{format_day(start_date)}**")
            lines.append(f"- Last day of class: **{format_day(end_date)}**")
        lines.extend(["", "## Semester week reference", "", render_week_table(semester_weeks), ""])
    else:
        lines.append("- Calendar: **none matched**. Week numbering and institutional break checks were skipped.")

    lines.extend(["", "## Attention needed", ""])
    if not issues:
        lines.extend(["No date problems or review flags were detected.", ""])
    else:
        for item in issues:
            prefix = item["severity"].upper()
            assignment = f" **{item['assignment']}**:" if item.get("assignment") else ""
            lines.append(f"- **{prefix}**{assignment} {item['message']}")
        lines.append("")

    lines.extend([
        "## Assignment schedule",
        "",
        "| Week | Day | Date | Time | Assignment | Group | Availability | Notes |",
        "|---:|---|---|---|---|---|---|---|",
    ])
    ordered_rows = sorted(rows, key=lambda item: (item.get("_due") is None, item.get("_due") or datetime.max.replace(tzinfo=zone), item.get("name") or ""))
    for row in ordered_rows:
        availability_parts = []
        if row["unlock_local"]:
            availability_parts.append(f"opens {row['unlock_local']}")
        if row["lock_local"]:
            availability_parts.append(f"locks {row['lock_local']}")
        note_parts = list(row["notes"]) + list(row["issues"])
        week_text = "" if row["week_number"] is None else str(row["week_number"])
        lines.append("| " + " | ".join([
            week_text,
            row["weekday"],
            row["date_local"] or "**NO DUE DATE**",
            row["time_local"],
            str(row["name"]).replace("|", "\\|"),
            str(row["assignment_group"]).replace("|", "\\|"),
            "; ".join(availability_parts).replace("|", "\\|"),
            "; ".join(note_parts).replace("|", "\\|"),
        ]) + " |")

    lines.extend(["", "## Patterns", "", f"- Assignments: **{len(rows)}** total; **{dated_count}** dated; **{undated_count}** without a due date."])
    if instructional_weeks:
        lines.append(f"- Numbered instructional weeks: **{instructional_weeks}**.")
    if weekdays:
        weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        weekday_text = ", ".join(f"{day} {weekdays[day]}" for day in weekday_order if weekdays.get(day))
        lines.append(f"- Due weekdays: {weekday_text}.")
    if common_time:
        common_display = datetime.strptime(common_time, "%H:%M").strftime("%I:%M %p").lstrip("0")
        lines.append(f"- Most common due time: **{common_display}** ({common_time_count}/{dated_count} dated assignments).")
    if largest_gap:
        lines.append(f"- Largest gap between due dates: **{largest_gap['days']} days**, from {largest_gap['from']} to {largest_gap['to']}.")

    lines.extend(["", "## Module unlock dates", ""])
    if module_rows:
        lines.extend(["| Week | Day | Date | Time | Module |", "|---:|---|---|---|---|"])
        for module in module_rows:
            week_text = "" if module["week_number"] is None else str(module["week_number"])
            lines.append(f"| {week_text} | {module['weekday']} | {module['date_local']} | {module['time_local']} | {str(module['name']).replace('|', '\\|')} |")
    else:
        lines.append("No module unlock dates are set.")

    lines.extend(["", "## Notes", "", "Assignments with differentiated overrides are flagged for manual review, but this audit does not request student-specific effective due dates or submission data.", ""])
    markdown_path.write_text("\n".join(lines), encoding="utf-8")

    return DateAuditResult(
        markdown_path=markdown_path,
        json_path=json_path,
        calendar_name=str(calendar.get("name")) if calendar else None,
        assignment_count=len(rows),
        dated_count=dated_count,
        undated_count=undated_count,
        issue_count=len(issues),
    )
