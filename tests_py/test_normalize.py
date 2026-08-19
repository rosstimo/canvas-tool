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

    def test_settings_ignore_volatile_signed_image_url(self):
        left = normalize_snapshot({
            "course": {},
            "settings": {
                "image": "https://example.invalid/banner.png?token=first-short-lived-token",
                "lock_all_announcements": True,
            },
        })
        right = normalize_snapshot({
            "course": {},
            "settings": {
                "image": "https://example.invalid/banner.png?token=second-short-lived-token",
                "lock_all_announcements": True,
            },
        })
        self.assertEqual(left, right)
        self.assertNotIn("image", left["settings"])
