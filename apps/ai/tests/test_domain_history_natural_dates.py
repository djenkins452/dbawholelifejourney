# ==============================================================================
# File: apps/ai/tests/test_domain_history_natural_dates.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: NATURAL DATE AUTHORITY — get_history resolves the user's natural
#   date expression in WLJ (shared temporal authority, user timezone), so the model
#   can never fabricate the calendar YEAR. Regression for the production defect
#   "What did I weigh on July 4?" → model sent 2023-07-04 → false "no data".
# ==============================================================================
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.ai.cos_services.domain_history import get_domain_history
from apps.core.truth.periods import resolve_date_expression
from apps.core.utils import get_user_today

User = get_user_model()


def _weigh(user, d, value):
    from apps.health.models import WeightEntry
    from datetime import datetime, time
    return WeightEntry.objects.create(
        user=user, value=Decimal(str(value)), unit="lb", status="active",
        recorded_at=timezone.make_aware(datetime.combine(d, time(7, 0))),
    )


def _expected_july_4(today):
    """The occurrence a year-less 'July 4' must mean: this year if it has already
    happened, otherwise last year. Never a year the model invented."""
    d = date(today.year, 7, 4)
    return d if d <= today else date(today.year - 1, 7, 4)


class HistoryNaturalDateTests(TestCase):
    """WLJ — not the model — owns calendar resolution for get_history."""

    def setUp(self):
        self.user = User.objects.create_user(email="natdate@test.com", password="x")
        self.today = get_user_today(self.user)
        self.july4 = _expected_july_4(self.today)
        _weigh(self.user, self.july4, "178.0")
        _weigh(self.user, self.today - timedelta(days=1), "175.0")

    # ---- the canonical production defect ----
    def test_bare_july_4_resolves_to_the_right_occurrence(self):
        r = get_domain_history(self.user, "health", "weight", period="July 4")
        self.assertEqual(r["status"], "ready", r)
        self.assertEqual(r["start"], self.july4.isoformat())
        self.assertEqual(r["end"], self.july4.isoformat())
        self.assertEqual(r["points"][0]["value"], 178.0)

    def test_model_cannot_fabricate_the_year(self):
        """The natural expression must NEVER resolve to an arbitrary past year (the
        model previously emitted 2023-07-04). Resolution is anchored to user-today."""
        r = get_domain_history(self.user, "health", "weight", period="July 4")
        self.assertEqual(r["status"], "ready")
        resolved_year = date.fromisoformat(r["start"]).year
        self.assertIn(resolved_year, (self.today.year, self.today.year - 1))
        self.assertNotEqual(resolved_year, 2023)

    def test_explicit_year_is_honored_not_overridden(self):
        target = date(2025, 7, 4)
        _weigh(self.user, target, "190.0")
        r = get_domain_history(self.user, "health", "weight", period="July 4, 2025")
        self.assertEqual(r["status"], "ready", r)
        self.assertEqual(r["start"], target.isoformat())
        self.assertEqual(r["points"][0]["value"], 190.0)

    # ---- the other natural forms the model will emit ----
    def test_yesterday_phrase(self):
        r = get_domain_history(self.user, "health", "weight", period="yesterday")
        self.assertEqual(r["status"], "ready", r)
        self.assertEqual(r["start"], (self.today - timedelta(days=1)).isoformat())
        self.assertEqual(r["points"][0]["value"], 175.0)

    def test_last_weekday_phrase_resolves_to_a_past_day(self):
        r = get_domain_history(self.user, "health", "weight", period="last Monday")
        self.assertIn(r["status"], ("ready", "empty"), r)
        start = date.fromisoformat(r["start"])
        self.assertLess(start, self.today)
        self.assertEqual(start.weekday(), 0)

    def test_relative_offset_phrase(self):
        r = get_domain_history(self.user, "health", "weight", period="two weeks ago")
        self.assertIn(r["status"], ("ready", "empty"), r)
        self.assertEqual(r["start"], (self.today - timedelta(days=14)).isoformat())

    # ---- backward compatibility: existing ISO callers are untouched ----
    def test_explicit_iso_custom_range_still_works(self):
        r = get_domain_history(self.user, "health", "weight", period="custom",
                               start=self.july4.isoformat(), end=self.july4.isoformat())
        self.assertEqual(r["status"], "ready", r)
        self.assertEqual(r["points"][0]["value"], 178.0)

    def test_named_window_still_works(self):
        r = get_domain_history(self.user, "health", "weight", period="last_7_days")
        self.assertEqual(r["status"], "ready", r)

    def test_natural_phrase_in_start_arg(self):
        r = get_domain_history(self.user, "health", "weight", start="July 4")
        self.assertEqual(r["status"], "ready", r)
        self.assertEqual(r["start"], self.july4.isoformat())

    # ---- honest rejection: never a fabricated date ----
    def test_unparseable_phrase_is_honestly_unsupported(self):
        r = get_domain_history(self.user, "health", "weight", period="sometime-ish")
        self.assertEqual(r["status"], "unsupported")
        self.assertIn("valid_periods", r)
        self.assertNotIn("points", r)

    # ---- timezone: resolution is anchored to the USER's local today ----
    def test_resolution_uses_user_timezone_today(self):
        prefs = self.user.preferences
        prefs.timezone = "Pacific/Kiritimati"           # UTC+14 (writable field;
        prefs.save()                                    # `timezone_iana` is a property)
        user_today = get_user_today(self.user)
        r = get_domain_history(self.user, "health", "weight", period="today")
        self.assertEqual(r.get("start", user_today.isoformat()),
                         user_today.isoformat())
        # the shared authority resolves against that same local today
        self.assertEqual(resolve_date_expression("today", user_today).start, user_today)


class SharedResolverOffsetTests(TestCase):
    """The relative-offset forms are added to the ONE shared temporal authority, so
    get_entity and get_history resolve them identically."""

    def setUp(self):
        self.today = date(2026, 7, 21)

    def test_word_and_numeric_offsets(self):
        for phrase, expected in (
            ("two weeks ago", self.today - timedelta(days=14)),
            ("3 days ago", self.today - timedelta(days=3)),
            ("a week ago", self.today - timedelta(days=7)),
        ):
            p = resolve_date_expression(phrase, self.today)
            self.assertIsNotNone(p, phrase)
            self.assertEqual(p.start, expected, phrase)
            self.assertEqual(p.start, p.end)

    def test_month_and_year_offsets(self):
        self.assertEqual(resolve_date_expression("2 months ago", self.today).start,
                         date(2026, 5, 21))
        self.assertEqual(resolve_date_expression("one year ago", self.today).start,
                         date(2025, 7, 21))

    def test_month_offset_clamps_short_month(self):
        p = resolve_date_expression("1 month ago", date(2026, 3, 31))
        self.assertEqual(p.start, date(2026, 2, 28))

    def test_unparseable_returns_none(self):
        self.assertIsNone(resolve_date_expression("whenever", self.today))
