import json
import tempfile
import unittest
from pathlib import Path

from canvas_tool.overview import _new_quiz_assignment_ids
from canvas_tool.report_index import refresh_report_index


class ReportIndexTests(unittest.TestCase):
    def test_index_links_every_markdown_report_and_reports_link_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "manifest.json").write_text(json.dumps({
                "course_id": "18637",
                "course_name": "Example Course",
                "course_code": "EX-1",
            }), encoding="utf-8")
            (directory / "course-overview.md").write_text("# Course overview\n\nOverview body.\n", encoding="utf-8")
            (directory / "date-audit.md").write_text("# Canvas date audit\n\nAudit body.\n", encoding="utf-8")
            (directory / "extra-report.md").write_text("# Extra report\n\nExtra body.\n", encoding="utf-8")

            index = refresh_report_index(directory)
            text = index.read_text(encoding="utf-8")

            self.assertIn("[Course overview](course-overview.md)", text)
            self.assertIn("[Canvas date audit](date-audit.md)", text)
            self.assertIn("[Extra report](extra-report.md)", text)
            self.assertIn("Course: **Example Course**", text)

            for name in ("course-overview.md", "date-audit.md", "extra-report.md"):
                report = (directory / name).read_text(encoding="utf-8")
                self.assertIn("[← Report index](README.md)", report)

            # Refreshing the index must not duplicate backlinks.
            refresh_report_index(directory)
            report = (directory / "course-overview.md").read_text(encoding="utf-8")
            self.assertEqual(report.count("[← Report index](README.md)"), 1)

    def test_new_quiz_can_use_its_own_id_when_assignment_id_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "assignments.json").write_text(json.dumps([
                {"id": 214949, "name": "test stuff"},
                {"id": 999999, "name": "other"},
            ]), encoding="utf-8")
            (directory / "new-quizzes.json").write_text(json.dumps([
                {"id": "214949", "title": "test stuff", "assignment_id": None},
                {"id": "123456", "title": "not an assignment", "assignment_id": None},
            ]), encoding="utf-8")

            self.assertEqual(_new_quiz_assignment_ids(directory), {"214949"})


if __name__ == "__main__":
    unittest.main()
