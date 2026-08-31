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
CLASSIFIER_VERSION = "1.2.0"

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

#: Borrowed money ARRIVING. The 2026-08-30 rehearsal found 259,531.55 of this
#: classified as refunds, offsetting purchases and driving net spending negative in 9
#: of 25 months, because the upstream `_looks_like_refund` treats any credit that is
#: neither a transfer nor INCOME as a refund. Borrowing is real cash in and it is
#: neither income nor a refund — it has to be given back.
LOAN_PROCEEDS_PRIMARIES = frozenset({"LOAN_DISBURSEMENTS", "LOAN_DISBURSEMENT"})
LOAN_PROCEEDS_DETAILED_HINTS = ("LOAN_DISBURSEMENT", "CASH_ADVANCES_AND_LOANS",
                                "LINE_OF_CREDIT", "STUDENT_LOAN_DISBURSEMENT")

#: Evidence that a credit really is money coming BACK from a purchase.
REFUND_DETAILED_HINTS = ("REFUND", "RETURN")
REVERSAL_DETAILED_HINTS = ("CHARGEBACK", "DISPUTE", "REVERSAL", "ADJUSTMENT")

#: Liability accounts whose payment settles revolving purchases already counted as
#: spending. Everything else on the liability side is debt service.
REVOLVING_LIABILITY_TYPES = frozenset({"credit_card"})

#: CLOSED-END debt: a fixed sum, repaid on a schedule. You cannot draw more on one, so
#: a credit arriving on it can only be a payment received. That is a fact about the
#: INSTRUMENT, which is why it is safe to rely on where a provider category is not.
CLOSED_END_LIABILITY_TYPES = frozenset({"mortgage", "loan", "student_loan"})

#: Accounts that actually hold the household's cash. A payment landing on a credit card
#: is not money arriving; measuring cash where the cash is keeps the difference honest.
CASH_ACCOUNT_TYPES = frozenset({"checking", "savings", "cash"})


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


def _looks_like_loan_proceeds(txn):
    """Borrowed money arriving — a draw, an advance, a disbursement."""
    if _primary(txn) in LOAN_PROCEEDS_PRIMARIES:
        return True
    detailed = _detailed(txn)
    return any(hint in detailed for hint in LOAN_PROCEEDS_DETAILED_HINTS)


def _refund_evidence(txn):
    """Why WLJ believes this credit is money coming back — or `None`.

    A refund OFFSETS spending, so it needs evidence, not a shape. The upstream
    `transfer_detection._looks_like_refund` is deliberately generous — it answers "is
    this a transfer?", where a wrong `kind` on a NOT_TRANSFER row costs nothing. Here
    the same guess would silently reduce net spending, so P1 tests the evidence itself
    rather than inheriting that verdict.

    Returns `(reason, confidence, source)` or `None`.
    """
    from apps.finance.models import Transaction as T

    # A proven relationship to the original purchase. Nothing beats this.
    if getattr(txn, "refund_of_id", None):
        return ("linked_refund_of_purchase", T.ROLE_CONFIDENCE_HIGH,
                T.ROLE_SOURCE_PAIRING)

    detailed = _detailed(txn)
    if any(hint in detailed for hint in REVERSAL_DETAILED_HINTS):
        return ("provider_reversal_or_chargeback", T.ROLE_CONFIDENCE_HIGH,
                T.ROLE_SOURCE_PROVIDER)
    if any(hint in detailed for hint in REFUND_DETAILED_HINTS):
        return ("provider_states_refund", T.ROLE_CONFIDENCE_HIGH,
                T.ROLE_SOURCE_PROVIDER)
    return None


def counterpart(txn):
    """The other leg of a matched transfer, whichever side holds the link.

    `transfer_pair` is a OneToOne, so only ONE of the two rows carries it; the other
    reaches back through `transfer_counterpart`. Checking a single direction would make
    a payment look paired from one leg and unpaired from the other — which is how a
    de-duplicated total quietly starts double counting.
    """
    from django.core.exceptions import ObjectDoesNotExist

    pair = getattr(txn, "transfer_pair", None)
    if pair is not None:
        return pair
    try:
        return txn.transfer_counterpart
    except ObjectDoesNotExist:
        return None


