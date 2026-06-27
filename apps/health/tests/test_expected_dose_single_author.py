"""
D5 / Canon §5 — Expected-dose single-author tests.

There must be exactly ONE expected-dose enumeration in WLJ
(`apps.health.medicine_utils._enumerate_expected_doses`, exposed publicly as
`get_expected_dose_entries`). These tests prove:

1. The canonical algorithm itself (PRN, multiple doses/day, weekly meds,
   day-of-week schedules, future-dose-today fairness, skipped doses).
2. Output PARITY across every engine that consumes it — the range adherence
   calculator, the EAE medication-adherence signal, and the dashboard_v2
   compliance adapter all agree on the expected-dose count, because they all
   call the one enumerator (single author).

If a future change re-introduces a second schedule walk, the parity assertions
here will diverge and fail.
"""

from datetime import date, datetime, time, timedelta
from unittest.mock import patch

from django.test import TestCase

from apps.core.ai_eae.signal_aggregation import SignalAggregationService
from apps.dashboard_v2.compliance.adapters.medication import evaluate_medication
from apps.health.medicine_utils import (
    _enumerate_expected_doses,
    calculate_medicine_adherence,
    get_expected_dose_entries,
)
from apps.health.models import Intake

from apps.health.tests.test_medicine_adherence import AdherenceTestMixin


class TestEnumeratorAlgorithm(AdherenceTestMixin, TestCase):
    """The canonical expected-dose algorithm, tested in isolation (deterministic)."""

    def setUp(self):
        self.user = self.create_user(email="enum-algo@test.com")
        # A fixed, fully-in-the-past anchor day (a Monday) so day-of-week is stable.
        self.monday = date(2026, 1, 5)  # 2026-01-05 is a Monday
        self.sunday = self.monday + timedelta(days=6)

    def _count(self, meds, start, end, today, now_time):
        return len(_enumerate_expected_doses(meds, start, end, today, now_time))

    def test_prn_medicine_has_no_expected_doses(self):
        """PRN ('as needed') meds carry no schedule → zero expected doses."""
        prn = self.create_medicine(self.user, name="PRN Pain", is_prn=True)
        # No schedule created — PRN doses are not scheduled.
        count = self._count([prn], self.monday, self.sunday, self.sunday, time(23, 59))
        self.assertEqual(count, 0)

    def test_multiple_doses_per_day(self):
        """Two schedules on one day → two expected doses that day."""
        med = self.create_medicine(self.user, name="BID Med")
        self.create_schedule(med, scheduled_time=time(8, 0))
        self.create_schedule(med, scheduled_time=time(20, 0))
        count = self._count([med], self.monday, self.monday, self.monday, time(23, 59))
        self.assertEqual(count, 2)

    def test_weekly_medicine(self):
        """A Monday-only schedule over a full week → exactly one expected dose."""
        med = self.create_medicine(self.user, name="Weekly Med")
        self.create_schedule(med, scheduled_time=time(8, 0), days="0")  # Mon only
        count = self._count([med], self.monday, self.sunday, self.sunday, time(23, 59))
        self.assertEqual(count, 1)

    def test_day_of_week_subset(self):
        """Mon/Wed/Fri schedule over a full week → three expected doses."""
        med = self.create_medicine(self.user, name="MWF Med")
        self.create_schedule(med, scheduled_time=time(8, 0), days="0,2,4")
        count = self._count([med], self.monday, self.sunday, self.sunday, time(23, 59))
        self.assertEqual(count, 3)

    def test_future_dose_today_excluded(self):
        """Fairness rule: a dose scheduled later today is not yet due → not expected."""
        med = self.create_medicine(self.user, name="Evening Med")
        self.create_schedule(med, scheduled_time=time(20, 0))
        # "Now" is 10:00 on the scheduled day → the 20:00 dose is in the future.
        before = self._count([med], self.monday, self.monday, self.monday, time(10, 0))
        self.assertEqual(before, 0)
        # Once 20:00 has passed, the same dose becomes expected.
        after = self._count([med], self.monday, self.monday, self.monday, time(22, 0))
        self.assertEqual(after, 1)

    def test_past_day_future_rule_does_not_apply(self):
        """The fairness rule only applies to *today* — past days always count."""
        med = self.create_medicine(self.user, name="Evening Med")
        self.create_schedule(med, scheduled_time=time(20, 0))
        # today = tuesday, the monday 20:00 dose is in the past → expected.
        tuesday = self.monday + timedelta(days=1)
        count = self._count([med], self.monday, self.monday, tuesday, time(10, 0))
        self.assertEqual(count, 1)

    def test_inactive_schedule_excluded(self):
        """Only is_active schedules are enumerated."""
        med = self.create_medicine(self.user, name="Toggled Med")
        sched = self.create_schedule(med, scheduled_time=time(8, 0))
        sched.is_active = False
        sched.save()
        count = self._count([med], self.monday, self.monday, self.monday, time(23, 59))
        self.assertEqual(count, 0)


