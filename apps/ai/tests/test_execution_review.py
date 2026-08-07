# Blocker #14 (Layer 1): the Execution Review is a deterministic PROJECTION exposed as ONE
# CoS read surface — "what represented the user's intended execution for a day?" — so the
# CoS never reduces "yesterday's items" to only Tasks. It owns zero truth; it composes it.
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.cos_services.execution_review import get_execution_review
from apps.ai.model_interface.constitution import all_tools
from apps.core.execution.execution_review import build_execution_review

User = get_user_model()


class ExecutionReviewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="execrev2@test.com", password="x")

    def _today(self):
        from apps.core.utils import get_user_today
        return get_user_today(self.user)

    def test_tool_is_registered_as_a_read_surface(self):
        names = [t["function"]["name"] for t in all_tools(writes_enabled=False)]
        self.assertIn("get_execution_review", names)

    def test_defaults_to_yesterday_and_returns_review_shape(self):
        r = get_execution_review(self.user)  # no day -> yesterday (reconciliation case)
        self.assertIn(r["status"], ("ready", "empty"))
        self.assertEqual(r["relative"], "yesterday")
        self.assertIn("items", r)
        self.assertEqual(set(r["summary"]),
                         {"intended", "completed", "remaining", "fully_reconciled"})

    def test_natural_day_phrase_resolves(self):
        r = get_execution_review(self.user, day="today")
        self.assertEqual(r["relative"], "today")

    def test_projection_composes_every_execution_type_not_just_tasks(self):
        # The core of Blocker #14: the review composes ALL intended execution — faith,
        # medication, workout, journal, routines — not only tasks. Feed synthetic execution
        # truth (the projection owns none) and assert every type surfaces with its status.
        from unittest import mock
        y = self._today() - timedelta(days=1)
        fake_truth = {
            "date": y.isoformat(),
            "domains": {
                "faith": {"prayer_expected": True, "prayer_completed": False,
                          "bible_expected": True, "bible_reading_completed": True,
                          "prayer_source": "routine", "bible_source": "reading_plan"},
                "workout": {"expected": True, "completed": False},
                "journal": {"expected": True, "completed": True},
            },
            "routines": {"items": {"Morning Routine": {"total": 3, "completed": 1,
                                                        "fully_complete": False},
                                   "Prayer Time": {"total": 1, "completed": 1,
                                                   "fully_complete": True}}},
            "tasks": {"total": 0, "completed": 0},
            "medications": {"taken": 2, "expected": 4, "all_taken": False},
        }
        with mock.patch("apps.core.execution.execution_truth_engine.get_execution_truth",
                        return_value=fake_truth):
            r = build_execution_review(self.user, y)
        kinds = {it["kind"] for it in r["items"]}
        # every non-task execution type is present — the reduction to tasks is impossible
        self.assertIn("prayer", kinds)
        self.assertIn("bible_reading", kinds)
        self.assertIn("workout", kinds)
        self.assertIn("journal", kinds)
        self.assertIn("medications", kinds)
        self.assertIn("routine", kinds)
        titles = [it["title"] for it in r["items"]]
        self.assertIn("Prayer Time", titles)          # from faith
        self.assertNotIn("Prayer Time", [it["title"] for it in r["items"]
                                         if it["kind"] == "routine"])  # deduped from routines
        self.assertIn("Morning Routine", titles)
        # completion state carried through
        bible = next(it for it in r["items"] if it["kind"] == "bible_reading")
        self.assertTrue(bible["completed"])
        prayer = next(it for it in r["items"] if it["kind"] == "prayer")
        self.assertFalse(prayer["completed"])
