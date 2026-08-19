from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from .course_overview import CourseOverviewResult, build_overview as _build_overview
from .report_index import refresh_report_index


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


def _new_quiz_assignment_ids(snapshot: Path) -> set[str]:
    try:
        quizzes = json.loads((snapshot / "new-quizzes.json").read_text(encoding="utf-8"))
        assignments = json.loads((snapshot / "assignments.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

    assignment_ids = {
        str(item.get("id"))
        for item in assignments
        if isinstance(item, dict) and item.get("id") is not None
    }
    result: set[str] = set()
    for quiz in quizzes:
        if not isinstance(quiz, dict):
            continue
        explicit = quiz.get("assignment_id")
        if explicit is not None:
            result.add(str(explicit))
            continue

        # Some Canvas New Quiz responses omit assignment_id while returning the
        # associated assignment ID as the quiz object's own id.
        fallback = quiz.get("id")
        if fallback is not None and str(fallback) in assignment_ids:
            result.add(str(fallback))
    return result


def _fix_new_quiz_types(snapshot: Path, text: str) -> str:
    quiz_assignment_ids = _new_quiz_assignment_ids(snapshot)
    if not quiz_assignment_ids:
        return text

    json_path = snapshot / "course-overview.json"
    try:
        report = json.loads(json_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        report = None

    if isinstance(report, dict):
        changed = False
        for item in report.get("graded_items_not_in_modules") or []:
            if not isinstance(item, dict):
                continue
            assignment_id = item.get("id")
            if assignment_id is not None and str(assignment_id) in quiz_assignment_ids:
                if item.get("type") != "New Quiz":
                    item["type"] = "New Quiz"
                    changed = True
        if changed:
            json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = text.splitlines()
    for index, line in enumerate(lines):
        for assignment_id in quiz_assignment_ids:
            if f'id="graded-item-{assignment_id}"' in line and "| External tool |" in line:
                lines[index] = line.replace("| External tool |", "| New Quiz |", 1)
                break
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


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

    return _fix_new_quiz_types(snapshot, text)


def build_overview(snapshot: Path) -> CourseOverviewResult:
    snapshot = snapshot.resolve()
    result = _build_overview(snapshot)
    text = result.markdown_path.read_text(encoding="utf-8")
    finished = _finish_report(snapshot, text)
    if finished != text:
        result.markdown_path.write_text(finished, encoding="utf-8")
    refresh_report_index(snapshot)
    return result


__all__ = ["CourseOverviewResult", "build_overview"]