class TestSingleAuthorParity(AdherenceTestMixin, TestCase):
    """Every engine agrees on the expected-dose count because they share one author."""

    def setUp(self):
        self.user = self.create_user(email="enum-parity@test.com")
        # A past week so the future-dose fairness rule is moot for parity.
        self.start = date(2026, 1, 5)       # Monday
        self.end = self.start + timedelta(days=6)
        self.med = self.create_medicine(self.user, name="Daily Med")
        self.create_schedule(self.med, scheduled_time=time(8, 0))  # every day

    def test_canonical_and_range_calculator_agree(self):
        canonical = len(
            get_expected_dose_entries(
                self.user, self.start, self.end, intake_type="medication"
            )
        )
        result = calculate_medicine_adherence(
            self.user, self.start, self.end, intake_type="medication"
        )
        self.assertEqual(canonical, 7)
        self.assertEqual(result["expected_doses"], canonical)

    def test_compliance_adapter_agrees(self):
        """The dashboard_v2 compliance adapter emits exactly one expected event per dose."""
        canonical = len(
            get_expected_dose_entries(
                self.user, self.start, self.end, intake_type="medication"
            )
        )
        events = evaluate_medication(self.user, self.start, self.end)
        # Every event the adapter emits is an expected dose.
        self.assertTrue(all(e["expected"] for e in events))
        self.assertEqual(len(events), canonical)

    def test_eae_signal_scheduled_count_agrees(self):
        """The EAE medication-adherence signal's denominator matches the canonical count."""
        day = self.start  # a single past day
        canonical_day = len(
            get_expected_dose_entries(
                self.user, day, day, intake_type="medication"
            )
        )
        snapshot = SignalAggregationService._compute_medication_adherence(
            self.user, day, {"medication": True}
        )
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.source_signals["scheduled"], canonical_day)

    def test_skipped_excluded_from_denominator_not_from_expected(self):
        """Skipped doses do not change the expected count; they only adjust adherence."""
        # One skipped + six taken over the week.
        self.create_log(self.user, self.med, self.start, status="skipped")
        for i in range(1, 7):
            self.create_log(
                self.user, self.med, self.start + timedelta(days=i), status="taken"
            )
        result = calculate_medicine_adherence(
            self.user, self.start, self.end, intake_type="medication"
        )
        # Expected stays 7 (enumeration is schedule-derived, skip-agnostic)...
        self.assertEqual(result["expected_doses"], 7)
        self.assertEqual(result["skipped_doses"], 1)
        # ...but adherence denominator excludes the skip: 6 taken / (7-1) = 100%.
        self.assertEqual(result["adherence_rate"], 100)


class TestComplianceFairnessFix(AdherenceTestMixin, TestCase):
    """The compliance adapter must inherit the future-dose-today fairness rule (bug fix)."""

    def setUp(self):
        self.user = self.create_user(email="enum-fairness@test.com")
        self.today = date(2026, 1, 5)  # Monday
        self.med = self.create_medicine(self.user, name="Evening Med")
        self.create_schedule(self.med, scheduled_time=time(20, 0))

    def test_future_dose_today_not_emitted_as_missed(self):
        """Before a dose is due today, the compliance adapter must not mark it missed."""
        fake_now = datetime.combine(self.today, time(10, 0))  # 10am, before 20:00
        with patch("apps.core.utils.get_user_today", return_value=self.today), \
             patch("apps.core.utils.get_user_now", return_value=fake_now):
            events = evaluate_medication(self.user, self.today, self.today)
        # The not-yet-due 20:00 dose is excluded entirely — no MISSED event.
        self.assertEqual(events, [])
