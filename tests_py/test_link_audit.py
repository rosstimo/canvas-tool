import json
import tempfile
import unittest
from pathlib import Path

from canvas_tool.link_audit import audit_links


class LinkAuditTests(unittest.TestCase):
    def write_json(self, directory: Path, name: str, value) -> None:
        (directory / name).write_text(json.dumps(value), encoding="utf-8")

    def test_internal_missing_cross_course_and_external_http_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = Path(tmp)
            self.write_json(snapshot, "manifest.json", {
                "course_id": "123",
                "course_name": "Link Test",
                "course_code": "LINK-123",
                "base_url": "https://isu.instructure.com",
            })
            self.write_json(snapshot, "course.json", {"syllabus_body": ""})
            self.write_json(snapshot, "assignments.json", [{"id": 10, "name": "A"}])
            self.write_json(snapshot, "modules.json", [{"id": 30, "name": "M"}])
            self.write_json(snapshot, "files.json", [{"id": 20, "display_name": "f.pdf"}])
            self.write_json(snapshot, "discussions.json", [])
            self.write_json(snapshot, "classic-quizzes.json", [])
            self.write_json(snapshot, "new-quizzes.json", [])
            self.write_json(snapshot, "module-items.json", [])
            self.write_json(snapshot, "announcements.json", [])
            self.write_json(snapshot, "pages.json", [{
                "page_id": 40,
                "url": "welcome",
                "title": "Welcome",
                "body": (
                    '<a href="/courses/123/assignments/10">valid</a>'
                    '<a href="https://isu.instructure.com/courses/123/files/999">missing file</a>'
                    '<a href="https://isu.instructure.com/courses/555/pages/old">old course</a>'
                    '<a href="http://example.com/resource">plain http</a>'
                ),
            }])

            result = audit_links(snapshot)
            report = json.loads(result.json_path.read_text(encoding="utf-8"))

            self.assertEqual(report["summary"]["valid_internal_targets"], 1)
            self.assertEqual(report["summary"]["missing_internal_targets"], 1)
            self.assertEqual(report["summary"]["cross_course_links"], 1)
            self.assertEqual(result.warning_count, 1)
            self.assertEqual(result.review_count, 2)

            text = result.markdown_path.read_text(encoding="utf-8")
            self.assertIn("Missing file 999", text)
            self.assertIn("Canvas course 555", text)
            self.assertIn("plain HTTP rather than HTTPS", text)
            self.assertIn("example.com", text)


if __name__ == "__main__":
    unittest.main()
