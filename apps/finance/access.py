# ==============================================================================
# File: apps/finance/access.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Who may reach Finance and provider workflows. Capability, not identity.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Finance access is an explicitly-granted capability, never a default.

Signing up must not grant access to a bank connection. `UserPreferences.finances_enabled`
already defaults to **False** (`apps/users/models.py:341`) but was enforced nowhere — the
flag only shaped navigation, so any authenticated user could open `/finance/connections/`
and start a provider link.

This module makes the flag an actual gate.

**No identity is hardcoded.** There is no name, email, or user id here — eligibility is a
per-user capability an administrator grants, so the trial population is whoever has been
explicitly approved, not whoever the code happens to know about.
"""
from __future__ import annotations

import functools

from django.core.exceptions import PermissionDenied
from django.http import JsonResponse


def finance_access_granted(user) -> bool:
    """Has this user been explicitly granted Finance access?"""
    if not getattr(user, "is_authenticated", False):
        return False
    preferences = getattr(user, "preferences", None)
    return bool(getattr(preferences, "finances_enabled", False))


def _denied(request):
    wants_json = (request.headers.get("Accept", "").startswith("application/json")
                  or request.headers.get("X-Requested-With") == "XMLHttpRequest"
                  or request.method == "POST")
    if wants_json:
        return JsonResponse({
            "success": False,
            "error": "Finance is not enabled for this account.",
            "finance_enabled": False,
        }, status=403)
    raise PermissionDenied("Finance is not enabled for this account.")


def finance_enabled_required(view_func):
    """Gate a function view behind the explicit Finance capability."""
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not finance_access_granted(request.user):
            return _denied(request)
        return view_func(request, *args, **kwargs)
    return wrapper


class FinanceEnabledRequiredMixin:
    """Gate a class-based view behind the explicit Finance capability.

    Place it BEFORE `LoginRequiredMixin` in the MRO so an anonymous visitor is sent to
    log in rather than told the feature is off.
    """

    def dispatch(self, request, *args, **kwargs):
        if getattr(request.user, "is_authenticated", False) and \
                not finance_access_granted(request.user):
            return _denied(request)
        return super().dispatch(request, *args, **kwargs)


def grant_finance_access(user, *, granted_by):
    """Administrative grant. `granted_by` must be staff — recorded, never inferred."""
    if not getattr(granted_by, "is_staff", False):
        raise PermissionDenied("Only staff may grant Finance access.")
    preferences = user.preferences
    preferences.finances_enabled = True
    preferences.save(update_fields=["finances_enabled"])
    return preferences


def revoke_finance_access(user, *, revoked_by):
    """Administrative revoke. Does NOT touch provider connections — disconnect does."""
    if not getattr(revoked_by, "is_staff", False):
        raise PermissionDenied("Only staff may revoke Finance access.")
    preferences = user.preferences
    preferences.finances_enabled = False
    preferences.save(update_fields=["finances_enabled"])
    return preferences
