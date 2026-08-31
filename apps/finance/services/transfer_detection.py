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
from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal

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


def paired_counterpart(txn):
    """The other leg of a matched transfer, from EITHER side.

    `transfer_pair` is a OneToOne, so only ONE of the two rows physically carries the
    column; the other reaches back through the reverse accessor. Reading a single
    direction — which `_assess` did until 2026-08-31 — means the leg without the column
    is not recognised as paired at all, and a settled card payment stays classified as
    an ordinary purchase. That is a card payment silently becoming spending.
    """
    from django.core.exceptions import ObjectDoesNotExist

    pair = getattr(txn, "transfer_pair", None)
    if pair is not None:
        return pair
    try:
        return txn.transfer_counterpart
    except ObjectDoesNotExist:
        return None


def is_paired(txn):
    return paired_counterpart(txn) is not None


def _assess(txn, liability_names):
    # 2 — a matched pair is conclusive, whichever leg holds the link.
    counterpart = paired_counterpart(txn)
    if counterpart is not None:
        # The KIND is decided by the pair as a whole: if EITHER leg touches a
        # liability, the movement settled a debt. Asking only about this leg makes the
        # chequing side of a card payment look like a plain internal transfer.
        touches = _touches_liability(txn) or _touches_liability(counterpart)
        kind = (Transaction.TRANSFER_KIND_CARD_PAYMENT
                if touches else Transaction.TRANSFER_KIND_INTERNAL)
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


def pair_transfers(user, *, window_days=PAIRING_WINDOW_DAYS, limit=None):
    """Compatibility wrapper. Pairs the FULL population unless a limit is forced.

    The old signature defaulted to `limit=2000` and silently stopped there — on a
    3,800-row history that dropped the most recent third, which is precisely where the
    still-unpaired legs live. The default is now "all of it"; a caller that genuinely
    wants a bounded slice has to ask for one.
    """
    return pair_all(user, window_days=window_days, limit=limit)["paired"]


def _eligible_population(user):
    """Every row that could take part in a pair. ONE query, no cap.

    `select_related` covers the account and BOTH directions of the pair link, because
    deciding whether a row is already paired reads the reverse accessor — and doing that
    lazily is one query per row over the whole history.
    """
    return list(
        Transaction.objects.filter(user=user)
        .exclude(is_opening_balance=True)
        .select_related("account", "category",
                        "transfer_pair", "transfer_pair__account",
                        "transfer_counterpart", "transfer_counterpart__account")
        .order_by("date", "id")
    )


def _propose_pairs(user, *, window_days=PAIRING_WINDOW_DAYS, population=None):
    """Work out every deterministic pair. Pure — decides, writes nothing.

    Shared by the rehearsal and the apply pass so the two can never disagree about what
    would happen.

    **A match must be mutually unique.** It is not enough that an outflow has exactly one
    candidate: that candidate must also have exactly one candidate outflow. Checking only
    one direction makes pairing order-dependent — one credit that could belong to either
    of two payments gets silently attached to whichever payment is processed first, which
    is guessing dressed up as determinism. Ambiguity has to be visible from both sides to
    be honoured.
    """
    rows = population if population is not None else _eligible_population(user)

    counts = {"population": len(rows), "eligible_outflows": 0,
              "already_paired": 0, "proposed": 0, "ambiguous": 0,
              "unmatched": 0, "skipped_user_confirmed": 0}
    proposals, ambiguous = [], []

    free = [t for t in rows if not is_paired(t)]
    counts["already_paired"] = len(rows) - len(free)

    # Bucket by absolute amount so each row inspects only same-magnitude rows instead of
    # the whole history. Without this the pass is O(n^2) on a real ledger.
    by_amount = defaultdict(list)
    for row in free:
        if (row.amount or 0) != 0 and \
                row.transfer_classified_by != Transaction.TRANSFER_BY_USER:
            by_amount[abs(row.amount)].append(row)

    def candidates_for(txn):
        window_start = txn.date - timedelta(days=window_days)
        window_end = txn.date + timedelta(days=window_days)
        target = -txn.amount
        return [
            other for other in by_amount.get(abs(txn.amount or 0), ())
            if other.id != txn.id
            and other.account_id != txn.account_id
            and other.amount == target
            and window_start <= other.date <= window_end
        ]

    outflows = [t for t in free if (t.amount or 0) < 0]
    counts["eligible_outflows"] = len(
        [t for t in outflows
         if t.transfer_classified_by != Transaction.TRANSFER_BY_USER])

    for txn in outflows:
        if txn.transfer_classified_by == Transaction.TRANSFER_BY_USER:
            # A decision the person made is not a hypothesis for pairing to overturn.
            counts["skipped_user_confirmed"] += 1
            continue

        candidates = candidates_for(txn)
        if not candidates:
            counts["unmatched"] += 1
            continue
        if len(candidates) > 1:
            counts["ambiguous"] += 1
            ambiguous.append((txn, candidates))
            continue

        counterpart = candidates[0]
        back = candidates_for(counterpart)
        if len(back) != 1 or back[0].id != txn.id:
            # The counterpart could equally belong to another payment. Attaching it to
            # this one would be arbitrary, and arbitrary is what the review queue is for.
            counts["ambiguous"] += 1
            ambiguous.append((txn, back or candidates))
            continue

        proposals.append((txn, counterpart))
        counts["proposed"] += 1

    return proposals, ambiguous, counts


