import json
import tempfile
import unittest
from pathlib import Path

from canvas_tool.schedule_audit import audit_dates


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
                "grading_type": "points",
                "points_possible": 10,
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
                "grading_type": "points",
                "points_possible": 10,
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
                "grading_type": "points",
                "points_possible": 10,
                "published": True,
                "due_at": "2026-09-08T18:00:00Z",
                "unlock_at": "2026-09-09T18:00:00Z",
                "lock_at": None,
                "has_overrides": True,
            },
        ])
        self.write_json(snapshot / "modules.json", [
            {"id": 20, "name": "Anything", "unlock_at": "2026-09-01T14:00:00Z", "published": True}
        ])
        return snapshot

    def make_calendar(self, root: Path) -> None:
        calendars = root / "calendars"
        calendars.mkdir()
        self.write_json(calendars / "isu-fall-2026.json", {
            "schema_version": 2,
            "name": "Idaho State University Fall 2026",
            "canvas_host": "isu.instructure.com",
            "term_name": "Fall 2026",
            "time_zone": "America/Denver",
            "first_class_date": "2026-08-24",
            "last_class_date": "2026-12-18",
            "break_weeks": [
                {"name": "Thanksgiving Break", "start": "2026-11-23", "end": "2026-11-27"}
            ],
            "holidays": [
                {"name": "Labor Day holiday", "start": "2026-09-07", "end": "2026-09-07"}
            ],
            "special_periods": [
                {"name": "Finals week", "start": "2026-12-14", "end": "2026-12-18"}
            ],
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

            labor_day = next(item for item in report["assignments"] if item["id"] == 10)
            self.assertEqual(labor_day["week_number"], 3)
            self.assertEqual(labor_day["weekday"], "Monday")
            self.assertEqual(labor_day["date_local"], "September 7, 2026")

            text = result.markdown_path.read_text(encoding="utf-8")
            self.assertIn("First day of class: **Monday, August 24, 2026**", text)
            self.assertIn("Last day of class: **Friday, December 18, 2026**", text)
            self.assertIn("| Week | Date range (Sunday-Saturday) | Notes |", text)
            self.assertIn("August 23-29, 2026", text)
            self.assertIn("Labor Day holiday", text)
            self.assertIn("Thanksgiving Break", text)
            self.assertIn("| Week | Day | Date | Time | Item", text)
            self.assertIn("NO DUE DATE", text)
            self.assertIn("Module unlock dates", text)
            self.assertIn("Names and titles are not interpreted", text)

    def test_assignment_names_are_not_interpreted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = self.make_snapshot(root)
            self.make_calendar(root)
            self.write_json(snapshot / "assignments.json", [
                {
                    "id": 30,
                    "name": "W99 - Arbitrary Label",
                    "assignment_group_id": 1,
                    "grading_type": "points",
                    "points_possible": 10,
                    "published": True,
                    "due_at": "2026-09-28T05:00:00Z",
                    "unlock_at": None,
                    "lock_at": None,
                    "has_overrides": False,
                },
                {
                    "id": 31,
                    "name": "Week 2 - Also Just Text",
                    "assignment_group_id": 1,
                    "grading_type": "points",
                    "points_possible": 10,
                    "published": True,
                    "due_at": "2026-11-23T06:00:00Z",
                    "unlock_at": None,
                    "lock_at": None,
                    "has_overrides": False,
                },
            ])

            result = audit_dates(snapshot, root)
            report = json.loads(result.json_path.read_text(encoding="utf-8"))
            codes = [item["code"] for item in report["issues"]]

            self.assertNotIn("week_name_mismatch", codes)
            self.assertNotIn("week_name_break", codes)

            first = next(item for item in report["assignments"] if item["id"] == 30)
            self.assertEqual(first["week_number"], 6)

            break_item = next(item for item in report["assignments"] if item["id"] == 31)
            self.assertIsNone(break_item["week_number"])
            self.assertEqual(break_item["week_label"], "Thanksgiving Break")
            self.assertIn("no_class_day", codes)

            text = result.markdown_path.read_text(encoding="utf-8")
            self.assertNotIn("Name indicates", text)

    def test_runs_without_matching_institution_calendar(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = self.make_snapshot(root)
            result = audit_dates(snapshot, root)
            self.assertIsNone(result.calendar_name)
            report = json.loads(result.json_path.read_text(encoding="utf-8"))
            self.assertIsNone(report["assignments"][0]["week_number"])


if __name__ == "__main__":
    unittest.main()
