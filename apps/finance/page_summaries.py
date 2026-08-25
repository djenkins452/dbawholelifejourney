# ==============================================================================
# File: apps/finance/page_summaries.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Current Context PAGE-SUMMARY provider for the Finance workspace.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Deterministic Current Context page-summary provider for the Finance dashboard.

Registered at app-ready (FinanceConfig.ready). Reads the ONE shared source
(build_finance_home_summary), which is request-path-safe (SAE snapshot only). Facts
only — no verdicts; the model decides what the numbers mean. Serves the finance dashboard
(/finance/), which declares page_summary_key="finance.dashboard".
"""

from apps.core.current_context import register_page_summary
from apps.finance.services.finance_home_summary import build_finance_home_summary


def _money(v):
    """Format a numeric dollar amount as facts (no verdict). None → em dash."""
    if v is None:
        return "—"
    return f"${v:,.2f}"


@register_page_summary("finance.dashboard")
def finance_dashboard_summary(user, params):
    """The Finance workspace — deterministic financial facts (no verdicts)."""
    facts = build_finance_home_summary(user)

    if facts.get("status") == "pending":
        return {"title": "Finance", "kind": "finance overview",
                "content": "Your finances — being prepared (up-to-date figures load momentarily)."}

    if not facts.get("has_data"):
        if facts.get("enabled") is False:
            return {"title": "Finance", "kind": "finance overview",
                    "content": "Finance — this feature is turned off."}
        return {"title": "Finance", "kind": "finance overview",
                "content": "Finance — no accounts or transactions on file yet."}

    lines = [
        f"Net worth: {_money(facts.get('net_worth'))} "
        f"(assets {_money(facts.get('total_assets'))}, "
        f"liabilities {_money(facts.get('total_liabilities'))})",
        f"Accounts on file: {facts.get('account_count', 0)}",
        f"This month — spending {_money(facts.get('month_spending'))}, "
        f"income {_money(facts.get('month_income'))}",
    ]
    if facts.get("cash_pressure_level"):
        lines.append(f"Cash-pressure level: {facts['cash_pressure_level']}")
    if facts.get("active_goal_count"):
        lines.append(f"Active financial goals: {facts['active_goal_count']}")
    if facts.get("overdue_bill_count"):
        lines.append(f"Overdue bills: {facts['overdue_bill_count']}")
    if facts.get("over_budget_count"):
        lines.append(f"Budgets over limit: {facts['over_budget_count']}")
    if facts.get("upcoming_recurring_count"):
        lines.append(f"Recurring due in next 14 days: {facts['upcoming_recurring_count']}")

    # Attribution intelligence — the SAME source the dashboard section renders.
    from apps.finance.services.finance_intelligence_summary import summary_lines
    lines.extend(summary_lines(user))

    return {"title": "Finance", "kind": "finance overview",
            "content": "Finance overview\n" + "\n".join(lines)}
