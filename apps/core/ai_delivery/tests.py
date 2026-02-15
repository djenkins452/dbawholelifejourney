"""
DNE — Delivery & Notification Engine Tests.
"""

import datetime
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.test import TestCase, RequestFactory
from django.utils import timezone

from apps.users.models import TermsAcceptance, User


class DNETestBase(TestCase):
    """Base test class with user setup."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="dne_test@example.com",
            password="testpass123",
            first_name="DNE",
            last_name="Test",
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.ai_enabled = True
        self.user.preferences.save()


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class DeliveredNotificationModelTests(DNETestBase):

    def test_create_delivered_notification(self):
        from apps.core.ai_delivery.models import DeliveredNotification

        record = DeliveredNotification.objects.create(
            user=self.user,
            source_engine="PGE",
            source_object_type="GuidanceItem",
            source_object_id=1,
            channel="in_app",
            title="Test Notification",
            message="Test message",
            status="sent",
            dedupe_hash=DeliveredNotification.compute_dedupe_hash(
                self.user.id, "in_app", "PGE", "GuidanceItem", 1,
            ),
        )
        self.assertEqual(record.source_engine, "PGE")
        self.assertEqual(record.channel, "in_app")
        self.assertEqual(record.status, "sent")

    def test_dedupe_hash_unique(self):
        from apps.core.ai_delivery.models import DeliveredNotification
        from django.db import IntegrityError

        hash_val = DeliveredNotification.compute_dedupe_hash(
            self.user.id, "in_app", "PGE", "GuidanceItem", 1,
        )
        DeliveredNotification.objects.create(
            user=self.user, source_engine="PGE", source_object_type="GuidanceItem",
            source_object_id=1, channel="in_app", title="T1", message="M1",
            status="sent", dedupe_hash=hash_val,
        )
        with self.assertRaises(IntegrityError):
            DeliveredNotification.objects.create(
                user=self.user, source_engine="PGE", source_object_type="GuidanceItem",
                source_object_id=1, channel="in_app", title="T2", message="M2",
                status="sent", dedupe_hash=hash_val,
            )

    def test_dedupe_hash_different_channels(self):
        from apps.core.ai_delivery.models import DeliveredNotification

        hash1 = DeliveredNotification.compute_dedupe_hash(
            self.user.id, "in_app", "PGE", "GuidanceItem", 1,
        )
        hash2 = DeliveredNotification.compute_dedupe_hash(
            self.user.id, "email", "PGE", "GuidanceItem", 1,
        )
        self.assertNotEqual(hash1, hash2)

    def test_str_representation(self):
        from apps.core.ai_delivery.models import DeliveredNotification

        record = DeliveredNotification(
            source_engine="PGE", channel="in_app", status="sent",
            title="A very long title that should be truncated",
        )
        result = str(record)
        self.assertIn("PGE", result)
        self.assertIn("in_app", result)
        self.assertIn("sent", result)


# ---------------------------------------------------------------------------
# Policy tests
# ---------------------------------------------------------------------------


class DeliveryPolicyTests(DNETestBase):

    def test_dedupe_passes_first_time(self):
        from apps.core.ai_delivery.delivery_policies import check_dedupe

        passed, reason = check_dedupe(self.user, "in_app", "PGE", "GuidanceItem", 999)
        self.assertTrue(passed)
        self.assertIsNone(reason)

    def test_dedupe_blocks_second_time(self):
        from apps.core.ai_delivery.delivery_policies import check_dedupe
        from apps.core.ai_delivery.models import DeliveredNotification

        dedupe_hash = DeliveredNotification.compute_dedupe_hash(
            self.user.id, "in_app", "PGE", "GuidanceItem", 1,
        )
        DeliveredNotification.objects.create(
            user=self.user, source_engine="PGE", source_object_type="GuidanceItem",
            source_object_id=1, channel="in_app", title="T", message="M",
            status="sent", dedupe_hash=dedupe_hash,
        )

        passed, reason = check_dedupe(self.user, "in_app", "PGE", "GuidanceItem", 1)
        self.assertFalse(passed)
        self.assertEqual(reason, "duplicate")

    def test_quiet_hours_allows_inapp(self):
        """In-app is always allowed regardless of quiet hours."""
        from apps.core.ai_delivery.delivery_policies import check_quiet_hours

        passed, reason = check_quiet_hours(self.user, "in_app")
        self.assertTrue(passed)
        self.assertIsNone(reason)

    def test_quiet_hours_blocks_email_during_quiet(self):
        from apps.core.ai_delivery.delivery_policies import check_quiet_hours

        self.user.preferences.sms_quiet_hours_enabled = True
        # Set quiet hours to cover now
        now = timezone.localtime().time()
        # Make quiet start 1 hour before now, end 1 hour after
        start_hour = (now.hour - 1) % 24
        end_hour = (now.hour + 1) % 24
        self.user.preferences.sms_quiet_start = datetime.time(start_hour, 0)
        self.user.preferences.sms_quiet_end = datetime.time(end_hour, 0)
        self.user.preferences.save()

        passed, reason = check_quiet_hours(self.user, "email")
        self.assertFalse(passed)
        self.assertIn("quiet_hours", reason)

    def test_throttle_allows_under_limit(self):
        from apps.core.ai_delivery.delivery_policies import check_throttle

        passed, reason = check_throttle(self.user, "in_app", max_per_hour=2, max_per_day=6)
        self.assertTrue(passed)

    def test_throttle_blocks_over_hourly_limit(self):
        from apps.core.ai_delivery.delivery_policies import check_throttle
        from apps.core.ai_delivery.models import DeliveredNotification

        # Create 2 sent notifications in the last hour
        for i in range(2):
            DeliveredNotification.objects.create(
                user=self.user, source_engine="PGE", source_object_type="GuidanceItem",
                source_object_id=100 + i, channel="in_app", title=f"T{i}", message=f"M{i}",
                status="sent",
                dedupe_hash=DeliveredNotification.compute_dedupe_hash(
                    self.user.id, "in_app", "PGE", "GuidanceItem", 100 + i,
                ),
            )

        passed, reason = check_throttle(self.user, "in_app", max_per_hour=2, max_per_day=6)
        self.assertFalse(passed)
        self.assertIn("throttle_hourly", reason)

    def test_throttle_blocks_over_daily_limit(self):
        from apps.core.ai_delivery.delivery_policies import check_throttle
        from apps.core.ai_delivery.models import DeliveredNotification

        # Create 3 sent notifications today
        for i in range(3):
            DeliveredNotification.objects.create(
                user=self.user, source_engine="PGE", source_object_type="GuidanceItem",
                source_object_id=200 + i, channel="in_app", title=f"T{i}", message=f"M{i}",
                status="sent",
                dedupe_hash=DeliveredNotification.compute_dedupe_hash(
                    self.user.id, "in_app", "PGE", "GuidanceItem", 200 + i,
                ),
            )

        passed, reason = check_throttle(self.user, "in_app", max_per_hour=10, max_per_day=3)
        self.assertFalse(passed)
        self.assertIn("throttle_daily", reason)

    def test_apply_delivery_policies_full_pass(self):
        from apps.core.ai_delivery.delivery_policies import apply_delivery_policies

        passed, reason = apply_delivery_policies(
            self.user, "in_app", "PGE", "GuidanceItem", 9999,
        )
        self.assertTrue(passed)
        self.assertIsNone(reason)


# ---------------------------------------------------------------------------
# Delivery engine tests
# ---------------------------------------------------------------------------


class DeliveryEngineTests(DNETestBase):

    def test_build_payload_guidance(self):
        from apps.core.ai_delivery.delivery_engine import _build_payload

        item = MagicMock()
        item.title = "Test Guidance"
        item.message = "Guidance message"
        type(item).__name__ = "GuidanceItem"

        payload = _build_payload("PGE", item)
        self.assertIn("Guidance", payload["title"])
        self.assertEqual(payload["icon"], "💡")

    def test_build_payload_briefing(self):
        from apps.core.ai_delivery.delivery_engine import _build_payload

        briefing = MagicMock()
        briefing.summary_text = "Today's summary"
        type(briefing).__name__ = "DailyBriefing"

        payload = _build_payload("DBE", briefing)
        self.assertIn("Briefing", payload["title"])
        self.assertEqual(payload["icon"], "📋")

    def test_build_payload_weekly_report(self):
        from apps.core.ai_delivery.delivery_engine import _build_payload

        report = MagicMock()
        report.summary_text = "Weekly summary"
        report.id = 42
        type(report).__name__ = "WeeklyIntelligenceReport"

        payload = _build_payload("WIRE", report)
        self.assertIn("Weekly", payload["title"])
        self.assertIn("/intelligence/weekly/42/", payload["action_url"])

    def test_build_payload_unknown_type(self):
        from apps.core.ai_delivery.delivery_engine import _build_payload

        obj = MagicMock()
        type(obj).__name__ = "UnknownType"

        payload = _build_payload("???", obj)
        self.assertIsNone(payload)

    def test_get_enabled_channels_defaults(self):
        """Default: in_app enabled, email/sms disabled."""
        from apps.core.ai_delivery.delivery_engine import _get_enabled_channels

        channels = _get_enabled_channels(self.user)
        self.assertIn("in_app", channels)
        self.assertNotIn("email", channels)
        self.assertNotIn("sms", channels)

    def test_get_enabled_channels_email_enabled(self):
        from apps.core.ai_delivery.delivery_engine import _get_enabled_channels

        self.user.preferences.intelligence_email_enabled = True
        self.user.preferences.email_notifications_enabled = True
        self.user.preferences.save()

        channels = _get_enabled_channels(self.user)
        self.assertIn("email", channels)

    def test_deliver_due_idempotent(self):
        """Running delivery twice should not create duplicates."""
        from apps.core.ai_delivery.delivery_engine import deliver_due_notifications
        from apps.core.ai_delivery.models import DeliveredNotification

        # First run
        deliver_due_notifications()
        count1 = DeliveredNotification.objects.filter(user=self.user).count()

        # Second run
        deliver_due_notifications()
        count2 = DeliveredNotification.objects.filter(user=self.user).count()

        self.assertEqual(count1, count2)


# ---------------------------------------------------------------------------
# Router tests
# ---------------------------------------------------------------------------


class DeliveryRouterTests(DNETestBase):

    def test_deliver_in_app_creates_notification(self):
        from apps.core.ai_delivery.delivery_router import deliver_in_app

        payload = {
            "title": "Test Guidance",
            "message": "A test message",
            "action_url": "/guidance/inbox/",
            "icon": "💡",
        }

        record = deliver_in_app(
            self.user, payload, "PGE", "GuidanceItem", 1,
        )

        self.assertIsNotNone(record)
        self.assertEqual(record.status, "sent")
        self.assertEqual(record.channel, "in_app")

        # Check in-app notification was also created
        from apps.core.models import Notification
        notif = Notification.objects.filter(
            user=self.user, category="intelligence",
        ).first()
        self.assertIsNotNone(notif)
        self.assertIn("Guidance", notif.title)

    def test_deliver_in_app_dedupe(self):
        """Second delivery of same item should return None."""
        from apps.core.ai_delivery.delivery_router import deliver_in_app

        payload = {
            "title": "Test", "message": "Msg",
            "action_url": "/test/", "icon": "🧠",
        }

        record1 = deliver_in_app(self.user, payload, "PGE", "GuidanceItem", 1)
        record2 = deliver_in_app(self.user, payload, "PGE", "GuidanceItem", 1)

        self.assertIsNotNone(record1)
        self.assertIsNone(record2)


# ---------------------------------------------------------------------------
# View tests
# ---------------------------------------------------------------------------


class DeliveryViewTests(DNETestBase):

    def setUp(self):
        super().setUp()
        self.client.login(email="dne_test@example.com", password="testpass123")

    def test_settings_page_loads(self):
        response = self.client.get("/intelligence/delivery/settings/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Intelligence Notifications")

    def test_settings_save(self):
        response = self.client.post("/intelligence/delivery/settings/save/", {
            "intelligence_inapp_enabled": "on",
            "intelligence_max_per_day": "10",
            "intelligence_max_per_hour": "3",
        })
        self.assertEqual(response.status_code, 302)

        self.user.preferences.refresh_from_db()
        self.assertTrue(self.user.preferences.intelligence_inapp_enabled)
        self.assertFalse(self.user.preferences.intelligence_email_enabled)
        self.assertEqual(self.user.preferences.intelligence_max_per_day, 10)
        self.assertEqual(self.user.preferences.intelligence_max_per_hour, 3)

    def test_history_page_loads(self):
        response = self.client.get("/intelligence/delivery/history/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Delivery History")

    def test_history_shows_records(self):
        from apps.core.ai_delivery.models import DeliveredNotification

        DeliveredNotification.objects.create(
            user=self.user, source_engine="PGE", source_object_type="GuidanceItem",
            source_object_id=1, channel="in_app", title="Test Title",
            message="Test msg", status="sent",
            dedupe_hash=DeliveredNotification.compute_dedupe_hash(
                self.user.id, "in_app", "PGE", "GuidanceItem", 1,
            ),
        )
        response = self.client.get("/intelligence/delivery/history/")
        self.assertContains(response, "Test Title")

    def test_settings_requires_login(self):
        self.client.logout()
        response = self.client.get("/intelligence/delivery/settings/")
        self.assertEqual(response.status_code, 302)

    def test_history_other_user_not_visible(self):
        """History only shows current user's records."""
        from apps.core.ai_delivery.models import DeliveredNotification

        other_user = User.objects.create_user(
            email="other_dne@example.com", password="testpass123",
        )
        TermsAcceptance.objects.create(
            user=other_user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        other_user.preferences.has_completed_onboarding = True
        other_user.preferences.save()

        DeliveredNotification.objects.create(
            user=other_user, source_engine="PGE", source_object_type="GuidanceItem",
            source_object_id=1, channel="in_app", title="Other User Record",
            message="Should not be visible", status="sent",
            dedupe_hash=DeliveredNotification.compute_dedupe_hash(
                other_user.id, "in_app", "PGE", "GuidanceItem", 1,
            ),
        )

        response = self.client.get("/intelligence/delivery/history/")
        self.assertNotContains(response, "Other User Record")


# ---------------------------------------------------------------------------
# ISE integration tests
# ---------------------------------------------------------------------------


class ISEIntegrationTests(TestCase):

    def test_dne_in_scheduler_registry(self):
        from apps.core.ai_scheduler.scheduler_registry import SCHEDULED_TASKS

        self.assertIn("deliver_intelligence_notifications", SCHEDULED_TASKS)
        task = SCHEDULED_TASKS["deliver_intelligence_notifications"]
        self.assertEqual(task["interval_seconds"], 600)

    def test_runner_function_importable(self):
        from apps.core.ai_scheduler.scheduler_runner import run_delivery_cycle

        self.assertIsNotNone(run_delivery_cycle)
