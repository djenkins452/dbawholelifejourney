"""Tests for the weight-sync staleness signal + source-aware accountability.

The trust contract: when recent weight came from Apple Health AND a sync
device is active, a multi-day gap is a SYNC failure (not the user failing to
weigh) and must be narrated as such. Manual-only gaps keep the generic
message.
"""

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.core.ai_insights.rules_health import MissingWeightLoggingRule
from apps.health.models import WeightEntry
from apps.health.services.weight_sync import get_weight_sync_status
from apps.users.models import TermsAcceptance, User


class WeightSyncStatusTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="wsync@test.com", password="testpass123"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )

    def _entry(self, days_ago, source):
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("293.7"),
            unit="lb",
            recorded_at=timezone.now() - timedelta(days=days_ago),
            source=source,
        )

    def _activate_device(self):
        from apps.mobile.models import MobileDevice
        MobileDevice.objects.create(
            user=self.user, device_id="dev-1", is_active=True,
        )

    def test_no_entries(self):
        st = get_weight_sync_status(self.user)
        self.assertFalse(st["has_entries"])
        self.assertFalse(st["sync_stale"])

    def test_apple_health_stale_with_active_device_is_sync_failure(self):
        # 25-day-old Apple Health entries + active device → sync stale.
        for d in (25, 26, 27):
            self._entry(d, "apple_health")
        self._activate_device()
        st = get_weight_sync_status(self.user)
        self.assertEqual(st["recent_source"], "apple_health")
        self.assertTrue(st["sync_device_active"])
        self.assertTrue(st["sync_expected"])
        self.assertTrue(st["sync_stale"])
        self.assertGreaterEqual(st["gap_days"], 24)

    def test_apple_health_gap_but_no_device_is_not_flagged_sync_stale(self):
        # Without an active device we cannot claim the sync stalled.
        for d in (25, 26):
            self._entry(d, "apple_health")
        st = get_weight_sync_status(self.user)
        self.assertFalse(st["sync_device_active"])
        self.assertFalse(st["sync_stale"])

    def test_manual_only_gap_is_not_sync_stale(self):
        # Manual logging gap is the user, not a sync — never "sync stale".
        for d in (25, 26):
            self._entry(d, "manual")
        self._activate_device()
        st = get_weight_sync_status(self.user)
        self.assertEqual(st["recent_source"], "manual")
        self.assertFalse(st["sync_stale"])

    def test_fresh_apple_health_sync_not_stale(self):
        self._entry(0, "apple_health")
        self._activate_device()
        st = get_weight_sync_status(self.user)
        self.assertFalse(st["sync_stale"])


class SourceAwareInsightTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="wsync2@test.com", password="testpass123"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.rule = MissingWeightLoggingRule()

    def _entry(self, days_ago, source):
        WeightEntry.objects.create(
            user=self.user, value=Decimal("293.7"), unit="lb",
            recorded_at=timezone.now() - timedelta(days=days_ago), source=source,
        )

    def test_stale_apple_sync_emits_sync_message_not_blame(self):
        from apps.mobile.models import MobileDevice
        for d in (25, 26, 27):
            self._entry(d, "apple_health")
        MobileDevice.objects.create(user=self.user, device_id="d", is_active=True)

        results = self.rule.evaluate(self.user, {"event_type": "scheduled_check"})
        self.assertTrue(results)
        ins = results[0]
        self.assertEqual(ins["severity"], "warning")
        self.assertIn("sync", ins["title"].lower())
        self.assertTrue(ins["evidence"]["sync_stale"])
        # Must NOT imply the user stopped weighing.
        self.assertNotIn("No weight entry", ins["title"])

    def test_manual_gap_keeps_generic_message(self):
        for d in (25, 26):
            self._entry(d, "manual")
        results = self.rule.evaluate(self.user, {"event_type": "scheduled_check"})
        self.assertTrue(results)
        ins = results[0]
        self.assertEqual(ins["severity"], "info")
        self.assertIn("No weight entry", ins["title"])
        self.assertFalse(ins["evidence"]["sync_stale"])
