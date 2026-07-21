"""
Meals Home Summary Certification (Truth milestone).

Governing investigation: docs/WLJ_COS_PLATFORM_EVOLUTION_INVESTIGATION.md (Part V/VI).
Contract: docs/WLJ_CURRENT_CONTEXT_CONTRACT.md (overview page-summary pattern).

Certifies the canonical Current Context summary for the Meals workspace, exactly like the
Dashboard Day Summary:
- DETERMINISTIC + facts-only (counts / names / dates; no verdicts).
- REQUEST-PATH SAFE — reads ONLY the SAE `meals` snapshot (allow_rebuild=False);
  never the live build_meals_state.
- SHARED — the meals dashboard page and the `meals.dashboard` provider read ONE builder.
- Deterministic PENDING when the snapshot is not yet warm (never a live rebuild).
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.ai_state.models import UserState
from apps.core.current_context import _PAGE_SUMMARY_PROVIDERS, resolve_current_context
from apps.meals.services.meals_home_summary import build_meals_home_summary

User = get_user_model()

# A known cached meals state (the flat shape build_meals_state caches into SAE).
STATE = {
    "has_household": True,
    "household_name": "The Jenkins",
    "grocery_cycle_days": 7,
    "pantry_item_count": 24,
    "pantry_expiring_count": 2,
    "expiring_item_names": ["milk", "spinach"],
    "has_dinner_planned": True,
    "dinner_recipe": "Sheet-pan salmon",
    "has_dietary_profile": True,
    "protein_target_daily": 120.0,
    "carb_limit_daily": 150.0,
}


class MealsHomeSummaryCertification(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="meal_cc@test.wlj", password="x")

    def _warm_snapshot(self, state=None):
        UserState.objects.update_or_create(
            user=self.user, defaults={"state_data": {"meals": state or STATE}})

    # ---- deterministic + facts-only projection of the cached state ----
    def test_builder_projects_cached_state(self):
        self._warm_snapshot()
        f = build_meals_home_summary(self.user)
        self.assertEqual(f["status"], "ready")
        self.assertTrue(f["has_household"])
        self.assertTrue(f["has_data"])
        self.assertEqual(f["household_name"], "The Jenkins")
        self.assertEqual(f["grocery_cycle_days"], 7)
        self.assertEqual(f["pantry_item_count"], 24)
        self.assertEqual(f["pantry_expiring_count"], 2)
        self.assertEqual(f["expiring_item_names"], ["milk", "spinach"])
        self.assertTrue(f["has_dinner_planned"])
        self.assertEqual(f["dinner_recipe"], "Sheet-pan salmon")
        self.assertEqual(f["protein_target_daily"], 120.0)

    # ---- no household is READY (not pending) — distinct from a cold snapshot ----
    def test_no_household_is_ready_not_pending(self):
        self._warm_snapshot({"has_household": False})
        f = build_meals_home_summary(self.user)
        self.assertEqual(f["status"], "ready")
        self.assertFalse(f["has_household"])
        self.assertFalse(f["has_data"])

    # ---- request-path safety: pending, never a live rebuild ----
    def test_pending_when_snapshot_cold(self):
        f = build_meals_home_summary(self.user)  # no UserState written
        self.assertEqual(f["status"], "pending")
        self.assertFalse(f["has_data"])

    def test_pending_provider_message_is_honest(self):
        summ = _PAGE_SUMMARY_PROVIDERS["meals.dashboard"](self.user, {})
        self.assertIn("being prepared", summ["content"].lower())

    # ---- full chain shares ONE source (page builder -> provider -> CC resolution) ----
    def test_full_chain_reads_one_source(self):
        self._warm_snapshot()
        facts = build_meals_home_summary(self.user)

        provider = _PAGE_SUMMARY_PROVIDERS.get("meals.dashboard")
        self.assertIsNotNone(provider)
        summ = provider(self.user, {})
        self.assertEqual(summ["title"], "Meals")
        self.assertIn("Pantry items on hand: 24", summ["content"])

        # Current Context resolution — the actual CoS path — resolves via the same provider.
        resolved = resolve_current_context(self.user, "summary:meals.dashboard")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved["ref"], "summary:meals.dashboard")
        self.assertIn("Pantry items on hand: 24", resolved["content"])
        self.assertIn("Sheet-pan salmon", resolved["content"])
        self.assertEqual(facts["pantry_item_count"], 24)

    # ---- the meals view declares the summary AND shares the one builder ----
    def test_view_declares_and_shares_builder(self):
        import apps.meals.views as v
        self.assertEqual(v.MealsDashboardView.page_summary_key, "meals.dashboard")
        # The view imports the SAME shared builder the provider uses — no parallel impl.
        self.assertIs(v.build_meals_home_summary, build_meals_home_summary)
