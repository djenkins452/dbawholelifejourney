# ==============================================================================
# File: apps/finance/services/opportunity_lifecycle.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: F3 — opportunity lifecycle and deterministic outcome verification.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""From "WLJ noticed" to "it actually changed" — without WLJ touching anything external.

**WLJ executes nothing here.** It cannot move money, change a payment method, cancel a
subscription, or reach an external account. It records what the user decided and then
watches ordinary transaction truth for evidence that the change happened.

Two deliberate reuses instead of new authorities:
  * detection stays in the canonical `Insight` (F1);
  * "ask me about this later" is the EXISTING `ConversationFollowUp` — WLJ owns the
    commitment, the model authors the wording fresh at fire time. No second scheduler.

Verification is deterministic and cannot be fooled by history: at acceptance we snapshot
the pattern's existing `Transaction.fingerprint` values, so only a genuinely NEW
transaction — one paid by the correct entity — can count as evidence.
"""
from __future__ import annotations

from django.db import transaction as db_transaction
from django.utils import timezone

from apps.finance.models import (
    FinanceOpportunity,
    FinancialEntity,
    Transaction,
    TransactionAttribution,
)
from apps.finance.services.finance_entities import _require_same_user, open_assignment_map

FOLLOW_UP_DAYS = 30


def _pattern_transactions(user, opportunity):
    """Every transaction belonging to this opportunity's pattern. ONE query."""
    qs = Transaction.objects.filter(user=user)
    if opportunity.recurring_id:
        return qs.filter(recurring_source_id=opportunity.recurring_id)
    if opportunity.payee_key:
        return qs.filter(payee__iexact=opportunity.payee_key)
    return qs.none()


@db_transaction.atomic
def sync_from_findings(user, findings):
    """Create or refresh an opportunity per detected finding. Idempotent.

    A finding the user has CLOSED (rejected / verified / not relevant) is never reopened
    by re-detection — WLJ does not nag past a decision.
    """
    seen = set()
    for finding in findings:
        key = finding["dedupe_key"]
        seen.add(key)
        recurring_id = finding["key"][1] if finding["is_recurring"] else None
        payee_key = "" if finding["is_recurring"] else str(finding["key"][1])
        opportunity, created = FinanceOpportunity.objects.get_or_create(
            user=user, dedupe_key=key,
            defaults={
                "attributed_entity": finding["bearer"],
                "paid_by_entity": finding["payer"],
                "recurring_id": recurring_id,
                "payee_key": payee_key,
                "label": finding["label"][:200],
                "occurrences": finding["occurrences"],
                "annual_estimate": finding["annual_estimate"],
            },
        )
        if not created and opportunity.is_open:
            opportunity.occurrences = finding["occurrences"]
            opportunity.annual_estimate = finding["annual_estimate"]
            opportunity.label = finding["label"][:200] or opportunity.label
            opportunity.save(update_fields=["occurrences", "annual_estimate", "label",
                                            "updated_at"])
    return seen


def mark_presented(opportunity):
    if opportunity.state == FinanceOpportunity.STATE_DETECTED:
        return _transition(opportunity, FinanceOpportunity.STATE_PRESENTED)
    return opportunity


@db_transaction.atomic
def accept(user, opportunity, *, schedule_follow_up=True):
    """The user intends to make the change themselves. WLJ starts watching.

    Snapshots the pattern's current fingerprints so nothing that already existed can later
    be mistaken for proof, and schedules the EXISTING follow-up so the CoS returns to it.
    """
    _require_same_user(user, opportunity=opportunity)
    fingerprints = list(
        _pattern_transactions(user, opportunity)
        .exclude(fingerprint="")
        .values_list("fingerprint", flat=True)[:500]
    )
    last_seen = (_pattern_transactions(user, opportunity)
                 .order_by("-date").values_list("date", flat=True).first())
    opportunity.baseline = {
        "accepted_on": timezone.now().date().isoformat(),
        "fingerprints": fingerprints,
        "last_seen_before": last_seen.isoformat() if last_seen else None,
        "paid_by_entity_id": opportunity.paid_by_entity_id,
    }
    opportunity.accepted_at = timezone.now()
    _transition(opportunity, FinanceOpportunity.STATE_ACCEPTED,
                extra_fields=["baseline", "accepted_at"])

    if schedule_follow_up and opportunity.follow_up_id is None:
        opportunity.follow_up = _schedule_follow_up(user, opportunity)
        opportunity.save(update_fields=["follow_up", "updated_at"])
    return opportunity


