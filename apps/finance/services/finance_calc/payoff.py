# ==============================================================================
# File: apps/finance/services/finance_calc/payoff.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Deterministic debt-payoff scenarios. Refuses to invent a term.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""How long the debt takes, what it costs, and what changes if you push harder.

Every figure here is arithmetic over facts the user or the bank supplied. Where a fact
is missing the engine says which one and stops — it does not assume an APR. A payoff
projection is one of the few numbers a household will actually reorganise its life
around, and a plausible invented rate produces a plausible invented answer that nobody
can tell apart from a real one.

**Snowball and avalanche are presented as a trade, never as a winner.** Avalanche costs
less; snowball clears an account sooner, and the person who sees a debt disappear in
month four is measurably more likely to still be paying in month twenty. WLJ computes
both and states the difference in money and in months. It does not decide.

**Balance-only mode** exists because a household usually knows what it owes long before
it can find the paperwork. With balances and payments but no APR, payoff order and
timing are still honest arithmetic; total interest is not, and is reported as unknown
rather than as zero.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

PAYOFF_VERSION = "1.0.0"

ZERO = Decimal("0.00")
CENT = Decimal("0.01")

#: A schedule that has not cleared in this many months is not converging — usually a
#: payment at or below the monthly interest. Reported as such, never looped forever.
MAX_MONTHS = 720

STRATEGY_MINIMUM = 'minimum'
STRATEGY_SNOWBALL = 'snowball'
STRATEGY_AVALANCHE = 'avalanche'
STRATEGY_CUSTOM = 'custom'
STRATEGIES = (STRATEGY_MINIMUM, STRATEGY_SNOWBALL, STRATEGY_AVALANCHE, STRATEGY_CUSTOM)


