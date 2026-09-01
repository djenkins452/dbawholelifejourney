# ==============================================================================
# File: apps/finance/services/finance_calc/backfill.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Persists economic roles. Batched, idempotent, reversible.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Writing the classification down, safely enough to do it twice.

Three properties make this safe to run against real financial history:

**Idempotent.** A row is written only when the computed assignment DIFFERS from what is
stored. Running it again after a clean run writes nothing and reports zero changes, so
"did it already run?" is never a question anyone has to answer from memory.

**Reversible.** `clear()` removes derived roles and leaves user decisions alone. The
source rows are never modified — a role is an added opinion about a transaction, not an
edit to it — so reversal is complete by construction.

**It cannot overwrite a person.** Rows whose `role_source` is `user` are skipped before
anything is computed. That is checked here AND in `roles.classify`, because a rule this
important should not have exactly one place to fail.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction as db_transaction
from django.utils import timezone

from apps.finance.services.finance_calc import roles as R

#: Bounded so one batch is a short transaction even on a slow database. Large enough
#: that 4k rows is a handful of round trips, small enough that a failure loses little.
BATCH_SIZE = 500

WRITE_FIELDS = ["economic_role", "role_confidence", "role_source", "role_reason",
                "role_classifier_version", "role_classified_at"]


def _population(user=None):
    from apps.finance.models import Transaction

    qs = (Transaction.objects.all()
          .select_related("account", "transfer_pair", "transfer_pair__account",
                          "transfer_counterpart", "transfer_counterpart__account"))
    if user is not None:
        qs = qs.filter(user=user)
    return qs.order_by("id")


def _differs(txn, assignment):
    return (txn.economic_role != assignment.role
            or txn.role_confidence != assignment.confidence
            or txn.role_source != assignment.source
            or txn.role_reason != assignment.reason
            or txn.role_classifier_version != assignment.classifier_version)


def run(user=None, *, commit=False, batch_size=BATCH_SIZE, progress=None):
    """Classify and (optionally) persist. Returns a report; raises nothing routine.

    `commit=False` is the default on purpose: the honest thing for a function that can
    rewrite four thousand financial rows is to require someone to ask for it twice.
    """
    from apps.finance.models import Transaction

    report = {
        "scanned": 0, "written": 0, "unchanged": 0, "user_protected": 0,
        "batches": 0, "by_role": {}, "committed": bool(commit),
        "classifier_version": R.CLASSIFIER_VERSION,
        "before": {"classified": 0, "unclassified": 0},
        "after": {"classified": 0, "unclassified": 0},
        "checkpoints": [],
        # WHICH role became which, and how much money moved with it. A rehearsal that
        # says "3,785 rows would change" answers nothing a person can act on: rows
        # moving from `purchase` to `card_payment` REMOVE double-counted spending and
        # are the point of the exercise, while rows moving the other way would ADD
        # spending and are the thing to look at twice before committing.
        "transitions": {},
        "transition_amounts": {},
        "role_changes": 0,
        # Rows that DIFFER from what the classifier now says. `written` only counts
        # rows actually persisted, so on a rehearsal it is zero by definition — and a
        # rehearsal reporting "would write 0" is worse than useless.
        "differing": 0,
    }

    base = _population(user)
    report["before"]["classified"] = base.filter(economic_role__isnull=False).count()
    report["before"]["unclassified"] = base.filter(economic_role__isnull=True).count()

    pending, now = [], timezone.now()
    for txn in base.iterator(chunk_size=batch_size):
        report["scanned"] += 1
        if txn.economic_role and txn.role_source == Transaction.ROLE_SOURCE_USER:
            report["user_protected"] += 1
            continue

        assignment = R.classify(txn)
        report["by_role"][assignment.role] = report["by_role"].get(assignment.role, 0) + 1

        if not _differs(txn, assignment):
            report["unchanged"] += 1
            continue

        # A version bump alone rewrites every row's provenance without changing what it
        # MEANS. Only a genuine role change is impact, so they are counted apart.
        if txn.economic_role != assignment.role:
            key = f"{txn.economic_role or 'unclassified'} -> {assignment.role}"
            report["transitions"][key] = report["transitions"].get(key, 0) + 1
            report["transition_amounts"][key] = str(
                Decimal(report["transition_amounts"].get(key, "0"))
                + abs(txn.amount or Decimal("0")))
            report["role_changes"] += 1

        report["differing"] += 1
        for field, value in assignment.as_update_fields().items():
            setattr(txn, field, value)
        txn.role_classified_at = now
        pending.append(txn)

        if len(pending) >= batch_size:
            _flush(pending, commit, report, progress)
            pending = []

    if pending:
        _flush(pending, commit, report, progress)

    after = _population(user)
    report["after"]["classified"] = after.filter(economic_role__isnull=False).count()
    report["after"]["unclassified"] = after.filter(economic_role__isnull=True).count()
    return report


def _flush(rows, commit, report, progress):
    from apps.finance.models import Transaction

    report["batches"] += 1
    if commit:
        with db_transaction.atomic():
            Transaction.objects.bulk_update(rows, WRITE_FIELDS)
        report["written"] += len(rows)
    checkpoint = {"batch": report["batches"], "rows": len(rows),
                  "scanned_so_far": report["scanned"], "committed": bool(commit)}
    report["checkpoints"].append(checkpoint)
    if progress:
        progress(checkpoint)


