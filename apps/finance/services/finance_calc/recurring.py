# ==============================================================================
# File: apps/finance/services/finance_calc/recurring.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Deterministic recurrence detection. Proposes; never promotes.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Finding what comes back — and refusing to be sure when it should not be.

The detector groups a person's history by payee and direction, then asks whether the
gaps between occurrences look like a schedule. It is deliberately conservative: three
occurrences minimum, gaps that agree with each other, and a stated confidence that a
person can disagree with.

**It never promotes.** Everything it finds is a `candidate`. Confirmation is a human
act, because the cost of a wrong obligation is asymmetric — a missing bill shows up as
an obvious hole in a forecast, while an invented one silently makes a plan
unachievable and the household cannot see why.

**Amount spread is information, not noise.** A utility bill between $80 and $210 is a
correctly detected VARIABLE obligation. Averaging it to $145 and calling that "expected"
would put a number nobody will ever be charged into the plan they budget from.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

DETECTOR_VERSION = "1.0.0"

ZERO = Decimal("0.00")

#: Below this, a repeat is a coincidence rather than a schedule.
MIN_OCCURRENCES = 3

#: How far a real due date may drift and still be the same schedule. Bills land on
#: weekends, months are different lengths, and processors take a day off.
GAP_TOLERANCE_DAYS = {
    "weekly": 2, "biweekly": 3, "semimonthly": 4, "monthly": 6,
    "quarterly": 12, "semiannual": 20, "annual": 30,
}

#: Amounts within this fraction of the median are "the same amount".
AMOUNT_TOLERANCE = Decimal("0.05")

#: Beyond this RATIO between the largest and smallest occurrence, the payee is not one
#: commitment — it is several things sharing a name. A power bill runs 80 to 210 (2.6x)
#: and is a real variable obligation; a supermarket runs 8 to 310 (39x) and is a place
#: you shop. Ratio separates those far more cleanly than spread-around-the-median does,
#: which is dominated by whichever single month was unusual.
MAX_AMOUNT_RATIO = Decimal("4.0")


def normalise_payee(txn):
    """A stable key for "the same payee". Merchant first; it survives reference codes.

    Descriptions carry transaction-specific noise — dates, store numbers, auth codes —
    so matching on them raw would split one subscription into twelve series.
    """
    raw = (getattr(txn, "merchant_name", "") or txn.description or "").strip().lower()
    kept = []
    for chunk in raw.split():
        # Drop anything that is mostly digits: reference numbers, dates, store ids.
        digits = sum(c.isdigit() for c in chunk)
        if digits and digits >= len(chunk) / 2:
            continue
        kept.append(chunk)
    return " ".join(kept[:4]) or raw[:60]


def _frequency_for(median_gap):
    """The schedule whose expected gap is closest, if any is close enough."""
    from apps.finance.models import RecurringSeries as RS

    best, best_distance = None, None
    for frequency, expected in RS.EXPECTED_GAP_DAYS.items():
        distance = abs(median_gap - expected)
        if distance <= GAP_TOLERANCE_DAYS[frequency] and (
                best_distance is None or distance < best_distance):
            best, best_distance = frequency, distance
    return best


def _kind_for(role, amount, account):
    from apps.finance.models import RecurringSeries as RS
    from apps.finance.models import Transaction as T

    if role == T.ROLE_INCOME:
        return RS.KIND_INCOME
    if role == T.ROLE_DEBT_SERVICE:
        return RS.KIND_DEBT_PAYMENT
    if role == T.ROLE_SAVINGS_ALLOCATION:
        return RS.KIND_SAVINGS
    if role in (T.ROLE_INTERNAL_TRANSFER, T.ROLE_CARD_PAYMENT):
        return RS.KIND_TRANSFER
    return RS.KIND_BILL


def _confidence(occurrences, gaps, gap_spread, amount_spread):
    """How sure the detector is — and it is allowed to be unsure.

    High needs a long, regular history with a steady amount. Everything else is
    medium or low, and a low-confidence candidate is still worth showing: the person
    can recognise their own gym membership far faster than any heuristic can.
    """
    if occurrences >= 6 and gap_spread <= 3 and amount_spread <= AMOUNT_TOLERANCE:
        return "high"
    if occurrences >= 4 and gap_spread <= 6:
        return "medium"
    return "low"


def detect(user, *, since=None, min_occurrences=MIN_OCCURRENCES):
    """Propose recurring series from history. Returns proposals; writes nothing."""
    from apps.finance.models import Transaction as T
    from apps.finance.services.finance_calc import measures as M
    from apps.finance.services.finance_calc import roles as R

    population = M._population(user, start=since)
    rows = R.classify_many(population)

    groups = defaultdict(list)
    for txn, assignment in rows:
        if assignment.role in (T.ROLE_UNCERTAIN, T.ROLE_OPENING_BALANCE,
                               T.ROLE_REFUND, T.ROLE_REVERSAL, T.ROLE_LOAN_PROCEEDS):
            continue
        amount = txn.amount or ZERO
        if amount == ZERO:
            continue
        key = (normalise_payee(txn), "in" if amount > 0 else "out", assignment.role)
        groups[key].append(txn)

    proposals = []
    for (payee, direction, role), items in groups.items():
        if len(items) < min_occurrences or not payee:
            continue
        proposal = _propose(payee, direction, role, items, min_occurrences)
        if proposal:
            proposals.append(proposal)
    proposals.sort(key=lambda p: p["monthly_equivalent"] or ZERO, reverse=True)
    return proposals


