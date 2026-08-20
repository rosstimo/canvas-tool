import json
import tempfile
import unittest
from pathlib import Path

from canvas_tool.question_audit import audit_questions


class QuestionAuditTests(unittest.TestCase):
    def write_json(self, directory: Path, name: str, value) -> None:
        (directory / name).write_text(json.dumps(value), encoding="utf-8")

    def test_question_level_review_across_classic_banks_and_new_quizzes(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = Path(tmp)
            self.write_json(snapshot, "manifest.json", {
                "course_id": "123",
                "course_name": "Question Audit Test",
                "course_code": "Q-123",
            })
            self.write_json(snapshot, "classic-quiz-questions.json", [{
                "source_id": "10",
                "title": "Classic Quiz",
                "items": [{
                    "id": 1,
                    "position": 1,
                    "question_name": "Choice",
                    "question_type": "multiple_choice_question",
                    "question_text": "<p>What is two plus two?</p>",
                    "points_possible": 1,
                    "answers": [
                        {"text": "4", "weight": 100},
                        {"text": "4", "weight": 0},
                    ],
                }],
            }])
            self.write_json(snapshot, "question-bank-questions.json", [{
                "source_id": "500",
                "title": "Legacy Bank",
                "items": [{
                    "id": 2,
                    "question_name": "Same body",
                    "question_type": "multiple_choice_question",
                    "question_text": "What is two plus two?",
                    "points_possible": 1,
                    "answers": [
                        {"text": "4", "weight": 100},
                        {"text": "5", "weight": 0},
                    ],
                }],
            }])
            self.write_json(snapshot, "new-quiz-items.json", [{
                "source_id": "100",
                "title": "New Quiz",
                "items": [{
                    "id": "q1",
                    "position": 1,
                    "entry_type": "Item",
                    "points_possible": 2,
                    "stimulus_quiz_entry_id": "missing-stimulus",
                    "entry": {
                        "title": "New question",
                        "item_body": "<p>Which option?</p>",
                        "interaction_type_slug": "choice",
                    },
                }],
            }])

            result = audit_questions(snapshot)
            report = json.loads(result.json_path.read_text(encoding="utf-8"))

            self.assertEqual(report["summary"]["classic_quiz_questions"], 1)
            self.assertEqual(report["summary"]["classic_question_bank_questions"], 1)
            self.assertEqual(report["summary"]["new_direct_questions"], 1)
            self.assertEqual(report["summary"]["duplicate_question_text_groups"], 1)
            self.assertEqual(report["new_quiz_interaction_types"]["choice"], 1)
            self.assertGreaterEqual(result.warning_count, 1)
            self.assertGreaterEqual(result.review_count, 2)

            text = result.markdown_path.read_text(encoding="utf-8")
            self.assertIn("duplicate answer text", text)
            self.assertIn("same normalized question body", text)
            self.assertIn("missing-stimulus", text)
            self.assertIn("Legacy Bank", text)

    def test_blank_stimulus_id_is_not_treated_as_missing_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = Path(tmp)
            self.write_json(snapshot, "manifest.json", {
                "course_id": "123",
                "course_name": "Blank Stimulus Test",
                "course_code": "Q-123",
            })
            self.write_json(snapshot, "classic-quiz-questions.json", [])
            self.write_json(snapshot, "question-bank-questions.json", [])
            self.write_json(snapshot, "new-quiz-items.json", [{
                "source_id": "100",
                "title": "New Quiz",
                "items": [{
                    "id": "q1",
                    "position": 1,
                    "entry_type": "Item",
                    "points_possible": 1,
                    "stimulus_quiz_entry_id": "",
                    "entry": {
                        "title": "Standalone question",
                        "item_body": "<p>Question body</p>",
                        "interaction_type_slug": "choice",
                    },
                }],
            }])

            result = audit_questions(snapshot)
            report = json.loads(result.json_path.read_text(encoding="utf-8"))

            self.assertEqual(result.warning_count, 0)
            self.assertFalse(any(item.get("area") == "New Quiz stimulus" for item in report["findings"]))
            self.assertIsNone(report["new_quiz_items"][0]["stimulus_quiz_entry_id"])


if __name__ == "__main__":
    unittest.main()
