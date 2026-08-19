from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .date_audit import audit_dates
from .duplicates import audit_snapshot
from .structure import audit_week_structure


@dataclass(frozen=True)
class CourseAuditResult:
    markdown_path: Path
    json_path: Path
    duplicate_count: int
    date_issue_count: int
    structure_issue_count: int


def audit_course(snapshot: Path, root: Path, calendar_path: Path | None = None) -> CourseAuditResult:
    snapshot = snapshot.resolve()
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))

    duplicate_result = audit_snapshot(snapshot)
    date_result = audit_dates(snapshot, root, calendar_path)
    structure = audit_week_structure(snapshot)

    duplicate_report = json.loads(duplicate_result.json_path.read_text(encoding="utf-8"))
    date_report = json.loads(date_result.json_path.read_text(encoding="utf-8"))

    duplicate_count = (
        len(duplicate_report.get("high_confidence") or [])
        + len(duplicate_report.get("review") or [])
        + len(duplicate_report.get("similar_names") or [])
    )
    date_issues = list(date_report.get("issues") or [])
    structure_issues = list(structure.get("issues") or [])

    report = {
        "schema_version": 1,
        "course_id": manifest.get("course_id"),
        "course_name": manifest.get("course_name"),
        "course_code": manifest.get("course_code"),
        "read_only": True,
        "summary": {
            "duplicate_candidates": duplicate_count,
            "date_issues": len(date_issues),
            "structure_issues": len(structure_issues),
        },
        "structure": structure,
        "date_issues": date_issues,
        "duplicates": {
            "high_confidence": duplicate_report.get("high_confidence") or [],
            "review": duplicate_report.get("review") or [],
            "similar_names": duplicate_report.get("similar_names") or [],
        },
        "reports": {
            "date": str(date_result.markdown_path),
            "duplicates": str(duplicate_result.markdown_path),
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
        "- Mode: **read-only**. No Canvas content or dates were modified.",
        "",
        "## Summary",
        "",
        f"- Weekly structure issues: **{len(structure_issues)}**",
        f"- Date/schedule issues: **{len(date_issues)}**",
        f"- Duplicate-content candidates: **{duplicate_count}**",
        "",
        "## Weekly structure issues",
        "",
    ]

    if structure_issues:
        for item in structure_issues:
            lines.append(f"- **{item['severity'].upper()}**: {item['message']}")
    else:
        lines.append("None found.")

    lines.extend(["", "## Date and schedule issues", ""])
    if date_issues:
        for item in date_issues:
            assignment = f" **{item['assignment']}**:" if item.get("assignment") else ""
            lines.append(f"- **{item['severity'].upper()}**{assignment} {item['message']}")
    else:
        lines.append("None found.")

    lines.extend(["", "## Duplicate-content candidates", ""])
    for key, title in (
        ("high_confidence", "Same name and normalized content"),
        ("review", "Same name, different content"),
        ("similar_names", "Similar names"),
    ):
        items = list(duplicate_report.get(key) or [])
        lines.append(f"### {title}")
        lines.append("")
        if not items:
            lines.append("None found.")
            lines.append("")
            continue
        for item in items:
            if item.get("name"):
                lines.append(f"- **{item.get('resource_label', item.get('resource', 'Resource'))}**: `{item['name']}` ({item.get('count', '?')} copies)")
            else:
                lines.append(f"- **{item.get('resource_label', item.get('resource', 'Resource'))}**: `{item.get('left', '')}` ↔ `{item.get('right', '')}`")
        lines.append("")

    lines.extend([
        "## Detailed reports",
        "",
        f"- Date audit: `{date_result.markdown_path}`",
        f"- Duplicate audit: `{duplicate_result.markdown_path}`",
        "",
    ])
    markdown_path.write_text("\n".join(lines), encoding="utf-8")

    return CourseAuditResult(
        markdown_path=markdown_path,
        json_path=json_path,
        duplicate_count=duplicate_count,
        date_issue_count=len(date_issues),
        structure_issue_count=len(structure_issues),
    )
