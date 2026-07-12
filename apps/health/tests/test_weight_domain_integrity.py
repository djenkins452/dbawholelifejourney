"""
Weight Layer 1 truth-domain integrity — the Weight domain must hold ONLY weight.

Regression guard for the 2026-07-12 incident where body measurements (chest/waist/hips,
unit "in") were written into WeightEntry via a fail-open log_weight path, corrupting every
weight reader ("51.0 in latest weight", "-198.6 lb weight loss"). Weight never consumes
BodyComposition; Body Intelligence consumes Weight.

Location: apps/health/tests/test_weight_domain_integrity.py
"""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.health.models import BodyCompositionEntry, WeightEntry
from apps.health.services.weight_summary import build_weight_summary
from apps.users.models import TermsAcceptance

User = get_user_model()


def _user(email="weightguard@example.com"):
    u = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0")
    )
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


class WeightModelGuardTest(TestCase):
    def setUp(self):
        self.user = _user()

    def test_valid_weight_units_allowed(self):
        WeightEntry.objects.create(user=self.user, value=Decimal("200.0"), unit="lb")
        WeightEntry.objects.create(user=self.user, value=Decimal("90.0"), unit="kg")
        self.assertEqual(WeightEntry.objects.filter(user=self.user).count(), 2)

    def test_non_weight_unit_rejected_on_insert(self):
        with self.assertRaises(ValueError):
            WeightEntry.objects.create(user=self.user, value=Decimal("51.0"), unit="in")
        self.assertEqual(WeightEntry.objects.filter(user=self.user).count(), 0)

    def test_unit_change_to_non_weight_rejected(self):
        w = WeightEntry.objects.create(user=self.user, value=Decimal("200.0"), unit="lb")
        w.unit = "in"
        with self.assertRaises(ValueError):
            w.save(update_fields=["unit"])

    def test_status_only_update_not_blocked_for_cleanup(self):
        # Insert a contaminated row bypassing save() (as legacy data would exist), then
        # confirm a status-only soft delete is NOT blocked (needed to clean it up).
        WeightEntry.objects.bulk_create([
            WeightEntry(user=self.user, value=Decimal("51.0"), unit="in",
                        recorded_at=timezone.now(), notes="Chest measurement")
        ])
        bad = WeightEntry.all_objects.get(user=self.user, unit="in")
        bad.status = "deleted"
        bad.deleted_at = timezone.now()
        bad.save(update_fields=["status", "deleted_at", "updated_at"])  # must not raise
        self.assertFalse(WeightEntry.objects.filter(user=self.user).exists())


class LogWeightHandlerGuardTest(TestCase):
    def setUp(self):
        self.user = _user()

    def test_log_weight_rejects_non_weight_unit(self):
        from apps.ai.action_handlers import ActionHandler
        h = ActionHandler(self.user)
        result = h.handle_log_weight(value=51.0, unit="in", notes="Chest measurement")
        self.assertFalse(result.success)
        self.assertEqual(result.error, "wrong_domain")
        self.assertEqual(WeightEntry.objects.filter(user=self.user).count(), 0)

    def test_log_weight_still_works_for_real_weight(self):
        from apps.ai.action_handlers import ActionHandler
        h = ActionHandler(self.user)
        result = h.handle_log_weight(value=198.5, unit="lb")
        self.assertTrue(result.success)
        self.assertEqual(WeightEntry.objects.filter(user=self.user).count(), 1)

    def test_body_measurement_still_routes_to_body_composition(self):
        from apps.ai.action_handlers import ActionHandler
        h = ActionHandler(self.user)
        result = h.handle_log_body_measurement(metric="waist", value=34.5)
        self.assertTrue(result.success)
        self.assertTrue(
            BodyCompositionEntry.objects.filter(user=self.user, metric_name="waist").exists()
        )
        # And it must NOT have leaked into Weight.
        self.assertEqual(WeightEntry.objects.filter(user=self.user).count(), 0)


class DecontaminationMigrationTest(TestCase):
    """The cleanup logic re-homes contaminated rows to BodyComposition and removes them
    from Weight, restoring correct weight truth."""

    def setUp(self):
        self.user = _user()

    def test_decontaminate_rehomes_and_restores_weight(self):
        now = timezone.now()
        # Real weight history.
        WeightEntry.objects.create(user=self.user, value=Decimal("311.0"), unit="lb",
                                   recorded_at=now - timedelta(days=60))
        WeightEntry.objects.create(user=self.user, value=Decimal("285.0"), unit="lb",
                                   recorded_at=now - timedelta(hours=2))
        # Contaminated rows (inserted bypassing the guard, as legacy prod data).
        WeightEntry.objects.bulk_create([
            WeightEntry(user=self.user, value=Decimal("51.0"), unit="in",
                        recorded_at=now, notes="Chest measurement"),
            WeightEntry(user=self.user, value=Decimal("53.5"), unit="in",
                        recorded_at=now, notes="Waist measurement"),
            WeightEntry(user=self.user, value=Decimal("47.0"), unit="in",
                        recorded_at=now, notes="Hips measurement"),
        ])

        # BEFORE: weight truth is corrupted — the latest "weight" is the 51.0 "in" chest
        # row, which value_in_lb mis-converts as kg (51 * 2.20462 = 112.4 lb), exactly
        # the "now 112.4 lb" seen in the incident screenshot.
        facts_before = build_weight_summary(self.user)
        self.assertAlmostEqual(facts_before["current_lb"], 112.4, places=1)
        self.assertNotEqual(facts_before["current_lb"], 285.0)

        # Run the migration's data function directly against the live model registry.
        from importlib import import_module
        from django.apps import apps as global_apps
        mig = import_module(
            "apps.health.migrations.0100_decontaminate_weight_domain"
        )
        mig.decontaminate(global_apps, None)

        # AFTER: contaminated rows are gone from Weight; real weight is restored.
        self.assertFalse(
            WeightEntry.objects.filter(user=self.user).exclude(unit__in=["lb", "kg"]).exists()
        )
        facts_after = build_weight_summary(self.user)
        self.assertEqual(facts_after["current_lb"], 285.0)
        self.assertEqual(facts_after["first_lb"], 311.0)
        self.assertEqual(facts_after["total_change_lb"], -26.0)

        # And the data was preserved as body measurements.
        self.assertTrue(BodyCompositionEntry.objects.filter(user=self.user, metric_name="chest").exists())
        self.assertTrue(BodyCompositionEntry.objects.filter(user=self.user, metric_name="waist").exists())
        self.assertTrue(BodyCompositionEntry.objects.filter(user=self.user, metric_name="hips").exists())
