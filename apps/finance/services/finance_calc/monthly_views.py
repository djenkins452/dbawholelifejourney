# ==============================================================================
# File: apps/finance/services/finance_calc/monthly_views.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The three monthly questions a person actually asks about money.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Three questions, three answers, never presented as each other.

    A. Did I spend more than I earned?      income - net spending
    B. Did my available cash go up or down?  cash in - cash out
    C. Did my card debt grow or shrink?      charges + interest - payments - credits

They are different numbers on purpose and the difference is informative: a large gap
between A and B means a lot went on a card and has not been paid off yet.

WHAT THIS REPLACES. The dashboard used to show one figure labelled "Monthly Cash Flow",
computed as the sum of positive amounts minus the sum of negative amounts over
`financial_activity` — every account, every role, no distinction. That is meaning #5 in
the architecture's six (§5.1), *account-level movement*, and it is none of A, B or C:

  * it counted a credit-card purchase AND the later payment that settled it, whenever
    the payment was not paired — the same consumption twice;
  * it counted mortgage principal as an expense;
  * it counted refunds as income;
  * it counted both legs of an unpaired internal transfer, which cancel out only by
    luck of the date range.

The figure was not wrong so much as unnamed. It is kept here, honestly labelled, so the
drill-down can show where the old number went — a number that changes without
explanation is a number nobody trusts again.

