# ==============================================================================
# File: apps/finance/page_summaries_money.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Current Context providers for the Finance 2.0 workspaces.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""What the Chief of Staff knows the user is looking at, on each money page.

ONE deterministic source feeds both the page render and the provider — the measures
service in every case. Re-deriving a summary here would reintroduce exactly the
page-versus-assistant drift the Current Context Contract exists to eliminate.

Facts only. No verdict: the numbers and the gaps are stated, and the model interprets.
"""
from apps.core.current_context import register_page_summary


@register_page_summary("finance.money")
def money_overview_summary(user):
    from apps.finance.services.finance_calc import measures as M

    results = M.all_measures(user)
    reconciliation = M.reconcile(results)
    return {
        "title": "Spending and Cash Flow",
        "facts": {
            name: {
                "value": str(result.value),
                "confidence": result.confidence,
                "missing_inputs": list(result.inputs_missing),
            } for name, result in results.items()
        },
        "reconciles": reconciliation["all_hold"],
        "calculation_version": M.MEASURES_VERSION,
    }


@register_page_summary("finance.money_review")
def money_review_summary(user):
    from apps.finance.models import RecurringSeries, Transaction

    return {
        "title": "Money Review Queue",
        "facts": {
            "transactions_held_for_review": Transaction.objects.filter(
                user=user, economic_role=Transaction.ROLE_UNCERTAIN).count(),
            "recurring_candidates_awaiting_decision": RecurringSeries.objects.filter(
                user=user, status="active",
                review_state=RecurringSeries.REVIEW_CANDIDATE).count(),
            "transactions_not_yet_classified": Transaction.objects.filter(
                user=user, economic_role__isnull=True).count(),
        },
    }


@register_page_summary("finance.money_control")
def money_control_summary(user):
    from apps.finance.models import SpendingClassification
    from apps.finance.services.finance_calc import measures as M
    from apps.finance.services.finance_calc import opportunities as OPP

    controllable = M.all_measures(user)["controllable_spending"]
    ranked = OPP.ranked(user, limit=1)
    return {
        "title": "Controllable Spending",
        "facts": {
            "controllable_spending": str(controllable.value),
            "controllable_confidence": controllable.confidence,
            "classifications_recorded": SpendingClassification.objects.filter(
                user=user, status="active").count(),
            "open_opportunities": len(OPP.ranked(user)),
            "largest_opportunity": (
                {"title": ranked[0].title,
                 "monthly": str(ranked[0].projected_monthly_savings)}
                if ranked else None),
        },
    }


@register_page_summary("finance.money_debt")
def money_debt_summary(user):
    from apps.finance.services.finance_calc import payoff as P

    debts = P.debts_for(user)
    return {
        "title": "Debts and Payoff",
        "facts": {
            "debt_count": len(debts),
            "total_balance": str(sum((d.balance for d in debts), P.ZERO)),
            "debts_missing_terms": [
                {"name": d.name, "missing": list(d.missing)}
                for d in debts if d.missing],
        },
    }


@register_page_summary("finance.money_budget")
def money_budget_summary(user):
    from apps.finance.models import CashReserve
    from apps.finance.services.finance_calc import forecast as F

    result = F.build(user)
    return {
        "title": "Budgets and Reserves",
        "facts": {
            "projectable": result["projectable"],
            "starting_liquid": str(result["starting_liquid"]),
            "committed_outflow": str(result["committed_outflow"]),
            "free_cash_flow": str(result["free_cash_flow"]),
            "reserve_floor": str(result["reserve_floor"]),
            "reserves_configured": CashReserve.objects.filter(
                user=user, status="active").count(),
            "missing_inputs": result["inputs_missing"],
        },
        "calculation_version": F.FORECAST_VERSION,
    }


@register_page_summary("finance.money_networth")
def money_networth_summary(user):
    from apps.finance.services.finance_calc import net_worth as NW

    position = NW.compose(user)
    history = NW.history(user)
    return {
        "title": "Assets and Net Worth",
        "facts": {
            "net_worth": str(position["net_worth"]),
            "gross_assets": str(position["gross_assets"]),
            "liabilities": str(position["liabilities"]),
            "unvalued_assets": position["unvalued_assets"],
            "stale_valuations": position["stale_valuations"],
            "snapshots": len(history["points"]),
            "confidence": position["confidence"],
        },
        "calculation_version": NW.NET_WORTH_VERSION,
    }


@register_page_summary("finance.money_health")
def money_health_summary(user):
    from apps.finance.services.finance_calc import data_health as DH

    report = DH.evaluate(user)
    return {
        "title": "Finance Data Health",
        "facts": {
            "healthy": report["healthy"],
            "counts": report["counts"],
            "issues": [{"code": i["code"], "severity": i["severity"],
                        "title": i["title"]} for i in report["issues"]],
        },
        "calculation_version": DH.DATA_HEALTH_VERSION,
    }
