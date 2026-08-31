# ==============================================================================
# File: apps/finance/services/finance_calc/roles.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The one economic-role authority. P1 SHADOW — writes nothing.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""What part does this transaction play in the household's economics?

ONE classification; the nine measures in `measures.py` are projections over it. Adding
a measure never means re-deciding what a transaction is.

**This is a layer ON TOP of `transfer_detection`, not a replacement.** That service
already decides *whether* something is a transfer and *what kind*, using provider facts,
matched pairs and user confirmation; it owns those questions and keeps owning them. This
module answers a different question — what the movement MEANS economically — and reads
`transfer_state` / `transfer_kind` / `transfer_by` as inputs. Re-deriving "is this a
transfer" here would be the parallel detection the architecture forbids.

**Shadow mode.** `classify()` is a pure function: it returns a `RoleAssignment` and
writes nothing, anywhere. Nothing in WLJ reads `Transaction.economic_role`.
`attribution_population.financial_activity` remains the sole authority for every
displayed total until Danny approves activation.

Deterministic, explainable, idempotent, versioned: the same row and the same classifier
version always produce the same role, and the reason is a stable key — never a merchant
name — so it is safe to log, group and show.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

#: Bump when the RULES change. A different version is a new opinion, which is what makes
#: reclassification explicable rather than mysterious.
CLASSIFIER_VERSION = "1.0.0"

ZERO = Decimal("0.00")

#: Provider categories that mean real income, as opposed to money merely arriving.
INCOME_PRIMARIES = frozenset({"INCOME"})

#: Bank fees and interest CHARGED to the user — a real cost, not a purchase.
FEE_PRIMARIES = frozenset({"BANK_FEES"})
FEE_DETAILED_HINTS = ("OVERDRAFT", "LATE_PAYMENT", "INTEREST_CHARGE", "FOREIGN_TRANSACTION",
                      "ATM_FEE", "INSUFFICIENT_FUNDS")

#: Cash out. Deliberately its own role — see `_cash_withdrawal`.
CASH_DETAILED_HINTS = ("ATM", "CASH_ADVANCE", "WITHDRAWAL")

#: Loan servicing that is NOT a credit-card payment.
LOAN_PAYMENT_PRIMARY = "LOAN_PAYMENTS"
CARD_PAYMENT_DETAILED = "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT"


@dataclass(frozen=True)
class RoleAssignment:
    """A classification, and everything needed to defend it."""
    role: str
    confidence: str
    source: str
    reason: str
    classifier_version: str = CLASSIFIER_VERSION

    def as_update_fields(self):
        """The shape a future backfill would persist. NOT used in shadow mode."""
        return {
            "economic_role": self.role,
            "role_confidence": self.confidence,
            "role_source": self.source,
            "role_reason": self.reason,
            "role_classifier_version": self.classifier_version,
        }


def _account_type(txn):
    account = getattr(txn, "account", None)
    return getattr(account, "account_type", "") or ""


def _is_liability_account(txn):
    account = getattr(txn, "account", None)
    return bool(account is not None and getattr(account, "is_liability", False))


def _detailed(txn):
    return (txn.provider_category_detailed or "").upper()


def _primary(txn):
    return (txn.provider_category_primary or "").upper()


def _looks_like_cash(txn):
    detailed = _detailed(txn)
    return any(hint in detailed for hint in CASH_DETAILED_HINTS)


def _looks_like_fee(txn):
    if _primary(txn) in FEE_PRIMARIES:
        return True
    detailed = _detailed(txn)
    return any(hint in detailed for hint in FEE_DETAILED_HINTS)


