# ==============================================================================
# File: apps/finance/services/attribution_rules.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: F0 — user-owned attribution rules: creation, precedence, application.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""User-owned rules that assign an entity to future transactions.

Rules exist to reduce review burden — never to manufacture confidence. Three guarantees:

  1. **No rule is ever created from inference.** Every rule originates in an explicit user
     decision. The broadest scope (account) is user-authored only.
  2. **Precedence is specificity, not scoring**: recurring series → payee → account.
     Deterministic, explainable, no model involved.
  3. **Category can never be a scope.** `TransactionCategory.user` is nullable with
     `is_system` (models.py:315) — system categories are shared across every user, so a
     category-anchored rule would leak one user's attribution into another's.

Applying a rule produces an INFERRED attribution (`source=user_rule`). It carries the
user's confidence but never their confirmation — a rule can never mark a row
`user_confirmed`.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction
from django.utils import timezone

from apps.finance.models import AttributionRule, TransactionAttribution
from apps.finance.services.attribution import attribute
from apps.finance.services.finance_entities import _require_same_user

#: The anchor field each scope requires.
SCOPE_ANCHOR_FIELD = {
    AttributionRule.SCOPE_RECURRING: "recurring",
    AttributionRule.SCOPE_PAYEE: "payee",
    AttributionRule.SCOPE_ACCOUNT: "account",
}


@db_transaction.atomic
def create_rule(user, *, scope, entity, payee=None, recurring=None, account=None,
                origin=AttributionRule.ORIGIN_USER_CONFIRMATION, confidence=1.0,
                effective_from=None, notes=""):
    """Create a user-owned rule. Supersedes any existing active rule on the same anchor."""
    if scope not in SCOPE_ANCHOR_FIELD:
        raise ValidationError(
            f"Scope {scope!r} is not available. Description patterns are reserved for a "
            "later phase, and category is never a scope."
        )
    anchors = {"payee": payee, "recurring": recurring, "account": account}
    required = SCOPE_ANCHOR_FIELD[scope]
    if anchors[required] is None:
        raise ValidationError(f"A {scope} rule needs a {required}.")
    for field, obj in anchors.items():
        if field != required and obj is not None:
            raise ValidationError(f"A {scope} rule must not also set {field}.")

    _require_same_user(user, entity=entity, **{required: anchors[required]})
    if not entity.is_active:
        raise ValidationError("Cannot create a rule pointing at a retired entity.")

    existing = (AttributionRule.objects
                .filter(user=user, scope=scope, rule_status=AttributionRule.STATUS_ACTIVE,
                        **{required: anchors[required]})
                .first())
    rule = AttributionRule.objects.create(
        user=user, scope=scope, entity=entity, origin=origin, confidence=confidence,
        effective_from=effective_from, notes=notes, user_confirmed=True,
        **{required: anchors[required]},
    )
    if existing is not None:
        existing.rule_status = AttributionRule.STATUS_SUPERSEDED
        existing.superseded_by = rule
        existing.save(update_fields=["rule_status", "superseded_by", "updated_at"])
    return rule


def active_rules(user):
    """Every active rule for a user — ONE query, indexed. Callers build their own map."""
    return (AttributionRule.objects
            .filter(user=user, rule_status=AttributionRule.STATUS_ACTIVE)
            .select_related("entity"))


def build_rule_index(user):
    """{scope: {anchor_id: rule}} preloaded once per batch — never a lookup per row."""
    index = {scope: {} for scope in SCOPE_ANCHOR_FIELD}
    for rule in active_rules(user):
        anchor = rule.anchor_id
        if anchor is None or rule.scope not in index:
            continue
        current = index[rule.scope].get(anchor)
        if current is None or _outranks(rule, current):
            index[rule.scope][anchor] = rule
    return index


def _outranks(candidate, incumbent):
    """Within one scope: confirmed first, then the newer effective date, then newer id."""
    if candidate.user_confirmed != incumbent.user_confirmed:
        return candidate.user_confirmed
    a = candidate.effective_from or candidate.created_at.date()
    b = incumbent.effective_from or incumbent.created_at.date()
    if a != b:
        return a > b
    return candidate.id > incumbent.id


def match_rule(transaction, rule_index, *, payee_id=None):
    """The winning rule for a transaction — most specific scope first.

    `payee_id` is passed in by batch callers that already resolved the user's Payee rows,
    so matching never issues a query per transaction.
    """
    for scope in AttributionRule.SCOPE_PRECEDENCE:
        bucket = rule_index.get(scope)
        if not bucket:
            continue
        if scope == AttributionRule.SCOPE_RECURRING:
            anchor = transaction.recurring_source_id
        elif scope == AttributionRule.SCOPE_PAYEE:
            anchor = payee_id
        elif scope == AttributionRule.SCOPE_ACCOUNT:
            anchor = transaction.account_id
        else:
            anchor = None
        if anchor is not None and anchor in bucket:
            return bucket[anchor]
    return None


def apply_rule(user, transaction, rule):
    """Record the inferred attribution a rule implies. Never sets `user_confirmed`."""
    _require_same_user(user, transaction=transaction)
    row = attribute(
        user, transaction, rule.entity,
        source=TransactionAttribution.SOURCE_USER_RULE,
        actor=TransactionAttribution.ACTOR_RULE,
        confidence=rule.confidence,
        evidence={"rule_id": rule.id, "rule_scope": rule.scope,
                  "matched_on": SCOPE_ANCHOR_FIELD.get(rule.scope, rule.scope)},
        rule=rule,
    )
    AttributionRule.objects.filter(pk=rule.pk).update(
        use_count=rule.use_count + 1, last_used_at=timezone.now(),
    )
    return row
