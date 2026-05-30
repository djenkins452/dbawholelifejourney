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

from apps.core.ai_insights.models import Insight
from apps.core.ai_insights.rules_health import MissingWeightLoggingRule
from apps.health.models import WeightEntry
from apps.health.services.weight_sync import (
    get_weight_sync_status,
    resolve_weight_gap_insights,
)
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


class BethDashboardConvergenceTests(TestCase):
    """Regression guard for the 2026-05-30 divergence: Beth read SAE (fresh)
    while the dashboard accountability card read persisted Insight rows
    (stale until 7-day window). When fresh weight arrives, both surfaces
    MUST converge in the same render cycle — no hard refresh, no waiting."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="converge@test.com", password="testpass123"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )

    def _make_stale_warning_insight(self):
        return Insight.objects.create(
            user=self.user,
            module="health",
            insight_type="missing_weight_logging",
            severity="warning",
            title="Apple Health weight sync may have stopped",
            message="Your last weight synced from Apple Health was 25 days ago.",
            confidence_score=0.9,
            explain_why="test",
            evidence={"sync_stale": True},
            dedupe_key="test-stale-1",
            status="new",
        )

    def test_resolver_dismisses_active_weight_gap_insight(self):
        ins = self._make_stale_warning_insight()
        count = resolve_weight_gap_insights(self.user)
        self.assertEqual(count, 1)
        ins.refresh_from_db()
        self.assertEqual(ins.status, "dismissed")

    def test_resolver_idempotent_and_safe_with_no_active_insight(self):
        self.assertEqual(resolve_weight_gap_insights(self.user), 0)

    def test_post_save_signal_dismisses_stale_insight_on_new_entry(self):
        """THE core defect: stale warning insight in DB, fresh WeightEntry
        ingests, signal fires → insight auto-dismissed in same transaction."""
        ins = self._make_stale_warning_insight()
        # Simulate Apple Health ingest creating a fresh entry today.
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("290.6"),
            unit="lb",
            recorded_at=timezone.now(),
            source="apple_health",
            sync_id="fresh-sync-1",
        )
        ins.refresh_from_db()
        self.assertEqual(
            ins.status, "dismissed",
            "Stale weight-gap insight MUST be dismissed when a fresh "
            "WeightEntry arrives — otherwise dashboard diverges from Beth.",
        )

    def test_composer_convergence_guard_suppresses_stale_insight(self):
        """Even if a dismissal is ever missed, the composer's SAE-aware
        guard must hide a stale weight insight when SAE says sync is
        fresh. Belt-and-suspenders so dashboard ≠ Beth is impossible."""
        from apps.dashboard_v3.services.composer import (
            _build_accountability_cards,
        )
        # 1) Create a fresh weight entry so SAE says sync is fresh.
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("290.6"),
            unit="lb",
            recorded_at=timezone.now(),
            source="apple_health",
            sync_id="fresh-sync-2",
        )
        # 2) Force a stale insight to LINGER (simulate missed signal).
        # The post_save signal will dismiss this — re-mark it 'new' to
        # specifically test the composer guard.
        ins = self._make_stale_warning_insight()
        Insight.objects.filter(pk=ins.pk).update(status="new")
        # 3) Composer must NOT surface it in the Health accountability card.
        cards = _build_accountability_cards(self.user)
        health = next((c for c in cards if c["slug"] == "health"), None)
        if health and health.get("needs_attention"):
            for n in health["needs_attention"]:
                self.assertNotIn(
                    "sync", n["title"].lower(),
                    "Composer guard failed — stale Apple Health sync warning "
                    "leaked to dashboard while SAE shows fresh sync. This is "
                    "the Beth/dashboard divergence we forbade."
                )
