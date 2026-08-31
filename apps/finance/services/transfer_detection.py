# ==============================================================================
# File: apps/finance/services/transfer_detection.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Decide, deterministically, what is a transfer and what is spending.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Moving your own money is not spending it.

Every wrong answer here corrupts a total. Two failures matter and they are not symmetric:

  * counting a transfer as spending **inflates** spending and manufactures false
    "business expense paid personally" findings;
  * counting spending as a transfer **hides** real money.

So the rule is: classify only on evidence, and when the evidence is partial, mark the row
a **candidate** — held out of totals AND sent to review. Never silently counted either way.

Evidence, strongest first:
  1. **The user said so** — outranks everything, permanently.
  2. **A matched pair** — two of the user's own accounts, opposite signs, same amount,
     within a few days. Both legs are linked and confirmed.
  3. **The provider said so** — `TRANSFER_IN` / `TRANSFER_OUT` / credit-card payment, or
     a `transfer` transaction code, at adequate confidence.
  4. **Shape alone** (an outflow naming one of the user's own liability accounts) —
     suggestive, never conclusive: **candidate**.

No model call. No per-transaction inference.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.db.models import Q

from apps.finance.models import FinancialAccount, Transaction

logger = logging.getLogger(__name__)

#: How far apart the two legs of one transfer may post.
PAIRING_WINDOW_DAYS = 5

#: Provider PRIMARY values that mean "money moved between accounts".
PROVIDER_TRANSFER_PRIMARIES = frozenset({"TRANSFER_IN", "TRANSFER_OUT"})
#: Provider DETAILED values that mean specifically "a credit-card bill was paid".
PROVIDER_CARD_PAYMENT_DETAILED = frozenset({
    "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT",
    "TRANSFER_OUT_ACCOUNT_TRANSFER",
})
#: Provider transaction codes that mean a transfer.
PROVIDER_TRANSFER_CODES = frozenset({"transfer", "bank transfer"})

LIABILITY_TYPES = (
    FinancialAccount.TYPE_CREDIT_CARD,
    FinancialAccount.TYPE_LOAN,
    FinancialAccount.TYPE_MORTGAGE,
    FinancialAccount.TYPE_STUDENT_LOAN,
    FinancialAccount.TYPE_OTHER_LIABILITY,
)

from apps.finance.services.category_taxonomy import TRUSTED_CONFIDENCE  # noqa: E402


def classify(transaction, *, liability_names=None, save=True):
    """Assign `transfer_state` / `transfer_kind` from the strongest available evidence.

    Returns the transaction. A user classification is never overwritten.
    """
    if transaction.transfer_classified_by == Transaction.TRANSFER_BY_USER:
        return transaction                      # the user has spoken; nothing outranks it

    state, kind, by = _assess(transaction, liability_names)
    changed = (transaction.transfer_state != state
               or transaction.transfer_kind != kind
               or transaction.transfer_classified_by != by)
    transaction.transfer_state = state
    transaction.transfer_kind = kind
    transaction.transfer_classified_by = by
    if save and changed:
        transaction.save(update_fields=["transfer_state", "transfer_kind",
                                        "transfer_classified_by", "updated_at"])
    return transaction


def _assess(txn, liability_names):
    # 2 — a matched pair is conclusive.
    if txn.transfer_pair_id:
        kind = (Transaction.TRANSFER_KIND_CARD_PAYMENT
                if _touches_liability(txn) else Transaction.TRANSFER_KIND_INTERNAL)
        return (Transaction.TRANSFER_STATE_CONFIRMED, kind,
                Transaction.TRANSFER_BY_PAIRING)

    # A transfer-typed category is conclusive about WHETHER it is a transfer. The KIND
    # still comes from the provider detail, so a card payment is not mislabelled as a
    # plain internal move.
    if txn.category_id and txn.category.category_type == "transfer":
        by = (Transaction.TRANSFER_BY_USER
              if txn.category_source == Transaction.CATEGORY_SOURCE_USER
              else Transaction.TRANSFER_BY_PROVIDER)
        return (Transaction.TRANSFER_STATE_CONFIRMED, _transfer_kind(txn), by)

    # 3 — the provider's own classification, when it is confident.
    detailed = (txn.provider_category_detailed or "").upper()
    primary = (txn.provider_category_primary or "").upper()
    confident = (txn.provider_category_confidence or "").upper() in TRUSTED_CONFIDENCE
    if confident and detailed in PROVIDER_CARD_PAYMENT_DETAILED and _touches_liability(txn):
        return (Transaction.TRANSFER_STATE_CONFIRMED,
                Transaction.TRANSFER_KIND_CARD_PAYMENT,
                Transaction.TRANSFER_BY_PROVIDER)
    if confident and detailed == "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT":
        return (Transaction.TRANSFER_STATE_CONFIRMED,
                Transaction.TRANSFER_KIND_CARD_PAYMENT,
                Transaction.TRANSFER_BY_PROVIDER)
    if confident and primary in PROVIDER_TRANSFER_PRIMARIES:
        return (Transaction.TRANSFER_STATE_CONFIRMED,
                Transaction.TRANSFER_KIND_INTERNAL,
                Transaction.TRANSFER_BY_PROVIDER)
    if (txn.provider_transaction_code or "").lower() in PROVIDER_TRANSFER_CODES:
        return (Transaction.TRANSFER_STATE_CONFIRMED,
                Transaction.TRANSFER_KIND_INTERNAL,
                Transaction.TRANSFER_BY_PROVIDER)

    # A refund is REAL money coming back — it offsets spending and stays in the totals.
    if txn.amount > 0 and _looks_like_refund(txn):
        return (Transaction.TRANSFER_STATE_NOT_TRANSFER,
                Transaction.TRANSFER_KIND_REFUND, Transaction.TRANSFER_BY_PROVIDER)

    # 4 — shape alone. Suggestive, never conclusive.
    if txn.amount < 0 and _names_own_liability(txn, liability_names):
        return (Transaction.TRANSFER_STATE_CANDIDATE,
                Transaction.TRANSFER_KIND_CARD_PAYMENT, "")
    if txn.amount < 0 and primary in PROVIDER_TRANSFER_PRIMARIES:
        # The provider hints at a transfer but is not confident — hold it.
        return (Transaction.TRANSFER_STATE_CANDIDATE,
                Transaction.TRANSFER_KIND_INTERNAL, "")

    return (Transaction.TRANSFER_STATE_NOT_TRANSFER, "", "")


def _transfer_kind(txn):
    """Card payment or plain internal movement? Decided from provider facts."""
    detailed = (txn.provider_category_detailed or "").upper()
    if "CREDIT_CARD_PAYMENT" in detailed or _touches_liability(txn):
        return Transaction.TRANSFER_KIND_CARD_PAYMENT
    if (txn.provider_category_primary or "").upper() == "LOAN_PAYMENTS":
        return Transaction.TRANSFER_KIND_CARD_PAYMENT
    return Transaction.TRANSFER_KIND_INTERNAL


def _touches_liability(txn):
    counterpart = txn.transfer_pair
    for account in (txn.account, getattr(counterpart, "account", None)):
        if account is not None and account.account_type in LIABILITY_TYPES:
            return True
    return False


def _looks_like_refund(txn):
    detailed = (txn.provider_category_detailed or "").upper()
    if "REFUND" in detailed:
        return True
    primary = (txn.provider_category_primary or "").upper()
    # An inflow the provider still classifies as a spending category is a refund of it.
    return bool(primary) and primary not in PROVIDER_TRANSFER_PRIMARIES \
        and primary != "INCOME"


def liability_account_names(user):
    return {(a.name or "").strip().casefold(): a
            for a in FinancialAccount.all_objects.filter(
                user=user, account_type__in=LIABILITY_TYPES).only(
                    "id", "name", "account_type")}


def _names_own_liability(txn, liability_names):
    if liability_names is None:
        liability_names = liability_account_names(txn.user)
    if not liability_names:
        return False
    haystack = " ".join(filter(None, [
        txn.description, txn.payee, txn.provider_merchant_name])).casefold()
    return any(name and name in haystack for name in liability_names)


def pair_transfers(user, *, window_days=PAIRING_WINDOW_DAYS, limit=2000):
    """Match unpaired legs of the same movement across the user's own accounts.

    Conservative by construction: exactly one candidate counterpart, or no pairing. An
    ambiguous match is left for review rather than guessed at.
    """
    unpaired = list(
        Transaction.objects.filter(user=user, transfer_pair__isnull=True)
        .exclude(is_opening_balance=True)
        .select_related("account")
        .order_by("date")[:limit]
    )
    by_id = {t.id: t for t in unpaired}
    paired = 0

    for txn in unpaired:
        if txn.transfer_pair_id or txn.amount >= 0:
            continue                            # drive from the OUTflow leg only
        window_start = txn.date - timedelta(days=window_days)
        window_end = txn.date + timedelta(days=window_days)
        candidates = [
            other for other in by_id.values()
            if other.id != txn.id
            and other.transfer_pair_id is None
            and other.account_id != txn.account_id
            and other.amount == -txn.amount
            and window_start <= other.date <= window_end
        ]
        if len(candidates) != 1:
            continue                            # zero or ambiguous — do not guess
        counterpart = candidates[0]
        txn.transfer_pair = counterpart
        counterpart.transfer_pair = txn
        txn.save(update_fields=["transfer_pair", "updated_at"])
        counterpart.save(update_fields=["transfer_pair", "updated_at"])
        classify(txn)
        classify(counterpart)
        paired += 1
    return paired


def classify_user_transactions(user, *, queryset=None):
    """Re-assess a user's transactions. ONE liability lookup for the whole batch."""
    names = liability_account_names(user)
    rows = queryset if queryset is not None else Transaction.objects.filter(user=user)
    counts = {"confirmed": 0, "candidate": 0, "not_transfer": 0, "skipped_user": 0}
    for txn in rows.select_related("account", "category").iterator(chunk_size=500):
        if txn.transfer_classified_by == Transaction.TRANSFER_BY_USER:
            counts["skipped_user"] += 1
            continue
        classify(txn, liability_names=names)
        counts[txn.transfer_state] = counts.get(txn.transfer_state, 0) + 1
    return counts


def confirm_transfer(user, transaction, *, is_transfer, kind=""):
    """The user settles an ambiguous case. Their answer outranks everything, forever."""
    if transaction.user_id != user.id:
        raise ValueError("Cross-user transfer confirmation rejected.")
    transaction.transfer_state = (Transaction.TRANSFER_STATE_CONFIRMED if is_transfer
                                  else Transaction.TRANSFER_STATE_NOT_TRANSFER)
    transaction.transfer_kind = kind if is_transfer else ""
    transaction.transfer_classified_by = Transaction.TRANSFER_BY_USER
    transaction.save(update_fields=["transfer_state", "transfer_kind",
                                    "transfer_classified_by", "updated_at"])
    return transaction


# ---------------------------------------------------------------------------
# Liability-credit pairing (Finance 2.0 completion)
# ---------------------------------------------------------------------------

#: Liabilities where a credit can ONLY be a payment received — you cannot draw more on
#: a closed-end loan. Pairing never reclassifies these: they are already debt service,
#: and turning a mortgage payment into a card payment is the defect that removed it
#: from every measure once before.
CLOSED_END_TYPES = frozenset({
    FinancialAccount.TYPE_LOAN,
    FinancialAccount.TYPE_MORTGAGE,
    FinancialAccount.TYPE_STUDENT_LOAN,
})


def _counterpart_free(txn):
    """Nothing claims this row as its pair, from either direction.

    `transfer_pair` is a OneToOne, so only one leg carries the column. Checking a
    single direction is how a row gets claimed twice.
    """
    from django.core.exceptions import ObjectDoesNotExist

    if txn.transfer_pair_id:
        return False
    try:
        txn.transfer_counterpart
    except ObjectDoesNotExist:
        return True
    return False


def _is_liability(txn):
    account = getattr(txn, "account", None)
    return bool(account is not None and getattr(account, "is_liability", False))


def pair_liability_credits(user, *, window_days=PAIRING_WINDOW_DAYS):
    """Match credits on revolving liabilities to the payment that produced them.

    The narrow residual left by the P1 work: a credit lands on a credit card and WLJ
    cannot tell a payment arriving from new borrowing, because the provider category
    does not distinguish them. When the funding leg is visible and unambiguous, it does.

    Deliberately conservative, in the same way `pair_transfers` is:

    * **Exactly one** candidate, or nothing happens. Several possible counterparts stay
      held — picking one is precisely the error the review queue exists to prevent.
    * **Closed-end debt is never touched.** A mortgage credit is already debt service.
    * **A row is claimed once.** Both legs are re-read `FOR UPDATE` and re-checked
      inside the transaction, so two concurrent runs cannot both claim the same leg.
    * **Idempotent.** An already-paired row is skipped, so running it twice pairs
      nothing the second time.

    Returns a report. Roles are NOT re-derived here — that is the caller's decision,
    because reclassification is a separate, auditable step.
    """
    from django.db import transaction as db_transaction

    held = list(
        Transaction.objects.filter(
            user=user,
            economic_role=Transaction.ROLE_UNCERTAIN,
            role_reason="unmatched_liability_credit")
        .select_related("account")
        .order_by("date", "id"))

    pool = list(
        Transaction.objects.filter(user=user)
        .exclude(is_opening_balance=True)
        .select_related("account")
        .order_by("date", "id"))

    report = {"considered": len(held), "paired": 0, "ambiguous": 0,
              "no_counterpart": 0, "skipped_closed_end": 0, "skipped_already": 0,
              "lost_race": 0, "window_days": window_days}

    for txn in held:
        account_type = getattr(getattr(txn, "account", None), "account_type", "")
        if account_type in CLOSED_END_TYPES:
            report["skipped_closed_end"] += 1
            continue
        if not _counterpart_free(txn):
            report["skipped_already"] += 1
            continue

        window_start = txn.date - timedelta(days=window_days)
        window_end = txn.date + timedelta(days=window_days)
        target = -txn.amount
        # The counterpart must look like the leg that FUNDED the payment: money
        # leaving an account that holds money. Every one of the 25 unambiguous matches
        # in the 2026-08-31 production rehearsal was exactly that — a chequing outflow
        # the provider called LOAN_PAYMENTS facing a card credit it called
        # LOAN_DISBURSEMENTS. Requiring it costs nothing today and refuses a whole
        # class of wrong match later: a card-to-card balance transfer stays held rather
        # than being asserted as a payment.
        candidates = [
            other for other in pool
            if other.id != txn.id
            and other.account_id != txn.account_id
            and other.amount == target
            and (other.amount or 0) < 0
            and not _is_liability(other)
            and window_start <= other.date <= window_end
            and _counterpart_free(other)
        ]
        if not candidates:
            report["no_counterpart"] += 1
            continue
        if len(candidates) > 1:
            report["ambiguous"] += 1
            continue

        counterpart = candidates[0]
        if not _claim(txn.pk, counterpart.pk):
            # Another worker took one of the legs between the read and the write.
            report["lost_race"] += 1
            continue

        report["paired"] += 1
        # Keep the in-memory pool honest so the NEXT row cannot propose the same leg.
        # Which row physically holds the column does not matter here — what matters is
        # that neither is offered again.
        txn.transfer_pair_id = counterpart.pk
        counterpart.transfer_pair_id = txn.pk

    return report


def _claim(txn_pk, counterpart_pk):
    """Link two legs atomically, or refuse. Returns True when the claim succeeded.

    The read that found the candidate and the write that claims it are not one step, so
    both rows are re-read `FOR UPDATE` and re-checked here. Without this, two concurrent
    passes — a manual run and a scheduled one — can each believe a leg is free.
    """
    from django.db import transaction as db_transaction

    with db_transaction.atomic():
        rows = {
            row.pk: row for row in
            Transaction.objects.select_for_update()
            .filter(pk__in=[txn_pk, counterpart_pk])
            .select_related("account")
        }
        txn, counterpart = rows.get(txn_pk), rows.get(counterpart_pk)
        if txn is None or counterpart is None:
            return False
        if txn.user_id != counterpart.user_id:
            # Cannot happen through this path, and would be a serious defect if it did.
            logger.error("Refused a cross-user transfer pair: %s / %s",
                         txn_pk, counterpart_pk)
            return False
        if not _counterpart_free(txn) or not _counterpart_free(counterpart):
            return False

        # The OUTFLOW leg carries the link, exactly as `pair_transfers` does it.
        # `transfer_pair` is a OneToOne, so only one row can hold the column, and
        # `_assess` reads `transfer_pair_id` in one direction only — put the link on
        # the leg that convention already expects to find it on, or the payment leg
        # stays classified as an ordinary purchase and the card payment becomes
        # spending.
        holder, other = ((txn, counterpart) if (txn.amount or 0) < 0
                         else (counterpart, txn))
        holder.transfer_pair = other
        holder.save(update_fields=["transfer_pair", "updated_at"])
        names = liability_account_names(holder.user)
        classify(holder, liability_names=names)
        classify(other, liability_names=names)
        return True


def pairing_coverage(user):
    """How much of this user's history the pairing pass can actually see.

    Lives HERE, in the pairing authority, rather than in the module that reports it.
    Counting unpaired rows means querying `transfer_pair__isnull`, and a constitutional
    contract test forbids any surface outside the population authority from writing that
    predicate — correctly, because it is one edit away from becoming a second definition
    of what counts as activity. The authority is allowed to describe itself.
    """
    total = Transaction.objects.filter(user=user).exclude(
        is_opening_balance=True).count()
    unpaired = Transaction.objects.filter(
        user=user, transfer_pair__isnull=True).exclude(
        is_opening_balance=True).count()
    return {
        "transactions": total,
        "unpaired": unpaired,
        "pass_reads_at_most": 2000,
        "limit_truncates": unpaired > 2000,
        "window_days": PAIRING_WINDOW_DAYS,
        "note": ("`pair_transfers` reads at most 2,000 unpaired rows ordered by date. "
                 "Above that it silently stops looking, and the rows it drops are the "
                 "most recent ones."),
    }
