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


# =============================================================================
# Managing personal categories — the Categories page
# =============================================================================
#
# The same module as assignment on purpose. The inline picker and the Categories
# page are two doors into ONE set of rules: what a user may see, what a name
# resolves to, and what may be changed. Splitting management into its own service
# is how the two surfaces would start disagreeing about which categories exist.

#: Everything that points at a category, and what deleting one would do to it.
#: `Budget.category` CASCADES — deleting a category in use would silently delete
#: the user's budgets, which is why deletion is refused rather than cascaded.
def category_usage(category):
    """What currently depends on this category. Counts only, cheap enough to render."""
    from apps.finance.models import (Budget, Payee, RecurringTransaction,
                                     Transaction, TransactionCategory)

    return {
        "transactions": Transaction.objects.filter(category=category).count(),
        "budgets": Budget.objects.filter(category=category).count(),
        "recurring": RecurringTransaction.objects.filter(category=category).count(),
        "payees": Payee.objects.filter(default_category=category).count(),
        "children": TransactionCategory.objects.filter(parent=category).count(),
    }


def is_in_use(category):
    return any(category_usage(category).values())


def _require_personal(user, category):
    """A user may only manage a category they own.

    System categories are shared by everyone and are never editable here — not
    renamed, not archived, not deleted — regardless of who is asking.
    """
    if category.is_system or category.user_id is None:
        raise ValidationError("System categories cannot be changed.")
    if category.user_id != user.id:
        raise ValidationError("That category does not belong to you.")


def create_personal_category(user, name, category_type, *, request=None):
    """Create a category from the Categories page.

    Goes through the SAME `resolve_or_create_category` the inline picker uses, so
    a name typed here and a name typed on a transaction resolve identically —
    including reusing an existing match instead of making a near-twin.
    """
    from apps.finance.models import TransactionCategory

    if category_type not in dict(TransactionCategory.CATEGORY_TYPE_CHOICES):
        raise ValidationError("Choose whether this is income or an expense.")

    category, created = resolve_or_create_category(user, name, category_type)
    if created:
        audit_category_created(user, category, request=request)
    return category, created


def rename_personal_category(user, category, new_name, *, request=None):
    """Rename a category the user owns, refusing a name they already use."""
    _require_personal(user, category)
    name = normalise_name(new_name)

    if name.lower() == category.name.lower():
        category.name = name                      # a pure case change is allowed
        category.save(update_fields=["name", "updated_at"])
        return category

    clash = find_visible_match(user, name, category.category_type)
    if clash is not None and clash.pk != category.pk:
        raise ValidationError(
            f'You already have a category called "{clash.name}".')

    previous = category.name
    category.name = name
    category.save(update_fields=["name", "updated_at"])
    _audit_category(user, request, category, "rename",
                    {"from": previous, "to": name})
    return category


def archive_personal_category(user, category, *, request=None):
    """Hide a category from future use WITHOUT touching what already uses it.

    Archiving is the safe, reversible answer and the reason deletion is rarely
    needed: every transaction already assigned keeps its category and keeps
    displaying it, while the category stops being offered for anything new.
    """
    _require_personal(user, category)
    if not category.is_active:
        return category

    category.is_active = False
    category.save(update_fields=["is_active", "updated_at"])
    _audit_category(user, request, category, "archive", category_usage(category))
    return category


def restore_personal_category(user, category, *, request=None):
    """Bring an archived category back into use."""
    _require_personal(user, category)
    if category.is_active:
        return category

    # While it was away the user may have created something with the same name.
    clash = find_visible_match(user, category.name, category.category_type)
    if clash is not None and clash.pk != category.pk and clash.is_active:
        raise ValidationError(
            f'"{clash.name}" is in use again — rename one of them first.')

    category.is_active = True
    category.save(update_fields=["is_active", "updated_at"])
    _audit_category(user, request, category, "restore", {})
    return category


def delete_personal_category(user, category, *, request=None):
    """Permanently remove a category — ONLY when nothing depends on it.

    Refused whenever anything references it, and that is not mere caution:
    `Budget.category` is `on_delete=CASCADE`, so deleting a category in use would
    silently delete the user's budgets, and `parent` cascades onto sub-categories.
    Archiving is offered instead, which is what someone almost always meant.
    """
    _require_personal(user, category)

    usage = category_usage(category)
    if any(usage.values()):
        parts = [f"{count} {label}" for label, count in usage.items() if count]
        raise ValidationError(
            "This category is still used by " + ", ".join(parts) +
            ". Archive it instead — that keeps the history and stops it being "
            "offered for anything new.")

    _audit_category(user, request, category, "delete",
                    {"name": category.name, "category_type": category.category_type})
    category.delete()
    return None


def _audit_category(user, request, category, action, details):
    """One audit shape for every management decision, on the existing logger."""
    from apps.finance.security import FinanceAuditLogger

    action_map = {
        "rename": FinanceAuditLogger.ACTION_UPDATE,
        "archive": FinanceAuditLogger.ACTION_UPDATE,
        "restore": FinanceAuditLogger.ACTION_UPDATE,
        "delete": FinanceAuditLogger.ACTION_DELETE,
    }
    try:
        FinanceAuditLogger(user=user, request=request).log(
            action=action_map.get(action, FinanceAuditLogger.ACTION_UPDATE),
            entity_type="transaction_category",
            entity_id=category.pk,
            details={"operation": action, **(details or {})},
        )
    except Exception:
        logger.warning("Could not audit category %s on %s", action, category.pk,
                       exc_info=True)


def manageable_categories(user):
    """Everything the Categories page shows, split the way a person thinks about it.

    ONE query per group, and the same visibility rule the picker uses — a category
    that is offered on a transaction is a category that appears here.
    """
    from apps.finance.models import TransactionCategory

    personal = list(TransactionCategory.objects
                    .filter(user=user)
                    .order_by("category_type", "sort_order", "name"))
    system = list(TransactionCategory.objects
                  .filter(is_system=True, is_active=True)
                  .order_by("category_type", "sort_order", "name"))

    return {
        "personal_active": [c for c in personal if c.is_active],
        "personal_archived": [c for c in personal if not c.is_active],
        "system": system,
    }
