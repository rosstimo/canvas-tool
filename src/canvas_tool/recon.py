from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .api import CanvasApiError, CanvasClient
from .course import resolve_course
from .normalize import normalize_snapshot
from .privacy import sanitize
from .report_index import refresh_report_index


@dataclass
class ReconResult:
    path: Path
    errors: list[dict[str, str]]


class Recon:
    def __init__(self, client: CanvasClient, root: Path):
        self.client = client
        self.root = root

    def run(self, target_text: str, requested_output: Path | None = None) -> ReconResult:
        target = resolve_course(target_text, self.client.base_url)
        course_id = target.course_id
        host = target.base_url.removeprefix("https://")
        output = requested_output or self.root / "snapshots" / host / course_id
        output.mkdir(parents=True, exist_ok=True)
        errors: list[dict[str, str]] = []
        captured: dict[str, Any] = {}

        print(f"Recon: {target.base_url} (course {course_id})", file=sys.stderr)
        course = self.client.request_json("GET", f"/api/v1/courses/{course_id}?include[]=permissions&include[]=term&include[]=syllabus_body")
        captured["course"] = sanitize(course)
        self._write_json(output / "course.json", captured["course"])

        name = course.get("name") or "unnamed course"
        code = course.get("course_code") or ""
        manifest = {
            "schema_version": 1,
            "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "base_url": target.base_url,
            "canonical_course_url": f"{target.base_url}/courses/{course_id}",
            "course_id": course_id,
            "course_name": name,
            "course_code": code,
            "student_data_included": False,
        }
        self._write_json(output / "manifest.json", manifest)

        def get(name_key: str, endpoint: str, collection: bool) -> Any:
            print(f"  {name_key:<28}", end="", file=sys.stderr)
            try:
                value = self.client.paginate(endpoint) if collection else self.client.request_json("GET", endpoint)
                value = sanitize(value)
                captured[name_key] = value
                self._write_json(output / f"{name_key}.json", value)
                print(f"{len(value)} items" if collection else "ok", file=sys.stderr)
                return value
            except CanvasApiError:
                errors.append({"name": name_key, "endpoint": endpoint})
                value = [] if collection else {}
                captured[name_key] = value
                self._write_json(output / f"{name_key}.json", value)
                print("unavailable", file=sys.stderr)
                return value

        def expand(
            name_key: str,
            index: list[dict[str, Any]],
            row: Callable[[dict[str, Any]], tuple[Any, str, Any]],
            endpoint_template: str,
            collection: bool,
            grouped: bool,
        ) -> list[Any]:
            print(f"  {name_key:<28}", end="", file=sys.stderr)
            result: list[Any] = []
            total_items = 0
            for source in index:
                source_id, title, position = row(source)
                if source_id is None:
                    continue
                endpoint = endpoint_template.format(id=source_id)
                try:
                    value = self.client.paginate(endpoint) if collection else self.client.request_json("GET", endpoint)
                    value = sanitize(value)
                except CanvasApiError:
                    errors.append({"name": f"{name_key}:{source_id}", "endpoint": endpoint})
                    continue
                if grouped:
                    items = value if isinstance(value, list) else []
                    total_items += len(items)
                    result.append({"source_id": str(source_id), "title": title, "source_position": position, "items": items})
                else:
                    result.append(value)
            captured[name_key] = result
            self._write_json(output / f"{name_key}.json", result)
            print(f"{len(result)} groups, {total_items} items" if grouped else f"{len(result)} records", file=sys.stderr)
            return result

        get("settings", f"/api/v1/courses/{course_id}/settings", False)
        get("tabs", f"/api/v1/courses/{course_id}/tabs", True)

        modules = get("modules", f"/api/v1/courses/{course_id}/modules", True)
        expand(
            "module-items",
            modules,
            lambda item: (item.get("id"), item.get("name") or "", item.get("position")),
            f"/api/v1/courses/{course_id}/modules/{{id}}/items?include[]=content_details",
            True,
            True,
        )

        get("assignment-groups", f"/api/v1/courses/{course_id}/assignment_groups", True)
        get("assignments", f"/api/v1/courses/{course_id}/assignments", True)

        classic = get("classic-quizzes", f"/api/v1/courses/{course_id}/quizzes", True)
        expand(
            "classic-quiz-questions",
            classic,
            lambda item: (item.get("id"), item.get("title") or "", None),
            f"/api/v1/courses/{course_id}/quizzes/{{id}}/questions",
            True,
            True,
        )
        expand(
            "classic-quiz-groups",
            classic,
            lambda item: (item.get("id"), item.get("title") or "", None),
            f"/api/v1/courses/{course_id}/quizzes/{{id}}/groups",
            True,
            True,
        )

        question_banks = get(
            "question-banks",
            f"/api/v1/question_banks?context_type=Course&context_id={course_id}&include_question_count=true",
            True,
        )
        expand(
            "question-bank-questions",
            question_banks,
            lambda item: (item.get("id"), item.get("title") or "", None),
            "/api/v1/question_banks/{id}/questions",
            True,
            True,
        )

        new_quizzes = get("new-quizzes", f"/api/quiz/v1/courses/{course_id}/quizzes", True)
        expand(
            "new-quiz-items",
            new_quizzes,
            lambda item: (item.get("assignment_id") or item.get("id"), item.get("title") or "", None),
            f"/api/quiz/v1/courses/{course_id}/quizzes/{{id}}/items",
            True,
            True,
        )

        pages_index = get("pages-index", f"/api/v1/courses/{course_id}/pages", True)
        expand(
            "pages",
            pages_index,
            lambda item: (item.get("page_id"), item.get("title") or "", None),
            f"/api/v1/courses/{course_id}/pages/page_id:{{id}}",
            False,
            False,
        )

        rubrics_index = get("rubrics-index", f"/api/v1/courses/{course_id}/rubrics", True)
        expand(
            "rubrics",
            rubrics_index,
            lambda item: (item.get("id"), item.get("title") or "", None),
            f"/api/v1/courses/{course_id}/rubrics/{{id}}?include[]=associations",
            False,
            False,
        )

        get("discussions", f"/api/v1/courses/{course_id}/discussion_topics", True)
        get("announcements", f"/api/v1/courses/{course_id}/discussion_topics?only_announcements=true", True)
        get("files", f"/api/v1/courses/{course_id}/files", True)
        get("folders", f"/api/v1/courses/{course_id}/folders", True)

        get("features", f"/api/v1/courses/{course_id}/features", True)
        get("external-tools", f"/api/v1/courses/{course_id}/external_tools?include_parents=true", True)
        get("lti-resource-links", f"/api/v1/courses/{course_id}/lti_resource_links?include_deleted=true", True)

        get("sections", f"/api/v1/courses/{course_id}/sections", True)
        get("group-categories", f"/api/v1/courses/{course_id}/group_categories?collaboration_state=all", True)
        get("groups", f"/api/v1/courses/{course_id}/groups?collaboration_state=all", True)

        get("grading-standards", f"/api/v1/courses/{course_id}/grading_standards", True)
        get("grading-periods", f"/api/v1/courses/{course_id}/grading_periods", True)
        get("late-policy", f"/api/v1/courses/{course_id}/late_policy", False)
        get("outcome-groups", f"/api/v1/courses/{course_id}/outcome_groups", True)
        get("outcome-links", f"/api/v1/courses/{course_id}/outcome_group_links?outcome_style=full&outcome_group_style=full", True)

        get("blackout-dates", f"/api/v1/courses/{course_id}/blackout_dates", True)
        get("calendar-events", f"/api/v1/calendar_events?context_codes[]=course_{course_id}&all_events=true", True)

        migrations = get("content-migrations", f"/api/v1/courses/{course_id}/content_migrations", True)
        expand(
            "migration-issues",
            migrations,
            lambda item: (item.get("id"), item.get("migration_type") or "", None),
            f"/api/v1/courses/{course_id}/content_migrations/{{id}}/migration_issues",
            True,
            True,
        )
        get("content-exports", f"/api/v1/courses/{course_id}/content_exports", True)

        normalized = normalize_snapshot(captured)
        self._write_json(output / "normalized.json", normalized)
        self._write_json(output / "errors.json", errors)
        manifest["error_count"] = len(errors)
        manifest["errors_file"] = "errors.json"
        self._write_json(output / "manifest.json", manifest)
        self._write_summary(output, manifest, captured, errors)
        refresh_report_index(output)
        print(f"\nRecon written to {output}", file=sys.stderr)
        return ReconResult(path=output, errors=errors)

    @staticmethod
    def _write_json(path: Path, value: Any) -> None:
        path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    @staticmethod
    def _write_summary(output: Path, manifest: dict[str, Any], data: dict[str, Any], errors: list[dict[str, str]]) -> None:
        module_item_count = sum(len(record.get("items") or []) for record in data.get("module-items", []))
        grouped_counts = {
            "Classic quiz questions": sum(len(record.get("items") or []) for record in data.get("classic-quiz-questions", [])),
            "Classic quiz question groups": sum(len(record.get("items") or []) for record in data.get("classic-quiz-groups", [])),
            "Question Bank questions": sum(len(record.get("items") or []) for record in data.get("question-bank-questions", [])),
            "New Quiz items": sum(len(record.get("items") or []) for record in data.get("new-quiz-items", [])),
            "Migration issues": sum(len(record.get("items") or []) for record in data.get("migration-issues", [])),
        }
        specs = [
            ("Modules", "modules"),
            ("Module items", None),
            ("Assignments", "assignments"),
            ("Assignment groups", "assignment-groups"),
            ("Classic quizzes", "classic-quizzes"),
            ("Classic quiz questions", "@grouped"),
            ("Classic quiz question groups", "@grouped"),
            ("Classic Question Banks", "question-banks"),
            ("Question Bank questions", "@grouped"),
            ("New quizzes", "new-quizzes"),
            ("New Quiz items", "@grouped"),
            ("Pages", "pages"),
            ("Rubrics", "rubrics"),
            ("Discussions", "discussions"),
            ("Announcements", "announcements"),
            ("Files", "files"),
            ("Sections", "sections"),
            ("Group categories", "group-categories"),
            ("Groups", "groups"),
            ("External tools", "external-tools"),
            ("LTI resource links", "lti-resource-links"),
            ("Grading standards", "grading-standards"),
            ("Grading periods", "grading-periods"),
            ("Outcome links", "outcome-links"),
            ("Blackout dates", "blackout-dates"),
            ("Calendar events", "calendar-events"),
            ("Content migrations", "content-migrations"),
            ("Migration issues", "@grouped"),
            ("Content exports", "content-exports"),
        ]
        lines = [
            "# Canvas course recon",
            "",
            f"- Course: **{manifest['course_name']}**",
            f"- Course code: `{manifest['course_code']}`",
            f"- Canvas course ID: `{manifest['course_id']}`",
            f"- Canvas origin: `{manifest['base_url']}`",
            f"- Captured: `{manifest['captured_at']}`",
            "",
            "## Counts",
            "",
            "| Resource | Count |",
            "|---|---:|",
        ]
        for label, key in specs:
            if key is None:
                count = module_item_count
            elif key == "@grouped":
                count = grouped_counts.get(label, 0)
            else:
                count = len(data.get(key, []))
            lines.append(f"| {label} | {count} |")
        lines += [
            "",
            "## Notes",
            "",
            "`normalized.json` omits Canvas object IDs and concrete semester dates where practical so copied courses can be compared with less noise. Other JSON files contain sanitized API results. Student rosters, enrollments, submissions, grades, quiz submissions, and discussion entries are not requested.",
            "",
            "All requested resources were retrieved successfully." if not errors else "Unavailable resources are listed in `errors.json`. An unavailable API endpoint does not mean the course has no content of that type.",
        ]
        (output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
