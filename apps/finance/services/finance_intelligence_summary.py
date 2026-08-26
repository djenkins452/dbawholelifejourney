# ==============================================================================
# File: apps/finance/services/finance_intelligence_summary.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The ONE deterministic source behind the Finance intelligence surface.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""What deserves attention, what is uncertain, what is unresolved, how fresh is any of it.

ONE source feeds the dashboard section, the Current Context summary, and (through the
canonical `Insight`/`FinanceOpportunity` records) the Chief of Staff — so the screen and
the assistant can never tell the user different things.

Facts only. It reports amounts, counts, dates, and lifecycle state; it never says an
opportunity is important, and never recommends an action. Bounded by construction: a
handful of indexed queries with hard caps, safe on the request path.

Honest about emptiness. "No findings" and "you have not set up an entity yet" are
completely different truths, and this returns them as different states rather than
rendering an encouraging blank.
"""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from apps.finance.models import (
    FinanceOpportunity,
    FinancialAccount,
    FinancialEntity,
    Transaction,
)

MAX_ATTENTION = 3
MAX_REVIEW = 3
MAX_UNRESOLVED = 3
#: Beyond this, the underlying financial data is old enough that a finding may be stale.
STALE_AFTER_DAYS = 45

SETUP_NO_ACCOUNTS = "no_accounts"
SETUP_NO_ENTITY = "no_entity"
SETUP_NO_ATTRIBUTION = "no_attribution"
SETUP_READY = "ready"


def _setup_state(user, has_business_entity, has_attribution, account_count):
    if not account_count:
        return SETUP_NO_ACCOUNTS
    if not has_business_entity:
        return SETUP_NO_ENTITY
    if not has_attribution:
        return SETUP_NO_ATTRIBUTION
    return SETUP_READY


def build_finance_intelligence(user):
    """The deterministic state of Finance intelligence for one user."""
    from apps.core.ai_insights.models import Insight
    from apps.finance.models import TransactionAttribution
    from apps.finance.services.attribution_review import review_counts

    entities = list(FinancialEntity.objects.filter(user=user, is_active=True)
                    .only("id", "name", "entity_type", "is_default_personal"))
    has_business = any(e.entity_type in (FinancialEntity.TYPE_BUSINESS,
                                         FinancialEntity.TYPE_OTHER)
                       for e in entities)
    account_count = FinancialAccount.objects.filter(user=user).count()
    unassigned_accounts = account_count - (
        FinancialAccount.objects.filter(user=user, entity_assignments__isnull=False)
        .distinct().count()
    )
    has_attribution = TransactionAttribution.objects.filter(
        user=user, attribution_status=TransactionAttribution.STATUS_ACTIVE).exists()

    # 1 — what deserves attention: material, still-open opportunities.
    open_states = (FinanceOpportunity.STATE_DETECTED, FinanceOpportunity.STATE_PRESENTED,
                   FinanceOpportunity.STATE_DEFERRED)
    today = timezone.now().date()
    attention_qs = (FinanceOpportunity.objects
                    .filter(user=user, state__in=open_states)
                    .exclude(state=FinanceOpportunity.STATE_DEFERRED,
                             deferred_until__gt=today)
                    .select_related("attributed_entity", "paid_by_entity")
                    .order_by("-annual_estimate")[:MAX_ATTENTION])
    insight_by_key = {
        i.dedupe_key: i for i in Insight.objects.filter(
            user=user, module="finance",
            dedupe_key__in=[o.dedupe_key for o in attention_qs])
    }
    attention = []
    for opportunity in attention_qs:
        insight = insight_by_key.get(opportunity.dedupe_key)
        attention.append({
            "opportunity": opportunity,
            "label": opportunity.label or "an expense",
            "bearer": opportunity.attributed_entity.name,
            "payer": opportunity.paid_by_entity.name,
            "occurrences": opportunity.occurrences,
            "annual_estimate": float(opportunity.annual_estimate),
            "why": insight.explain_why if insight else "",
            "message": insight.message if insight else "",
            "evidence": (insight.evidence if insight else {}) or {},
            "state": opportunity.state,
            "state_label": opportunity.get_state_display(),
        })

    # 2 — what is uncertain and needs a person.
    counts = review_counts(user)

    # 3 — accepted, still unresolved.
    unresolved = list(FinanceOpportunity.objects
                      .filter(user=user, state__in=(FinanceOpportunity.STATE_ACCEPTED,
                                                    FinanceOpportunity.STATE_IN_PROGRESS))
                      .select_related("attributed_entity")
                      .order_by("accepted_at")[:MAX_UNRESOLVED])

    # 4 — how fresh is the underlying data.
    from apps.finance.models import BankConnection
    incomplete_history = BankConnection.objects.filter(
        user=user, historical_update_complete=False).exclude(
        connection_status=BankConnection.STATUS_DISCONNECTED).exists()

    last_txn = (Transaction.objects.filter(user=user)
                .order_by("-date").values_list("date", flat=True).first())
    age_days = (today - last_txn).days if last_txn else None
    connections = FinancialAccount.objects.filter(user=user, is_synced=True).count()

    return {
        "setup_state": _setup_state(user, has_business, has_attribution, account_count),
        "entities": entities,
        "entity_count": len(entities),
        "has_business_entity": has_business,
        "account_count": account_count,
        "unassigned_accounts": max(unassigned_accounts, 0),
        "attention": attention,
        "attention_count": FinanceOpportunity.objects.filter(
            user=user, state__in=open_states).count(),
        "review_counts": counts,
        "needs_review": counts["unattributed"] + counts["inferred"] + counts["uncertain"],
        "unresolved": unresolved,
        "freshness": {
            "last_transaction_date": last_txn,
            "age_days": age_days,
            "is_stale": bool(age_days is not None and age_days > STALE_AFTER_DAYS),
            "synced_accounts": connections,
            "manual_only": connections == 0,
            # A conclusion drawn from half the history is not a conclusion.
            "history_incomplete": incomplete_history,
            "earliest_transaction_date": (
                Transaction.objects.filter(user=user)
                .order_by("date").values_list("date", flat=True).first()),
        },
    }


def summary_lines(user, intelligence=None):
    """Facts-only lines for the Current Context page summary. Same source as the page."""
    data = intelligence or build_finance_intelligence(user)
    lines = []
    if data["setup_state"] == SETUP_NO_ACCOUNTS:
        lines.append("No financial accounts on file yet.")
    elif data["setup_state"] == SETUP_NO_ENTITY:
        lines.append("Entities set up: Personal only — no business or shared entity yet, "
                     "so expense attribution has not started.")
    elif data["setup_state"] == SETUP_NO_ATTRIBUTION:
        lines.append(f"{data['entity_count']} entities set up; no transaction has been "
                     "attributed to one yet.")
    else:
        lines.append(f"Open opportunities: {data['attention_count']}")
        for item in data["attention"]:
            lines.append(
                f"- {item['label']}: {item['occurrences']} charge(s) attributed to "
                f"{item['bearer']}, paid by {item['payer']} "
                f"(est. ${item['annual_estimate']:,.2f}/yr)")
    lines.append(f"Awaiting review: {data['needs_review']}")
    if data["unresolved"]:
        lines.append(f"Accepted, not yet verified: {len(data['unresolved'])}")
    fresh = data["freshness"]
    if fresh["last_transaction_date"]:
        lines.append(
            f"Most recent transaction: {fresh['last_transaction_date'].isoformat()}"
            f" ({fresh['age_days']} days ago)"
            + (" — data may be out of date" if fresh["is_stale"] else ""))
    if fresh.get("history_incomplete"):
        earliest = fresh.get("earliest_transaction_date")
        lines.append(
            "Historical import is still in progress"
            + (f"; transactions currently start {earliest.isoformat()}"
               if earliest else "")
            + " — totals and trends are provisional.")
    if fresh["manual_only"]:
        lines.append("No connected accounts — transactions arrive by manual entry or import.")
    return lines
