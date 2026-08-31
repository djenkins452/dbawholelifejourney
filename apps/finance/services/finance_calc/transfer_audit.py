# ==============================================================================
# File: apps/finance/services/finance_calc/transfer_audit.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Is the transfer total double counting? Is cash outflow two ideas?
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Two accounting questions the reported numbers cannot answer about themselves.

**Is 549,702.15 of transfers one household movement counted twice?** A paired card
payment is two rows — cash leaving chequing, credit arriving on the card — and both
carry the `card_payment` role. Summing both is right at the ACCOUNT level and wrong at
the HOUSEHOLD level: one payment of 1,500 is not 3,000 of transfers.

**Does `cash_outflow` mean external economic outflow or liquid-cash reduction?** It
currently means neither cleanly: it includes debt service (which is cash out) and
excludes card payments (which are also cash out). One label is being asked to answer two
questions, and it answers both slightly wrongly.

This module computes CURRENT and PROPOSED side by side and writes nothing, so the change
can be judged on Danny's real numbers before it is made.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

ZERO = Decimal("0.00")

AUDIT_VERSION = "1.0.0"


def _cash_account(txn):
    from apps.finance.services.finance_calc import roles as R

    account_type = getattr(getattr(txn, "account", None), "account_type", "") or ""
    return account_type in R.CASH_ACCOUNT_TYPES


def _pair_key(txn):
    """A stable identity for the MOVEMENT, shared by both legs.

    The lower of the two primary keys, so whichever leg is inspected first produces the
    same key. This is what lets a household total count a movement once without caring
    which leg physically holds the OneToOne column.
    """
    from apps.finance.services.transfer_detection import paired_counterpart

    other = paired_counterpart(txn)
    if other is None:
        return f"single:{txn.pk}"
    return f"pair:{min(txn.pk, other.pk)}-{max(txn.pk, other.pk)}"


def audit(user):
    """Current versus proposed, on real rows. Read-only."""
    from apps.finance.models import Transaction as T
    from apps.finance.services.finance_calc import measures as M
    from apps.finance.services.finance_calc import roles as R

    rows = M._rows(user, None, None)
    measures = M.all_measures(user)

    return {
        "audit_version": AUDIT_VERSION,
        "transfers": _transfer_audit(rows, measures),
        "cash": _cash_audit(rows, measures),
        "pairs": _pair_audit(rows),
        "net_worth_effect": _net_worth_effect(rows),
        "note": ("Report only. Nothing here is written. CURRENT is what production "
                 "reports today; PROPOSED is what the corrected definition would."),
    }


def _transfer_audit(rows, measures):
    """Does the transfer total count one household movement twice?"""
    from apps.finance.models import Transaction as T

    transfer_roles = {T.ROLE_INTERNAL_TRANSFER, T.ROLE_CARD_PAYMENT,
                      T.ROLE_SAVINGS_ALLOCATION, T.ROLE_INVESTMENT_CONTRIBUTION}

    both_legs = ZERO
    by_movement = {}
    paired_rows, single_rows = 0, 0
    by_role_both = defaultdict(lambda: ZERO)
    by_role_once = defaultdict(lambda: ZERO)

    for txn, assignment in rows:
        if assignment.role not in transfer_roles:
            continue
        amount = abs(txn.amount or ZERO)
        both_legs += amount
        by_role_both[assignment.role] += amount

        key = _pair_key(txn)
        if key.startswith("pair:"):
            paired_rows += 1
        else:
            single_rows += 1
        # One entry per MOVEMENT. Both legs of a pair have the same magnitude, so
        # keeping either one is the household amount.
        if key not in by_movement:
            by_movement[key] = (amount, assignment.role)

    once = sum((amount for amount, _ in by_movement.values()), ZERO)
    for amount, role in by_movement.values():
        by_role_once[role] += amount

    return {
        "current_total_both_legs": str(both_legs),
        "proposed_total_once_per_movement": str(once),
        "overstatement": str(both_legs - once),
        "movements": len(by_movement),
        "rows_in_pairs": paired_rows,
        "rows_without_a_visible_pair": single_rows,
        "by_role_both_legs": {k: str(v) for k, v in sorted(by_role_both.items())},
        "by_role_once": {k: str(v) for k, v in sorted(by_role_once.items())},
        "reported_measure": str(measures["transfers_and_allocations"].value),
        "double_counts": both_legs != once,
        "explains": ("One card payment of 1,500 is two rows of 1,500 and ONE household "
                     "movement. Summing both legs is correct per account and wrong per "
                     "household."),
    }


