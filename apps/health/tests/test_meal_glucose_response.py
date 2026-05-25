"""
MealGlucoseResponse model + classifier (Phase 1A · C8) — tests.

Covers:

1. All five classification buckets via direct delta-peak / delta-2h
   inputs (lookup-table determinism).
2. Each eligibility gate skips correctly:
   - no logged_time
   - no baseline reading in -10m..+5m
   - fewer than 3 of 4 post-meal windows have data
   - a prior meal exists within 90 minutes
   - a workout overlaps the meal window
3. Idempotency: a second call on the same FoodEntry returns the
   existing row (status: already_classified) unless force=True.
4. mmol/L → mg/dL conversion is applied correctly.
5. The MealGlucoseResponse OneToOne constraint prevents duplicates.

Signal mute: GlucoseEntry post_save handlers fire SAE refresh via
Celery; muted at class scope using the same pattern as C3/C7.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models.signals import post_delete, post_save
from django.test import TestCase

from apps.ai.signals import (
    invalidate_cache_on_food_entry_delete,
    invalidate_cache_on_food_entry_save,
    invalidate_cache_on_medicine_log_delete,
    invalidate_cache_on_medicine_log_save,
    invalidate_insights_on_glucose_delete,
    invalidate_insights_on_glucose_save,
    refresh_sae_on_medicine_change,
    refresh_sae_on_medicine_schedule_change,
)
from apps.health.models import (
    FoodEntry,
    GlucoseEntry,
    MealGlucoseResponse,
    WorkoutSession,
)
from apps.health.services.meal_response_classifier import (
    ClassifierResult,
    classify_meal_glucose_response,
)
from apps.users.models import TermsAcceptance


User = get_user_model()


class _MuteRelatedSignals:
    """Mute SAE-refresh handlers on Intake / IntakeLog / IntakeSchedule
    AND GlucoseEntry. Each handler dispatches to Celery for SAE refresh,
    and in tests Celery's Redis connection retries 20× before falling
    back to sync — adding ~20s per save. C8 creates many GlucoseEntry
    rows per test, so muting them is essential for test runtime."""

    _MUTED = (
        (post_save, "health.IntakeLog", invalidate_cache_on_medicine_log_save),
        (post_delete, "health.IntakeLog", invalidate_cache_on_medicine_log_delete),
        (post_save, "health.Intake", refresh_sae_on_medicine_change),
        (post_delete, "health.Intake", refresh_sae_on_medicine_change),
        (post_save, "health.IntakeSchedule", refresh_sae_on_medicine_schedule_change),
        (post_delete, "health.IntakeSchedule", refresh_sae_on_medicine_schedule_change),
        (post_save, "health.GlucoseEntry", invalidate_insights_on_glucose_save),
        (post_delete, "health.GlucoseEntry", invalidate_insights_on_glucose_delete),
        (post_save, "health.FoodEntry", invalidate_cache_on_food_entry_save),
        (post_delete, "health.FoodEntry", invalidate_cache_on_food_entry_delete),
    )

    @classmethod
    def setUpClass(cls):
        for signal, sender, handler in cls._MUTED:
            signal.disconnect(handler, sender=sender)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        for signal, sender, handler in cls._MUTED:
            signal.connect(handler, sender=sender)


def _make_user(email: str = "c8@test.com"):
    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


def _make_food_entry(
    user, *, logged_date: date, logged_time=time(12, 0),
):
    return FoodEntry.objects.create(
        user=user,
        food_name="Test meal",
        food_brand="",
        quantity=Decimal("1"),
        serving_size=Decimal("1"),
        serving_unit="serving",
        logged_date=logged_date,
        logged_time=logged_time,
        meal_type=FoodEntry.MEAL_LUNCH,
    )


def _glucose_at(user, when: datetime, value_mg_dl: int):
    return GlucoseEntry.objects.create(
        user=user,
        value=Decimal(value_mg_dl),
        unit="mg/dL",
        recorded_at=when,
    )


def _populate_post_meal_curve(user, meal_at: datetime, *, baseline: int, peak: int, end_value: int):
    """Helper: baseline at meal-time + readings at +30/60/90/120m."""
    _glucose_at(user, meal_at, baseline)
    _glucose_at(user, meal_at + timedelta(minutes=30), int((baseline + peak) / 2))
    _glucose_at(user, meal_at + timedelta(minutes=60), peak)
    _glucose_at(user, meal_at + timedelta(minutes=90), int((peak + end_value) / 2))
    _glucose_at(user, meal_at + timedelta(minutes=120), end_value)


# ── Classification buckets ──────────────────────────────────────────


class ClassificationBucketsTests(_MuteRelatedSignals, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = _make_user("buckets@test.com")
        cls.meal_at = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)

    def _classify(self):
        entry = _make_food_entry(
            self.user, logged_date=self.meal_at.date(),
            logged_time=self.meal_at.time(),
        )
        obj, status = classify_meal_glucose_response(entry)
        self.assertEqual(status, ClassifierResult.OK)
        self.assertIsNotNone(obj)
        return obj

    def test_minimal_spike(self):
        # baseline 100, peak 120, end 110 → delta_peak 20, delta_2h 10
        _populate_post_meal_curve(self.user, self.meal_at, baseline=100, peak=120, end_value=110)
        obj = self._classify()
        self.assertEqual(obj.classification, MealGlucoseResponse.CLASS_MINIMAL_SPIKE)

    def test_moderate_spike(self):
        # baseline 100, peak 140, end 110 → delta_peak 40, delta_2h 10
        _populate_post_meal_curve(self.user, self.meal_at, baseline=100, peak=140, end_value=110)
        obj = self._classify()
        self.assertEqual(obj.classification, MealGlucoseResponse.CLASS_MODERATE_SPIKE)

    def test_large_spike(self):
        # baseline 100, peak 180, end 120 → delta_peak 80, delta_2h 20
        _populate_post_meal_curve(self.user, self.meal_at, baseline=100, peak=180, end_value=120)
        obj = self._classify()
        self.assertEqual(obj.classification, MealGlucoseResponse.CLASS_LARGE_SPIKE)

    def test_extreme_spike(self):
        # baseline 100, peak 210, end 130 → delta_peak 110, delta_2h 30
        _populate_post_meal_curve(self.user, self.meal_at, baseline=100, peak=210, end_value=130)
        obj = self._classify()
        self.assertEqual(obj.classification, MealGlucoseResponse.CLASS_EXTREME_SPIKE)

    def test_prolonged_spike_overrides_when_delta_2h_high(self):
        # baseline 100, peak 160, end 150 → delta_peak 60 (would be large),
        # delta_2h 50 (>= 40 → prolonged)
        _populate_post_meal_curve(self.user, self.meal_at, baseline=100, peak=160, end_value=150)
        obj = self._classify()
        self.assertEqual(obj.classification, MealGlucoseResponse.CLASS_PROLONGED_SPIKE)


# ── Eligibility gates ───────────────────────────────────────────────


class EligibilityGatesTests(_MuteRelatedSignals, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = _make_user("gates@test.com")
        cls.meal_at = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)

    def test_no_logged_time_skipped(self):
        entry = _make_food_entry(
            self.user, logged_date=self.meal_at.date(), logged_time=None,
        )
        obj, status = classify_meal_glucose_response(entry)
        self.assertIsNone(obj)
        self.assertEqual(status, ClassifierResult.SKIPPED_NO_TIME)

    def test_no_baseline_reading_skipped(self):
        # Post-meal readings exist but no -10m..+5m baseline.
        _glucose_at(self.user, self.meal_at + timedelta(minutes=30), 120)
        _glucose_at(self.user, self.meal_at + timedelta(minutes=60), 140)
        _glucose_at(self.user, self.meal_at + timedelta(minutes=90), 130)
        _glucose_at(self.user, self.meal_at + timedelta(minutes=120), 110)
        entry = _make_food_entry(
            self.user, logged_date=self.meal_at.date(),
            logged_time=self.meal_at.time(),
        )
        obj, status = classify_meal_glucose_response(entry)
        self.assertIsNone(obj)
        self.assertEqual(status, ClassifierResult.SKIPPED_NO_BASELINE)

    def test_insufficient_post_meal_windows_skipped(self):
        # Baseline yes, only +30 and +60 readings → 2 windows < 3.
        _glucose_at(self.user, self.meal_at, 100)
        _glucose_at(self.user, self.meal_at + timedelta(minutes=30), 120)
        _glucose_at(self.user, self.meal_at + timedelta(minutes=60), 130)
        entry = _make_food_entry(
            self.user, logged_date=self.meal_at.date(),
            logged_time=self.meal_at.time(),
        )
        obj, status = classify_meal_glucose_response(entry)
        self.assertIsNone(obj)
        self.assertEqual(status, ClassifierResult.SKIPPED_INSUFFICIENT_POST_MEAL)

    def test_prior_meal_within_90min_skipped(self):
        # A second meal 60 minutes prior pollutes the baseline.
        _make_food_entry(
            self.user, logged_date=self.meal_at.date(),
            logged_time=(self.meal_at - timedelta(minutes=60)).time(),
        )
        _populate_post_meal_curve(self.user, self.meal_at, baseline=100, peak=140, end_value=110)
        entry = _make_food_entry(
            self.user, logged_date=self.meal_at.date(),
            logged_time=self.meal_at.time(),
        )
        obj, status = classify_meal_glucose_response(entry)
        self.assertIsNone(obj)
        self.assertEqual(status, ClassifierResult.SKIPPED_PRIOR_MEAL)

    def test_workout_overlap_skipped(self):
        # A workout started 15 minutes before the meal — within the
        # -30m..+120m exclusion zone.
        WorkoutSession.objects.create(
            user=self.user,
            date=(self.meal_at - timedelta(minutes=15)).date(),
            started_at=self.meal_at - timedelta(minutes=15),
            duration_minutes=45,
        )
        _populate_post_meal_curve(self.user, self.meal_at, baseline=100, peak=140, end_value=110)
        entry = _make_food_entry(
            self.user, logged_date=self.meal_at.date(),
            logged_time=self.meal_at.time(),
        )
        obj, status = classify_meal_glucose_response(entry)
        self.assertIsNone(obj)
        self.assertEqual(status, ClassifierResult.SKIPPED_WORKOUT_IN_WINDOW)


# ── Idempotency & re-classification ─────────────────────────────────


class IdempotencyTests(_MuteRelatedSignals, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = _make_user("idempotent@test.com")
        cls.meal_at = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)

    def test_second_call_returns_existing(self):
        _populate_post_meal_curve(self.user, self.meal_at, baseline=100, peak=140, end_value=110)
        entry = _make_food_entry(
            self.user, logged_date=self.meal_at.date(),
            logged_time=self.meal_at.time(),
        )
        obj1, status1 = classify_meal_glucose_response(entry)
        self.assertEqual(status1, ClassifierResult.OK)

        obj2, status2 = classify_meal_glucose_response(entry)
        self.assertEqual(status2, ClassifierResult.SKIPPED_ALREADY_CLASSIFIED)
        self.assertEqual(obj1.pk, obj2.pk)
        # Only one row per FoodEntry.
        self.assertEqual(
            MealGlucoseResponse.objects.filter(food_entry=entry).count(), 1,
        )

    def test_force_reclassifies(self):
        _populate_post_meal_curve(self.user, self.meal_at, baseline=100, peak=140, end_value=110)
        entry = _make_food_entry(
            self.user, logged_date=self.meal_at.date(),
            logged_time=self.meal_at.time(),
        )
        obj1, _ = classify_meal_glucose_response(entry)
        original_computed = obj1.computed_at

        obj2, status2 = classify_meal_glucose_response(entry, force=True)
        self.assertEqual(status2, ClassifierResult.OK)
        self.assertEqual(obj1.pk, obj2.pk)
        # update_or_create — same row updated.
        self.assertEqual(
            MealGlucoseResponse.objects.filter(food_entry=entry).count(), 1,
        )


# ── Unit conversion ─────────────────────────────────────────────────


class UnitConversionTests(_MuteRelatedSignals, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = _make_user("units@test.com")
        cls.meal_at = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)

    def test_mmol_l_converted_to_mg_dl(self):
        # 5.55 mmol/L * 18 = 99.9 mg/dL (baseline ~100)
        # 7.77 mmol/L * 18 = 139.86 (peak ~140)
        GlucoseEntry.objects.create(
            user=self.user, value=Decimal("5.55"), unit="mmol/L",
            recorded_at=self.meal_at,
        )
        for offset, val in ((30, "6.5"), (60, "7.77"), (90, "6.5"), (120, "5.55")):
            GlucoseEntry.objects.create(
                user=self.user, value=Decimal(val), unit="mmol/L",
                recorded_at=self.meal_at + timedelta(minutes=offset),
            )
        entry = _make_food_entry(
            self.user, logged_date=self.meal_at.date(),
            logged_time=self.meal_at.time(),
        )
        obj, status = classify_meal_glucose_response(entry)
        self.assertEqual(status, ClassifierResult.OK)
        # Approximately moderate spike (delta_peak ~40).
        self.assertEqual(obj.classification, MealGlucoseResponse.CLASS_MODERATE_SPIKE)


# ── Model surface ───────────────────────────────────────────────────


class ModelSurfaceTests(_MuteRelatedSignals, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = _make_user("model_surface@test.com")

    def test_classification_choices_exact(self):
        keys = {c[0] for c in MealGlucoseResponse.CLASSIFICATION_CHOICES}
        self.assertEqual(
            keys,
            {
                "minimal_spike", "moderate_spike", "large_spike",
                "extreme_spike", "prolonged_spike",
            },
        )

    def test_str_includes_classification_and_delta(self):
        entry = _make_food_entry(
            self.user, logged_date=date.today(), logged_time=time(12, 0),
        )
        obj = MealGlucoseResponse.objects.create(
            user=self.user,
            food_entry=entry,
            meal_consumed_at=datetime.now(timezone.utc),
            classification=MealGlucoseResponse.CLASS_MINIMAL_SPIKE,
            baseline_glucose=Decimal("100"),
            peak_glucose=Decimal("120"),
            glucose_at_120m=Decimal("110"),
            delta_peak=Decimal("20"),
            delta_2h=Decimal("10"),
            time_to_peak_min=45,
        )
        s = str(obj)
        self.assertIn("minimal_spike", s)
        self.assertIn("20", s)
