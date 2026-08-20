import json
import tempfile
import unittest
from pathlib import Path

from canvas_tool.full_audit import _consolidate_findings, build_full_audit


class FullAuditTests(unittest.TestCase):
    def write_json(self, directory: Path, name: str, value) -> None:
        (directory / name).write_text(json.dumps(value), encoding="utf-8")

    def test_master_report_includes_new_and_existing_audits(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = Path(tmp)
            self.write_json(snapshot, "manifest.json", {
                "course_id": "123",
                "course_name": "Full Audit Test",
                "course_code": "FULL-123",
                "base_url": "https://isu.instructure.com",
                "student_data_included": False,
            })
            self.write_json(snapshot, "course.json", {"apply_assignment_group_weights": False})
            self.write_json(snapshot, "errors.json", [])
            self.write_json(snapshot, "assignment-overrides.json", [])
            self.write_json(snapshot, "date-audit.json", {
                "calendar": {},
                "issues": [{
                    "severity": "warning",
                    "assignment": "Before term",
                    "message": "Due before the first class day.",
                }],
            })
            self.write_json(snapshot, "duplicate-audit.json", {
                "high_confidence": [{
                    "resource_label": "Pages",
                    "name": "Welcome",
                    "count": 2,
                }],
                "review": [],
                "similar_names": [],
            })

            for name, title in [
                ("course-overview.md", "Course overview"),
                ("course-audit.md", "Course audit"),
                ("date-audit.md", "Canvas date audit"),
                ("duplicate-audit.md", "Duplicate content audit"),
                ("summary.md", "Canvas course recon"),
            ]:
                (snapshot / name).write_text(f"# {title}\n\n", encoding="utf-8")

            result = build_full_audit(snapshot)

            self.assertEqual(len(result.report_paths), 12)
            self.assertGreaterEqual(result.warning_count, 1)
            self.assertGreaterEqual(result.review_count, 1)

            text = result.comprehensive_path.read_text(encoding="utf-8")
            self.assertIn("[Course overview](course-overview.md)", text)
            self.assertIn("[Canvas date audit](date-audit.md)", text)
            self.assertIn("[Duplicate content audit](duplicate-audit.md)", text)
            self.assertIn("[Assignment Assign To and override audit](assignment-override-audit.md)", text)
            self.assertIn("[Quiz question audit](question-audit.md)", text)
            self.assertIn("[Link and internal-reference audit](link-audit.md)", text)
            self.assertIn("Due before the first class day", text)
            self.assertIn("same-name records with the same normalized content", text)

            index = (snapshot / "README.md").read_text(encoding="utf-8")
            self.assertIn("[Comprehensive course audit](comprehensive-audit.md)", index)
            self.assertIn("[Assignment Assign To and override audit](assignment-override-audit.md)", index)
            self.assertIn("[Quiz question audit](question-audit.md)", index)
            self.assertIn("[Link and internal-reference audit](link-audit.md)", index)

    def test_master_consolidates_repeated_findings_and_historical_migration_warnings(self):
        findings = [
            {
                "severity": "review",
                "area": "due date",
                "item": "Roll Call Attendance",
                "message": "No due date is set.",
                "source_report": "assignment-audit.md",
            },
            {
                "severity": "review",
                "area": "schedule / availability",
                "item": "Roll Call Attendance",
                "message": "No due date is set.",
                "source_report": "date-audit.md",
            },
            {
                "severity": "review",
                "area": "page titles",
                "item": "Welcome",
                "message": "This exact page title appears 2 times.",
                "source_report": "content-audit.md",
            },
            {
                "severity": "warning",
                "area": "content migration issue",
                "item": "migration 42",
                "message": "Missing links found in imported content.",
                "source_report": "migration-audit.md",
            },
            {
                "severity": "warning",
                "area": "content migration issue",
                "item": "migration 42",
                "message": "Missing links found in imported content.",
                "source_report": "migration-audit.md",
            },
        ]
        duplicate_report = {
            "high_confidence": [{"name": "Welcome"}],
            "review": [],
        }

        result = _consolidate_findings(findings, duplicate_report)

        self.assertEqual(len(result), 2)
        roll_call = next(item for item in result if item["item"] == "Roll Call Attendance")
        self.assertEqual(roll_call["occurrences"], 2)
        self.assertEqual(set(roll_call["source_reports"]), {"assignment-audit.md", "date-audit.md"})

        migration = next(item for item in result if item["item"] == "migration 42")
        self.assertEqual(migration["severity"], "review")
        self.assertEqual(migration["occurrences"], 2)


if __name__ == "__main__":
    unittest.main()
