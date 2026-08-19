import json
import tempfile
import unittest
from pathlib import Path

from canvas_tool.course_audit import audit_course


class CourseAuditTests(unittest.TestCase):
    def write_json(self, path: Path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_combines_structure_date_and_duplicate_checks(self):
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
                "name": "W15 - Example",
                "assignment_group_id": 1,
                "published": True,
                "due_at": None,
                "unlock_at": None,
                "lock_at": None,
                "has_overrides": False,
            }])
            self.write_json(snapshot / "modules.json", [{"id": 5, "name": "W5", "position": 1}])
            self.write_json(snapshot / "module-items.json", [{
                "source_id": "5",
                "title": "W5",
                "items": [{"id": 50, "type": "Assignment", "title": "W15 - Example"}],
            }])
            self.write_json(snapshot / "normalized.json", {
                "modules": [],
                "assignment_groups": [],
                "assignments": [],
                "classic_quizzes": [],
                "new_quizzes": [],
                "pages": [],
                "rubrics": [],
                "discussions": [],
                "announcements": [],
                "files": [],
            })

            result = audit_course(snapshot, root)
            report = json.loads(result.json_path.read_text(encoding="utf-8"))

            self.assertEqual(result.structure_issue_count, 2)
            self.assertEqual(result.date_issue_count, 1)
            self.assertEqual(result.duplicate_count, 0)
            self.assertEqual(report["summary"]["structure_issues"], 2)
            text = result.markdown_path.read_text(encoding="utf-8")
            self.assertIn("Module 'W5' declares Week 5", text)
            self.assertIn("no Week 15 module exists", text)
            self.assertIn("No due date is set", text)


if __name__ == "__main__":
    unittest.main()
