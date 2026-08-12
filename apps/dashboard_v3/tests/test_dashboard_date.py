"""Dashboard(date) — date-navigation + Daily Review reconstruction tests.

Verifies the smallest-seam design: ONE dashboard parameterized by a date.
  - Today renders the full LIVE cockpit; a past day renders only the DATE-SCOPED
    Daily Review, with LIVE cards hidden (card-temporality contract).
  - The Daily Review reconstructs completion score / outstanding / completed from
    deterministic day truth (build_execution_review) — no snapshots.
  - Current Context folds the viewed date so the assistant answers "what did this
    day look like?" from the same day.
  - A future date is clamped to today (the review is retrospective).
"""

import datetime as dt

from django.conf import settings
from django.test import Client, TestCase
from django.urls import reverse

from apps.core.temporality import RenderMode, Temporality, render_mode
from apps.core.utils import get_user_today
from apps.life.models import Task
from apps.users.models import TermsAcceptance, User


class TemporalityPrimitiveTests(TestCase):
    """The reusable render policy: card declares, renderer decides."""

    def test_today_shows_every_implemented_card(self):
        self.assertEqual(render_mode(Temporality.LIVE, is_today=True), RenderMode.SHOW)
        self.assertEqual(
            render_mode(Temporality.DATE_SCOPED, is_today=True), RenderMode.SHOW)

    def test_past_shows_date_scoped_hides_live(self):
        self.assertEqual(
            render_mode(Temporality.DATE_SCOPED, is_today=False), RenderMode.SHOW)
        self.assertEqual(
            render_mode(Temporality.LIVE, is_today=False), RenderMode.HIDE)

    def test_live_on_past_can_opt_into_current_badge(self):
        self.assertEqual(
            render_mode(Temporality.LIVE, is_today=False, live_on_past="badge"),
            RenderMode.SHOW_CURRENT)

    def test_future_reserved_never_renders(self):
        self.assertEqual(render_mode(Temporality.FUTURE, is_today=True), RenderMode.HIDE)
        self.assertEqual(render_mode(Temporality.FUTURE, is_today=False), RenderMode.HIDE)


class _DashboardUserMixin:
    def setUp(self):
        self.user = User.objects.create_user(
            email="v3date@test.com", password="testpass123")
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()
        self.today = get_user_today(self.user)
        self.past = self.today - dt.timedelta(days=1)
        self.client = Client()
        self.client.login(email="v3date@test.com", password="testpass123")


class DailyReviewReconstructionTests(_DashboardUserMixin, TestCase):
    """The DATE-SCOPED reconstruction composes deterministic day truth."""

    def test_score_outstanding_completed_from_day_truth(self):
        from apps.dashboard_v3.services.daily_review import build_daily_review
        from django.utils import timezone

        # One task DUE on the past day, completed (occurrence-scoped) + one open.
        Task.objects.create(
            user=self.user, title="Did on past day", module="life",
            due_date=self.past, completion_status="completed",
            completed_at=timezone.now())
        Task.objects.create(
            user=self.user, title="Missed on past day", module="life",
            due_date=self.past, completion_status="pending")

        review = build_daily_review(self.user, self.past)

        titles_done = [i["title"] for i in review["completed"]]
        titles_open = [i["title"] for i in review["outstanding"]]
        self.assertIn("Did on past day", titles_done)
        self.assertIn("Missed on past day", titles_open)
        self.assertEqual(review["intended"], 2)
        self.assertEqual(review["completed_count"], 1)
        self.assertEqual(review["score"], 50)  # 1 of 2

    def test_day_summary_historical_has_no_now_relative_fields(self):
        from apps.core.execution.dashboard_day_summary import (
            build_dashboard_day_summary,
        )
        facts = build_dashboard_day_summary(self.user, self.past)
        # A past day is retrospective — no "now"-relative overdue / next item.
        self.assertEqual(facts["overdue"], 0)
        self.assertEqual(facts["upcoming"], 0)
        self.assertIsNone(facts["next_item"])


