import json
import tempfile
import unittest
from pathlib import Path

from canvas_tool.date_audit import audit_dates


class DateAuditTests(unittest.TestCase):
    def write_json(self, path: Path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    def make_snapshot(self, root: Path) -> Path:
        snapshot = root / "snapshot"
        snapshot.mkdir()
        self.write_json(snapshot / "manifest.json", {
            "course_id": "18637",
            "course_name": "RCET 2265 Fall 2026",
            "course_code": "RCET2265-01-F26",
            "base_url": "https://isu.instructure.com",
        })
        self.write_json(snapshot / "course.json", {
            "time_zone": "America/Denver",
            "term": {"name": "Fall 2026"},
        })
        self.write_json(snapshot / "assignment-groups.json", [{"id": 1, "name": "Weekly Work"}])
        self.write_json(snapshot / "assignments.json", [
            {
                "id": 10,
                "name": "Labor Day assignment",
                "assignment_group_id": 1,
                "published": True,
                "due_at": "2026-09-07T18:00:00Z",
                "unlock_at": None,
                "lock_at": None,
                "has_overrides": False,
            },
            {
                "id": 11,
                "name": "Undated assignment",
                "assignment_group_id": 1,
                "published": True,
                "due_at": None,
                "unlock_at": None,
                "lock_at": None,
                "has_overrides": False,
            },
            {
                "id": 12,
                "name": "Bad availability",
                "assignment_group_id": 1,
                "published": True,
                "due_at": "2026-09-08T18:00:00Z",
                "unlock_at": "2026-09-09T18:00:00Z",
                "lock_at": None,
                "has_overrides": True,
            },
        ])
        self.write_json(snapshot / "modules.json", [
            {"id": 20, "name": "Week 2", "unlock_at": "2026-09-01T14:00:00Z"}
        ])
        return snapshot

    def make_calendar(self, root: Path) -> None:
        calendars = root / "calendars"
        calendars.mkdir()
        self.write_json(calendars / "isu-fall-2026.json", {
            "schema_version": 1,
            "name": "Idaho State University Fall 2026",
            "canvas_host": "isu.instructure.com",
            "term_name": "Fall 2026",
            "time_zone": "America/Denver",
            "start_date": "2026-08-24",
            "end_date": "2026-12-18",
            "no_class_periods": [
                {"name": "Labor Day holiday", "start": "2026-09-07", "end": "2026-09-07"}
            ],
            "special_periods": [],
        })

    def test_flags_calendar_collision_missing_date_and_bad_availability(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = self.make_snapshot(root)
            self.make_calendar(root)

            result = audit_dates(snapshot, root)
            report = json.loads(result.json_path.read_text(encoding="utf-8"))
            codes = {item["code"] for item in report["issues"]}

            self.assertEqual(result.calendar_name, "Idaho State University Fall 2026")
            self.assertEqual(result.assignment_count, 3)
            self.assertEqual(result.dated_count, 2)
            self.assertEqual(result.undated_count, 1)
            self.assertIn("no_class_day", codes)
            self.assertIn("missing_due_date", codes)
            self.assertIn("unlock_after_due", codes)
            self.assertIn("has_overrides", codes)
            self.assertTrue(result.markdown_path.exists())
            text = result.markdown_path.read_text(encoding="utf-8")
            self.assertIn("Labor Day holiday", text)
            self.assertIn("NO DUE DATE", text)
            self.assertIn("Module unlock dates", text)

    def test_runs_without_matching_institution_calendar(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = self.make_snapshot(root)
            result = audit_dates(snapshot, root)
            self.assertIsNone(result.calendar_name)
            text = result.markdown_path.read_text(encoding="utf-8")
            self.assertIn("none matched", text)


if __name__ == "__main__":
    unittest.main()
