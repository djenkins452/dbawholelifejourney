# ==============================================================================
# File: apps/finance/services/attribution_review.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: F2 — the deterministic review queue and scoped decision application.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""What still needs a human decision, and what a decision does once it is made.

ONE deterministic source feeds BOTH the review page and its Current Context summary —
never two independent derivations (the drift class the Current Context Contract exists to
eliminate).

A decision may be applied at three bounded scopes:
  * `transaction`  — just this one;
  * `payee`        — this vendor from now on (a rule);
  * `recurring`    — this recurring commitment (a rule).

Applying to a scope also settles the transactions already sitting in that scope, EXCEPT
any the user has already confirmed — a batch decision never overrules an individual one.
That is how a user makes exceptions inside a batch: confirm the exception, then apply the
batch; the exception stands.
"""
from __future__ import annotations

from django.db.models import Exists, OuterRef

from apps.finance.models import Payee, Transaction, TransactionAttribution
from apps.finance.services import attribution as attribution_service
from apps.finance.services import attribution_population as population
from apps.finance.services import attribution_rules as rules_service
from apps.finance.services.finance_entities import _require_same_user

#: How many transactions a single scoped decision may settle. Bounded on purpose: a rule
#: should reduce future review burden, not silently rewrite years of history in one click.
MAX_SCOPE_APPLY = 200
REVIEW_PAGE_SIZE = 50


def _active_attribution_subquery():
    return TransactionAttribution.objects.filter(
        transaction=OuterRef("pk"),
        attribution_status=TransactionAttribution.STATUS_ACTIVE,
    )


def unattributed(user, *, limit=REVIEW_PAGE_SIZE, liability_names=None):
    """Attributable transactions nobody has decided on yet — ONE query."""
    return (population.attributable_transactions(user, liability_names=liability_names)
            .annotate(has_attribution=Exists(_active_attribution_subquery()))
            .filter(has_attribution=False)
            .select_related("account", "category")
            .order_by("-date", "-id")[:limit])


def inferred_attributions(user, *, limit=REVIEW_PAGE_SIZE):
    """Decided by a rule or by account default — still awaiting a human's word."""
    return (TransactionAttribution.objects
            .filter(user=user,
                    attribution_status=TransactionAttribution.STATUS_ACTIVE,
                    user_confirmed=False,
                    transaction__status="active")
            .select_related("transaction", "transaction__account",
                            "attributed_entity", "paid_by_entity", "rule")
            .order_by("-transaction__date", "-id")[:limit])


def uncertain(user, *, limit=REVIEW_PAGE_SIZE, liability_names=None):
    """Structurally uncertain rows — pending, or a suspected internal transfer.

    Surfaced with the REASON, never silently attributed and never silently dropped.
    """
    rows = (population.review_candidates(user, liability_names=liability_names)
            .select_related("account", "category")
            .order_by("-date", "-id")[:limit])
    names = liability_names if liability_names is not None \
        else population.liability_account_names(user)
    return [(txn, population.exclusion_reason(txn, names)) for txn in rows]


def review_counts(user):
    """The deterministic counts behind both the page and its Current Context summary."""
    names = population.liability_account_names(user)
    active_unattributed = (
        population.attributable_transactions(user, liability_names=names)
        .annotate(has_attribution=Exists(_active_attribution_subquery()))
        .filter(has_attribution=False).count()
    )
    return {
        "unattributed": active_unattributed,
        "inferred": TransactionAttribution.objects.filter(
            user=user, attribution_status=TransactionAttribution.STATUS_ACTIVE,
            user_confirmed=False, transaction__status="active").count(),
        "uncertain": population.review_candidates(user, liability_names=names).count(),
        "confirmed": TransactionAttribution.objects.filter(
            user=user, attribution_status=TransactionAttribution.STATUS_ACTIVE,
            user_confirmed=True).count(),
    }


def explain(transaction, attribution=None):
    """Why WLJ proposed what it proposed — in the user's terms, always available."""
    if attribution is None:
        return "No one has decided who this belongs to yet."
    if attribution.user_confirmed:
        return "You confirmed this."
    if attribution.source == TransactionAttribution.SOURCE_USER_RULE and attribution.rule_id:
        scope = attribution.rule.get_scope_display().lower()
        return (f"A rule you created for this {scope} assigns it to "
                f"{attribution.attributed_entity.name}.")
    if attribution.source == TransactionAttribution.SOURCE_ACCOUNT_DEFAULT:
        return (f"The account that paid it belonged to "
                f"{attribution.paid_by_entity.name} on {transaction.date:%b %-d, %Y}.")
    if attribution.source == TransactionAttribution.SOURCE_IMPORT_DECLARED:
        return "The import that created this transaction declared the entity."
    return f"Assigned automatically ({attribution.get_source_display().lower()})."


def resolve_payee(user, transaction):
    """The user-owned Payee row behind a transaction, if there is one."""
    name = (transaction.payee or "").strip()
    if not name:
        return None
    return Payee.objects.filter(user=user, name__iexact=name).first()


def apply_decision(user, transaction, entity, *, scope="transaction"):
    """Record a user decision and, for a scoped decision, settle its siblings.

    Returns `{"confirmed": <attribution>, "rule": <rule|None>, "also_settled": int}`.
    A user-confirmed sibling is NEVER overwritten — an exception made inside a batch
    survives the batch.
    """
    _require_same_user(user, transaction=transaction, entity=entity)
    confirmed = attribution_service.confirm(
        user, transaction, entity,
        evidence={"account_id": transaction.account_id, "matched_on": scope},
    )
    rule, settled = None, 0

    if scope == "payee":
        payee = resolve_payee(user, transaction)
        if payee is not None:
            rule = rules_service.create_rule(
                user, scope="payee", entity=entity, payee=payee,
            )
            settled = _settle_scope(
                user, entity, rule,
                Transaction.objects.filter(user=user, payee__iexact=payee.name),
                exclude_id=transaction.id,
            )
    elif scope == "recurring" and transaction.recurring_source_id:
        rule = rules_service.create_rule(
            user, scope="recurring_series", entity=entity,
            recurring=transaction.recurring_source,
        )
        settled = _settle_scope(
            user, entity, rule,
            Transaction.objects.filter(
                user=user, recurring_source_id=transaction.recurring_source_id),
            exclude_id=transaction.id,
        )
    return {"confirmed": confirmed, "rule": rule, "also_settled": settled}


def _settle_scope(user, entity, rule, queryset, *, exclude_id=None):
    """Apply a new rule to the transactions already in its scope.

    Skips anything the user confirmed (their word stands) and anything not attributable
    (uncertain rows are never settled to shrink a queue).
    """
    confirmed_ids = set(
        TransactionAttribution.objects
        .filter(user=user, attribution_status=TransactionAttribution.STATUS_ACTIVE,
                user_confirmed=True)
        .values_list("transaction_id", flat=True)
    )
    names = population.liability_account_names(user)
    candidates = (queryset.exclude(id=exclude_id)
                  .exclude(id__in=confirmed_ids)
                  .select_related("account", "category")[:MAX_SCOPE_APPLY])

    settled = 0
    for txn in candidates:
        if population.exclusion_reason(txn, names) is not None:
            continue
        try:
            rules_service.apply_rule(user, txn, rule)
            settled += 1
        except attribution_service.AttributionConflict:
            continue  # a confirmation appeared underneath us; it wins
    return settled
