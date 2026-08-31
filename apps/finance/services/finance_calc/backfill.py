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