def _schedule_follow_up(user, opportunity):
    """Reuse the existing durable follow-through record. No new scheduler, no stored prose."""
    try:
        from apps.ai.models import ConversationFollowUp
    except Exception:          # pragma: no cover - ai app always present in WLJ
        return None
    due = timezone.now() + timezone.timedelta(days=FOLLOW_UP_DAYS)
    return ConversationFollowUp.objects.create(
        user=user,
        due_at=due,
        topic=f"whether {opportunity.label or 'this expense'} is now paid by "
              f"{opportunity.attributed_entity.name}"[:280],
        subject_ref=f"finance.financeopportunity:{opportunity.pk}",
        origin=ConversationFollowUp.ORIGIN_ASSISTANT,
        metadata={"source": "finance_opportunity", "kind": opportunity.kind},
    )


def reject(user, opportunity, *, reason=""):
    _require_same_user(user, opportunity=opportunity)
    opportunity.notes = reason or opportunity.notes
    return _transition(opportunity, FinanceOpportunity.STATE_REJECTED,
                       extra_fields=["notes"])


def defer(user, opportunity, *, until):
    _require_same_user(user, opportunity=opportunity)
    opportunity.deferred_until = until
    return _transition(opportunity, FinanceOpportunity.STATE_DEFERRED,
                       extra_fields=["deferred_until"])


def mark_in_progress(user, opportunity):
    _require_same_user(user, opportunity=opportunity)
    return _transition(opportunity, FinanceOpportunity.STATE_IN_PROGRESS)


def verify_manually(user, opportunity, *, note=""):
    """The user says they did it. Recorded as THEIR word, never dressed up as evidence."""
    _require_same_user(user, opportunity=opportunity)
    opportunity.verification_evidence = {
        "method": "user_stated",
        "recorded_at": timezone.now().isoformat(),
        "note": note[:200],
    }
    opportunity.verified_at = timezone.now()
    return _transition(opportunity, FinanceOpportunity.STATE_VERIFIED_MANUAL,
                       extra_fields=["verification_evidence", "verified_at"])


def _transition(opportunity, state, *, extra_fields=()):
    opportunity.state = state
    opportunity.state_changed_at = timezone.now()
    opportunity.save(update_fields=["state", "state_changed_at", "updated_at",
                                    *extra_fields])
    return opportunity


def verify_from_truth(user, opportunity):
    """Did later transaction truth show the change? Deterministic; never inferred.

    Evidence = a transaction in this pattern that (a) is NOT in the accepted-time baseline
    and (b) was paid from an account owned by the entity that should bear the cost.
    """
    if opportunity.state not in FinanceOpportunity.WATCHING_STATES:
        return None
    baseline = opportunity.baseline or {}
    known = set(baseline.get("fingerprints") or [])
    accepted_on = baseline.get("accepted_on")
    if not accepted_on:
        return None

    entity_by_account = open_assignment_map(user)
    candidates = (_pattern_transactions(user, opportunity)
                  .filter(date__gte=accepted_on, status="active")
                  .order_by("date"))

    for txn in candidates:
        if txn.fingerprint and txn.fingerprint in known:
            continue                                   # already existed at acceptance
        payer = entity_by_account.get(txn.account_id)
        if payer is None or payer.id != opportunity.attributed_entity_id:
            continue                                   # still on the wrong account
        opportunity.verification_evidence = {
            "method": "transaction_truth",
            "transaction_id": txn.id,
            "date": txn.date.isoformat(),
            "account_id": txn.account_id,
            "paid_by_entity_id": payer.id,
            "checked_at": timezone.now().isoformat(),
        }
        opportunity.verified_at = timezone.now()
        return _transition(opportunity, FinanceOpportunity.STATE_VERIFIED_AUTO,
                           extra_fields=["verification_evidence", "verified_at"])
    return None


def retire_resolved(user, live_keys):
    """A pattern that no longer holds is no longer an opportunity.

    Only touches opportunities WLJ itself opened and the user has not decided on — an
    accepted or rejected one belongs to the user until they say otherwise.
    """
    stale = FinanceOpportunity.objects.filter(
        user=user,
        state__in=(FinanceOpportunity.STATE_DETECTED, FinanceOpportunity.STATE_PRESENTED),
    ).exclude(dedupe_key__in=live_keys)
    return stale.update(state=FinanceOpportunity.STATE_NOT_RELEVANT,
                        state_changed_at=timezone.now())
