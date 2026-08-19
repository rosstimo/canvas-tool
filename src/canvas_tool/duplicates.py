from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .report_index import refresh_report_index


_RESOURCE_SPECS = (
    ("modules", "Modules", "name"),
    ("assignment_groups", "Assignment groups", "name"),
    ("assignments", "Assignments", "name"),
    ("classic_quizzes", "Classic quizzes", "title"),
    ("new_quizzes", "New quizzes", "title"),
    ("pages", "Pages", "title"),
    ("rubrics", "Rubrics", "title"),
    ("discussions", "Discussions", "title"),
    ("announcements", "Announcements", "title"),
    ("files", "Files", "display_name"),
)


@dataclass(frozen=True)
class DuplicateAuditResult:
    markdown_path: Path
    json_path: Path
    high_confidence: int
    review: int
    similar_names: int


def _name_key(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def _content_value(record: dict[str, Any], title_field: str) -> Any:
    value = dict(record)
    value.pop(title_field, None)
    value.pop("position", None)
    return value


def _record_hint(record: dict[str, Any]) -> dict[str, Any]:
    hint: dict[str, Any] = {}
    for key in ("position", "published", "assignment_group", "points_possible", "filename", "size"):
        if key in record and record.get(key) is not None:
            hint[key] = record.get(key)
    if isinstance(record.get("items"), list):
        hint["item_count"] = len(record["items"])
    return hint


def find_duplicates(normalized: dict[str, Any], near_threshold: float = 0.90) -> dict[str, list[dict[str, Any]]]:
    high_confidence: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    similar_names: list[dict[str, Any]] = []

    for key, label, title_field in _RESOURCE_SPECS:
        records = [item for item in normalized.get(key, []) if isinstance(item, dict) and item.get(title_field)]
        groups: dict[str, list[tuple[int, dict[str, Any]]]] = {}
        for index, record in enumerate(records):
            groups.setdefault(_name_key(record.get(title_field)), []).append((index, record))

        exact_members: set[int] = set()
        for normalized_name, members in groups.items():
            if not normalized_name or len(members) < 2:
                continue
            exact_members.update(index for index, _record in members)
            content = [_content_value(record, title_field) for _index, record in members]
            same_content = all(value == content[0] for value in content[1:])
            finding = {
                "resource": key,
                "resource_label": label,
                "name": members[0][1].get(title_field),
                "count": len(members),
                "classification": "same_name_same_content" if same_content else "same_name_different_content",
                "records": [_record_hint(record) for _index, record in members],
            }
            (high_confidence if same_content else review).append(finding)

        for left in range(len(records)):
            if left in exact_members:
                continue
            left_name = _name_key(records[left].get(title_field))
            if len(left_name) < 5:
                continue
            for right in range(left + 1, len(records)):
                if right in exact_members:
                    continue
                right_name = _name_key(records[right].get(title_field))
                if len(right_name) < 5 or left_name == right_name:
                    continue
                ratio = SequenceMatcher(None, left_name, right_name).ratio()
                if ratio < near_threshold:
                    continue
                similar_names.append({
                    "resource": key,
                    "resource_label": label,
                    "left": records[left].get(title_field),
                    "right": records[right].get(title_field),
                    "similarity": round(ratio, 3),
                    "left_record": _record_hint(records[left]),
                    "right_record": _record_hint(records[right]),
                })

    return {
        "high_confidence": high_confidence,
        "review": review,
        "similar_names": similar_names,
    }


def audit_snapshot(snapshot: Path) -> DuplicateAuditResult:
    snapshot = snapshot.resolve()
    normalized = json.loads((snapshot / "normalized.json").read_text(encoding="utf-8"))
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    findings = find_duplicates(normalized)

    report = {
        "schema_version": 1,
        "course_id": manifest.get("course_id"),
        "course_name": manifest.get("course_name"),
        "course_code": manifest.get("course_code"),
        "read_only": True,
        **findings,
    }
    json_path = snapshot / "duplicate-audit.json"
    markdown_path = snapshot / "duplicate-audit.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "# Duplicate content audit",
        "",
        f"- Course: **{manifest.get('course_name', 'unnamed course')}**",
        f"- Course code: `{manifest.get('course_code', '')}`",
        f"- Canvas course ID: `{manifest.get('course_id', '')}`",
        "- Mode: **read-only**. No Canvas content was modified.",
        "",
        "This report identifies duplicate candidates. Matching names alone are never treated as permission to delete content.",
        "",
    ]

    def add_group(title: str, items: list[dict[str, Any]], description: str) -> None:
        lines.extend([f"## {title}", "", description, ""])
        if not items:
            lines.extend(["None found.", ""])
            return
        for item in items:
            if "name" in item:
                lines.append(f"- **{item['resource_label']}**: `{item['name']}` ({item['count']} copies)")
                hints = item.get("records") or []
                for number, hint in enumerate(hints, start=1):
                    details = ", ".join(f"{key}={value}" for key, value in hint.items()) or "no distinguishing summary fields"
                    lines.append(f"  - copy {number}: {details}")
            else:
                percent = round(float(item["similarity"]) * 100)
                lines.append(f"- **{item['resource_label']}**: `{item['left']}` ↔ `{item['right']}` ({percent}% name similarity)")
        lines.append("")

    add_group(
        "High-confidence duplicate candidates",
        findings["high_confidence"],
        "These records have the same normalized name and the same normalized content. They are strong duplicate candidates, but still require review before any future deletion action.",
    )
    add_group(
        "Same name, different content",
        findings["review"],
        "These records share a normalized name but their normalized content differs. They should be reviewed side by side and must not be automatically removed.",
    )
    add_group(
        "Similar-name candidates",
        findings["similar_names"],
        "These records have similar names but are not exact normalized-name matches. They are lower-confidence review candidates.",
    )

    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    refresh_report_index(snapshot)
    return DuplicateAuditResult(
        markdown_path=markdown_path,
        json_path=json_path,
        high_confidence=len(findings["high_confidence"]),
        review=len(findings["review"]),
        similar_names=len(findings["similar_names"]),
    )