def _money(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass
class Debt:
    """One debt, reduced to what the arithmetic needs — and what it is missing."""
    key: str
    name: str
    balance: Decimal
    apr: Decimal = None
    minimum_payment: Decimal = None
    account_id: int = None
    is_overdue: bool = False
    missing: list = field(default_factory=list)

    @property
    def monthly_rate(self):
        if self.apr is None:
            return None
        return (self.apr / Decimal("100") / Decimal("12"))

    @property
    def can_amortise(self):
        return self.apr is not None and self.minimum_payment is not None


@dataclass
class Scenario:
    """One strategy, fully worked through."""
    strategy: str
    order: list = field(default_factory=list)
    months: int = None
    debt_free_date: date = None
    total_paid: Decimal = ZERO
    total_interest: Decimal = None
    monthly_commitment: Decimal = ZERO
    per_debt: dict = field(default_factory=dict)
    excluded: list = field(default_factory=list)
    released_schedule: list = field(default_factory=list)
    assumptions: list = field(default_factory=list)
    inputs_missing: list = field(default_factory=list)
    limitations: list = field(default_factory=list)
    converged: bool = True
    calculation_version: str = PAYOFF_VERSION

    def as_dict(self):
        return {
            "strategy": self.strategy,
            "order": list(self.order),
            "months": self.months,
            "debt_free_date": str(self.debt_free_date) if self.debt_free_date else None,
            "total_paid": str(self.total_paid),
            "total_interest": (str(self.total_interest)
                               if self.total_interest is not None else None),
            "monthly_commitment": str(self.monthly_commitment),
            "per_debt": {k: {kk: (str(vv) if isinstance(vv, Decimal) else vv)
                             for kk, vv in v.items()}
                         for k, v in self.per_debt.items()},
            "excluded_for_missing_payment": list(self.excluded),
            "released_schedule": list(self.released_schedule),
            "assumptions": list(self.assumptions),
            "inputs_missing": list(self.inputs_missing),
            "limitations": list(self.limitations),
            "converged": self.converged,
            "calculation_version": self.calculation_version,
        }


# ---------------------------------------------------------------------------
# Building the inputs
# ---------------------------------------------------------------------------

def debts_for(user):
    """Every live liability, with whatever terms exist and a list of what does not."""
    from apps.finance.models import FinancialAccount, LoanTerms

    accounts = (FinancialAccount.objects.filter(
        user=user, status="active",
        account_type__in=FinancialAccount.LIABILITY_TYPES)
        .select_related("loan_terms"))

    debts = []
    for account in accounts:
        terms = getattr(account, "loan_terms", None)
        balance = account.current_balance
        balance = abs(balance) if balance is not None else None
        missing = []
        if balance is None:
            missing.append("current_balance")
        apr = terms.effective_apr if terms else None
        minimum = terms.minimum_payment if terms else None
        if apr is None:
            missing.append("apr")
        if minimum is None:
            missing.append("minimum_payment")
        debts.append(Debt(
            key=f"account:{account.pk}", name=account.name,
            balance=balance if balance is not None else ZERO,
            apr=apr, minimum_payment=minimum, account_id=account.pk,
            missing=missing))
    return debts


# ---------------------------------------------------------------------------
# Ordering
# ---------------------------------------------------------------------------

def _order(debts, strategy, custom_order=None):
    """Which debt gets the extra money first."""
    if strategy == STRATEGY_SNOWBALL:
        return sorted(debts, key=lambda d: (d.balance, d.name))
    if strategy == STRATEGY_AVALANCHE:
        # A debt with no known rate cannot be ranked by rate. It goes LAST rather than
        # being treated as 0% — which would be a recommendation built on an absence.
        return sorted(debts, key=lambda d: (
            d.apr is None, -(d.apr or ZERO), d.balance, d.name))
    if strategy == STRATEGY_CUSTOM and custom_order:
        rank = {key: i for i, key in enumerate(custom_order)}
        return sorted(debts, key=lambda d: (rank.get(d.key, len(rank)), d.name))
    return sorted(debts, key=lambda d: d.name)


# ---------------------------------------------------------------------------
# The simulation
# ---------------------------------------------------------------------------

def simulate(user, strategy=STRATEGY_AVALANCHE, *, extra_monthly=ZERO,
             lump_sum=ZERO, custom_order=None, debts=None, start=None,
             roll_forward=True):
    """Run one strategy to completion. Pure arithmetic; writes nothing."""
    from django.utils import timezone

    debts = list(debts if debts is not None else debts_for(user))
    start = start or timezone.now().date()
    extra_monthly = _money(extra_monthly or ZERO)
    lump_sum = _money(lump_sum or ZERO)

    scenario = Scenario(strategy=strategy)
    live = [d for d in debts if d.balance and d.balance > ZERO]
    if not live:
        scenario.months = 0
        scenario.assumptions.append("no live liability with a balance was found")
        return scenario

    unknown_rate = [d for d in live if d.apr is None]
    no_minimum = [d for d in live if d.minimum_payment is None]
    for debt in no_minimum:
        scenario.inputs_missing.append(f"minimum_payment:{debt.name}")
    for debt in unknown_rate:
        scenario.inputs_missing.append(f"apr:{debt.name}")

    if no_minimum:
        # A debt with no payment has no schedule, but that is no reason to refuse a
        # plan for the ones that do. It is EXCLUDED and named, and the timeline is
        # reported as partial — a household with five debts and one gap is better
        # served by four modelled debts and a clear question than by nothing.
        scenario.excluded = [d.name for d in no_minimum]
        scenario.limitations.append(
            ", ".join(sorted(d.name for d in no_minimum))
            + " has no minimum payment recorded and is EXCLUDED from this timeline. "
              "Every figure below covers the remaining debts only.")
        live = [d for d in live if d.minimum_payment is not None]
        if not live:
            scenario.order = [d.name for d in _order(no_minimum, strategy, custom_order)]
            scenario.limitations.append(
                "No debt has a recorded payment, so no timeline is calculable at all. "
                "The payoff ORDER above is still valid.")
            scenario.converged = False
            return scenario

    if unknown_rate:
        scenario.limitations.append(
            "Balance-only mode for "
            + ", ".join(sorted(d.name for d in unknown_rate))
            + ": with no APR, payments are applied entirely to principal. The payoff "
              "date is therefore the EARLIEST possible and total interest is UNKNOWN, "
              "not zero.")

    ordered = _order(live, strategy, custom_order)
    scenario.order = [d.name for d in ordered]
    scenario.monthly_commitment = _money(
        sum((d.minimum_payment for d in live), ZERO) + extra_monthly)

    balances = {d.key: _money(d.balance) for d in live}
    interest_paid = {d.key: ZERO for d in live}
    principal_paid = {d.key: ZERO for d in live}
    cleared_month = {}
    any_unknown_rate = bool(unknown_rate)

    # A lump sum goes to the front of the chosen order — that is what "one-time
    # payment towards the plan" means under any of these strategies.
    remaining_lump = lump_sum
    for debt in ordered:
        if remaining_lump <= ZERO:
            break
        applied = min(remaining_lump, balances[debt.key])
        balances[debt.key] -= applied
        principal_paid[debt.key] += applied
        remaining_lump -= applied
    if lump_sum > ZERO:
        scenario.assumptions.append(
            f"a one-off {lump_sum} is applied immediately, in the strategy's order")

    month = 0
    released = ZERO
    while any(b > ZERO for b in balances.values()) and month < MAX_MONTHS:
        month += 1

        # 1. interest accrues on what is still owed
        for debt in ordered:
            if balances[debt.key] <= ZERO:
                continue
            rate = debt.monthly_rate
            if rate is None:
                continue
            charge = _money(balances[debt.key] * rate)
            balances[debt.key] += charge
            interest_paid[debt.key] += charge

        # 2. every live debt takes its minimum
        budget_extra = extra_monthly + (released if roll_forward else ZERO)
        for debt in ordered:
            if balances[debt.key] <= ZERO:
                continue
            payment = min(debt.minimum_payment, balances[debt.key])
            balances[debt.key] -= payment
            principal_paid[debt.key] += payment

        # 3. everything spare goes to the front of the order
        for debt in ordered:
            if budget_extra <= ZERO:
                break
            if balances[debt.key] <= ZERO:
                continue
            payment = min(budget_extra, balances[debt.key])
            balances[debt.key] -= payment
            principal_paid[debt.key] += payment
            budget_extra -= payment

        # 4. a cleared debt releases its payment to the next one
        for debt in ordered:
            if debt.key in cleared_month or balances[debt.key] > ZERO:
                continue
            cleared_month[debt.key] = month
            released += debt.minimum_payment
            scenario.released_schedule.append({
                "month": month, "debt": debt.name,
                "payment_released": str(_money(debt.minimum_payment)),
                "now_available_each_month": str(_money(released + extra_monthly)),
            })

    scenario.converged = all(b <= ZERO for b in balances.values())
    scenario.months = month if scenario.converged else None
    if not scenario.converged:
        scenario.limitations.append(
            f"These payments do not clear the debt within {MAX_MONTHS // 12} years. "
            f"That normally means a payment at or below the monthly interest — the "
            f"balance is not falling.")

    total_interest = sum(interest_paid.values(), ZERO)
    scenario.total_paid = _money(sum(principal_paid.values(), ZERO))
    scenario.total_interest = None if any_unknown_rate else _money(total_interest)
    if any_unknown_rate:
        scenario.assumptions.append(
            "total interest is not reported because at least one APR is unknown; a "
            "partial total would read as the whole cost")

    if scenario.converged:
        scenario.debt_free_date = _add_months(start, month)

    for debt in ordered:
        cleared = cleared_month.get(debt.key)
        scenario.per_debt[debt.name] = {
            "starting_balance": _money(debt.balance),
            "apr": str(debt.apr) if debt.apr is not None else None,
            "minimum_payment": _money(debt.minimum_payment),
            "months_to_clear": cleared,
            "payoff_date": str(_add_months(start, cleared)) if cleared else None,
            "interest_paid": (str(_money(interest_paid[debt.key]))
                              if debt.apr is not None else None),
            "missing": list(debt.missing),
        }

    if roll_forward:
        scenario.assumptions.append(
            "each cleared debt's payment rolls forward onto the next one")
    if extra_monthly > ZERO:
        scenario.assumptions.append(f"an extra {extra_monthly} a month is applied")
    return scenario


def _add_months(start, months):
    if months is None:
        return None
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
                          else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day)


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

