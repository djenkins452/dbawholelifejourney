# ==============================================================================
# File: apps/finance/services/category_assignment.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Choosing (and creating) the WLJ category for a transaction.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""The user's own answer to "what kind of spending is this?".

Category is ONE of three independent dimensions on a transaction — category (what kind
of spending), economic entity (who it belongs to), and transfer state (whether it is
spending at all). This module owns only the first, and only the user's decision about
it.

**Nothing here is a parallel category system.** Visibility comes from
`TransactionCategory.get_for_user` — the existing authority — so system categories and
the user's own categories are surfaced by the same rule the Categories page already
uses. Assignment writes `category_source = 'user'`, which the ingestion pipeline already
treats as final: `sync_service._apply_provider_category` returns early on a user choice,
so a later Plaid sync can never quietly overwrite it. The provider's own classification
is untouched in `provider_category_*`, so lineage survives the correction.
"""
from __future__ import annotations

import logging

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction as db_transaction
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)

#: A name longer than the column is a mistake, not a category.
MAX_NAME_LENGTH = 100


def assignable_categories(user, category_type=None, include=None):
    """Categories the user may pick, plus `include` even if it is archived.

    `include` is the transaction's CURRENT category. An archived category stays valid
    on the transactions already assigned to it — hiding it from the control would
    misreport what the transaction is, and the first save would silently change it.
    """
    from apps.finance.models import TransactionCategory

    categories = list(
        TransactionCategory.get_for_user(user, category_type=category_type))

    if include is not None and include.pk not in {c.pk for c in categories}:
        # Only ever re-admit a category this user is actually entitled to see.
        if include.is_system or include.user_id == user.id:
            categories.append(include)

    return sorted(categories, key=lambda c: (c.category_type, c.sort_order, c.name))


def category_choices(user, transaction=None):
    """The dropdown's payload: what may be chosen, and what is chosen now."""
    current = transaction.category if transaction is not None else None
    categories = assignable_categories(user, include=current)
    return {
        "current_id": current.pk if current else None,
        "categories": [
            {
                "id": c.pk,
                "name": c.name,
                "type": c.category_type,
                "personal": c.user_id is not None,
                "archived": not c.is_active,
            }
            for c in categories
        ],
    }


def infer_category_type(transaction):
    """The one field we would otherwise have to ask for — derived, not requested.

    A transaction's own sign already says whether it is income or expense (WLJ
    convention: positive = money in). Asking the user to restate it would be asking
    for information the record already holds, so creation needs a NAME and nothing
    else. A transaction already classified as a transfer keeps that type.
    """
    from apps.finance.models import Transaction, TransactionCategory

    if transaction is None:
        return TransactionCategory.CATEGORY_TYPE_EXPENSE
    if transaction.transfer_state == Transaction.TRANSFER_STATE_CONFIRMED:
        return TransactionCategory.CATEGORY_TYPE_TRANSFER
    if transaction.amount is not None and transaction.amount >= 0:
        return TransactionCategory.CATEGORY_TYPE_INCOME
    return TransactionCategory.CATEGORY_TYPE_EXPENSE


def normalise_name(raw):
    """Collapse whitespace; reject what is not a name."""
    name = " ".join((raw or "").split())
    if not name:
        raise ValidationError("Give the category a name.")
    if len(name) > MAX_NAME_LENGTH:
        raise ValidationError(
            f"Category names are limited to {MAX_NAME_LENGTH} characters.")
    return name


def find_visible_match(user, name, category_type):
    """An existing category this user can already see with this name and type."""
    from apps.finance.models import TransactionCategory

    return (TransactionCategory.objects
            .filter(Q(user=user) | Q(is_system=True))
            .filter(name__iexact=name, category_type=category_type)
            .order_by("is_system")          # prefer the user's own over the system one
            .first())


