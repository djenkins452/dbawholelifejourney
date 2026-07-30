# ==============================================================================
# File: apps/ai/tests/test_health_question_certification.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Health QUESTION Certification — proves real customer questions across
#   the previously-uncertified metrics (heart rate, water, SpO2, temperature, blood
#   pressure) are now answerable from deterministic truth via the reusable spine, and
#   the blind overview pages now expose Current Context.
# ==============================================================================
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.ai.cos_services.domain_history import get_domain_history
from apps.ai.cos_services.domain_readings import get_domain_readings
from apps.ai.cos_services.domain_analysis import get_domain_analysis
from apps.ai.cos_services.domain_adherence import get_domain_adherence
from apps.core.current_context import resolve_current_context

User = get_user_model()


def _today(user):
    from apps.core.utils import get_user_today
    return get_user_today(user)


class HeartRateQuestionTests(TestCase):
    """"Has my resting heart rate improved / what's my trend?" """
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="hr@test.com", password="x")
        from apps.health.models import HeartRateEntry
        now = timezone.now()
        # resting HR trending DOWN 62→56 over 12 days (improving baseline)
        for i in range(12):
            HeartRateEntry.objects.create(
                user=cls.user, bpm=62 - i // 2, context="resting",
                recorded_at=now - timedelta(days=11 - i))

    def test_resting_hr_history_and_trend(self):
        r = get_domain_history(self.user, "health", "resting_heart_rate",
                               period="last_7_days")
        self.assertEqual(r["status"], "ready")
        self.assertIsNotNone(r["change"])
        self.assertEqual(r["change"]["direction"], "falling")  # improving baseline
        self.assertEqual(r["unit"], "bpm")

    def test_hr_is_analyzable(self):
        r = get_domain_analysis(self.user, "health", "heart_rate")
        self.assertIn(r["status"], ("ready",))

    def test_hr_intra_day_readings(self):
        r = get_domain_readings(self.user, "health", "heart_rate", window="past 24 hours")
        self.assertIn(r["status"], ("ready", "empty"))  # window depends on wall-clock


class WaterQuestionTests(TestCase):
    """"Am I drinking enough water?" — adherence vs the 64 oz target."""
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="water@test.com", password="x")
        from apps.health.models import WaterEntry
        today = _today(cls.user)
        for i in range(7):
            WaterEntry.objects.create(user=cls.user, amount=Decimal("48"), unit="oz",
                                      logged_date=today - timedelta(days=i))

    def test_water_history(self):
        r = get_domain_history(self.user, "health", "water", period="last_7_days")
        self.assertEqual(r["status"], "ready")
        self.assertEqual(r["unit"], "oz")

    def test_water_adherence_answers_enough(self):
        r = get_domain_adherence(self.user, "health", "water", period="last_7_days")
        self.assertEqual(r["status"], "ready")
        self.assertEqual(r["target"]["value"], 64.0)
        self.assertEqual(r["actual"]["avg_daily"], 48.0)   # under target
        self.assertEqual(r["variance"]["pct_of_target"], 75.0)


class SpO2AndTemperatureQuestionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="vit@test.com", password="x")
        from apps.health.models import BloodOxygenEntry, BodyTemperatureEntry
        now = timezone.now()
        for i in range(8):
            BloodOxygenEntry.objects.create(user=cls.user, spo2=97,
                                            recorded_at=now - timedelta(days=i))
            BodyTemperatureEntry.objects.create(user=cls.user,
                                                temperature=Decimal("98.6"), unit="fahrenheit",
                                                recorded_at=now - timedelta(days=i))

    def test_spo2_history_and_analysis(self):
        self.assertEqual(get_domain_history(self.user, "health", "spo2",
                                            period="last_7_days")["status"], "ready")
        self.assertIn(get_domain_analysis(self.user, "health", "spo2")["status"],
                      ("ready",))

    def test_temperature_history(self):
        r = get_domain_history(self.user, "health", "body_temperature",
                               period="last_7_days")
        self.assertEqual(r["status"], "ready")
        self.assertEqual(r["unit"], "°F")


class BloodPressureTimeOfDayTests(TestCase):
    """"What time of day is my blood pressure highest?" — hour-of-day distribution."""
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="bptod@test.com", password="x")
        from apps.health.models import BloodPressureEntry
        now = timezone.now()
        base = now.replace(hour=0, minute=0, second=0, microsecond=0)
        # morning ~118, evening ~145 across the last 3 days → peak hour = 18
        for d in range(3):
            day = base - timedelta(days=d)
            BloodPressureEntry.objects.create(user=cls.user, systolic=118, diastolic=76,
                                              recorded_at=day + timedelta(hours=8))
            BloodPressureEntry.objects.create(user=cls.user, systolic=145, diastolic=90,
                                              recorded_at=day + timedelta(hours=18))

    def test_bp_reading_window_has_hour_distribution(self):
        # explicit 4-day window so it's independent of wall-clock
        now = timezone.now()
        r = get_domain_readings(
            self.user, "health", "blood_pressure",
            start=(now - timedelta(days=4)).isoformat(), end=now.isoformat())
        self.assertEqual(r["status"], "ready")
        self.assertIsNotNone(r["by_hour"])
        self.assertEqual(r["by_hour"]["peak_hour"], 18)
        self.assertEqual(r["by_hour"]["lowest_hour"], 8)


class BlindPageCurrentContextTests(TestCase):
    """The previously-blind overview pages now resolve Current Context."""
    def setUp(self):
        self.user = User.objects.create_user(email="cc@test.com", password="pw12345!")
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(
            user=self.user, terms_version=settings.WLJ_SETTINGS["TERMS_VERSION"])
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()
        from apps.health.models import (HeartRateEntry, WaterEntry, StepsEntry,
                                        BloodPressureEntry, SleepEntry)
        now = timezone.now()
        today = _today(self.user)
        for i in range(3):
            HeartRateEntry.objects.create(user=self.user, bpm=58, context="resting",
                                          recorded_at=now - timedelta(days=i))
            WaterEntry.objects.create(user=self.user, amount=Decimal("50"), unit="oz",
                                      logged_date=today - timedelta(days=i))
            StepsEntry.objects.create(user=self.user, count=8000, goal=10000,
                                      logged_date=today - timedelta(days=i),
                                      recorded_at=now - timedelta(days=i))
            BloodPressureEntry.objects.create(user=self.user, systolic=122, diastolic=80,
                                              recorded_at=now - timedelta(days=i))
            SleepEntry.objects.create(
                user=self.user, sleep_date=today - timedelta(days=i),
                bedtime=now - timedelta(days=i, hours=8), wake_time=now - timedelta(days=i),
                total_duration_minutes=440, asleep_duration_minutes=420)

    def test_all_blind_pages_now_resolve_current_context(self):
        for ref, token in (("summary:health.heart_rate", "Heart Rate"),
                           ("summary:health.water", "Water"),
                           ("summary:health.steps", "Steps"),
                           ("summary:health.blood_pressure", "Blood Pressure"),
                           ("summary:health.sleep", "Sleep")):
            summ = resolve_current_context(self.user, ref=ref)
            self.assertIsNotNone(summ, ref)
            self.assertIn(token, summ["content"], ref)

    def test_water_page_shows_target(self):
        summ = resolve_current_context(self.user, ref="summary:health.water")
        self.assertIn("Target", summ["content"])
