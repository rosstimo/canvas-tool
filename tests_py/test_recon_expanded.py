import json
import tempfile
import unittest
from pathlib import Path

from canvas_tool.recon import Recon


class FakeCanvasClient:
    base_url = "https://canvas.example.edu"

    def __init__(self):
        self.requested = []

    def request_json(self, method, endpoint):
        self.requested.append((method, endpoint))
        if endpoint.startswith("/api/v1/courses/123?"):
            return {
                "id": 123,
                "name": "Expanded Recon Test",
                "course_code": "RECON-123",
                "time_zone": "America/Denver",
                "permissions": {"manage_content": True},
            }
        if endpoint.endswith("/settings"):
            return {"allow_student_discussion_topics": False}
        if endpoint.endswith("/late_policy"):
            return {"late_policy": {"missing_submission_deduction_enabled": False}}
        return {}

    def paginate(self, endpoint):
        self.requested.append(("GET", endpoint))
        if "/external_tools" in endpoint:
            return [{
                "id": 1,
                "name": "LTI Tool",
                "domain": "tool.example.edu",
                "consumer_key": "do-not-store",
                "custom_fields": {"private": "value"},
            }]
        return []


class ExpandedReconTests(unittest.TestCase):
    def test_expanded_recon_stays_course_configuration_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            client = FakeCanvasClient()
            result = Recon(client, root).run("123")

            expected_files = [
                "classic-quiz-groups.json",
                "question-banks.json",
                "question-bank-questions.json",
                "external-tools.json",
                "lti-resource-links.json",
                "group-categories.json",
                "groups.json",
                "grading-periods.json",
                "late-policy.json",
                "blackout-dates.json",
                "content-migrations.json",
                "migration-issues.json",
                "content-exports.json",
                "README.md",
            ]
            for name in expected_files:
                self.assertTrue((result.path / name).is_file(), name)

            external_tools = json.loads((result.path / "external-tools.json").read_text(encoding="utf-8"))
            self.assertEqual(external_tools[0]["name"], "LTI Tool")
            self.assertNotIn("consumer_key", external_tools[0])
            self.assertNotIn("custom_fields", external_tools[0])

            requested = "\n".join(endpoint for _method, endpoint in client.requested)
            self.assertIn("/api/v1/question_banks?context_type=Course&context_id=123&include_question_count=true", requested)
            self.assertIn("/api/v1/courses/123/external_tools?include_parents=true", requested)
            self.assertIn("/api/v1/courses/123/content_migrations", requested)

            forbidden = [
                "/enrollments",
                "/submissions",
                "/users",
                "/memberships",
                "quiz_submissions",
                "discussion_entries",
            ]
            for value in forbidden:
                self.assertNotIn(value, requested)

            manifest = json.loads((result.path / "manifest.json").read_text(encoding="utf-8"))
            self.assertFalse(manifest["student_data_included"])


if __name__ == "__main__":
    unittest.main()
