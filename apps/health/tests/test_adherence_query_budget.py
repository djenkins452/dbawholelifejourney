"""
Medication adherence — query-budget enforcement.

Locks in the 2026-07-05 fix for the production dashboard N+1: the expected-dose
enumeration (`_enumerate_expected_doses`) must fetch each medicine's schedules
ONCE, not once per day. Before the fix, `medicine.schedules.filter(is_active=True)`
ran inside the day loop and bypassed `prefetch_related`, so IntakeSchedule
queries scaled with the number of days in the range (30-day adherence = ~hundreds
of identical SELECTs) — invisible on SQLite, ~5–7s of the dashboard load on
Postgres.

The invariant this test enforces: **the IntakeSchedule query count for an
adherence calculation does NOT grow with the length of the date range.** If a
future change reintroduces a per-day schedule query, the 60-day count diverges
from the 1-day count and this fails.
"""
from __future__ import annotations

from datetime import date, time, timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.health.medicine_utils import calculate_medicine_adherence
from apps.health.models import Intake, IntakeSchedule

User = get_user_model()


def _count_schedule_queries(fn):
    with CaptureQueriesContext(connection) as ctx:
        fn()
    return sum(
        1 for q in ctx.captured_queries
        if 'from "health_intakeschedule"' in q["sql"].lower()
    )


class AdherenceQueryBudgetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="adherence-budget@test.com", password="x" * 12,
        )
        # Two active medicines, each with a daily schedule — enough to make a
        # per-day N+1 explode visibly across a 60-day window.
        for name in ("Med A", "Med B"):
            med = Intake.objects.create(
                user=cls.user, name=name, dose="10mg", frequency="daily",
                start_date=date(2026, 1, 1),
                intake_status=Intake.STATUS_ACTIVE,
                intake_type=Intake.INTAKE_TYPE_MEDICATION,
            )
            IntakeSchedule.objects.create(
                intake=med, scheduled_time=time(8, 0),
                days_of_week="0,1,2,3,4,5,6", is_active=True,
            )

    def test_schedule_queries_do_not_scale_with_date_range(self):
        end = date(2026, 3, 1)
        one_day = _count_schedule_queries(
            lambda: calculate_medicine_adherence(self.user, end, end)
        )
        sixty_days = _count_schedule_queries(
            lambda: calculate_medicine_adherence(
                self.user, end - timedelta(days=59), end)
        )
        # The 60-day range must not issue materially more schedule queries than
        # the 1-day range. A per-day N+1 would make sixty_days ≈ one_day × 60.
        self.assertLessEqual(
            sixty_days, one_day + 1,
            f"IntakeSchedule query count scales with the date range "
            f"(1-day={one_day}, 60-day={sixty_days}) — the expected-dose "
            f"enumeration reintroduced a per-day schedule query (N+1). Fetch "
            f"schedules once before the day loop (prefetch cache).",
        )

    def test_adherence_schedule_queries_are_bounded(self):
        end = date(2026, 3, 1)
        n = _count_schedule_queries(
            lambda: calculate_medicine_adherence(
                self.user, end - timedelta(days=29), end)
        )
        # A handful (prefetch batch + incidental), never ~60.
        self.assertLess(
            n, 10,
            f"30-day adherence issued {n} IntakeSchedule queries — expected a "
            f"single prefetch batch. A per-day N+1 has regressed.",
        )
