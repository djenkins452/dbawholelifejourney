"""
Medication adherence chart drift regression tests (D2).

Before this fix the adherence view's daily chart performed its OWN
logs-only calculation:

    rate = round(day_taken / day_total * 100) if day_total > 0 else 100

…where ``day_total`` counted only LOGGED doses (not expected doses from
schedules) and defaulted to 100% on days with no logs. That silently
disagreed with the schedule-based headline.

The chart now consumes ``calculate_daily_medicine_adherence`` — the same
expected-dose enumeration and formula the headline uses. These tests prove:

1. Zero logged doses no longer displays 100%.
2. The daily chart equals the canonical per-day calculation.
3. The daily chart and the headline cannot disagree for the same day.
4. Expected-dose edge cases (PRN, multiple/day, weekly, future-today,
   day-of-week) all behave correctly.
5. The view wires the chart to the canonical utility.

Path: apps/health/tests/test_adherence_chart_drift.py
"""

from datetime import date, time, timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.health.medicine_utils import (
    calculate_daily_medicine_adherence,
    calculate_medicine_adherence,
)
from apps.health.models import Intake, IntakeLog, IntakeSchedule
from apps.users.models import TermsAcceptance

User = get_user_model()


class ChartDriftMixin:
    """Setup helpers mirroring test_medicine_adherence.AdherenceTestMixin."""

    def create_user(self, email="chartdrift@test.com"):
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
# 1. ZERO LOGGED DOSES NO LONGER 100%
# =============================================================================


class TestZeroDosesNotHundred(ChartDriftMixin, TestCase):
    def setUp(self):
        self.user = self.create_user()
        self.med = self.create_medicine(self.user)
        self.schedule = self.create_schedule(self.med)

    def test_no_logs_day_is_zero_not_hundred(self):
        """A day with expected doses but no logs must read 0%, never 100%."""
        start = date(2026, 2, 1)
        end = date(2026, 2, 7)
        daily = calculate_daily_medicine_adherence(self.user, start, end)
        self.assertEqual(len(daily), 7)
        for entry in daily:
            self.assertEqual(entry["expected_doses"], 1)
            self.assertEqual(entry["taken_doses"], 0)
            self.assertEqual(
                entry["adherence_rate"], 0,
                f"{entry['date']} showed {entry['adherence_rate']}%, expected 0%",
            )
            self.assertNotEqual(entry["adherence_rate"], 100)

    def test_no_expected_doses_day_is_none_not_hundred(self):
        """A day with NO scheduled doses reads None (no data), never 100%."""
        # Weekday-only med; evaluate a weekend day.
        self.schedule.days_of_week = "0,1,2,3,4"  # Mon–Fri
        self.schedule.save()
        saturday = date(2026, 2, 7)
        daily = calculate_daily_medicine_adherence(self.user, saturday, saturday)
        self.assertEqual(daily[0]["expected_doses"], 0)
        self.assertIsNone(daily[0]["adherence_rate"])


# =============================================================================
# 2 & 3. CHART == CANONICAL, CHART CANNOT DISAGREE WITH HEADLINE
# =============================================================================


class TestChartEqualsCanonical(ChartDriftMixin, TestCase):
    def setUp(self):
        self.user = self.create_user()
        self.med = self.create_medicine(self.user)
        self.schedule = self.create_schedule(self.med)

    def test_each_day_matches_single_day_canonical(self):
        """Every chart day equals calculate_medicine_adherence(user, day, day)."""
        start = date(2026, 2, 1)
        end = date(2026, 2, 7)
        # Mixed activity: taken, missed, skipped, unlogged.
        self.create_log(self.user, self.med, date(2026, 2, 1), "taken")
        self.create_log(self.user, self.med, date(2026, 2, 2), "missed")
        self.create_log(self.user, self.med, date(2026, 2, 3), "skipped")
        self.create_log(self.user, self.med, date(2026, 2, 4), "late")
        # 2/5, 2/6, 2/7 unlogged

        daily = calculate_daily_medicine_adherence(self.user, start, end)
        for entry in daily:
            day = date.fromisoformat(entry["date"])
            canonical = calculate_medicine_adherence(self.user, day, day)
            self.assertEqual(
                entry["adherence_rate"], canonical["adherence_rate"],
                f"Chart/headline disagree on {entry['date']}: "
                f"chart={entry['adherence_rate']} headline={canonical['adherence_rate']}",
            )
            self.assertEqual(entry["expected_doses"], canonical["expected_doses"])
            self.assertEqual(entry["taken_doses"], canonical["taken_doses"])

    def test_chart_and_headline_cannot_disagree_same_day(self):
        """Single-day period: chart entry == headline exactly."""
        day = date(2026, 2, 3)
        self.create_log(self.user, self.med, day, "taken")
        headline = calculate_medicine_adherence(self.user, day, day)
        daily = calculate_daily_medicine_adherence(self.user, day, day)
        self.assertEqual(len(daily), 1)
        self.assertEqual(daily[0]["adherence_rate"], headline["adherence_rate"])
        self.assertEqual(daily[0]["adherence_rate"], 100)  # 1/1


# =============================================================================
# 4. EXPECTED-DOSE EDGE CASES
# =============================================================================


