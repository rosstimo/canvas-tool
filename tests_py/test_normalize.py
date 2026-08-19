import unittest

from canvas_tool.normalize import normalize_snapshot, sanitize


class NormalizeTests(unittest.TestCase):
    def test_sanitize_removes_access_code(self):
        data = {"title": "Quiz", "access_code": "SECRET", "nested": {"verifier": "NOPE"}}
        result = sanitize(data)
        self.assertNotIn("access_code", result)
        self.assertNotIn("verifier", result["nested"])

    def test_large_page_body(self):
        body = "x" * 3_000_000
        normalized = normalize_snapshot({"course": {}, "pages": [{"title": "Large page", "body": body}]})
        self.assertEqual(len(normalized["pages"][0]["body"]), 3_000_000)
