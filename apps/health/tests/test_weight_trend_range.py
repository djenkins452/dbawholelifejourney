"""Weight TREND-RANGE capability — every consumer of the page is driven by ONE selected
time range over ONE filtered dataset.

The whole point of this feature is that the graph, the statistics, the subtitle, and the
assistant's Current Context can never disagree, because they all read the SAME
range-filtered series. These tests prove that invariant for every supported range, and
that the shared core primitives (parsing, resolution, persistence) behave.
"""
from datetime import date, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from apps.core import trend_range
from apps.health.models import WeightEntry
from apps.health.services import weight_queries
from apps.health.services.weight_summary import build_weight_range_summary

User = get_user_model()

WEIGHT_URL = "/health/physical/weight/"


def _mk_user(email):
    u = User.objects.create_user(email=email, password="pw12345!")
    from apps.users.models import TermsAcceptance
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS["TERMS_VERSION"])
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


# ---------------------------------------------------------------------------
# Core reusable primitive
# ---------------------------------------------------------------------------
class TrendRangeCoreTests(TestCase):
    def test_range_start_dates_are_calendar_accurate(self):
        today = date(2026, 8, 2)
        self.assertIsNone(trend_range.range_start_date("all", today))
        self.assertEqual(trend_range.range_start_date("3m", today), date(2026, 5, 2))
        self.assertEqual(trend_range.range_start_date("6m", today), date(2026, 2, 2))
        self.assertEqual(trend_range.range_start_date("1y", today), date(2025, 8, 2))
        self.assertEqual(trend_range.range_start_date("2y", today), date(2024, 8, 2))

    def test_normalize_range_falls_back_safely(self):
        self.assertEqual(trend_range.normalize_range("6m"), "6m")
        self.assertEqual(trend_range.normalize_range("bogus"), "all")
        self.assertEqual(trend_range.normalize_range(None, default="1y"), "1y")
        self.assertEqual(trend_range.normalize_range("x", default="also-bad"), "all")

    def test_options_mark_active(self):
        opts = trend_range.trend_range_options("6m")
        active = [o["key"] for o in opts if o["active"]]
        self.assertEqual(active, ["6m"])
        self.assertEqual([o["key"] for o in opts],
                         ["all", "2y", "1y", "6m", "3m"])  # canonical order

    def test_persistence_round_trip_and_no_write_when_unchanged(self):
        user = _mk_user("persist@example.com")
        self.assertEqual(trend_range.get_saved_range(user, "health.weight"), "all")
        trend_range.save_range(user, "health.weight", "6m")
        self.assertEqual(trend_range.get_saved_range(user, "health.weight"), "6m")
        # Unchanged save is a no-op (returns the value, doesn't error).
        self.assertEqual(trend_range.save_range(user, "health.weight", "6m"), "6m")
        # Invalid persists as the safe default.
        self.assertEqual(trend_range.save_range(user, "health.weight", "nope"), "all")

    def test_persistence_is_per_workspace_independent(self):
        # Each trend page remembers its OWN range; one never overwrites another.
        user = _mk_user("perworkspace@example.com")
        trend_range.save_range(user, "health.weight", "6m")
        trend_range.save_range(user, "health.glucose", "3m")
        trend_range.save_range(user, "health.sleep", "1y")
        self.assertEqual(trend_range.get_saved_range(user, "health.weight"), "6m")
        self.assertEqual(trend_range.get_saved_range(user, "health.glucose"), "3m")
        self.assertEqual(trend_range.get_saved_range(user, "health.sleep"), "1y")
        # Changing one workspace leaves the others untouched.
        trend_range.save_range(user, "health.weight", "2y")
        self.assertEqual(trend_range.get_saved_range(user, "health.weight"), "2y")
        self.assertEqual(trend_range.get_saved_range(user, "health.glucose"), "3m")
        self.assertEqual(trend_range.get_saved_range(user, "health.sleep"), "1y")
        # An untouched workspace still falls back to its own default.
        self.assertEqual(trend_range.get_saved_range(user, "health.bp"), "all")
        # Stored under the per-workspace MAP, keyed by page.
        store = User.objects.get(pk=user.pk).preferences.dashboard_config["trend_ranges"]
        self.assertEqual(store, {"health.weight": "2y", "health.glucose": "3m",
                                 "health.sleep": "1y"})


