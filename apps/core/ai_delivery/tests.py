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


# ---------------------------------------------------------------------------
# Push notification tests
# ---------------------------------------------------------------------------


class PushChannelModelTests(DNETestBase):
    """Tests for push channel data model additions."""

    def test_push_channel_in_choices(self):
        from apps.core.ai_delivery.models import DeliveredNotification

        channels = [c[0] for c in DeliveredNotification.CHANNEL_CHOICES]
        self.assertIn("push", channels)

    def test_push_channel_constant(self):
        from apps.core.ai_delivery.models import DeliveredNotification

        self.assertEqual(DeliveredNotification.CHANNEL_PUSH, "push")

    def test_dedupe_hash_push_unique(self):
        """Push channel gets its own dedupe hash distinct from other channels."""
        from apps.core.ai_delivery.models import DeliveredNotification

        hash_inapp = DeliveredNotification.compute_dedupe_hash(
            self.user.id, "in_app", "PGE", "GuidanceItem", 1,
        )
        hash_push = DeliveredNotification.compute_dedupe_hash(
            self.user.id, "push", "PGE", "GuidanceItem", 1,
        )
        self.assertNotEqual(hash_inapp, hash_push)


class PushDeliveryRouterTests(DNETestBase):
    """Tests for the deliver_push handler in delivery_router."""

    def test_push_in_channel_handlers(self):
        from apps.core.ai_delivery.delivery_router import CHANNEL_HANDLERS

        self.assertIn("push", CHANNEL_HANDLERS)

    def test_deliver_push_no_devices_skips(self):
        """Push with no registered devices should skip."""
        from apps.core.ai_delivery.delivery_router import deliver_push

        payload = {"title": "Test", "message": "Msg", "action_url": "/test/"}
        record = deliver_push(self.user, payload, "PGE", "GuidanceItem", 1)

        self.assertIsNotNone(record)
        self.assertEqual(record.status, "skipped")
        self.assertEqual(record.skip_reason, "no_push_devices")
        self.assertEqual(record.channel, "push")

    @patch("apps.core.ai_delivery.apns_sender.send_push_notification")
    def test_deliver_push_success(self, mock_send):
        """Push with valid device should send."""
        mock_send.return_value = True

        from apps.mobile.models import MobileDevice

        MobileDevice.objects.create(
            user=self.user, device_id="test-device-123",
            push_token="abc123hex", push_enabled=True, is_active=True,
        )

        from apps.core.ai_delivery.delivery_router import deliver_push

        payload = {"title": "Test", "message": "Msg", "action_url": "/test/"}
        record = deliver_push(self.user, payload, "PGE", "GuidanceItem", 1)

        self.assertIsNotNone(record)
        self.assertEqual(record.status, "sent")
        self.assertEqual(record.channel, "push")
        mock_send.assert_called_once()
        # Adjustment 3: verify device results stored in metadata
        self.assertIn("devices", record.metadata)
        self.assertEqual(record.metadata["sent_count"], 1)

    @patch("apps.core.ai_delivery.apns_sender.send_push_notification")
    def test_deliver_push_multi_device(self, mock_send):
        """Push delivers to all active push devices and stores per-device results."""
        mock_send.side_effect = [True, False]  # First succeeds, second fails

        from apps.mobile.models import MobileDevice

        MobileDevice.objects.create(
            user=self.user, device_id="device-1",
            push_token="token1", push_enabled=True, is_active=True,
        )
        MobileDevice.objects.create(
            user=self.user, device_id="device-2",
            push_token="token2", push_enabled=True, is_active=True,
        )

        from apps.core.ai_delivery.delivery_router import deliver_push

        payload = {"title": "Test", "message": "Msg"}
        record = deliver_push(self.user, payload, "PGE", "GuidanceItem", 2)

        self.assertEqual(record.status, "sent")  # At least one succeeded
        self.assertEqual(len(record.metadata["devices"]), 2)
        self.assertEqual(record.metadata["sent_count"], 1)

    def test_deliver_push_dedupe(self):
        """Second push delivery of same item should dedupe."""
        from apps.core.ai_delivery.delivery_router import deliver_push

        payload = {"title": "Test", "message": "Msg"}
        record1 = deliver_push(self.user, payload, "PGE", "GuidanceItem", 1)
        record2 = deliver_push(self.user, payload, "PGE", "GuidanceItem", 1)

        self.assertIsNotNone(record1)
        self.assertIsNone(record2)


