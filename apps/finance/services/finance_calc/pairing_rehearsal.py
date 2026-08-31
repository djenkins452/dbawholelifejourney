# ==============================================================================
# File: apps/finance/services/finance_calc/pairing_rehearsal.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Why are these credits unpaired? Read-only diagnosis. Writes nothing.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Diagnosing the pairing gap before touching the pairing authority.

62 credits on revolving liabilities are held for review because WLJ cannot see their
other leg. They distort nothing — they sit on card accounts, so they touch no cash
measure, and the purchases they settle were already counted from the card side. But a
held row is a question asked of a person, and asking 62 of them when the answer is
deterministic is a poor trade.

This module answers ONE question per row: **is there exactly one counterpart, or not?**
It writes nothing, and it deliberately reports the ambiguous and the unmatched as
loudly as the pairable, because "we could pair 40" is only trustworthy alongside "and
these 22 we could not, for these reasons".
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal

ZERO = Decimal("0.00")

REHEARSAL_VERSION = "1.0.0"

#: Same window the existing pairing authority uses. Deliberately not widened here:
#: this rehearsal asks why the CURRENT rule misses, not what a looser rule would catch.
from apps.finance.services.transfer_detection import PAIRING_WINDOW_DAYS  # noqa: E402

#: Outcomes, in the order a person would want to read them.
OUTCOME_ONE = "exactly_one_counterpart"
OUTCOME_MANY = "several_possible_counterparts"
OUTCOME_NONE = "no_counterpart_visible"
OUTCOME_ALREADY = "already_paired"


def _bucket(amount):
    a = abs(amount or ZERO)
    for edge, label in ((10, "<$10"), (50, "$10–50"), (200, "$50–200"),
                        (1000, "$200–1k"), (5000, "$1k–5k")):
        if a < edge:
            return label
    return ">$5k"


def held_liability_credits(user):
    """The rows this rehearsal is about: credits on a liability, held for review."""
    from apps.finance.models import Transaction

    return list(
        Transaction.objects.filter(
            user=user,
            economic_role=Transaction.ROLE_UNCERTAIN,
            role_reason="unmatched_liability_credit")
        .select_related("account")
        .order_by("date", "id"))


def candidate_counterparts(txn, pool, *, window_days=PAIRING_WINDOW_DAYS):
    """Rows that could be the other leg of `txn`, under the existing rule.

    Deliberately the SAME predicate `pair_transfers` uses — opposite sign, equal
    magnitude, a different account of the same user, inside the window, not already
    paired — so the diagnosis explains the real authority rather than a hypothetical one.
    """
    window_start = txn.date - timedelta(days=window_days)
    window_end = txn.date + timedelta(days=window_days)
    target = -txn.amount
    return [
        other for other in pool
        if other.id != txn.id
        and other.transfer_pair_id is None
        and _counterpart_free(other)
        and other.account_id != txn.account_id
        and other.amount == target
        and (other.amount or ZERO) < ZERO
        and not _is_liability(other)
        and window_start <= other.date <= window_end
    ]


def _is_liability(txn):
    account = getattr(txn, "account", None)
    return bool(account is not None and getattr(account, "is_liability", False))


def _counterpart_free(txn):
    """True when nothing already claims this row as its pair, from either direction."""
    from django.core.exceptions import ObjectDoesNotExist

    if txn.transfer_pair_id:
        return False
    try:
        txn.transfer_counterpart
    except ObjectDoesNotExist:
        return True
    return False


def _pool(user):
    """Every row that could serve as a counterpart. One query, no cap.

    The existing `pair_transfers` reads at most 2,000 rows ordered by date, which on a
    3,795-row history silently excludes the most recent third — the part most likely to
    contain a still-unpaired leg. The rehearsal reads them all so the diagnosis is not
    itself truncated.
    """
    from apps.finance.models import Transaction

    return list(
        Transaction.objects.filter(user=user)
        .exclude(is_opening_balance=True)
        .select_related("account")
        .order_by("date", "id"))


