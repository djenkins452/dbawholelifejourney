# ==============================================================================
# File: apps/finance/services/attribution_population.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: F0 — THE authority for which transactions may be attributed.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""One definition of "a transaction that counts", for attribution and detection.

WHY THIS EXISTS. Finance had FOUR competing populations and TWO incompatible definitions
of "transfer":

    Budget.spent_amount            (models.py:661)  — no transfer OR opening exclusion
    FinancialMetricSnapshot        (models.py:1065) — excludes by `transfer_pair`
    FinanceHistory._monthly_rows   (finance_history.py:57) — excludes by category type
    FinanceDomainTruth.describe    (finance_domain_truth.py:81) — excludes neither

And `transfer_pair` is set in exactly ONE place in the codebase — the manual transfer form
(`forms.py:526`). Plaid sync and the file importer never set it. So an imported card
payment from a personal account to a business card looks exactly like an expense. Silently
attributing it would make the F1 detector flag the very correction the user is trying to
make.

THE CONTRACT (conservative by decision):
  * excluded outright  — soft-deleted/archived, opening balances, known transfers
  * needs_review       — structurally uncertain: pending, or a suspected unpaired internal
                         transfer (a payment toward one of the user's own liability
                         accounts). Surfaced, never silently attributed, never dropped.
  * attributable       — everything else, INCLUDING income, refunds, and reversals: a
                         business deposit landing in a personal account is a mismatch too.
                         Direction is the detector's concern, not the population's.

No automatic transfer pairing happens here — that needs deterministic evidence a later
phase can defend.
"""
from __future__ import annotations

from django.db.models import Q

from apps.finance.models import FinancialAccount, Transaction

# ── exclusion reasons ──────────────────────────────────────────────────────────
EXCLUDED_INACTIVE = "inactive"
EXCLUDED_OPENING_BALANCE = "opening_balance"
EXCLUDED_PAIRED_TRANSFER = "paired_transfer"
EXCLUDED_TRANSFER_CATEGORY = "transfer_category"
REVIEW_PENDING = "pending"
REVIEW_SUSPECTED_INTERNAL_TRANSFER = "suspected_internal_transfer"
REVIEW_AMBIGUOUS_TRANSFER = "ambiguous_transfer"
EXCLUDED_CONFIRMED_TRANSFER = "confirmed_transfer"
EXCLUDED_CARD_PAYMENT = "credit_card_payment"

#: Excluded from attribution but NOT settled — F2 shows these; F1 must never treat them
#: as ordinary expenses.
NEEDS_REVIEW_REASONS = frozenset({
    REVIEW_PENDING, REVIEW_SUSPECTED_INTERNAL_TRANSFER, REVIEW_AMBIGUOUS_TRANSFER,
})

#: Account types that represent money the user OWES — a payment toward one of these from
#: another of their own accounts is an internal movement, not a business expense.
LIABILITY_ACCOUNT_TYPES = (
    FinancialAccount.TYPE_CREDIT_CARD,
    FinancialAccount.TYPE_LOAN,
    FinancialAccount.TYPE_MORTGAGE,
    FinancialAccount.TYPE_STUDENT_LOAN,
    FinancialAccount.TYPE_OTHER_LIABILITY,
)

def financial_activity(user, *, start=None, end=None):
    """THE shared definition of real economic activity — for reporting AND attribution.

    Active, not an opening balance, and not a transfer under EITHER signal. This is the
    definition Budget, FinanceHistory, the metric snapshots, the dashboard, and
    `FinanceDomainTruth` all consume, so they can no longer disagree about what counts
    (Article III.1).

    It deliberately does NOT apply the attribution-only exclusions (pending rows and
    suspected internal transfers): those express "we are not sure enough to CLASSIFY
    this", which is a different question from "did money actually move". Reporting keeps
    showing the user their real activity; attribution is the cautious one.

    It DOES exclude ambiguous transfers, because a possible transfer counted as spending
    inflates every total built on it. Those rows are surfaced by `review_candidates`
    instead of being silently counted either way.
    """
    qs = (_base(user).filter(is_opening_balance=False)
          .exclude(_known_transfer_q())
          .exclude(_ambiguous_transfer_q()))
    if start:
        qs = qs.filter(date__gte=start)
    if end:
        qs = qs.filter(date__lte=end)
    return qs


def _base(user):
    """Soft-deleted/archived rows are excluded by the default manager itself
    (`SoftDeleteManager`, apps/core/models.py:71) — we do not repeat `status='active'`."""
    return Transaction.objects.filter(user=user)


def _known_transfer_q():
    """Everything CONFIRMED to be movement of the user's own money.

    Three signals unioned: the explicit `transfer_state` (set by `transfer_detection`
    from provider facts, pairing, or the user), a matched pair, and a transfer-typed
    category. The latter two are kept so manually-created and legacy rows keep behaving.
    """
    from apps.finance.models import Transaction as _T

    return (Q(transfer_state=_T.TRANSFER_STATE_CONFIRMED)
            | Q(transfer_pair__isnull=False)
            | Q(category__category_type="transfer"))


def _ambiguous_transfer_q():
    """Possible transfers: held OUT of totals AND sent to review — never guessed."""
    from apps.finance.models import Transaction as _T

    return Q(transfer_state=_T.TRANSFER_STATE_CANDIDATE)


def liability_account_names(user):
    """{normalized name: account} for the user's own liability accounts."""
    rows = FinancialAccount.all_objects.filter(
        user=user, account_type__in=LIABILITY_ACCOUNT_TYPES,
    ).only("id", "name", "account_type")
    return {(a.name or "").strip().casefold(): a for a in rows}