class PushDeliveryEngineTests(DNETestBase):
    """Tests for push integration in the delivery engine."""

    def test_get_enabled_channels_push_enabled(self):
        """Push appears when preference AND device both enabled."""
        from apps.core.ai_delivery.delivery_engine import _get_enabled_channels
        from apps.mobile.models import MobileDevice

        self.user.preferences.intelligence_push_enabled = True
        self.user.preferences.save()

        MobileDevice.objects.create(
            user=self.user, device_id="test-123",
            push_token="abc", push_enabled=True, is_active=True,
        )

        channels = _get_enabled_channels(self.user)
        self.assertIn("push", channels)

    def test_get_enabled_channels_push_no_device(self):
        """Push does NOT appear when preference on but no device registered."""
        from apps.core.ai_delivery.delivery_engine import _get_enabled_channels

        self.user.preferences.intelligence_push_enabled = True
        self.user.preferences.save()

        channels = _get_enabled_channels(self.user)
        self.assertNotIn("push", channels)

    def test_get_enabled_channels_push_disabled_pref(self):
        """Push does NOT appear when preference off even with device."""
        from apps.core.ai_delivery.delivery_engine import _get_enabled_channels
        from apps.mobile.models import MobileDevice

        MobileDevice.objects.create(
            user=self.user, device_id="test-123",
            push_token="abc", push_enabled=True, is_active=True,
        )

        channels = _get_enabled_channels(self.user)
        self.assertNotIn("push", channels)

    def test_get_enabled_channels_push_device_no_token(self):
        """Push does NOT appear when device has push_enabled but empty token."""
        from apps.core.ai_delivery.delivery_engine import _get_enabled_channels
        from apps.mobile.models import MobileDevice

        self.user.preferences.intelligence_push_enabled = True
        self.user.preferences.save()

        MobileDevice.objects.create(
            user=self.user, device_id="test-123",
            push_token="", push_enabled=True, is_active=True,
        )

        channels = _get_enabled_channels(self.user)
        self.assertNotIn("push", channels)


