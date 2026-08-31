# ==============================================================================
# File: apps/finance/services/finance_calc/forecast.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Deterministic cash-flow forecast. Refuses to invent the inputs.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""How much money is actually free, between now and then.

Four numbers a household confuses constantly, kept apart here on purpose:

* **balance** — what is in the accounts today;
* **income** — what arrives;
* **spending** — what leaves;
* **free cash flow** — what is left after everything already promised.

Only the last one answers "can I afford this", and it is the one no bank shows you.

**The forecast degrades; it does not lie and it does not disappear.** With nothing
confirmed it reports the starting balance, states plainly that no commitments are known,
names the candidates waiting for confirmation, and refuses to project. A forecast built
on WLJ's own guesses would look identical to a real one, and the household would plan
from it.

**Provisional never mixes with committed.** Unconfirmed recurring candidates are
computed and shown, in their own column, clearly labelled. They are never added into the
committed figure — a bill nobody confirmed becoming a commitment is how a plan silently
becomes unachievable.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

ZERO = Decimal("0.00")

FORECAST_VERSION = "1.0.0"

#: Horizons a person actually asks about. Longer than 90 days and the confirmed inputs
#: stop being the dominant term.
HORIZONS = (30, 60, 90)

#: Account types whose balance is spendable this month.
LIQUID_TYPES = frozenset({"checking", "savings", "cash"})

#: Average days in a month. Used only to count OCCURRENCES, never to scale an amount.
DAYS_PER_MONTH = Decimal("30.4375")


