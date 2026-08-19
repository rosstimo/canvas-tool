import json
import tempfile
import unittest
from pathlib import Path

from canvas_tool.audit_suite import build_audit_suite


class AuditSuiteTests(unittest.TestCase):
    def write_json(self, directory: Path, name: str, value) -> None:
        (directory / name).write_text(json.dumps(value), encoding="utf-8")

    def test_comprehensive_suite_generates_linked_specialized_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = Path(tmp)
            self.write_json(snapshot, "manifest.json", {
                "course_id": "123",
                "course_name": "Audit Test Course",
                "course_code": "AUD-123",
                "student_data_included": False,
            })
            self.write_json(snapshot, "course.json", {
                "workflow_state": "available",
                "default_view": "modules",
                "time_zone": "America/Denver",
                "course_format": "on_campus",
                "apply_assignment_group_weights": False,
                "syllabus_body": '<p>Syllabus</p><img src="syllabus.png">',
            })
            self.write_json(snapshot, "settings.json", {"allow_student_discussion_topics": False})
            self.write_json(snapshot, "errors.json", [])

            self.write_json(snapshot, "modules.json", [{
                "id": 1,
                "position": 1,
                "name": "Start",
                "published": True,
                "prerequisite_module_ids": [],
                "require_sequential_progress": False,
            }])
            self.write_json(snapshot, "module-items.json", [{
                "source_id": "1",
                "title": "Start",
                "items": [],
            }])
            self.write_json(snapshot, "assignment-groups.json", [{
                "id": 50,
                "position": 1,
                "name": "Assignments",
                "group_weight": 100,
            }])
            self.write_json(snapshot, "assignments.json", [{
                "id": 100,
                "name": "New Quiz Example",
                "assignment_group_id": 50,
                "grading_type": "points",
                "points_possible": 10,
                "published": True,
                "due_at": "2026-09-01T05:00:00Z",
                "submission_types": ["external_tool"],
                "external_tool_tag_attributes": {
                    "url": "https://example.quiz-lti.instructure.com/lti/launch",
                    "content_id": "12",
                },
            }])

            self.write_json(snapshot, "classic-quizzes.json", [{
                "id": 10,
                "title": "Classic Example",
                "published": True,
                "quiz_type": "assignment",
                "points_possible": 5,
                "question_count": 1,
                "allowed_attempts": 1,
            }])
            self.write_json(snapshot, "classic-quiz-questions.json", [{
                "source_id": "10",
                "title": "Classic Example",
                "items": [{
                    "id": 11,
                    "question_name": "Question 1",
                    "question_type": "multiple_choice_question",
                    "assessment_question_bank_id": 500,
                }],
            }])
            self.write_json(snapshot, "classic-quiz-groups.json", [{
                "source_id": "10",
                "title": "Classic Example",
                "items": [{
                    "id": 12,
                    "name": "Random bank questions",
                    "pick_count": 1,
                    "question_points": 5,
                    "assessment_question_bank_id": 500,
                }],
            }])
            self.write_json(snapshot, "question-banks.json", [{
                "id": 500,
                "title": "Legacy Bank",
                "workflow_state": "active",
                "assessment_question_count": 1,
                "context_type": "Course",
            }])
            self.write_json(snapshot, "question-bank-questions.json", [{
                "source_id": "500",
                "title": "Legacy Bank",
                "items": [{"id": 501, "question_type": "multiple_choice_question"}],
            }])

            self.write_json(snapshot, "new-quizzes.json", [{
                "id": "100",
                "assignment_id": None,
                "title": "New Quiz Example",
                "published": True,
                "points_possible": 10,
                "grading_type": "points",
                "quiz_settings": {"shuffle_answers": True},
            }])
            self.write_json(snapshot, "new-quiz-items.json", [{
                "source_id": "100",
                "title": "New Quiz Example",
                "items": [{
                    "id": "item-1",
                    "entry_type": "BankEntry",
                    "points_possible": 10,
                    "entry": {
                        "bank_id": "new-bank-7",
                        "title": "New Quiz Item Bank",
                        "archived": True,
                        "entry_count": 20,
                        "item_entry_count": 20,
                        "interaction_type_slug": "choice",
                    },
                }],
            }])

            self.write_json(snapshot, "pages.json", [{
                "page_id": 201,
                "url": "welcome",
                "title": "Welcome",
                "body": '<p>Hello</p><img src="welcome.png">',
                "published": True,
                "front_page": True,
            }])
            self.write_json(snapshot, "files.json", [{
                "id": 301,
                "display_name": "empty.txt",
                "filename": "empty.txt",
                "size": 0,
                "content-type": "text/plain",
                "hidden": False,
                "locked": False,
            }])
            self.write_json(snapshot, "folders.json", [])
            self.write_json(snapshot, "discussions.json", [])
            self.write_json(snapshot, "announcements.json", [])
            self.write_json(snapshot, "calendar-events.json", [])

            self.write_json(snapshot, "rubrics.json", [{
                "id": 401,
                "title": "Empty Rubric",
                "points_possible": 10,
                "data": [],
                "associations": [],
            }])
            self.write_json(snapshot, "grading-standards.json", [])
            self.write_json(snapshot, "outcome-links.json", [])
            self.write_json(snapshot, "grading-periods.json", [{
                "id": 1,
                "title": "Semester",
                "weight": 100,
            }])
            self.write_json(snapshot, "late-policy.json", {})

            self.write_json(snapshot, "tabs.json", [{
                "id": "modules",
                "label": "Modules",
                "type": "internal",
                "position": 1,
                "hidden": False,
            }])
            self.write_json(snapshot, "features.json", [])
            self.write_json(snapshot, "external-tools.json", [{
                "id": 600,
                "name": "Example Tool",
                "domain": "tool.example.edu",
                "workflow_state": "public",
                "privacy_level": "public",
                "placements": {"course_navigation": {}},
            }])
            self.write_json(snapshot, "lti-resource-links.json", [{
                "id": 601,
                "title": "Old Link",
                "workflow_state": "deleted",
            }])

            self.write_json(snapshot, "sections.json", [{"id": 1, "name": "Section 1"}])
            self.write_json(snapshot, "group-categories.json", [])
            self.write_json(snapshot, "groups.json", [])
            self.write_json(snapshot, "blackout-dates.json", [])

            self.write_json(snapshot, "content-migrations.json", [{
                "id": 700,
                "migration_type": "course_copy_importer",
                "workflow_state": "completed",
                "settings": {"source_course_id": 99},
            }])
            self.write_json(snapshot, "migration-issues.json", [{
                "source_id": "700",
                "title": "course_copy_importer",
                "items": [{
                    "id": 701,
                    "workflow_state": "active",
                    "issue_type": "warning",
                    "description": "Imported content needs review.",
                    "created_at": "2026-01-01T00:00:00Z",
                }],
            }])
            self.write_json(snapshot, "content-exports.json", [{
                "id": 800,
                "export_type": "common_cartridge",
                "workflow_state": "failed",
            }])

            result = build_audit_suite(snapshot)

            expected = [
                "assignment-audit.md",
                "module-audit.md",
                "quiz-audit.md",
                "question-bank-audit.md",
                "content-audit.md",
                "grading-audit.md",
                "integration-audit.md",
                "migration-audit.md",
                "course-settings-audit.md",
                "comprehensive-audit.md",
                "README.md",
            ]
            for name in expected:
                self.assertTrue((snapshot / name).is_file(), name)

            self.assertEqual(len(result.report_paths), 9)
            self.assertGreaterEqual(result.warning_count, 1)
            self.assertGreaterEqual(result.review_count, 1)

            assignment_report = json.loads((snapshot / "assignment-audit.json").read_text(encoding="utf-8"))
            self.assertEqual(assignment_report["assignments"][0]["type"], "New Quiz")

            bank_text = (snapshot / "question-bank-audit.md").read_text(encoding="utf-8")
            self.assertIn("Legacy Bank", bank_text)
            self.assertIn("New Quiz Item Bank", bank_text)
            self.assertIn("does not claim to enumerate every New Quiz item bank", bank_text)

            migration_text = (snapshot / "migration-audit.md").read_text(encoding="utf-8")
            self.assertIn("Imported content needs review", migration_text)
            self.assertIn("failed", migration_text.casefold())

            comprehensive = (snapshot / "comprehensive-audit.md").read_text(encoding="utf-8")
            self.assertIn("[Quiz audit](quiz-audit.md)", comprehensive)
            self.assertIn("[Question bank audit](question-bank-audit.md)", comprehensive)
            self.assertIn("API coverage", comprehensive)

            index = (snapshot / "README.md").read_text(encoding="utf-8")
            self.assertIn("[Comprehensive course audit](comprehensive-audit.md)", index)
            self.assertIn("[Quiz audit](quiz-audit.md)", index)
            self.assertIn("[Question bank audit](question-bank-audit.md)", index)
            self.assertIn("[Course import, migration, and export audit](migration-audit.md)", index)


if __name__ == "__main__":
    unittest.main()