class PushPolicyTests(DNETestBase):
    """Tests for push-specific delivery policies."""

    def test_quiet_hours_blocks_push(self):
        """Push respects quiet hours (same as email/SMS)."""
        from apps.core.ai_delivery.delivery_policies import check_quiet_hours

        self.user.preferences.sms_quiet_hours_enabled = True
        now = timezone.localtime().time()
        start_hour = (now.hour - 1) % 24
        end_hour = (now.hour + 1) % 24
        self.user.preferences.sms_quiet_start = datetime.time(start_hour, 0)
        self.user.preferences.sms_quiet_end = datetime.time(end_hour, 0)
        self.user.preferences.save()

        passed, reason = check_quiet_hours(self.user, "push")
        self.assertFalse(passed)
        self.assertIn("quiet_hours", reason)

    def test_critical_push_bypasses_quiet_hours(self):
        """Critical priority push (priority=1) bypasses quiet hours."""
        from apps.core.ai_delivery.delivery_policies import check_quiet_hours

        self.user.preferences.sms_quiet_hours_enabled = True
        now = timezone.localtime().time()
        start_hour = (now.hour - 1) % 24
        end_hour = (now.hour + 1) % 24
        self.user.preferences.sms_quiet_start = datetime.time(start_hour, 0)
        self.user.preferences.sms_quiet_end = datetime.time(end_hour, 0)
        self.user.preferences.save()

        passed, reason = check_quiet_hours(self.user, "push", priority=1)
        self.assertTrue(passed)
        self.assertIsNone(reason)

    def test_non_critical_push_does_not_bypass_quiet_hours(self):
        """Non-critical push (priority=3) does NOT bypass quiet hours."""
        from apps.core.ai_delivery.delivery_policies import check_quiet_hours

        self.user.preferences.sms_quiet_hours_enabled = True
        now = timezone.localtime().time()
        start_hour = (now.hour - 1) % 24
        end_hour = (now.hour + 1) % 24
        self.user.preferences.sms_quiet_start = datetime.time(start_hour, 0)
        self.user.preferences.sms_quiet_end = datetime.time(end_hour, 0)
        self.user.preferences.save()

        passed, reason = check_quiet_hours(self.user, "push", priority=3)
        self.assertFalse(passed)

    def test_throttle_applies_to_push(self):
        """Push has its own throttle counters."""
        from apps.core.ai_delivery.delivery_policies import check_throttle
        from apps.core.ai_delivery.models import DeliveredNotification

        for i in range(2):
            DeliveredNotification.objects.create(
                user=self.user, source_engine="PGE",
                source_object_type="GuidanceItem",
                source_object_id=300 + i, channel="push", title=f"T{i}",
                message=f"M{i}", status="sent",
                dedupe_hash=DeliveredNotification.compute_dedupe_hash(
                    self.user.id, "push", "PGE", "GuidanceItem", 300 + i,
                ),
            )

        passed, reason = check_throttle(self.user, "push", max_per_hour=2, max_per_day=6)
        self.assertFalse(passed)
        self.assertIn("throttle_hourly", reason)


class PushAPNsSenderTests(TestCase):
    """Tests for the APNs sender module."""

    def test_apns_not_configured_returns_false(self):
        """send_push_notification returns False when APNs not configured."""
        from apps.core.ai_delivery import apns_sender

        # Reset cached client
        apns_sender.reset_client()

        with self.settings(APNS_AUTH_KEY="", APNS_KEY_ID="", APNS_TEAM_ID=""):
            result = apns_sender.send_push_notification(
                "abc123", "Title", "Body",
            )
            self.assertFalse(result)

    def test_reset_client_clears_cache(self):
        from apps.core.ai_delivery import apns_sender

        apns_sender._apns_client = "fake_client"
        apns_sender.reset_client()
        self.assertIsNone(apns_sender._apns_client)


class PushViewTests(DNETestBase):
    """Tests for push toggle in settings UI."""

    def setUp(self):
        super().setUp()
        self.client.login(email="dne_test@example.com", password="testpass123")

    def test_settings_save_with_push(self):
        response = self.client.post("/intelligence/delivery/settings/save/", {
            "intelligence_inapp_enabled": "on",
            "intelligence_push_enabled": "on",
            "intelligence_max_per_day": "6",
            "intelligence_max_per_hour": "2",
        })
        self.assertEqual(response.status_code, 302)
        self.user.preferences.refresh_from_db()
        self.assertTrue(self.user.preferences.intelligence_push_enabled)

    def test_settings_save_without_push(self):
        self.user.preferences.intelligence_push_enabled = True
        self.user.preferences.save()

        response = self.client.post("/intelligence/delivery/settings/save/", {
            "intelligence_inapp_enabled": "on",
            "intelligence_max_per_day": "6",
            "intelligence_max_per_hour": "2",
        })
        self.assertEqual(response.status_code, 302)
        self.user.preferences.refresh_from_db()
        self.assertFalse(self.user.preferences.intelligence_push_enabled)

    def test_settings_page_shows_push_toggle(self):
        response = self.client.get("/intelligence/delivery/settings/")
        self.assertContains(response, "Push Notifications")
        self.assertContains(response, "intelligence_push_enabled")

    def test_settings_page_push_disabled_without_device(self):
        """Push toggle should be disabled when no push device is registered."""
        response = self.client.get("/intelligence/delivery/settings/")
        self.assertContains(response, "Requires iOS app with push notifications enabled")

    def test_settings_page_push_enabled_with_device(self):
        """Push toggle should be enabled when push device is registered."""
        from apps.mobile.models import MobileDevice

        MobileDevice.objects.create(
            user=self.user, device_id="test-123",
            push_token="abc", push_enabled=True, is_active=True,
        )

        response = self.client.get("/intelligence/delivery/settings/")
        self.assertContains(response, "Receive intelligence alerts on your iOS device")

    def test_history_shows_push_icon(self):
        from apps.core.ai_delivery.models import DeliveredNotification

        DeliveredNotification.objects.create(
            user=self.user, source_engine="PGE",
            source_object_type="GuidanceItem",
            source_object_id=1, channel="push", title="Push Test",
            message="Push msg", status="sent",
            dedupe_hash=DeliveredNotification.compute_dedupe_hash(
                self.user.id, "push", "PGE", "GuidanceItem", 1,
            ),
        )
        response = self.client.get("/intelligence/delivery/history/")
        self.assertContains(response, "Push Test")