# ---------------------------------------------------------------------------
# The dataset invariant: stats + chart come from the identical filtered series
# ---------------------------------------------------------------------------
class WeightRangeDatasetTests(TestCase):
    def setUp(self):
        self.user = _mk_user("range@example.com")
        self.today = timezone.localtime(timezone.now()).date()
        # ~2.5 years of monthly weigh-ins trending down, so every range has data and
        # the ranges genuinely differ.
        self.by_date = {}
        for months_ago in range(30, -1, -1):  # 30 months ago → today
            d = self.today - timedelta(days=months_ago * 30)
            val = 320 - (30 - months_ago) * 1.0  # oldest highest, newest lowest
            WeightEntry.objects.create(
                user=self.user, value=val, unit="lb",
                recorded_at=timezone.make_aware(
                    timezone.datetime(d.year, d.month, d.day, 8, 0)),
            )
            self.by_date[d] = round(val, 1)

    def _expected_series(self, range_key):
        start = trend_range.range_start_date(range_key, self.today)
        return weight_queries.series(self.user, start_date=start)

    def test_every_range_stats_match_its_filtered_series(self):
        for range_key in ("all", "2y", "1y", "6m", "3m"):
            with self.subTest(range=range_key):
                facts = build_weight_range_summary(
                    self.user, range_key=range_key, today=self.today)
                s = self._expected_series(range_key)
                vals = [p["value_lb"] for p in s]
                self.assertEqual(facts["count"], len(s))
                self.assertEqual(facts["low_lb"], round(min(vals), 1))
                self.assertEqual(facts["high_lb"], round(max(vals), 1))
                self.assertEqual(facts["avg_lb"], round(sum(vals) / len(vals), 1))
                # Total change is FIRST visible → LAST visible in the window.
                self.assertEqual(
                    facts["total_change_lb"],
                    round(s[-1]["value_lb"] - s[0]["value_lb"], 1))
                # The chart plots the exact same points the stats were computed from.
                self.assertEqual([c["value"] for c in facts["chart_points"]], vals)

    def test_shorter_ranges_are_strict_subsets(self):
        # A tighter window can never contain more points than a wider one.
        counts = {k: build_weight_range_summary(self.user, range_key=k, today=self.today)["count"]
                  for k in ("all", "2y", "1y", "6m", "3m")}
        self.assertGreaterEqual(counts["all"], counts["2y"])
        self.assertGreaterEqual(counts["2y"], counts["1y"])
        self.assertGreaterEqual(counts["1y"], counts["6m"])
        self.assertGreaterEqual(counts["6m"], counts["3m"])

    def test_latest_is_range_independent(self):
        # "Latest" is the true most-recent weigh-in regardless of the selected window.
        true_latest = weight_queries.latest(self.user)["value_lb"]
        for range_key in ("all", "2y", "1y", "6m", "3m"):
            facts = build_weight_range_summary(
                self.user, range_key=range_key, today=self.today)
            self.assertEqual(facts["current_lb"], true_latest)

    # -- the HTTP layer: HTML context and JSON share ONE payload ------------
    def test_html_and_json_return_identical_payload(self):
        c = Client()
        c.force_login(self.user)
        html = c.get(WEIGHT_URL + "?range=6m")
        self.assertEqual(html.status_code, 200)
        wp = html.context["wp"]
        js = c.get(WEIGHT_URL + "?range=6m&fmt=json")
        self.assertEqual(js["Content-Type"], "application/json")
        payload = js.json()
        # The chart, stats, and subtitle the browser animates to are byte-for-byte the
        # same values the server rendered into the initial HTML context.
        self.assertEqual(payload["chart"]["data"], wp["chart"]["data"])
        self.assertEqual([s["value"] for s in payload["stats"]],
                         [s["value"] for s in wp["stats"]])
        self.assertEqual(payload["subtitle"], wp["subtitle"])
        self.assertEqual(payload["range"]["key"], "6m")

    def test_stat_labels_reflect_selected_range(self):
        c = Client()
        c.force_login(self.user)
        labels_6m = {s["key"]: s["label"]
                     for s in c.get(WEIGHT_URL + "?range=6m&fmt=json").json()["stats"]}
        self.assertEqual(labels_6m["low"], "Low (6M)")
        self.assertEqual(labels_6m["avg"], "Avg (6M)")
        self.assertEqual(labels_6m["change"], "Total Change (6M)")
        labels_all = {s["key"]: s["label"]
                      for s in c.get(WEIGHT_URL + "?range=all&fmt=json").json()["stats"]}
        self.assertEqual(labels_all["low"], "Lowest Ever")
        self.assertEqual(labels_all["high"], "Highest Ever")
        self.assertEqual(labels_all["avg"], "Lifetime Average")
        self.assertEqual(labels_all["change"], "Total Change")

    def test_range_selection_persists_across_visits(self):
        c = Client()
        c.force_login(self.user)
        c.get(WEIGHT_URL + "?range=1y")                       # choose 1Y
        # Reload the user — the request wrote to the DB; setUp's instance is stale.
        fresh = User.objects.get(pk=self.user.pk)
        self.assertEqual(
            trend_range.get_saved_range(fresh, "health.weight"), "1y")
        # A later visit with NO param defaults to the remembered range.
        again = c.get(WEIGHT_URL)
        self.assertEqual(again.context["range_key"], "1y")

    def test_current_context_mirrors_selected_range(self):
        from apps.ai.cos_services.current_context import get_current_context_baseline
        c = Client()
        c.force_login(self.user)
        c.get(WEIGHT_URL + "?range=6m")                       # user is looking at 6M
        fresh = User.objects.get(pk=self.user.pk)             # fresh prefs, like a new request
        summ = get_current_context_baseline(
            fresh,
            page_context={"url": WEIGHT_URL, "focus_ref": "summary:health.weight"},
        )["current_screen"]["focus"]
        self.assertIn("6 Months", summ["content"])            # assistant sees 6M, not 2Y


