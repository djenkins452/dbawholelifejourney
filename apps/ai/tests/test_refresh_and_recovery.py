# ==============================================================================
# File: apps/ai/tests/test_refresh_and_recovery.py
# Description: REFRESH INTENT + PLAN-AWARE RECOVERY GUARD (Phase 2 trust). Two production
#   failures: (1) after a problem-solving flow, "I updated my stuff, look again" was
#   mis-routed to correction-repair (which recalled prayer/Bible + replayed an old brief)
#   because "look again" is a critique cue; (2) the stale overtraining line ("5 workouts
#   in 7 days — consider a rest day") surfaced from an old persisted insight despite the
#   plan-aware fix. Refresh must re-read today's tasks and stay problem-solving; the old
#   recovery wording must never surface when the plan has a built-in recovery day.
# ==============================================================================
from unittest import mock
import datetime

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase

from apps.ai.chatgpt_cos import conversation_planner as cp
from apps.ai.chatgpt_cos.naturalize import recovery_reframe

User = get_user_model()
_C = "apps.ai.services.ai_service._call_api"
_CT = "apps.ai.services.ai_service._call_api_with_tools"
_RHYTHM = "apps.core.cos_briefing.rhythm_api.get_remaining_rhythm_items"
_NOW = "apps.core.utils.get_user_now"
_PLAN = "apps.health.services.training_plan.read_training_plan"
_OLD_RECOVERY = ("Sleep averaging 5.7h/night with 5 workouts in 7 days. Recovery is "
                 "compromised — consider a rest day or lighter session.")
TASKS = [{"title": "Call the plumber", "source_type": "task", "scheduled_time": "11:00"},
         {"title": "Fish Oil", "source_type": "supplement_dose", "scheduled_time": "09:30"}]


def _mkuser(email):
    from apps.users.models import TermsAcceptance
    u = User.objects.create_user(email=email, password="x")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


class RefreshDetectorTests(SimpleTestCase):
    def test_recognizes_refresh_phrasing(self):
        for m in ("I updated my stuff, look again", "look again", "refresh",
                  "check again", "recheck", "I updated my tasks", "I changed it, recheck",
                  "take another look", "look at the current version"):
            self.assertTrue(cp.is_refresh_request(m), m)

    def test_not_a_refresh(self):
        for m in ("what is my weight", "how am I doing today", "good morning",
                  "I feel great"):
            self.assertFalse(cp.is_refresh_request(m), m)


class RecoveryReframeTests(SimpleTestCase):
    def test_reframes_when_plan_has_a_built_in_recovery_day(self):
        with mock.patch(_PLAN, return_value={"has_recovery_day": True}):
            out = recovery_reframe("One thing — " + _OLD_RECOVERY, None)
        self.assertNotIn("consider a rest day", out.lower())
        self.assertNotIn("workouts in 7 days", out.lower())
        self.assertIn("protect", out.lower())
        self.assertIn("training plan", out.lower())

    def test_left_alone_when_no_built_in_recovery_day(self):
        with mock.patch(_PLAN, return_value={"has_recovery_day": False}):
            out = recovery_reframe(_OLD_RECOVERY, None)
        self.assertEqual(out, _OLD_RECOVERY)              # rest-day advice is legitimate

    def test_ignores_unrelated_text(self):
        self.assertEqual(recovery_reframe("You're doing great today.", None),
                         "You're doing great today.")


class RefreshRoutingTests(TestCase):
    def setUp(self):
        from apps.ai.models import AssistantConversation
        self.u = _mkuser("refresh@example.com")
        self.conv = AssistantConversation.objects.create(user=self.u, is_active=True)

    def _route(self, msg):
        from apps.ai.chatgpt_cos.lanes import route_message
        from apps.ai.models import AssistantMessage
        AssistantMessage.objects.create(conversation=self.conv, role="user", content=msg)
        with mock.patch(_C, side_effect=RuntimeError("down")), \
             mock.patch(_CT, side_effect=RuntimeError("down")), \
             mock.patch(_RHYTHM, return_value=TASKS), \
             mock.patch(_NOW, return_value=datetime.datetime(2026, 7, 3, 9, 0,
                                                             tzinfo=datetime.timezone.utc)):
            res = route_message(self.u, msg, self.conv)
        if res:
            AssistantMessage.objects.create(conversation=self.conv, role="assistant",
                                            content=res.get("answer") or "")
        return res

    def test_look_again_after_problem_solving_refreshes_not_repairs(self):
        r1 = self._route("I am feeling overwhelmed right now trying to get a lot done.")
        self.assertEqual(r1["lane"], "problem_solving")
        # user updates and asks to look again
        r2 = self._route("I updated my stuff, look again")
        self.assertEqual(r2["lane"], "problem_solving")     # NOT conversation_repair
        ans = r2["answer"].lower()
        self.assertIn("current version", ans)               # re-read the current state
        # No unrelated context contamination, no old brief, no recovery line.
        for off_topic in ("prayer", "bible", "france", "protein",
                          "consider a rest day", "workouts in 7 days"):
            self.assertNotIn(off_topic, ans)

    def test_look_again_without_problem_solving_context_still_repairs(self):
        # A genuine critique-repair still works when NOT in a task-review flow.
        from apps.ai.models import AssistantMessage
        AssistantMessage.objects.create(
            conversation=self.conv, role="assistant", content="Here's your brief…")
        r = self._route("look again")
        self.assertEqual(r["lane"], "conversation_repair")