def _propose(payee, direction, role, items, min_occurrences):
    from apps.finance.models import RecurringSeries as RS

    items = sorted(items, key=lambda t: t.date)
    dates = [t.date for t in items]
    gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
    if not gaps:
        return None

    median_gap = statistics.median(gaps)
    frequency = _frequency_for(median_gap)
    if frequency is None:
        # Repeats, but on no schedule WLJ recognises. That is a real answer, and the
        # person may still want it in view — irregular but predictable.
        frequency = RS.FREQ_IRREGULAR

    amounts = [abs(t.amount) for t in items]
    median_amount = Decimal(str(statistics.median(amounts))).quantize(Decimal("0.01"))
    lo, hi = min(amounts), max(amounts)
    if lo <= ZERO or (hi / lo) > MAX_AMOUNT_RATIO:
        # Several things sharing a payee, not one commitment.
        return None
    amount_spread = ((hi - lo) / median_amount) if median_amount else Decimal("1")

    gap_spread = (statistics.pstdev(gaps) if len(gaps) > 1 else 0)
    is_variable = amount_spread > AMOUNT_TOLERANCE

    expected_gap = RS.EXPECTED_GAP_DAYS.get(frequency)
    next_due = (dates[-1] + timedelta(days=expected_gap)) if expected_gap else None

    series = RS(
        name=payee.title()[:200], payee=payee,
        kind=_kind_for(role, direction, None), frequency=frequency,
        amount_expected=None if is_variable else median_amount,
        amount_min=lo, amount_max=hi, is_variable=is_variable,
        first_seen_date=dates[0], last_seen_date=dates[-1],
        next_due_date=next_due, occurrence_count=len(items),
        confidence=_confidence(len(items), gaps, gap_spread, amount_spread),
        detector_version=DETECTOR_VERSION,
        review_state=RS.REVIEW_CANDIDATE, source=RS.SOURCE_DETECTED,
        account=items[-1].account,
    )
    monthly = series.monthly_equivalent(use='max' if is_variable else 'expected')
    return {
        "series": series,
        "transaction_ids": [t.pk for t in items],
        "monthly_equivalent": monthly,
        "evidence": {
            "occurrences": len(items),
            "first": str(dates[0]), "last": str(dates[-1]),
            "median_gap_days": median_gap,
            "gap_standard_deviation_days": round(float(gap_spread), 2),
            "amount_median": str(median_amount),
            "amount_min": str(lo), "amount_max": str(hi),
            "amount_spread_fraction": round(float(amount_spread), 3),
            "detector_version": DETECTOR_VERSION,
        },
    }


def persist(user, proposals, *, commit=False):
    """Store proposals as CANDIDATES. Never confirms, never overwrites a decision."""
    from apps.finance.models import RecurringSeries as RS

    created, skipped = 0, 0
    for proposal in proposals:
        series = proposal["series"]
        series.user = user
        series.evidence = proposal["evidence"]
        series.declared_template = _matching_template(user, series.payee)
        existing = RS.objects.filter(
            user=user, payee=series.payee, frequency=series.frequency,
            kind=series.kind, status="active").first()
        if existing is not None:
            # The person has already seen this one. Refresh the OBSERVATIONS but never
            # the decision — re-proposing something they ignored would be nagging, and
            # re-opening something they confirmed would discard their judgement.
            if commit:
                existing.last_seen_date = series.last_seen_date
                existing.occurrence_count = series.occurrence_count
                existing.next_due_date = series.next_due_date
                existing.amount_min = series.amount_min
                existing.amount_max = series.amount_max
                existing.evidence = series.evidence
                existing.save(update_fields=[
                    "last_seen_date", "occurrence_count", "next_due_date",
                    "amount_min", "amount_max", "evidence", "updated_at"])
            skipped += 1
            continue
        if commit:
            series.save()
            from apps.finance.models import Transaction
            Transaction.objects.filter(
                pk__in=proposal["transaction_ids"]).update(recurring_series=series)
        created += 1
    return {"proposed": len(proposals), "created": created, "refreshed": skipped,
            "committed": bool(commit), "detector_version": DETECTOR_VERSION}


def _matching_template(user, payee):
    """A user-written RecurringTransaction describing the same commitment, if any.

    Cross-referenced rather than merged: the template is the user's declaration and the
    series is WLJ's observation, and both are worth keeping. What matters is that the
    household is shown one Netflix rather than two.
    """
    from apps.finance.models import RecurringTransaction

    if not payee:
        return None
    for template in RecurringTransaction.objects.filter(user=user, status="active"):
        name = (getattr(template, "name", "") or "").strip().lower()
        if name and (name in payee or payee in name):
            return template
    return None


def confirmed_obligations(user):
    """The series a person has confirmed as costs. The ONLY input to a forward total."""
    from apps.finance.models import RecurringSeries as RS

    return list(RS.objects.filter(
        user=user, status="active", review_state=RS.REVIEW_CONFIRMED,
        merged_into__isnull=True, kind__in=RS.OBLIGATION_KINDS
    ).select_related("account", "category"))


def confirmed_income(user):
    from apps.finance.models import RecurringSeries as RS

    return list(RS.objects.filter(
        user=user, status="active", review_state=RS.REVIEW_CONFIRMED,
        merged_into__isnull=True, kind=RS.KIND_INCOME).select_related("account"))


def monthly_obligation_total(user):
    """Confirmed monthly commitment, plus what could not be expressed monthly."""
    total, unknown = ZERO, []
    for series in confirmed_obligations(user):
        monthly = series.monthly_equivalent(
            use='max' if series.is_variable else 'expected')
        if monthly is None:
            unknown.append(series)
            continue
        total += monthly
    return total, unknown
