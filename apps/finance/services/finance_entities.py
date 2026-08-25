# ==============================================================================
# File: apps/finance/services/finance_entities.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: F0 — the ONE service that creates entities and owns account→entity time.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Financial entities and the temporal truth of who owned an account when.

THE single writer for `FinancialEntity` and `AccountEntityAssignment`. Views, forms, admin,
and importers call this module; they never construct these rows themselves, because the
same-user invariant across `user`/`account`/`entity` cannot be expressed as a database
constraint in Django (no composite foreign keys) — so it is enforced here, at every write
boundary, and proven by adversarial tests.

`paid_by` is resolved from `AccountEntityAssignment`, never cached on the account. The
assignment table carries a partial unique index on the open row, so "who owns this account
now" is one indexed read and a whole user's map is one query.
"""
from __future__ import annotations

from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction
from django.db.models import Min

from apps.finance.models import (
    AccountEntityAssignment,
    FinancialAccount,
    FinancialEntity,
    Transaction,
    normalize_entity_name,
)

DEFAULT_PERSONAL_NAME = "Personal"
UNKNOWN_NAME = "Unknown"


class CrossUserReference(ValidationError):
    """Raised when a write would link records belonging to different users."""


def _require_same_user(user, **objects):
    """Every related record must belong to `user`. The security boundary for all writes."""
    for label, obj in objects.items():
        if obj is None:
            continue
        owner_id = getattr(obj, "user_id", None)
        if owner_id != user.id:
            raise CrossUserReference(
                f"{label} belongs to user {owner_id}, not {user.id}. "
                "Cross-user financial references are rejected."
            )


# ---------------------------------------------------------------------------
# Finance activation + bootstrap
# ---------------------------------------------------------------------------

def is_finance_active(user) -> bool:
    """Has this user actually used Finance?

    Proven from existing repository truth — an account, a transaction, or a bank
    connection. Entities are bootstrapped only for these users; everyone else gets them
    lazily on first use, so WLJ does not manufacture Finance rows for people who never
    open the module.
    """
    from apps.finance.models import BankConnection

    return (
        FinancialAccount.objects.filter(user=user).exists()
        or Transaction.objects.filter(user=user).exists()
        or BankConnection.objects.filter(user=user).exists()
    )


@db_transaction.atomic
def ensure_default_entities(user):
    """Idempotently return this user's (personal, unknown) entities, creating if needed.

    The canonical lazy-creation path. `Personal` is an ordinary user-owned row whose NAME
    happens to be "Personal" — no code branches on it; `is_default_personal` is the flag
    that carries meaning.
    """
    personal = FinancialEntity.objects.filter(
        user=user, is_default_personal=True, is_active=True,
    ).first()
    if personal is None:
        personal = FinancialEntity.objects.create(
            user=user, entity_type=FinancialEntity.TYPE_PERSONAL,
            name=DEFAULT_PERSONAL_NAME, is_default_personal=True, sort_order=0,
        )

    unknown = FinancialEntity.objects.filter(
        user=user, entity_type=FinancialEntity.TYPE_UNKNOWN, is_active=True,
    ).first()
    if unknown is None:
        unknown = FinancialEntity.objects.create(
            user=user, entity_type=FinancialEntity.TYPE_UNKNOWN,
            name=UNKNOWN_NAME, sort_order=99,
        )
    return personal, unknown


def default_personal_entity(user):
    return ensure_default_entities(user)[0]


def unknown_entity(user):
    return ensure_default_entities(user)[1]


# ---------------------------------------------------------------------------
# Entity CRUD (creation is centralized here)
# ---------------------------------------------------------------------------

def create_entity(user, *, entity_type, name, notes="", sort_order=0):
    """Create a user-owned entity, rejecting case/whitespace-duplicate active names."""
    cleaned = " ".join((name or "").split())
    if not cleaned:
        raise ValidationError("An entity needs a name.")
    if entity_type not in dict(FinancialEntity.ENTITY_TYPE_CHOICES):
        raise ValidationError(f"Unknown entity type {entity_type!r}.")
    key = normalize_entity_name(cleaned)
    if FinancialEntity.objects.filter(user=user, name_key=key, is_active=True).exists():
        raise ValidationError(
            f"You already have an active entity named {cleaned!r} "
            "(names are compared ignoring case and spacing)."
        )
    return FinancialEntity.objects.create(
        user=user, entity_type=entity_type, name=cleaned, notes=notes,
        sort_order=sort_order,
    )


def retire_entity(entity):
    """Retire without deleting — historical attribution must keep resolving."""
    entity.is_active = False
    entity.save(update_fields=["is_active", "updated_at"])
    return entity


# ---------------------------------------------------------------------------
# Account → entity, over time
# ---------------------------------------------------------------------------

def earliest_account_activity(account) -> date:
    """The earliest date an account can truthfully be said to have existed.

    Used so a FIRST assignment covers imported history rather than starting today and
    leaving every historical transaction with no resolvable `paid_by`.
    """
    first_txn = (Transaction.all_objects.filter(account=account)
                 .aggregate(first=Min("date"))["first"])
    if first_txn:
        return first_txn
    created = getattr(account, "created_at", None)
    return created.date() if created else date.today()


@db_transaction.atomic
def assign_account_entity(user, account, entity, *, effective_from=None,
                          actor=AccountEntityAssignment.ACTOR_USER, reason=""):
    """Assign (or reassign) an account's economic owner.

    Temporal policy:
      * FIRST assignment for an account reaches back to the earliest known activity, so
        imported history resolves truthfully.
      * A LATER change is FORWARD-DATED (effective today) by default.
      * A retroactive change requires an explicit `effective_from` in the past — a
        deliberate act, never a side effect.

    Existing attributions are never rewritten here: their `paid_by_entity` snapshot is
    historical evidence of what was true when the attribution was made.
    """
    _require_same_user(user, account=account, entity=entity)
    if not entity.is_active:
        raise ValidationError("Cannot assign a retired entity.")

    open_assignment = (AccountEntityAssignment.objects
                       .filter(account=account, effective_to__isnull=True)
                       .select_related("entity").first())
    has_history = AccountEntityAssignment.objects.filter(account=account).exists()

    if effective_from is None:
        effective_from = earliest_account_activity(account) if not has_history \
            else _today_for(user)

    if open_assignment is not None:
        if open_assignment.entity_id == entity.id and \
                open_assignment.effective_from <= effective_from:
            return open_assignment  # already true; nothing to record
        if effective_from <= open_assignment.effective_from:
            # The new assignment fully covers the open one — supersede it outright.
            open_assignment.soft_delete()
        else:
            open_assignment.effective_to = effective_from - timedelta(days=1)
            open_assignment.save(update_fields=["effective_to", "updated_at"])

    return AccountEntityAssignment.objects.create(
        user=user, account=account, entity=entity,
        effective_from=effective_from, effective_to=None,
        actor=actor, reason=reason,
    )


def _today_for(user):
    from apps.core.utils import get_user_today
    return get_user_today(user)


def resolve_paid_by(user, account, on_date):
    """Which entity owned `account` on `on_date` — the source of `paid_by`.

    Fallback chain (each step is truth, never a guess):
      1. the assignment covering that date
      2. the earliest assignment, if the date predates all history
      3. the user's default personal entity
    """
    _require_same_user(user, account=account)
    covering = (AccountEntityAssignment.objects
                .filter(account=account, effective_from__lte=on_date)
                .filter(models_q_effective_to_covers(on_date))
                .select_related("entity")
                .order_by("-effective_from").first())
    if covering:
        return covering.entity
    earliest = (AccountEntityAssignment.objects.filter(account=account)
                .select_related("entity").order_by("effective_from").first())
    if earliest:
        return earliest.entity
    return default_personal_entity(user)


def models_q_effective_to_covers(on_date):
    from django.db.models import Q
    return Q(effective_to__isnull=True) | Q(effective_to__gte=on_date)


def open_assignment_map(user):
    """{account_id: FinancialEntity} for every currently-open assignment — ONE query.

    The batch shape: F1 resolves `paid_by` for thousands of transactions without a
    per-row lookup.
    """
    rows = (AccountEntityAssignment.objects
            .filter(user=user, effective_to__isnull=True)
            .select_related("entity"))
    return {row.account_id: row.entity for row in rows}
