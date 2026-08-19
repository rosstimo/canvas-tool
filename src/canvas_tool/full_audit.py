from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .assignment_override_audit import audit_assignment_overrides
from .audit_suite import build_audit_suite
from .link_audit import audit_links
from .question_audit import audit_questions
from .report_index import refresh_report_index


@dataclass(frozen=True)
class FullAuditResult:
    comprehensive_path: Path
    report_paths: tuple[Path, ...]
    finding_count: int
    warning_count: int
    review_count: int
    observation_count: int


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _md(value: Any) -> str:
    return str(value if value is not None else "").replace("\n", " ").replace("\r", " ").replace("|", "\\|")


def _date_findings(snapshot: Path) -> list[dict[str, str]]:
    report = _load(snapshot / "date-audit.json", {})
    findings: list[dict[str, str]] = []
    for issue in report.get("issues") or []:
        if not isinstance(issue, dict):
            continue
        severity = str(issue.get("severity") or "review").casefold()
        if severity not in {"warning", "review", "observation"}:
            severity = "review"
        findings.append({
            "severity": severity,
            "area": "schedule / availability",
            "item": str(issue.get("assignment") or issue.get("module") or ""),
            "message": str(issue.get("message") or issue.get("code") or "Schedule review item"),
            "source_report": "date-audit.md",
        })
    return findings


def _duplicate_findings(snapshot: Path) -> list[dict[str, str]]:
    report = _load(snapshot / "duplicate-audit.json", {})
    findings: list[dict[str, str]] = []

    for item in report.get("high_confidence") or []:
        if not isinstance(item, dict):
            continue
        findings.append({
            "severity": "review",
            "area": "duplicate content",
            "item": str(item.get("name") or ""),
            "message": f"{item.get('resource_label', 'Content')} has {item.get('count', 0)} same-name records with the same normalized content.",
            "source_report": "duplicate-audit.md",
        })

    for item in report.get("review") or []:
        if not isinstance(item, dict):
            continue
        findings.append({
            "severity": "review",
            "area": "duplicate content",
            "item": str(item.get("name") or ""),
            "message": f"{item.get('resource_label', 'Content')} has {item.get('count', 0)} same-name records whose normalized content differs.",
            "source_report": "duplicate-audit.md",
        })

    for item in report.get("similar_names") or []:
        if not isinstance(item, dict):
            continue
        percent = round(float(item.get("similarity") or 0) * 100)
        findings.append({
            "severity": "review",
            "area": "similar-name content",
            "item": f"{item.get('left', '')} ↔ {item.get('right', '')}",
            "message": f"{item.get('resource_label', 'Content')} names are {percent}% similar and are candidates for side-by-side review.",
            "source_report": "duplicate-audit.md",
        })
    return findings


def _report_entry(path: Path, category: str) -> dict[str, str]:
    title = path.stem.replace("-", " ").title()
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                title = line[2:].strip() or title
                break
    except OSError:
        pass
    return {"title": title, "markdown": path.name, "category": category}