# ---------------------------------------------------------------------------
# Phase 4: Proactive Intelligence Delivery Tests
# ---------------------------------------------------------------------------


class ProactiveDeliveryPayloadTests(DNETestBase):
    """Tests for new payload builders (Insight, DomainCorrelation, CosPromptSchedule)."""

    def test_insight_payload_critical(self):
        from apps.core.ai_delivery.delivery_engine import _build_payload

        insight = MagicMock()
        insight.__class__.__name__ = "Insight"
        type(insight).__name__ = "Insight"
        insight.title = "Sleep below 5h for 3 consecutive days"
        insight.message = "Your sleep has dropped critically low."
        insight.severity = "critical"

        payload = _build_payload("PIE", insight)
        self.assertIsNotNone(payload)
        self.assertIn("🚨", payload["title"])
        self.assertEqual(payload["priority"], 1)

    def test_insight_payload_warning(self):
        from apps.core.ai_delivery.delivery_engine import _build_payload

        insight = MagicMock()
        type(insight).__name__ = "Insight"
        insight.title = "Weight trending up"
        insight.message = "Weight has increased 3 lbs this week."
        insight.severity = "warning"

        payload = _build_payload("PIE", insight)
        self.assertIsNotNone(payload)
        self.assertIn("⚠️", payload["title"])
        self.assertEqual(payload["priority"], 3)

    def test_correlation_payload(self):
        from apps.core.ai_delivery.delivery_engine import _build_payload

        corr = MagicMock()
        type(corr).__name__ = "DomainCorrelation"
        corr.strength = "strong"
        corr.narrative = "When sleep drops below 6.5h, mood is negative 78% of the time."

        payload = _build_payload("CDCE", corr)
        self.assertIsNotNone(payload)
        self.assertIn("🔗", payload["title"])
        self.assertIn("6.5h", payload["message"])

    def test_cos_prompt_payload(self):
        from apps.core.ai_delivery.delivery_engine import _build_payload

        prompt = MagicMock()
        type(prompt).__name__ = "CosPromptSchedule"
        prompt.activity_type = "workout"
        prompt.prompt_text = "Time to get moving! Your workout is in 15 minutes."

        payload = _build_payload("COS", prompt)
        self.assertIsNotNone(payload)
        self.assertIn("Workout", payload["title"])
        self.assertIn("15 minutes", payload["message"])


