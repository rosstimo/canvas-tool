import tempfile
import unittest
from pathlib import Path

from canvas_tool.duplicates import audit_snapshot, find_duplicates


class DuplicateAuditTests(unittest.TestCase):
    def test_classifies_same_name_same_and_different_content(self):
        normalized = {
            "modules": [
                {"name": "Faculty Module", "position": 1, "published": True, "items": [{"title": "Help", "type": "Page", "position": 1}]},
                {"name": "Faculty Module", "position": 9, "published": True, "items": [{"title": "Help", "type": "Page", "position": 1}]},
                {"name": "Start Here", "position": 2, "published": True, "items": [{"title": "Instructor Start", "type": "Page", "position": 1}]},
                {"name": "Start Here", "position": 3, "published": True, "items": [{"title": "Institution Start", "type": "Page", "position": 1}]},
            ]
        }
        result = find_duplicates(normalized)
        self.assertEqual([item["name"] for item in result["high_confidence"]], ["Faculty Module"])
        self.assertEqual([item["name"] for item in result["review"]], ["Start Here"])

    def test_flags_similar_names(self):
        normalized = {
            "pages": [
                {"title": "Faculty Resources", "body": "A"},
                {"title": "Faculty Resource", "body": "B"},
            ]
        }
        result = find_duplicates(normalized)
        self.assertEqual(len(result["similar_names"]), 1)
        self.assertGreaterEqual(result["similar_names"][0]["similarity"], 0.90)

    def test_audit_writes_read_only_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = Path(tmp)
            (snapshot / "manifest.json").write_text(
                '{"course_id":"18637","course_name":"Test Course","course_code":"TEST-F26"}\n',
                encoding="utf-8",
            )
            (snapshot / "normalized.json").write_text(
                '{"modules":[{"name":"Faculty Module","position":1,"items":[]},{"name":"Faculty Module","position":2,"items":[]}]}\n',
                encoding="utf-8",
            )
            result = audit_snapshot(snapshot)
            self.assertTrue(result.markdown_path.exists())
            self.assertTrue(result.json_path.exists())
            self.assertEqual(result.high_confidence, 1)
            self.assertIn("read-only", result.markdown_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
