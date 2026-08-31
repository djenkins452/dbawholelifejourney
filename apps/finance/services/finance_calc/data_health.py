# ==============================================================================
# File: apps/finance/services/finance_calc/data_health.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: What is stale, missing or unresolved — stated, never concluded from.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""How much of this can you actually trust?

Every figure WLJ produces rests on data of varying age and completeness, and the number
itself cannot say which. "Net worth: $184,000" means something different when a house
was valued last week than when it was valued in 2023 — and looks identical either way.

So the gaps are a first-class output. Each issue names what is wrong, how much it
affects, and the exact place to fix it. None of them is a verdict: WLJ says "this
valuation is fourteen months old", never "your net worth is wrong".
"""
from __future__ import annotations

from decimal import Decimal

ZERO = Decimal("0.00")

DATA_HEALTH_VERSION = "1.0.0"

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

#: A connection quieter than this has probably stopped delivering.
STALE_ACCOUNT_DAYS = 14
#: A valuation older than this is a real number about how things were.
STALE_VALUATION_DAYS = 365
#: Above this, a single unresolved row is worth naming individually.
HIGH_VALUE_THRESHOLD = Decimal("1000")


def _issue(code, severity, title, detail, *, count=0, amount=ZERO, route=None):
    return {
        "code": code, "severity": severity, "title": title, "detail": detail,
        "count": count, "amount": str(amount), "route": route,
    }


def evaluate(user, *, today=None):
    """Every current data-quality issue, worst first. Reads only; concludes nothing."""
    from apps.core.utils import get_user_today

    today = today or get_user_today(user)
    issues = []
    issues += _account_freshness(user, today)
    issues += _classification_gaps(user)
    issues += _loan_term_gaps(user)
    issues += _valuation_gaps(user, today)
    issues += _recurring_gaps(user)
    issues += _plan_gaps(user)
    issues += _reconciliation(user)

    order = {SEVERITY_HIGH: 0, SEVERITY_MEDIUM: 1, SEVERITY_LOW: 2}
    issues.sort(key=lambda i: (order[i["severity"]], -float(i["amount"] or 0)))

    return {
        "as_of": str(today),
        "issues": issues,
        "counts": {
            severity: sum(1 for i in issues if i["severity"] == severity)
            for severity in (SEVERITY_HIGH, SEVERITY_MEDIUM, SEVERITY_LOW)
        },
        "healthy": not issues,
        "version": DATA_HEALTH_VERSION,
    }


def _account_freshness(user, today):
    from datetime import timedelta

    from apps.finance.models import FinancialAccount, Transaction

    out = []
    cutoff = today - timedelta(days=STALE_ACCOUNT_DAYS)
    for account in FinancialAccount.objects.filter(user=user, status="active"):
        if account.current_balance is None:
            out.append(_issue(
                "account_no_balance", SEVERITY_HIGH,
                f"{account.name} has no balance",
                "Every total that includes this account is incomplete until it does.",
                count=1, route="finance:account_list"))
            continue
        latest = Transaction.objects.filter(
            user=user, account=account).order_by("-date").values_list(
            "date", flat=True).first()
        if latest is not None and latest < cutoff:
            out.append(_issue(
                "account_stale", SEVERITY_MEDIUM,
                f"{account.name} has not seen a transaction since {latest}",
                f"Quiet for over {STALE_ACCOUNT_DAYS} days. That can be normal for a "
                f"savings account and can also mean the connection stopped delivering.",
                count=1, route="finance:connection_list"))
    return out


def _classification_gaps(user):
    from apps.finance.models import Transaction

    out = []
    unclassified = Transaction.objects.filter(user=user, economic_role__isnull=True)
    count = unclassified.count()
    if count:
        out.append(_issue(
            "unclassified_transactions", SEVERITY_HIGH,
            f"{count} transaction(s) have no economic role",
            "They are in no measure at all — not counted, not excluded, just absent.",
            count=count, route="finance:money_review"))

    held = Transaction.objects.filter(
        user=user, economic_role=Transaction.ROLE_UNCERTAIN)
    held_count = held.count()
    if held_count:
        total = sum((abs(t.amount or ZERO) for t in held), ZERO)
        high_value = [t for t in held if abs(t.amount or ZERO) >= HIGH_VALUE_THRESHOLD]
        out.append(_issue(
            "held_for_review", SEVERITY_MEDIUM if high_value else SEVERITY_LOW,
            f"{held_count} transaction(s) are waiting for your decision",
            (f"{len(high_value)} of them are over {HIGH_VALUE_THRESHOLD} each, so they "
             f"move a total noticeably." if high_value else
             "None is individually large, but together they are unresolved."),
            count=held_count, amount=total, route="finance:money_review"))
    return out


def _loan_term_gaps(user):
    from apps.finance.services.finance_calc import payoff as P

    missing = [d for d in P.debts_for(user) if d.missing and d.balance]
    if not missing:
        return []
    return [_issue(
        "loan_terms_missing", SEVERITY_HIGH,
        f"{len(missing)} debt(s) are missing terms",
        "Without an APR or a minimum payment, no payoff date can be calculated for "
        "them and they are absent from your committed cash. "
        + ", ".join(f"{d.name} needs {', '.join(d.missing)}" for d in missing[:4]),
        count=len(missing),
        amount=sum((d.balance for d in missing), ZERO),
        route="finance:money_debt")]


def _valuation_gaps(user, today):
    from apps.finance.models import TangibleAsset
    from apps.finance.services import asset_registry

    out, unvalued, stale = [], [], []
    for asset in TangibleAsset.objects.filter(
            user=user, status="active", include_in_net_worth=True
    ).prefetch_related("valuations"):
        value = asset_registry.current_value(asset)
        if value is None:
            unvalued.append(asset.name)
            continue
        age = asset_registry.valuation_age_days(asset, today)
        if age is not None and age > STALE_VALUATION_DAYS:
            stale.append((asset.name, age))

    if unvalued:
        out.append(_issue(
            "assets_unvalued", SEVERITY_HIGH,
            f"{len(unvalued)} asset(s) have never been valued",
            f"They are counted as unknown, not as zero, so your net worth is "
            f"understated by whatever they are worth: {', '.join(unvalued[:4])}.",
            count=len(unvalued), route="finance:asset_list"))
    if stale:
        oldest = max(age for _, age in stale)
        out.append(_issue(
            "valuations_stale", SEVERITY_MEDIUM,
            f"{len(stale)} valuation(s) are over a year old",
            f"The oldest is {oldest} days. These are real numbers about how things "
            f"were, not about how things are.",
            count=len(stale), route="finance:asset_list"))
    return out


def _recurring_gaps(user):
    from apps.finance.models import RecurringSeries

    candidates = RecurringSeries.objects.filter(
        user=user, status="active", review_state=RecurringSeries.REVIEW_CANDIDATE)
    count = candidates.count()
    if not count:
        return []
    return [_issue(
        "recurring_awaiting_review", SEVERITY_MEDIUM,
        f"{count} recurring pattern(s) are waiting for confirmation",
        "None of them counts towards your committed monthly total until you confirm "
        "it, so your forecast is missing whatever is real here.",
        count=count, route="finance:money_review")]


def _plan_gaps(user):
    from django.utils import timezone

    from apps.finance.models import SavingsOpportunity

    accepted = SavingsOpportunity.objects.filter(
        user=user, status="active", decision=SavingsOpportunity.STATUS_ACCEPTED)
    unmeasured = [o for o in accepted if o.realized_monthly_savings is None]
    if not unmeasured:
        return []
    return [_issue(
        "plans_without_results", SEVERITY_LOW,
        f"{len(unmeasured)} accepted plan(s) have no observed result yet",
        "WLJ needs a window of transactions after the start date before it can say "
        "whether the saving actually happened.",
        count=len(unmeasured),
        amount=sum((o.projected_monthly_savings for o in unmeasured), ZERO),
        route="finance:money_control")]


def _reconciliation(user):
    from apps.finance.services.finance_calc import measures as M

    result = M.reconcile(M.all_measures(user))
    if result["all_hold"]:
        return []
    failed = [name for name, check in result["checks"].items() if not check["passed"]]
    return [_issue(
        "reconciliation_failed", SEVERITY_HIGH,
        "Some totals do not reconcile",
        f"These identities failed: {', '.join(failed)}. Treat the affected figures as "
        f"provisional — WLJ is reporting the disagreement rather than hiding it.",
        count=len(failed), route="finance:money_overview")]