def compare(user, *, extra_monthly=ZERO, lump_sum=ZERO, debts=None, start=None):
    """Snowball against avalanche against minimums. A trade-off, not a verdict."""
    debts = list(debts if debts is not None else debts_for(user))
    scenarios = {
        name: simulate(user, name, extra_monthly=extra_monthly, lump_sum=lump_sum,
                       debts=debts, start=start)
        for name in (STRATEGY_MINIMUM, STRATEGY_SNOWBALL, STRATEGY_AVALANCHE)
    }

    baseline = scenarios[STRATEGY_MINIMUM]
    out = {"scenarios": {k: v.as_dict() for k, v in scenarios.items()},
           "calculation_version": PAYOFF_VERSION, "trade_off": None,
           "comparable": False}

    snowball, avalanche = scenarios[STRATEGY_SNOWBALL], scenarios[STRATEGY_AVALANCHE]
    if snowball.months is None or avalanche.months is None:
        out["trade_off"] = (
            "Snowball and avalanche cannot be compared yet: no debt has a recorded "
            "minimum payment, so there is no schedule to run.")
        return out
    if avalanche.excluded:
        out["excluded_for_missing_payment"] = list(avalanche.excluded)

    out["comparable"] = True
    interest_gap = (None if snowball.total_interest is None
                    or avalanche.total_interest is None
                    else snowball.total_interest - avalanche.total_interest)
    first_snowball = _first_clear(snowball)
    first_avalanche = _first_clear(avalanche)

    out["trade_off"] = {
        "avalanche_saves_interest": (str(interest_gap) if interest_gap is not None
                                     else None),
        "months_difference": (snowball.months or 0) - (avalanche.months or 0),
        "snowball_first_debt_cleared_month": first_snowball,
        "avalanche_first_debt_cleared_month": first_avalanche,
        "statement": _trade_off_sentence(interest_gap, first_snowball, first_avalanche),
        "note": ("WLJ computes both and does not declare a winner. Avalanche is "
                 "cheaper; snowball clears an account sooner, and finishing something "
                 "changes whether a plan survives contact with month nine."),
    }
    if baseline.months and avalanche.months:
        out["versus_minimums"] = {
            "months_saved": baseline.months - avalanche.months,
            "interest_saved": (
                str(baseline.total_interest - avalanche.total_interest)
                if baseline.total_interest is not None
                and avalanche.total_interest is not None else None),
        }
    return out


def _first_clear(scenario):
    months = [v["months_to_clear"] for v in scenario.per_debt.values()
              if v["months_to_clear"]]
    return min(months) if months else None


def _trade_off_sentence(interest_gap, first_snowball, first_avalanche):
    if interest_gap is None:
        return ("Interest cannot be compared while an APR is missing. The payoff "
                "ORDER and dates below are still calculable.")
    if interest_gap == ZERO and first_snowball == first_avalanche:
        return "The two strategies produce the same plan for these debts."
    parts = []
    if interest_gap > ZERO:
        parts.append(f"Avalanche costs {interest_gap} less in interest")
    elif interest_gap < ZERO:
        parts.append(f"Snowball costs {abs(interest_gap)} less in interest")
    if first_snowball and first_avalanche and first_snowball < first_avalanche:
        parts.append(f"snowball clears its first debt in month {first_snowball} "
                     f"rather than month {first_avalanche}")
    return "; ".join(parts) + "." if parts else "The two are equivalent here."
