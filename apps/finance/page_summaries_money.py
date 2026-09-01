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


#: EVERY provider takes `(user, params)`. The resolver calls
#: `provider(user, _parse_summary_params(...))` and wraps the call in a try/except, so a
#: one-argument provider raises TypeError, gets swallowed, and the page silently has NO
#: Current Context — the assistant simply does not know what the person is looking at.
#: All seven Finance providers were written one-argument and had been failing that way.
#: `PageSummaryProviderSignatureTests` now fails if a new one repeats it.

@register_page_summary("finance.money")
def money_overview_summary(user, params=None):
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
def money_review_summary(user, params=None):
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
def money_control_summary(user, params=None):
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
def money_debt_summary(user, params=None):
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
def money_budget_summary(user, params=None):
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
def money_networth_summary(user, params=None):
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
def money_health_summary(user, params=None):
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


@register_page_summary("finance.recurring")
def recurring_summary(user, params=None):
    """What the Recurring page is showing, as facts. Never a verdict.

    Counts only, and the counts a person is actually looking at: how many commitments
    they have confirmed, how many WLJ is proposing, and what the confirmed ones come to
    each month. Whether that total is affordable is the model's call, not WLJ's.
    """
    from apps.finance.models import RecurringSeries
    from apps.finance.services.finance_calc import recurring as REC

    rows = RecurringSeries.objects.filter(user=user, status="active",
                                          merged_into__isnull=True)
    confirmed = rows.filter(review_state=RecurringSeries.REVIEW_CONFIRMED)
    return {
        "title": "Recurring",
        "facts": {
            "confirmed": confirmed.count(),
            "awaiting_review": rows.filter(
                review_state=RecurringSeries.REVIEW_CANDIDATE).count(),
            "ignored_or_ended": rows.filter(
                review_state=RecurringSeries.REVIEW_IGNORED).count(),
            "archived": RecurringSeries.objects.archived_only().filter(
                user=user).count(),
            # `monthly_obligation_total` returns (total, series it could not express
            # monthly) — an irregular commitment is real but has no monthly figure, and
            # counting it as zero would understate the obligation.
            "confirmed_monthly_obligation": str(
                REC.monthly_obligation_total(user)[0]),
            "confirmed_without_a_monthly_figure": len(
                REC.monthly_obligation_total(user)[1]),
            "by_kind": {
                kind: confirmed.filter(kind=kind).count()
                for kind, _label in RecurringSeries.KIND_CHOICES
                if confirmed.filter(kind=kind).exists()
            },
        },
    }
