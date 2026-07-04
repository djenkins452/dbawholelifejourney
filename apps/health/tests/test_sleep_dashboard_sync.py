# ==============================================================================
# File: apps/health/tests/test_sleep_dashboard_sync.py
# Description: Dashboard Context Synchronization for the Sleep page. The trend graph
#   must describe the SAME nights as the history list currently on screen — not a
#   fixed recent window. Paging back through history moves the graph to that same
#   period, so the graph, the summary, and the history tell one coherent story about
#   one slice of time. Origin: history paged to May while the graph still showed the
#   last 14 days (July) — two truths on one page.
# ==============================================================================
import json
from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.health.models import SleepEntry

User = get_user_model()
PAGE = 30


class SleepDashboardSyncTests(TestCase):
    def setUp(self):
        from apps.users.models import TermsAcceptance
        self.user = User.objects.create_user(email="sleepsync@test.com", password="pw12345!")
        TermsAcceptance.objects.create(
            user=self.user, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()
        self.client.force_login(self.user)
        self.url = reverse("health:sleep_list")

    def _make_nights(self, n, *, start=None):
        """n nights, one per day going back from `start` (default today)."""
        start = start or timezone.now().date()
        for i in range(n):
            d = start - timedelta(days=i)
            SleepEntry.objects.create(
                user=self.user, sleep_date=d, source="apple_health",
                sync_id=f"sleep-{d.isoformat()}",
                total_duration_minutes=360 + (i % 60),
                asleep_duration_minutes=340 + (i % 60), quality_score=80 + (i % 15),
                bedtime=timezone.make_aware(datetime.combine(d, time(22, 0)) - timedelta(days=1)),
                wake_time=timezone.make_aware(datetime.combine(d, time(6, 0))))

    def _labels(self, response):
        return json.loads(response.context["chart_labels"])

    def _page_dates(self, response):
        return [e.sleep_date for e in response.context["entries"]]

    def _assert_graph_matches_history(self, response):
        """The graph's labels/range must be exactly the page's nights (asc)."""
        page_dates = self._page_dates(response)
        expected = [d.strftime("%m/%d") for d in sorted(page_dates)]
        self.assertEqual(self._labels(response), expected)
        self.assertEqual(len(json.loads(response.context["chart_data"])), len(page_dates))
        self.assertEqual(response.context["chart_range_start"], min(page_dates))
        self.assertEqual(response.context["chart_range_end"], max(page_dates))

    # 75 nights → 3 pages (30 / 30 / 15).
    def test_first_page_graph_matches_first_page_history(self):
        self._make_nights(75)
        self._assert_graph_matches_history(self.client.get(self.url))

    def test_middle_page_graph_matches_middle_page_history(self):
        self._make_nights(75)
        self._assert_graph_matches_history(self.client.get(self.url, {"page": 2}))

    def test_last_page_graph_matches_last_page_history(self):
        self._make_nights(75)
        r = self.client.get(self.url, {"page": 3})
        self.assertEqual(len(self._page_dates(r)), 15)
        self._assert_graph_matches_history(r)

    def test_pagination_moves_graph_and_history_together(self):
        # The core capability: the graph on page 1 (recent) and page 3 (oldest) cover
        # DISJOINT periods — the graph is never stuck on the recent window.
        self._make_nights(75)
        p1 = self.client.get(self.url)
        p3 = self.client.get(self.url, {"page": 3})
        self.assertNotEqual(self._labels(p1), self._labels(p3))
        # p1's window is entirely AFTER p3's window (newest-first pagination).
        self.assertGreater(p1.context["chart_range_start"], p3.context["chart_range_end"])

    def test_empty_history_renders_without_a_graph(self):
        r = self.client.get(self.url)          # no entries at all
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.context.get("chart_data"))
        self.assertFalse(r.context["entries"])

    def test_single_partial_last_page_graph_matches(self):
        # 31 nights → page 2 has exactly 1 night; the graph shows that one night.
        self._make_nights(31)
        r = self.client.get(self.url, {"page": 2})
        self.assertEqual(len(self._page_dates(r)), 1)
        self._assert_graph_matches_history(r)
        self.assertEqual(len(self._labels(r)), 1)
