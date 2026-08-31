# ==============================================================================
# File: apps/finance/services/finance_calc/dry_run.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Report-only P1 classification rehearsal. Writes NOTHING, ever.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""What the backfill WOULD do, without doing any of it.

Every function here is read-only by construction: it classifies in memory and returns a
dictionary. There is no `save()`, no `update()`, no `create()` in this module, and the
classification it produces is thrown away when the report is rendered.

**Redaction is a hard requirement, not a courtesy.** The report is written to be pasted
into a conversation, so it may never contain a description, merchant, account
identifier, address, token or provider payload. Amounts appear only as AGGREGATES; the
per-class samples carry a role, a reason, a confidence and an order-of-magnitude bucket
— never a figure tied to an identifiable transaction.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal

from apps.finance.services.finance_calc import measures as M
from apps.finance.services.finance_calc import roles as R

ZERO = Decimal("0.00")

#: Coarse buckets so a sample can convey scale without revealing an amount.
def _bucket(amount):
    a = abs(amount or ZERO)
    for edge, label in ((10, "<$10"), (50, "$10–50"), (200, "$50–200"),
                        (1000, "$200–1k"), (5000, "$1k–5k")):
        if a < edge:
            return label
    return ">$5k"


def _month(d):
    return f"{d.year:04d}-{d.month:02d}"


def run(user, *, sample_per_class=3):
    """The full report. Persists nothing."""
    from apps.finance.models import Transaction

    population = list(M._population(user))
    rows = R.classify_many(population)

    report = {
        "population": _population_summary(population, rows),
        "by_role": _by_role(rows),
        "by_source": Counter(a.source for _, a in rows),
        "by_confidence": Counter(a.confidence for _, a in rows),
        "uncertain_reasons": _uncertain_reasons(rows),
        "monthly": _monthly(user, rows),
        "totals": _totals(user, rows),
        "reconciliation": None,
        "gates": None,
        "protected_user_rows": _protected(rows),
        "debt_composition": _debt_composition(rows),
        "high_value": _high_value(rows),
        "samples": _samples(rows, sample_per_class),
        "classifier_version": R.CLASSIFIER_VERSION,
        "measures_version": M.MEASURES_VERSION,
    }

    measures = M.all_measures(user, transactions=population)
    report["reconciliation"] = M.reconcile(measures)
    report["gates"] = _gates(rows, measures, population)
    report["measures"] = {k: v.as_dict() for k, v in measures.items()}
    return report


def _population_summary(population, rows):
    dates = [t.date for t in population if t.date]
    return {
        "transactions": len(population),
        "coverage_start": str(min(dates)) if dates else None,
        "coverage_end": str(max(dates)) if dates else None,
        "already_classified": sum(1 for t in population if t.economic_role),
    }


def _by_role(rows):
    counts = Counter(a.role for _, a in rows)
    amounts = defaultdict(lambda: ZERO)
    for txn, a in rows:
        amounts[a.role] += abs(txn.amount or ZERO)
    return {role: {"count": counts[role], "amount": str(amounts[role])}
            for role in sorted(counts)}


def _uncertain_reasons(rows):
    from apps.finance.models import Transaction as T
    counts = Counter(a.reason for _, a in rows if a.role == T.ROLE_UNCERTAIN)
    amounts = defaultdict(lambda: ZERO)
    for txn, a in rows:
        if a.role == T.ROLE_UNCERTAIN:
            amounts[a.reason] += abs(txn.amount or ZERO)
    return {r: {"count": counts[r], "amount": str(amounts[r])} for r in sorted(counts)}


def _monthly(user, rows):
    """Proposed measure totals per month. The 'current' column is the live authority."""
    by_month = defaultdict(list)
    for txn, a in rows:
        by_month[_month(txn.date)].append((txn, a))

    out = {}
    for month in sorted(by_month):
        month_rows = by_month[month]
        proposed = {
            "gross_purchases": M.gross_purchases(user, rows=month_rows).value,
            "net_spending": M.net_spending(user, rows=month_rows).value,
            "cash_outflow": M.cash_outflow(user, rows=month_rows).value,
            "cash_inflow": M.cash_inflow(user, rows=month_rows).value,
            "income": M.income(user, rows=month_rows).value,
            "debt_service": M.debt_service(user, rows=month_rows).value,
            "transfers": M.transfers_and_allocations(user, rows=month_rows).value,
        }
        out[month] = {
            "current_financial_activity": str(_current_activity(user, month_rows)),
            "proposed": {k: str(v) for k, v in proposed.items()},
        }
    return out


def _current_activity(user, month_rows):
    """What the LIVE authority counts for these rows, for a like-for-like comparison."""
    from apps.finance.services.attribution_population import financial_activity

    pks = {t.pk for t, _ in month_rows}
    total = ZERO
    for txn in financial_activity(user):
        if txn.pk in pks and (txn.amount or ZERO) < 0:
            total += abs(txn.amount)
    return total


def _totals(user, rows):
    return {
        "current_financial_activity_outflow": str(_current_activity(user, rows)),
    }


