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
    resolve_stale_weight_insight_if_cleared,
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

    def test_dashboard_load_resolves_preexisting_stale_insight(self):
        """THE production fix: a stale insight that predated the post_save
        signal still gets resolved on the NEXT dashboard load — because
        the resolver runs on render whenever SAE says the condition cleared.

        Simulates the exact prod scenario:
          1. WeightEntry already exists (May 30 fresh weight) — saved before
             the signal-based fix deployed, so the post_save handler never
             dismissed the stale insight.
          2. The stale 'missing_weight_logging' insight from when sync was
             actually stalled is still status='new' in the DB.
          3. Dashboard loads → SAE-gated resolver runs → insight dismissed.
          4. Neither the accountability card NOR the executive summary's
             needs_attention surfaces the stale warning anymore.
        """
        from apps.core.cos_briefing.executive_summary import build_executive_summary
        from apps.dashboard_v3.services.composer import _build_accountability_cards

        # Pre-existing fresh weight (the May 30 ingest).
        WeightEntry.objects.create(
            user=self.user, value=Decimal("290.6"), unit="lb",
            recorded_at=timezone.now(), source="apple_health",
            sync_id="prod-fresh-1",
        )
        # Pre-existing stale warning insight that NEVER got dismissed.
        ins = self._make_stale_warning_insight()
        # Defeat the post_save dismissal so we're testing the load-path
        # resolver specifically (this is the "predated the signal" case).
        Insight.objects.filter(pk=ins.pk).update(status="new")

        # 1. The resolver runs (this is what the v3 view calls on load).
        dismissed = resolve_stale_weight_insight_if_cleared(self.user)
        self.assertGreaterEqual(
            dismissed, 1,
            "Pre-existing stale insight MUST be dismissed when SAE says "
            "sync is fresh — otherwise Danny's dashboard keeps showing a "
            "warning Beth already cleared.",
        )
        ins.refresh_from_db()
        self.assertEqual(ins.status, "dismissed")

        # 2. Executive summary's needs_attention is now clean (it filters
        #    on status in (new,read) — dismissed rows excluded).
        summary = build_executive_summary(self.user)
        for n in summary.get("needs_attention", []):
            self.assertNotIn(
                "sync", n["title"].lower(),
                "Executive Summary's 'Needs Attention' is leaking a stale "
                "weight-sync warning — Beth/dashboard divergence.",
            )

        # 3. Accountability card is also clean.
        cards = _build_accountability_cards(self.user)
        health = next((c for c in cards if c["slug"] == "health"), None)
        if health:
            for n in health.get("needs_attention", []):
                self.assertNotIn("sync", n["title"].lower())

    def test_resolver_does_not_dismiss_when_sync_is_actually_stale(self):
        """Safety: if SAE genuinely still says stale, do NOT auto-dismiss
        (we'd be hiding a real warning)."""
        # No fresh weight; old apple_health entries → sync_stale=True via SAE
        WeightEntry.objects.create(
            user=self.user, value=Decimal("293.7"), unit="lb",
            recorded_at=timezone.now() - timedelta(days=25),
            source="apple_health", sync_id="old-1",
        )
        from apps.mobile.models import MobileDevice
        MobileDevice.objects.create(user=self.user, device_id="d", is_active=True)
        ins = self._make_stale_warning_insight()
        Insight.objects.filter(pk=ins.pk).update(status="new")

        dismissed = resolve_stale_weight_insight_if_cleared(self.user)
        self.assertEqual(dismissed, 0)
        ins.refresh_from_db()
        self.assertEqual(ins.status, "new")  # genuine warning preserved

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
