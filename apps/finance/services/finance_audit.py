# ==============================================================================
# File: apps/finance/services/finance_audit.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Read-only aggregate health audit of Finance truth (operator tooling).
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Is Finance truth healthy, and is there enough real history to trust a finding?

**READ-ONLY and AGGREGATE-ONLY.** No transaction description, payee, amount, account
number, institution, or token is ever returned. Users appear as a redacted handle, never
an address. Nothing here writes, and nothing here calls a model or a provider.

It answers three operator questions:
  1. what does production actually hold (entities, assignments, attribution, findings)?
  2. is any of it structurally broken (cross-user references, accounts with no owner)?
  3. is there enough real financial history for a finding to be trustworthy?
"""
from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Count, F, Max, Min, Q, Sum

from apps.finance.models import (
    AccountEntityAssignment,
    AttributionRule,
    BankConnection,
    FinanceOpportunity,
    FinancialAccount,
    FinancialEntity,
    Transaction,
    TransactionAttribution,
)

#: Below this, a "pattern" is one or two rows and a finding cannot be trusted.
MIN_TRANSACTIONS_FOR_TRUST = 50
MIN_MONTHS_FOR_TRUST = 2


def redact(email):
    """`d***@gmail.com` — enough to tell users apart, not enough to identify them."""
    email = email or ""
    if "@" not in email:
        return "***"
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


def _counts_by(queryset, field):
    return {row[field]: row["n"] for row in
            queryset.values(field).annotate(n=Count("id")).order_by()}


def audit():
    """One aggregate snapshot of Finance truth in this environment."""
    User = get_user_model()

    finance_user_ids = set()
    for model in (FinancialAccount, Transaction, BankConnection):
        finance_user_ids.update(model.objects.values_list("user_id", flat=True).distinct())

    txns = Transaction.objects.all()
    accounts = FinancialAccount.objects.all()

    # -- population classes (aggregate counts only) --------------------------
    opening = txns.filter(is_opening_balance=True).count()
    paired = txns.filter(transfer_pair__isnull=False).count()
    categorised_transfer = txns.filter(category__category_type="transfer").count()
    pending = txns.filter(plaid_pending=True).count()

    from apps.finance.services.attribution_population import (
        financial_activity, liability_account_names, suspected_internal_transfer_q,
    )

    suspected = 0
    eligible = 0
    unattributed = 0
    for user in User.objects.filter(id__in=finance_user_ids).iterator():
        names = liability_account_names(user)
        suspected += Transaction.objects.filter(user=user).filter(
            suspected_internal_transfer_q(user, names)).count()
        user_eligible = financial_activity(user).exclude(plaid_pending=True).exclude(
            suspected_internal_transfer_q(user, names))
        eligible += user_eligible.count()
        attributed_ids = TransactionAttribution.objects.filter(
            user=user, attribution_status=TransactionAttribution.STATUS_ACTIVE,
        ).values_list("transaction_id", flat=True)
        unattributed += user_eligible.exclude(id__in=attributed_ids).count()

    # -- convergence delta (the F4 measurement) -------------------------------
    old_metrics = txns.filter(is_opening_balance=False).exclude(
        transfer_pair__isnull=False).aggregate(t=Sum("amount"))["t"] or Decimal("0")
    converged = txns.filter(is_opening_balance=False).exclude(
        Q(transfer_pair__isnull=False)
        | Q(category__category_type="transfer")).aggregate(
        t=Sum("amount"))["t"] or Decimal("0")

    # -- integrity: cross-user references -------------------------------------
    integrity = {
        "attribution_entity_mismatch": TransactionAttribution.objects.exclude(
            attributed_entity__user_id=F("user_id")).count(),
        "attribution_payer_mismatch": TransactionAttribution.objects.exclude(
            paid_by_entity__user_id=F("user_id")).count(),
        "attribution_transaction_mismatch": TransactionAttribution.objects.exclude(
            transaction__user_id=F("user_id")).count(),
        "assignment_account_mismatch": AccountEntityAssignment.objects.exclude(
            account__user_id=F("user_id")).count(),
        "assignment_entity_mismatch": AccountEntityAssignment.objects.exclude(
            entity__user_id=F("user_id")).count(),
        "rule_entity_mismatch": AttributionRule.objects.exclude(
            entity__user_id=F("user_id")).count(),
        "opportunity_entity_mismatch": FinanceOpportunity.objects.exclude(
            attributed_entity__user_id=F("user_id")).count(),
    }

    # -- ingestion reality ----------------------------------------------------
    span = txns.aggregate(first=Min("date"), last=Max("date"))
    months = 0
    if span["first"] and span["last"]:
        months = ((span["last"].year - span["first"].year) * 12
                  + span["last"].month - span["first"].month + 1)
    connections = BankConnection.objects.all()
    # Legacy plaintext credentials, COUNTED never displayed. A non-zero count is a stop
    # condition: the value is potentially the only credential able to revoke a live Item.
    legacy_plaintext = connections.filter(
        access_token_encrypted__startswith="UNENCRYPTED:").count()
    tokens_stored = connections.exclude(access_token_encrypted="").count()

    from apps.core.ai_insights.models import Insight
    finance_insights = Insight.objects.filter(module="finance")

    accounts_with_owner = AccountEntityAssignment.objects.values(
        "account_id").distinct().count()

    provider = _provider_state()

    return {
        "environment": {
            "provider": provider,
            "finance_active_users": len(finance_user_ids),
            "total_users": User.objects.count(),
            # Explicit capability grants — the trial population, as a COUNT only.
            "finance_enabled_users": User.objects.filter(
                preferences__finances_enabled=True).count(),
        },
        "entities": {
            "total": FinancialEntity.objects.count(),
            "by_type": _counts_by(FinancialEntity.objects.all(), "entity_type"),
            "active": FinancialEntity.objects.filter(is_active=True).count(),
            "users_with_entities": FinancialEntity.objects.values(
                "user_id").distinct().count(),
        },
        "accounts": {
            "total": accounts.count(),
            "with_entity_assignment": accounts_with_owner,
            "without_entity_assignment": max(accounts.count() - accounts_with_owner, 0),
            "assignments_total": AccountEntityAssignment.objects.count(),
            "assignments_open": AccountEntityAssignment.objects.filter(
                effective_to__isnull=True).count(),
        },
        "transactions": {
            "total_active": txns.count(),
            "eligible_for_attribution": eligible,
            "ineligible": max(txns.count() - eligible, 0),
            "opening_balances": opening,
            "known_transfers_paired": paired,
            "known_transfers_categorised": categorised_transfer,
            "suspected_unpaired_transfers": suspected,
            "pending": pending,
            "unattributed_eligible": unattributed,
            "first_date": span["first"].isoformat() if span["first"] else None,
            "last_date": span["last"].isoformat() if span["last"] else None,
            "months_of_history": months,
        },
        "attribution": {
            "active": TransactionAttribution.objects.filter(
                attribution_status=TransactionAttribution.STATUS_ACTIVE).count(),
            "superseded": TransactionAttribution.objects.filter(
                attribution_status=TransactionAttribution.STATUS_SUPERSEDED).count(),
            "by_source": _counts_by(TransactionAttribution.objects.filter(
                attribution_status=TransactionAttribution.STATUS_ACTIVE), "source"),
            "user_confirmed": TransactionAttribution.objects.filter(
                attribution_status=TransactionAttribution.STATUS_ACTIVE,
                user_confirmed=True).count(),
            "inferred": TransactionAttribution.objects.filter(
                attribution_status=TransactionAttribution.STATUS_ACTIVE,
                user_confirmed=False).count(),
        },
        "rules": {
            "total": AttributionRule.objects.count(),
            "active": AttributionRule.objects.filter(
                rule_status=AttributionRule.STATUS_ACTIVE).count(),
            "by_scope": _counts_by(AttributionRule.objects.all(), "scope"),
        },
        "insights": {
            "finance_total": finance_insights.count(),
            "active": finance_insights.exclude(status="dismissed").count(),
            "by_status": _counts_by(finance_insights, "status"),
        },
        "opportunities": {
            "total": FinanceOpportunity.objects.count(),
            "by_state": _counts_by(FinanceOpportunity.objects.all(), "state"),
        },
        # Only the DELTA is reported. The absolute totals are a customer's finances, and
        # with few rows they would be a single transaction's amount — an operator needs to
        # know whether convergence MOVED anything, not what anyone spent.
        "convergence": {
            "delta": float(converged - old_metrics),
            "totals_changed": bool(converged != old_metrics),
            "rows_affected": categorised_transfer + paired,
        },
        "credentials": {
            "connections_with_stored_token": tokens_stored,
            "legacy_plaintext_tokens": legacy_plaintext,
            "all_tokens_encrypted": legacy_plaintext == 0,
        },
        "sync": {
            "connections": connections.count(),
            "institutions": connections.values("institution_name").distinct().count()
            if connections.exists() else 0,
            "last_sync": _last_sync(connections),
            "accounts_synced": accounts.filter(is_synced=True).count(),
        },
        "dependencies": _installed_distributions(),
        "integrity": integrity,
        "readiness": _readiness(eligible, months, len(finance_user_ids), integrity),
    }


def _last_sync(connections):
    if not connections.exists():
        return None
    latest = connections.aggregate(last=Max("last_sync_at"))["last"] \
        if _has_field(connections.model, "last_sync_at") else None
    return latest.isoformat() if latest else None


def _has_field(model, name):
    return any(f.name == name for f in model._meta.fields)


def _provider_state():
    """Booleans and versions only — never a key value, not even a prefix."""
    import sys

    import django
    from django.conf import settings

    from apps.finance.services.encryption import encryption_available

    try:
        from importlib.metadata import version as _pkg_version
        plaid_version = _pkg_version("plaid-python")
    except Exception:
        plaid_version = None

    return {
        "plaid_env": getattr(settings, "PLAID_ENV", "unset"),
        "plaid_configured": bool(getattr(settings, "PLAID_CLIENT_ID", "")
                                 and getattr(settings, "PLAID_SECRET", "")),
        # The single fact that decides whether a token can be stored at all.
        "bank_token_encryption_configured": encryption_available(),
        "python": sys.version.split()[0],
        "django": django.get_version(),
        "plaid_python": plaid_version,
    }


def _installed_distributions():
    """The RESOLVED dependency set of this environment: {name: version}.

    Package names and versions are public metadata — no secret, no user data. This is
    what makes the deployed set auditable, since the repository pins ranges rather than
    exact versions.
    """
    try:
        from importlib.metadata import distributions
    except Exception:
        return {}
    resolved = {}
    for dist in distributions():
        try:
            name = dist.metadata["Name"]
        except Exception:
            continue
        if name:
            resolved[name] = dist.version
    return dict(sorted(resolved.items(), key=lambda kv: kv[0].lower()))


def _readiness(eligible, months, users, integrity):
    """Is production healthy, and is there enough real history to trust a finding?"""
    problems = [k for k, v in integrity.items() if v]
    if problems:
        return {"status": "unhealthy", "reason": "cross_user_references",
                "detail": problems}
    if users == 0 or eligible == 0:
        return {"status": "no_data",
                "reason": "no finance-active users or no eligible transactions"}
    if eligible < MIN_TRANSACTIONS_FOR_TRUST or months < MIN_MONTHS_FOR_TRUST:
        return {"status": "thin",
                "reason": f"{eligible} eligible transactions over {months} month(s); "
                          f"a pattern needs at least {MIN_TRANSACTIONS_FOR_TRUST} rows "
                          f"and {MIN_MONTHS_FOR_TRUST} months to be trustworthy"}
    return {"status": "healthy", "reason": "sufficient history and no integrity faults"}
