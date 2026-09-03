"""The clock seam's own contract.

If this seam is wrong, every test that relies on it is quietly wrong too — so it
asserts, rather than assumes, that WLJ's time authorities all agree with what it
was asked for. There are two of them, which is the whole reason this file exists:
`django.utils.timezone.now` and `apps.core.time.system_clock.get_current_time`,
the latter calling Python's `datetime.now(tz)` directly. They report the same
instant in production and diverge the moment a test freezes only one.
"""
from datetime import date

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.core.tests.clock import (
    EVENING_HOUR, MORNING_HOUR, REFERENCE_DAY, evening, morning, pin_clock, user_clock,
)
from apps.core.utils import get_user_now, get_user_today
from apps.users.models import TermsAcceptance

User = get_user_model()


class ClockSeamContract(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(email="clockseam@example.com", password="x")
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))

    def test_both_halves_of_the_authority_agree(self):
        """Date and hour come from one instant, so they cannot drift apart."""
        with user_clock(self.user, hour=15, minute=45, on=date(2026, 3, 9)) as clock:
            self.assertEqual(get_user_now(self.user).hour, 15)
            self.assertEqual(get_user_now(self.user).minute, 45)
            self.assertEqual(get_user_today(self.user), date(2026, 3, 9))
            self.assertEqual(clock.today, date(2026, 3, 9))
            self.assertEqual(clock.hour, 15)

    def test_the_second_time_authority_is_frozen_too(self):
        """system_clock.get_current_time reads Python's clock, not Django's."""
        from apps.core.time.system_clock import get_current_time

        with user_clock(self.user, hour=15, on=date(2026, 3, 9)):
            self.assertEqual(get_current_time().date(), date(2026, 3, 9))
            self.assertEqual(get_current_time().astimezone(timezone.utc).hour,
                             get_user_now(self.user).astimezone(timezone.utc).hour)

    def test_dayparts_land_on_the_intended_sides_of_the_pivot(self):
        """The CoS composers pivot at 8 PM; morning/evening must straddle it."""
        with morning(self.user):
            self.assertLess(get_user_now(self.user).hour, 20)
            self.assertEqual(get_user_now(self.user).hour, MORNING_HOUR)
        with evening(self.user):
            self.assertGreaterEqual(get_user_now(self.user).hour, 20)
            self.assertEqual(get_user_now(self.user).hour, EVENING_HOUR)

    def test_no_dependence_on_the_real_current_date(self):
        with morning(self.user) as clock:
            self.assertEqual(clock.today, REFERENCE_DAY)

    def test_the_clock_is_released_afterwards(self):
        before = timezone.now()
        with morning(self.user, on=date(2026, 3, 9)):
            pass
        self.assertGreaterEqual(timezone.now(), before)
        self.assertNotEqual(get_user_today(self.user), date(2026, 3, 9))

    def test_pin_clock_covers_the_whole_test(self):
        clock = pin_clock(self, self.user, hour=EVENING_HOUR)
        self.assertEqual(get_user_today(self.user), clock.today)
        self.assertEqual(get_user_now(self.user).hour, EVENING_HOUR)