def resolve_or_create_category(user, name, category_type):
    """Return `(category, created)` for a name the user typed.

    Matching an existing visible category REUSES it rather than erroring or creating a
    near-twin: typing "groceries" when "Groceries" already exists means the user wants
    that category, and a second row differing only in case would make the dropdown
    ambiguous forever. That is what "no duplicates" has to mean at the point of entry.
    """
    from apps.finance.models import TransactionCategory

    name = normalise_name(name)

    existing = find_visible_match(user, name, category_type)
    if existing is not None:
        if not existing.is_active:
            # Reviving the user's own archived category is the honest reading of
            # "create it again"; a system category is never mutated here.
            if existing.user_id == user.id:
                existing.is_active = True
                existing.save(update_fields=["is_active", "updated_at"])
        return existing, False

    try:
        with db_transaction.atomic():
            category = TransactionCategory.objects.create(
                user=user,
                name=name,
                category_type=category_type,
                is_system=False,
                is_active=True,
            )
    except IntegrityError:
        # Lost a race against the same user creating the same name in another tab.
        # The constraint did its job; re-read rather than surface a database error.
        existing = find_visible_match(user, name, category_type)
        if existing is None:
            raise
        return existing, False

    return category, True


def assign_category(user, transaction, category, *, request=None):
    """Record the user's decision as the authoritative WLJ category.

    The provider's classification in `provider_category_*` is deliberately left alone —
    it is lineage, not a competing answer.
    """
    from apps.finance.models import Transaction

    if transaction.user_id != user.id:
        raise ValidationError("That transaction does not belong to you.")
    if category is not None and not (category.is_system or category.user_id == user.id):
        raise ValidationError("That category is not available to you.")

    previous = transaction.category
    transaction.category = category
    transaction.category_source = (Transaction.CATEGORY_SOURCE_USER if category
                                   else Transaction.CATEGORY_SOURCE_NONE)
    transaction.category_confirmed_at = timezone.now() if category else None
    transaction.save(update_fields=[
        "category", "category_source", "category_confirmed_at", "updated_at"])

    _audit(user, request, transaction, previous, category)
    return transaction


def _audit(user, request, transaction, previous, category):
    """Durable, redacted record of who recategorised what, and away from what.

    Uses the existing `FinanceAuditLogger` rather than a second audit trail. No amount,
    payee or description is recorded — the entity id is enough to find the row, and the
    interesting fact is the CHANGE.
    """
    from apps.finance.security import FinanceAuditLogger

    try:
        FinanceAuditLogger(user=user, request=request).log(
            action=FinanceAuditLogger.ACTION_UPDATE,
            entity_type=FinanceAuditLogger.ENTITY_TRANSACTION,
            entity_id=transaction.pk,
            details={
                "field": "category",
                "from_category_id": previous.pk if previous else None,
                "from_category": previous.name if previous else None,
                "to_category_id": category.pk if category else None,
                "to_category": category.name if category else None,
                "category_source": transaction.category_source,
            },
        )
    except Exception:                       # audit must never break the user's action
        logger.warning("Could not audit a category assignment for transaction %s",
                       transaction.pk, exc_info=True)


def audit_category_created(user, category, *, request=None):
    """Record that a personal category came into existence, and who owns it."""
    from apps.finance.security import FinanceAuditLogger

    try:
        FinanceAuditLogger(user=user, request=request).log(
            action=FinanceAuditLogger.ACTION_CREATE,
            entity_type="transaction_category",
            entity_id=category.pk,
            details={"name": category.name, "category_type": category.category_type,
                     "is_system": category.is_system},
        )
    except Exception:
        logger.warning("Could not audit category creation %s", category.pk,
                       exc_info=True)


def attach_category_options(user, transactions):
    """Give every transaction the option list its picker needs — in ONE query.

    The visible set is identical for every row, so it is fetched once and shared. The
    only per-row difference is a transaction sitting on an ARCHIVED category: that
    category is absent from the shared list and is appended for that row alone, so the
    control shows what the transaction actually is instead of silently offering to
    change it.

    Request-path safe: one categories query regardless of page size.
    """
    from apps.finance.models import TransactionCategory

    shared = list(TransactionCategory.get_for_user(user))
    shared_ids = {c.pk for c in shared}
    base = [_option(c) for c in shared]

    for transaction in transactions:
        current = transaction.category
        if current is not None and current.pk not in shared_ids:
            if current.is_system or current.user_id == user.id:
                transaction.category_options = base + [_option(current)]
                continue
        transaction.category_options = base

    return transactions


def _option(category):
    return {
        "id": category.pk,
        "name": category.name,
        "type": category.category_type,
        "personal": category.user_id is not None,
        "archived": not category.is_active,
    }
