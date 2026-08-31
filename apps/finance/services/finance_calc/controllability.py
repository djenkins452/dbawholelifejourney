# ==============================================================================
# File: apps/finance/services/finance_calc/controllability.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Resolves which classification governs a transaction, and why.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Which of a person's classifications applies to THIS cost — and can it say why?

A household accumulates overlapping opinions: "groceries are essential", "this shop is
discretionary", "that one purchase was a one-off". They will conflict, and a savings
engine that resolves conflicts arbitrarily produces advice nobody can audit.

The rule is specificity first, authority second:

    transaction (100) > recurring series (80) > payee (60) > rule (40) > category (20)

and within one scope, a decision the USER made beats one WLJ inferred. `resolve` returns
the winning classification together with the losers it beat, so any number built on it
can show its reasoning rather than asserting it.

Unclassified is a real answer. It is not "uncontrollable", and it is emphatically not
"controllable" — a savings opportunity invented from an absence of data is exactly the
failure this module exists to prevent.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

ZERO = Decimal("0.00")

CONTROLLABILITY_VERSION = "1.0.0"


@dataclass
class Verdict:
    """What governs one transaction, what it means, and what it beat."""
    classification: Optional[object] = None
    necessity: str = "unknown"
    variability: str = "unknown"
    levers: list = field(default_factory=list)
    scope: str = ""
    source: str = ""
    beat: list = field(default_factory=list)

    @property
    def is_known(self):
        return self.classification is not None

    @property
    def is_controllable(self):
        return bool(self.levers)

    def as_dict(self):
        return {
            "known": self.is_known, "controllable": self.is_controllable,
            "necessity": self.necessity, "variability": self.variability,
            "levers": list(self.levers), "decided_by": self.scope,
            "source": self.source, "also_matched": list(self.beat),
            "version": CONTROLLABILITY_VERSION,
        }


def active_classifications(user):
    """Every live classification for a user, ready to be indexed. One query."""
    from apps.finance.models import SpendingClassification

    return list(SpendingClassification.objects.filter(user=user, status="active")
                .select_related("category", "transaction"))


def _matches(classification, txn, payee):
    from apps.finance.models import SpendingClassification as SC

    scope = classification.scope
    if scope == SC.SCOPE_TRANSACTION:
        return classification.transaction_id == txn.pk
    if scope == SC.SCOPE_CATEGORY:
        return (classification.category_id is not None
                and classification.category_id == txn.category_id)
    if scope == SC.SCOPE_PAYEE:
        return bool(classification.payee) and classification.payee.lower() == payee
    if scope == SC.SCOPE_RULE:
        fragment = (classification.match_contains or "").strip().lower()
        return bool(fragment) and fragment in (txn.description or "").lower()
    if scope == SC.SCOPE_SERIES:
        series_id = getattr(txn, "recurring_series_id", None)
        return (series_id is not None
                and getattr(classification, "series_id", None) == series_id)
    return False


def payee_of(txn):
    """The payee WLJ will match on. Merchant first — it is the stable identity."""
    return ((getattr(txn, "merchant_name", "") or txn.description or "")
            .strip().lower())


def resolve(txn, classifications):
    """The governing classification for one transaction, plus what it outranked."""
    payee = payee_of(txn)
    matched = [c for c in classifications if _matches(c, txn, payee)]
    if not matched:
        return Verdict()

    matched.sort(key=lambda c: (c.precedence, c.authority, c.pk), reverse=True)
    winner, losers = matched[0], matched[1:]
    return Verdict(
        classification=winner,
        necessity=winner.necessity,
        variability=winner.variability,
        levers=winner.clean_levers(),
        scope=winner.scope,
        source=winner.source,
        beat=[f"{c.scope}:{c.pk}" for c in losers],
    )


def resolve_many(user, transactions, classifications=None):
    """`{transaction_pk: Verdict}` — the classifications are fetched ONCE.

    Resolving per transaction with its own query is the N+1 that would make a spending
    page unusable on a real history; the whole set is small enough to hold in memory.
    """
    classifications = (active_classifications(user) if classifications is None
                       else classifications)
    return {txn.pk: resolve(txn, classifications) for txn in transactions}


def coverage(user, rows):
    """How much of the spending has an opinion attached, and how much does not.

    Reported alongside every controllable figure. "Controllable spending: $412" means
    something different when 90% of purchases are classified than when 9% are, and the
    number alone cannot tell them apart.
    """
    from apps.finance.models import Transaction as T

    classifications = active_classifications(user)
    purchases = [(txn, a) for txn, a in rows if a.role == T.ROLE_PURCHASE]
    verdicts = resolve_many(user, [t for t, _ in purchases], classifications)

    classified_amount, unclassified_amount = ZERO, ZERO
    classified_n = 0
    for txn, _ in purchases:
        verdict = verdicts[txn.pk]
        amount = abs(txn.amount or ZERO)
        if verdict.is_known:
            classified_amount += amount
            classified_n += 1
        else:
            unclassified_amount += amount

    total = classified_amount + unclassified_amount
    return {
        "purchases": len(purchases),
        "classified": classified_n,
        "unclassified": len(purchases) - classified_n,
        "classified_amount": classified_amount,
        "unclassified_amount": unclassified_amount,
        "pct_of_spend_classified": (
            float(classified_amount * 100 / total) if total else 0.0),
        "verdicts": verdicts,
    }
