# ==============================================================================
# File: apps/finance/services/attribution.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: F0 — THE single writer for transaction attribution truth.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Create, correct, confirm, and supersede transaction attribution.

THE only module that writes `TransactionAttribution`. Every invariant that cannot be a
database constraint lives here and is proven by adversarial tests:

  * same-user across transaction / attributed entity / paid-by entity / rule;
  * `user_confirmed` is settable ONLY by `confirm()` — no rule, import, or migration path
    can reach it, and no inferred `source` may carry it;
  * corrections SUPERSEDE (a new active row + the old row marked superseded); nothing is
    mutated or erased;
  * a user-confirmed row may be superseded ONLY by another explicit user confirmation —
    a rule, a stronger inference, or corrected account truth cannot silently replace it;
  * `paid_by_entity` is SNAPSHOTTED at creation and is historical evidence forever.

Conflicts that cannot be resolved deterministically (retroactive account truth vs a user
confirmation) are RECORDED as review conflicts, never auto-resolved.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction
from django.utils import timezone

from apps.finance.models import TransactionAttribution
from apps.finance.services.attribution_population import exclusion_reason
from apps.finance.services.finance_entities import _require_same_user, resolve_paid_by

#: Evidence keys allowed to be persisted. References and scalars only — never account
#: numbers, tokens, provider ids, or free-text notes (mirrors the never-surface list in
#: finance_domain_truth.py).
ALLOWED_EVIDENCE_KEYS = frozenset({
    "rule_id", "rule_scope", "payee_id", "recurring_id", "account_id", "amount", "date",
    "matched_on", "previous_attribution_id", "conflict", "exclusion_reason",
})
MAX_EVIDENCE_ITEMS = 12


class AttributionConflict(ValidationError):
    """A user confirmation stands and an inferred change was refused."""


def sanitize_evidence(evidence):
    """Keep evidence concise and non-sensitive. Unknown keys are dropped, not stored."""
    if not evidence:
        return {}
    clean = {k: v for k, v in evidence.items() if k in ALLOWED_EVIDENCE_KEYS}
    return dict(list(clean.items())[:MAX_EVIDENCE_ITEMS])


def current_attribution(transaction):
    """The one active whole-transaction attribution, or None. DB-guaranteed unique."""
    return (TransactionAttribution.objects
            .filter(transaction=transaction,
                    attribution_status=TransactionAttribution.STATUS_ACTIVE,
                    share_basis=TransactionAttribution.SHARE_FULL)
            .select_related("attributed_entity", "paid_by_entity", "rule")
            .first())


@db_transaction.atomic
def attribute(user, transaction, entity, *, source, actor, confidence=1.0,
              evidence=None, rule=None, notes="", allow_supersede=True):
    """Record (or correct) an INFERRED attribution.

    Refuses to override a user-confirmed attribution — that is the whole point of the
    confirmation outranking inference. When refused, the caller receives an
    `AttributionConflict` carrying the standing row so it can be surfaced for review.
    """
    if source == TransactionAttribution.SOURCE_USER_DIRECT:
        raise ValidationError(
            "user_direct attribution must go through confirm(); attribute() records "
            "inferred truth only."
        )
    _require_same_user(user, transaction=transaction, entity=entity, rule=rule)
    if not entity.is_active:
        raise ValidationError("Cannot attribute to a retired entity.")

    reason = exclusion_reason(transaction)
    if reason is not None:
        raise ValidationError(
            f"Transaction {transaction.id} is not attributable ({reason}). "
            "Uncertain transactions are surfaced for review, never attributed to empty a queue."
        )

    existing = current_attribution(transaction)
    if existing is not None:
        if existing.user_confirmed:
            raise AttributionConflict(
                f"Transaction {transaction.id} carries a user-confirmed attribution "
                f"(entity {existing.attributed_entity_id}); inferred source {source!r} "
                "may not replace it."
            )
        if existing.attributed_entity_id == entity.id:
            return existing
        if not allow_supersede:
            return existing

    paid_by = resolve_paid_by(user, transaction.account, transaction.date)
    # Retire the incumbent BEFORE inserting: `uq_txattr_one_active_full` is checked at
    # insert time, so the replacement cannot coexist with the row it replaces.
    if existing is not None:
        _retire(existing)
    new_row = TransactionAttribution.objects.create(
        user=user, transaction=transaction, attributed_entity=entity,
        paid_by_entity=paid_by, source=source, actor=actor,
        confidence=confidence, evidence=sanitize_evidence(evidence),
        rule=rule, notes=notes, user_confirmed=False,
    )
    if existing is not None:
        _link_supersession(existing, new_row)
    return new_row


