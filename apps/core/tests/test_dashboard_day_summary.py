"""
Dashboard Day Summary Certification (Truth milestone).

Governing investigation: docs/WLJ_COS_PLATFORM_EVOLUTION_INVESTIGATION.md (Part VI).
Constitution: Article II (Current Context) + Article III.1/III.2 (single execution authority).

Certifies the canonical Current Context summary for the Dashboard workspace:
- DETERMINISTIC + facts-only (numbers/titles; no verdicts).
- REQUEST-PATH SAFE — reads ONLY the SAE `execution` snapshot (allow_rebuild=False);
  never the live build_execution_state/build_today_execution.
- SHARED — the dashboard page and the `dashboard.day` provider read ONE builder.
- Deterministic PENDING when the snapshot is not yet warm (never a live rebuild).
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.ai_state.models import UserState
from apps.core.current_context import _PAGE_SUMMARY_PROVIDERS, resolve_current_context
from apps.core.execution.dashboard_day_summary import build_dashboard_day_summary

User = get_user_model()

# A known cached execution contract (the shape build_today_execution caches into SAE).
CONTRACT = {
    "items": [
        {"source_type": "task", "title": "Pay bills", "scheduled_time": "09:00",
         "completed_today": False, "time_status": "overdue"},
        {"source_type": "task", "title": "Standup", "scheduled_time": "10:00",
         "completed_today": True, "time_status": "upcoming"},
        {"source_type": "medication_dose", "title": "Vit D", "scheduled_time": "08:00",
         "completed_today": False, "time_status": "upcoming"},
    ],
    "summaries": {"tasks_completed_today": 1},
}


class DashboardDaySummaryCertification(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="dash_cc@test.wlj", password="x")

    def _warm_snapshot(self):
        UserState.objects.update_or_create(
            user=self.user, defaults={"state_data": {"execution": CONTRACT}})

    # ---- deterministic + facts-only projection of the cached contract ----
    def test_builder_projects_cached_contract(self):
        self._warm_snapshot()
        f = build_dashboard_day_summary(self.user)
        self.assertEqual(f["status"], "ready")
        self.assertEqual(f["total"], 3)
        self.assertEqual(f["completed"], 1)
        self.assertEqual(f["remaining"], 2)
        self.assertEqual(f["overdue"], 1)
        self.assertEqual(f["upcoming"], 1)
        self.assertEqual(f["tasks_completed_today"], 1)
        self.assertEqual(f["by_type"], {"task": 2, "medication_dose": 1})
        # earliest not-completed timed item (08:00), NOT a prioritized "do now"
        self.assertEqual(f["next_item"]["title"], "Vit D")

    # ---- request-path safety: pending, never a live rebuild ----
    def test_pending_when_snapshot_cold(self):
        f = build_dashboard_day_summary(self.user)  # no UserState written
        self.assertEqual(f["status"], "pending")
        self.assertEqual(f["total"], 0)

    def test_pending_provider_message_is_honest(self):
        summ = _PAGE_SUMMARY_PROVIDERS["dashboard.day"](self.user, {})
        self.assertIn("being prepared", summ["content"].lower())

    # ---- full chain shares ONE source (page builder -> provider -> CC resolution) ----
    def test_full_chain_reads_one_source(self):
        self._warm_snapshot()
        facts = build_dashboard_day_summary(self.user)

        provider = _PAGE_SUMMARY_PROVIDERS.get("dashboard.day")
        self.assertIsNotNone(provider)
        summ = provider(self.user, {})
        self.assertEqual(summ["title"], "Today")
        self.assertIn(f"Commitments today: {facts['total']}", summ["content"])

        # Current Context resolution — the actual CoS path — resolves via the same provider.
        resolved = resolve_current_context(self.user, "summary:dashboard.day")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved["ref"], "summary:dashboard.day")
        self.assertIn("Commitments today: 3", resolved["content"])
        self.assertIn("Completed: 1", resolved["content"])

    # ---- the dashboard views declare the summary AND share the one builder ----
    def test_dashboard_views_declare_and_share_builder(self):
        import apps.dashboard_v2.views as v2
        import apps.dashboard_v3.views as v3
        self.assertEqual(v2.DashboardV2View.page_summary_key, "dashboard.day")
        self.assertEqual(v3.DashboardV3View.page_summary_key, "dashboard.day")
        # Both views import the SAME shared builder the provider uses — no parallel impl.
        self.assertIs(v2.build_dashboard_day_summary, build_dashboard_day_summary)
        self.assertIs(v3.build_dashboard_day_summary, build_dashboard_day_summary)
