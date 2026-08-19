from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from .course_overview import CourseOverviewResult, build_overview as _build_overview


def _format_range(start_value: Any, end_value: Any) -> str:
    try:
        start = date.fromisoformat(str(start_value))
        end = date.fromisoformat(str(end_value))
    except ValueError:
        return f"{start_value} - {end_value}"

    if start.year != end.year:
        return f"{start:%B} {start.day}, {start.year} - {end:%B} {end.day}, {end.year}"
    if start.month != end.month:
        return f"{start:%B} {start.day} - {end:%B} {end.day}, {end.year}"
    return f"{start:%B} {start.day}-{end.day}, {end.year}"


def _week_reference(snapshot: Path) -> str:
    try:
        date_report = json.loads((snapshot / "date-audit.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return ""

    weeks = [item for item in (date_report.get("semester_weeks") or []) if isinstance(item, dict)]
    if not weeks:
        return ""

    lines = [
        "### Week number reference",
        "",
        "| Week | Date range (Sunday-Saturday) | Notes |",
        "|---:|---|---|",
    ]
    for week in weeks:
        number = week.get("week_number")
        week_text = "—" if number is None else str(number)
        notes = [str(value) for value in (week.get("notes") or []) if value]
        if str(week.get("kind") or "") == "break" and week.get("label"):
            notes.insert(0, str(week["label"]))
        lines.append(
            f"| {week_text} | {_format_range(week.get('calendar_start'), week.get('calendar_end'))} | {'; '.join(dict.fromkeys(notes))} |"
        )
    return "\n".join(lines)


def _finish_report(snapshot: Path, text: str) -> str:
    text = text.replace(
        "- Mode: **read-only**. Names and titles are displayed but never interpreted as schedule or placement configuration.",
        "- Mode: **read-only**. No Canvas content is changed.",
    )
    calendar_note = (
        "Calculated week numbers in this report come from the semester calendar, not from item or module names. "
        "Weeks run Sunday-Saturday; configured break weeks remain visible but are unnumbered."
    )
    simple_note = "Weeks run Sunday-Saturday; configured break weeks remain visible but are unnumbered."
    text = text.replace(calendar_note, simple_note)

    reference = _week_reference(snapshot)
    if reference and reference not in text:
        marker = simple_note + "\n"
        text = text.replace(marker, marker + "\n" + reference + "\n", 1)
    return text


def build_overview(snapshot: Path) -> CourseOverviewResult:
    result = _build_overview(snapshot)
    text = result.markdown_path.read_text(encoding="utf-8")
    finished = _finish_report(snapshot, text)
    if finished != text:
        result.markdown_path.write_text(finished, encoding="utf-8")
    return result


__all__ = ["CourseOverviewResult", "build_overview"]
