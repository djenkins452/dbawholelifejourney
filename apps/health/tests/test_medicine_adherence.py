"""
Medicine Adherence Calculation Tests

Tests for apps.health.medicine_utils — the correct adherence calculation
that counts expected doses from schedules rather than just taken/missed logs.

This was created to fix a critical bug where adherence showed 100% even when
a user only logged 2 of 20 expected doses (because unlogged doses weren't counted).
"""

from datetime import date, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.health.medicine_utils import (
    calculate_medicine_adherence,
    calculate_medicine_adherence_rate,
)
from apps.health.models import Intake, IntakeLog, IntakeSchedule
from apps.users.models import TermsAcceptance

User = get_user_model()


class AdherenceTestMixin:
    """Common setup for adherence tests."""

    def create_user(self, email="adherence@test.com"):
        user = User.objects.create_user(email=email, password="testpass123")
        TermsAcceptance.objects.create(
            user=user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        user.preferences.has_completed_onboarding = True
        user.preferences.save()
        return user

    def create_medicine(self, user, name="Test Med", **kwargs):
        defaults = {
            "user": user,
            "name": name,
            "dose": "10mg",
            "frequency": "daily",
            "start_date": date(2026, 1, 1),
            "intake_status": Intake.STATUS_ACTIVE,
        }
        defaults.update(kwargs)
        return Intake.objects.create(**defaults)

    def create_schedule(self, medicine, scheduled_time=None, days="0,1,2,3,4,5,6", **kwargs):
        if scheduled_time is None:
            scheduled_time = time(8, 0)
        return IntakeSchedule.objects.create(
            intake=medicine,
            scheduled_time=scheduled_time,
            days_of_week=days,
            is_active=True,
            **kwargs,
        )

    def create_log(self, user, medicine, scheduled_date, status="taken", **kwargs):
        return IntakeLog.objects.create(
            user=user,
            intake=medicine,
            scheduled_date=scheduled_date,
            log_status=status,
            **kwargs,
        )


# =============================================================================
# CORE ADHERENCE CALCULATION
# =============================================================================


class TestAdherenceNoMedicines(AdherenceTestMixin, TestCase):
    """When user has no active medicines."""

    def setUp(self):
        self.user = self.create_user()

    def test_no_medicines_returns_none_rate(self):
        result = calculate_medicine_adherence(
            self.user, date(2026, 2, 1), date(2026, 2, 7)
        )
        self.assertEqual(result["expected_doses"], 0)
        self.assertEqual(result["taken_doses"], 0)
        self.assertIsNone(result["adherence_rate"])


class TestAdherenceNoSchedules(AdherenceTestMixin, TestCase):
    """Active medicine but no active schedules."""

    def setUp(self):
        self.user = self.create_user()
        self.med = self.create_medicine(self.user)
        # No schedules created

    def test_no_schedules_returns_none_rate(self):
        result = calculate_medicine_adherence(
            self.user, date(2026, 2, 1), date(2026, 2, 7)
        )
        self.assertEqual(result["expected_doses"], 0)
        self.assertIsNone(result["adherence_rate"])


class TestAdherencePerfect(AdherenceTestMixin, TestCase):
    """User takes every scheduled dose."""

    def setUp(self):
        self.user = self.create_user()
        self.med = self.create_medicine(self.user)
        # Daily schedule, every day
        self.schedule = self.create_schedule(self.med)

    def test_100_percent_when_all_taken(self):
        # 7 days = 7 expected doses, log all as taken
        start = date(2026, 2, 1)  # Sunday
        for i in range(7):
            day = start + timedelta(days=i)
            self.create_log(self.user, self.med, day, "taken")

        result = calculate_medicine_adherence(self.user, start, start + timedelta(days=6))
        self.assertEqual(result["expected_doses"], 7)
        self.assertEqual(result["taken_doses"], 7)
        self.assertEqual(result["missed_doses"], 0)
        self.assertEqual(result["unlogged_doses"], 0)
        self.assertEqual(result["adherence_rate"], 100)


class TestAdherencePartialLogging(AdherenceTestMixin, TestCase):
    """THE CRITICAL BUG CASE: User only logs some doses, rest are unlogged."""

    def setUp(self):
        self.user = self.create_user()
        self.med = self.create_medicine(self.user)
        self.schedule = self.create_schedule(self.med)

    def test_unlogged_doses_count_against_adherence(self):
        """
        If 7 doses expected but only 2 logged as taken and 5 never logged,
        adherence must be 2/7 = 29%, NOT 2/2 = 100%.
        This was the original bug.
        """
        start = date(2026, 2, 1)
        # Only log 2 of 7 days
        self.create_log(self.user, self.med, start, "taken")
        self.create_log(self.user, self.med, start + timedelta(days=1), "taken")

        result = calculate_medicine_adherence(self.user, start, start + timedelta(days=6))
        self.assertEqual(result["expected_doses"], 7)
        self.assertEqual(result["taken_doses"], 2)
        self.assertEqual(result["unlogged_doses"], 5)
        self.assertEqual(result["adherence_rate"], 29)  # 2/7 = 28.57 rounds to 29

    def test_single_taken_out_of_many_expected(self):
        """1 taken out of 7 expected = 14%, not 100%."""
        start = date(2026, 2, 1)
        self.create_log(self.user, self.med, start, "taken")

        result = calculate_medicine_adherence(self.user, start, start + timedelta(days=6))
        self.assertEqual(result["expected_doses"], 7)
        self.assertEqual(result["taken_doses"], 1)
        self.assertEqual(result["adherence_rate"], 14)  # 1/7 = 14.28 rounds to 14

    def test_zero_logs_means_zero_adherence(self):
        """No logs at all = 0% adherence, not None."""
        start = date(2026, 2, 1)
        result = calculate_medicine_adherence(self.user, start, start + timedelta(days=6))
        self.assertEqual(result["expected_doses"], 7)
        self.assertEqual(result["taken_doses"], 0)
        self.assertEqual(result["unlogged_doses"], 7)
        self.assertEqual(result["adherence_rate"], 0)


class TestAdherenceMissedDoses(AdherenceTestMixin, TestCase):
    """Explicitly missed doses."""

    def setUp(self):
        self.user = self.create_user()
        self.med = self.create_medicine(self.user)
        self.schedule = self.create_schedule(self.med)

    def test_mix_of_taken_and_missed(self):
        """3 taken + 2 missed + 2 unlogged out of 7 expected."""
        start = date(2026, 2, 1)
        self.create_log(self.user, self.med, start, "taken")
        self.create_log(self.user, self.med, start + timedelta(days=1), "taken")
        self.create_log(self.user, self.med, start + timedelta(days=2), "taken")
        self.create_log(self.user, self.med, start + timedelta(days=3), "missed")
        self.create_log(self.user, self.med, start + timedelta(days=4), "missed")
        # Days 5 and 6 unlogged

        result = calculate_medicine_adherence(self.user, start, start + timedelta(days=6))
        self.assertEqual(result["expected_doses"], 7)
        self.assertEqual(result["taken_doses"], 3)
        self.assertEqual(result["missed_doses"], 2)
        self.assertEqual(result["unlogged_doses"], 2)
        self.assertEqual(result["adherence_rate"], 43)  # 3/7 = 42.85 rounds to 43


class TestAdherenceSkippedDoses(AdherenceTestMixin, TestCase):
    """Skipped doses are excluded from the denominator."""

    def setUp(self):
        self.user = self.create_user()
        self.med = self.create_medicine(self.user)
        self.schedule = self.create_schedule(self.med)

    def test_skipped_excluded_from_denominator(self):
        """
        7 expected, 2 taken, 2 skipped, 3 unlogged.
        Effective expected = 7 - 2 = 5. Adherence = 2/5 = 40%.
        """
        start = date(2026, 2, 1)
        self.create_log(self.user, self.med, start, "taken")
        self.create_log(self.user, self.med, start + timedelta(days=1), "taken")
        self.create_log(self.user, self.med, start + timedelta(days=2), "skipped")
        self.create_log(self.user, self.med, start + timedelta(days=3), "skipped")
        # Days 4, 5, 6 unlogged

        result = calculate_medicine_adherence(self.user, start, start + timedelta(days=6))
        self.assertEqual(result["expected_doses"], 7)
        self.assertEqual(result["taken_doses"], 2)
        self.assertEqual(result["unlogged_doses"], 3)
        self.assertEqual(result["adherence_rate"], 40)  # 2/5 = 40

    def test_all_skipped_returns_none(self):
        """If all expected doses are skipped, effective expected = 0 → None."""
        start = date(2026, 2, 7)  # Just one day (Saturday)
        self.create_log(self.user, self.med, start, "skipped")

        result = calculate_medicine_adherence(self.user, start, start)
        self.assertEqual(result["expected_doses"], 1)
        self.assertIsNone(result["adherence_rate"])


class TestAdherenceLateDoses(AdherenceTestMixin, TestCase):
    """Late doses count as taken."""

    def setUp(self):
        self.user = self.create_user()
        self.med = self.create_medicine(self.user)
        self.schedule = self.create_schedule(self.med)

    def test_late_counted_as_taken(self):
        start = date(2026, 2, 1)
        self.create_log(self.user, self.med, start, "late")
        self.create_log(self.user, self.med, start + timedelta(days=1), "late")

        result = calculate_medicine_adherence(self.user, start, start + timedelta(days=6))
        self.assertEqual(result["taken_doses"], 2)
        self.assertEqual(result["adherence_rate"], 29)  # 2/7


# =============================================================================
# MULTI-SCHEDULE AND MULTI-MEDICINE
# =============================================================================


class TestAdherenceMultipleSchedules(AdherenceTestMixin, TestCase):
    """Medicine with multiple daily doses."""

    def setUp(self):
        self.user = self.create_user()
        self.med = self.create_medicine(self.user)
        # Twice daily
        self.schedule_am = self.create_schedule(self.med, time(8, 0))
        self.schedule_pm = self.create_schedule(self.med, time(20, 0))

    def test_twice_daily_expected(self):
        """7 days × 2 doses/day = 14 expected."""
        start = date(2026, 2, 1)
        result = calculate_medicine_adherence(self.user, start, start + timedelta(days=6))
        self.assertEqual(result["expected_doses"], 14)

    def test_twice_daily_half_taken(self):
        """Take only morning doses for 7 days = 7/14 = 50%."""
        start = date(2026, 2, 1)
        for i in range(7):
            self.create_log(self.user, self.med, start + timedelta(days=i), "taken")

        result = calculate_medicine_adherence(self.user, start, start + timedelta(days=6))
        self.assertEqual(result["expected_doses"], 14)
        self.assertEqual(result["taken_doses"], 7)
        self.assertEqual(result["adherence_rate"], 50)


class TestAdherenceMultipleMedicines(AdherenceTestMixin, TestCase):
    """Multiple active medicines."""

    def setUp(self):
        self.user = self.create_user()
        self.med1 = self.create_medicine(self.user, name="Med A")
        self.med2 = self.create_medicine(self.user, name="Med B")
        self.schedule1 = self.create_schedule(self.med1)
        self.schedule2 = self.create_schedule(self.med2)

    def test_two_medicines_doubles_expected(self):
        """7 days × 2 medicines = 14 expected."""
        start = date(2026, 2, 1)
        result = calculate_medicine_adherence(self.user, start, start + timedelta(days=6))
        self.assertEqual(result["expected_doses"], 14)

    def test_only_one_medicine_taken(self):
        """Take only Med A all week = 7/14 = 50%."""
        start = date(2026, 2, 1)
        for i in range(7):
            self.create_log(self.user, self.med1, start + timedelta(days=i), "taken")

        result = calculate_medicine_adherence(self.user, start, start + timedelta(days=6))
        self.assertEqual(result["taken_doses"], 7)
        self.assertEqual(result["adherence_rate"], 50)


# =============================================================================
# DAY-OF-WEEK SCHEDULES
# =============================================================================


class TestAdherenceWeekdayOnly(AdherenceTestMixin, TestCase):
    """Schedules that don't apply every day."""

    def setUp(self):
        self.user = self.create_user()
        self.med = self.create_medicine(self.user)
        # Monday through Friday only (0,1,2,3,4)
        self.schedule = self.create_schedule(self.med, days="0,1,2,3,4")

    def test_weekday_only_schedule(self):
        """Mon Feb 2 to Sun Feb 8, 2026 = Mon-Fri = 5 expected."""
        start = date(2026, 2, 2)  # Monday
        end = date(2026, 2, 8)    # Sunday
        result = calculate_medicine_adherence(self.user, start, end)
        self.assertEqual(result["expected_doses"], 5)

    def test_weekend_days_dont_count(self):
        """Only Saturday-Sunday range with weekday-only schedule = 0 expected."""
        start = date(2026, 2, 7)  # Saturday
        end = date(2026, 2, 8)    # Sunday
        result = calculate_medicine_adherence(self.user, start, end)
        self.assertEqual(result["expected_doses"], 0)
        self.assertIsNone(result["adherence_rate"])


# =============================================================================
# INACTIVE SCHEDULES AND MEDICINES
# =============================================================================


class TestAdherenceInactiveIntake(AdherenceTestMixin, TestCase):
    """Only active medicines count."""

    def setUp(self):
        self.user = self.create_user()
        self.active_med = self.create_medicine(self.user, name="Active Med")
        self.paused_med = self.create_medicine(
            self.user, name="Paused Med",
            intake_status=Intake.STATUS_PAUSED,
        )
        self.create_schedule(self.active_med)
        self.create_schedule(self.paused_med)

    def test_paused_medicine_excluded(self):
        start = date(2026, 2, 1)
        result = calculate_medicine_adherence(self.user, start, start + timedelta(days=6))
        # Only active medicine counts: 7 expected, not 14
        self.assertEqual(result["expected_doses"], 7)


class TestAdherenceInactiveSchedule(AdherenceTestMixin, TestCase):
    """Only active schedules count."""

    def setUp(self):
        self.user = self.create_user()
        self.med = self.create_medicine(self.user)
        self.active_schedule = self.create_schedule(self.med, time(8, 0))
        self.inactive_schedule = IntakeSchedule.objects.create(
            intake=self.med,
            scheduled_time=time(20, 0),
            days_of_week="0,1,2,3,4,5,6",
            is_active=False,
        )

    def test_inactive_schedule_excluded(self):
        start = date(2026, 2, 1)
        result = calculate_medicine_adherence(self.user, start, start + timedelta(days=6))
        # Only active schedule counts: 7 expected, not 14
        self.assertEqual(result["expected_doses"], 7)


# =============================================================================
# CONVENIENCE WRAPPER
# =============================================================================


class TestAdherenceRateWrapper(AdherenceTestMixin, TestCase):
    """Tests for calculate_medicine_adherence_rate() convenience function."""

    def setUp(self):
        self.user = self.create_user()
        self.med = self.create_medicine(self.user)
        self.schedule = self.create_schedule(self.med)

    def test_returns_rate_only(self):
        """Should return just the integer rate, not the full dict."""
        result = calculate_medicine_adherence_rate(self.user, days=7)
        # No logs, all expected → 0%
        self.assertIsInstance(result, int)
        self.assertEqual(result, 0)

    def test_returns_none_when_no_expected(self):
        """No active medicines → None."""
        self.med.intake_status = Intake.STATUS_COMPLETED
        self.med.save()
        result = calculate_medicine_adherence_rate(self.user, days=7)
        self.assertIsNone(result)


# =============================================================================
# EDGE CASES
# =============================================================================


class TestAdherenceEdgeCases(AdherenceTestMixin, TestCase):
    """Edge cases and boundary conditions."""

    def setUp(self):
        self.user = self.create_user()

    def test_single_day_range(self):
        """Start date = end date = single day."""
        med = self.create_medicine(self.user)
        self.create_schedule(med)
        day = date(2026, 2, 3)  # Tuesday
        self.create_log(self.user, med, day, "taken")

        result = calculate_medicine_adherence(self.user, day, day)
        self.assertEqual(result["expected_doses"], 1)
        self.assertEqual(result["taken_doses"], 1)
        self.assertEqual(result["adherence_rate"], 100)

    def test_data_isolation_between_users(self):
        """One user's logs don't affect another user's adherence."""
        user_a = self.create_user("usera@test.com")
        user_b = self.create_user("userb@test.com")

        med_a = self.create_medicine(user_a, name="Med A")
        med_b = self.create_medicine(user_b, name="Med B")
        self.create_schedule(med_a)
        self.create_schedule(med_b)

        start = date(2026, 2, 1)
        # User A takes all 7 doses
        for i in range(7):
            self.create_log(user_a, med_a, start + timedelta(days=i), "taken")
        # User B takes nothing

        result_a = calculate_medicine_adherence(user_a, start, start + timedelta(days=6))
        result_b = calculate_medicine_adherence(user_b, start, start + timedelta(days=6))

        self.assertEqual(result_a["adherence_rate"], 100)
        self.assertEqual(result_b["adherence_rate"], 0)

    def test_unlogged_count_not_negative(self):
        """Even with extra logs, unlogged shouldn't go negative."""
        med = self.create_medicine(self.user)
        self.create_schedule(med)
        day = date(2026, 2, 3)

        # Log more than expected (e.g., duplicate log + missed for same day)
        self.create_log(self.user, med, day, "taken")
        self.create_log(self.user, med, day, "missed")

        result = calculate_medicine_adherence(self.user, day, day)
        self.assertEqual(result["expected_doses"], 1)
        self.assertGreaterEqual(result["unlogged_doses"], 0)


# =============================================================================
# VIEW CONSISTENCY TESTS
# =============================================================================


class TestViewsUseMedicineUtils(AdherenceTestMixin, TestCase):
    """
    Verify that health views use medicine_utils for adherence, not their own
    logs-only calculation. This prevents the critical bug where unlogged doses
    are invisible (showing 100% when real adherence is 20%).
    """

    def setUp(self):
        self.user = self.create_user()
        self.client = self._get_logged_in_client()
        self.med = self.create_medicine(self.user, name="Consistency Test Med")
        self.schedule = self.create_schedule(self.med)

    def _get_logged_in_client(self):
        from django.test import Client
        client = Client()
        client.login(email="adherence@test.com", password="testpass123")
        return client

    def test_medicine_detail_uses_schedule_based_adherence(self):
        """
        MedicineDetailView must show schedule-based adherence.
        If 7 doses expected but only 1 logged as taken, adherence should be ~14%,
        NOT 100%.
        """
        from django.urls import reverse
        from apps.core.utils import get_user_today

        today = get_user_today(self.user)

        # Only log 1 of 7 expected doses as taken
        self.create_log(self.user, self.med, today, "taken")

        response = self.client.get(
            reverse("health:intake_detail", kwargs={"pk": self.med.pk}),
        )
        self.assertEqual(response.status_code, 200)
        # week_adherence must be <= 20% (1 of ~7 expected), NOT 100%
        week_adherence = response.context.get("week_adherence", 0)
        self.assertLessEqual(
            week_adherence, 20,
            f"Adherence should be ~14% (1/7 expected) but got {week_adherence}%. "
            f"View may be using logs-only denominator instead of medicine_utils."
        )

    def test_adherence_view_uses_schedule_based_adherence(self):
        """
        MedicineAdherenceView must show schedule-based adherence.
        """
        from django.urls import reverse
        from apps.core.utils import get_user_today

        today = get_user_today(self.user)

        # Only log 1 of 7 expected doses
        self.create_log(self.user, self.med, today, "taken")

        response = self.client.get(reverse("health:intake_adherence"))
        self.assertEqual(response.status_code, 200)
        adherence_rate = response.context.get("adherence_rate", 0)
        self.assertLessEqual(
            adherence_rate, 20,
            f"Adherence should be ~14% (1/7) but got {adherence_rate}%. "
            f"View may be using logs-only denominator instead of medicine_utils."
        )
