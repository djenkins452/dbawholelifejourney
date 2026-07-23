# ==============================================================================
# File: apps/ai/tests/test_nutrition_truth_agreement.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Nutrition full-surface agreement + snapshot lifecycle certification
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-23
# ==============================================================================
"""
Nutrition Truth Agreement certification.

Origin: `docs/WLJ_NUTRITION_STATE_INVESTIGATION.md` (2026-07-23). The SAE nutrition
snapshot independently re-aggregated the daily macro totals AND had no record of which
calendar day those totals described. Because the freshness guard detects staleness by
looking for a NEWER RAW WRITE, a date rollover was structurally invisible: overnight,
`get_domain_state("nutrition").daily_protein_g` kept reporting the previous day's 79 g
as *today's* while `metric_on_date`/`get_history` correctly said `not_recorded`.

These gates assert the invariant:

    ONE deterministic daily Nutrition authority supplies every page, summary,
    retrieval tool, snapshot and model-facing projection. A snapshot may CACHE
    that truth; it may never compute or reinterpret it.
"""
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.test import TestCase

from apps.ai.cos_services import metric_date as md
from apps.ai.cos_services.domain_history import get_domain_history
from apps.ai.cos_services.domain_state import get_domain_state
from apps.ai.cos_services.health_facts import get_foundational_health_facts
from apps.core.ai_state.state_engine import get_module_state, rebuild_user_state
from apps.core.utils import get_user_today
from apps.health.models import FoodEntry
from apps.health.services.nutrition_queries import NutritionQueries as NQ
from apps.users.models import User

# The validated production-shaped day.
DAY = (("Breakfast bowl", 380, 24, 34, 16, "breakfast"),
       ("Chicken salad", 450, 33, 30, 22, "lunch"),
       ("Steak & veg", 440, 22, 45, 22, "dinner"))
EXPECTED = {"calories": 1270.0, "protein": 79.0, "carbs": 109.0, "fat": 60.0}
# canonical daily-totals key per macro, and the SAE snapshot field per macro
TOTALS_KEY = {"calories": "calories", "protein": "protein_g",
              "carbs": "carbs_g", "fat": "fat_g"}
SNAPSHOT_KEY = {"calories": "daily_calories", "protein": "daily_protein_g",
                "carbs": "daily_carbs_g", "fat": "daily_fat_g"}


def _seed(user, on_date):
    for name, cal, pro, carb, fat, meal in DAY:
        FoodEntry.objects.create(
            user=user, food_name=name, serving_size=Decimal("1"),
            serving_unit="serving", total_calories=Decimal(cal),
            total_protein_g=Decimal(pro), total_carbohydrates_g=Decimal(carb),
            total_fat_g=Decimal(fat), total_fiber_g=Decimal("4"),
            total_sugar_g=Decimal("9"), logged_date=on_date, meal_type=meal,
            status="active")