class DashboardDateViewTests(_DashboardUserMixin, TestCase):
    """The one view renders the right card set for the viewed date."""

    def test_today_renders_live_cockpit_not_review(self):
        resp = self.client.get(reverse("dashboard_v3:home"))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8", "ignore")
        self.assertIn('class="v3-gauges"', html)                 # LIVE cockpit shown
        self.assertNotIn('<section class="v3-review"', html)     # no Daily Review

    def test_past_renders_review_not_live_cockpit(self):
        resp = self.client.get(
            reverse("dashboard_v3:home") + f"?date={self.past.isoformat()}")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8", "ignore")
        self.assertIn('<section class="v3-review"', html)        # Daily Review shown
        self.assertNotIn('class="v3-gauges"', html)              # LIVE cockpit hidden

    def test_current_context_folds_the_viewed_date(self):
        resp = self.client.get(
            reverse("dashboard_v3:home") + f"?date={self.past.isoformat()}")
        html = resp.content.decode("utf-8", "ignore")
        self.assertIn(f"summary:dashboard.day;date={self.past.isoformat()}", html)

    def test_today_current_context_has_no_date_param(self):
        resp = self.client.get(reverse("dashboard_v3:home"))
        html = resp.content.decode("utf-8", "ignore")
        self.assertIn('summary:dashboard.day"', html)  # bare key, no ;date=
        self.assertNotIn("summary:dashboard.day;date=", html)

    def test_future_date_clamps_to_today(self):
        future = (self.today + dt.timedelta(days=3)).isoformat()
        resp = self.client.get(reverse("dashboard_v3:home") + f"?date={future}")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8", "ignore")
        # Clamped to today → the LIVE cockpit renders, not a future Daily Review.
        self.assertIn('class="v3-gauges"', html)
        self.assertNotIn('<section class="v3-review"', html)

    def test_invalid_date_falls_back_to_today(self):
        resp = self.client.get(reverse("dashboard_v3:home") + "?date=not-a-date")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8", "ignore")
        self.assertIn('class="v3-gauges"', html)


class HistoricalRhythmInteractionTests(_DashboardUserMixin, TestCase):
    """THE primary acceptance scenario: a past day stays an operational workspace
    — expand a routine, complete the forgotten item, it belongs to that day while
    the completion timestamp stays now, and the card recalculates in place."""

    def setUp(self):
        super().setUp()
        from datetime import time
        from apps.life.models import Routine, RoutineSchedule
        self.routine = Routine.objects.create(
            user=self.user, name="Morning Routine",
            time_of_day="morning", is_active=True)
        self.items = [
            RoutineSchedule.objects.create(
                routine=self.routine, name=n, scheduled_time=time(7, 0),
                days_of_week="0,1,2,3,4,5,6", is_active=True)
            for n in ["Prayer", "Make Bed", "Vitamins", "Stretch", "Review Goals"]
        ]

    def test_acceptance_complete_forgotten_item_on_yesterday(self):
        from django.utils import timezone
        from apps.core.execution.today_execution import build_today_execution
        from apps.life.models import RoutineLog
        from apps.life.services.routine_helpers import toggle_routine_completion

        # Yesterday: 4 of 5 done, "Stretch" forgotten.
        for item in self.items:
            if item.name != "Stretch":
                toggle_routine_completion(self.user, item, self.past)

        contract = build_today_execution(self.user, self.past)
        ritems = [i for i in contract["items"] if i["source_type"] == "routine_item"]
        self.assertEqual(len(ritems), 5)
        open_items = [i for i in ritems if not i["completed_today"]]
        self.assertEqual([i["title"] for i in open_items], ["Stretch"])

        # Complete the forgotten item FROM the historical dashboard endpoint,
        # passing the viewed occurrence date.
        stretch = next(i for i in self.items if i.name == "Stretch")
        resp = self.client.post(
            reverse("dashboard_v2:routine_schedule_toggle",
                    kwargs={"schedule_id": stretch.id}),
            data={"date": self.past.isoformat()})
        self.assertIn(resp.status_code, (200, 204))

        # Occurrence belongs to yesterday; completion timestamp stays TODAY.
        log = RoutineLog.objects.get(schedule=stretch, scheduled_date=self.past)
        self.assertIn(log.log_status, ("completed", "completed_late"))
        self.assertEqual(log.completed_at.date(), self.today)  # not falsified to past

        # Dashboard(yesterday) immediately recalculates to 5/5.
        contract2 = build_today_execution(self.user, self.past)
        r2 = [i for i in contract2["items"] if i["source_type"] == "routine_item"]
        self.assertTrue(r2 and all(i["completed_today"] for i in r2))

    def test_past_day_renders_interactive_rhythm_plus_summary(self):
        from apps.life.services.routine_helpers import toggle_routine_completion
        toggle_routine_completion(self.user, self.items[0], self.past)

        resp = self.client.get(
            reverse("dashboard_v3:home") + f"?date={self.past.isoformat()}")
        html = resp.content.decode("utf-8", "ignore")
        # The rhythm (interactive workspace) renders on a past day, with real
        # per-item completion buttons (not just the JS handler string) …
        self.assertIn("v3-rhythm-section", html)
        self.assertIn("v3-ritem-glyph-btn", html)  # an actual open-item toggle button
        self.assertIn("Make Bed", html)             # individual routine items are shown
        # … completion POSTs are stamped with the viewed occurrence date …
        self.assertIn(f'data-view-date="{self.past.isoformat()}"', html)
        # … and the Daily Review summary is ALSO present (secondary, not a replacement).
        self.assertIn('<section class="v3-review"', html)
        # LIVE cockpit stays hidden.
        self.assertNotIn('class="v3-gauges"', html)
