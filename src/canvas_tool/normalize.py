from __future__ import annotations

import copy
import re
from typing import Any


_DROP_KEYS = {
    "id", "quiz_id", "course_id", "assignment_id", "assessment_question_id",
    "quiz_group_id", "item_id", "entry_id", "context_id", "rubric_id",
    "rubric_association_id", "access_code", "student_access_code", "verifier",
    "html_url", "url", "api_url", "created_at", "updated_at",
}

_SECRET_KEYS = {
    "access_code", "student_access_code", "access_code_expiration", "verifier",
    "secure_params", "submissions_download_url", "speed_grader_url",
    "message_students_url", "quiz_submissions_url", "quiz_statistics_url",
    "quiz_reports_url", "quiz_submission_versions_html_url", "mobile_url",
    "preview_url", "thumbnail_url", "author", "user", "participants",
    "lockdown_browser_monitor_data", "ip_filter", "ics",
}


def sanitize(value: Any) -> Any:
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: sanitize(item) for key, item in value.items() if key not in _SECRET_KEYS}
    if "filename" in result and "folder_id" in result:
        result.pop("url", None)
    return result


def normalize_html(value: Any) -> Any:
    if value is None or not isinstance(value, str):
        return value
    replacements = [
        (r"/courses/\d+", "/courses/<COURSE_ID>"),
        (r"/files/\d+", "/files/<FILE_ID>"),
        (r"/assignments/\d+", "/assignments/<ASSIGNMENT_ID>"),
        (r"/quizzes/\d+", "/quizzes/<QUIZ_ID>"),
        (r"/modules/\d+", "/modules/<MODULE_ID>"),
    ]
    for pattern, replacement in replacements:
        value = re.sub(pattern, replacement, value)
    return value


def strip_canvas_ids(value: Any) -> Any:
    if isinstance(value, list):
        return [strip_canvas_ids(item) for item in value]
    if not isinstance(value, dict):
        return value
    return {key: strip_canvas_ids(item) for key, item in value.items() if key not in _DROP_KEYS}


def _sort(items: list[dict[str, Any]], *keys: str) -> list[dict[str, Any]]:
    def keyfn(item: dict[str, Any]) -> tuple[Any, ...]:
        result: list[Any] = []
        for key in keys:
            value = item.get(key)
            result.append((value is None, value if value is not None else ""))
        return tuple(result)
    return sorted(items, key=keyfn)