def pair_all(user, *, window_days=PAIRING_WINDOW_DAYS, limit=None, batch_size=500):
    """Pair the whole eligible population. Bounded batches, never a silent cap.

    `limit` exists only so a caller can deliberately bound a run; when it bites, the
    report says so in `skipped_over_limit` rather than quietly returning a smaller
    number. Idempotent: a second run proposes nothing because every row it paired is
    now paired.
    """
    population = _eligible_population(user)
    if limit is not None:
        skipped = max(0, len(population) - limit)
        population = population[:limit]
    else:
        skipped = 0

    proposals, ambiguous, counts = _propose_pairs(
        user, window_days=window_days, population=population)

    paired, lost_race = 0, 0
    for start in range(0, len(proposals), batch_size):
        for txn, counterpart in proposals[start:start + batch_size]:
            if _claim_pair(txn.pk, counterpart.pk):
                paired += 1
            else:
                lost_race += 1

    counts.update({
        "paired": paired,
        "lost_race": lost_race,
        "skipped_over_limit": skipped,
        "truncated": bool(skipped),
        "window_days": window_days,
        "batch_size": batch_size,
    })
    return counts


def rehearse_pairing(user, *, window_days=PAIRING_WINDOW_DAYS, sample=4):
    """What full-population pairing WOULD do. Writes nothing.

    The same `_propose_pairs` the apply pass uses, so a rehearsal cannot describe a
    different plan from the one that runs.
    """
    population = _eligible_population(user)
    proposals, ambiguous, counts = _propose_pairs(
        user, window_days=window_days, population=population)

    def _redacted(txn, other=None):
        row = {
            "month": f"{txn.date.year:04d}-{txn.date.month:02d}",
            "magnitude": _magnitude(txn.amount),
            "direction": "in" if (txn.amount or 0) > 0 else "out",
            "account_type": getattr(getattr(txn, "account", None), "account_type", ""),
            "provider_primary": (txn.provider_category_primary or "")[:32],
            "role": txn.economic_role,
        }
        if other is not None:
            row["counterpart_account_type"] = getattr(
                getattr(other, "account", None), "account_type", "")
            row["counterpart_primary"] = (other.provider_category_primary or "")[:32]
            row["counterpart_role"] = other.economic_role
        return row

    counterpart_roles = Counter()
    driver_roles = Counter()
    for txn, other in proposals:
        counterpart_roles[other.economic_role or "unclassified"] += 1
        driver_roles[txn.economic_role or "unclassified"] += 1

    return {
        "counts": counts,
        "would_pair_amount": str(sum(
            (abs(t.amount or 0) for t, _ in proposals), Decimal("0.00"))),
        "driver_roles": dict(driver_roles),
        "counterpart_roles": dict(counterpart_roles),
        "ambiguity_sizes": dict(Counter(len(c) for _, c in ambiguous)),
        "samples": {
            "proposed": [_redacted(t, o) for t, o in proposals[:sample]],
            "ambiguous": [_redacted(t) for t, _ in ambiguous[:sample]],
        },
        "note": ("Report only. The proposals come from the SAME function the apply "
                 "pass runs, so a rehearsal cannot describe a different plan."),
    }


def _magnitude(amount):
    value = abs(amount or Decimal("0"))
    for edge, label in ((10, "<$10"), (50, "$10–50"), (200, "$50–200"),
                        (1000, "$200–1k"), (5000, "$1k–5k")):
        if value < edge:
            return label
    return ">$5k"


def _claim_pair(txn_pk, counterpart_pk):
    """Link two legs atomically, or refuse.

    The read that chose the counterpart and the write that claims it are not one step,
    so both rows are re-read FOR UPDATE and re-checked here. The OUTflow leg carries the
    column, matching the convention every other reader expects.
    """
    from django.db import transaction as db_transaction

    with db_transaction.atomic():
        rows = {row.pk: row for row in
                Transaction.objects.select_for_update()
                .filter(pk__in=[txn_pk, counterpart_pk])
                .select_related("account")}
        first, second = rows.get(txn_pk), rows.get(counterpart_pk)
        if first is None or second is None:
            return False
        if first.user_id != second.user_id:
            logger.error("Refused a cross-user transfer pair: %s / %s",
                         txn_pk, counterpart_pk)
            return False
        if is_paired(first) or is_paired(second):
            return False
        if Transaction.TRANSFER_BY_USER in (first.transfer_classified_by,
                                            second.transfer_classified_by):
            return False

        holder, other = ((first, second) if (first.amount or 0) < 0
                         else (second, first))
        holder.transfer_pair = other
        holder.save(update_fields=["transfer_pair", "updated_at"])
        names = liability_account_names(holder.user)
        classify(holder, liability_names=names)
        classify(other, liability_names=names)
        return True


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
# Pairing support
# ---------------------------------------------------------------------------

#: Liabilities where a credit can ONLY be a payment received — nothing can be drawn on
#: a closed-end loan. Classification relies on this; pairing never needs to special-case
#: it, because `_assess` reads the settled liability from the pair.
CLOSED_END_TYPES = frozenset({
    FinancialAccount.TYPE_LOAN,
    FinancialAccount.TYPE_MORTGAGE,
    FinancialAccount.TYPE_STUDENT_LOAN,
})


def _is_liability(txn):
    account = getattr(txn, "account", None)
    return bool(account is not None and getattr(account, "is_liability", False))


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
        "reads_full_population": True,
        "window_days": PAIRING_WINDOW_DAYS,
        "note": ("The pass reads the whole eligible population in bounded batches. The "
                 "old 2,000-row cap silently dropped the most recent third of a long "
                 "history — exactly where unpaired legs collect."),
    }
