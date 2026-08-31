# ==============================================================================
# File: apps/finance/services/finance_calc/review_queue.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Grouped, impact-ranked review with previewed, reversible bulk decisions.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Turning 155 questions into a handful of decisions.

A flat queue asks the same question 155 times and gets abandoned around row nine. The
rows are not 155 independent puzzles: they cluster by *why* WLJ held them and by *who*
took the money, and one answer usually settles a whole cluster.

Three properties make bulk safe:

**Preview binds the set.** `preview()` returns a token derived from the exact row ids it
counted. `apply_bulk()` refuses any set whose token does not match, so a batch can never
quietly include a row that arrived between looking and clicking.

**Every batch is reversible.** The prior role of every row is recorded before it is
overwritten, and undo restores exactly those — skipping any row edited by hand
afterwards, because that later decision outranks the record.

**A confirmed decision is never bulk-overwritten.** Rows the user already decided are
excluded from every group before they can be selected.

Impact ranking exists because 155 rows are not equally worth the attention. A group is
ranked by the money it moves and by whether it moves a *spending* measure — the figure
people actually plan from.
"""
from __future__ import annotations

import hashlib
from collections import defaultdict
from decimal import Decimal

ZERO = Decimal("0.00")

REVIEW_VERSION = "1.0.0"

#: The decision a user can take on a held row, beyond assigning a role outright.
DECISION_LEAVE = "leave_uncertain"

#: What each held reason usually turns out to be, and what a decision there changes.
#: `suggests` is a STARTING POINT shown to the person — never applied automatically.
REASON_GUIDANCE = {
    "unmatched_liability_credit": {
        "label": "Credit on a card — a payment, or borrowing?",
        "explain": ("Money landed on a credit card. If you paid the card, it is a card "
                    "payment and changes nothing you spent. If you drew cash or "
                    "transferred a balance, it is borrowing."),
        "suggests": "card_payment",
        "affects": ["cash_inflow", "transfers_and_allocations"],
    },
    "unmatched_transfer_candidate": {
        "label": "Looks like a transfer, but the other side is not visible",
        "explain": ("The money definitely left the account. Where it went is the open "
                    "question — another of your accounts, or someone else's."),
        "suggests": "internal_transfer",
        "affects": ["cash_outflow", "net_spending", "transfers_and_allocations"],
    },
    "ambiguous_credit": {
        "label": "Money arrived and WLJ cannot say why",
        "explain": ("It could be a reimbursement, a refund the bank did not label, or "
                    "a transfer from an account WLJ cannot see. Each changes a "
                    "different total."),
        "suggests": "reimbursement",
        "affects": ["cash_inflow", "income", "net_spending"],
    },
    "zero_amount": {
        "label": "No amount to classify",
        "explain": "There is nothing to count either way.",
        "suggests": None,
        "affects": [],
    },
}

#: Measures a person plans from. A group that moves one of these is worth more attention
#: than a group of the same size that does not.
SPENDING_MEASURES = frozenset({"net_spending", "gross_purchases", "cash_outflow"})


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------

def held_rows(user):
    """Held transactions the user has NOT already decided.

    A confirmed decision is excluded before grouping, so it cannot be swept into a
    bulk action and silently overwritten.
    """
    from apps.finance.models import Transaction

    return list(
        Transaction.objects.filter(
            user=user, economic_role=Transaction.ROLE_UNCERTAIN)
        .exclude(role_source=Transaction.ROLE_SOURCE_USER)
        .select_related("account", "category")
        .order_by("-date", "-id"))


def _payee(txn):
    from apps.finance.services.finance_calc.recurring import normalise_payee
    return normalise_payee(txn) or "(no payee)"


def _magnitude_band(amount):
    a = abs(amount or ZERO)
    for edge, label in ((10, "under $10"), (50, "$10–50"), (200, "$50–200"),
                        (1000, "$200–1k"), (5000, "$1k–5k")):
        if a < edge:
            return label
    return "over $5k"


def build_groups(user, rows=None):
    """Cluster held rows into decisions. Ranked by how much they matter.

    Grouped by (reason, payee, direction): the reason is why WLJ could not decide, and
    the payee is almost always what settles it. Direction is kept separate because a
    credit and a debit to the same payee are different questions.
    """
    rows = held_rows(user) if rows is None else rows
    buckets = defaultdict(list)
    for txn in rows:
        direction = "in" if (txn.amount or ZERO) > 0 else "out"
        buckets[(txn.role_reason or "unknown", _payee(txn), direction)].append(txn)

    groups = []
    for (reason, payee, direction), members in buckets.items():
        guidance = REASON_GUIDANCE.get(reason, {
            "label": reason.replace("_", " "), "explain": "",
            "suggests": None, "affects": [],
        })
        total = sum((abs(t.amount or ZERO) for t in members), ZERO)
        accounts = sorted({(t.account.name if t.account_id else "—") for t in members})
        bands = sorted({_magnitude_band(t.amount) for t in members})
        ids = sorted(t.pk for t in members)

        groups.append({
            "key": _group_key(reason, payee, direction),
            "reason": reason,
            "reason_label": guidance["label"],
            "explain": guidance["explain"],
            "payee": payee,
            "direction": direction,
            "count": len(members),
            "total_amount": total,
            "accounts": accounts,
            "magnitude_bands": bands,
            "suggested_role": guidance["suggests"],
            "affects": guidance["affects"],
            "confidence": _group_confidence(members, reason),
            "evidence": _group_evidence(members),
            "impact": _impact(total, guidance["affects"], len(members)),
            "ids": ids,
            "token": selection_token(ids),
            "rows": members[:12],
            "more_rows": max(0, len(members) - 12),
        })

    groups.sort(key=lambda g: (g["impact"], g["total_amount"]), reverse=True)
    return groups


def _group_key(reason, payee, direction):
    raw = f"{reason}|{payee}|{direction}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _group_confidence(members, reason):
    """How safe one answer for the whole group looks.

    High only when the rows genuinely look alike: one account, one magnitude band, and
    more than one of them. A group of one is not a pattern.
    """
    if len(members) < 2:
        return "low"
    accounts = {t.account_id for t in members}
    bands = {_magnitude_band(t.amount) for t in members}
    if len(accounts) == 1 and len(bands) == 1:
        return "high"
    if len(accounts) == 1:
        return "medium"
    return "low"


def _group_evidence(members):
    first, last = min(t.date for t in members), max(t.date for t in members)
    primaries = sorted({(t.provider_category_primary or "").strip()
                        for t in members if t.provider_category_primary})
    return {
        "first_seen": str(first), "last_seen": str(last),
        "provider_categories": primaries[:4],
        "distinct_accounts": len({t.account_id for t in members}),
        "review_version": REVIEW_VERSION,
    }


def _impact(total, affects, count):
    """Money, weighted by whether it moves a figure people plan from."""
    weight = Decimal("1.0")
    if any(measure in SPENDING_MEASURES for measure in affects):
        weight = Decimal("1.5")
    return (total * weight).quantize(Decimal("0.01"))


def highest_impact(user, limit=5):
    """The short list. Value without reviewing all 155."""
    groups = build_groups(user)
    covered = sum(g["count"] for g in groups[:limit])
    total = sum(g["count"] for g in groups)
    return {
        "groups": groups[:limit],
        "covers": covered,
        "of": total,
        "pct": round(covered * 100.0 / total, 1) if total else 0.0,
        "remaining_groups": max(0, len(groups) - limit),
    }


# ---------------------------------------------------------------------------
# Preview and apply
# ---------------------------------------------------------------------------

def selection_token(ids):
    """A fingerprint of an exact set of rows.

    Binds a preview to the decision that follows it. Without this, a transaction that
    synced between looking and clicking would be swept into a batch nobody previewed.
    """
    joined = ",".join(str(i) for i in sorted(ids))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:32]


def preview(user, ids, decision):
    """What this decision would do, before it does it."""
    from apps.finance.models import Transaction

    rows = list(Transaction.objects.filter(
        user=user, pk__in=ids, economic_role=Transaction.ROLE_UNCERTAIN)
        .exclude(role_source=Transaction.ROLE_SOURCE_USER)
        .select_related("account"))

    eligible = sorted(t.pk for t in rows)
    refused = sorted(set(ids) - set(eligible))
    total = sum((abs(t.amount or ZERO) for t in rows), ZERO)

    return {
        "decision": decision,
        "eligible_count": len(rows),
        "eligible_ids": eligible,
        "refused_count": len(refused),
        "refused_reason": ("not yours, already decided by you, or no longer held"
                           if refused else None),
        "total_amount": total,
        "inflow": sum((t.amount for t in rows if (t.amount or ZERO) > 0), ZERO),
        "outflow": sum((abs(t.amount) for t in rows if (t.amount or ZERO) < 0), ZERO),
        "token": selection_token(eligible),
        "affects": sorted({m for t in rows
                           for m in REASON_GUIDANCE.get(t.role_reason, {})
                           .get("affects", [])}),
        "review_version": REVIEW_VERSION,
    }


def apply_bulk(user, ids, decision, *, token, create_rule=False, group_label=""):
    """Apply one decision to a previewed set. Reversible, audited, exactly scoped.

    Refuses outright when the token does not match the rows actually eligible now —
    that mismatch means the world changed since the preview, and applying anyway is how
    a batch silently grows.
    """
    from django.db import transaction as db_transaction

    from apps.finance.models import ReviewBatch, Transaction

    if decision != DECISION_LEAVE and \
            decision not in dict(Transaction.ECONOMIC_ROLE_CHOICES):
        raise ValueError("unknown decision")

    current = preview(user, ids, decision)
    if current["token"] != token:
        return {
            "applied": 0, "refused": True,
            "reason": "the rows changed since you previewed them — preview again",
            "expected_token": token, "current_token": current["token"],
        }
    if not current["eligible_ids"]:
        return {"applied": 0, "refused": True, "reason": "nothing eligible"}

    with db_transaction.atomic():
        rows = list(Transaction.objects.select_for_update()
                    .filter(user=user, pk__in=current["eligible_ids"]))
        previous = [{
            "id": t.pk,
            "role": t.economic_role,
            "source": t.role_source,
            "reason": t.role_reason,
            "confidence": t.role_confidence,
        } for t in rows]

        if decision == DECISION_LEAVE:
            # A deliberate "I looked and I still do not know" is a real answer. It is
            # recorded as a decision so the row stops being re-proposed as new.
            for txn in rows:
                txn.role_reason = f"{txn.role_reason}:reviewed"
            Transaction.objects.bulk_update(rows, ["role_reason"])
        else:
            for txn in rows:
                txn.economic_role = decision
                txn.role_source = Transaction.ROLE_SOURCE_USER
                txn.role_confidence = Transaction.ROLE_CONFIDENCE_HIGH
                txn.role_reason = "user_bulk_decision"
            Transaction.objects.bulk_update(
                rows, ["economic_role", "role_source", "role_confidence",
                       "role_reason"])

        batch = ReviewBatch.objects.create(
            user=user, decision=decision, group_label=group_label[:200],
            row_count=len(rows),
            total_amount=current["total_amount"],
            previous_state=previous)

        rule = None
        if create_rule and decision != DECISION_LEAVE and rows:
            rule = _create_rule(user, rows, decision)
            if rule is not None:
                batch.created_rule = rule
                batch.save(update_fields=["created_rule", "updated_at"])

    return {
        "applied": len(rows), "refused": False, "batch_id": batch.pk,
        "decision": decision, "total_amount": str(current["total_amount"]),
        "rule_created": rule.pk if rule is not None else None,
        "can_undo": True,
    }


def _create_rule(user, rows, decision):
    """Turn one batch into an enduring payee rule, when the rows share a payee."""
    from apps.finance.models import SpendingClassification

    payees = {_payee(t) for t in rows}
    if len(payees) != 1:
        return None                     # no single payee — a rule would over-reach
    payee = payees.pop()
    if not payee or payee == "(no payee)":
        return None
    classification, _ = SpendingClassification.objects.update_or_create(
        user=user, payee=payee.lower(), status="active",
        defaults={
            "scope": SpendingClassification.SCOPE_PAYEE,
            "source": SpendingClassification.SOURCE_USER,
            "note": f"Created from a review decision: {decision}",
        })
    return classification


def undo(user, batch_id):
    """Put the rows back exactly as they were — and no further.

    A row someone edited by hand after the batch is left alone: their later decision
    outranks this record, and quietly reverting it would be the same kind of silent
    overwrite bulk actions are supposed to avoid.
    """
    from django.db import transaction as db_transaction
    from django.utils import timezone

    from apps.finance.models import ReviewBatch, Transaction

    batch = ReviewBatch.objects.filter(user=user, pk=batch_id,
                                       status="active").first()
    if batch is None:
        return {"restored": 0, "refused": True, "reason": "no such batch"}
    if not batch.can_undo:
        return {"restored": 0, "refused": True,
                "reason": "this batch has already been undone"}

    restored, skipped = 0, 0
    with db_transaction.atomic():
        by_id = {row["id"]: row for row in batch.previous_state}
        rows = list(Transaction.objects.select_for_update()
                    .filter(user=user, pk__in=list(by_id)))
        to_write = []
        for txn in rows:
            previous = by_id[txn.pk]
            if txn.role_reason not in ("user_bulk_decision",
                                       f"{previous['reason']}:reviewed"):
                skipped += 1
                continue
            txn.economic_role = previous["role"]
            txn.role_source = previous["source"]
            txn.role_reason = previous["reason"]
            txn.role_confidence = previous["confidence"]
            to_write.append(txn)
        if to_write:
            Transaction.objects.bulk_update(
                to_write, ["economic_role", "role_source", "role_reason",
                           "role_confidence"])
            restored = len(to_write)

        batch.batch_status = ReviewBatch.STATUS_UNDONE
        batch.undone_at = timezone.now()
        batch.save(update_fields=["batch_status", "undone_at", "updated_at"])

    return {"restored": restored, "skipped_edited_since": skipped, "refused": False}
