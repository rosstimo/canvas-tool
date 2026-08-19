import json
import tempfile
import unittest
from pathlib import Path

from canvas_tool.course_audit import audit_course


class CourseAuditTests(unittest.TestCase):
    def write_json(self, path: Path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_names_are_not_interpreted_as_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = root / "snapshot"
            snapshot.mkdir()

            self.write_json(snapshot / "manifest.json", {
                "course_id": "1",
                "course_name": "Test Course",
                "course_code": "TEST-F26",
                "base_url": "https://example.instructure.com",
            })
            self.write_json(snapshot / "course.json", {
                "time_zone": "America/Denver",
                "term": {"name": "Fall 2026"},
            })
            self.write_json(snapshot / "assignment-groups.json", [{"id": 1, "name": "Assignments"}])
            self.write_json(snapshot / "assignments.json", [{
                "id": 15,
                "name": "W99 - Arbitrary Text",
                "assignment_group_id": 1,
                "grading_type": "points",
                "points_possible": 10,
                "published": True,
                "due_at": None,
                "unlock_at": None,
                "lock_at": None,
                "has_overrides": False,
            }])
            self.write_json(snapshot / "modules.json", [{
                "id": 5,
                "name": "Totally Different Name",
                "position": 1,
                "published": True,
                "prerequisite_module_ids": [],
                "require_sequential_progress": False,
            }])
            self.write_json(snapshot / "module-items.json", [{
                "source_id": "5",
                "title": "Totally Different Name",
                "items": [{
                    "id": 50,
                    "content_id": 15,
                    "position": 1,
                    "published": True,
                    "type": "Assignment",
                    "title": "W99 - Arbitrary Text",
                }],
            }])
            self.write_json(snapshot / "module-overrides.json", [{
                "source_id": "5",
                "available": True,
                "items": [],
            }])
            self.write_json(snapshot / "classic-quizzes.json", [])
            self.write_json(snapshot / "new-quizzes.json", [])
            self.write_json(snapshot / "discussions.json", [])
            self.write_json(snapshot / "rubrics.json", [])
            self.write_json(snapshot / "sections.json", [])
            self.write_json(snapshot / "errors.json", [])

            result = audit_course(snapshot, root)
            report = json.loads(result.json_path.read_text(encoding="utf-8"))

            self.assertEqual(result.schedule_issue_count, 1)
            self.assertEqual(result.unplaced_graded_item_count, 0)
            self.assertEqual(result.recon_error_count, 0)
            self.assertEqual(report["summary"]["schedule_issues"], 1)
            text = result.markdown_path.read_text(encoding="utf-8")
            self.assertIn("No due date is set", text)
            self.assertNotIn("Week 99", text)
            self.assertNotIn("name indicates", text.casefold())


if __name__ == "__main__":
    unittest.main()
