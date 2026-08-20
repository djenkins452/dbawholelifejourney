# ==============================================================================
# File: apps/ai/tests/test_daily_executive_brief.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Proactive Daily Executive Brief (Product Milestone 1) — authored by the
#   CERTIFIED CoS (ModelInterfaceService), delivered via existing proactive machinery.
#   Verifies certified-runtime authorship, per-user-local-day idempotency, eligibility,
#   fail-safe (no fabricated brief, no legacy fallback), and is_proactive persistence.
# ==============================================================================
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase, override_settings

from apps.ai.models import AssistantConversation, AssistantMessage
from apps.ai.proactive_checkins import generate_daily_executive_brief_for_user
from apps.users.models import TermsAcceptance

try:
    from apps.users.models import User
except ImportError:
    from django.contrib.auth import get_user_model
    User = get_user_model()


def _user(email, *, proactive=True):
    u = User.objects.create_user(email=email, password="pw12345!")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    p = u.preferences
    p.has_completed_onboarding = True
    p.personal_assistant_enabled = True
    p.assistant_proactive_checkins = proactive
    p.save()
    return u


# Provider-backed proactive AI is PAUSED by default pre-production. These tests certify
# the brief's behaviour WHEN IT RUNS, so they enable the gate explicitly — the architecture
# is preserved, only its scheduled execution is paused.
@override_settings(WLJ_PROACTIVE_AI_ENABLED=True)
class DailyExecutiveBriefTests(TestCase):
    def setUp(self):
        self.user = _user("brief@test.com")

    def _gen(self, answer="Your one focus today: protein — you're at 57% of target.",
             synthesis=True):
        # Author via the CERTIFIED runtime — mock ONLY the model call, exercise the real
        # idempotency + delivery + persistence path.
        with patch("apps.ai.model_interface.service.ModelInterfaceService.generate",
                   return_value={"answer": answer, "synthesis_used": synthesis}) as m:
            msg = generate_daily_executive_brief_for_user(self.user)
        return msg, m

    def test_authored_by_certified_runtime_and_persisted_proactive(self):
        msg, m = self._gen()
        self.assertTrue(m.called)                                  # certified CoS authored it
        self.assertIsNotNone(msg)
        self.assertEqual(msg.role, "assistant")
        self.assertTrue(msg.is_proactive)
        self.assertEqual(msg.message_type, "daily_brief")
        self.assertIn("protein", msg.content)
        self.assertEqual(msg.metadata.get("authored_by"), "model_interface")
        self.assertIn("brief_date", msg.metadata)

    def test_directive_not_persisted_as_user_turn(self):
        self._gen()
        # Only the assistant brief exists — the internal directive is NOT a visible user turn.
        self.assertEqual(AssistantMessage.objects.filter(role="user").count(), 0)
        self.assertEqual(AssistantMessage.objects.filter(role="assistant").count(), 1)

    def test_idempotent_one_per_local_day(self):
        msg1, _ = self._gen()
        msg2, m2 = self._gen()               # same local day → no second brief
        self.assertIsNotNone(msg1)
        self.assertIsNone(msg2)
        self.assertFalse(m2.called)          # certified CoS not even invoked the 2nd time
        conv = AssistantConversation.get_or_create_active(self.user)
        self.assertEqual(
            AssistantMessage.objects.filter(conversation=conv,
                                            message_type="daily_brief").count(), 1)

    def test_next_local_day_regenerates(self):
        self._gen()
        from datetime import timedelta
        from apps.core.utils import get_user_today
        tomorrow = get_user_today(self.user) + timedelta(days=1)
        with patch("apps.core.utils.get_user_today", return_value=tomorrow), \
             patch("apps.ai.model_interface.service.ModelInterfaceService.generate",
                   return_value={"answer": "New day, new focus.", "synthesis_used": True}):
            msg = generate_daily_executive_brief_for_user(self.user)
        self.assertIsNotNone(msg)
        conv = AssistantConversation.get_or_create_active(self.user)
        self.assertEqual(
            AssistantMessage.objects.filter(conversation=conv,
                                            message_type="daily_brief").count(), 2)

    def test_proactive_disabled_user_gets_no_brief(self):
        off = _user("off@test.com", proactive=False)
        with patch("apps.ai.model_interface.service.ModelInterfaceService.generate") as m:
            msg = generate_daily_executive_brief_for_user(off)
        self.assertIsNone(msg)
        self.assertFalse(m.called)           # not even authored

    def test_empty_answer_writes_no_brief(self):
        msg, _ = self._gen(answer="   ")
        self.assertIsNone(msg)
        self.assertEqual(AssistantMessage.objects.filter(message_type="daily_brief").count(), 0)

    def test_model_failure_no_brief_no_fallback_never_raises(self):
        with patch("apps.ai.model_interface.service.ModelInterfaceService.generate",
                   side_effect=RuntimeError("model down")):
            msg = generate_daily_executive_brief_for_user(self.user)   # must not raise
        self.assertIsNone(msg)
        self.assertEqual(AssistantMessage.objects.filter(message_type="daily_brief").count(), 0)