# ---------------------------------------------------------------------------
# Graceful degradation: empty / sparse windows
# ---------------------------------------------------------------------------
class WeightRangeEdgeCaseTests(TestCase):
    def test_no_entries_at_all_returns_empty_facts(self):
        user = _mk_user("none@example.com")
        self.assertEqual(build_weight_range_summary(user, range_key="all"), {})

    def test_window_with_no_data_is_graceful(self):
        # Only an OLD weigh-in exists; a 3-month window is empty but must not crash.
        user = _mk_user("stale@example.com")
        old = timezone.now() - timedelta(days=400)
        WeightEntry.objects.create(user=user, value=200, unit="lb", recorded_at=old)
        facts = build_weight_range_summary(user, range_key="3m")
        self.assertFalse(facts["has_range_data"])
        self.assertEqual(facts["count"], 0)
        self.assertIsNone(facts["low_lb"])
        self.assertIsNone(facts["total_change_lb"])
        self.assertEqual(facts["current_lb"], 200.0)          # Latest still honest
        self.assertEqual(facts["total_count"], 1)             # all-time count preserved

    def test_single_point_in_window_has_no_change(self):
        user = _mk_user("single@example.com")
        WeightEntry.objects.create(
            user=user, value=180, unit="lb", recorded_at=timezone.now())
        facts = build_weight_range_summary(user, range_key="6m")
        self.assertEqual(facts["count"], 1)
        self.assertEqual(facts["low_lb"], 180.0)
        self.assertEqual(facts["high_lb"], 180.0)
        self.assertIsNone(facts["total_change_lb"])           # one point → no change
