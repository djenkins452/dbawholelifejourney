# ==============================================================================
# File: apps/ai/tests/test_log_prayer_fix.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Regression test — handle_log_prayer must not pass prayer_status
# ==============================================================================
"""
Regression for the pre-existing log_prayer bug (surfaced during ChatGPT CoS
Phase 6 validation): handle_log_prayer passed a non-existent `prayer_status`
kwarg to PrayerRequest.objects.create(), raising TypeError at model init, so
logging a prayer via the AI/CoS path always failed.

PrayerRequest's status is the `is_answered` BooleanField (default False =
active/unanswered); there is no `prayer_status` field.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.action_handlers import ActionHandler
from apps.faith.models import PrayerRequest

User = get_user_model()


class LogPrayerRegressionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="pray@example.com", password="x")

    def test_handle_log_prayer_creates_request(self):
        handler = ActionHandler(self.user)
        result = handler.handle_log_prayer(title="Health and healing")
        self.assertTrue(result.success, msg=getattr(result, "error", None))
        prayer = PrayerRequest.objects.get(user=self.user, title="Health and healing")
        # default active/unanswered state
        self.assertFalse(prayer.is_answered)
        self.assertEqual(result.created_object["model"], "PrayerRequest")
        self.assertEqual(result.action_type, "log_prayer")

    def test_handle_log_prayer_with_optional_fields(self):
        handler = ActionHandler(self.user)
        result = handler.handle_log_prayer(
            title="Wisdom", description="for a decision",
            person_or_situation="work", priority="high", is_personal=True,
        )
        self.assertTrue(result.success)
        prayer = PrayerRequest.objects.get(user=self.user, title="Wisdom")
        self.assertEqual(prayer.priority, "high")
        self.assertTrue(prayer.is_personal)

    def test_no_prayer_status_attribute_on_model(self):
        # Guard: the field the bug referenced does not exist.
        self.assertFalse(hasattr(PrayerRequest, "prayer_status"))