def normalize_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    course = data.get("course", {})
    settings = data.get("settings", {})
    tabs = data.get("tabs", [])
    modules = data.get("modules", [])
    module_items = data.get("module-items", [])
    groups = data.get("assignment-groups", [])
    assignments = data.get("assignments", [])
    classic_quizzes = data.get("classic-quizzes", [])
    classic_questions = data.get("classic-quiz-questions", [])
    new_quizzes = data.get("new-quizzes", [])
    new_items = data.get("new-quiz-items", [])
    pages = data.get("pages", [])
    rubrics = data.get("rubrics", [])
    discussions = data.get("discussions", [])
    announcements = data.get("announcements", [])
    files = data.get("files", [])
    folders = data.get("folders", [])
    features = data.get("features", [])
    grading_standards = data.get("grading-standards", [])
    outcome_links = data.get("outcome-links", [])
    calendar_events = data.get("calendar-events", [])

    group_names = {str(item.get("id")): item.get("name") for item in groups}
    assignment_names = {str(item.get("id")): item.get("name") for item in assignments}
    module_names = {str(item.get("id")): item.get("name") for item in modules}
    module_meta = {str(item.get("id")): item for item in modules}

    normalized_modules: list[dict[str, Any]] = []
    for record in module_items:
        meta = module_meta.get(str(record.get("source_id")), {})
        prerequisites = [module_names.get(str(module_id), "<unknown module>") for module_id in (meta.get("prerequisite_module_ids") or [])]
        items = []
        for item in record.get("items") or []:
            items.append({
                "title": item.get("title"), "type": item.get("type"), "position": item.get("position"),
                "indent": item.get("indent"), "completion_requirement": item.get("completion_requirement"),
                "external_url": item.get("external_url"), "new_tab": item.get("new_tab"),
                "content_details": strip_canvas_ids(item.get("content_details")),
            })
        normalized_modules.append({
            "name": record.get("title"), "position": record.get("source_position"),
            "published": meta.get("published"), "require_sequential_progress": meta.get("require_sequential_progress"),
            "prerequisites": sorted(prerequisites), "items": _sort(items, "position", "title"),
        })

    normalized_groups = []
    for group in groups:
        rules = group.get("rules")
        normalized_rules = None
        if rules is not None:
            normalized_rules = {
                "drop_lowest": rules.get("drop_lowest"), "drop_highest": rules.get("drop_highest"),
                "never_drop": sorted(assignment_names.get(str(item), "<unknown assignment>") for item in (rules.get("never_drop") or [])),
            }
        normalized_groups.append({"name": group.get("name"), "position": group.get("position"), "group_weight": group.get("group_weight"), "rules": normalized_rules})

    normalized_assignments = [{
        "name": item.get("name"), "description": normalize_html(item.get("description")),
        "assignment_group": group_names.get(str(item.get("assignment_group_id"))),
        "points_possible": item.get("points_possible"), "grading_type": item.get("grading_type"),
        "submission_types": item.get("submission_types"), "published": item.get("published"),
        "omit_from_final_grade": item.get("omit_from_final_grade"), "peer_reviews": item.get("peer_reviews"),
        "automatic_peer_reviews": item.get("automatic_peer_reviews"), "anonymous_peer_reviews": item.get("anonymous_peer_reviews"),
        "grade_group_students_individually": item.get("grade_group_students_individually"),
    } for item in assignments]

    normalized_classic = [{
        "title": item.get("title"), "description": normalize_html(item.get("description")), "quiz_type": item.get("quiz_type"),
        "assignment_group": group_names.get(str(item.get("assignment_group_id"))), "points_possible": item.get("points_possible"),
        "time_limit": item.get("time_limit"), "shuffle_answers": item.get("shuffle_answers"), "allowed_attempts": item.get("allowed_attempts"),
        "scoring_policy": item.get("scoring_policy"), "one_question_at_a_time": item.get("one_question_at_a_time"),
        "cant_go_back": item.get("cant_go_back"), "published": item.get("published"), "question_count": item.get("question_count"),
        "show_correct_answers": item.get("show_correct_answers"),
    } for item in classic_quizzes]

    normalized_new = [{
        "title": item.get("title"), "instructions": normalize_html(item.get("instructions")),
        "assignment_group": group_names.get(str(item.get("assignment_group_id"))), "points_possible": item.get("points_possible"),
        "grading_type": item.get("grading_type"), "published": item.get("published"), "quiz_settings": strip_canvas_ids(item.get("quiz_settings")),
    } for item in new_quizzes]

    normalized_rubrics = []
    for rubric in rubrics:
        criteria = []
        for criterion in rubric.get("data") or []:
            ratings = [{"description": rating.get("description"), "long_description": rating.get("long_description"), "points": rating.get("points")} for rating in (criterion.get("ratings") or [])]
            criteria.append({"description": criterion.get("description"), "long_description": criterion.get("long_description"), "points": criterion.get("points"), "criterion_use_range": criterion.get("criterion_use_range"), "ratings": ratings})
        normalized_rubrics.append({"title": rubric.get("title"), "points_possible": rubric.get("points_possible"), "free_form_criterion_comments": rubric.get("free_form_criterion_comments"), "hide_score_total": rubric.get("hide_score_total"), "data": criteria})

    return {
        "course": {"syllabus_body": normalize_html(course.get("syllabus_body")), "default_view": course.get("default_view"), "apply_assignment_group_weights": course.get("apply_assignment_group_weights"), "grading_standard_present": course.get("grading_standard_id") is not None, "course_format": course.get("course_format")},
        "settings": {key: copy.deepcopy(value) for key, value in settings.items() if not key.endswith("_id")},
        "tabs": _sort([{"id": item.get("id"), "label": item.get("label"), "type": item.get("type"), "hidden": item.get("hidden"), "visibility": item.get("visibility"), "position": item.get("position")} for item in tabs], "position", "label"),
        "modules": _sort(normalized_modules, "position", "name"),
        "assignment_groups": _sort(normalized_groups, "position", "name"),
        "assignments": _sort(normalized_assignments, "assignment_group", "name"),
        "classic_quizzes": _sort(normalized_classic, "title"),
        "classic_quiz_questions": _sort([{"title": item.get("title"), "questions": strip_canvas_ids(item.get("items") or [])} for item in classic_questions], "title"),
        "new_quizzes": _sort(normalized_new, "title"),
        "new_quiz_items": _sort([{"title": item.get("title"), "items": strip_canvas_ids(item.get("items") or [])} for item in new_items], "title"),
        "pages": _sort([{"title": item.get("title"), "body": normalize_html(item.get("body")), "published": item.get("published"), "front_page": item.get("front_page"), "editing_roles": item.get("editing_roles")} for item in pages], "title"),
        "rubrics": _sort(normalized_rubrics, "title"),
        "discussions": _sort([{"title": item.get("title"), "message": normalize_html(item.get("message")), "discussion_type": item.get("discussion_type"), "published": item.get("published"), "pinned": item.get("pinned"), "require_initial_post": item.get("require_initial_post"), "allow_rating": item.get("allow_rating"), "only_graders_can_rate": item.get("only_graders_can_rate"), "sort_by_rating": item.get("sort_by_rating"), "anonymous_state": item.get("anonymous_state")} for item in discussions], "title"),
        "announcements": _sort([{"title": item.get("title"), "message": normalize_html(item.get("message")), "published": item.get("published")} for item in announcements], "title"),
        "files": _sort([{"display_name": item.get("display_name"), "filename": item.get("filename"), "size": item.get("size"), "content_type": item.get("content-type"), "hidden": item.get("hidden"), "locked": item.get("locked"), "visibility_level": item.get("visibility_level")} for item in files], "display_name"),
        "folders": _sort([{"name": item.get("name"), "full_name": item.get("full_name"), "position": item.get("position"), "locked": item.get("locked")} for item in folders], "full_name"),
        "features": _sort([{"feature": item.get("feature"), "display_name": item.get("display_name"), "applies_to": item.get("applies_to"), "state": (item.get("feature_flag") or {}).get("state")} for item in features], "feature"),
        "grading_standards": _sort([{"title": item.get("title"), "points_based": item.get("points_based"), "scaling_factor": item.get("scaling_factor"), "grading_scheme": item.get("grading_scheme")} for item in grading_standards], "title"),
        "outcomes": sorted([strip_canvas_ids(item) for item in outcome_links], key=lambda item: ((item.get("outcome") or {}).get("title") or "", (item.get("outcome") or {}).get("display_name") or "")),
        "calendar_events": _sort([{"title": item.get("title"), "description": normalize_html(item.get("description")), "location_name": item.get("location_name"), "location_address": item.get("location_address"), "all_day": item.get("all_day"), "workflow_state": item.get("workflow_state"), "important_dates": item.get("important_dates"), "blackout_date": item.get("blackout_date")} for item in calendar_events], "title"),
    }