@db_transaction.atomic
def confirm(user, transaction, entity, *, evidence=None, notes=""):
    """Record an EXPLICIT user decision. The only path that may set `user_confirmed`.

    A user confirmation always wins — over a rule, over account defaults, over a previous
    confirmation. It is the strongest truth Finance holds.
    """
    _require_same_user(user, transaction=transaction, entity=entity)
    if not entity.is_active:
        raise ValidationError("Cannot attribute to a retired entity.")

    existing = current_attribution(transaction)
    paid_by = resolve_paid_by(user, transaction.account, transaction.date)
    ev = sanitize_evidence(evidence)
    if existing is not None:
        ev.setdefault("previous_attribution_id", existing.id)

    if existing is not None:
        _retire(existing)
    new_row = TransactionAttribution.objects.create(
        user=user, transaction=transaction, attributed_entity=entity,
        paid_by_entity=paid_by,
        source=TransactionAttribution.SOURCE_USER_DIRECT,
        actor=TransactionAttribution.ACTOR_USER,
        confidence=1.0, evidence=ev, notes=notes,
        user_confirmed=True, confirmed_at=timezone.now(),
    )
    if existing is not None:
        _link_supersession(existing, new_row)
    return new_row


def _retire(old_row):
    """Step 1 of a correction: free the one-active-attribution slot."""
    old_row.attribution_status = TransactionAttribution.STATUS_SUPERSEDED
    old_row.save(update_fields=["attribution_status", "updated_at"])


def _link_supersession(old_row, new_row):
    """Step 2: point the retired row at its replacement. Together with `_retire`, these
    are the ONLY fields that ever change after a row is created."""
    old_row.superseded_by = new_row
    old_row.save(update_fields=["superseded_by", "updated_at"])


def supersession_chain(attribution):
    """Walk forward through corrections — the complete audit trail."""
    chain, seen, row = [attribution], {attribution.id}, attribution
    while row.superseded_by_id and row.superseded_by_id not in seen:
        row = row.superseded_by
        seen.add(row.id)
        chain.append(row)
    return chain


@db_transaction.atomic
def record_account_change_conflicts(user, account, *, effective_from):
    """After a RETROACTIVE account-entity change, refresh what may be refreshed.

    Inferred attributions whose `paid_by_entity` snapshot no longer matches the corrected
    account truth are superseded with a refreshed snapshot. **User-confirmed attributions
    are never touched** — instead each is recorded as an explicit review conflict so a
    human resolves it. Returns `(refreshed, conflicts)`.
    """
    rows = (TransactionAttribution.objects
            .filter(user=user, transaction__account=account,
                    attribution_status=TransactionAttribution.STATUS_ACTIVE,
                    transaction__date__gte=effective_from)
            .select_related("transaction", "attributed_entity", "paid_by_entity"))

    refreshed, conflicts = [], []
    for row in rows:
        truth = resolve_paid_by(user, account, row.transaction.date)
        if truth.id == row.paid_by_entity_id:
            continue
        if row.user_confirmed:
            conflicts.append(row)
            continue
        _retire(row)
        new_row = TransactionAttribution.objects.create(
            user=user, transaction=row.transaction,
            attributed_entity=row.attributed_entity, paid_by_entity=truth,
            source=TransactionAttribution.SOURCE_ACCOUNT_DEFAULT,
            actor=TransactionAttribution.ACTOR_SYSTEM,
            confidence=row.confidence,
            evidence=sanitize_evidence({
                "previous_attribution_id": row.id,
                "account_id": account.id,
                "conflict": "account_entity_retroactive_change",
            }),
        )
        _link_supersession(row, new_row)
        refreshed.append(new_row)
    return refreshed, conflicts
