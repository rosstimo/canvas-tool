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


@dataclass(frozen=True)
class SemesterDay:
    day: date
    week_number: int | None
    week_label: str
    kind: str
    notes: tuple[str, ...] = ()


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


def _period_names_for_day(periods: list[dict[str, Any]], day: date) -> list[str]:
    names: list[str] = []
    for period in periods:
        start, end = _period_bounds(period)
        if start <= day <= end:
            names.append(str(period.get("name") or "Special date"))
    return names


def _period_names_for_week(periods: list[dict[str, Any]], start: date, end: date) -> list[str]:
    names: list[str] = []
    for period in periods:
        period_start, period_end = _period_bounds(period)
        if _overlaps(start, end, period_start, period_end):
            names.append(str(period.get("name") or "Special date"))
    return names


def _sunday_on_or_before(day: date) -> date:
    # date.weekday(): Monday=0 ... Sunday=6
    return day - timedelta(days=(day.weekday() + 1) % 7)


def _saturday_on_or_after(day: date) -> date:
    # Saturday is weekday 5.
    return day + timedelta(days=(5 - day.weekday()) % 7)


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
    calendar_start = _sunday_on_or_before(first_class_date)
    calendar_end = _saturday_on_or_after(last_class_date)
    cursor = calendar_start
    week_number = 0
    result: list[SemesterWeek] = []

    while cursor <= calendar_end:
        week_end = cursor + timedelta(days=6)
        active_start = max(cursor, first_class_date)
        active_end = min(week_end, last_class_date)

        matching_breaks = _period_names_for_week(breaks, cursor, week_end)
        notes = _period_names_for_week(holiday_periods + specials, cursor, week_end)

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
    return build_semester_weeks(
        first,
        last,
        break_weeks=list(calendar.get("break_weeks") or []),
        holidays=list(calendar.get("holidays") or calendar.get("no_class_periods") or []),
        special_periods=list(calendar.get("special_periods") or []),
    )


def week_for_date(weeks: list[SemesterWeek], day: date) -> SemesterWeek | None:
    for week in weeks:
        if week.contains(day):
            return week
    return None


def build_semester_days(
    first_class_date: date,
    last_class_date: date,
    break_weeks: list[dict[str, Any]] | None = None,
    holidays: list[dict[str, Any]] | None = None,
    special_periods: list[dict[str, Any]] | None = None,
    weekdays_only: bool = True,
) -> list[SemesterDay]:
    breaks = list(break_weeks or [])
    holiday_periods = list(holidays or [])
    specials = list(special_periods or [])
    weeks = build_semester_weeks(
        first_class_date,
        last_class_date,
        break_weeks=breaks,
        holidays=holiday_periods,
        special_periods=specials,
    )
    result: list[SemesterDay] = []

    cursor = first_class_date
    while cursor <= last_class_date:
        if not weekdays_only or cursor.weekday() < 5:
            week = week_for_date(weeks, cursor)
            if week is not None:
                notes = (
                    _period_names_for_day(breaks, cursor)
                    + _period_names_for_day(holiday_periods, cursor)
                    + _period_names_for_day(specials, cursor)
                )
                result.append(SemesterDay(
                    day=cursor,
                    week_number=week.week_number,
                    week_label=week.label,
                    kind=week.kind,
                    notes=tuple(dict.fromkeys(notes)),
                ))
        cursor += timedelta(days=1)

    return result


def days_from_calendar(calendar: dict[str, Any], weekdays_only: bool = True) -> list[SemesterDay]:
    first, last = semester_bounds(calendar)
    return build_semester_days(
        first,
        last,
        break_weeks=list(calendar.get("break_weeks") or []),
        holidays=list(calendar.get("holidays") or calendar.get("no_class_periods") or []),
        special_periods=list(calendar.get("special_periods") or []),
        weekdays_only=weekdays_only,
    )


def format_range(start: date, end: date) -> str:
    if start.year != end.year:
        return f"{start:%B} {start.day}, {start.year} - {end:%B} {end.day}, {end.year}"
    if start.month != end.month:
        return f"{start:%B} {start.day} - {end:%B} {end.day}, {end.year}"
    return f"{start:%B} {start.day}-{end.day}, {end.year}"


def format_day(day: date) -> str:
    return f"{day:%A}, {day:%B} {day.day}, {day.year}"


def render_week_table(weeks: list[SemesterWeek]) -> str:
    lines = ["| Week | Date range (Sunday-Saturday) | Notes |", "|---:|---|---|"]
    for week in weeks:
        week_text = "" if week.week_number is None else str(week.week_number)
        notes = list(week.notes)
        if week.kind == "break":
            notes.insert(0, week.label)
        lines.append(
            f"| {week_text} | {format_range(week.calendar_start, week.calendar_end)} | {'; '.join(dict.fromkeys(notes))} |"
        )
    return "\n".join(lines)


def render_week_text(weeks: list[SemesterWeek]) -> str:
    lines = [f"{'WEEK':<6}{'DATE RANGE (SUNDAY-SATURDAY)':<38}NOTES"]
    for week in weeks:
        week_text = "" if week.week_number is None else str(week.week_number)
        notes = list(week.notes)
        if week.kind == "break":
            notes.insert(0, week.label)
        lines.append(
            f"{week_text:<6}{format_range(week.calendar_start, week.calendar_end):<38}{'; '.join(dict.fromkeys(notes))}"
        )
    return "\n".join(lines)


def render_day_table(days: list[SemesterDay]) -> str:
    lines = ["| Week | Day | Date | Notes |", "|---:|---|---|---|"]
    for item in days:
        week = "" if item.week_number is None else str(item.week_number)
        notes = "; ".join(item.notes)
        lines.append(f"| {week} | {item.day:%A} | {item.day:%B} {item.day.day}, {item.day.year} | {notes} |")
    return "\n".join(lines)


def render_day_text(days: list[SemesterDay]) -> str:
    lines = [f"{'WEEK':<6}{'DAY':<12}{'DATE':<22}NOTES"]
    for item in days:
        week = "" if item.week_number is None else str(item.week_number)
        notes = "; ".join(item.notes)
        day_text = item.day.strftime("%A")
        date_text = f"{item.day:%B} {item.day.day}, {item.day.year}"
        lines.append(f"{week:<6}{day_text:<12}{date_text:<22}{notes}")
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


def day_to_dict(item: SemesterDay) -> dict[str, Any]:
    return {
        "week_number": item.week_number,
        "week_label": item.week_label,
        "kind": item.kind,
        "weekday": item.day.strftime("%A"),
        "date": item.day.isoformat(),
        "notes": list(item.notes),
    }
