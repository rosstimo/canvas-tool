import unittest

from canvas_tool.privacy import sanitize


class PrivacyTests(unittest.TestCase):
    def test_extra_identity_and_lti_fields_are_removed_recursively(self):
        value = {
            "name": "Tool",
            "consumer_key": "key-that-should-not-be-stored",
            "custom_fields": {"secretish": "value"},
            "user_id": 999,
            "email": "person@example.edu",
            "nested": {
                "student_ids": [111, 222],
                "users": [{"id": 111, "name": "Student"}],
                "safe": "keep me",
            },
        }

        result = sanitize(value)

        self.assertEqual(result["name"], "Tool")
        self.assertEqual(result["nested"]["safe"], "keep me")
        self.assertNotIn("consumer_key", result)
        self.assertNotIn("custom_fields", result)
        self.assertNotIn("user_id", result)
        self.assertNotIn("email", result)
        self.assertNotIn("student_ids", result["nested"])
        self.assertNotIn("users", result["nested"])


if __name__ == "__main__":
    unittest.main()
