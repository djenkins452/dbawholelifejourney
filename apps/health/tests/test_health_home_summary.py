"""
Health Home Summary Certification (Truth milestone).

Governing investigation: docs/WLJ_COS_PLATFORM_EVOLUTION_INVESTIGATION.md (Part V/VI).
Contract: docs/WLJ_CURRENT_CONTEXT_CONTRACT.md (overview page-summary pattern).

Certifies the canonical Current Context summary for the Health workspace, exactly like the
Dashboard Day Summary:
- DETERMINISTIC + facts-only (numbers; no verdicts).
- REQUEST-PATH SAFE — reads ONLY the SAE `health` snapshot (allow_rebuild=False);
  never the live build_health_state (the banned ~69-query builder).
- SHARED — the Health Home page and the `health.home` provider read ONE builder.
- Deterministic PENDING when the snapshot is not yet warm (never a live rebuild).
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.ai_state.models import UserState
from apps.core.current_context import _PAGE_SUMMARY_PROVIDERS, resolve_current_context
from apps.health.services.health_home_summary import build_health_home_summary

User = get_user_model()

# A known cached health state (the flat shape build_health_state caches into SAE).
STATE = {
    "weight_current": 185.4,
    "weight_change_30d": -2.3,
    "sleep_avg_hours_7d": 7.1,
    "steps_avg_7d": 8200,
    "heart_rate_avg_7d": 61,
    "glucose_latest": 98.0,
    "glucose_avg_7d": 104.0,
    "bp_systolic": 120,
    "bp_diastolic": 78,
    "water_today_oz": 40.0,
    "water_goal_oz": 64.0,
    "medication_status": "on_track",
}


class HealthHomeSummaryCertification(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="health_cc@test.wlj", password="x")

    def _warm_snapshot(self, state=None):
        UserState.objects.update_or_create(
            user=self.user, defaults={"state_data": {"health": state or STATE}})

    # ---- deterministic + facts-only projection of the cached state ----
    def test_builder_projects_cached_state(self):
        self._warm_snapshot()
        f = build_health_home_summary(self.user)
        self.assertEqual(f["status"], "ready")
        self.assertTrue(f["has_data"])
        self.assertEqual(f["weight_current"], 185.4)
        self.assertEqual(f["weight_change_30d"], -2.3)
        self.assertEqual(f["sleep_avg_hours_7d"], 7.1)
        self.assertEqual(f["steps_avg_7d"], 8200)
        self.assertEqual(f["heart_rate_avg_7d"], 61)
        self.assertEqual(f["glucose_latest"], 98.0)
        self.assertEqual(f["bp_systolic"], 120)
        self.assertEqual(f["bp_diastolic"], 78)
        self.assertEqual(f["water_today_oz"], 40.0)
        self.assertEqual(f["medication_status"], "on_track")

    # ---- request-path safety: pending, never a live rebuild ----
    def test_pending_when_snapshot_cold(self):
        f = build_health_home_summary(self.user)  # no UserState written
        self.assertEqual(f["status"], "pending")
        self.assertFalse(f["has_data"])

    def test_pending_provider_message_is_honest(self):
        summ = _PAGE_SUMMARY_PROVIDERS["health.home"](self.user, {})
        self.assertIn("being prepared", summ["content"].lower())

    # ---- full chain shares ONE source (page builder -> provider -> CC resolution) ----
    def test_full_chain_reads_one_source(self):
        self._warm_snapshot()
        facts = build_health_home_summary(self.user)

        provider = _PAGE_SUMMARY_PROVIDERS.get("health.home")
        self.assertIsNotNone(provider)
        summ = provider(self.user, {})
        self.assertEqual(summ["title"], "Health")
        self.assertIn("Current weight: 185.4 lb", summ["content"])

        # Current Context resolution — the actual CoS path — resolves via the same provider.
        resolved = resolve_current_context(self.user, "summary:health.home")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved["ref"], "summary:health.home")
        self.assertIn("Current weight: 185.4 lb", resolved["content"])
        self.assertIn("120/78", resolved["content"])
        self.assertEqual(facts["weight_current"], 185.4)

    # ---- the health view declares the summary AND shares the one builder ----
    def test_view_declares_and_shares_builder(self):
        import apps.health.views as v
        self.assertEqual(v.HealthHomeView.page_summary_key, "health.home")
        # The view imports the SAME shared builder the provider uses — no parallel impl.
        self.assertIs(v.build_health_home_summary, build_health_home_summary)
