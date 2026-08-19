import json
import tempfile
import unittest
from pathlib import Path

from canvas_tool.full_audit import build_full_audit


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

            self.assertEqual(len(result.report_paths), 11)
            self.assertGreaterEqual(result.warning_count, 1)
            self.assertGreaterEqual(result.review_count, 1)

            text = result.comprehensive_path.read_text(encoding="utf-8")
            self.assertIn("[Course overview](course-overview.md)", text)
            self.assertIn("[Canvas date audit](date-audit.md)", text)
            self.assertIn("[Duplicate content audit](duplicate-audit.md)", text)
            self.assertIn("[Assignment Assign To and override audit](assignment-override-audit.md)", text)
            self.assertIn("[Link and internal-reference audit](link-audit.md)", text)
            self.assertIn("Due before the first class day", text)
            self.assertIn("same-name records with the same normalized content", text)

            index = (snapshot / "README.md").read_text(encoding="utf-8")
            self.assertIn("[Comprehensive course audit](comprehensive-audit.md)", index)
            self.assertIn("[Assignment Assign To and override audit](assignment-override-audit.md)", index)
            self.assertIn("[Link and internal-reference audit](link-audit.md)", index)


if __name__ == "__main__":
    unittest.main()
