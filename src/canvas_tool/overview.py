from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CourseOverviewResult:
    markdown_path: Path
    json_path: Path
    module_count: int
    graded_item_count: int
    unplaced_graded_item_count: int
    schedule_issue_count: int


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def _yes_no(value: Any) -> str:
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return "?"


def _points(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _md(value: Any) -> str:
    text = str(value if value is not None else "")
    return text.replace("\n", " ").replace("\r", " ").replace("|", "\\|")


def _schedule_text(
    row: dict[str, Any] | None,
    field: str = "due_at",
    *,
    have_calendar: bool = True,
) -> str:
    if not row or not row.get(field):
        return "—"
    week_number = row.get("week_number")
    week_label = str(row.get("week_label") or "")
    parts: list[str] = []
    if week_number is not None:
        parts.append(f"W{week_number}")
    elif week_label:
        parts.append(week_label)
    elif have_calendar:
        parts.append("OUTSIDE")
    if row.get("weekday"):
        parts.append(str(row["weekday"]))
    if row.get("time_local"):
        parts.append(str(row["time_local"]))
    if row.get("date_local"):
        parts.append(str(row["date_local"]))
    return " · ".join(parts) or "—"


def _completion_requirement(value: Any) -> str:
    if not isinstance(value, dict) or not value:
        return "—"
    kind = str(value.get("type") or "")
    labels = {
        "must_view": "View",
        "must_contribute": "Contribute",
        "must_submit": "Submit",
        "must_mark_done": "Mark done",
        "min_score": "Minimum score",
    }
    label = labels.get(kind, kind or "Requirement")
    if value.get("min_score") is not None:
        label += f" ≥ {_points(value.get('min_score'))}"
    return label


def _graded_type(assignment: dict[str, Any]) -> str:
    submission_types = {str(value).casefold() for value in (assignment.get("submission_types") or [])}
    if "online_quiz" in submission_types:
        return "Quiz"
    if "discussion_topic" in submission_types:
        return "Graded discussion"
    if "external_tool" in submission_types:
        return "External tool"
    return "Assignment"


def _rubric_map(rubrics: list[dict[str, Any]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for rubric in rubrics:
        if not isinstance(rubric, dict):
            continue
        title = str(rubric.get("title") or "Rubric")
        for association in (rubric.get("associations") or []):
            if not isinstance(association, dict):
                continue
            association_type = str(association.get("association_type") or association.get("type") or "").casefold()
            if association_type != "assignment":
                continue
            assignment_id = association.get("association_id")
            if assignment_id is not None:
                result[str(assignment_id)] = title
    return result


def _assignment_rubric(assignment: dict[str, Any], rubric_by_assignment: dict[str, str]) -> str:
    settings = assignment.get("rubric_settings")
    if isinstance(settings, dict) and settings.get("title"):
        return str(settings["title"])
    assignment_id = assignment.get("id")
    if assignment_id is not None and str(assignment_id) in rubric_by_assignment:
        return rubric_by_assignment[str(assignment_id)]
    if assignment.get("rubric"):
        return "Attached rubric"
    return "—"


def _assignment_id_from_module_item(
    item: dict[str, Any],
    assignments: dict[str, dict[str, Any]],
    classic_quizzes: dict[str, dict[str, Any]],
    new_quizzes: dict[str, dict[str, Any]],
    discussions: dict[str, dict[str, Any]],
) -> str | None:
    details = item.get("content_details") if isinstance(item.get("content_details"), dict) else {}
    direct = item.get("assignment_id") or details.get("assignment_id")
    if direct is not None and str(direct) in assignments:
        return str(direct)

    item_type = str(item.get("type") or "").casefold()
    content_id = item.get("content_id")
    content_key = str(content_id) if content_id is not None else ""

    if item_type == "assignment" and content_key in assignments:
        return content_key

    if item_type == "quiz":
        for source in (classic_quizzes.get(content_key), new_quizzes.get(content_key)):
            if not isinstance(source, dict):
                continue
            assignment_id = source.get("assignment_id")
            if assignment_id is not None and str(assignment_id) in assignments:
                return str(assignment_id)
        if content_key in assignments:
            return content_key

    if item_type == "discussion":
        source = discussions.get(content_key)
        if isinstance(source, dict):
            assignment_id = source.get("assignment_id")
            if assignment_id is None and isinstance(source.get("assignment"), dict):
                assignment_id = source["assignment"].get("id")
            if assignment_id is not None and str(assignment_id) in assignments:
                return str(assignment_id)

    html_url = str(item.get("html_url") or "")
    match = re.search(r"/assignments/(\d+)(?:\b|/|$)", html_url)
    if match and match.group(1) in assignments:
        return match.group(1)
    return None


def _assign_to_text(record: dict[str, Any] | None, section_names: dict[str, str]) -> str:
    if record is None or record.get("available") is False:
        return "Unavailable from API"
    overrides = list(record.get("items") or [])
    if not overrides:
        return "Everyone"
    labels: list[str] = []
    for override in overrides:
        if not isinstance(override, dict):
            continue
        target_type = override.get("target_type")
        if target_type == "specific_students":
            labels.append(f"Specific students ({int(override.get('student_count') or 0)})")
        elif target_type == "section":
            section_id = str(override.get("course_section_id") or "")
            labels.append(section_names.get(section_id) or str(override.get("title") or f"Section {section_id}"))
        elif target_type == "group":
            labels.append(str(override.get("title") or "Group"))
        else:
            labels.append(str(override.get("title") or "Override"))
    return ", ".join(dict.fromkeys(labels)) or "Configured overrides"


def build_overview(snapshot: Path) -> CourseOverviewResult:
    snapshot = snapshot.resolve()
    manifest = _load(snapshot / "manifest.json", {})
    course = _load(snapshot / "course.json", {})
    modules = _load(snapshot / "modules.json", [])
    module_items = _load(snapshot / "module-items.json", [])
    module_overrides = _load(snapshot / "module-overrides.json", [])
    assignments_list = _load(snapshot / "assignments.json", [])
    assignment_groups = _load(snapshot / "assignment-groups.json", [])
    classic_list = _load(snapshot / "classic-quizzes.json", [])
    new_list = _load(snapshot / "new-quizzes.json", [])
    discussions_list = _load(snapshot / "discussions.json", [])
    rubrics = _load(snapshot / "rubrics.json", [])
    sections = _load(snapshot / "sections.json", [])
    date_report = _load(snapshot / "date-audit.json", {})
    recon_errors = _load(snapshot / "errors.json", [])
    have_calendar = bool(date_report.get("calendar"))

    assignments = {str(item.get("id")): item for item in assignments_list if isinstance(item, dict) and item.get("id") is not None}
    classic_quizzes = {str(item.get("id")): item for item in classic_list if isinstance(item, dict) and item.get("id") is not None}
    new_quizzes = {str(item.get("id")): item for item in new_list if isinstance(item, dict) and item.get("id") is not None}
    discussions = {str(item.get("id")): item for item in discussions_list if isinstance(item, dict) and item.get("id") is not None}
    group_names = {str(item.get("id")): str(item.get("name") or "") for item in assignment_groups if isinstance(item, dict)}
    module_names = {str(item.get("id")): str(item.get("name") or "") for item in modules if isinstance(item, dict)}
    section_names = {str(item.get("id")): str(item.get("name") or "") for item in sections if isinstance(item, dict)}
    rubric_by_assignment = _rubric_map(rubrics)

    items_by_module = {str(item.get("source_id")): item for item in module_items if isinstance(item, dict)}
    overrides_by_module = {str(item.get("source_id")): item for item in module_overrides if isinstance(item, dict)}
    date_rows = {str(item.get("id")): item for item in (date_report.get("assignments") or []) if isinstance(item, dict) and item.get("id") is not None}
    module_date_rows = {str(item.get("id")): item for item in (date_report.get("module_unlocks") or []) if isinstance(item, dict) and item.get("id") is not None}

    placed_assignment_ids: set[str] = set()
    module_rows: list[dict[str, Any]] = []
    unpublished_item_count = 0

    for module in sorted((item for item in modules if isinstance(item, dict)), key=lambda item: (item.get("position") is None, item.get("position") or 0)):
        module_id = str(module.get("id") or "")
        group = items_by_module.get(module_id, {})
        rendered_items: list[dict[str, Any]] = []
        for item in list(group.get("items") or []):
            if not isinstance(item, dict):
                continue
            assignment_id = _assignment_id_from_module_item(item, assignments, classic_quizzes, new_quizzes, discussions)
            assignment = assignments.get(assignment_id or "")
            if assignment_id:
                placed_assignment_ids.add(assignment_id)
            if item.get("published") is False:
                unpublished_item_count += 1

            points = None
            if assignment:
                points = assignment.get("points_possible")
            elif isinstance(item.get("content_details"), dict):
                points = item["content_details"].get("points_possible")

            rendered_items.append({
                "position": item.get("position"),
                "title": str(item.get("title") or ""),
                "type": str(item.get("type") or ""),
                "published": item.get("published"),
                "assignment_id": assignment_id,
                "due": _schedule_text(date_rows.get(assignment_id or ""), have_calendar=have_calendar) if assignment else "—",
                "assignment_group": group_names.get(str(assignment.get("assignment_group_id"))) if assignment else "—",
                "points": points,
                "rubric": _assignment_rubric(assignment, rubric_by_assignment) if assignment else "—",
                "completion_requirement": _completion_requirement(item.get("completion_requirement")),
            })

        prerequisites: list[str] = []
        for prerequisite_id in module.get("prerequisite_module_ids") or []:
            key = str(prerequisite_id)
            prerequisites.append(module_names.get(key) or f"[missing module {key}]")

        requirement_type = str(module.get("requirement_type") or "")
        if requirement_type == "one":
            completion_mode = "Complete one required item"
        elif requirement_type == "all":
            completion_mode = "Complete all required items"
        else:
            completion_mode = "—"

        module_rows.append({
            "id": module.get("id"),
            "position": module.get("position"),
            "name": str(module.get("name") or ""),
            "published": module.get("published"),
            "assign_to": _assign_to_text(overrides_by_module.get(module_id), section_names),
            "unlock": _schedule_text(module_date_rows.get(module_id), "unlock_at", have_calendar=have_calendar),
            "prerequisites": prerequisites,
            "require_sequential_progress": module.get("require_sequential_progress"),
            "completion_mode": completion_mode,
            "items": rendered_items,
        })

    graded_items = [item for item in assignments_list if isinstance(item, dict) and str(item.get("grading_type") or "").casefold() != "not_graded"]
    unplaced: list[dict[str, Any]] = []
    for assignment in graded_items:
        assignment_id = str(assignment.get("id") or "")
        if assignment_id in placed_assignment_ids:
            continue
        unplaced.append({
            "id": assignment.get("id"),
            "name": str(assignment.get("name") or ""),
            "type": _graded_type(assignment),
            "published": assignment.get("published"),
            "due": _schedule_text(date_rows.get(assignment_id), have_calendar=have_calendar),
            "assignment_group": group_names.get(str(assignment.get("assignment_group_id"))) or "—",
            "points": assignment.get("points_possible"),
            "rubric": _assignment_rubric(assignment, rubric_by_assignment),
        })

    group_counts: dict[str, int] = {}
    for assignment in graded_items:
        key = str(assignment.get("assignment_group_id") or "")
        group_counts[key] = group_counts.get(key, 0) + 1
    group_rows = [
        {
            "id": group.get("id"),
            "position": group.get("position"),
            "name": str(group.get("name") or ""),
            "weight": group.get("group_weight"),
            "graded_items": group_counts.get(str(group.get("id") or ""), 0),
        }
        for group in sorted((item for item in assignment_groups if isinstance(item, dict)), key=lambda item: (item.get("position") is None, item.get("position") or 0))
    ]

    schedule_issues = list(date_report.get("issues") or [])
    report = {
        "schema_version": 2,
        "course_id": manifest.get("course_id"),
        "course_name": manifest.get("course_name"),
        "course_code": manifest.get("course_code"),
        "read_only": True,
        "logic": "structured_fields_only",
        "summary": {
            "modules": len(module_rows),
            "module_items": sum(len(item["items"]) for item in module_rows),
            "graded_items": len(graded_items),
            "graded_items_not_in_modules": len(unplaced),
            "unpublished_module_items": unpublished_item_count,
            "schedule_issues": len(schedule_issues),
            "recon_errors": len(recon_errors),
            "weighted_assignment_groups": bool(course.get("apply_assignment_group_weights")),
        },
        "assignment_groups": group_rows,
        "schedule_issues": schedule_issues,
        "modules": module_rows,
        "graded_items_not_in_modules": unplaced,
    }

    json_path = snapshot / "course-overview.json"
    markdown_path = snapshot / "course-overview.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "# Course overview",
        "",
        f"- Course: **{manifest.get('course_name', 'unnamed course')}**",
        f"- Course code: `{manifest.get('course_code', '')}`",
        f"- Canvas course ID: `{manifest.get('course_id', '')}`",
        "- Mode: **read-only**. Names and titles are displayed but never interpreted as configuration.",
        "",
        "## At a glance",
        "",
        f"- Modules: **{len(module_rows)}**",
        f"- Module items: **{sum(len(item['items']) for item in module_rows)}**",
        f"- Graded items: **{len(graded_items)}**",
        f"- Graded items not represented in any module: **{len(unplaced)}**",
        f"- Unpublished module items: **{unpublished_item_count}**",
        f"- Structured schedule/availability flags: **{len(schedule_issues)}**",
        f"- Weighted assignment groups: **{_yes_no(bool(course.get('apply_assignment_group_weights')))}**",
        f"- Recon retrieval errors: **{len(recon_errors)}**",
        "",
        "## Schedule / availability flags",
        "",
    ]
    if schedule_issues:
        for issue in schedule_issues:
            label = issue.get("assignment") or issue.get("module")
            prefix = f" **{label}**:" if label else ""
            lines.append(f"- **{str(issue.get('severity', 'review')).upper()}**{prefix} {issue.get('message', '')}")
    else:
        lines.append("None found.")

    lines.extend([
        "",
        "## Assignment groups / grade categories",
        "",
        "| # | Group | Weight | Graded items |",
        "|---:|---|---:|---:|",
    ])
    for group in group_rows:
        weight = "—" if group.get("weight") is None else f"{_points(group.get('weight'))}%"
        lines.append(f"| {group.get('position') or ''} | {_md(group['name'])} | {weight} | {group['graded_items']} |")

    lines.extend(["", "## Modules", ""])
    for module in module_rows:
        lines.extend([
            f"### {module.get('position') or '?'}. {module['name']}",
            "",
            f"- Published: **{_yes_no(module.get('published'))}**",
            f"- Assign to: **{module['assign_to']}**",
            f"- Lock until: **{module['unlock']}**",
            f"- Prerequisites: **{', '.join(module['prerequisites']) if module['prerequisites'] else 'None'}**",
            f"- Requirements: **{module['completion_mode']}**",
            f"- Require sequential progress: **{_yes_no(module.get('require_sequential_progress'))}**",
            "",
        ])
        if not module["items"]:
            lines.extend(["_No items in this module._", ""])
            continue
        lines.extend([
            "| # | Pub | Type | Item | Due | Grade category/group | Points | Rubric | Requirement |",
            "|---:|---|---|---|---|---|---:|---|---|",
        ])
        for item in module["items"]:
            lines.append(
                f"| {item.get('position') or ''} | {_yes_no(item.get('published'))} | {_md(item['type'])} | {_md(item['title'])} | {_md(item['due'])} | {_md(item['assignment_group'])} | {_points(item.get('points'))} | {_md(item['rubric'])} | {_md(item['completion_requirement'])} |"
            )
        lines.append("")

    lines.extend(["## Graded items not represented in a module", ""])
    if not unplaced:
        lines.append("None found.")
    else:
        lines.extend([
            "These objects are returned by Canvas's Assignments API but were not matched to any module item. This is an inventory observation, not an automatic error.",
            "",
            "| Pub | Type | Item | Due | Grade category/group | Points | Rubric |",
            "|---|---|---|---|---|---:|---|",
        ])
        for item in unplaced:
            lines.append(f"| {_yes_no(item.get('published'))} | {_md(item['type'])} | {_md(item['name'])} | {_md(item['due'])} | {_md(item['assignment_group'])} | {_points(item.get('points'))} | {_md(item['rubric'])} |")

    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return CourseOverviewResult(
        markdown_path=markdown_path,
        json_path=json_path,
        module_count=len(module_rows),
        graded_item_count=len(graded_items),
        unplaced_graded_item_count=len(unplaced),
        schedule_issue_count=len(schedule_issues),
    )
