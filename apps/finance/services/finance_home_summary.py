# ==============================================================================
# File: apps/finance/services/finance_home_summary.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: THE single deterministic Finance Home summary — facts only, read from the
#              request-path-safe SAE finance snapshot. One builder; every consumer
#              (finance dashboard page + Current Context provider) reads from it.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Deterministic Finance Home summary (facts only).

The Finance workspace's canonical Current Context summary. It projects the cached
finance state into a compact facts-only shape the conversational model reasons over — WLJ
never renders a verdict ("overspending"/"healthy"); it exposes numbers only.

REQUEST-PATH SAFE — the single most important property. It reads the **already-cached**
finance contract via the SAE snapshot (`get_module_state(user, 'finance',
allow_rebuild=False)`), NEVER the live `build_finance_state` (which runs the account /
transaction / budget aggregation). If the snapshot is not yet warm it returns
`status="pending"` — it NEVER falls back to a live rebuild.

Single authority / no drift: `build_finance_state` (the one finance-state producer) is what
the SAE caches AND what `CurrentFinance` reads for typed truth, so this summary is rooted in
the SAME truth. This module adds NO new finance calculation, NO new authority, NO new
cache — it exposes existing cached truth. Exactly the Dashboard Day Summary pattern.

Cache architecture it depends on (owned elsewhere, reused here):
  • ownership   : SAE (UserState snapshot; module key "finance").
  • producer    : build_finance_state (single finance-state authority).
  • refresh     : SAE background cycle + incremental state_updater.
  • runtime cost: one cached dict read (allow_rebuild=False) — no queries on miss.
"""

import logging

logger = logging.getLogger(__name__)


def _pending():
    return {"status": "pending", "enabled": True, "has_data": False}


def build_finance_home_summary(user):
    """Return deterministic facts for the Finance workspace (facts only, never raises).

    Shape:
        {
          "status": "ready" | "pending",   # pending = SAE snapshot not warm yet
          "enabled": bool,                  # False when the user has finances disabled
          "has_data": bool,                 # a finance _contract is present
          "account_count": int,
          "net_worth": float | None,
          "total_assets": float | None,
          "total_liabilities": float | None,
          "month_spending": float | None,
          "month_income": float | None,
          "active_goal_count": int,
          "cash_pressure_level": str | None,     # "low"|"medium"|"high" (a FACT the SAE
                                                 #   already computed — not a WLJ verdict)
          "overdue_bill_count": int,
          "over_budget_count": int,
          "upcoming_recurring_count": int,
        }
    """
    try:
        from apps.core.ai_state.state_engine import get_module_state

        # Request-path-safe: read the SAE snapshot ONLY. Never rebuild here.
        state = get_module_state(user, "finance", allow_rebuild=False) or {}

        if not state:
            # Snapshot not warm — honest pending state, never a live rebuild.
            return _pending()

        # Finances explicitly disabled (build_finance_state → {"enabled": False}):
        # a warm, ready snapshot that simply has no finance data to summarize.
        if state.get("enabled") is False:
            return {"status": "ready", "enabled": False, "has_data": False}

        contract = state.get("_contract") or {}
        summary = contract.get("summary") or {}
        if not summary:
            return {"status": "ready", "enabled": True, "has_data": False}

        alerts = contract.get("alerts") or {}
        upcoming = contract.get("upcoming") or {}

        return {
            "status": "ready",
            "enabled": True,
            "has_data": True,
            "account_count": summary.get("account_count", 0),
            "net_worth": summary.get("net_worth"),
            "total_assets": summary.get("total_assets"),
            "total_liabilities": summary.get("total_liabilities"),
            "month_spending": summary.get("month_spending"),
            "month_income": summary.get("month_income"),
            "active_goal_count": summary.get("active_goal_count", 0),
            "cash_pressure_level": summary.get("cash_pressure_level"),
            "overdue_bill_count": len(alerts.get("overdue_bills") or []),
            "over_budget_count": len(alerts.get("over_budget") or []),
            "upcoming_recurring_count": len(upcoming.get("recurring_due_14d") or []),
        }
    except Exception:  # pragma: no cover - defensive; a summary must never hard-fail
        logger.warning("build_finance_home_summary failed user=%s",
                       getattr(user, "id", None), exc_info=True)
        return _pending()