def run(user, *, window_days=PAIRING_WINDOW_DAYS):
    """Report what improved pairing would and would not resolve. Persists nothing."""
    from apps.finance.models import Transaction

    held = held_liability_credits(user)
    pool = _pool(user)

    outcomes = Counter()
    amounts = defaultdict(lambda: ZERO)
    samples = defaultdict(list)
    ambiguity_sizes = Counter()
    counterpart_roles = Counter()
    by_account_type = defaultdict(lambda: {"count": 0, "amount": ZERO})

    claimed = set()          # nothing may be proposed as two different rows' pair
    pairable = []

    for txn in held:
        if not _counterpart_free(txn):
            outcomes[OUTCOME_ALREADY] += 1
            continue

        candidates = [c for c in candidate_counterparts(txn, pool, window_days=window_days)
                      if c.id not in claimed]
        if len(candidates) == 1:
            outcome = OUTCOME_ONE
            counterpart = candidates[0]
            claimed.add(counterpart.id)
            claimed.add(txn.id)
            pairable.append((txn, counterpart))
            counterpart_roles[counterpart.economic_role or "unclassified"] += 1
        elif candidates:
            outcome = OUTCOME_MANY
            ambiguity_sizes[len(candidates)] += 1
        else:
            outcome = OUTCOME_NONE

        outcomes[outcome] += 1
        amounts[outcome] += abs(txn.amount or ZERO)
        bucket = by_account_type[
            getattr(getattr(txn, "account", None), "account_type", "") or "?"]
        bucket["count"] += 1
        bucket["amount"] += abs(txn.amount or ZERO)

        if len(samples[outcome]) < 4:
            samples[outcome].append({
                "month": f"{txn.date.year:04d}-{txn.date.month:02d}",
                "magnitude": _bucket(txn.amount),
                "account_type": getattr(getattr(txn, "account", None),
                                        "account_type", ""),
                "provider_primary": (txn.provider_category_primary or "")[:32],
                "provider_detailed": (txn.provider_category_detailed or "")[:48],
                "candidates": len(candidates),
                "counterpart_account_type": (
                    getattr(getattr(candidates[0], "account", None), "account_type", "")
                    if len(candidates) == 1 else None),
                "counterpart_primary": (
                    (candidates[0].provider_category_primary or "")[:32]
                    if len(candidates) == 1 else None),
            })

    return {
        "rehearsal_version": REHEARSAL_VERSION,
        "window_days": window_days,
        "held_liability_credits": len(held),
        "held_total": str(sum((abs(t.amount or ZERO) for t in held), ZERO)),
        "pool_size": len(pool),
        "outcomes": {k: {"count": v, "amount": str(amounts[k])}
                     for k, v in sorted(outcomes.items())},
        "ambiguity_sizes": dict(sorted(ambiguity_sizes.items())),
        "counterpart_roles": dict(counterpart_roles),
        "by_account_type": {k: {"count": v["count"], "amount": str(v["amount"])}
                            for k, v in by_account_type.items()},
        "samples": {k: v for k, v in samples.items()},
        "would_pair": len(pairable),
        "would_pair_amount": str(sum((abs(t.amount or ZERO) for t, _ in pairable), ZERO)),
        "note": ("Report only. Nothing here is written. A row with several possible "
                 "counterparts stays held: guessing which one is exactly the error "
                 "this queue exists to prevent."),
    }


def existing_authority_limits(user):
    """Facts about the CURRENT pairing pass, so the gap is attributed correctly.

    Delegated to `transfer_detection.pairing_coverage`: counting unpaired rows means
    querying `transfer_pair__isnull`, and a contract test forbids any surface outside
    the population authority from writing that predicate. The pairing authority is
    allowed to describe itself; this module is not allowed to describe it for it.
    """
    from apps.finance.services import transfer_detection as TD

    return TD.pairing_coverage(user)