class DeliverSingleWithPayloadTests(DNETestBase):
    """Tests for deliver_single with optional payload parameter."""

    @patch("apps.core.ai_delivery.delivery_engine._get_enabled_channels")
    @patch("apps.core.ai_delivery.delivery_engine._deliver_to_channel")
    def test_deliver_single_with_explicit_payload(self, mock_channel, mock_channels):
        from apps.core.ai_delivery.delivery_engine import deliver_single

        mock_channels.return_value = ["in_app"]
        mock_channel.return_value = True

        source = MagicMock()
        source.id = 42
        type(source).__name__ = "TestObject"

        payload = {
            "title": "Custom Title",
            "message": "Custom message",
            "action_url": "/custom/",
            "priority": 2,
        }

        deliver_single(self.user, "TEST", source, payload=payload)
        mock_channel.assert_called_once()
        call_args = mock_channel.call_args
        self.assertEqual(call_args[0][2], payload)  # payload arg

    @patch("apps.core.ai_delivery.delivery_engine._get_enabled_channels")
    @patch("apps.core.ai_delivery.delivery_engine._deliver_to_channel")
    def test_deliver_single_auto_builds_payload(self, mock_channel, mock_channels):
        from apps.core.ai_delivery.delivery_engine import deliver_single

        mock_channels.return_value = ["in_app"]
        mock_channel.return_value = True

        # Use a mock that looks like a DomainCorrelation
        corr = MagicMock()
        corr.id = 1
        type(corr).__name__ = "DomainCorrelation"
        corr.strength = "moderate"
        corr.narrative = "Test pattern found."

        deliver_single(self.user, "CDCE", corr)
        mock_channel.assert_called_once()


class InsightGathererTests(DNETestBase):
    """Tests for _get_undelivered_insights."""

    def test_gets_critical_insights(self):
        from apps.core.ai_delivery.delivery_engine import _get_undelivered_insights
        from apps.core.ai_insights.models import Insight

        Insight.objects.create(
            user=self.user,
            insight_type="rule",
            severity="critical",
            title="Critical Sleep Pattern",
            message="Sleep below safe levels.",
            module="health",
            confidence_score=0.9,
        )
        Insight.objects.create(
            user=self.user,
            insight_type="rule",
            severity="info",
            title="Info only",
            message="FYI.",
            module="health",
            confidence_score=0.5,
        )

        items = _get_undelivered_insights(self.user)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0][0], "PIE")
        self.assertEqual(items[0][1], "Insight")

    def test_empty_when_no_critical(self):
        from apps.core.ai_delivery.delivery_engine import _get_undelivered_insights

        items = _get_undelivered_insights(self.user)
        self.assertEqual(len(items), 0)


class CorrelationGathererTests(DNETestBase):
    """Tests for _get_undelivered_correlations."""

    def test_gets_strong_correlations(self):
        from apps.core.ai_delivery.delivery_engine import _get_undelivered_correlations
        from apps.core.ai_cross_domain.models import DomainCorrelation

        DomainCorrelation.objects.create(
            user=self.user,
            domain_a="health",
            domain_b="journal",
            correlation_type="sleep_mood",
            strength="strong",
            strength_score=0.78,
            narrative="Test pattern.",
            evidence_summary="Test evidence.",
            dedupe_key="dne_test_1",
            status="active",
        )
        DomainCorrelation.objects.create(
            user=self.user,
            domain_a="health",
            domain_b="health",
            correlation_type="fasting_fitness",
            strength="weak",
            strength_score=0.35,
            narrative="Weak pattern.",
            evidence_summary="Weak evidence.",
            dedupe_key="dne_test_2",
            status="active",
        )

        items = _get_undelivered_correlations(self.user)
        # Only strong/moderate, not weak
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0][0], "CDCE")

    def test_ignores_old_correlations(self):
        from apps.core.ai_delivery.delivery_engine import _get_undelivered_correlations
        from apps.core.ai_cross_domain.models import DomainCorrelation

        corr = DomainCorrelation.objects.create(
            user=self.user,
            domain_a="health",
            domain_b="journal",
            correlation_type="sleep_mood",
            strength="strong",
            strength_score=0.78,
            narrative="Old pattern.",
            evidence_summary="Old evidence.",
            dedupe_key="dne_test_old",
            status="active",
        )
        # Backdate to 48h ago
        DomainCorrelation.objects.filter(pk=corr.pk).update(
            created_at=timezone.now() - datetime.timedelta(hours=48),
        )

        items = _get_undelivered_correlations(self.user)
        self.assertEqual(len(items), 0)