def build_full_audit(snapshot: Path) -> FullAuditResult:
    snapshot = snapshot.resolve()
    manifest = _load(snapshot / "manifest.json", {})

    suite = build_audit_suite(snapshot)
    override_result = audit_assignment_overrides(snapshot)
    question_result = audit_questions(snapshot)
    link_result = audit_links(snapshot)

    suite_payload = _load(snapshot / "comprehensive-audit.json", {})
    findings = [dict(item, source_report=str(item.get("source_report") or "specialized audit")) for item in (suite_payload.get("findings") or []) if isinstance(item, dict)]

    for path in (override_result.json_path, question_result.json_path, link_result.json_path):
        payload = _load(path, {})
        source_report = path.with_suffix(".md").name
        for item in payload.get("findings") or []:
            if isinstance(item, dict):
                findings.append({**item, "source_report": source_report})

    findings.extend(_date_findings(snapshot))
    findings.extend(_duplicate_findings(snapshot))

    counts = Counter(str(item.get("severity") or "observation") for item in findings)
    date_report = _load(snapshot / "date-audit.json", {})
    duplicate_report = _load(snapshot / "duplicate-audit.json", {})
    coverage = list(suite_payload.get("coverage") or [])

    reports: list[dict[str, str]] = []
    core_names = [
        "course-overview.md",
        "course-audit.md",
        "date-audit.md",
        "duplicate-audit.md",
        "summary.md",
    ]
    for name in core_names:
        path = snapshot / name
        if path.is_file():
            reports.append(_report_entry(path, "Core / existing"))

    for path in suite.report_paths:
        if path.is_file():
            reports.append(_report_entry(path, "Specialized audit"))
    for path in (override_result.markdown_path, question_result.markdown_path, link_result.markdown_path):
        if path.is_file():
            reports.append(_report_entry(path, "Specialized audit"))

    seen: set[str] = set()
    reports = [item for item in reports if not (item["markdown"] in seen or seen.add(item["markdown"]))]

    summary = {
        "specialized_audit_reports": len(suite.report_paths) + 3,
        "warnings": counts.get("warning", 0),
        "reviews": counts.get("review", 0),
        "observations": counts.get("observation", 0),
        "findings_total": len(findings),
        "schedule_availability_flags": len(date_report.get("issues") or []),
        "duplicate_candidates": (
            len(duplicate_report.get("high_confidence") or [])
            + len(duplicate_report.get("review") or [])
            + len(duplicate_report.get("similar_names") or [])
        ),
        "api_resource_groups_unavailable": sum(1 for item in coverage if isinstance(item, dict) and not item.get("available")),
    }

    payload = {
        "schema_version": 2,
        "course_id": manifest.get("course_id"),
        "course_name": manifest.get("course_name"),
        "course_code": manifest.get("course_code"),
        "read_only": True,
        "student_data_included": False,
        "summary": summary,
        "findings": findings,
        "coverage": coverage,
        "reports": reports,
        "scope_notes": [
            "Student rosters, enrollments, submissions, grades, quiz submissions, discussion entries, and other student-level records are intentionally excluded.",
            "Specific-student assignment and module overrides are retained only as counts; student identifiers are not stored.",
            "Unavailable API data is reported as unavailable rather than interpreted as an empty feature.",
            "New Quiz item-bank coverage includes banks referenced by captured New Quiz items and does not claim to enumerate every item bank accessible to the instructor or account.",
            "External URLs are inventoried but are not fetched or network-validated by the link audit.",
            "HTML accessibility-review signals are structural cues only and do not replace an accessibility checker or human review.",
            "Question-level scoring checks are limited to question types whose answer-key meaning is clear from the captured API structure; unusual does not automatically mean wrong.",
        ],
    }

    json_path = snapshot / "comprehensive-audit.json"
    markdown_path = snapshot / "comprehensive-audit.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "# Comprehensive course audit",
        "",
        f"- Course: **{manifest.get('course_name', 'unnamed course')}**",
        f"- Course code: `{manifest.get('course_code', '')}`",
        f"- Canvas course ID: `{manifest.get('course_id', '')}`",
        "- Mode: **read-only**. No Canvas content is changed.",
        "",
        "This is the master course-health report. Warnings indicate objective structural/date conflicts, reviews identify things worth inspecting, and observations are inventory facts that may be completely intentional.",
        "",
        "## Audit summary",
        "",
        f"- Specialized audit reports: **{summary['specialized_audit_reports']}**",
        f"- Warnings: **{summary['warnings']}**",
        f"- Reviews: **{summary['reviews']}**",
        f"- Observations: **{summary['observations']}**",
        f"- Findings total: **{summary['findings_total']}**",
        f"- Schedule / availability flags: **{summary['schedule_availability_flags']}**",
        f"- Duplicate-content candidates: **{summary['duplicate_candidates']}**",
        f"- API resource groups unavailable: **{summary['api_resource_groups_unavailable']}**",
        "",
        "## Report directory",
        "",
        "| Category | Report | File |",
        "|---|---|---|",
    ]
    for item in reports:
        lines.append(f"| {_md(item['category'])} | [{_md(item['title'])}]({_md(item['markdown'])}) | `{_md(item['markdown'])}` |")

    lines.extend(["", "## All warnings and review items", ""])
    actionable = [item for item in findings if str(item.get("severity")) in {"warning", "review"}]
    if actionable:
        for item in actionable:
            label = f" **{_md(item.get('item'))}**:" if item.get("item") else ""
            source = str(item.get("source_report") or "")
            source_link = f" ([details]({source}))" if source.endswith(".md") else ""
            lines.append(
                f"- **{str(item.get('severity', 'review')).upper()} · {_md(item.get('area', 'review'))}**{label} "
                f"{_md(item.get('message', ''))}{source_link}"
            )
    else:
        lines.append("None found.")

    lines.extend(["", "## API coverage", "", "| Resource | Status | Captured records/groups |", "|---|---|---:|"])
    for item in coverage:
        if not isinstance(item, dict):
            continue
        lines.append(f"| {_md(item.get('resource'))} | {'Available' if item.get('available') else 'Unavailable'} | {item.get('count', 0)} |")

    lines.extend(["", "## Scope notes", ""])
    for note in payload["scope_notes"]:
        lines.append(f"- {note}")
    lines.append("")
    markdown_path.write_text("\n".join(lines), encoding="utf-8")

    refresh_report_index(snapshot)

    report_paths = tuple(suite.report_paths) + (override_result.markdown_path, question_result.markdown_path, link_result.markdown_path)
    return FullAuditResult(
        comprehensive_path=markdown_path,
        report_paths=report_paths,
        finding_count=len(findings),
        warning_count=counts.get("warning", 0),
        review_count=counts.get("review", 0),
        observation_count=counts.get("observation", 0),
    )
