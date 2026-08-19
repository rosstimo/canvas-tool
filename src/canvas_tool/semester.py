from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any


@dataclass(frozen=True)
class SemesterWeek:
    calendar_start: date
    calendar_end: date
    active_start: date
    active_end: date
    week_number: int | None
    label: str
    kind: str
    notes: tuple[str, ...] = ()

    def contains(self, day: date) -> bool:
        return self.calendar_start <= day <= self.calendar_end


def parse_date(value: Any, field: str = "date") -> date:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {field}: {value!r}; expected YYYY-MM-DD") from exc


def _period_bounds(period: dict[str, Any]) -> tuple[date, date]:
    start = parse_date(period.get("start"), "period start")
    end = parse_date(period.get("end") or period.get("start"), "period end")
    if end < start:
        raise ValueError(f"Period ends before it starts: {period!r}")
    return start, end


def _overlaps(left_start: date, left_end: date, right_start: date, right_end: date) -> bool:
    return left_start <= right_end and right_start <= left_end


def semester_bounds(calendar: dict[str, Any]) -> tuple[date, date]:
    first = calendar.get("first_class_date", calendar.get("start_date"))
    last = calendar.get("last_class_date", calendar.get("end_date"))
    start = parse_date(first, "first class date")
    end = parse_date(last, "last class date")
    if end < start:
        raise ValueError("Last class date must be on or after first class date")
    return start, end


def build_semester_weeks(
    first_class_date: date,
    last_class_date: date,
    break_weeks: list[dict[str, Any]] | None = None,
    holidays: list[dict[str, Any]] | None = None,
    special_periods: list[dict[str, Any]] | None = None,
) -> list[SemesterWeek]:
    if last_class_date < first_class_date:
        raise ValueError("Last class date must be on or after first class date")

    breaks = list(break_weeks or [])
    holiday_periods = list(holidays or [])
    specials = list(special_periods or [])

    calendar_start = first_class_date - timedelta(days=first_class_date.weekday())
    calendar_end = last_class_date + timedelta(days=(6 - last_class_date.weekday()))
    cursor = calendar_start
    week_number = 0
    result: list[SemesterWeek] = []

    while cursor <= calendar_end:
        week_end = cursor + timedelta(days=6)
        active_start = max(cursor, first_class_date)
        active_end = min(week_end, last_class_date)

        matching_breaks: list[str] = []
        for period in breaks:
            start, end = _period_bounds(period)
            if _overlaps(cursor, week_end, start, end):
                matching_breaks.append(str(period.get("name") or "Break"))

        notes: list[str] = []
        for period in holiday_periods + specials:
            start, end = _period_bounds(period)
            if _overlaps(cursor, week_end, start, end):
                notes.append(str(period.get("name") or "Special date"))

        if matching_breaks:
            label = " / ".join(dict.fromkeys(matching_breaks))
            kind = "break"
            number = None
        else:
            week_number += 1
            label = f"Week {week_number}"
            kind = "instruction"
            number = week_number

        result.append(SemesterWeek(
            calendar_start=cursor,
            calendar_end=week_end,
            active_start=active_start,
            active_end=active_end,
            week_number=number,
            label=label,
            kind=kind,
            notes=tuple(dict.fromkeys(notes)),
        ))
        cursor += timedelta(days=7)

    return result


def weeks_from_calendar(calendar: dict[str, Any]) -> list[SemesterWeek]:
    first, last = semester_bounds(calendar)
    breaks = list(calendar.get("break_weeks") or [])
    holidays = list(calendar.get("holidays") or calendar.get("no_class_periods") or [])
    specials = list(calendar.get("special_periods") or [])
    return build_semester_weeks(first, last, breaks, holidays, specials)


def week_for_date(weeks: list[SemesterWeek], day: date) -> SemesterWeek | None:
    for week in weeks:
        if week.contains(day):
            return week
    return None


def format_range(start: date, end: date) -> str:
    if start.year != end.year:
        return f"{start:%b} {start.day}, {start.year} - {end:%b} {end.day}, {end.year}"
    if start.month != end.month:
        return f"{start:%b} {start.day} - {end:%b} {end.day}, {end.year}"
    return f"{start:%b} {start.day}-{end.day}, {end.year}"


def render_week_table(weeks: list[SemesterWeek]) -> str:
    lines = ["| Semester week | Dates | Notes |", "|---|---|---|"]
    for week in weeks:
        notes = "; ".join(week.notes)
        lines.append(f"| {week.label} | {format_range(week.active_start, week.active_end)} | {notes} |")
    return "\n".join(lines)


def week_to_dict(week: SemesterWeek) -> dict[str, Any]:
    return {
        "week_number": week.week_number,
        "label": week.label,
        "kind": week.kind,
        "calendar_start": week.calendar_start.isoformat(),
        "calendar_end": week.calendar_end.isoformat(),
        "start": week.active_start.isoformat(),
        "end": week.active_end.isoformat(),
        "notes": list(week.notes),
    }
