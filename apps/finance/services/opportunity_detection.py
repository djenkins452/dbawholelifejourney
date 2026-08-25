# ==============================================================================
# File: apps/finance/services/opportunity_detection.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: F1 — deterministic detection of entity payment mismatches.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Deterministic detection: expenses attributed to one entity but paid by another.

WLJ COMPUTES; the model INTERPRETS. This module emits FACTS — which transactions, how
much, how often, since when — into the canonical `Insight` record. It never says "you
should move this", never ranks something as "your biggest problem", and never assigns a
severity band: `severity` stays `info` and the magnitude travels as evidence, so the
Chief of Staff does the prioritising (Constitution I.4).

Nothing here branches on an entity NAME. The rule is structural: an active attribution
whose attributed entity differs from the entity that actually paid.

Shape:
  * one `Insight` per PATTERN (entity-pair + payee/recurring series), not per transaction —
    "four Beacon charges on your personal card" is one finding, not four;
  * the scan is a single indexed query over `TransactionAttribution` plus one bounded
    lookup — no joins per row, no per-transaction model call, ever;
  * idempotent: a stable `dedupe_key` means re-running updates the existing insight
    instead of duplicating it.
"""
from __future__ import annotations

import hashlib
from collections import defaultdict
from decimal import Decimal

from django.db.models import F
from django.utils import timezone

from apps.finance.models import FinancialEntity, TransactionAttribution

#: A mismatch is only interesting when the payer is a personal/household entity and the
#: cost belongs to a business/other entity — structural, never name-based.
BEARER_TYPES = (FinancialEntity.TYPE_BUSINESS, FinancialEntity.TYPE_OTHER)
PAYER_TYPES = (FinancialEntity.TYPE_PERSONAL, FinancialEntity.TYPE_HOUSEHOLD)

INSIGHT_MODULE = "finance"
INSIGHT_TYPE = "entity_expense_mismatch"

#: Confidence follows the strength of the attribution behind the finding, nothing else.
CONFIDENCE_CONFIRMED = 1.0
CONFIDENCE_INFERRED = 0.6


def _pattern_key(row):
    """Group by what the user would ACT on: a payee or a recurring series, per entity pair."""
    if row.transaction.recurring_source_id:
        return ("recurring", row.transaction.recurring_source_id,
                row.attributed_entity_id, row.paid_by_entity_id)
    payee = (row.transaction.payee or row.transaction.description or "").strip().casefold()
    return ("payee", payee, row.attributed_entity_id, row.paid_by_entity_id)


def _dedupe_key(user, key):
    raw = f"{user.id}:{INSIGHT_TYPE}:{key[0]}:{key[1]}:{key[2]}:{key[3]}"
    return hashlib.sha256(raw.encode()).hexdigest()[:48]


def _annualized(rows):
    """Deterministic annual estimate. Recurring uses its own cadence; otherwise the
    observed span. A calculation WLJ owns (I.3) — not a judgement about it."""
    total = sum(abs(r.transaction.amount) for r in rows)
    dates = sorted(r.transaction.date for r in rows)
    if len(dates) < 2:
        return float(total)
    span_days = max((dates[-1] - dates[0]).days, 1)
    per_day = Decimal(total) / Decimal(span_days)
    return float((per_day * Decimal(365)).quantize(Decimal("0.01")))


def find_mismatches(user):
    """Every active attribution where the bearer and the payer differ. ONE query.

    The population contract is re-asserted here rather than assumed. An attribution is
    written only for an attributable transaction, but a transaction can CHANGE after the
    fact — it can be soft-deleted, re-categorised as a transfer, or paired with its
    counterpart later. A finding must reflect truth NOW, so the same exclusions are
    applied at read time. They cost nothing: same query, same indexes.
    """
    from django.db.models import Q

    return (TransactionAttribution.objects
            .filter(user=user,
                    attribution_status=TransactionAttribution.STATUS_ACTIVE,
                    attributed_entity__entity_type__in=BEARER_TYPES,
                    paid_by_entity__entity_type__in=PAYER_TYPES,
                    transaction__status="active",
                    transaction__is_opening_balance=False,
                    transaction__plaid_pending=False)
            .exclude(Q(transaction__transfer_pair__isnull=False)
                     | Q(transaction__category__category_type="transfer"))
            .exclude(attributed_entity=F("paid_by_entity"))
            .select_related("transaction", "attributed_entity", "paid_by_entity"))


def build_findings(user):
    """Group mismatches into actionable patterns. Facts only; no verdict, no ranking."""
    grouped = defaultdict(list)
    for row in find_mismatches(user):
        grouped[_pattern_key(row)].append(row)

    findings = []
    for key, rows in grouped.items():
        rows.sort(key=lambda r: r.transaction.date)
        confirmed = [r for r in rows if r.user_confirmed]
        bearer = rows[0].attributed_entity
        payer = rows[0].paid_by_entity
        findings.append({
            "key": key,
            "dedupe_key": _dedupe_key(user, key),
            "bearer": bearer,
            "payer": payer,
            "rows": rows,
            "transaction_ids": [r.transaction_id for r in rows],
            "occurrences": len(rows),
            "confirmed_occurrences": len(confirmed),
            "total_amount": float(sum(abs(r.transaction.amount) for r in rows)),
            "annual_estimate": _annualized(rows),
            "first_seen": rows[0].transaction.date,
            "last_seen": rows[-1].transaction.date,
            "is_recurring": key[0] == "recurring",
            "label": (rows[0].transaction.payee or rows[0].transaction.description
                      or "").strip(),
            # A finding is CONFIRMED when a human confirmed the attribution behind it;
            # otherwise it is a review candidate. The distinction is never blurred.
            "confirmed": bool(confirmed),
            "confidence": CONFIDENCE_CONFIRMED if confirmed else CONFIDENCE_INFERRED,
        })
    findings.sort(key=lambda f: f["annual_estimate"], reverse=True)
    return findings


def _compose(finding):
    """Facts, in plain language. No recommendation — the model decides what to say."""
    bearer = finding["bearer"].name
    payer = finding["payer"].name
    label = finding["label"] or "an expense"
    occurrences = finding["occurrences"]
    title = f"{label}: attributed to {bearer}, paid by {payer}"
    plural = "charge" if occurrences == 1 else "charges"
    message = (
        f"{occurrences} {plural} attributed to {bearer} were paid from {payer} "
        f"(${finding['total_amount']:,.2f} total, "
        f"{finding['first_seen'].isoformat()} to {finding['last_seen'].isoformat()}). "
        f"Estimated annual value at this rate: ${finding['annual_estimate']:,.2f}."
    )
    explain = (
        f"WLJ compared each transaction's attributed entity with the entity that owned the "
        f"paying account on the transaction date. "
        f"{finding['confirmed_occurrences']} of {occurrences} attributions were confirmed "
        f"by you; the rest were inferred. Transfers, card payments, opening balances, "
        f"pending rows, and suspected internal transfers are excluded from this comparison."
    )
    return title[:180], message, explain


def record_findings(user, findings=None):
    """Write findings to the canonical `Insight` record. Idempotent by `dedupe_key`.

    Reuses the platform insight lifecycle — status, notification, engagement, and the
    executive briefing all already consume it. Finance does not get its own
    recommendation authority.
    """
    from apps.core.ai_insights.models import Insight

    findings = build_findings(user) if findings is None else findings
    seen_keys = set()
    created, updated = 0, 0

    for finding in findings:
        title, message, explain = _compose(finding)
        evidence = {
            "rule_name": INSIGHT_TYPE,
            "attributed_entity_id": finding["bearer"].id,
            "paid_by_entity_id": finding["payer"].id,
            "transaction_ids": finding["transaction_ids"][:25],
            "occurrences": finding["occurrences"],
            "confirmed_occurrences": finding["confirmed_occurrences"],
            "total_amount": finding["total_amount"],
            "annual_estimate": finding["annual_estimate"],
            "first_seen": finding["first_seen"].isoformat(),
            "last_seen": finding["last_seen"].isoformat(),
            "is_recurring": finding["is_recurring"],
            "confirmed": finding["confirmed"],
            "computed_at": timezone.now().isoformat(),
        }
        obj, was_created = Insight.objects.update_or_create(
            user=user, dedupe_key=finding["dedupe_key"],
            defaults={
                "module": INSIGHT_MODULE,
                "insight_type": INSIGHT_TYPE,
                # Deliberately flat: materiality travels as `annual_estimate` evidence.
                # A "warning" band would be WLJ rendering judgement (Constitution I.4).
                "severity": "info",
                "title": title,
                "message": message,
                "confidence_score": finding["confidence"],
                "explain_why": explain,
                "evidence": evidence,
            },
        )
        seen_keys.add(finding["dedupe_key"])
        created += int(was_created)
        updated += int(not was_created)

    # A pattern that no longer holds is no longer true — retire it rather than leave a
    # stale finding standing. Dismissed insights are left alone (the user has spoken).
    stale = (Insight.objects
             .filter(user=user, module=INSIGHT_MODULE, insight_type=INSIGHT_TYPE)
             .exclude(dedupe_key__in=seen_keys)
             .exclude(status="dismissed"))
    resolved = stale.update(status="dismissed")
    return {"created": created, "updated": updated, "resolved": resolved,
            "findings": len(findings)}
