# ==============================================================================
# File: apps/ai/tests/test_conversation_follow_up.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Durable Conversational Follow-Through (Proactive Phase 2, M2) tests.
#   Deterministic (no real model): schedule validation + lifecycle, fire-time authoring via
#   the certified runtime (mocked), duplicate-safety, fail-safe (no fabricated follow-up),
#   proactive-pref gating, supersede, and the handle_remind_later promise now being real.
# ==============================================================================
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.ai.cos_services.follow_up import (deliver_due_follow_ups_for_user,
                                            schedule_follow_up)
from apps.ai.models import AssistantConversation, AssistantMessage, ConversationFollowUp
from apps.core.utils import get_user_now
from apps.users.models import TermsAcceptance

try:
    from apps.users.models import User
except ImportError:
    from django.contrib.auth import get_user_model
    User = get_user_model()


def _user(email="fu@test.com", *, proactive=True):
    u = User.objects.create_user(email=email, password="pw12345!")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    p = u.preferences
    p.has_completed_onboarding = True
    p.personal_assistant_enabled = True
    p.assistant_proactive_checkins = proactive
    p.timezone = "UTC"
    p.save()
    return u


class ScheduleFollowUpTests(TestCase):
    def setUp(self):
        self.user = _user()
        self.conv = AssistantConversation.get_or_create_active(self.user)

    def test_creates_pending_future_commitment(self):
        when = (get_user_now(self.user) + timedelta(hours=3)).replace(microsecond=0)
        out = schedule_follow_up(self.user, self.conv, topic="whether he did his workout",
                                 when_local=when.isoformat(), when_label="tonight")
        self.assertEqual(out["status"], "scheduled")
        fu = ConversationFollowUp.objects.get()
        self.assertEqual(fu.status, ConversationFollowUp.STATUS_PENDING)
        self.assertEqual(fu.topic, "whether he did his workout")
        self.assertEqual(fu.conversation_id, self.conv.id)
        self.assertGreater(fu.due_at, timezone.now())

    def test_rejects_past_time(self):
        when = get_user_now(self.user) - timedelta(hours=1)
        out = schedule_follow_up(self.user, self.conv, topic="x", when_local=when.isoformat())
        self.assertEqual(out["status"], "needs_info")
        self.assertEqual(ConversationFollowUp.objects.count(), 0)

    def test_rejects_beyond_horizon(self):
        when = get_user_now(self.user) + timedelta(days=30)
        out = schedule_follow_up(self.user, self.conv, topic="x", when_local=when.isoformat())
        self.assertEqual(out["status"], "needs_info")
        self.assertEqual(ConversationFollowUp.objects.count(), 0)

    def test_supersedes_prior_pending_on_same_subject(self):
        when = (get_user_now(self.user) + timedelta(hours=2)).isoformat()
        schedule_follow_up(self.user, self.conv, topic="a", when_local=when,
                           subject_ref="life.task:5")
        schedule_follow_up(self.user, self.conv, topic="a again", when_local=when,
                           subject_ref="life.task:5")
        statuses = sorted(ConversationFollowUp.objects.values_list("status", flat=True))
        self.assertEqual(statuses, ["pending", "resolved"])


class DeliverFollowUpTests(TestCase):
    def setUp(self):
        self.user = _user("deliver@test.com")
        self.conv = AssistantConversation.get_or_create_active(self.user)

    def _due_followup(self, topic="whether he did his workout"):
        return ConversationFollowUp.objects.create(
            user=self.user, conversation=self.conv,
            due_at=timezone.now() - timedelta(minutes=1), topic=topic)

    def test_due_followup_authored_by_certified_runtime_and_delivered(self):
        fu = self._due_followup()
        with patch("apps.ai.model_interface.service.ModelInterfaceService.generate",
                   return_value={"answer": "Earlier you planned your workout — did you get it in?"}) as m:
            n = deliver_due_follow_ups_for_user(self.user)
        self.assertEqual(n, 1)
        self.assertTrue(m.called)                      # certified CoS authored it
        fu.refresh_from_db()
        self.assertEqual(fu.status, ConversationFollowUp.STATUS_DELIVERED)
        self.assertIsNotNone(fu.delivered_at)
        msg = AssistantMessage.objects.get(message_type="follow_up")
        self.assertTrue(msg.is_proactive)
        self.assertEqual(msg.metadata.get("follow_up_id"), fu.pk)

    def test_not_yet_due_is_not_delivered(self):
        ConversationFollowUp.objects.create(
            user=self.user, conversation=self.conv,
            due_at=timezone.now() + timedelta(hours=1), topic="later")
        with patch("apps.ai.model_interface.service.ModelInterfaceService.generate") as m:
            n = deliver_due_follow_ups_for_user(self.user)
        self.assertEqual(n, 0)
        self.assertFalse(m.called)

    def test_already_delivering_is_not_double_delivered(self):
        # Simulate a concurrent worker having claimed it.
        ConversationFollowUp.objects.create(
            user=self.user, conversation=self.conv,
            due_at=timezone.now() - timedelta(minutes=1), topic="claimed",
            status=ConversationFollowUp.STATUS_DELIVERING)
        with patch("apps.ai.model_interface.service.ModelInterfaceService.generate") as m:
            n = deliver_due_follow_ups_for_user(self.user)
        self.assertEqual(n, 0)
        self.assertFalse(m.called)

    def test_empty_answer_not_delivered_retries_then_fails(self):
        fu = self._due_followup()
        with patch("apps.ai.model_interface.service.ModelInterfaceService.generate",
                   return_value={"answer": "   "}):
            for _ in range(ConversationFollowUp.MAX_ATTEMPTS):
                deliver_due_follow_ups_for_user(self.user)
        fu.refresh_from_db()
        self.assertEqual(fu.status, ConversationFollowUp.STATUS_FAILED)
        self.assertEqual(AssistantMessage.objects.filter(message_type="follow_up").count(), 0)

    def test_proactive_disabled_no_delivery(self):
        off = _user("off@test.com", proactive=False)
        conv = AssistantConversation.get_or_create_active(off)
        ConversationFollowUp.objects.create(
            user=off, conversation=conv, due_at=timezone.now() - timedelta(minutes=1),
            topic="x")
        with patch("apps.ai.model_interface.service.ModelInterfaceService.generate") as m:
            n = deliver_due_follow_ups_for_user(off)
        self.assertEqual(n, 0)
        self.assertFalse(m.called)


class RemindLaterPromiseIsRealTests(TestCase):
    def test_remind_later_creates_durable_follow_up(self):
        from apps.ai.quick_reply_handlers import handle_remind_later
        user = _user("remind@test.com")
        res = handle_remind_later(user, {"reminder_type": "workout"})
        self.assertTrue(res["success"])
        self.assertIn("follow_up_id", res.get("data", {}))
        self.assertEqual(ConversationFollowUp.objects.filter(user=user).count(), 1)


class ToolRegistrationTests(TestCase):
    def test_schedule_follow_up_tool_is_exposed(self):
        from apps.ai.model_interface.constitution import action_tools
        names = {t["function"]["name"] for t in action_tools()}
        self.assertIn("schedule_follow_up", names)