def _settled_liability_type(txn):
    """Which liability does this payment settle? Own account first, then its pair.

    A payment has two legs and only one of them sits on the liability. Reading the
    other leg is what tells a mortgage payment apart from a card payment — from the
    cash side alone the two look identical.
    """
    account = getattr(txn, "account", None)
    if account is not None and getattr(account, "is_liability", False):
        return getattr(account, "account_type", "") or ""
    other = counterpart(txn)
    other_account = getattr(other, "account", None) if other is not None else None
    if other_account is not None and getattr(other_account, "is_liability", False):
        return getattr(other_account, "account_type", "") or ""
    return ""


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

    # ------------------------------------------------- 0b. a role the USER decided
    # Once a person tells WLJ what a transaction is, no derivation may take it back.
    # Returning it here (rather than only skipping it in the backfill) makes the rule
    # true of the classifier itself, so every caller inherits it.
    if txn.economic_role and txn.role_source == T.ROLE_SOURCE_USER:
        return RoleAssignment(txn.economic_role, T.ROLE_CONFIDENCE_HIGH,
                              T.ROLE_SOURCE_USER,
                              txn.role_reason or "user_confirmed_role",
                              txn.role_classifier_version or CLASSIFIER_VERSION)

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
            # `transfer_detection._transfer_kind` calls ANY transfer touching a
            # liability a card payment. That is fine for its own question, but here it
            # would drop mortgage and instalment payments out of spending (right) AND
            # out of debt service (wrong) — the 2026-08-30 rehearsal showed exactly
            # that. Only revolving credit settles purchases already counted.
            liability = _settled_liability_type(txn)
            if liability and liability not in REVOLVING_LIABILITY_TYPES:
                return RoleAssignment(T.ROLE_DEBT_SERVICE, T.ROLE_CONFIDENCE_HIGH,
                                      source, "confirmed_non_card_debt_payment")
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

    # ------------------------------- 2. a credit landing on a liability account
    # The 2026-08-31 rehearsal made this necessary. 249,246.70 of credits on a credit
    # card carried the provider category LOAN_DISBURSEMENTS, which reads as borrowing —
    # but each one matched, to the cent and to the month, a payment leaving checking
    # that the provider labelled a credit-card payment. Removing them made cash inflow
    # equal income plus refunds EXACTLY, which is the arithmetic of money that never
    # entered the household at all.
    #
    # So the provider category cannot separate "a payment arrived" from "I borrowed
    # more" on a revolving account. The INSTRUMENT can:
    if amount > 0 and _is_liability_account(txn):
        liability_type = _account_type(txn)
        if liability_type in CLOSED_END_LIABILITY_TYPES:
            # Nothing can be drawn on a closed-end loan, so this is a payment received.
            return RoleAssignment(T.ROLE_DEBT_SERVICE, T.ROLE_CONFIDENCE_HIGH,
                                  T.ROLE_SOURCE_DERIVED,
                                  "payment_received_on_closed_end_loan")
        if counterpart(txn) is not None:
            # Revolving, and WLJ can see the other leg: it is a card payment.
            return RoleAssignment(T.ROLE_CARD_PAYMENT, T.ROLE_CONFIDENCE_HIGH,
                                  T.ROLE_SOURCE_PAIRING, "paired_card_payment")
        # Revolving, no visible counterpart. It is a payment or it is borrowing, and
        # WLJ cannot tell. Held — the row keeps its place and enters no measure that
        # would state one reading as fact. A genuine cash advance still shows up as
        # cash where it lands, on the cash account.
        return RoleAssignment(T.ROLE_UNCERTAIN, T.ROLE_CONFIDENCE_LOW,
                              T.ROLE_SOURCE_DERIVED, "unmatched_liability_credit")

    # -------------------------------------------- 3. borrowed money arriving
    # Checked BEFORE refunds, because a loan draw satisfies the generous upstream
    # refund shape and would otherwise offset spending with money that must be repaid.
    # Reached only for a CASH account now: a loan funding a chequing account really is
    # money arriving, and it really is not income.
    if amount > 0 and _looks_like_loan_proceeds(txn):
        return RoleAssignment(T.ROLE_LOAN_PROCEEDS, T.ROLE_CONFIDENCE_HIGH,
                              T.ROLE_SOURCE_PROVIDER, "loan_proceeds_received")

    # ------------------------------------------------------ 4. refund / reversal
    # Evidence only. `transfer_kind == refund` is NOT evidence — see `_refund_evidence`.
    if amount > 0:
        evidence = _refund_evidence(txn)
        if evidence:
            reason, confidence, source = evidence
            role = (T.ROLE_REVERSAL if reason == "provider_reversal_or_chargeback"
                    else T.ROLE_REFUND)
            return RoleAssignment(role, confidence, source, reason)

    # ----------------------------------------------- 5. held-for-review transfers
    # A possible transfer whose counterpart WLJ cannot see. The cash genuinely moved —
    # that is not in doubt — but its economic meaning is. It keeps its cash movement
    # and enters NO spending measure.
    if txn.transfer_state == T.TRANSFER_STATE_CANDIDATE:
        return RoleAssignment(T.ROLE_UNCERTAIN, T.ROLE_CONFIDENCE_LOW,
                              T.ROLE_SOURCE_DERIVED, "unmatched_transfer_candidate")

    # --------------------------------------------------------- 6. debt servicing
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

    # ------------------------------------------------------------- 7. fees / cash
    if amount < 0 and _looks_like_fee(txn):
        return RoleAssignment(T.ROLE_FEE_INTEREST, T.ROLE_CONFIDENCE_MEDIUM,
                              T.ROLE_SOURCE_PROVIDER, "provider_fee_or_interest")
    if amount < 0 and _looks_like_cash(txn):
        # Cash left the account — certain. What it bought — unknown. WLJ refuses to
        # assume consumption OR harmless movement; either default is wrong for someone.
        return RoleAssignment(T.ROLE_CASH_WITHDRAWAL, T.ROLE_CONFIDENCE_MEDIUM,
                              T.ROLE_SOURCE_PROVIDER, "cash_withdrawal_unresolved")

    # ----------------------------------------------------------------- 8. income
    if amount > 0 and primary in INCOME_PRIMARIES:
        return RoleAssignment(T.ROLE_INCOME, T.ROLE_CONFIDENCE_HIGH,
                              T.ROLE_SOURCE_PROVIDER, "provider_income")

    # ------------------------------------------------- 9. ambiguous credits
    # Money arrived and WLJ cannot say why. It might be a reimbursement, a refund the
    # provider did not label, or a transfer from an account WLJ cannot see. Each of
    # those would change a different measure, so it is held for review and enters
    # NEITHER income nor any spending offset — while its cash movement stays real.
    if amount > 0:
        return RoleAssignment(T.ROLE_UNCERTAIN, T.ROLE_CONFIDENCE_LOW,
                              T.ROLE_SOURCE_DERIVED, "ambiguous_credit")

    # --------------------------------------------------------- 10. the ordinary case
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
