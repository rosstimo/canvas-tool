from __future__ import annotations

from pathlib import Path

from .course_overview import CourseOverviewResult, build_overview as _build_overview


def _simplify_report_wording(text: str) -> str:
    text = text.replace(
        "- Mode: **read-only**. Names and titles are displayed but never interpreted as schedule or placement configuration.",
        "- Mode: **read-only**. No Canvas content is changed.",
    )
    text = text.replace(
        "Calculated week numbers in this report come from the semester calendar, not from item or module names. Weeks run Sunday-Saturday; configured break weeks remain visible but are unnumbered.",
        "Weeks run Sunday-Saturday; configured break weeks remain visible but are unnumbered.",
    )
    return text


def build_overview(snapshot: Path) -> CourseOverviewResult:
    result = _build_overview(snapshot)
    text = result.markdown_path.read_text(encoding="utf-8")
    simplified = _simplify_report_wording(text)
    if simplified != text:
        result.markdown_path.write_text(simplified, encoding="utf-8")
    return result


__all__ = ["CourseOverviewResult", "build_overview"]