def clear(user=None, *, commit=False):
    """Undo a backfill. Derived roles only — a user's decision is not ours to erase."""
    from apps.finance.models import Transaction

    qs = _population(user).filter(economic_role__isnull=False).exclude(
        role_source=Transaction.ROLE_SOURCE_USER)
    count = qs.count()
    if commit:
        qs.update(economic_role=None, role_confidence=None, role_source=None,
                  role_reason="", role_classifier_version="", role_classified_at=None)
    return {"cleared": count, "committed": bool(commit)}


def classify_one(txn, *, commit=True):
    """Classify a single transaction — the path new rows take after activation."""
    from apps.finance.models import Transaction

    if txn.economic_role and txn.role_source == Transaction.ROLE_SOURCE_USER:
        return None
    assignment = R.classify(txn)
    if not _differs(txn, assignment):
        return assignment
    for field, value in assignment.as_update_fields().items():
        setattr(txn, field, value)
    txn.role_classified_at = timezone.now()
    if commit:
        txn.save(update_fields=WRITE_FIELDS)
    return assignment


#: Cache key the deploy-time rehearsal writes and the audit endpoint reads. The audit
#: runs on the request path and must NEVER classify four thousand rows to answer a
#: question — background writes, request-path reads, exactly as the platform requires.
ROLE_REHEARSAL_CACHE_KEY = "wlj:finance:role_backfill_rehearsal"
ROLE_REHEARSAL_TTL_SECONDS = 60 * 60 * 24 * 30

#: Roles a row may be moved INTO without anyone looking first.
#:
#: Every one of these takes a transaction OUT of consumer spending or leaves it out:
#: settling a card, servicing a debt, moving your own money, or admitting WLJ cannot
#: tell. Being wrong in these directions understates spending and holds something for
#: review — recoverable, and visible on the review queue.
#:
#: Deliberately ABSENT: `purchase`, `income`, `refund`, `reimbursement`,
#: `reversal_chargeback`. Each of those ADDS spending, income, or an offset against
#: spending, and a mass rewrite that quietly increases what a person appears to have
#: spent is not something a deploy gets to do unattended.
SAFE_BACKFILL_TARGETS = frozenset({
    "card_payment", "debt_service", "internal_transfer", "savings_allocation",
    "investment_contribution", "uncertain", "fee_or_interest_charged",
    "cash_withdrawal", "opening_balance", "loan_proceeds",
})


def _is_safe_transition(previous_role, new_role):
    """May this row be rewritten without review?"""
    if not previous_role:
        # It had no role at all. Anything is an improvement on nothing.
        return True
    if previous_role == new_role:
        return True
    return new_role in SAFE_BACKFILL_TARGETS


def rehearse_and_apply(user=None, *, commit=False, batch_size=BATCH_SIZE):
    """Rehearse the reclassification, then apply ONLY the transitions that are safe.

    Two passes on purpose. The first writes nothing and produces the impact report —
    which roles become which, how many rows, and how much money moves with each. The
    second applies only the subset whose direction cannot increase what a person
    appears to have spent; everything else is reported and left exactly as it was, for
    a human to look at.

    A classifier version bump alone makes every row differ, so `role_changes` (a row
    whose MEANING changed) is reported apart from `written` (a row whose provenance was
    refreshed). Confusing the two turns "3,785 rows changed" into a number nobody can
    act on.
    """
    from apps.finance.models import Transaction

    rehearsal = run(user, commit=False, batch_size=batch_size)
    report = {
        "rehearsal": {
            "scanned": rehearsal["scanned"],
            "would_write": rehearsal["differing"],
            "role_changes": rehearsal["role_changes"],
            "transitions": dict(rehearsal["transitions"]),
            "transition_amounts": dict(rehearsal["transition_amounts"]),
            "user_protected": rehearsal["user_protected"],
        },
        "classifier_version": R.CLASSIFIER_VERSION,
        "applied": {"written": 0, "held_for_review": 0, "held_transitions": {}},
        "committed": bool(commit),
    }

    held = {}
    for key in rehearsal["transitions"]:
        previous, _, new = key.partition(" -> ")
        if not _is_safe_transition(
                None if previous == "unclassified" else previous, new):
            held[key] = rehearsal["transitions"][key]
    report["applied"]["held_transitions"] = held

    if not commit:
        return report

    pending, now = [], timezone.now()
    applied = {"scanned": 0, "written": 0, "batches": 0, "checkpoints": []}
    held_rows = 0
    for txn in _population(user).iterator(chunk_size=batch_size):
        applied["scanned"] += 1
        if txn.economic_role and txn.role_source == Transaction.ROLE_SOURCE_USER:
            continue
        assignment = R.classify(txn)
        if not _differs(txn, assignment):
            continue
        if not _is_safe_transition(txn.economic_role, assignment.role):
            held_rows += 1
            continue
        for field, value in assignment.as_update_fields().items():
            setattr(txn, field, value)
        txn.role_classified_at = now
        pending.append(txn)
        if len(pending) >= batch_size:
            _flush(pending, True, applied, None)
            pending = []
    if pending:
        _flush(pending, True, applied, None)

    report["applied"]["written"] = applied["written"]
    report["applied"]["held_for_review"] = held_rows
    return report


def publish_rehearsal(report):
    """Put the report where the audit endpoint can read it without recomputing."""
    from django.core.cache import cache

    try:
        cache.set(ROLE_REHEARSAL_CACHE_KEY, report, ROLE_REHEARSAL_TTL_SECONDS)
    except Exception:
        # Losing the report must never fail the reclassification it describes.
        pass


def read_rehearsal():
    """The last published report, or None. Never computes — see the cache key note."""
    from django.core.cache import cache

    try:
        return cache.get(ROLE_REHEARSAL_CACHE_KEY)
    except Exception:
        return None
