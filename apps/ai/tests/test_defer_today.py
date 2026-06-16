"""Explicit user-deferral handling — trust tests (2026-06-15).

Failure: at 9:52 PM user said "I won't be studying for SHRM today, getting too
late." Beth acknowledged, then one message later recommended SHRM. Beth treated
the deferral as conversational text — no execution state changed.

Contracts:
  - "I won't do X today" deterministically modifies today's plan (task →
    reschedule to tomorrow; routine → skip today), not just empathetic text.
  - Temporary + truthful: deferred ≠ completed, ≠ skipped-forever; returns
    tomorrow; adherence not inflated.
  - Bounded: only acts on an unambiguous match against real today items;
    "I hate studying" / questions never trigger a mutation.
  - Gap A: skipped tasks drop out of today's context (mirror routines).
"""
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.ai import deterministic_router as dr

User = get_user_model()
_MOD = "apps.core.today.today_engine.get_today_context"


class DeferMatcher(SimpleTestCase):
    def test_matches_real_deferrals(self):
        for q in (
            "i won't be studying for shrm today, getting too late",
            "i'll do that tomorrow instead",
            "skip my workout tonight",
            "not happening today",
            "too late for the run tonight",
        ):
            self.assertTrue(dr._is_defer_today_intent(q), q)

    def test_does_not_over_trigger(self):
        for q in (
            "i hate studying",                 # emotion, no defer cue
            "should i skip my workout?",       # question
            "what's left today",               # status query
            "i won't",                          # cue but no scope
            "i crushed my workout today",       # positive, no defer cue
        ):
            self.assertFalse(dr._is_defer_today_intent(q), q)


class DeferResolver(SimpleTestCase):
    def _ctx(self, *items):
        return {"all_items": list(items), "overdue": [], "coming_up": [],
                "later": [], "foundation": [], "completed": []}

    def test_resolves_single_match_by_token(self):
        ctx = self._ctx(
            {"name": "Study for SHRM", "source": "task", "id": "task:5",
             "completed": False},
            {"name": "Evening Walk", "source": "routine", "id": "routine:9",
             "completed": False},
        )
        with patch(_MOD, return_value=ctx):
            item = dr._resolve_defer_target(object(), "i won't be studying for shrm today")
        self.assertIsNotNone(item)
        self.assertEqual(item["id"], "task:5")

    def test_ambiguous_returns_none(self):
        ctx = self._ctx(
            {"name": "Morning Study", "source": "task", "id": "task:1", "completed": False},
            {"name": "Study Group", "source": "task", "id": "task:2", "completed": False},
        )
        with patch(_MOD, return_value=ctx):
            self.assertIsNone(dr._resolve_defer_target(object(), "skip study today"))

    def test_no_match_returns_none(self):
        ctx = self._ctx(
            {"name": "Workout", "source": "routine", "id": "routine:1", "completed": False},
        )
        with patch(_MOD, return_value=ctx):
            self.assertIsNone(
                dr._resolve_defer_target(object(), "i won't be studying for shrm today"))

    def test_completed_items_not_targetable(self):
        ctx = self._ctx(
            {"name": "Study for SHRM", "source": "task", "id": "task:5", "completed": True},
        )
        with patch(_MOD, return_value=ctx):
            self.assertIsNone(
                dr._resolve_defer_target(object(), "i won't be studying for shrm today"))


class DeferTaskEndToEnd(TestCase):
    def setUp(self):
        from apps.users.models import TermsAcceptance
        self.user = User.objects.create_user(email="defer@test.com", password="x" * 20)
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()
        from apps.core.utils import get_user_today
        self.today = get_user_today(self.user)
        from apps.life.models import Task
        self.task = Task.objects.create(
            user=self.user, title="Study for SHRM", due_date=self.today,
            is_routine=False)

    def _names_today(self):
        from apps.core.today.today_engine import get_today_context
        ctx = get_today_context(self.user)
        return {(i.get("name") or "").lower() for i in ctx.get("all_items", [])}

    def test_defer_reschedules_to_tomorrow_truthfully(self):
        # Pre: SHRM is in today's context.
        self.assertIn("study for shrm", self._names_today())

        resp = dr._handle_defer_today(self.user, "i won't be studying for shrm today")
        self.assertIsNotNone(resp)
        self.assertIn("tomorrow", resp.lower())
        self.assertIn("deferred", resp.lower())

        self.task.refresh_from_db()
        # Rescheduled, NOT completed/skipped (truthful).
        self.assertEqual(self.task.due_date, self.today + timedelta(days=1))
        self.assertEqual(self.task.completion_status, "pending")

        # Contradiction fixed: gone from TODAY's context, returns tomorrow.
        self.assertNotIn("study for shrm", self._names_today())

    def test_skipped_task_drops_from_today_context(self):
        # Gap A: a skipped task must not surface in today's context.
        self.task.completion_status = "skipped"
        self.task.save(update_fields=["completion_status"])
        self.assertNotIn("study for shrm", self._names_today())