NO NEW CLASSIFIER. Every figure comes from `measures.py`, which reads the economic-role
authority. This module composes; it never decides what a transaction is.
"""
from __future__ import annotations

from decimal import Decimal

from apps.finance.services.finance_calc import measures as M
from apps.finance.services.finance_calc import roles as role_authority

ZERO = Decimal("0.00")

VIEWS_VERSION = "1.0.0"

#: A month is only "complete" once its last day has passed. Until then every figure is
#: month-TO-DATE, and saying so is the difference between a low number meaning "a quiet
#: month" and meaning "it is the 3rd".
PARTIAL_MONTH_NOTE = "month to date"


def _is_card(txn):
    account_type = getattr(getattr(txn, "account", None), "account_type", "") or ""
    return account_type == "credit_card"


def _card_rows(rows):
    return [(txn, assignment) for txn, assignment in rows if _is_card(txn)]


def spending_result(user, start=None, end=None, rows=None, measures=None):
    """A — "Am I spending more than I earned this month?"

    `income - net_spending`. A credit-card purchase counts here the day it is made,
    because that is when the money was committed; the payment that settles it later is
    NOT spending again. Loan principal is not consumption. Transfers and savings
    allocations are not spending — moving your own money is not spending it.
    """
    rows = rows if rows is not None else M._rows(user, start, end)
    measures = measures if measures is not None else M.all_measures(user, start, end)

    inc = measures["income"]
    net = measures["net_spending"]
    components = net.components or {}
    credits_back = (components.get("refunds", ZERO)
                    + components.get("reimbursements", ZERO)
                    + components.get("reversals", ZERO))
    value = inc.value - net.value

    return {
        "key": "spending_result",
        "question": "Am I spending more than I earned this month?",
        "label": "Spending surplus" if value >= ZERO else "Spending deficit",
        "amount": value,
        "is_surplus": value >= ZERO,
        "lines": [
            {"key": "income", "label": "Income", "amount": inc.value, "sign": +1},
            {"key": "gross_purchases", "label": "Purchases",
             "amount": components.get("gross_purchases", ZERO), "sign": -1},
            {"key": "fees_and_interest", "label": "Fees and interest",
             "amount": components.get("fees_and_interest", ZERO), "sign": -1},
            {"key": "refunds", "label": "Refunds and credits",
             "amount": credits_back, "sign": +1},
            {"key": "net_spending", "label": "Net spending",
             "amount": net.value, "sign": -1, "is_subtotal": True},
        ],
        "means": ("What you earned against what your living actually cost. A card "
                  "purchase counts the day you make it; paying the card later is not "
                  "spending it again."),
        "excludes": ["credit-card payments", "internal transfers", "savings allocations",
                     "loan principal"],
        "assumptions": list(net.assumptions),
        "inputs_missing": list(net.inputs_missing),
        "confidence": net.confidence,
    }


def liquid_cash_movement(user, start=None, end=None, rows=None, measures=None):
    """B — "Did the money available in my cash accounts go up or down?"

    Measured where the cash is: chequing, savings and cash accounts only. A card
    purchase does not reduce liquid cash until the card is paid, and a payment landing
    ON a card is not money arriving.

    An internal transfer between two of Danny's own liquid accounts nets to zero at the
    household level because both legs are on cash accounts and cancel — while staying
    fully visible per account in the drill-down.
    """
    rows = rows if rows is not None else M._rows(user, start, end)
    measures = measures if measures is not None else M.all_measures(user, start, end)

    cash_in = measures["cash_inflow"]
    cash_out = measures["cash_outflow"]
    value = cash_in.value - cash_out.value

    return {
        "key": "liquid_cash",
        "question": "Did the money available in my cash accounts increase or decrease?",
        "label": "Cash increased" if value >= ZERO else "Cash decreased",
        "amount": value,
        "is_increase": value >= ZERO,
        "lines": [
            {"key": "cash_in", "label": "Cash in", "amount": cash_in.value, "sign": +1},
            {"key": "cash_out", "label": "Cash out",
             "amount": cash_out.value, "sign": -1},
        ],
        "in_components": dict(cash_in.components or {}),
        "out_components": dict(cash_out.components or {}),
        "means": ("Every credit and debit on an account that holds money — including "
                  "card payments, loan payments and transfers out. This is liquidity, "
                  "not spending, and it is not income minus expenses."),
        "assumptions": list(cash_out.assumptions),
        "confidence": cash_out.confidence,
    }


def card_activity(user, start=None, end=None, rows=None):
    """C — "Did my credit-card debt grow or shrink this month?"

    SIGN CONVENTION: positive means the debt GREW. Charges and interest push the number
    up; payments and credits pull it down. One convention, stated on the surface that
    renders it.

    WLJ keeps no per-account balance history, so this cannot be reconciled from an
    opening balance to a closing balance. It is therefore reported as an
    **activity-based** debt change and says so — claiming a reconciliation that the
    stored data cannot support would be the more comfortable lie.
    """
    from apps.finance.models import FinancialAccount
    from apps.finance.models import Transaction as T

    rows = rows if rows is not None else M._rows(user, start, end)
    on_card = _card_rows(rows)

    charges, _ = M._sum(on_card, {T.ROLE_PURCHASE})
    fees, _ = M._sum(on_card, {T.ROLE_FEE_INTEREST})
    payments, _ = M._sum(on_card, {T.ROLE_CARD_PAYMENT})
    credits_back, _ = M._sum(on_card, {T.ROLE_REFUND, T.ROLE_REVERSAL,
                                       T.ROLE_REIMBURSEMENT})
    cash_advances, _ = M._sum(on_card, {T.ROLE_CASH_WITHDRAWAL})

    value = charges + fees + cash_advances - payments - credits_back

    balance = ZERO
    card_count = 0
    for account in FinancialAccount.objects.filter(
            user=user, status="active",
            account_type=FinancialAccount.TYPE_CREDIT_CARD):
        card_count += 1
        balance += abs(account.current_balance or ZERO)

    lines = [
        {"key": "charges", "label": "New charges", "amount": charges, "sign": +1},
        {"key": "fees", "label": "Interest and fees", "amount": fees, "sign": +1},
        {"key": "payments", "label": "Payments", "amount": payments, "sign": -1},
        {"key": "credits", "label": "Refunds and credits",
         "amount": credits_back, "sign": -1},
    ]
    if cash_advances:
        lines.insert(2, {"key": "cash_advances", "label": "Cash advances",
                         "amount": cash_advances, "sign": +1})

    return {
        "key": "card_activity",
        "question": "Did my credit-card debt grow or shrink this month?",
        "label": "Card debt grew" if value > ZERO else (
            "Card debt shrank" if value < ZERO else "Card debt unchanged"),
        "amount": value,
        "debt_grew": value > ZERO,
        "lines": lines,
        "current_balance": balance,
        "card_count": card_count,
        "sign_convention": ("Positive means the debt grew. Charges and interest push "
                            "it up; payments and credits pull it down."),
        "basis": "activity_based",
        "basis_note": (
            "Activity-based. WLJ does not store a statement balance for each month, so "
            "this is the movement its transactions can prove, not an opening-to-closing "
            "reconciliation."),
        "means": ("Everything that happened on the cards themselves. The purchases here "
                  "are the same ones counted in your spending — this view asks whether "
                  "you paid for them yet."),
    }


def account_movement(user, start=None, end=None, rows=None):
    """#5 — every credit minus every debit, on every account. What the old figure was.

    Kept, and named, so the drill-down can answer "where did the number I used to see
    go?". It is not offered as an answer to any of the three questions, because it is
    not one: it double-counts a card purchase and its later payment, treats mortgage
    principal as an expense, and counts refunds as income.
    """
    rows = rows if rows is not None else M._rows(user, start, end)
    from apps.finance.services.attribution_population import financial_activity

    activity = set(financial_activity(user, start=start, end=end)
                   .values_list("id", flat=True))

    credits_in, debits_out = ZERO, ZERO
    # What the old figure was actually made of, by role. This is the answer to "does
    # the expense number include card payments?" — a question the number itself cannot
    # answer, which is the whole reason it had to be replaced.
    credits_by_role, debits_by_role = {}, {}
    for txn, assignment in rows:
        if txn.id not in activity:
            continue
        amount = txn.amount or ZERO
        if amount > ZERO:
            credits_in += amount
            credits_by_role[assignment.role] = (
                credits_by_role.get(assignment.role, ZERO) + amount)
        elif amount < ZERO:
            debits_out += abs(amount)
            debits_by_role[assignment.role] = (
                debits_by_role.get(assignment.role, ZERO) + abs(amount))

    return {
        "key": "account_movement",
        "label": "Every credit minus every debit",
        "amount": credits_in - debits_out,
        "credits": credits_in,
        "debits": debits_out,
        "credits_by_role": credits_by_role,
        "debits_by_role": debits_by_role,
        "means": ("The sum of everything that moved, on every account, with no view "
                  "taken on what it meant. This was the old \"Monthly Cash Flow\" "
                  "figure. It answers none of the three questions cleanly, because a "
                  "card purchase and the payment that settles it are both in it."),
        "why_superseded": (
            "It counts the same consumption twice whenever a card payment is not "
            "matched to its purchases, treats loan principal as an expense, and reads "
            "a refund as income."),
    }


def monthly_views(user, start, end, *, today=None, rows=None, measures=None):
    """The three views plus the superseded figure, over one period.

    ONE set of classified rows and ONE set of measures feed every view, so the numbers
    on the dashboard, in the drill-down and in the Chief of Staff's evidence cannot
    drift apart.
    """
    rows = rows if rows is not None else M._rows(user, start, end)
    measures = measures if measures is not None else M.all_measures(
        user, start, end, rows=rows)

    spending = spending_result(user, start, end, rows=rows, measures=measures)
    cash = liquid_cash_movement(user, start, end, rows=rows, measures=measures)
    card = card_activity(user, start, end, rows=rows)
    superseded = account_movement(user, start, end, rows=rows)

    return {
        "period": period_label(start, end, today=today),
        "views": [spending, cash, card],
        "spending_result": spending,
        "liquid_cash": cash,
        "card_activity": card,
        "superseded_account_movement": superseded,
        "explains_the_difference": (
            "These three answer different questions, so they are different numbers. "
            "Spending counts a card purchase the day you make it; liquid cash only "
            "notices when you pay the card; card activity is about the debt itself. A "
            "wide gap between the first two means a lot went on a card this month."),
        "calculation_version": VIEWS_VERSION,
        "measures_version": M.MEASURES_VERSION,
    }


def period_label(start, end, *, today=None):
    """Whether this period is finished, and what to call it if not."""
    import calendar

    last_day = calendar.monthrange(start.year, start.month)[1]
    month_end = start.replace(day=last_day)
    is_partial = (start.day == 1 and end < month_end)
    return {
        "start": start,
        "end": end,
        "is_month": start.day == 1,
        "is_partial": is_partial,
        "label": start.strftime("%B %Y"),
        "qualifier": PARTIAL_MONTH_NOTE if is_partial else "",
        "days_elapsed": (end - start).days + 1,
        "days_in_month": last_day,
    }


def reconcile_views(views):
    """The identities that must hold across the three views.

    Not decoration. Each of these has already been violated once by an earlier version
    of this code, and each failure looked like a plausible number at the time.
    """
    checks = {}

    spending = views["spending_result"]
    lines = {line["key"]: line["amount"] for line in spending["lines"]}
    walked = (lines["income"] - lines["gross_purchases"] - lines["fees_and_interest"]
              + lines["refunds"])
    checks["spending_result_walks"] = {
        "passed": walked == spending["amount"],
        "expected": str(spending["amount"]), "actual": str(walked),
    }

    cash = views["liquid_cash"]
    cash_lines = {line["key"]: line["amount"] for line in cash["lines"]}
    checks["liquid_cash_walks"] = {
        "passed": (cash_lines["cash_in"] - cash_lines["cash_out"]) == cash["amount"],
        "expected": str(cash["amount"]),
        "actual": str(cash_lines["cash_in"] - cash_lines["cash_out"]),
    }

    card = views["card_activity"]
    card_walked = sum((line["sign"] * line["amount"] for line in card["lines"]), ZERO)
    checks["card_activity_walks"] = {
        "passed": card_walked == card["amount"],
        "expected": str(card["amount"]), "actual": str(card_walked),
    }

    checks["views_are_distinct_questions"] = {
        "passed": True,
        "note": ("Spending, liquid cash and card debt are not required to agree — they "
                 "answer different questions. What is required is that each walks to "
                 "its own total."),
    }
    return {"all_hold": all(c.get("passed") for c in checks.values()),
            "checks": checks, "calculation_version": VIEWS_VERSION}
