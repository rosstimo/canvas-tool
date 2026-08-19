import json
import tempfile
import unittest
from pathlib import Path

from canvas_tool.overview import build_overview


class OverviewTests(unittest.TestCase):
    def write_json(self, path: Path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_overview_joins_module_gradebook_rubric_and_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = Path(tmp)
            self.write_json(snapshot / "manifest.json", {
                "course_id": "1",
                "course_name": "Arbitrary Course",
                "course_code": "ARB-1",
            })
            self.write_json(snapshot / "modules.json", [
                {
                    "id": 10,
                    "position": 1,
                    "name": "Pointers and Memory",
                    "published": True,
                    "unlock_at": "2026-09-01T14:00:00Z",
                    "require_sequential_progress": True,
                    "requirement_type": "all",
                    "prerequisite_module_ids": [],
                },
                {
                    "id": 20,
                    "position": 2,
                    "name": "Capstone",
                    "published": False,
                    "unlock_at": None,
                    "require_sequential_progress": False,
                    "requirement_type": "one",
                    "prerequisite_module_ids": [10],
                },
            ])
            self.write_json(snapshot / "module-items.json", [
                {
                    "source_id": "10",
                    "items": [
                        {
                            "id": 101,
                            "content_id": 1001,
                            "position": 1,
                            "title": "Memory Lab",
                            "type": "Assignment",
                            "published": True,
                            "completion_requirement": {"type": "must_submit"},
                        },
                        {
                            "id": 102,
                            "position": 2,
                            "title": "Reference Page",
                            "type": "Page",
                            "published": False,
                            "completion_requirement": {"type": "must_view"},
                        },
                    ],
                },
                {"source_id": "20", "items": []},
            ])
            self.write_json(snapshot / "module-overrides.json", [
                {"source_id": "10", "available": True, "items": []},
                {
                    "source_id": "20",
                    "available": True,
                    "items": [{
                        "target_type": "section",
                        "course_section_id": 7,
                        "title": "Section 7",
                        "student_count": 0,
                    }],
                },
            ])
            self.write_json(snapshot / "sections.json", [{"id": 7, "name": "Lab Section A"}])
            self.write_json(snapshot / "assignment-groups.json", [
                {"id": 50, "name": "Labs"},
                {"id": 60, "name": "Exams"},
            ])
            self.write_json(snapshot / "assignments.json", [
                {
                    "id": 1001,
                    "name": "Memory Lab",
                    "assignment_group_id": 50,
                    "grading_type": "points",
                    "points_possible": 25,
                    "published": True,
                    "submission_types": ["online_upload"],
                    "rubric_settings": {"title": "Lab Rubric"},
                },
                {
                    "id": 1002,
                    "name": "Hidden Midterm",
                    "assignment_group_id": 60,
                    "grading_type": "points",
                    "points_possible": 100,
                    "published": False,
                    "submission_types": ["online_quiz"],
                },
            ])
            self.write_json(snapshot / "classic-quizzes.json", [])
            self.write_json(snapshot / "new-quizzes.json", [])
            self.write_json(snapshot / "discussions.json", [])
            self.write_json(snapshot / "rubrics.json", [])
            self.write_json(snapshot / "errors.json", [])
            self.write_json(snapshot / "date-audit.json", {
                "calendar": {"name": "Example"},
                "issues": [{"code": "missing_due_date", "severity": "review", "assignment": "Hidden Midterm", "message": "No due date is set."}],
                "assignments": [
                    {
                        "id": 1001,
                        "due_at": "2026-09-04T20:50:00Z",
                        "week_number": 2,
                        "week_label": "Week 2",
                        "weekday": "Friday",
                        "time_local": "2:50 PM MDT",
                        "date_local": "September 4, 2026",
                    },
                    {
                        "id": 1002,
                        "due_at": None,
                        "week_number": None,
                        "week_label": "",
                        "weekday": "",
                        "time_local": "",
                        "date_local": "",
                    },
                ],
                "module_unlocks": [
                    {
                        "id": 10,
                        "unlock_at": "2026-09-01T14:00:00Z",
                        "week_number": 2,
                        "week_label": "Week 2",
                        "weekday": "Tuesday",
                        "time_local": "8:00 AM MDT",
                        "date_local": "September 1, 2026",
                    }
                ],
            })

            result = build_overview(snapshot)
            report = json.loads(result.json_path.read_text(encoding="utf-8"))

            self.assertEqual(result.module_count, 2)
            self.assertEqual(result.graded_item_count, 2)
            self.assertEqual(result.unplaced_graded_item_count, 1)
            self.assertEqual(report["summary"]["unpublished_module_items"], 1)

            first = report["modules"][0]
            self.assertEqual(first["name"], "Pointers and Memory")
            self.assertEqual(first["assign_to"], "Everyone")
            self.assertEqual(first["completion_mode"], "Complete all required items")
            self.assertTrue(first["require_sequential_progress"])
            lab = first["items"][0]
            self.assertEqual(lab["assignment_group"], "Labs")
            self.assertEqual(lab["points"], 25)
            self.assertEqual(lab["rubric"], "Lab Rubric")
            self.assertEqual(lab["due"], "W2 · Friday · 2:50 PM MDT · September 4, 2026")
            self.assertEqual(lab["completion_requirement"], "Submit")

            second = report["modules"][1]
            self.assertEqual(second["assign_to"], "Lab Section A")
            self.assertEqual(second["prerequisites"], ["Pointers and Memory"])
            self.assertEqual(second["completion_mode"], "Complete one required item")

            unplaced = report["graded_items_not_in_modules"][0]
            self.assertEqual(unplaced["name"], "Hidden Midterm")
            self.assertEqual(unplaced["type"], "Quiz")
            self.assertEqual(unplaced["assignment_group"], "Exams")

            text = result.markdown_path.read_text(encoding="utf-8")
            self.assertIn("Pointers and Memory", text)
            self.assertIn("Assign to: **Everyone**", text)
            self.assertIn("Lab Rubric", text)
            self.assertIn("Graded items not represented in a module", text)
            self.assertIn("Hidden Midterm", text)


if __name__ == "__main__":
    unittest.main()