class NutritionSurfaceAgreementTests(TestCase):
    """Phase 3 — every reachable Nutrition surface, same user-local day, same facts."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="nutagree@test.com", password="x")
        cls.today = get_user_today(cls.user)
        _seed(cls.user, cls.today)
        rebuild_user_state(cls.user)

    def test_canonical_producer_matches_the_expected_day(self):
        totals = NQ.get_daily_totals(self.user, self.today)
        for metric, expected in EXPECTED.items():
            self.assertEqual(float(totals[TOTALS_KEY[metric]]), expected, metric)

    def test_rendered_page_agrees(self):
        from apps.health.services.nutrition_summary import build_nutrition_summary
        totals = build_nutrition_summary(self.user, target_date=self.today)["totals"]
        for metric, expected in EXPECTED.items():
            self.assertEqual(float(totals[TOTALS_KEY[metric]]), expected, metric)

    def test_current_context_page_summary_agrees(self):
        import apps.health.page_summaries  # noqa: F401 - registers the provider
        from apps.core.current_context import _PAGE_SUMMARY_PROVIDERS
        content = _PAGE_SUMMARY_PROVIDERS["health.nutrition"](
            self.user, {"date": self.today.isoformat()})["content"]
        for expected in ("1270", "79", "109", "60"):
            self.assertIn(expected, content)

    def test_get_history_agrees(self):
        for metric, expected in EXPECTED.items():
            hist = get_domain_history(self.user, "nutrition", metric,
                                      period="custom", start=self.today,
                                      end=self.today)
            self.assertEqual(hist["status"], "ready", metric)
            self.assertEqual(hist["points"][-1]["value"], expected, metric)

    def test_metric_date_agrees_with_exact_date_semantics(self):
        for metric, expected in EXPECTED.items():
            fact = md.metric_on_date(self.user, "nutrition", metric, self.today)
            self.assertEqual(fact["status"], "ok", metric)
            self.assertEqual(fact["value"], expected, metric)
            self.assertEqual(fact["semantics"], md.EXACT_DATE, metric)
            self.assertEqual(fact["observed_on"], self.today.isoformat(), metric)
            self.assertTrue(fact["exact"], metric)
            self.assertEqual(fact["authority"],
                             f"get_domain_history:nutrition.{metric}", metric)

    def test_foundational_day_keys_agree(self):
        keys = [f"{m}_today" for m in EXPECTED]
        facts = get_foundational_health_facts(self.user, keys=keys)
        for metric, expected in EXPECTED.items():
            self.assertEqual(facts[f"{metric}_today"].get("value"), expected, metric)

    def test_domain_state_snapshot_agrees(self):
        """The surface that used to contradict: the SAE projection."""
        env = get_domain_state(self.user, "nutrition")
        state = env["state"]
        for metric, expected in EXPECTED.items():
            self.assertEqual(state[SNAPSHOT_KEY[metric]], expected, metric)

    def test_snapshot_declares_the_day_it_describes(self):
        env = get_domain_state(self.user, "nutrition")
        self.assertEqual(env["state"]["daily_totals_date"], self.today.isoformat())
        self.assertEqual(env["day_freshness"], "current")
        self.assertEqual(env["state_date"], self.today.isoformat())
        self.assertEqual(env["user_local_date"], self.today.isoformat())

    def test_all_surfaces_agree_pairwise(self):
        """The matrix itself — one assertion set per macro across every surface."""
        from apps.health.services.nutrition_summary import build_nutrition_summary
        page = build_nutrition_summary(self.user, target_date=self.today)["totals"]
        totals = NQ.get_daily_totals(self.user, self.today)
        snap = get_domain_state(self.user, "nutrition")["state"]
        facts = get_foundational_health_facts(
            self.user, keys=[f"{m}_today" for m in EXPECTED])
        for metric, expected in EXPECTED.items():
            values = {
                "page": float(page[TOTALS_KEY[metric]]),
                "canonical": float(totals[TOTALS_KEY[metric]]),
                "get_history": get_domain_history(
                    self.user, "nutrition", metric, period="custom",
                    start=self.today, end=self.today)["points"][-1]["value"],
                "metric_date": md.metric_on_date(
                    self.user, "nutrition", metric, self.today)["value"],
                "foundational": facts[f"{metric}_today"]["value"],
                "domain_state": snap[SNAPSHOT_KEY[metric]],
            }
            self.assertEqual(set(values.values()), {expected},
                             f"{metric} disagreement: {values}")

    def test_snapshot_does_not_compute_its_own_totals(self):
        """A snapshot may CACHE canonical truth; it must not produce it. If the
        canonical producer is the only source, stubbing it changes the snapshot."""
        sentinel = {"calories": Decimal("999"), "protein_g": Decimal("11"),
                    "carbs_g": Decimal("22"), "fat_g": Decimal("33"),
                    "fiber_g": Decimal("1"), "sugar_g": Decimal("2")}
        with mock.patch.object(NQ, "get_daily_totals", return_value=sentinel):
            rebuild_user_state(self.user)
            state = get_module_state(self.user, "nutrition", allow_rebuild=False)
        self.assertEqual(state["daily_protein_g"], 11.0)
        self.assertEqual(state["daily_calories"], 999.0)
        rebuild_user_state(self.user)          # restore real truth for other tests

    def test_rolling_average_declares_its_different_contract(self):
        """It legitimately describes a DIFFERENT period — so it must say so, and can
        never be mistaken for the daily value."""
        state = get_module_state(self.user, "nutrition", allow_rebuild=False)
        basis = state.get("rolling_7d_basis")
        self.assertIsNotNone(basis)
        self.assertTrue(basis["excludes_today"])
        self.assertEqual(basis["denominator"], "days_with_data")
        self.assertEqual(basis["window_end_exclusive"], self.today.isoformat())


class NutritionSnapshotLifecycleTests(TestCase):
    """Phase 4 — staleness, refresh, and honest disclosure."""

    def setUp(self):
        self.user = User.objects.create_user(email="nutlife@test.com", password="x")
        self.today = get_user_today(self.user)

    def test_a_new_record_refreshes_the_snapshot(self):
        rebuild_user_state(self.user)
        self.assertEqual(
            get_domain_state(self.user, "nutrition")["state"]["daily_protein_g"], 0.0)
        _seed(self.user, self.today)
        # The read-path guard repairs the manual-entry snapshot.
        self.assertEqual(
            get_domain_state(self.user, "nutrition")["state"]["daily_protein_g"], 79.0)

    def test_date_rollover_is_repaired_even_with_no_new_write(self):
        """The proven hole: no raw write exists to detect, so only a DATE check works."""
        _seed(self.user, self.today)
        rebuild_user_state(self.user)
        self.assertEqual(
            get_module_state(self.user, "nutrition")["daily_protein_g"], 79.0)
        tomorrow = self.today + timedelta(days=1)
        with mock.patch("apps.core.utils.get_user_today", return_value=tomorrow):
            env = get_domain_state(self.user, "nutrition")
        self.assertEqual(env["state"]["daily_protein_g"], 0.0)
        self.assertEqual(env["state"]["daily_totals_date"], tomorrow.isoformat())
        self.assertEqual(env["day_freshness"], "current")

    def test_stale_snapshot_is_disclosed_not_silently_current(self):
        """If the repair cannot run, the envelope must SAY the day is stale rather
        than presenting a past day's numbers as today's."""
        _seed(self.user, self.today)
        rebuild_user_state(self.user)
        tomorrow = self.today + timedelta(days=1)
        with mock.patch("apps.core.utils.get_user_today", return_value=tomorrow), \
             mock.patch("apps.core.ai_state.state_updater.update_user_state",
                        side_effect=RuntimeError("worker down")):
            env = get_domain_state(self.user, "nutrition")
        self.assertEqual(env["day_freshness"], "stale")
        self.assertEqual(env["state_date"], self.today.isoformat())
        self.assertEqual(env["user_local_date"], tomorrow.isoformat())
        self.assertIn("NOT the user's today", env["day_freshness_reason"])
        # The stale numbers are still present — disclosed, never hidden or suppressed.
        self.assertEqual(env["state"]["daily_protein_g"], 79.0)

    def test_unstamped_snapshot_is_reported_unknown_not_current(self):
        """A pre-upgrade snapshot carries no day stamp; it must not read as today's."""
        _seed(self.user, self.today)
        rebuild_user_state(self.user)
        from apps.core.ai_state.models import UserState
        st = UserState.objects.get(user=self.user)
        st.state_data["nutrition"].pop("daily_totals_date", None)
        st.save(update_fields=["state_data"])
        with mock.patch("apps.core.ai_state.state_updater.update_user_state",
                        side_effect=RuntimeError("worker down")):
            env = get_domain_state(self.user, "nutrition")
        self.assertEqual(env["day_freshness"], "unknown")
        self.assertIsNone(env["state_date"])

    def test_refresh_is_a_bounded_single_module_rebuild_not_a_full_one(self):
        """Request-path safety: the repair runs the ONE light nutrition builder —
        never the full multi-module rebuild."""
        _seed(self.user, self.today)
        rebuild_user_state(self.user)
        tomorrow = self.today + timedelta(days=1)
        with mock.patch("apps.core.utils.get_user_today", return_value=tomorrow), \
             mock.patch("apps.core.ai_state.state_engine.rebuild_user_state") as full, \
             mock.patch("apps.core.ai_state.state_updater.update_user_state") as one:
            get_domain_state(self.user, "nutrition")
        self.assertFalse(full.called, "full SAE rebuild ran on the request path")
        one.assert_called_once_with(self.user, "nutrition")

    def test_freshness_disclosure_never_breaks_the_read(self):
        rebuild_user_state(self.user)
        with mock.patch("apps.core.ai_state.state_freshness.day_bound_field",
                        side_effect=RuntimeError("boom")):
            env = get_domain_state(self.user, "nutrition")
        self.assertEqual(env["status"], "ready")
