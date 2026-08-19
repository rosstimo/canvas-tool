from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .report_index import refresh_report_index


@dataclass(frozen=True)
class AuditSuiteResult:
    comprehensive_path: Path
    report_paths: tuple[Path, ...]
    finding_count: int
    warning_count: int
    review_count: int


def _load(snapshot: Path, name: str, default: Any) -> Any:
    try:
        return json.loads((snapshot / name).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _records(snapshot: Path, stem: str) -> list[dict[str, Any]]:
    value = _load(snapshot, f"{stem}.json", [])
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _grouped(snapshot: Path, stem: str) -> list[dict[str, Any]]:
    return _records(snapshot, stem)


def _md(value: Any) -> str:
    text = str(value if value is not None else "")
    return text.replace("\n", " ").replace("\r", " ").replace("|", "\\|")


def _yes_no(value: Any) -> str:
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return "—"


def _num(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _domain(value: Any) -> str:
    if not value:
        return "—"
    try:
        parsed = urlparse(str(value))
    except ValueError:
        return str(value)
    return parsed.netloc or str(value)


def _exact_duplicates(records: list[dict[str, Any]], field: str) -> list[tuple[str, int]]:
    counts = Counter(str(item.get(field) or "") for item in records if str(item.get(field) or ""))
    return sorted(((name, count) for name, count in counts.items() if count > 1), key=lambda pair: pair[0].casefold())


def _flatten_group_items(groups: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    result: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for group in groups:
        for item in group.get("items") or []:
            if isinstance(item, dict):
                result.append((group, item))
    return result


def _error_names(snapshot: Path) -> set[str]:
    errors = _load(snapshot, "errors.json", [])
    result: set[str] = set()
    for item in errors if isinstance(errors, list) else []:
        if isinstance(item, dict) and item.get("name"):
            result.add(str(item["name"]))
    return result


def _available(errors: set[str], name: str) -> bool:
    return name not in errors and not any(value.startswith(name + ":") for value in errors)


def _finding(severity: str, area: str, message: str, item: str = "") -> dict[str, str]:
    return {"severity": severity, "area": area, "item": item, "message": message}


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_markdown(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _report_header(title: str, manifest: dict[str, Any], intro: str) -> list[str]:
    return [
        f"# {title}",
        "",
        f"- Course: **{manifest.get('course_name', 'unnamed course')}**",
        f"- Course code: `{manifest.get('course_code', '')}`",
        f"- Canvas course ID: `{manifest.get('course_id', '')}`",
        "- Mode: **read-only**. No Canvas content is changed.",
        "",
        intro,
        "",
    ]


def _add_findings(lines: list[str], findings: list[dict[str, str]]) -> None:
    lines.extend(["## Attention / review", ""])
    actionable = [item for item in findings if item["severity"] in {"warning", "review"}]
    if not actionable:
        lines.extend(["None found.", ""])
        return
    for item in actionable:
        label = f" **{_md(item['item'])}**:" if item.get("item") else ""
        lines.append(f"- **{item['severity'].upper()} · {_md(item['area'])}**{label} {_md(item['message'])}")
    lines.append("")


class _HtmlReview(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.images = 0
        self.images_without_alt = 0
        self.tables = 0
        self.tables_with_th: set[int] = set()
        self._table_stack: list[int] = []
        self.links = 0
        self.external_links = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.casefold(): value for key, value in attrs}
        lowered = tag.casefold()
        if lowered == "img":
            self.images += 1
            if "alt" not in values:
                self.images_without_alt += 1
        elif lowered == "table":
            self.tables += 1
            self._table_stack.append(self.tables)
        elif lowered == "th" and self._table_stack:
            self.tables_with_th.add(self._table_stack[-1])
        elif lowered == "a":
            self.links += 1
            href = values.get("href")
            if href and urlparse(href).scheme in {"http", "https"}:
                self.external_links += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "table" and self._table_stack:
            self._table_stack.pop()

    @property
    def tables_without_headers(self) -> int:
        return max(0, self.tables - len(self.tables_with_th))


def _html_review(value: Any) -> dict[str, int]:
    parser = _HtmlReview()
    try:
        parser.feed(str(value or ""))
    except Exception:
        pass
    return {
        "images": parser.images,
        "images_without_alt": parser.images_without_alt,
        "tables": parser.tables,
        "tables_without_headers": parser.tables_without_headers,
        "links": parser.links,
        "external_links": parser.external_links,
    }


def _build_assignment_audit(snapshot: Path, manifest: dict[str, Any]) -> tuple[Path, Path, list[dict[str, str]], dict[str, Any]]:
    course = _load(snapshot, "course.json", {})
    groups = _records(snapshot, "assignment-groups")
    assignments = _records(snapshot, "assignments")
    module_items = _grouped(snapshot, "module-items")
    new_quizzes = _records(snapshot, "new-quizzes")

    new_quiz_ids = {
        str(item.get("assignment_id") or item.get("id"))
        for item in new_quizzes
        if item.get("assignment_id") is not None or item.get("id") is not None
    }
    placed_ids: set[str] = set()
    for _group, item in _flatten_group_items(module_items):
        if str(item.get("type") or "").casefold() == "assignment" and item.get("content_id") is not None:
            placed_ids.add(str(item["content_id"]))
        details = item.get("content_details") if isinstance(item.get("content_details"), dict) else {}
        if details.get("assignment_id") is not None:
            placed_ids.add(str(details["assignment_id"]))

    group_names = {str(item.get("id")): str(item.get("name") or "") for item in groups}
    group_counts = Counter(str(item.get("assignment_group_id") or "") for item in assignments)
    findings: list[dict[str, str]] = []

    if course.get("apply_assignment_group_weights"):
        total = sum(float(item.get("group_weight") or 0) for item in groups)
        if abs(total - 100.0) > 0.01:
            findings.append(_finding("warning", "grade weighting", f"Assignment-group weights total {_num(total)}%, not 100%."))
    for group in groups:
        gid = str(group.get("id") or "")
        weight = float(group.get("group_weight") or 0)
        count = group_counts.get(gid, 0)
        if count == 0:
            findings.append(_finding("review", "assignment group", "This assignment group contains no assignments.", str(group.get("name") or gid)))
        if course.get("apply_assignment_group_weights") and count and weight == 0:
            findings.append(_finding("review", "assignment group", "This group contains graded items but has a 0% weight.", str(group.get("name") or gid)))

    for name, count in _exact_duplicates(assignments, "name"):
        findings.append(_finding("review", "assignment names", f"This exact assignment name appears {count} times.", name))

    for assignment in assignments:
        aid = str(assignment.get("id") or "")
        name = str(assignment.get("name") or aid or "unnamed assignment")
        grading_type = str(assignment.get("grading_type") or "")
        if grading_type != "not_graded" and not assignment.get("due_at"):
            findings.append(_finding("review", "due date", "No due date is set.", name))
        if grading_type != "not_graded" and assignment.get("points_possible") in (None, 0):
            findings.append(_finding("review", "points", f"Points possible is {_num(assignment.get('points_possible'))}.", name))
        if grading_type != "not_graded" and not assignment.get("submission_types"):
            findings.append(_finding("review", "submission type", "No submission type is reported.", name))
        if aid and aid not in placed_ids:
            findings.append(_finding("observation", "module placement", "This assignment is not directly represented by a module item.", name))

    rows = []
    for assignment in assignments:
        aid = str(assignment.get("id") or "")
        submission_types = [str(value) for value in (assignment.get("submission_types") or [])]
        launch = assignment.get("external_tool_tag_attributes")
        launch_url = launch.get("url") if isinstance(launch, dict) else None
        item_type = "New Quiz" if aid in new_quiz_ids else ("External tool" if "external_tool" in {value.casefold() for value in submission_types} else "Assignment")
        rows.append({
            "id": assignment.get("id"),
            "name": assignment.get("name"),
            "type": item_type,
            "published": assignment.get("published"),
            "group": group_names.get(str(assignment.get("assignment_group_id") or ""), ""),
            "points": assignment.get("points_possible"),
            "grading_type": assignment.get("grading_type"),
            "due_at": assignment.get("due_at"),
            "submission_types": submission_types,
            "external_domain": _domain(launch_url) if launch_url else "",
            "in_module": aid in placed_ids,
            "has_overrides": bool(assignment.get("has_overrides")),
            "omit_from_final_grade": bool(assignment.get("omit_from_final_grade")),
            "peer_reviews": bool(assignment.get("peer_reviews")),
        })

    summary = {
        "assignment_groups": len(groups),
        "assignments": len(assignments),
        "published": sum(1 for item in assignments if item.get("published") is True),
        "unpublished": sum(1 for item in assignments if item.get("published") is False),
        "not_in_modules": sum(1 for item in rows if not item["in_module"]),
        "external_tool_assignments": sum(1 for item in rows if item["external_domain"]),
        "new_quizzes": sum(1 for item in rows if item["type"] == "New Quiz"),
        "peer_review_assignments": sum(1 for item in rows if item["peer_reviews"]),
        "differentiated_assignments": sum(1 for item in rows if item["has_overrides"]),
    }
    payload = {"schema_version": 1, "summary": summary, "findings": findings, "assignments": rows}
    json_path = snapshot / "assignment-audit.json"
    markdown_path = snapshot / "assignment-audit.md"
    _write_json(json_path, payload)

    lines = _report_header("Assignment and gradebook audit", manifest, "Inventory and objective review of assignments, assignment groups, grading setup, module placement, and submission types.")
    lines.extend(["## Summary", ""])
    for key, value in summary.items():
        lines.append(f"- {key.replace('_', ' ').title()}: **{value}**")
    lines.append("")
    _add_findings(lines, findings)
    lines.extend([
        "## Assignment groups",
        "",
        "| # | Group | Weight | Assignments |",
        "|---:|---|---:|---:|",
    ])
    for group in sorted(groups, key=lambda item: (item.get("position") is None, item.get("position") or 0)):
        gid = str(group.get("id") or "")
        lines.append(f"| {group.get('position') or ''} | {_md(group.get('name'))} | {_num(group.get('group_weight'))}% | {group_counts.get(gid, 0)} |")
    lines.extend([
        "",
        "## Assignments",
        "",
        "| Pub | Type | Assignment | Group | Points | Grading | Due | Submission | Module | Notes |",
        "|---|---|---|---|---:|---|---|---|---|---|",
    ])
    for item in rows:
        notes = []
        if item["has_overrides"]:
            notes.append("Assign To overrides")
        if item["omit_from_final_grade"]:
            notes.append("omitted from final grade")
        if item["peer_reviews"]:
            notes.append("peer reviews")
        if item["external_domain"]:
            notes.append(item["external_domain"])
        lines.append(
            f"| {_yes_no(item['published'])} | {_md(item['type'])} | {_md(item['name'])} | {_md(item['group'])} | {_num(item['points'])} | "
            f"{_md(item['grading_type'])} | {_md(item['due_at'] or '—')} | {_md(', '.join(item['submission_types']) or '—')} | "
            f"{'Yes' if item['in_module'] else 'No'} | {_md('; '.join(notes) or '—')} |"
        )
    _write_markdown(markdown_path, lines)
    return markdown_path, json_path, findings, summary


def _build_module_audit(snapshot: Path, manifest: dict[str, Any]) -> tuple[Path, Path, list[dict[str, str]], dict[str, Any]]:
    modules = _records(snapshot, "modules")
    grouped_items = _grouped(snapshot, "module-items")
    assignments = _records(snapshot, "assignments")
    classic_quizzes = _records(snapshot, "classic-quizzes")
    new_quizzes = _records(snapshot, "new-quizzes")
    pages = _records(snapshot, "pages")
    files = _records(snapshot, "files")
    discussions = _records(snapshot, "discussions")

    items_by_module = {str(group.get("source_id")): [item for item in (group.get("items") or []) if isinstance(item, dict)] for group in grouped_items}
    module_ids = {str(item.get("id")) for item in modules if item.get("id") is not None}
    assignment_ids = {str(item.get("id")) for item in assignments if item.get("id") is not None}
    quiz_ids = {str(item.get("id")) for item in classic_quizzes if item.get("id") is not None}
    quiz_ids |= {str(item.get("id")) for item in new_quizzes if item.get("id") is not None}
    quiz_ids |= {str(item.get("assignment_id")) for item in new_quizzes if item.get("assignment_id") is not None}
    page_ids = {str(item.get("page_id")) for item in pages if item.get("page_id") is not None}
    page_urls = {str(item.get("url")) for item in pages if item.get("url")}
    file_ids = {str(item.get("id")) for item in files if item.get("id") is not None}
    discussion_ids = {str(item.get("id")) for item in discussions if item.get("id") is not None}

    findings: list[dict[str, str]] = []
    duplicate_names = _exact_duplicates(modules, "name")
    for name, count in duplicate_names:
        findings.append(_finding("review", "module names", f"This exact module name appears {count} times.", name))

    type_counts: Counter[str] = Counter()
    broken_items: list[dict[str, Any]] = []
    empty_modules = 0
    required_items = 0
    unpublished_items = 0

    def check_reference(item: dict[str, Any]) -> bool | None:
        item_type = str(item.get("type") or "")
        content_id = item.get("content_id")
        key = str(content_id) if content_id is not None else ""
        if item_type == "Assignment":
            return key in assignment_ids if key else False
        if item_type == "Quiz":
            return key in quiz_ids if key else False
        if item_type == "File":
            return key in file_ids if key else False
        if item_type == "Discussion":
            return key in discussion_ids if key else False
        if item_type == "Page":
            page_url = str(item.get("page_url") or "")
            return (key in page_ids if key else False) or (page_url in page_urls if page_url else False)
        return None

    rows = []
    for module in sorted(modules, key=lambda item: (item.get("position") is None, item.get("position") or 0)):
        mid = str(module.get("id") or "")
        name = str(module.get("name") or mid or "unnamed module")
        items = items_by_module.get(mid, [])
        if not items:
            empty_modules += 1
            findings.append(_finding("review", "empty module", "This module contains no items.", name))
        prereqs = [str(value) for value in (module.get("prerequisite_module_ids") or [])]
        missing_prereqs = [value for value in prereqs if value not in module_ids]
        if missing_prereqs:
            findings.append(_finding("warning", "module prerequisite", f"References missing prerequisite module ID(s): {', '.join(missing_prereqs)}.", name))

        for item in items:
            type_counts[str(item.get("type") or "Unknown")] += 1
            if item.get("published") is False:
                unpublished_items += 1
            if item.get("completion_requirement"):
                required_items += 1
            resolved = check_reference(item)
            if resolved is False:
                broken = {
                    "module": name,
                    "item": str(item.get("title") or item.get("id") or "unnamed item"),
                    "type": str(item.get("type") or ""),
                    "content_id": item.get("content_id"),
                }
                broken_items.append(broken)
                findings.append(_finding("warning", "module content reference", f"Could not match this {broken['type']} module item to the captured course inventory.", broken["item"]))

        rows.append({
            "id": module.get("id"),
            "position": module.get("position"),
            "name": name,
            "published": module.get("published"),
            "items": len(items),
            "required_items": sum(1 for item in items if item.get("completion_requirement")),
            "prerequisites": prereqs,
            "sequential": bool(module.get("require_sequential_progress")),
            "requirement_type": module.get("requirement_type"),
            "unlock_at": module.get("unlock_at"),
        })

    summary = {
        "modules": len(modules),
        "module_items": sum(item["items"] for item in rows),
        "empty_modules": empty_modules,
        "unpublished_modules": sum(1 for item in modules if item.get("published") is False),
        "unpublished_items": unpublished_items,
        "required_completion_items": required_items,
        "broken_content_references": len(broken_items),
        "sequential_modules": sum(1 for item in rows if item["sequential"]),
        "exact_duplicate_module_names": sum(count for _name, count in duplicate_names),
    }
    payload = {"schema_version": 1, "summary": summary, "findings": findings, "item_type_counts": dict(type_counts), "modules": rows, "broken_items": broken_items}
    json_path = snapshot / "module-audit.json"
    markdown_path = snapshot / "module-audit.md"
    _write_json(json_path, payload)

    lines = _report_header("Module structure audit", manifest, "Inventory and objective review of module structure, prerequisites, completion requirements, publication state, and content references.")
    lines.extend(["## Summary", ""])
    for key, value in summary.items():
        lines.append(f"- {key.replace('_', ' ').title()}: **{value}**")
    lines.append("")
    _add_findings(lines, findings)
    lines.extend(["## Module item types", "", "| Type | Count |", "|---|---:|"])
    for key, value in sorted(type_counts.items()):
        lines.append(f"| {_md(key)} | {value} |")
    lines.extend([
        "",
        "## Modules",
        "",
        "| # | Pub | Module | Items | Required | Prerequisites | Sequential | Unlock |",
        "|---:|---|---|---:|---:|---|---|---|",
    ])
    name_by_id = {str(item.get("id")): str(item.get("name") or "") for item in modules}
    for row in rows:
        prereq_names = [name_by_id.get(value) or f"missing:{value}" for value in row["prerequisites"]]
        lines.append(
            f"| {row['position'] or ''} | {_yes_no(row['published'])} | {_md(row['name'])} | {row['items']} | {row['required_items']} | "
            f"{_md(', '.join(prereq_names) or '—')} | {_yes_no(row['sequential'])} | {_md(row['unlock_at'] or '—')} |"
        )
    _write_markdown(markdown_path, lines)
    return markdown_path, json_path, findings, summary


def _question_type_new(item: dict[str, Any]) -> str:
    entry = item.get("entry") if isinstance(item.get("entry"), dict) else {}
    return str(entry.get("interaction_type_slug") or item.get("entry_type") or "Unknown")


def _build_quiz_audit(snapshot: Path, manifest: dict[str, Any], errors: set[str]) -> tuple[Path, Path, list[dict[str, str]], dict[str, Any]]:
    classic = _records(snapshot, "classic-quizzes")
    classic_questions = _grouped(snapshot, "classic-quiz-questions")
    classic_groups = _grouped(snapshot, "classic-quiz-groups")
    new = _records(snapshot, "new-quizzes")
    new_items = _grouped(snapshot, "new-quiz-items")

    classic_q_by_id = {str(group.get("source_id")): [item for item in (group.get("items") or []) if isinstance(item, dict)] for group in classic_questions}
    classic_g_by_id = {str(group.get("source_id")): [item for item in (group.get("items") or []) if isinstance(item, dict)] for group in classic_groups}
    new_i_by_id = {str(group.get("source_id")): [item for item in (group.get("items") or []) if isinstance(item, dict)] for group in new_items}

    findings: list[dict[str, str]] = []
    title_counts = Counter()
    for item in classic:
        title_counts[str(item.get("title") or "")] += 1
    for item in new:
        title_counts[str(item.get("title") or "")] += 1
    for title, count in sorted(title_counts.items()):
        if title and count > 1:
            findings.append(_finding("review", "quiz titles", f"This exact quiz title appears {count} times across Classic and New Quizzes.", title))

    classic_rows = []
    classic_question_types: Counter[str] = Counter()
    for quiz in classic:
        qid = str(quiz.get("id") or "")
        questions = classic_q_by_id.get(qid, [])
        groups = classic_g_by_id.get(qid, [])
        for question in questions:
            classic_question_types[str(question.get("question_type") or "Unknown")] += 1
        if _available(errors, "classic-quiz-questions"):
            reported = quiz.get("question_count")
            if reported is not None and int(reported or 0) != len(questions) and not groups:
                findings.append(_finding("review", "Classic Quiz questions", f"Canvas reports {reported} questions but {len(questions)} direct question records were captured.", str(quiz.get("title") or qid)))
            if quiz.get("published") is True and not questions and not groups:
                findings.append(_finding("review", "Classic Quiz", "Published quiz has no captured direct questions or question groups.", str(quiz.get("title") or qid)))
        classic_rows.append({
            "id": quiz.get("id"),
            "title": quiz.get("title"),
            "published": quiz.get("published"),
            "quiz_type": quiz.get("quiz_type"),
            "points": quiz.get("points_possible"),
            "reported_questions": quiz.get("question_count"),
            "captured_questions": len(questions),
            "question_groups": len(groups),
            "time_limit": quiz.get("time_limit"),
            "allowed_attempts": quiz.get("allowed_attempts"),
            "shuffle_answers": quiz.get("shuffle_answers"),
            "one_question_at_a_time": quiz.get("one_question_at_a_time"),
            "cant_go_back": quiz.get("cant_go_back"),
        })

    new_rows = []
    new_entry_types: Counter[str] = Counter()
    new_question_types: Counter[str] = Counter()
    bank_backed = 0
    for quiz in new:
        qid = str(quiz.get("assignment_id") or quiz.get("id") or "")
        items = new_i_by_id.get(qid, [])
        for item in items:
            entry_type = str(item.get("entry_type") or "Unknown")
            new_entry_types[entry_type] += 1
            new_question_types[_question_type_new(item)] += 1
            if entry_type in {"Bank", "BankEntry"}:
                bank_backed += 1
        if _available(errors, "new-quiz-items") and quiz.get("published") is True and not items:
            findings.append(_finding("review", "New Quiz", "Published quiz has no captured quiz items.", str(quiz.get("title") or qid)))
        point_sum = sum(float(item.get("points_possible") or 0) for item in items)
        if items and quiz.get("points_possible") is not None and abs(float(quiz.get("points_possible") or 0) - point_sum) > 0.01:
            findings.append(_finding("observation", "New Quiz points", f"Quiz points possible is {_num(quiz.get('points_possible'))}; captured item points sum to {_num(point_sum)}.", str(quiz.get("title") or qid)))
        new_rows.append({
            "id": quiz.get("id"),
            "assignment_id": quiz.get("assignment_id"),
            "title": quiz.get("title"),
            "published": quiz.get("published"),
            "points": quiz.get("points_possible"),
            "grading_type": quiz.get("grading_type"),
            "items": len(items),
            "item_points": point_sum,
            "settings": quiz.get("quiz_settings") if isinstance(quiz.get("quiz_settings"), dict) else {},
        })

    summary = {
        "classic_quizzes": len(classic),
        "classic_questions": sum(row["captured_questions"] for row in classic_rows),
        "classic_question_groups": sum(row["question_groups"] for row in classic_rows),
        "new_quizzes": len(new),
        "new_quiz_items": sum(row["items"] for row in new_rows),
        "new_quiz_bank_backed_entries": bank_backed,
        "published_quizzes": sum(1 for item in classic + new if item.get("published") is True),
        "unpublished_quizzes": sum(1 for item in classic + new if item.get("published") is False),
    }
    payload = {
        "schema_version": 1,
        "summary": summary,
        "findings": findings,
        "classic_question_types": dict(classic_question_types),
        "new_entry_types": dict(new_entry_types),
        "new_question_types": dict(new_question_types),
        "classic_quizzes": classic_rows,
        "new_quizzes": new_rows,
        "api_availability": {
            "classic_questions": _available(errors, "classic-quiz-questions"),
            "classic_groups": _available(errors, "classic-quiz-groups"),
            "new_items": _available(errors, "new-quiz-items"),
        },
    }
    json_path = snapshot / "quiz-audit.json"
    markdown_path = snapshot / "quiz-audit.md"
    _write_json(json_path, payload)

    lines = _report_header("Quiz audit", manifest, "Detailed inventory of Classic Quizzes, New Quizzes, question/item counts, quiz settings, question types, and item-bank-backed entries.")
    lines.extend(["## Summary", ""])
    for key, value in summary.items():
        lines.append(f"- {key.replace('_', ' ').title()}: **{value}**")
    lines.append("")
    _add_findings(lines, findings)

    lines.extend(["## Classic Quizzes", ""])
    if not classic:
        lines.append("None found.")
    else:
        lines.extend([
            "| Pub | Quiz | Type | Points | Questions | Groups | Attempts | Time limit | Shuffle | One at a time | No backtracking |",
            "|---|---|---|---:|---:|---:|---:|---:|---|---|---|",
        ])
        for row in classic_rows:
            lines.append(
                f"| {_yes_no(row['published'])} | {_md(row['title'])} | {_md(row['quiz_type'])} | {_num(row['points'])} | "
                f"{row['captured_questions']} | {row['question_groups']} | {_num(row['allowed_attempts'])} | {_num(row['time_limit'])} | "
                f"{_yes_no(row['shuffle_answers'])} | {_yes_no(row['one_question_at_a_time'])} | {_yes_no(row['cant_go_back'])} |"
            )
    lines.extend(["", "### Classic question types", "", "| Type | Count |", "|---|---:|"])
    for key, value in sorted(classic_question_types.items()):
        lines.append(f"| {_md(key)} | {value} |")

    lines.extend(["", "## New Quizzes", ""])
    if not new:
        lines.append("None found.")
    else:
        lines.extend([
            "| Pub | Quiz | Points | Items | Item points | Grading | Settings |",
            "|---|---|---:|---:|---:|---|---|",
        ])
        for row in new_rows:
            settings = ", ".join(f"{key}={value}" for key, value in sorted(row["settings"].items()) if value not in (None, False, "", [], {}))
            lines.append(
                f"| {_yes_no(row['published'])} | {_md(row['title'])} | {_num(row['points'])} | {row['items']} | {_num(row['item_points'])} | "
                f"{_md(row['grading_type'])} | {_md(settings or '—')} |"
            )
    lines.extend(["", "### New Quiz entry types", "", "| Entry type | Count |", "|---|---:|"])
    for key, value in sorted(new_entry_types.items()):
        lines.append(f"| {_md(key)} | {value} |")
    lines.extend(["", "### New Quiz question types", "", "| Question type | Count |", "|---|---:|"])
    for key, value in sorted(new_question_types.items()):
        lines.append(f"| {_md(key)} | {value} |")

    _write_markdown(markdown_path, lines)
    return markdown_path, json_path, findings, summary


def _build_question_bank_audit(snapshot: Path, manifest: dict[str, Any], errors: set[str]) -> tuple[Path, Path, list[dict[str, str]], dict[str, Any]]:
    banks = _records(snapshot, "question-banks")
    bank_questions = _grouped(snapshot, "question-bank-questions")
    classic_quizzes = _records(snapshot, "classic-quizzes")
    classic_groups = _grouped(snapshot, "classic-quiz-groups")
    classic_questions = _grouped(snapshot, "classic-quiz-questions")
    new_items = _grouped(snapshot, "new-quiz-items")

    bank_by_id = {str(item.get("id")): item for item in banks if item.get("id") is not None}
    bank_q_by_id = {str(group.get("source_id")): [item for item in (group.get("items") or []) if isinstance(item, dict)] for group in bank_questions}
    quiz_title_by_id = {str(item.get("id")): str(item.get("title") or "") for item in classic_quizzes if item.get("id") is not None}

    findings: list[dict[str, str]] = []
    for name, count in _exact_duplicates(banks, "title"):
        findings.append(_finding("review", "Classic Question Bank names", f"This exact question-bank title appears {count} times.", name))

    classic_bank_rows = []
    question_types: Counter[str] = Counter()
    for bank in banks:
        bid = str(bank.get("id") or "")
        questions = bank_q_by_id.get(bid, [])
        for question in questions:
            question_types[str(question.get("question_type") or "Unknown")] += 1
        reported = bank.get("assessment_question_count")
        if _available(errors, "question-bank-questions") and reported is not None and int(reported or 0) != len(questions):
            findings.append(_finding("review", "Classic Question Bank", f"Canvas reports {reported} questions; {len(questions)} question records were captured.", str(bank.get("title") or bid)))
        if reported in (0, None) and _available(errors, "question-bank-questions") and not questions:
            findings.append(_finding("review", "Classic Question Bank", "This question bank is empty.", str(bank.get("title") or bid)))
        classic_bank_rows.append({
            "id": bank.get("id"),
            "title": bank.get("title"),
            "workflow_state": bank.get("workflow_state"),
            "reported_count": reported,
            "captured_count": len(questions),
            "context_type": bank.get("context_type"),
        })

    group_rows = []
    missing_bank_refs = 0
    for group in classic_groups:
        quiz_title = str(group.get("title") or quiz_title_by_id.get(str(group.get("source_id"))) or group.get("source_id") or "")
        for item in group.get("items") or []:
            if not isinstance(item, dict):
                continue
            bank_id = str(item.get("assessment_question_bank_id") or "")
            bank = bank_by_id.get(bank_id)
            if bank_id and bank is None and _available(errors, "question-banks"):
                missing_bank_refs += 1
                findings.append(_finding("warning", "Classic Quiz question group", f"References question bank ID {bank_id}, which is not in the captured course question-bank inventory.", quiz_title))
            group_rows.append({
                "quiz": quiz_title,
                "name": item.get("name"),
                "pick_count": item.get("pick_count"),
                "question_points": item.get("question_points"),
                "bank_id": bank_id or None,
                "bank_title": bank.get("title") if bank else None,
            })

    direct_bank_refs: Counter[str] = Counter()
    for group in classic_questions:
        for question in group.get("items") or []:
            if isinstance(question, dict) and question.get("assessment_question_bank_id") is not None:
                direct_bank_refs[str(question["assessment_question_bank_id"])] += 1

    new_bank_rows = []
    seen_new_bank_keys: set[tuple[str, str, str]] = set()
    for group in new_items:
        quiz_title = str(group.get("title") or group.get("source_id") or "")
        for item in group.get("items") or []:
            if not isinstance(item, dict):
                continue
            entry_type = str(item.get("entry_type") or "")
            if entry_type not in {"Bank", "BankEntry"}:
                continue
            entry = item.get("entry") if isinstance(item.get("entry"), dict) else {}
            properties = item.get("properties") if isinstance(item.get("properties"), dict) else {}
            bank_id = str(entry.get("bank_id") or entry.get("id") or "")
            bank_title = str(entry.get("title") or "")
            key = (quiz_title, bank_id, bank_title)
            if key in seen_new_bank_keys:
                continue
            seen_new_bank_keys.add(key)
            new_bank_rows.append({
                "quiz": quiz_title,
                "entry_type": entry_type,
                "bank_id": bank_id or None,
                "bank_title": bank_title or None,
                "archived": entry.get("archived"),
                "entry_count": entry.get("entry_count"),
                "item_entry_count": entry.get("item_entry_count"),
                "sample_num": properties.get("sample_num"),
            })
            if entry.get("archived") is True:
                findings.append(_finding("review", "New Quiz item bank", "This referenced item bank is marked archived.", bank_title or bank_id or quiz_title))

    summary = {
        "classic_question_banks": len(banks),
        "classic_bank_questions": sum(row["captured_count"] for row in classic_bank_rows),
        "classic_quiz_question_groups": len(group_rows),
        "classic_direct_bank_question_refs": sum(direct_bank_refs.values()),
        "missing_classic_bank_references": missing_bank_refs,
        "new_quiz_bank_references": len(new_bank_rows),
    }
    payload = {
        "schema_version": 1,
        "summary": summary,
        "findings": findings,
        "classic_banks": classic_bank_rows,
        "classic_question_types": dict(question_types),
        "classic_quiz_groups": group_rows,
        "classic_direct_bank_references": dict(direct_bank_refs),
        "new_quiz_bank_references": new_bank_rows,
        "coverage_note": "The Canvas New Quiz Items API exposes bank-backed items referenced by quizzes. This report does not claim to enumerate every New Quiz item bank available to the instructor or account.",
        "api_availability": {
            "question_banks": _available(errors, "question-banks"),
            "bank_questions": _available(errors, "question-bank-questions"),
            "classic_quiz_groups": _available(errors, "classic-quiz-groups"),
            "new_quiz_items": _available(errors, "new-quiz-items"),
        },
    }
    json_path = snapshot / "question-bank-audit.json"
    markdown_path = snapshot / "question-bank-audit.md"
    _write_json(json_path, payload)

    lines = _report_header("Question bank audit", manifest, "Inventory of Classic Question Banks, Classic Quiz question groups that draw from banks, direct bank-linked questions, and New Quiz bank-backed items.")
    lines.extend([
        "> **New Quiz item-bank coverage:** Canvas exposes bank-backed items used by captured New Quizzes, but this report does not claim to enumerate every New Quiz item bank available to the instructor or account.",
        "",
        "## Summary",
        "",
    ])
    for key, value in summary.items():
        lines.append(f"- {key.replace('_', ' ').title()}: **{value}**")
    lines.append("")
    _add_findings(lines, findings)

    lines.extend(["## Classic Question Banks", ""])
    if not classic_bank_rows:
        lines.append("None found." if _available(errors, "question-banks") else "Question-bank inventory was unavailable from the Canvas API.")
    else:
        lines.extend(["| Bank | State | Reported questions | Captured questions | Context |", "|---|---|---:|---:|---|"])
        for row in classic_bank_rows:
            lines.append(f"| {_md(row['title'])} | {_md(row['workflow_state'])} | {_num(row['reported_count'])} | {row['captured_count']} | {_md(row['context_type'])} |")

    lines.extend(["", "### Classic bank question types", "", "| Type | Count |", "|---|---:|"])
    for key, value in sorted(question_types.items()):
        lines.append(f"| {_md(key)} | {value} |")

    lines.extend(["", "## Classic Quiz question groups", ""])
    if not group_rows:
        lines.append("None found." if _available(errors, "classic-quiz-groups") else "Quiz question-group inventory was unavailable from the Canvas API.")
    else:
        lines.extend(["| Quiz | Group | Pick | Points each | Question bank |", "|---|---|---:|---:|---|"])
        for row in group_rows:
            bank = row["bank_title"] or (f"ID {row['bank_id']}" if row["bank_id"] else "—")
            lines.append(f"| {_md(row['quiz'])} | {_md(row['name'])} | {_num(row['pick_count'])} | {_num(row['question_points'])} | {_md(bank)} |")

    lines.extend(["", "## New Quiz bank-backed items", ""])
    if not new_bank_rows:
        lines.append("None found in the captured New Quiz items." if _available(errors, "new-quiz-items") else "New Quiz item inventory was unavailable from the Canvas API.")
    else:
        lines.extend(["| Quiz | Entry type | Bank | Archived | Entries | Question entries | Sample |", "|---|---|---|---|---:|---:|---:|"])
        for row in new_bank_rows:
            bank = row["bank_title"] or (f"ID {row['bank_id']}" if row["bank_id"] else "—")
            lines.append(
                f"| {_md(row['quiz'])} | {_md(row['entry_type'])} | {_md(bank)} | {_yes_no(row['archived'])} | "
                f"{_num(row['entry_count'])} | {_num(row['item_entry_count'])} | {_num(row['sample_num'])} |"
            )
    _write_markdown(markdown_path, lines)
    return markdown_path, json_path, findings, summary


def _build_content_audit(snapshot: Path, manifest: dict[str, Any]) -> tuple[Path, Path, list[dict[str, str]], dict[str, Any]]:
    course = _load(snapshot, "course.json", {})
    pages = _records(snapshot, "pages")
    files = _records(snapshot, "files")
    folders = _records(snapshot, "folders")
    discussions = _records(snapshot, "discussions")
    announcements = _records(snapshot, "announcements")
    calendar_events = _records(snapshot, "calendar-events")
    module_items = _grouped(snapshot, "module-items")

    placed_page_ids: set[str] = set()
    placed_page_urls: set[str] = set()
    placed_file_ids: set[str] = set()
    placed_discussion_ids: set[str] = set()
    for _group, item in _flatten_group_items(module_items):
        kind = str(item.get("type") or "")
        cid = str(item.get("content_id") or "")
        if kind == "Page":
            if cid:
                placed_page_ids.add(cid)
            if item.get("page_url"):
                placed_page_urls.add(str(item["page_url"]))
        elif kind == "File" and cid:
            placed_file_ids.add(cid)
        elif kind == "Discussion" and cid:
            placed_discussion_ids.add(cid)

    findings: list[dict[str, str]] = []
    for name, count in _exact_duplicates(pages, "title"):
        findings.append(_finding("review", "page titles", f"This exact page title appears {count} times.", name))
    for name, count in _exact_duplicates(files, "display_name"):
        findings.append(_finding("review", "file names", f"This exact file display name appears {count} times.", name))
    for name, count in _exact_duplicates(discussions, "title"):
        findings.append(_finding("review", "discussion titles", f"This exact discussion title appears {count} times.", name))

    html_rows = []
    syllabus_review = _html_review(course.get("syllabus_body"))
    if syllabus_review["images_without_alt"]:
        findings.append(_finding("review", "syllabus HTML", f"{syllabus_review['images_without_alt']} image(s) have no alt attribute."))
    if syllabus_review["tables_without_headers"]:
        findings.append(_finding("review", "syllabus HTML", f"{syllabus_review['tables_without_headers']} table(s) contain no <th> header cells."))

    for page in pages:
        name = str(page.get("title") or page.get("url") or "unnamed page")
        body = str(page.get("body") or "")
        if not body.strip():
            findings.append(_finding("review", "page content", "Page body is empty.", name))
        review = _html_review(body)
        if review["images_without_alt"]:
            findings.append(_finding("review", "page HTML", f"{review['images_without_alt']} image(s) have no alt attribute.", name))
        if review["tables_without_headers"]:
            findings.append(_finding("review", "page HTML", f"{review['tables_without_headers']} table(s) contain no <th> header cells.", name))
        page_id = str(page.get("page_id") or "")
        page_url = str(page.get("url") or "")
        html_rows.append({
            "type": "Page",
            "name": name,
            "published": page.get("published"),
            "in_module": page_id in placed_page_ids or page_url in placed_page_urls,
            **review,
        })

    for discussion in discussions:
        name = str(discussion.get("title") or discussion.get("id") or "unnamed discussion")
        review = _html_review(discussion.get("message"))
        if review["images_without_alt"]:
            findings.append(_finding("review", "discussion HTML", f"{review['images_without_alt']} image(s) have no alt attribute.", name))
        if review["tables_without_headers"]:
            findings.append(_finding("review", "discussion HTML", f"{review['tables_without_headers']} table(s) contain no <th> header cells.", name))
        html_rows.append({
            "type": "Discussion",
            "name": name,
            "published": discussion.get("published"),
            "in_module": str(discussion.get("id") or "") in placed_discussion_ids,
            **review,
        })

    for announcement in announcements:
        review = _html_review(announcement.get("message"))
        name = str(announcement.get("title") or announcement.get("id") or "unnamed announcement")
        if review["images_without_alt"]:
            findings.append(_finding("review", "announcement HTML", f"{review['images_without_alt']} image(s) have no alt attribute.", name))
        html_rows.append({"type": "Announcement", "name": name, "published": announcement.get("published"), "in_module": None, **review})

    zero_byte_files = [item for item in files if item.get("size") == 0]
    for item in zero_byte_files:
        findings.append(_finding("review", "file", "File size is 0 bytes.", str(item.get("display_name") or item.get("filename") or item.get("id"))))

    summary = {
        "pages": len(pages),
        "front_pages": sum(1 for item in pages if item.get("front_page") is True),
        "unpublished_pages": sum(1 for item in pages if item.get("published") is False),
        "pages_not_directly_in_modules": sum(1 for row in html_rows if row["type"] == "Page" and not row["in_module"]),
        "files": len(files),
        "hidden_files": sum(1 for item in files if item.get("hidden") is True),
        "locked_files": sum(1 for item in files if item.get("locked") is True),
        "zero_byte_files": len(zero_byte_files),
        "files_not_directly_in_modules": sum(1 for item in files if str(item.get("id") or "") not in placed_file_ids),
        "folders": len(folders),
        "discussions": len(discussions),
        "announcements": len(announcements),
        "calendar_events": len(calendar_events),
        "images_without_alt_attributes": syllabus_review["images_without_alt"] + sum(row["images_without_alt"] for row in html_rows),
        "tables_without_header_cells": syllabus_review["tables_without_headers"] + sum(row["tables_without_headers"] for row in html_rows),
    }
    payload = {"schema_version": 1, "summary": summary, "findings": findings, "html_review": {"syllabus": syllabus_review, "content": html_rows}}
    json_path = snapshot / "content-audit.json"
    markdown_path = snapshot / "content-audit.md"
    _write_json(json_path, payload)

    lines = _report_header(
        "Content inventory and HTML review",
        manifest,
        "Inventory of pages, files, folders, discussions, announcements, calendar events, and lightweight HTML accessibility-review signals. Missing alt attributes and tables without header cells are review cues, not automatic accessibility violations.",
    )
    lines.extend(["## Summary", ""])
    for key, value in summary.items():
        lines.append(f"- {key.replace('_', ' ').title()}: **{value}**")
    lines.append("")
    _add_findings(lines, findings)

    lines.extend(["## Pages / discussions / announcements HTML inventory", "", "| Type | Pub | Content | In module | Images | Missing alt attr | Tables | Tables without th | External links |", "|---|---|---|---|---:|---:|---:|---:|---:|"])
    for row in html_rows:
        in_module = "—" if row["in_module"] is None else ("Yes" if row["in_module"] else "No")
        lines.append(
            f"| {_md(row['type'])} | {_yes_no(row['published'])} | {_md(row['name'])} | {in_module} | {row['images']} | "
            f"{row['images_without_alt']} | {row['tables']} | {row['tables_without_headers']} | {row['external_links']} |"
        )

    lines.extend(["", "## Files", "", "| File | Size | Type | Hidden | Locked | Module item |", "|---|---:|---|---|---|---|"])
    for item in files:
        fid = str(item.get("id") or "")
        lines.append(
            f"| {_md(item.get('display_name') or item.get('filename'))} | {_num(item.get('size'))} | {_md(item.get('content-type') or item.get('content_type'))} | "
            f"{_yes_no(item.get('hidden'))} | {_yes_no(item.get('locked'))} | {'Yes' if fid in placed_file_ids else 'No'} |"
        )
    _write_markdown(markdown_path, lines)
    return markdown_path, json_path, findings, summary


def _build_grading_audit(snapshot: Path, manifest: dict[str, Any], errors: set[str]) -> tuple[Path, Path, list[dict[str, str]], dict[str, Any]]:
    course = _load(snapshot, "course.json", {})
    groups = _records(snapshot, "assignment-groups")
    assignments = _records(snapshot, "assignments")
    rubrics = _records(snapshot, "rubrics")
    grading_standards = _records(snapshot, "grading-standards")
    outcomes = _records(snapshot, "outcome-links")
    grading_periods = _records(snapshot, "grading-periods")
    late_policy = _load(snapshot, "late-policy.json", {})
    if isinstance(late_policy, dict) and isinstance(late_policy.get("late_policy"), dict):
        late_policy = late_policy["late_policy"]

    assignment_by_id = {str(item.get("id")): item for item in assignments if item.get("id") is not None}
    findings: list[dict[str, str]] = []

    for name, count in _exact_duplicates(rubrics, "title"):
        findings.append(_finding("review", "rubric titles", f"This exact rubric title appears {count} times.", name))
    for rubric in rubrics:
        title = str(rubric.get("title") or rubric.get("id") or "unnamed rubric")
        criteria = [item for item in (rubric.get("data") or []) if isinstance(item, dict)]
        if not criteria:
            findings.append(_finding("review", "rubric", "Rubric has no criteria.", title))
        associations = [item for item in (rubric.get("associations") or []) if isinstance(item, dict)]
        assignment_associations = [
            item for item in associations
            if str(item.get("association_type") or item.get("type") or "").casefold() == "assignment"
        ]
        if not assignment_associations:
            findings.append(_finding("observation", "rubric association", "No assignment association is present in the captured rubric record.", title))
        for association in assignment_associations:
            aid = str(association.get("association_id") or "")
            assignment = assignment_by_id.get(aid)
            if assignment is None:
                findings.append(_finding("review", "rubric association", f"References assignment ID {aid}, which is not in the captured assignment inventory.", title))
                continue
            rubric_points = rubric.get("points_possible")
            assignment_points = assignment.get("points_possible")
            if rubric_points is not None and assignment_points is not None and abs(float(rubric_points) - float(assignment_points)) > 0.01:
                findings.append(_finding("observation", "rubric points", f"Rubric points ({_num(rubric_points)}) differ from assignment points ({_num(assignment_points)}).", str(assignment.get("name") or aid)))

    if course.get("apply_assignment_group_weights"):
        total = sum(float(item.get("group_weight") or 0) for item in groups)
        if abs(total - 100.0) > 0.01:
            findings.append(_finding("warning", "assignment group weights", f"Weights total {_num(total)}%, not 100%."))

    if grading_periods:
        period_total = sum(float(item.get("weight") or 0) for item in grading_periods)
        if any(item.get("weight") is not None for item in grading_periods) and abs(period_total - 100.0) > 0.01:
            findings.append(_finding("review", "grading periods", f"Grading-period weights total {_num(period_total)}%."))

    outcome_titles = []
    for link in outcomes:
        outcome = link.get("outcome") if isinstance(link.get("outcome"), dict) else {}
        title = str(outcome.get("title") or outcome.get("display_name") or "")
        if title:
            outcome_titles.append({"title": title})
    for name, count in _exact_duplicates(outcome_titles, "title"):
        findings.append(_finding("review", "outcomes", f"This exact outcome title appears {count} times in course outcome links.", name))

    summary = {
        "weighted_assignment_groups": bool(course.get("apply_assignment_group_weights")),
        "assignment_groups": len(groups),
        "rubrics": len(rubrics),
        "rubrics_without_assignment_association": sum(
            1 for rubric in rubrics
            if not any(str(item.get("association_type") or item.get("type") or "").casefold() == "assignment" for item in (rubric.get("associations") or []) if isinstance(item, dict))
        ),
        "grading_standards": len(grading_standards),
        "outcome_links": len(outcomes),
        "grading_periods": len(grading_periods),
        "late_policy_available": _available(errors, "late-policy") and bool(late_policy),
    }

    rubric_rows = []
    for rubric in rubrics:
        associations = [item for item in (rubric.get("associations") or []) if isinstance(item, dict)]
        linked_assignments = []
        for association in associations:
            if str(association.get("association_type") or association.get("type") or "").casefold() == "assignment":
                aid = str(association.get("association_id") or "")
                linked_assignments.append(str((assignment_by_id.get(aid) or {}).get("name") or f"ID {aid}"))
        rubric_rows.append({
            "title": rubric.get("title"),
            "points": rubric.get("points_possible"),
            "criteria": len(rubric.get("data") or []),
            "assignments": linked_assignments,
            "free_form_comments": rubric.get("free_form_criterion_comments"),
            "hide_score_total": rubric.get("hide_score_total"),
        })

    payload = {"schema_version": 1, "summary": summary, "findings": findings, "rubrics": rubric_rows, "grading_standards": grading_standards, "outcomes": outcomes, "grading_periods": grading_periods, "late_policy": late_policy}
    json_path = snapshot / "grading-audit.json"
    markdown_path = snapshot / "grading-audit.md"
    _write_json(json_path, payload)

    lines = _report_header("Grading, rubric, and outcomes audit", manifest, "Inventory and objective review of grade weighting, rubrics, grading standards, learning outcomes, grading periods, and late-policy settings.")
    lines.extend(["## Summary", ""])
    for key, value in summary.items():
        lines.append(f"- {key.replace('_', ' ').title()}: **{value}**")
    lines.append("")
    _add_findings(lines, findings)

    lines.extend(["## Rubrics", "", "| Rubric | Points | Criteria | Assignment associations | Free-form comments | Hide score total |", "|---|---:|---:|---|---|---|"])
    for row in rubric_rows:
        lines.append(
            f"| {_md(row['title'])} | {_num(row['points'])} | {row['criteria']} | {_md(', '.join(row['assignments']) or '—')} | "
            f"{_yes_no(row['free_form_comments'])} | {_yes_no(row['hide_score_total'])} |"
        )
    lines.extend(["", "## Late policy", ""])
    if _available(errors, "late-policy"):
        if late_policy:
            for key, value in sorted(late_policy.items()):
                if key not in {"id", "course_id", "created_at", "updated_at"}:
                    lines.append(f"- `{key}`: **{_md(value)}**")
        else:
            lines.append("No late policy is configured.")
    else:
        lines.append("Late-policy API data was unavailable.")

    lines.extend(["", "## Grading periods", ""])
    if grading_periods:
        lines.extend(["| Period | Start | End | Close | Weight | Closed |", "|---|---|---|---|---:|---|"])
        for item in grading_periods:
            lines.append(
                f"| {_md(item.get('title'))} | {_md(item.get('start_date'))} | {_md(item.get('end_date'))} | {_md(item.get('close_date'))} | "
                f"{_num(item.get('weight'))}% | {_yes_no(item.get('is_closed'))} |"
            )
    else:
        lines.append("None found." if _available(errors, "grading-periods") else "Grading-period API data was unavailable.")
    _write_markdown(markdown_path, lines)
    return markdown_path, json_path, findings, summary


def _build_integration_audit(snapshot: Path, manifest: dict[str, Any], errors: set[str]) -> tuple[Path, Path, list[dict[str, str]], dict[str, Any]]:
    tabs = _records(snapshot, "tabs")
    features = _records(snapshot, "features")
    tools = _records(snapshot, "external-tools")
    resource_links = _records(snapshot, "lti-resource-links")
    assignments = _records(snapshot, "assignments")
    new_quizzes = _records(snapshot, "new-quizzes")
    module_items = _grouped(snapshot, "module-items")

    findings: list[dict[str, str]] = []
    for name, count in _exact_duplicates(tools, "name"):
        findings.append(_finding("review", "external tools", f"This exact external-tool name appears {count} times in the returned tool inventory.", name))

    new_quiz_ids = {
        str(item.get("assignment_id") or item.get("id"))
        for item in new_quizzes
        if item.get("assignment_id") is not None or item.get("id") is not None
    }
    external_assignments = []
    for item in assignments:
        submission_types = {str(value).casefold() for value in (item.get("submission_types") or [])}
        if "external_tool" not in submission_types:
            continue
        attrs = item.get("external_tool_tag_attributes") if isinstance(item.get("external_tool_tag_attributes"), dict) else {}
        aid = str(item.get("id") or "")
        external_assignments.append({
            "name": item.get("name"),
            "kind": "New Quiz" if aid in new_quiz_ids else "External tool assignment",
            "domain": _domain(attrs.get("url")),
            "content_id": attrs.get("content_id"),
            "published": item.get("published"),
        })

    module_external = []
    for group, item in _flatten_group_items(module_items):
        if str(item.get("type") or "") not in {"ExternalTool", "ExternalUrl"}:
            continue
        module_external.append({
            "module": group.get("title"),
            "type": item.get("type"),
            "title": item.get("title"),
            "domain": _domain(item.get("external_url") or item.get("html_url")),
            "new_tab": item.get("new_tab"),
        })

    tool_rows = []
    for tool in tools:
        placements = tool.get("placements")
        placement_names = sorted(placements.keys()) if isinstance(placements, dict) else []
        tool_rows.append({
            "id": tool.get("id"),
            "name": tool.get("name"),
            "domain": tool.get("domain") or _domain(tool.get("url")),
            "privacy_level": tool.get("privacy_level"),
            "workflow_state": tool.get("workflow_state"),
            "placements": placement_names,
            "context_id": tool.get("context_id"),
            "context_type": tool.get("context_type"),
        })

    deleted_links = [item for item in resource_links if str(item.get("workflow_state") or "").casefold() == "deleted"]
    if deleted_links:
        findings.append(_finding("observation", "LTI resource links", f"{len(deleted_links)} deleted LTI resource link(s) were returned because the recon includes deleted links."))

    summary = {
        "tabs": len(tabs),
        "hidden_tabs": sum(1 for item in tabs if item.get("hidden") is True),
        "feature_flags": len(features),
        "external_tools": len(tools),
        "external_tool_assignments": len(external_assignments),
        "new_quizzes_using_lti": sum(1 for item in external_assignments if item["kind"] == "New Quiz"),
        "external_module_links": len(module_external),
        "lti_resource_links": len(resource_links),
        "deleted_lti_resource_links": len(deleted_links),
    }
    payload = {
        "schema_version": 1,
        "summary": summary,
        "findings": findings,
        "tabs": tabs,
        "features": features,
        "external_tools": tool_rows,
        "external_assignments": external_assignments,
        "module_external_links": module_external,
        "lti_resource_links": resource_links,
        "api_availability": {
            "external_tools": _available(errors, "external-tools"),
            "lti_resource_links": _available(errors, "lti-resource-links"),
        },
    }
    json_path = snapshot / "integration-audit.json"
    markdown_path = snapshot / "integration-audit.md"
    _write_json(json_path, payload)

    lines = _report_header("Navigation, feature, and LTI integration audit", manifest, "Inventory of course navigation, feature flags, external tools, LTI-backed assignments, module links, and LTI resource links.")
    lines.extend(["## Summary", ""])
    for key, value in summary.items():
        lines.append(f"- {key.replace('_', ' ').title()}: **{value}**")
    lines.append("")
    _add_findings(lines, findings)

    lines.extend(["## External-tool assignments", ""])
    if external_assignments:
        lines.extend(["| Pub | Kind | Assignment | Launch domain | Content ID |", "|---|---|---|---|---|"])
        for item in external_assignments:
            lines.append(f"| {_yes_no(item['published'])} | {_md(item['kind'])} | {_md(item['name'])} | {_md(item['domain'])} | {_md(item['content_id'] or '—')} |")
    else:
        lines.append("None found.")

    lines.extend(["", "## External tools", ""])
    if tool_rows:
        lines.extend(["| Tool | Domain | State | Privacy | Context | Placements |", "|---|---|---|---|---|---|"])
        for item in tool_rows:
            context = " / ".join(str(value) for value in (item["context_type"], item["context_id"]) if value is not None)
            lines.append(f"| {_md(item['name'])} | {_md(item['domain'])} | {_md(item['workflow_state'])} | {_md(item['privacy_level'])} | {_md(context or '—')} | {_md(', '.join(item['placements']) or '—')} |")
    else:
        lines.append("None returned." if _available(errors, "external-tools") else "External-tool API data was unavailable.")

    lines.extend(["", "## Course navigation tabs", "", "| # | Tab | Type | Hidden | Visibility |", "|---:|---|---|---|---|"])
    for item in sorted(tabs, key=lambda value: (value.get("position") is None, value.get("position") or 0)):
        lines.append(f"| {item.get('position') or ''} | {_md(item.get('label'))} | {_md(item.get('type'))} | {_yes_no(item.get('hidden'))} | {_md(item.get('visibility') or '—')} |")

    lines.extend(["", "## Feature flags", "", "| Feature | Display name | State | Applies to |", "|---|---|---|---|"])
    for item in sorted(features, key=lambda value: str(value.get("feature") or "")):
        flag = item.get("feature_flag") if isinstance(item.get("feature_flag"), dict) else {}
        lines.append(f"| {_md(item.get('feature'))} | {_md(item.get('display_name'))} | {_md(flag.get('state') or item.get('state') or '—')} | {_md(item.get('applies_to') or '—')} |")
    _write_markdown(markdown_path, lines)
    return markdown_path, json_path, findings, summary


def _build_migration_audit(snapshot: Path, manifest: dict[str, Any], errors: set[str]) -> tuple[Path, Path, list[dict[str, str]], dict[str, Any]]:
    migrations = _records(snapshot, "content-migrations")
    issues = _grouped(snapshot, "migration-issues")
    exports = _records(snapshot, "content-exports")

    findings: list[dict[str, str]] = []
    issue_rows = []
    for group in issues:
        migration_id = str(group.get("source_id") or "")
        migration_type = str(group.get("title") or "")
        for item in group.get("items") or []:
            if not isinstance(item, dict):
                continue
            row = {
                "migration_id": migration_id,
                "migration_type": migration_type,
                "workflow_state": item.get("workflow_state"),
                "issue_type": item.get("issue_type"),
                "description": item.get("description"),
                "created_at": item.get("created_at"),
                "fix_url": item.get("fix_issue_html_url"),
            }
            issue_rows.append(row)
            if str(item.get("workflow_state") or "").casefold() == "active":
                severity = "warning" if str(item.get("issue_type") or "").casefold() in {"warning", "error"} else "review"
                findings.append(_finding(severity, "content migration issue", str(item.get("description") or "Active migration issue."), f"migration {migration_id}"))

    migration_rows = []
    for migration in migrations:
        state = str(migration.get("workflow_state") or "")
        title = str(migration.get("migration_type") or migration.get("id") or "migration")
        if state.casefold() in {"failed", "error"}:
            findings.append(_finding("warning", "content migration", f"Migration workflow state is {state}.", title))
        elif state.casefold() in {"waiting_for_select", "pre_processing"}:
            findings.append(_finding("review", "content migration", f"Migration workflow state is {state}.", title))
        settings = migration.get("settings") if isinstance(migration.get("settings"), dict) else {}
        migration_rows.append({
            "id": migration.get("id"),
            "migration_type": migration.get("migration_type"),
            "workflow_state": state,
            "created_at": migration.get("created_at"),
            "updated_at": migration.get("updated_at"),
            "source_course_id": settings.get("source_course_id"),
            "question_bank_id": settings.get("question_bank_id"),
            "question_bank_name": settings.get("question_bank_name"),
        })

    export_rows = []
    for item in exports:
        state = str(item.get("workflow_state") or "")
        if state.casefold() == "failed":
            findings.append(_finding("review", "content export", "A content export has failed.", str(item.get("export_type") or item.get("id") or "export")))
        export_rows.append({
            "id": item.get("id"),
            "export_type": item.get("export_type"),
            "workflow_state": state,
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
        })

    summary = {
        "content_migrations": len(migrations),
        "migration_issues": len(issue_rows),
        "active_migration_issues": sum(1 for item in issue_rows if str(item["workflow_state"] or "").casefold() == "active"),
        "failed_migrations": sum(1 for item in migration_rows if str(item["workflow_state"]).casefold() in {"failed", "error"}),
        "content_exports": len(exports),
        "failed_exports": sum(1 for item in export_rows if str(item["workflow_state"]).casefold() == "failed"),
    }
    payload = {
        "schema_version": 1,
        "summary": summary,
        "findings": findings,
        "migrations": migration_rows,
        "migration_issues": issue_rows,
        "content_exports": export_rows,
        "api_availability": {
            "content_migrations": _available(errors, "content-migrations"),
            "migration_issues": _available(errors, "migration-issues"),
            "content_exports": _available(errors, "content-exports"),
        },
    }
    json_path = snapshot / "migration-audit.json"
    markdown_path = snapshot / "migration-audit.md"
    _write_json(json_path, payload)

    lines = _report_header("Course import, migration, and export audit", manifest, "Inventory of course content migrations, migration issues, and content exports. This is especially useful when investigating residue from old course copies or imports.")
    lines.extend(["## Summary", ""])
    for key, value in summary.items():
        lines.append(f"- {key.replace('_', ' ').title()}: **{value}**")
    lines.append("")
    _add_findings(lines, findings)

    lines.extend(["## Content migrations", ""])
    if migration_rows:
        lines.extend(["| ID | Type | State | Created | Updated | Source course | Question bank target |", "|---|---|---|---|---|---|---|"])
        for item in migration_rows:
            bank = item["question_bank_name"] or item["question_bank_id"] or "—"
            lines.append(f"| {_md(item['id'])} | {_md(item['migration_type'])} | {_md(item['workflow_state'])} | {_md(item['created_at'])} | {_md(item['updated_at'])} | {_md(item['source_course_id'] or '—')} | {_md(bank)} |")
    else:
        lines.append("None found." if _available(errors, "content-migrations") else "Content-migration API data was unavailable.")

    lines.extend(["", "## Migration issues", ""])
    if issue_rows:
        lines.extend(["| Migration | State | Severity | Description | Created |", "|---|---|---|---|---|"])
        for item in issue_rows:
            lines.append(f"| {_md(item['migration_id'])} | {_md(item['workflow_state'])} | {_md(item['issue_type'])} | {_md(item['description'])} | {_md(item['created_at'])} |")
    else:
        lines.append("None found." if _available(errors, "migration-issues") else "Migration-issue API data was unavailable.")
    _write_markdown(markdown_path, lines)
    return markdown_path, json_path, findings, summary


def _build_settings_audit(snapshot: Path, manifest: dict[str, Any], errors: set[str]) -> tuple[Path, Path, list[dict[str, str]], dict[str, Any]]:
    course = _load(snapshot, "course.json", {})
    settings = _load(snapshot, "settings.json", {})
    sections = _records(snapshot, "sections")
    group_categories = _records(snapshot, "group-categories")
    groups = _records(snapshot, "groups")
    blackout_dates = _records(snapshot, "blackout-dates")
    calendar_events = _records(snapshot, "calendar-events")

    findings: list[dict[str, str]] = []
    if not course.get("syllabus_body"):
        findings.append(_finding("review", "course settings", "No syllabus body is present in the captured course record."))
    if course.get("start_at") and course.get("end_at") and str(course["start_at"]) > str(course["end_at"]):
        findings.append(_finding("warning", "course dates", "Course start timestamp sorts after the end timestamp."))

    for name, count in _exact_duplicates(sections, "name"):
        findings.append(_finding("review", "sections", f"This exact section name appears {count} times.", name))
    for name, count in _exact_duplicates(group_categories, "name"):
        findings.append(_finding("review", "group categories", f"This exact group-category name appears {count} times.", name))
    for name, count in _exact_duplicates(groups, "name"):
        findings.append(_finding("review", "groups", f"This exact group name appears {count} times.", name))

    summary = {
        "workflow_state": course.get("workflow_state"),
        "default_view": course.get("default_view"),
        "time_zone": course.get("time_zone"),
        "course_format": course.get("course_format"),
        "sections": len(sections),
        "group_categories": len(group_categories),
        "groups": len(groups),
        "blackout_dates": len(blackout_dates),
        "calendar_events": len(calendar_events),
        "settings_keys": len(settings) if isinstance(settings, dict) else 0,
    }

    payload = {
        "schema_version": 1,
        "summary": summary,
        "findings": findings,
        "course": course,
        "settings": settings,
        "sections": sections,
        "group_categories": group_categories,
        "groups": groups,
        "blackout_dates": blackout_dates,
        "calendar_events": calendar_events,
        "api_availability": {
            "group_categories": _available(errors, "group-categories"),
            "groups": _available(errors, "groups"),
            "blackout_dates": _available(errors, "blackout-dates"),
        },
    }
    json_path = snapshot / "course-settings-audit.json"
    markdown_path = snapshot / "course-settings-audit.md"
    _write_json(json_path, payload)

    lines = _report_header("Course settings and supporting-feature audit", manifest, "Inventory of course identity/settings, sections, group categories, groups, blackout dates, and calendar-event configuration. No memberships or student records are requested.")
    lines.extend(["## Summary", ""])
    for key, value in summary.items():
        lines.append(f"- {key.replace('_', ' ').title()}: **{_md(value)}**")
    lines.append("")
    _add_findings(lines, findings)

    lines.extend(["## Course settings", "", "| Setting | Value |", "|---|---|"])
    for key, value in sorted((settings.items() if isinstance(settings, dict) else [])):
        if isinstance(value, (dict, list)):
            rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
        else:
            rendered = str(value)
        lines.append(f"| `{_md(key)}` | {_md(rendered)} |")

    lines.extend(["", "## Sections", "", "| Section | Start | End | Restricted to section dates |", "|---|---|---|---|"])
    for item in sections:
        lines.append(f"| {_md(item.get('name'))} | {_md(item.get('start_at') or '—')} | {_md(item.get('end_at') or '—')} | {_yes_no(item.get('restrict_enrollments_to_section_dates'))} |")

    lines.extend(["", "## Blackout dates", ""])
    if blackout_dates:
        lines.extend(["| Title | Start | End |", "|---|---|---|"])
        for item in blackout_dates:
            lines.append(f"| {_md(item.get('event_title'))} | {_md(item.get('start_date'))} | {_md(item.get('end_date'))} |")
    else:
        lines.append("None found." if _available(errors, "blackout-dates") else "Blackout-date API data was unavailable.")
    _write_markdown(markdown_path, lines)
    return markdown_path, json_path, findings, summary


def _build_comprehensive(
    snapshot: Path,
    manifest: dict[str, Any],
    errors: set[str],
    reports: list[tuple[str, Path, Path, list[dict[str, str]], dict[str, Any]]],
) -> tuple[Path, Path, list[dict[str, str]]]:
    all_findings: list[dict[str, str]] = []
    for _label, _md_path, _json_path, findings, _summary in reports:
        all_findings.extend(findings)

    coverage_specs = [
        ("Course settings", "settings", "settings.json"),
        ("Modules", "modules", "modules.json"),
        ("Module items", "module-items", "module-items.json"),
        ("Assignment groups", "assignment-groups", "assignment-groups.json"),
        ("Assignments", "assignments", "assignments.json"),
        ("Classic quizzes", "classic-quizzes", "classic-quizzes.json"),
        ("Classic quiz questions", "classic-quiz-questions", "classic-quiz-questions.json"),
        ("Classic quiz question groups", "classic-quiz-groups", "classic-quiz-groups.json"),
        ("Classic Question Banks", "question-banks", "question-banks.json"),
        ("Question Bank questions", "question-bank-questions", "question-bank-questions.json"),
        ("New Quizzes", "new-quizzes", "new-quizzes.json"),
        ("New Quiz items", "new-quiz-items", "new-quiz-items.json"),
        ("Pages", "pages", "pages.json"),
        ("Rubrics", "rubrics", "rubrics.json"),
        ("Discussions", "discussions", "discussions.json"),
        ("Announcements", "announcements", "announcements.json"),
        ("Files", "files", "files.json"),
        ("Folders", "folders", "folders.json"),
        ("Tabs", "tabs", "tabs.json"),
        ("Feature flags", "features", "features.json"),
        ("External tools", "external-tools", "external-tools.json"),
        ("LTI resource links", "lti-resource-links", "lti-resource-links.json"),
        ("Sections", "sections", "sections.json"),
        ("Group categories", "group-categories", "group-categories.json"),
        ("Groups", "groups", "groups.json"),
        ("Grading standards", "grading-standards", "grading-standards.json"),
        ("Grading periods", "grading-periods", "grading-periods.json"),
        ("Late policy", "late-policy", "late-policy.json"),
        ("Outcome links", "outcome-links", "outcome-links.json"),
        ("Blackout dates", "blackout-dates", "blackout-dates.json"),
        ("Calendar events", "calendar-events", "calendar-events.json"),
        ("Content migrations", "content-migrations", "content-migrations.json"),
        ("Migration issues", "migration-issues", "migration-issues.json"),
        ("Content exports", "content-exports", "content-exports.json"),
    ]
    coverage = []
    for label, key, filename in coverage_specs:
        value = _load(snapshot, filename, [])
        if isinstance(value, list):
            count = len(value)
        elif isinstance(value, dict):
            count = 1 if value else 0
        else:
            count = 0
        coverage.append({"resource": label, "key": key, "available": _available(errors, key), "count": count})

    severity_counts = Counter(item["severity"] for item in all_findings)
    payload = {
        "schema_version": 1,
        "course_id": manifest.get("course_id"),
        "course_name": manifest.get("course_name"),
        "read_only": True,
        "student_data_included": False,
        "summary": {
            "specialized_reports": len(reports),
            "findings": len(all_findings),
            "warnings": severity_counts.get("warning", 0),
            "reviews": severity_counts.get("review", 0),
            "observations": severity_counts.get("observation", 0),
            "api_resources_unavailable": sum(1 for item in coverage if not item["available"]),
        },
        "findings": all_findings,
        "coverage": coverage,
        "reports": [{"title": label, "markdown": md_path.name, "json": json_path.name, "summary": summary} for label, md_path, json_path, _findings, summary in reports],
    }
    json_path = snapshot / "comprehensive-audit.json"
    markdown_path = snapshot / "comprehensive-audit.md"
    _write_json(json_path, payload)

    lines = _report_header(
        "Comprehensive course audit",
        manifest,
        "This report combines the specialized read-only audits into one course-health view. Findings are intentionally conservative: warnings indicate objective structural conflicts, reviews identify items worth inspecting, and observations are inventory facts that may be completely intentional.",
    )
    lines.extend([
        "## Audit summary",
        "",
        f"- Specialized reports: **{len(reports)}**",
        f"- Warnings: **{severity_counts.get('warning', 0)}**",
        f"- Reviews: **{severity_counts.get('review', 0)}**",
        f"- Observations: **{severity_counts.get('observation', 0)}**",
        f"- API resource groups unavailable: **{sum(1 for item in coverage if not item['available'])}**",
        "",
        "## Specialized reports",
        "",
        "| Report | Warnings | Reviews | Observations |",
        "|---|---:|---:|---:|",
    ])
    for label, md_path, _json_path, findings, _summary in reports:
        counts = Counter(item["severity"] for item in findings)
        lines.append(f"| [{_md(label)}]({md_path.name}) | {counts.get('warning', 0)} | {counts.get('review', 0)} | {counts.get('observation', 0)} |")

    lines.extend(["", "## All warnings and review items", ""])
    actionable = [item for item in all_findings if item["severity"] in {"warning", "review"}]
    if not actionable:
        lines.append("None found.")
    else:
        for item in actionable:
            label = f" **{_md(item['item'])}**:" if item.get("item") else ""
            lines.append(f"- **{item['severity'].upper()} · {_md(item['area'])}**{label} {_md(item['message'])}")

    lines.extend(["", "## API coverage", "", "| Resource | Status | Captured records/groups |", "|---|---|---:|"])
    for item in coverage:
        lines.append(f"| {_md(item['resource'])} | {'Available' if item['available'] else 'Unavailable'} | {item['count']} |")

    lines.extend([
        "",
        "## Scope notes",
        "",
        "- Student rosters, enrollments, submissions, grades, quiz submissions, discussion entries, and other student-level records are intentionally excluded.",
        "- A resource marked unavailable means Canvas denied or did not expose that endpoint for this course/token; it does **not** mean the course has no such feature.",
        "- New Quiz item-bank reporting covers banks referenced by captured New Quiz items. It is not a course-wide inventory of every New Quiz item bank the instructor can access.",
        "- HTML review checks are lightweight structural signals only. They do not replace an accessibility checker or human review.",
        "",
    ])
    _write_markdown(markdown_path, lines)
    return markdown_path, json_path, all_findings


def build_audit_suite(snapshot: Path) -> AuditSuiteResult:
    snapshot = snapshot.resolve()
    manifest = _load(snapshot, "manifest.json", {})
    errors = _error_names(snapshot)

    generated: list[tuple[str, Path, Path, list[dict[str, str]], dict[str, Any]]] = []
    builders = [
        ("Assignment and gradebook audit", lambda: _build_assignment_audit(snapshot, manifest)),
        ("Module structure audit", lambda: _build_module_audit(snapshot, manifest)),
        ("Quiz audit", lambda: _build_quiz_audit(snapshot, manifest, errors)),
        ("Question bank audit", lambda: _build_question_bank_audit(snapshot, manifest, errors)),
        ("Content inventory and HTML review", lambda: _build_content_audit(snapshot, manifest)),
        ("Grading, rubric, and outcomes audit", lambda: _build_grading_audit(snapshot, manifest, errors)),
        ("Navigation, feature, and LTI integration audit", lambda: _build_integration_audit(snapshot, manifest, errors)),
        ("Course import, migration, and export audit", lambda: _build_migration_audit(snapshot, manifest, errors)),
        ("Course settings and supporting-feature audit", lambda: _build_settings_audit(snapshot, manifest, errors)),
    ]
    for label, builder in builders:
        markdown_path, json_path, findings, summary = builder()
        generated.append((label, markdown_path, json_path, findings, summary))

    comprehensive_path, _comprehensive_json, all_findings = _build_comprehensive(snapshot, manifest, errors, generated)
    refresh_report_index(snapshot)

    counts = Counter(item["severity"] for item in all_findings)
    return AuditSuiteResult(
        comprehensive_path=comprehensive_path,
        report_paths=tuple(item[1] for item in generated),
        finding_count=len(all_findings),
        warning_count=counts.get("warning", 0),
        review_count=counts.get("review", 0),
    )