def _occurrences(horizon_days):
    """How many times a monthly item falls inside the horizon. A whole number.

    Scaling by `days / 30.4375` would put 0.9856 of a rent payment into a 30-day
    forecast, and rent does not arrive in fractions. A monthly bill lands once in a
    month, twice in two, three times in three — and understating it by 1.4% is a
    forecast that is quietly optimistic in exactly the direction that hurts.
    """
    from decimal import ROUND_HALF_UP
    raw = Decimal(horizon_days) / DAYS_PER_MONTH
    return max(Decimal("1"), raw.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def liquid_balance(user):
    """Cash that could be spent today. Investments are not liquid for this purpose."""
    from apps.finance.models import FinancialAccount

    total, accounts = ZERO, []
    for account in FinancialAccount.objects.filter(
            user=user, status="active", account_type__in=LIQUID_TYPES):
        balance = account.current_balance
        if balance is None:
            accounts.append({"name": account.name, "amount": None,
                             "reason": "no balance recorded"})
            continue
        total += balance
        accounts.append({"name": account.name, "amount": str(balance)})
    return total, accounts


def reserve_floor(user):
    """Cash the household has declared off-limits. Zero when nothing is declared.

    Zero here means "no floor has been set", NOT "no floor is needed", and the forecast
    says so — inventing an emergency-fund target would be putting a number the user
    never chose into the figure they plan from.
    """
    from apps.finance.models import CashReserve

    reserves = list(CashReserve.objects.filter(
        user=user, status="active", kind=CashReserve.KIND_RESERVE)
        .select_related("goal", "account"))
    floor = sum((r.target_amount for r in reserves
                 if r.target_amount is not None), ZERO)
    return floor, [{
        "name": r.name,
        "target": str(r.target_amount) if r.target_amount is not None else None,
        "balance": str(r.effective_balance),
        "shortfall": str(r.shortfall) if r.shortfall is not None else None,
        "source": ("goal" if r.goal_id else "account" if r.account_id else "manual"),
    } for r in reserves]


def sinking_contributions(user):
    """Monthly money already spoken for by a known future cost."""
    from apps.finance.models import CashReserve

    funds = list(CashReserve.objects.filter(
        user=user, status="active", kind=CashReserve.KIND_SINKING))
    monthly = sum((f.monthly_contribution for f in funds
                   if f.monthly_contribution is not None), ZERO)
    return monthly, [{
        "name": f.name,
        "monthly": str(f.monthly_contribution) if f.monthly_contribution is not None
        else None,
        "target": str(f.target_amount) if f.target_amount is not None else None,
        "balance": str(f.effective_balance),
        "due": str(f.due_date) if f.due_date else None,
    } for f in funds]


def debt_minimums(user):
    """Contractual minimums. A debt with no recorded minimum is NAMED, not assumed."""
    from apps.finance.services.finance_calc import payoff as P

    debts = P.debts_for(user)
    known = [d for d in debts if d.minimum_payment is not None]
    unknown = [d.name for d in debts if d.minimum_payment is None and d.balance]
    total = sum((d.minimum_payment for d in known), ZERO)
    return total, [{"name": d.name, "minimum": str(d.minimum_payment)}
                   for d in known], unknown


def build(user, *, horizon_days=30, today=None):
    """One horizon, fully worked. Deterministic; writes nothing."""
    from apps.core.utils import get_user_today
    from apps.finance.models import RecurringSeries
    from apps.finance.services.finance_calc import opportunities as OPP
    from apps.finance.services.finance_calc import recurring as REC

    today = today or get_user_today(user)
    months = _occurrences(horizon_days)

    starting, account_rows = liquid_balance(user)
    floor, reserve_rows = reserve_floor(user)
    sinking_monthly, sinking_rows = sinking_contributions(user)
    minimums, minimum_rows, minimums_unknown = debt_minimums(user)

    confirmed_income = REC.confirmed_income(user)
    monthly_income = sum(
        (s.monthly_equivalent() for s in confirmed_income
         if s.monthly_equivalent() is not None), ZERO)

    obligations_monthly, unknown_obligations = REC.monthly_obligation_total(user)

    candidates = list(RecurringSeries.objects.filter(
        user=user, status="active",
        review_state=RecurringSeries.REVIEW_CANDIDATE))
    provisional_monthly = sum(
        (s.monthly_equivalent(use='max' if s.is_variable else 'expected') or ZERO
         for s in candidates if s.kind in RecurringSeries.OBLIGATION_KINDS), ZERO)

    inflow = (monthly_income * months).quantize(Decimal("0.01"))
    committed = ((obligations_monthly + minimums + sinking_monthly)
                 * months).quantize(Decimal("0.01"))
    provisional = (provisional_monthly * months).quantize(Decimal("0.01"))

    projected_end = starting + inflow - committed
    free_cash = projected_end - floor

    missing = _missing_inputs(confirmed_income, obligations_monthly, candidates,
                              minimums_unknown, floor, account_rows)
    projectable = bool(confirmed_income or obligations_monthly or minimums)

    return {
        "horizon_days": horizon_days,
        "as_of": str(today),
        "ends": str(today + timedelta(days=horizon_days)),
        "projectable": projectable,

        "starting_liquid": starting,
        "accounts": account_rows,

        "expected_inflow": inflow if projectable else ZERO,
        "monthly_income": monthly_income,
        "income_sources": [{"name": s.name,
                            "monthly": str(s.monthly_equivalent() or ZERO)}
                           for s in confirmed_income],

        "committed_outflow": committed if projectable else ZERO,
        "committed_breakdown": {
            "recurring_obligations": (obligations_monthly * months)
            .quantize(Decimal("0.01")),
            "debt_minimums": (minimums * months).quantize(Decimal("0.01")),
            "planned_allocations": (sinking_monthly * months)
            .quantize(Decimal("0.01")),
        },
        "debt_minimums": minimum_rows,
        "debts_without_a_minimum": minimums_unknown,
        "sinking_funds": sinking_rows,

        "provisional_outflow": provisional,
        "provisional_count": len([c for c in candidates
                                  if c.kind in RecurringSeries.OBLIGATION_KINDS]),
        "provisional_note": (
            "Detected but not confirmed. Shown so you can see what WOULD change, and "
            "deliberately kept out of the committed figure — a bill nobody confirmed "
            "becoming a commitment is how a plan silently stops being achievable."
            if provisional else None),

        "reserve_floor": floor,
        "reserves": reserve_rows,

        "projected_ending_cash": projected_end if projectable else starting,
        "free_cash_flow": free_cash if projectable else (starting - floor),
        "lowest_projected_balance": _lowest_balance(
            starting, inflow, committed, horizon_days) if projectable else starting,
        "lowest_balance_date": (str(today + timedelta(days=horizon_days))
                                if projectable else str(today)),

        "confidence": _confidence(projectable, confirmed_income, obligations_monthly,
                                  minimums_unknown, floor),
        "inputs_missing": missing,
        "assumptions": _assumptions(projectable, floor, unknown_obligations,
                                    minimums_unknown, provisional),
        "calculation_version": FORECAST_VERSION,
    }


def _lowest_balance(starting, inflow, committed, horizon_days):
    """The worst point, assuming outflows land before inflows within the horizon.

    Deliberately pessimistic: rent on the 1st and pay on the 28th is a real shape, and
    a forecast that assumes the friendly ordering tells people they are fine in the
    week they are not.
    """
    return (starting - committed).quantize(Decimal("0.01"))


def _confidence(projectable, income, obligations, minimums_unknown, floor):
    if not projectable:
        return "low"
    if not income or not obligations:
        return "low"
    if minimums_unknown or floor == ZERO:
        return "medium"
    return "high"


def _missing_inputs(income, obligations, candidates, minimums_unknown, floor,
                    account_rows):
    missing = []
    if not income:
        missing.append("confirmed_recurring_income")
    if not obligations:
        missing.append("confirmed_recurring_obligations")
    if minimums_unknown:
        missing.append("debt_minimum_payments")
    if floor == ZERO:
        missing.append("reserve_target")
    if any(row.get("amount") is None for row in account_rows):
        missing.append("account_balance")
    return missing


def _assumptions(projectable, floor, unknown_obligations, minimums_unknown,
                 provisional):
    out = []
    if not projectable:
        out.append(
            "No confirmed income, obligations or debt minimums, so nothing is "
            "projected forward. The starting balance is real; everything past today "
            "would be WLJ's guess, and a guess here looks exactly like a fact.")
        return out
    out.append("Outflows are assumed to land before inflows, so the low point is the "
               "worst case rather than the comfortable one.")
    if floor == ZERO:
        out.append(
            "No reserve floor is set, so free cash flow has nothing under it. That is "
            "an absent decision, not a judgement that you need no buffer.")
    if unknown_obligations:
        out.append(
            f"{len(unknown_obligations)} confirmed obligation(s) have no monthly "
            f"equivalent and are NOT in the committed figure.")
    if minimums_unknown:
        out.append(
            f"{len(minimums_unknown)} debt(s) have no recorded minimum payment and are "
            f"NOT in the committed figure: {', '.join(sorted(minimums_unknown))}.")
    if provisional:
        out.append("Provisional obligations are shown separately and excluded from "
                   "every committed total.")
    return out


def all_horizons(user, *, today=None):
    """30, 60 and 90 days, from ONE read of each underlying authority."""
    return {days: build(user, horizon_days=days, today=today) for days in HORIZONS}


def setup_state(user):
    """What a person must supply before a forecast means anything.

    Returned even when the forecast IS projectable, because a projection resting on
    one confirmed bill deserves to say so.
    """
    from apps.finance.models import CashReserve, RecurringSeries
    from apps.finance.services.finance_calc import payoff as P
    from apps.finance.services.finance_calc import recurring as REC

    confirmed_income = len(REC.confirmed_income(user))
    confirmed_obligations = len(REC.confirmed_obligations(user))
    candidates = RecurringSeries.objects.filter(
        user=user, status="active",
        review_state=RecurringSeries.REVIEW_CANDIDATE).count()
    reserves = CashReserve.objects.filter(
        user=user, status="active", kind=CashReserve.KIND_RESERVE).count()
    debts_missing = [d.name for d in P.debts_for(user)
                     if d.minimum_payment is None and d.balance]

    steps = []
    if candidates and not (confirmed_obligations or confirmed_income):
        steps.append({
            "what": "confirm_recurring",
            "detail": f"{candidates} recurring pattern(s) are detected and waiting. "
                      f"Confirming the real ones is the single biggest thing you can "
                      f"do for this forecast.",
            "route": "finance:money_review",
        })
    elif not candidates and not confirmed_obligations:
        steps.append({
            "what": "detect_recurring",
            "detail": "No recurring patterns are known yet. Run detection from the "
                      "review queue, then confirm the ones that are real.",
            "route": "finance:money_review",
        })
    if not confirmed_income:
        steps.append({
            "what": "confirm_income",
            "detail": "No recurring income is confirmed, so nothing is projected as "
                      "arriving.",
            "route": "finance:money_review",
        })
    if not reserves:
        steps.append({
            "what": "set_reserve",
            "detail": "No reserve floor is set. Without one, free cash flow has no "
                      "buffer under it.",
            "route": "finance:money_budget",
        })
    if debts_missing:
        steps.append({
            "what": "debt_minimums",
            "detail": f"{len(debts_missing)} debt(s) have no minimum payment recorded, "
                      f"so their commitment is missing from the forecast.",
            "route": "finance:money_debt",
        })

    return {
        "ready": not steps,
        "confirmed_income": confirmed_income,
        "confirmed_obligations": confirmed_obligations,
        "candidates_awaiting": candidates,
        "reserves": reserves,
        "steps": steps,
    }
