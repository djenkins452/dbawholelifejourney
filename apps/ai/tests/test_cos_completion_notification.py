# ==============================================================================
# File: apps/ai/tests/test_cos_completion_notification.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Durable "Beth finished your response" completion notification.
# ==============================================================================
"""
A long-running Beth answer creates a durable Notification (reusing the core
Notification model/service) so the user never loses it: bell + deep-link, one
per job, none for quick (live-delivered) answers.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.ai import chat_stream_bus as bus
from apps.ai.chatgpt_cos.tasks import (
    _notify_beth_completion,
    run_chatgpt_cos_generation,
)
from apps.ai.models import AssistantConversation, AssistantMessage
from apps.core.models import Notification

User = get_user_model()


class CompletionNotificationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="cn@example.com", password="x")
        p = cls.user.preferences
        p.ai_enabled = True
        p.use_chatgpt_cos = True
        p.save()
        cls.conv = AssistantConversation.objects.create(user=cls.user)

    def _msg(self, content="Your health review is ready."):
        return AssistantMessage.objects.create(
            conversation=self.conv, role="assistant", content=content,
            message_type="text")

    def test_helper_creates_intelligence_notification_with_deeplink(self):
        am = self._msg()
        _notify_beth_completion(
            self.user.id, self.conv.id, am,
            "How am I doing overall with my health goals?")
        n = Notification.objects.filter(
            user=self.user, category="intelligence").first()
        self.assertIsNotNone(n)
        self.assertIn("Beth finished", n.title)
        self.assertEqual(n.action_url, f"/assistant/?beth_msg={am.id}")
        self.assertIn("health goals", n.message)
        self.assertFalse(n.is_read)

    @override_settings(WLJ_COS_EVIDENCE_TOOLS_ENABLED=True,
                       CELERY_TASK_ALWAYS_EAGER=True)
    def test_long_running_job_creates_exactly_one_notification(self):
        job = "cn-long"
        bus.write(job, bus.new_snapshot(self.user.id, self.conv.id))
        with mock.patch("apps.ai.chatgpt_cos.tasks.COS_COMPLETION_NOTIFY_MS", 0), \
             mock.patch("apps.ai.services.ai_service._call_api",
                        return_value="You're doing well overall."), \
             mock.patch("apps.ai.services.ai_service._call_api_with_tools",
                        return_value="You're doing well overall."):
            run_chatgpt_cos_generation.apply(args=[
                self.user.id, self.conv.id,
                "how am I doing overall with my health goals?", {}, job])
        self.assertEqual(
            Notification.objects.filter(
                user=self.user, category="intelligence").count(), 1)

    @override_settings(WLJ_COS_EVIDENCE_TOOLS_ENABLED=True,
                       CELERY_TASK_ALWAYS_EAGER=True)
    def test_quick_job_creates_no_notification(self):
        job = "cn-quick"
        bus.write(job, bus.new_snapshot(self.user.id, self.conv.id))
        with mock.patch("apps.ai.chatgpt_cos.tasks.COS_COMPLETION_NOTIFY_MS",
                        999999), \
             mock.patch("apps.ai.services.ai_service._call_api",
                        return_value="ok"), \
             mock.patch("apps.ai.services.ai_service._call_api_with_tools",
                        return_value="ok"):
            run_chatgpt_cos_generation.apply(args=[
                self.user.id, self.conv.id, "what is my weight?", {}, job])
        self.assertEqual(
            Notification.objects.filter(
                user=self.user, category="intelligence").count(), 0)

    def test_helper_never_raises_on_bad_user(self):
        # resilience: notification failure must never break the task
        _notify_beth_completion(999999999, self.conv.id, self._msg(), "x")
