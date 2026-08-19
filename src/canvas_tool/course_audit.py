from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .overview import build_overview
from .report_index import refresh_report_index
from .schedule_audit import audit_dates


@dataclass(frozen=True)
class CourseAuditResult:
    markdown_path: Path
    json_path: Path
    schedule_issue_count: int
    unplaced_graded_item_count: int
    recon_error_count: int


def audit_course(snapshot: Path, root: Path, calendar_path: Path | None = None) -> CourseAuditResult:
    """Run convention-free checks and produce a compact audit beside the full overview."""
    snapshot = snapshot.resolve()
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))

    date_result = audit_dates(snapshot, root, calendar_path)
    overview_result = build_overview(snapshot)
    date_report = json.loads(date_result.json_path.read_text(encoding="utf-8"))
    overview_report = json.loads(overview_result.json_path.read_text(encoding="utf-8"))
    recon_errors = json.loads((snapshot / "errors.json").read_text(encoding="utf-8"))

    schedule_issues = list(date_report.get("issues") or [])
    unplaced = list(overview_report.get("graded_items_not_in_modules") or [])

    report = {
        "schema_version": 2,
        "course_id": manifest.get("course_id"),
        "course_name": manifest.get("course_name"),
        "course_code": manifest.get("course_code"),
        "read_only": True,
        "logic": "structured_fields_only",
        "summary": {
            "schedule_issues": len(schedule_issues),
            "graded_items_not_in_modules": len(unplaced),
            "recon_errors": len(recon_errors),
        },
        "schedule_issues": schedule_issues,
        "graded_items_not_in_modules": unplaced,
        "recon_errors": recon_errors,
        "reports": {
            "overview": str(overview_result.markdown_path),
            "dates": str(date_result.markdown_path),
        },
    }

    json_path = snapshot / "course-audit.json"
    markdown_path = snapshot / "course-audit.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "# Course audit",
        "",
        f"- Course: **{manifest.get('course_name', 'unnamed course')}**",
        f"- Course code: `{manifest.get('course_code', '')}`",
        f"- Canvas course ID: `{manifest.get('course_id', '')}`",
        "- Mode: **read-only**. No Canvas content is changed.",
        "",
        "## Summary",
        "",
        f"- Schedule / availability flags: **{len(schedule_issues)}**",
        f"- Graded items not represented in any module: **{len(unplaced)}**",
        f"- Recon retrieval errors: **{len(recon_errors)}**",
        "",
        "## Schedule / availability flags",
        "",
    ]

    if schedule_issues:
        for item in schedule_issues:
            label = item.get("assignment") or item.get("module")
            prefix = f" **{label}**:" if label else ""
            lines.append(f"- **{str(item.get('severity', 'review')).upper()}**{prefix} {item.get('message', '')}")
    else:
        lines.append("None found.")

    lines.extend(["", "## Graded items not represented in a module", ""])
    if unplaced:
        lines.append("These are inventory findings, not automatic errors.")
        lines.append("")
        for item in unplaced:
            lines.append(
                f"- **{item.get('name', 'unnamed item')}**: {item.get('type', 'Assignment')}; "
                f"due {item.get('due', '—')}; group {item.get('assignment_group', '—')}; "
                f"points {item.get('points') if item.get('points') is not None else '—'}; "
                f"published {item.get('published')}"
            )
    else:
        lines.append("None found.")

    lines.extend([
        "",
        "## Detailed reports",
        "",
        f"- [Full course overview]({overview_result.markdown_path.name})",
        f"- [Date audit]({date_result.markdown_path.name})",
        "",
    ])
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    refresh_report_index(snapshot)

    return CourseAuditResult(
        markdown_path=markdown_path,
        json_path=json_path,
        schedule_issue_count=len(schedule_issues),
        unplaced_graded_item_count=len(unplaced),
        recon_error_count=len(recon_errors),
    )