def _cash_audit(rows, measures):
    """Is `cash_outflow` external economic outflow, or liquid-cash reduction?"""
    from apps.finance.models import Transaction as T

    economic_out = {T.ROLE_PURCHASE, T.ROLE_DEBT_SERVICE, T.ROLE_FEE_INTEREST,
                    T.ROLE_CASH_WITHDRAWAL}

    current_out, current_in = ZERO, ZERO
    liquid_out, liquid_in = ZERO, ZERO
    liquid_out_by_role = defaultdict(lambda: ZERO)
    liquid_in_by_role = defaultdict(lambda: ZERO)
    missing_from_current = defaultdict(lambda: ZERO)

    for txn, assignment in rows:
        amount = txn.amount or ZERO
        if amount == ZERO or assignment.role == T.ROLE_OPENING_BALANCE:
            continue

        if amount < 0 and assignment.role in economic_out:
            current_out += abs(amount)
        if amount > 0 and assignment.role in {
                T.ROLE_INCOME, T.ROLE_REFUND, T.ROLE_REIMBURSEMENT,
                T.ROLE_REVERSAL, T.ROLE_LOAN_PROCEEDS}:
            current_in += amount

        if not _cash_account(txn):
            continue
        if amount < 0:
            liquid_out += abs(amount)
            liquid_out_by_role[assignment.role] += abs(amount)
            if assignment.role not in economic_out:
                # Real money leaving a real account that the current definition omits.
                missing_from_current[assignment.role] += abs(amount)
        else:
            liquid_in += amount
            liquid_in_by_role[assignment.role] += amount

    return {
        "current_cash_outflow": str(measures["cash_outflow"].value),
        "current_cash_inflow": str(measures["cash_inflow"].value),
        "proposed_liquid_outflow": str(liquid_out),
        "proposed_liquid_inflow": str(liquid_in),
        "liquid_outflow_by_role": {k: str(v) for k, v
                                   in sorted(liquid_out_by_role.items())},
        "liquid_inflow_by_role": {k: str(v) for k, v
                                  in sorted(liquid_in_by_role.items())},
        "real_cash_movement_the_current_definition_omits": {
            k: str(v) for k, v in sorted(missing_from_current.items())},
        "current_net_movement": str(measures["cash_inflow"].value
                                    - measures["cash_outflow"].value),
        "proposed_net_liquid_movement": str(liquid_in - liquid_out),
        "explains": ("`cash_outflow` today includes debt service (cash out, correctly) "
                     "and excludes card payments (also cash out). It is being asked to "
                     "mean external economic outflow AND liquid-cash reduction, and it "
                     "answers both slightly wrongly."),
    }


def _pair_audit(rows):
    """Every pair should have exactly one canonical identity and two legs."""
    from apps.finance.services.transfer_detection import paired_counterpart

    seen = defaultdict(list)
    for txn, _ in rows:
        other = paired_counterpart(txn)
        if other is None:
            continue
        seen[_pair_key(txn)].append(txn.pk)

    malformed = {k: v for k, v in seen.items() if len(v) != 2}
    return {
        "pairs": len(seen),
        "well_formed": len(seen) - len(malformed),
        "malformed": len(malformed),
        "note": ("A well-formed pair is exactly two rows sharing one identity. Anything "
                 "else means a leg was claimed twice or a link points nowhere."),
    }


def _net_worth_effect(rows):
    """A principal payment moves cash and debt by the same amount. Net worth is flat."""
    from apps.finance.models import Transaction as T
    from apps.finance.services.transfer_detection import paired_counterpart

    cash_side, liability_side, movements = ZERO, ZERO, 0
    for txn, assignment in rows:
        if assignment.role != T.ROLE_CARD_PAYMENT:
            continue
        other = paired_counterpart(txn)
        if other is None or txn.pk > other.pk:
            continue                      # count each movement once, from the lower pk
        movements += 1
        for leg in (txn, other):
            amount = leg.amount or ZERO
            if _cash_account(leg):
                cash_side += amount
            else:
                liability_side += amount

    return {
        "paired_card_payments": movements,
        "cash_change": str(cash_side),
        "liability_reduction": str(liability_side),
        "net_worth_change": str(cash_side + liability_side),
        "balances": (cash_side + liability_side) == ZERO,
        "explains": ("Paying a card moves cash down and debt down by the same amount. "
                     "Net worth is unchanged by principal alone — only fees and "
                     "interest are an expense, and only when they are known."),
    }