def _debt_composition(rows):
    """Where debt service comes from — the number that decides double counting.

    A paid loan can appear twice: cash leaving the funding account and the credit
    landing on the liability. The measure counts the cash leg, plus liability credits
    with no visible counterpart (otherwise a loan paid from an unconnected account
    would vanish). That second rule is only safe if the counterpart detection is
    reliable, so the split is reported rather than assumed.
    """
    from apps.finance.models import Transaction as T
    from apps.finance.services.finance_calc import roles as _R

    out = {"cash_leg": ZERO, "cash_leg_n": 0,
           "liability_credit_unpaired": ZERO, "liability_credit_unpaired_n": 0,
           "liability_credit_mirrored": ZERO, "liability_credit_mirrored_n": 0,
           "unpaired_by_account_type": {}}
    for txn, a in rows:
        if a.role != T.ROLE_DEBT_SERVICE:
            continue
        amount = txn.amount or ZERO
        account_type = getattr(getattr(txn, "account", None), "account_type", "") or "?"
        if amount < 0:
            out["cash_leg"] += abs(amount)
            out["cash_leg_n"] += 1
        elif _R.counterpart(txn) is None:
            out["liability_credit_unpaired"] += amount
            out["liability_credit_unpaired_n"] += 1
            bucket = out["unpaired_by_account_type"].setdefault(
                account_type, {"count": 0, "amount": ZERO})
            bucket["count"] += 1
            bucket["amount"] += amount
        else:
            out["liability_credit_mirrored"] += amount
            out["liability_credit_mirrored_n"] += 1
    out["unpaired_by_account_type"] = {
        k: {"count": v["count"], "amount": str(v["amount"])}
        for k, v in out["unpaired_by_account_type"].items()}
    return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in out.items()}


def _high_value(rows, top=8):
    """The largest single rows per role, redacted. One misclassified big row can move
    a measure more than a thousand small ones, so they are reviewed by hand."""
    from collections import defaultdict as _dd
    buckets = _dd(list)
    for txn, a in rows:
        buckets[a.role].append((abs(txn.amount or ZERO), txn, a))
    out = {}
    for role, items in buckets.items():
        items.sort(key=lambda x: x[0], reverse=True)
        out[role] = [{
            "amount": str(amount), "month": _month(txn.date), "reason": a.reason,
            "confidence": a.confidence,
            "account_type": getattr(getattr(txn, "account", None), "account_type", ""),
            "provider_primary": (txn.provider_category_primary or "")[:32],
            "provider_detailed": (txn.provider_category_detailed or "")[:48],
            "paired": bool(txn.transfer_pair_id),
        } for amount, txn, a in items[:top]]
    return out


def _protected(rows):
    from apps.finance.models import Transaction as T
    return sum(1 for _, a in rows if a.source == T.ROLE_SOURCE_USER)


def _gates(rows, measures, population):
    """Warning gates. They inform the decision; they never make it."""
    from apps.finance.models import Transaction as T

    total = len(rows) or 1
    non_spending = sum(1 for _, a in rows if a.role in {
        T.ROLE_INTERNAL_TRANSFER, T.ROLE_CARD_PAYMENT, T.ROLE_SAVINGS_ALLOCATION,
        T.ROLE_INVESTMENT_CONTRIBUTION, T.ROLE_UNCERTAIN, T.ROLE_CASH_WITHDRAWAL,
        T.ROLE_DEBT_SERVICE})
    uncertain = sum(1 for _, a in rows if a.role == T.ROLE_UNCERTAIN)
    uncertain_amount = sum((abs(t.amount or ZERO) for t, a in rows
                            if a.role == T.ROLE_UNCERTAIN), ZERO)
    outflow = measures["cash_outflow"].value or Decimal("1")

    return {
        "reclassified_as_non_spending_pct": round(non_spending * 100.0 / total, 2),
        "reclassified_gate_5pct_exceeded": (non_spending * 100.0 / total) > 5,
        "uncertain_pct_of_rows": round(uncertain * 100.0 / total, 2),
        "uncertain_gate_10pct_exceeded": (uncertain * 100.0 / total) > 10,
        "uncertain_pct_of_outflow": round(float(uncertain_amount * 100 / outflow), 2),
        "uncertain_gate_15pct_outflow_exceeded":
            float(uncertain_amount * 100 / outflow) > 15,
        "note": ("Gates are WARNINGS, never approval. Every backfill requires Danny's "
                 "explicit authorisation regardless of how small the change is."),
    }


def _samples(rows, per_class):
    """Redacted exemplars — enough to judge a class, never enough to identify a row."""
    out = defaultdict(list)
    for txn, a in rows:
        if len(out[a.role]) >= per_class:
            continue
        out[a.role].append({
            "reason": a.reason,
            "confidence": a.confidence,
            "source": a.source,
            "direction": "in" if (txn.amount or ZERO) > 0 else "out",
            "magnitude": _bucket(txn.amount),
            "month": _month(txn.date),
            "account_type": getattr(getattr(txn, "account", None), "account_type", ""),
            "provider_primary": (txn.provider_category_primary or "")[:32],
        })
    return dict(out)