def classify(txn) -> RoleAssignment:
    """The economic role of one transaction. Pure — writes nothing.

    Order matters, and it runs from most authoritative to least: a decision the USER
    made, then a conclusive transfer classification, then provider facts, then shape.
    Anything that survives to the end without a confident answer is `uncertain`, which
    is a real answer and not a failure.
    """
    from apps.finance.models import Transaction as T

    amount = txn.amount if txn.amount is not None else ZERO

    # ------------------------------------------------- 0a. not activity at all
    # An opening balance is an account's starting position, not something that
    # happened. It gets a ROLE rather than being filtered out, because
    # `attribution_population` is the ONLY module permitted to define the activity
    # exclusion — re-deriving it here would be the second definition the Finance
    # constitution forbids (and two contract tests enforce).
    if getattr(txn, "is_opening_balance", False):
        return RoleAssignment(T.ROLE_OPENING_BALANCE, T.ROLE_CONFIDENCE_HIGH,
                              T.ROLE_SOURCE_DERIVED, "opening_balance")

    # ------------------------------------------------------------------ 0. user
    # A user decision outranks every derivation, exactly as `category_source='user'`
    # already does for categories. Nothing below may overturn it.
    # `transfer_classified_by` is the real field name. Read it directly rather than
    # through a defaulted getattr: a getattr default turns a typo into a silent "no
    # user confirmation", which would quietly overwrite the one authority that must
    # never be overwritten.
    classified_by = txn.transfer_classified_by or ""
    if classified_by == T.TRANSFER_BY_USER and \
            txn.transfer_state == T.TRANSFER_STATE_CONFIRMED:
        role = (T.ROLE_CARD_PAYMENT
                if txn.transfer_kind == T.TRANSFER_KIND_CARD_PAYMENT
                else T.ROLE_INTERNAL_TRANSFER)
        return RoleAssignment(role, T.ROLE_CONFIDENCE_HIGH, T.ROLE_SOURCE_USER,
                              "user_confirmed_transfer")

    # ------------------------------------------------- 1. conclusive transfers
    if txn.transfer_state == T.TRANSFER_STATE_CONFIRMED:
        source = {
            T.TRANSFER_BY_PAIRING: T.ROLE_SOURCE_PAIRING,
            T.TRANSFER_BY_PROVIDER: T.ROLE_SOURCE_PROVIDER,
        }.get(classified_by, T.ROLE_SOURCE_DERIVED)

        if txn.transfer_kind == T.TRANSFER_KIND_CARD_PAYMENT:
            # Paying a card is NOT spending — the purchases it settles already were.
            return RoleAssignment(T.ROLE_CARD_PAYMENT, T.ROLE_CONFIDENCE_HIGH,
                                  source, "confirmed_card_payment")
        if txn.transfer_kind == T.TRANSFER_KIND_REVERSAL:
            return RoleAssignment(T.ROLE_REVERSAL, T.ROLE_CONFIDENCE_HIGH,
                                  source, "confirmed_reversal")
        # An internal move into savings or investment is an ALLOCATION, not consumption
        # and not merely plumbing — the distinction matters for "where did it go".
        destination = _account_type(txn)
        if destination == "savings" and amount > 0:
            return RoleAssignment(T.ROLE_SAVINGS_ALLOCATION, T.ROLE_CONFIDENCE_HIGH,
                                  source, "confirmed_savings_allocation")
        if destination == "investment":
            return RoleAssignment(T.ROLE_INVESTMENT_CONTRIBUTION,
                                  T.ROLE_CONFIDENCE_HIGH, source,
                                  "confirmed_investment_contribution")
        return RoleAssignment(T.ROLE_INTERNAL_TRANSFER, T.ROLE_CONFIDENCE_HIGH,
                              source, "confirmed_internal_transfer")

    # ------------------------------------------------------ 2. refund / reversal
    if txn.transfer_kind == T.TRANSFER_KIND_REFUND and amount > 0:
        return RoleAssignment(T.ROLE_REFUND, T.ROLE_CONFIDENCE_MEDIUM,
                              T.ROLE_SOURCE_PROVIDER, "provider_refund")

    # ----------------------------------------------- 3. held-for-review transfers
    # A possible transfer whose counterpart WLJ cannot see. The cash genuinely moved —
    # that is not in doubt — but its economic meaning is. It keeps its cash movement
    # and enters NO spending measure.
    if txn.transfer_state == T.TRANSFER_STATE_CANDIDATE:
        return RoleAssignment(T.ROLE_UNCERTAIN, T.ROLE_CONFIDENCE_LOW,
                              T.ROLE_SOURCE_DERIVED, "unmatched_transfer_candidate")

    # --------------------------------------------------------- 4. debt servicing
    detailed, primary = _detailed(txn), _primary(txn)
    if amount < 0 and primary == LOAN_PAYMENT_PRIMARY and detailed != CARD_PAYMENT_DETAILED:
        # Real cash out and real debt service. NOT net spending: the principal is
        # balance-sheet movement, and WLJ has no authoritative split (no LoanTerms
        # until P7). Recorded unsplit, with the limitation stated by the measure.
        return RoleAssignment(T.ROLE_DEBT_SERVICE, T.ROLE_CONFIDENCE_MEDIUM,
                              T.ROLE_SOURCE_PROVIDER, "provider_loan_payment")
    if amount < 0 and _is_liability_account(txn) and primary == LOAN_PAYMENT_PRIMARY:
        return RoleAssignment(T.ROLE_DEBT_SERVICE, T.ROLE_CONFIDENCE_MEDIUM,
                              T.ROLE_SOURCE_DERIVED, "liability_account_loan_payment")

    # ------------------------------------------------------------- 5. fees / cash
    if amount < 0 and _looks_like_fee(txn):
        return RoleAssignment(T.ROLE_FEE_INTEREST, T.ROLE_CONFIDENCE_MEDIUM,
                              T.ROLE_SOURCE_PROVIDER, "provider_fee_or_interest")
    if amount < 0 and _looks_like_cash(txn):
        # Cash left the account — certain. What it bought — unknown. WLJ refuses to
        # assume consumption OR harmless movement; either default is wrong for someone.
        return RoleAssignment(T.ROLE_CASH_WITHDRAWAL, T.ROLE_CONFIDENCE_MEDIUM,
                              T.ROLE_SOURCE_PROVIDER, "cash_withdrawal_unresolved")

    # ----------------------------------------------------------------- 6. income
    if amount > 0 and primary in INCOME_PRIMARIES:
        return RoleAssignment(T.ROLE_INCOME, T.ROLE_CONFIDENCE_HIGH,
                              T.ROLE_SOURCE_PROVIDER, "provider_income")

    # ------------------------------------------------- 7. unexplained credits
    # A credit that is neither income, refund nor transfer might be a reimbursement —
    # but WLJ cannot TELL them apart from provider data alone, and claiming a
    # reimbursement offset it cannot evidence would understate spending. Held.
    if amount > 0:
        return RoleAssignment(T.ROLE_UNCERTAIN, T.ROLE_CONFIDENCE_LOW,
                              T.ROLE_SOURCE_DERIVED, "unclassified_credit")

    # ---------------------------------------------------------- 8. the ordinary case
    if amount < 0:
        confidence = (T.ROLE_CONFIDENCE_HIGH if primary
                      else T.ROLE_CONFIDENCE_MEDIUM)
        return RoleAssignment(T.ROLE_PURCHASE, confidence,
                              T.ROLE_SOURCE_PROVIDER if primary
                              else T.ROLE_SOURCE_DERIVED,
                              "purchase" if primary else "purchase_no_provider_category")

    # A zero-amount row has no economic meaning to assign.
    return RoleAssignment(T.ROLE_UNCERTAIN, T.ROLE_CONFIDENCE_LOW,
                          T.ROLE_SOURCE_DERIVED, "zero_amount")


def classify_many(transactions):
    """`[(transaction, RoleAssignment)]`. Pure — persists nothing."""
    return [(txn, classify(txn)) for txn in transactions]
