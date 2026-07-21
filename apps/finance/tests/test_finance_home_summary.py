"""
Finance Home Summary Certification (Truth milestone).

Governing investigation: docs/WLJ_COS_PLATFORM_EVOLUTION_INVESTIGATION.md (Part V/VI).
Contract: docs/WLJ_CURRENT_CONTEXT_CONTRACT.md (overview page-summary pattern).

Certifies the canonical Current Context summary for the Finance workspace, exactly like
the Dashboard Day Summary:
- DETERMINISTIC + facts-only (numbers; no verdicts).
- REQUEST-PATH SAFE — reads ONLY the SAE `finance` snapshot (allow_rebuild=False);
  never the live build_finance_state.
- SHARED — the finance dashboard page and the `finance.dashboard` provider read ONE builder.
- Deterministic PENDING when the snapshot is not yet warm (never a live rebuild).
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.ai_state.models import UserState
from apps.core.current_context import _PAGE_SUMMARY_PROVIDERS, resolve_current_context
from apps.finance.services.finance_home_summary import build_finance_home_summary

User = get_user_model()

# A known cached finance contract (the shape build_finance_state caches into SAE).
CONTRACT = {
    "enabled": True,
    "_contract": {
        "summary": {
            "account_count": 3,
            "net_worth": 42000.00,
            "total_assets": 50000.00,
            "total_liabilities": 8000.00,
            "active_goal_count": 2,
            "month_spending": 1234.56,
            "month_income": 5000.00,
            "cash_pressure_level": "low",
        },
        "upcoming": {"recurring_due_14d": [{"name": "Rent"}, {"name": "Netflix"}]},
        "alerts": {"overdue_bills": [{"name": "Water"}], "over_budget": []},
    },
}


class FinanceHomeSummaryCertification(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="fin_cc@test.wlj", password="x")

    def _warm_snapshot(self):
        UserState.objects.update_or_create(
            user=self.user, defaults={"state_data": {"finance": CONTRACT}})

    # ---- deterministic + facts-only projection of the cached contract ----
    def test_builder_projects_cached_contract(self):
        self._warm_snapshot()
        f = build_finance_home_summary(self.user)
        self.assertEqual(f["status"], "ready")
        self.assertTrue(f["has_data"])
        self.assertEqual(f["account_count"], 3)
        self.assertEqual(f["net_worth"], 42000.00)
        self.assertEqual(f["total_assets"], 50000.00)
        self.assertEqual(f["total_liabilities"], 8000.00)
        self.assertEqual(f["month_spending"], 1234.56)
        self.assertEqual(f["month_income"], 5000.00)
        self.assertEqual(f["active_goal_count"], 2)
        self.assertEqual(f["cash_pressure_level"], "low")
        self.assertEqual(f["overdue_bill_count"], 1)
        self.assertEqual(f["over_budget_count"], 0)
        self.assertEqual(f["upcoming_recurring_count"], 2)

    # ---- request-path safety: pending, never a live rebuild ----
    def test_pending_when_snapshot_cold(self):
        f = build_finance_home_summary(self.user)  # no UserState written
        self.assertEqual(f["status"], "pending")
        self.assertFalse(f["has_data"])

    def test_pending_provider_message_is_honest(self):
        summ = _PAGE_SUMMARY_PROVIDERS["finance.dashboard"](self.user, {})
        self.assertIn("being prepared", summ["content"].lower())

    # ---- full chain shares ONE source (page builder -> provider -> CC resolution) ----
    def test_full_chain_reads_one_source(self):
        self._warm_snapshot()
        facts = build_finance_home_summary(self.user)

        provider = _PAGE_SUMMARY_PROVIDERS.get("finance.dashboard")
        self.assertIsNotNone(provider)
        summ = provider(self.user, {})
        self.assertEqual(summ["title"], "Finance")
        self.assertIn("$42,000.00", summ["content"])

        # Current Context resolution — the actual CoS path — resolves via the same provider.
        resolved = resolve_current_context(self.user, "summary:finance.dashboard")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved["ref"], "summary:finance.dashboard")
        self.assertIn("$42,000.00", resolved["content"])
        self.assertIn("Accounts on file: 3", resolved["content"])
        # facts and rendered content agree (no drift).
        self.assertEqual(facts["net_worth"], 42000.00)

    # ---- the finance view declares the summary AND shares the one builder ----
    def test_view_declares_and_shares_builder(self):
        import apps.finance.views as v
        self.assertEqual(v.FinanceDashboardView.page_summary_key, "finance.dashboard")
        # The view imports the SAME shared builder the provider uses — no parallel impl.
        self.assertIs(v.build_finance_home_summary, build_finance_home_summary)