def suspected_internal_transfer_q(user, liability_names=None):
    """Queryset form of the suspicion, so it filters in SQL rather than per row.

    An OUTGOING transaction naming one of the user's own liability accounts is very
    probably a payment toward that account — an internal movement, not a business expense.
    Bounded: one clause per liability account, and users have a handful.
    """
    if liability_names is None:
        liability_names = liability_account_names(user)
    names = [n for n in liability_names if n]
    if not names:
        return Q(pk__in=[])
    text = Q()
    for name in names:
        text |= Q(description__icontains=name) | Q(payee__icontains=name)
    return Q(amount__lt=0) & text


def looks_like_internal_transfer(transaction, liability_names=None) -> bool:
    """Deterministic, conservative suspicion — never an automatic pairing.

    True when an outgoing transaction names one of the user's own liability accounts, or
    reads as a payment toward one. It is a REVIEW signal only: WLJ says "I am not sure",
    which is honest truth, rather than inventing a pairing it cannot prove.
    """
    if transaction.amount >= 0:
        return False
    if liability_names is None:
        liability_names = liability_account_names(transaction.user)
    haystack = f"{transaction.description or ''} {transaction.payee or ''}".casefold()
    if not haystack.strip():
        return False
    for name in liability_names:
        if name and name in haystack:
            return True
    return False


def attributable_transactions(user, *, start=None, end=None, liability_names=None):
    """THE attributable population. One queryset, index-friendly, no per-row work.

    Costs one small lookup of the user's liability-account names plus the query itself.
    Batch callers (F1) hoist that lookup once via `liability_account_names(user)` and pass
    it in, so scanning ten transactions and ten thousand costs the same number of queries.
    """
    qs = financial_activity(user)
    qs = qs.exclude(plaid_pending=True)
    # Structurally uncertain rows are EXCLUDED here and surfaced by `review_candidates`.
    # Nothing uncertain is quietly turned into an expense to empty a queue.
    qs = qs.exclude(suspected_internal_transfer_q(user, liability_names))
    if start:
        qs = qs.filter(date__gte=start)
    if end:
        qs = qs.filter(date__lte=end)
    return qs


def review_candidates(user, *, start=None, end=None, liability_names=None):
    """Structurally uncertain rows: pending, plus suspected unpaired internal transfers.

    Kept OUT of the attributable population and surfaced explicitly, so nothing uncertain
    is quietly turned into an expense in order to empty a queue.
    """
    # Review candidates deliberately IGNORE the ambiguity exclusion — that is the whole
    # point: rows held out of the totals must still be visible to a person.
    base = (_base(user).filter(is_opening_balance=False).exclude(_known_transfer_q()))
    if start:
        base = base.filter(date__gte=start)
    if end:
        base = base.filter(date__lte=end)
    return base.filter(
        Q(plaid_pending=True)
        | _ambiguous_transfer_q()
        | suspected_internal_transfer_q(user, liability_names))


def exclusion_reason(transaction, liability_names=None):
    """Why one transaction is not attributable — or None when it is.

    Facts, not verdicts: the caller decides what to do about it.
    """
    if getattr(transaction, "status", "active") != "active":
        return EXCLUDED_INACTIVE
    if transaction.is_opening_balance:
        return EXCLUDED_OPENING_BALANCE
    from apps.finance.models import Transaction as _T

    # `transfer_state` is the modern authority and is the only signal that knows the
    # KIND, so it is consulted before the older pair/category signals — a card payment
    # must not be reported as a generic "transfer category".
    if transaction.transfer_state == _T.TRANSFER_STATE_CONFIRMED:
        return (EXCLUDED_CARD_PAYMENT
                if transaction.transfer_kind == _T.TRANSFER_KIND_CARD_PAYMENT
                else EXCLUDED_CONFIRMED_TRANSFER)
    if transaction.transfer_pair_id:
        return EXCLUDED_PAIRED_TRANSFER
    category = transaction.category
    if category is not None and category.category_type == "transfer":
        return EXCLUDED_TRANSFER_CATEGORY
    if transaction.plaid_pending:
        return REVIEW_PENDING
    if transaction.transfer_state == _T.TRANSFER_STATE_CANDIDATE:
        return REVIEW_AMBIGUOUS_TRANSFER
    if looks_like_internal_transfer(transaction, liability_names):
        return REVIEW_SUSPECTED_INTERNAL_TRANSFER
    return None


def is_attributable(transaction, liability_names=None) -> bool:
    return exclusion_reason(transaction, liability_names) is None
