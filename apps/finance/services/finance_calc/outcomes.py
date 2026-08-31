# ==============================================================================
# File: apps/finance/services/finance_calc/outcomes.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Did the saving actually happen? Observed, never assumed.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""The difference between "you could save $47" and "you have saved $47".

Most systems never close this loop. They suggest, the user accepts, and the suggestion
quietly becomes a fact in every subsequent total — so the household is told it is saving
money it is still spending.

WLJ measures. For a series-backed opportunity the saving is visible: the series either
stopped, shrank, or did not. The comparison is between the observed monthly cost BEFORE
the start date and the observed monthly cost after it.

**Three honest outcomes besides success:**

* `too_early` — accepted last week; the window has not elapsed. Not a failure.
* `unmeasurable` — no single series to watch, so no claim is made either way.
* `not_achieved` — the money is still going out. Said plainly, because the whole point
  of measuring is to notice.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

ZERO = Decimal("0.00")

OUTCOMES_VERSION = "1.0.0"

#: Within this fraction of the projection, call it achieved. A cancelled subscription
#: rarely returns exactly the projected figure — a part-month refund moves it.
ACHIEVED_TOLERANCE = Decimal("0.15")
#: Below this share of the projection, nothing meaningful happened.
PARTIAL_FLOOR = Decimal("0.25")


def measure(opportunity, *, today=None, commit=False):
    """Compare what was projected against what the transactions actually show."""
    from apps.core.utils import get_user_today
    from apps.finance.models import SavingsOpportunity as SO
    from django.utils import timezone

    user = opportunity.user
    today = today or get_user_today(user)

    if not opportunity.is_being_tracked:
        return _result(opportunity, SO.OUTCOME_PENDING, None,
                       "Not being tracked yet — accept it and give it a start date.",
                       commit=commit)

    if not opportunity.is_measurable:
        return _result(
            opportunity, SO.OUTCOME_UNMEASURABLE, None,
            "There is no single recurring series behind this, so WLJ has nothing "
            "specific to watch. It will not guess whether it worked.",
            commit=commit)

    elapsed = (today - opportunity.started_on).days
    if elapsed < opportunity.observation_days:
        return _result(
            opportunity, SO.OUTCOME_TOO_EARLY, None,
            f"{elapsed} of {opportunity.observation_days} days observed. Too early to "
            f"say, which is not the same as not working.",
            commit=commit, evidence={"days_elapsed": elapsed})

    before, after = _monthly_cost_either_side(opportunity, today)
    if before is None:
        return _result(
            opportunity, SO.OUTCOME_UNMEASURABLE, None,
            "No spending on this series before the start date, so there is no "
            "baseline to compare against.",
            commit=commit)

    saved = before - after
    projected = opportunity.projected_monthly_savings or ZERO
    evidence = {
        "monthly_before": str(before), "monthly_after": str(after),
        "observed_saving": str(saved), "projected_saving": str(projected),
        "days_observed": elapsed, "version": OUTCOMES_VERSION,
    }

    if projected <= ZERO:
        outcome = SO.OUTCOME_UNMEASURABLE
        note = "No projected saving to compare against."
    elif saved <= ZERO:
        outcome = SO.OUTCOME_NOT_ACHIEVED
        note = (f"The money is still going out — about {after} a month, against "
                f"{before} before. Nothing has been saved here.")
    elif saved >= projected * (Decimal("1") - ACHIEVED_TOLERANCE):
        outcome = SO.OUTCOME_ACHIEVED
        note = f"About {saved} a month is genuinely no longer being spent."
    elif saved >= projected * PARTIAL_FLOOR:
        outcome = SO.OUTCOME_PARTIAL
        note = (f"About {saved} a month less, against {projected} projected. Real, "
                f"but short of the plan.")
    else:
        outcome = SO.OUTCOME_NOT_ACHIEVED
        note = (f"Only {saved} a month less against {projected} projected — not enough "
                f"to call this done.")

    return _result(opportunity, outcome, saved, note, commit=commit, evidence=evidence)


def _monthly_cost_either_side(opportunity, today):
    """Observed monthly cost of the series before and after the start date."""
    from apps.finance.models import Transaction

    series = opportunity.series
    start = opportunity.started_on
    window = timedelta(days=opportunity.observation_days)

    rows = list(Transaction.objects.filter(user=opportunity.user, recurring_series=series)
                .values_list("date", "amount"))
    if not rows:
        return None, ZERO

    before_rows = [amount for date_, amount in rows
                   if start - window <= date_ < start]
    after_rows = [amount for date_, amount in rows if start <= date_ <= today]

    if not before_rows:
        return None, ZERO

    months = max(Decimal("1"), Decimal(opportunity.observation_days) / Decimal("30.4375"))
    before = (sum((abs(a) for a in before_rows), ZERO) / months).quantize(Decimal("0.01"))
    observed_months = max(
        Decimal("1"), Decimal((today - start).days) / Decimal("30.4375"))
    after = (sum((abs(a) for a in after_rows), ZERO)
             / observed_months).quantize(Decimal("0.01"))
    return before, after


def _result(opportunity, outcome, saved, note, *, commit=False, evidence=None):
    from django.utils import timezone

    payload = dict(evidence or {})
    payload["note"] = note
    if commit:
        opportunity.outcome = outcome
        opportunity.realized_monthly_savings = saved
        opportunity.outcome_checked_at = timezone.now()
        opportunity.outcome_evidence = payload
        opportunity.save(update_fields=[
            "outcome", "realized_monthly_savings", "outcome_checked_at",
            "outcome_evidence", "updated_at"])
    return {
        "opportunity": opportunity.pk, "outcome": outcome,
        "realized": str(saved) if saved is not None else None,
        "projected": str(opportunity.projected_monthly_savings),
        "variance": str(opportunity.variance) if saved is not None else None,
        "note": note, "evidence": payload,
    }


def measure_all(user, *, today=None, commit=False):
    """Measure every tracked opportunity. Reports nothing when nothing is tracked."""
    from apps.finance.models import SavingsOpportunity as SO

    tracked = [o for o in SO.objects.filter(user=user, status="active")
               .select_related("series") if o.is_being_tracked]
    results = [measure(o, today=today, commit=commit) for o in tracked]
    return {
        "measured": len(results),
        "achieved": sum(1 for r in results if r["outcome"] == SO.OUTCOME_ACHIEVED),
        "not_achieved": sum(1 for r in results
                            if r["outcome"] == SO.OUTCOME_NOT_ACHIEVED),
        "too_early": sum(1 for r in results if r["outcome"] == SO.OUTCOME_TOO_EARLY),
        "results": results,
        "version": OUTCOMES_VERSION,
    }


def underperforming(user):
    """Accepted plans that are not producing what they promised.

    The question "which plan is not working?" only has an answer because projected and
    realized were never allowed to become the same field.
    """
    from apps.finance.models import SavingsOpportunity as SO

    rows = SO.objects.filter(
        user=user, status="active",
        outcome__in=[SO.OUTCOME_NOT_ACHIEVED, SO.OUTCOME_PARTIAL])
    return [{
        "title": o.title,
        "projected_monthly": str(o.projected_monthly_savings),
        "realized_monthly": (str(o.realized_monthly_savings)
                             if o.realized_monthly_savings is not None else None),
        "variance": str(o.variance) if o.variance is not None else None,
        "outcome": o.outcome,
        "note": (o.outcome_evidence or {}).get("note"),
    } for o in rows]
