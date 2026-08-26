# ==============================================================================
# File: apps/finance/services/finance_reset.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Permanently remove all Finance operational and derived data.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Return the Finance module to a clean slate — deliberately, and only deliberately.

This is a destructive operation with a narrow blast radius: it removes Finance
operational and derived records and **nothing else**. Users, authentication, feature
grants, provider configuration, system taxonomy, migrations, and every other WLJ domain
are untouched.

Two safety properties matter more than convenience:

  * **It refuses to run while a provider credential exists.** Deleting a live
    `BankConnection` locally would strand Plaid's access to a real bank account with the
    only revocation credential destroyed. Revoke first (`provider_disconnect`), then reset.
  * **It deletes HARD, in dependency order.** Soft-deleted rows are included: a row that
    survives could reappear through the soft-delete manager, or collide on a provider
    identifier, fingerprint, dedupe key, or attribution constraint during the first real
    sync. A "reset" that leaves ghosts is worse than no reset.

Counts only ever leave this module as counts. No amount, description, payee, account
name, identifier, payload, or token is read or reported.
"""
from __future__ import annotations

import logging

from django.db import transaction as db_transaction

logger = logging.getLogger(__name__)


class ProviderCredentialPresent(RuntimeError):
    """A provider connection still holds a credential. Revoke at the provider first."""


def _manager(model):
    """Prefer `all_objects` so soft-deleted rows are included, never left behind."""
    return getattr(model, "all_objects", model.objects)


def _finance_models():
    """Finance models in SAFE DELETION ORDER (dependents before their targets).

    `FinancialEntity` is PROTECTed by attributions, assignments, rules, and
    opportunities, so those come first. Accounts are PROTECTed by assignments.
    """
    from apps.finance import models as m

    return [
        ("transaction_attributions", m.TransactionAttribution, None),
        ("attribution_rules", m.AttributionRule, None),
        ("finance_opportunities", m.FinanceOpportunity, None),
        ("account_entity_assignments", m.AccountEntityAssignment, None),
        ("financial_entities", m.FinancialEntity, None),
        ("transactions", m.Transaction, None),
        ("recurring_transactions", m.RecurringTransaction, None),
        ("budgets", m.Budget, None),
        ("financial_goals", m.FinancialGoal, None),
        ("metric_snapshots", m.FinancialMetricSnapshot, None),
        ("transaction_imports", m.TransactionImport, None),
        ("payees", m.Payee, None),
        # User-created categories only. System taxonomy (user IS NULL, is_system) is
        # reference data the module needs to function and is deliberately preserved.
        ("user_categories", m.TransactionCategory, {"is_system": False}),
        ("bank_integration_logs", m.BankIntegrationLog, None),
        ("bank_connections", m.BankConnection, None),
        ("finance_audit_logs", m.FinanceAuditLog, None),
        ("financial_accounts", m.FinancialAccount, None),
    ]


def _derived_sources():
    """Finance-derived records living OUTSIDE apps/finance."""
    from apps.ai.models import ConversationFollowUp
    from apps.core.ai_insights.models import Insight
    from apps.core.models import Notification

    return [
        ("finance_insights", Insight, {"module": "finance"}),
        ("finance_notifications", Notification, {"category": "finance"}),
        ("finance_follow_ups", ConversationFollowUp,
         {"subject_ref__startswith": "finance."}),
    ]


def inventory():
    """Redacted census: counts by model, split by ownership state. Reads no values."""
    from django.contrib.auth import get_user_model
    from apps.finance import models as m

    User = get_user_model()
    report = {"finance_models": {}, "derived": {}, "ownership": {}, "provider": {}}

    for key, model, extra in _finance_models():
        queryset = _manager(model).all()
        if extra:
            queryset = queryset.filter(**extra)
        total = queryset.count()
        entry = {"total": total}
        if hasattr(model, "status"):
            entry["soft_deleted"] = queryset.exclude(status="active").count()
        if any(f.name == "user" for f in model._meta.fields):
            entry["orphaned_no_user"] = queryset.filter(user__isnull=True).count()
            entry["distinct_owners"] = (
                queryset.values("user_id").distinct().count())
        report["finance_models"][key] = entry

    for key, model, filters in _derived_sources():
        report["derived"][key] = _manager(model).filter(**filters).count()

    # Preserved reference data, reported so the operator can see it survive.
    report["preserved"] = {
        "system_categories": m.TransactionCategory.objects.filter(
            is_system=True).count(),
        "users_total": User.objects.count(),
        "finance_enabled_users": User.objects.filter(
            preferences__finances_enabled=True).count(),
    }

    connections = _manager(m.BankConnection).all()
    report["provider"] = {
        "connections": connections.count(),
        "with_stored_token": connections.exclude(access_token_encrypted="").count(),
        "live_access": sum(1 for c in connections if c.has_live_provider_access),
    }
    report["state_rows_with_finance_key"] = _user_states_with_finance().count()
    return report


def _user_states_with_finance():
    from apps.core.ai_state.models import UserState
    return UserState.objects.filter(state_data__has_key="finance")


def assert_no_provider_credentials():
    """Refuse to delete anything while a provider credential still exists."""
    from apps.finance.models import BankConnection

    connections = _manager(BankConnection).exclude(access_token_encrypted="")
    count = connections.count()
    if count:
        raise ProviderCredentialPresent(
            f"{count} bank connection(s) still hold a provider access token. Revoke them "
            "at the provider first (finance.services.provider_disconnect), otherwise "
            "deleting locally strands live access with no way to withdraw it."
        )
    return True


@db_transaction.atomic
def reset(*, actor=None):
    """Delete every Finance operational and derived record. Idempotent.

    Runs inside one transaction: it either fully completes or changes nothing.
    Returns redacted counts of what was removed.
    """
    assert_no_provider_credentials()

    affected_user_ids = _affected_user_ids()
    removed = {}

    for key, model, extra in _finance_models():
        queryset = _manager(model).all()
        if extra:
            queryset = queryset.filter(**extra)
        # Hard delete. A surviving row could reappear through the soft-delete manager or
        # collide on a provider id, fingerprint, dedupe key, or attribution constraint.
        removed[key] = queryset.delete()[0]

    for key, model, filters in _derived_sources():
        removed[key] = _manager(model).filter(**filters).delete()[0]

    removed["state_finance_keys_cleared"] = _strip_finance_state()
    _record_reset(actor, removed)
    return {"removed": removed, "affected_users": len(affected_user_ids),
            "user_ids": affected_user_ids}


def _affected_user_ids():
    from apps.finance.models import FinancialAccount, Transaction
    ids = set()
    for model in (FinancialAccount, Transaction):
        ids.update(_manager(model).values_list("user_id", flat=True).distinct())
    ids.discard(None)
    return sorted(ids)


def _strip_finance_state():
    """Remove the `finance` key from SAE state WITHOUT touching other domains.

    Deleting the row would destroy health, goals, faith and everything else stored
    alongside it — a different domain's data, which this reset must never touch.
    """
    cleared = 0
    for state in _user_states_with_finance():
        data = state.state_data or {}
        if "finance" in data:
            data.pop("finance", None)
            state.state_data = data
            state.save(update_fields=["state_data"])
            cleared += 1
    return cleared


def _record_reset(actor, removed):
    """Leave redacted evidence that the reset happened — counts only."""
    from apps.finance.models import FinanceAuditLog

    FinanceAuditLog.objects.create(
        user=actor,
        action=FinanceAuditLog.ACTION_RESET,
        entity_type="module",
        entity_id=None,
        success=True,
        details={"removed": {k: v for k, v in removed.items() if v},
                 "scope": "all_finance_operational_and_derived"},
    )
    logger.warning("FINANCE RESET completed: %s",
                   {k: v for k, v in removed.items() if v})


def invalidate_caches(user_ids):
    """Drop Finance-derived caches so no stale fact can be served after the wipe."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    cleared = 0
    for user in User.objects.filter(id__in=user_ids):
        try:
            from apps.ai.readiness_cache import invalidate_cos_context
            invalidate_cos_context(user)
            cleared += 1
        except Exception:
            logger.warning("CoS cache invalidation failed for a user", exc_info=True)
    return cleared
