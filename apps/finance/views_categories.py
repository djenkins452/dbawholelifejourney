# ==============================================================================
# File: apps/finance/views_categories.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Choosing or creating a transaction's category, in place.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Set a transaction's category without leaving the page.

Reached through ordinary Finance permissions — `finance_enabled_required`, the same
capability gate every other Finance surface uses. Nothing here needs staff access or
Django admin; a category is the user's own description of their own money.

One endpoint deliberately covers both "pick an existing one" and "create this one and
use it", because they are the same intention. Splitting them would make the common case
two round trips and leave a window where a category exists but nothing is categorised.
"""
from __future__ import annotations

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from apps.finance.access import finance_enabled_required
from apps.finance.models import Transaction, TransactionCategory
from apps.finance.services import category_assignment as categories


@login_required
@finance_enabled_required
def category_options(request, pk):
    """What this transaction may be categorised as, and what it is now."""
    transaction = get_object_or_404(
        Transaction, pk=pk, user=request.user, status="active")
    payload = categories.category_choices(request.user, transaction)
    payload["success"] = True
    payload["transaction_id"] = transaction.pk
    return JsonResponse(payload)


@login_required
@finance_enabled_required
@require_POST
def category_set(request, pk):
    """Assign an existing category, or create one by name and assign it.

    Body: {"category_id": int}            — choose an existing category
          {"new_name": str}               — create (or reuse) by name, then assign
          {"category_id": null}           — clear the category

    `category_type` is NOT accepted from the client: it is derived from the transaction
    itself (see `infer_category_type`), so creating a category asks for a name and
    nothing else.
    """
    try:
        payload = json.loads(request.body or "{}")
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"success": False, "error": "Invalid request."}, status=400)

    transaction = get_object_or_404(
        Transaction, pk=pk, user=request.user, status="active")

    created = False
    reused = False
    new_name = (payload.get("new_name") or "").strip()

    if new_name:
        try:
            category, created = categories.resolve_or_create_category(
                request.user, new_name,
                categories.infer_category_type(transaction),
            )
        except ValidationError as exc:
            return JsonResponse({"success": False, "error": "; ".join(exc.messages)},
                                status=400)
        reused = not created
        if created:
            categories.audit_category_created(request.user, category, request=request)
    elif payload.get("category_id"):
        # Ownership is enforced in the LOOKUP, not after it: a category belonging to
        # someone else is simply not found, so one user can never reach another's.
        category = get_object_or_404(
            TransactionCategory.objects.filter(
                pk=payload["category_id"]).filter(
                    _visible_to(request.user)),
        )
    else:
        category = None

    try:
        categories.assign_category(request.user, transaction, category,
                                   request=request)
    except ValidationError as exc:
        return JsonResponse({"success": False, "error": "; ".join(exc.messages)},
                            status=400)

    return JsonResponse({
        "success": True,
        "transaction_id": transaction.pk,
        "category": ({"id": category.pk, "name": category.name,
                      "type": category.category_type,
                      "personal": category.user_id is not None}
                     if category else None),
        "created": created,
        "reused": reused,
        "category_source": transaction.category_source,
    })


def _visible_to(user):
    """System categories, plus this user's own. Never anyone else's."""
    from django.db.models import Q
    return Q(is_system=True) | Q(user=user)


# =============================================================================
# Categories page — managing personal categories
# =============================================================================
#
# Ordinary Finance permissions throughout: `finance_enabled_required`, the same
# gate as every other Finance surface. Nothing here needs staff or Django admin.
# Ownership is enforced in the LOOKUP, so another user's category is simply not
# found rather than found-then-refused.

def _owned_category(request, pk):
    """This user's own category, or a 404. Never anyone else's, never a system row."""
    from apps.finance.models import TransactionCategory
    return get_object_or_404(
        TransactionCategory, pk=pk, user=request.user, is_system=False)


def _back(request):
    return redirect("finance:category_list")


@login_required
@finance_enabled_required
@require_POST
def category_create(request):
    """Create a personal income or expense category."""
    name = (request.POST.get("name") or "").strip()
    category_type = (request.POST.get("category_type") or "").strip()

    try:
        category, created = categories.create_personal_category(
            request.user, name, category_type, request=request)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
        return _back(request)

    if created:
        messages.success(request, f'Category "{category.name}" created.')
    else:
        messages.info(
            request,
            f'"{category.name}" already exists — no duplicate was created.')
    return _back(request)


@login_required
@finance_enabled_required
@require_POST
def category_rename(request, pk):
    """Rename a personal category."""
    category = _owned_category(request, pk)
    try:
        categories.rename_personal_category(
            request.user, category, request.POST.get("name"), request=request)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(request, f'Renamed to "{category.name}".')
    return _back(request)


@login_required
@finance_enabled_required
@require_POST
def category_archive(request, pk):
    """Stop offering a category without disturbing anything already using it."""
    category = _owned_category(request, pk)
    try:
        categories.archive_personal_category(request.user, category,
                                             request=request)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(
            request,
            f'"{category.name}" archived. Transactions already using it keep it.')
    return _back(request)


@login_required
@finance_enabled_required
@require_POST
def category_restore(request, pk):
    """Bring an archived category back."""
    category = _owned_category(request, pk)
    try:
        categories.restore_personal_category(request.user, category,
                                             request=request)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(request, f'"{category.name}" restored.')
    return _back(request)


@login_required
@finance_enabled_required
@require_POST
def category_delete(request, pk):
    """Delete a personal category — only when nothing depends on it."""
    category = _owned_category(request, pk)
    name = category.name
    try:
        categories.delete_personal_category(request.user, category,
                                            request=request)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(request, f'"{name}" deleted.')
    return _back(request)