class TestChartEdgeCases(ChartDriftMixin, TestCase):
    def setUp(self):
        self.user = self.create_user()

    def test_prn_medicine_has_no_expected_doses(self):
        """PRN (as-needed) meds have no schedule → 0 expected, rate None."""
        prn = self.create_medicine(self.user, name="PRN Pain", is_prn=True)
        # PRN: no schedule. A PRN dose was taken, but it must not create
        # expected doses nor a false 100%.
        self.create_log(
            self.user, prn, date(2026, 2, 3), "taken", is_prn_dose=True
        )
        daily = calculate_daily_medicine_adherence(
            self.user, date(2026, 2, 3), date(2026, 2, 3)
        )
        self.assertEqual(daily[0]["expected_doses"], 0)
        self.assertIsNone(daily[0]["adherence_rate"])

    def test_multiple_doses_per_day(self):
        """Twice-daily med: 2 expected/day; one taken → 50%."""
        med = self.create_medicine(self.user, name="Twice Daily")
        self.create_schedule(med, time(8, 0))
        self.create_schedule(med, time(20, 0))
        day = date(2026, 2, 3)
        self.create_log(self.user, med, day, "taken")  # only one of two

        daily = calculate_daily_medicine_adherence(self.user, day, day)
        self.assertEqual(daily[0]["expected_doses"], 2)
        self.assertEqual(daily[0]["taken_doses"], 1)
        self.assertEqual(daily[0]["adherence_rate"], 50)

    def test_weekly_medicine(self):
        """Weekly med (Mondays only): expected only on Mondays."""
        med = self.create_medicine(self.user, name="Weekly", frequency="weekly")
        self.create_schedule(med, days="0")  # Monday only
        # Mon 2026-02-02 .. Sun 2026-02-08
        daily = calculate_daily_medicine_adherence(
            self.user, date(2026, 2, 2), date(2026, 2, 8)
        )
        expected_per_day = {e["date"]: e["expected_doses"] for e in daily}
        self.assertEqual(expected_per_day["2026-02-02"], 1)  # Monday
        for iso in [
            "2026-02-03", "2026-02-04", "2026-02-05",
            "2026-02-06", "2026-02-07", "2026-02-08",
        ]:
            self.assertEqual(expected_per_day[iso], 0)
            # Non-scheduled days are None, not 100.
            entry = next(e for e in daily if e["date"] == iso)
            self.assertIsNone(entry["adherence_rate"])

    def test_day_of_week_schedule(self):
        """Mon/Wed/Fri schedule yields expected doses only on those days."""
        med = self.create_medicine(self.user, name="MWF")
        self.create_schedule(med, days="0,2,4")  # Mon, Wed, Fri
        daily = calculate_daily_medicine_adherence(
            self.user, date(2026, 2, 2), date(2026, 2, 8)
        )
        expected = {e["date"]: e["expected_doses"] for e in daily}
        self.assertEqual(expected["2026-02-02"], 1)  # Mon
        self.assertEqual(expected["2026-02-03"], 0)  # Tue
        self.assertEqual(expected["2026-02-04"], 1)  # Wed
        self.assertEqual(expected["2026-02-06"], 1)  # Fri
        self.assertEqual(expected["2026-02-07"], 0)  # Sat

    def test_future_doses_today_excluded(self):
        """Today's not-yet-due doses are excluded from expected (fairness)."""
        med = self.create_medicine(self.user, name="Future Dose")
        self.create_schedule(med, time(8, 0))   # already due
        self.create_schedule(med, time(23, 0))  # not yet due at 10:00

        fake_today = date(2026, 2, 3)  # a Tuesday
        with patch(
            "apps.core.utils.get_user_today", return_value=fake_today
        ), patch("apps.core.utils.get_user_now") as mock_now:
            # 10:00 local — 08:00 dose due, 23:00 dose not yet.
            mock_now.return_value = type(
                "DT", (), {"time": staticmethod(lambda: time(10, 0))}
            )()
            daily = calculate_daily_medicine_adherence(
                self.user, fake_today, fake_today
            )
        # Only the 08:00 dose is due → expected 1, not 2.
        self.assertEqual(daily[0]["expected_doses"], 1)


# =============================================================================
# 5. VIEW WIRES CHART TO CANONICAL UTILITY
# =============================================================================


class TestAdherenceViewChartConsistent(ChartDriftMixin, TestCase):
    def setUp(self):
        self.user = self.create_user()
        self.med = self.create_medicine(self.user, name="View Chart Med")
        self.schedule = self.create_schedule(self.med)
        from django.test import Client
        self.client = Client()
        self.client.login(email="chartdrift@test.com", password="testpass123")

    def test_view_daily_data_never_100_with_no_logs(self):
        """The rendered chart context must not show 100% for unlogged days."""
        response = self.client.get(reverse("health:intake_adherence"))
        self.assertEqual(response.status_code, 200)
        daily_data = response.context["daily_data"]
        self.assertTrue(daily_data)
        for entry in daily_data:
            # No logs created → every day with expected doses is 0%, none 100%.
            if entry["total"] > 0:
                self.assertEqual(
                    entry["rate"], 0,
                    f"{entry['date']} rendered {entry['rate']}% with no logs",
                )

    def test_view_chart_matches_headline_for_each_day(self):
        """Each rendered chart day agrees with the canonical per-day calc."""
        from apps.core.utils import get_user_today

        today = get_user_today(self.user)
        # Log one dose today.
        self.create_log(self.user, self.med, today, "taken")

        response = self.client.get(reverse("health:intake_adherence"))
        daily_data = response.context["daily_data"]
        for entry in daily_data:
            day = date.fromisoformat(entry["date"])
            canonical = calculate_medicine_adherence(self.user, day, day)
            expected_rate = (
                canonical["adherence_rate"]
                if canonical["adherence_rate"] is not None
                else 0
            )
            self.assertEqual(
                entry["rate"], expected_rate,
                f"View chart {entry['date']} = {entry['rate']}% but canonical "
                f"= {expected_rate}%",
            )
