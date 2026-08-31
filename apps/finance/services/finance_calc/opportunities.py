# ==============================================================================
# File: apps/finance/services/finance_calc/opportunities.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Deterministic savings opportunities. Evidence or nothing.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""What could this household stop paying, and what would it be worth?

Two questions drive the design:

* *"What is my largest cost that I can control easily?"* — ranking.
* *"How can I save $100 a month?"* — assembly, from compatible candidates.

Both are answered from CONFIRMED recurring series carrying a user-recorded LEVER. That
is a deliberately narrow foundation: an opportunity built on a detected-but-unconfirmed
series, or on an inferred controllability, is a recommendation built on WLJ's own
guesswork presented to a person as a fact about their life.

**Nothing is proposed without traceable evidence.** Every opportunity records the
transaction ids it was derived from and the arithmetic that produced its figure.

**Ease is not the same as size.** A $400 mortgage saving that requires refinancing is
not more actionable than a $40 subscription somebody can cancel this afternoon. Ranking
weighs the money against effort and disruption, and reports each separately so a person
can disagree with the weighting rather than only with the answer.
"""
from __future__ import annotations

from decimal import Decimal

ENGINE_VERSION = "1.0.0"

ZERO = Decimal("0.00")

#: Which lever implies which action. A lever the person recorded is what makes an
#: opportunity legitimate; this only chooses how to describe it.
LEVER_TO_KIND = {
    "cancellable": "cancel",
    "negotiable": "negotiate",
    "reducible": "downgrade",
    "deferrable": "reduce_frequency",
    "avoidable": "cancel",
}

#: How much of the cost a lever plausibly removes. Deliberately conservative: an
#: over-stated saving is discovered only when the money fails to appear.
LEVER_SAVING_FRACTION = {
    "cancellable": Decimal("1.00"),   # stopping it removes all of it
    "avoidable": Decimal("1.00"),
    "reducible": Decimal("0.30"),     # a cheaper tier, not a free one
    "negotiable": Decimal("0.15"),    # a discount, not a waiver
    "deferrable": Decimal("0.25"),
}

EFFORT_BY_KIND = {
    "cancel": "low", "downgrade": "low", "negotiate": "medium",
    "reduce_frequency": "medium", "reduce_category": "high",
    "move_to_entity": "low", "eliminate_duplicate": "low",
    "correct_classification": "low",
}
DISRUPTION_BY_KIND = {
    "cancel": "medium", "downgrade": "medium", "negotiate": "low",
    "reduce_frequency": "medium", "reduce_category": "high",
    "move_to_entity": "low", "eliminate_duplicate": "low",
    "correct_classification": "low",
}

_EASE = {"low": Decimal("1.0"), "medium": Decimal("0.6"), "high": Decimal("0.3")}
_CONFIDENCE_WEIGHT = {"high": Decimal("1.0"), "medium": Decimal("0.7"),
                      "low": Decimal("0.4")}


def ease_score(opportunity):
    """Money, discounted by how hard and how unpleasant it is. Reported, not hidden."""
    weight = (_EASE[opportunity.effort] * _EASE[opportunity.disruption]
              * _CONFIDENCE_WEIGHT[opportunity.confidence])
    return (opportunity.projected_monthly_savings * weight).quantize(Decimal("0.01"))


def generate(user):
    """Build the current opportunity set. Returns unsaved objects plus evidence."""
    from apps.finance.models import SavingsOpportunity as SO
    from apps.finance.services.finance_calc import controllability as C
    from apps.finance.services.finance_calc import recurring as REC

    classifications = C.active_classifications(user)
    proposals = []

    for series in REC.confirmed_obligations(user):
        monthly = series.monthly_equivalent(
            use='expected' if not series.is_variable else 'min')
        if monthly is None or monthly <= ZERO:
            # No monthly figure means no claim can be made about monthly savings.
            continue

        verdict = _verdict_for_series(series, classifications)
        if verdict is None or not verdict.levers:
            continue

        transaction_ids = list(
            series.transactions.values_list("pk", flat=True)[:24])

        for lever in verdict.levers:
            kind = LEVER_TO_KIND.get(lever)
            if kind is None:
                continue
            fraction = LEVER_SAVING_FRACTION[lever]
            saving = (monthly * fraction).quantize(Decimal("0.01"))
            if saving <= ZERO:
                continue
            proposals.append({
                "opportunity": SO(
                    user=user, kind=kind,
                    title=f"{_verb(kind)} {series.name}",
                    rationale=_rationale(kind, series, monthly, fraction, verdict),
                    series=series, payee=series.payee,
                    projected_monthly_savings=saving,
                    confidence=_confidence(series, verdict),
                    effort=EFFORT_BY_KIND[kind],
                    disruption=DISRUPTION_BY_KIND[kind],
                    engine_version=ENGINE_VERSION),
                "evidence": {
                    "series_id": series.pk,
                    "series_name": series.name,
                    "frequency": series.frequency,
                    "monthly_equivalent": str(monthly),
                    "lever": lever,
                    "saving_fraction": str(fraction),
                    "calculation": f"{monthly} x {fraction} = {saving}",
                    "controllability_decided_by": verdict.scope,
                    "controllability_source": verdict.source,
                    "occurrences": series.occurrence_count,
                    "transaction_ids": transaction_ids,
                    "engine_version": ENGINE_VERSION,
                },
            })

    proposals.sort(key=lambda p: ease_score(p["opportunity"]), reverse=True)
    return proposals


def _verdict_for_series(series, classifications):
    """The controllability decision governing a whole series.

    Resolved from the series' most recent occurrence, so the same precedence rules
    apply as anywhere else rather than a second, series-only ruleset.
    """
    from apps.finance.services.finance_calc import controllability as C

    latest = series.transactions.order_by("-date").first()
    if latest is None:
        return None
    return C.resolve(latest, classifications)


def _verb(kind):
    return {"cancel": "Cancel", "downgrade": "Downgrade",
            "negotiate": "Renegotiate", "reduce_frequency": "Use less often",
            }.get(kind, "Review")


def _confidence(series, verdict):
    """Confident only when BOTH the pattern and the person's decision are solid."""
    if verdict.source != "user":
        return "low"
    if series.confidence == "high" and not series.is_variable:
        return "high"
    if series.confidence in ("high", "medium"):
        return "medium"
    return "low"


def _rationale(kind, series, monthly, fraction, verdict):
    basis = (f"{series.name} recurs {series.get_frequency_display().lower()} and works "
             f"out at about {monthly} a month across {series.occurrence_count} "
             f"observed payments.")
    if fraction == Decimal("1.00"):
        effect = "Stopping it removes the whole amount."
    else:
        effect = (f"WLJ assumes {int(fraction * 100)}% of it could realistically go — "
                  f"a cheaper deal, not a free one.")
    who = ("You classified this yourself." if verdict.source == "user"
           else "This rests on a classification WLJ inferred, so treat it as a "
                "suggestion rather than a finding.")
    return f"{basis} {effect} {who}"


def persist(user, proposals, *, commit=False):
    """Store proposals. An existing decision is never reopened."""
    from apps.finance.models import SavingsOpportunity as SO

    created, kept = 0, 0
    for proposal in proposals:
        opportunity = proposal["opportunity"]
        opportunity.evidence = proposal["evidence"]
        existing = SO.objects.filter(
            user=user, kind=opportunity.kind, series=opportunity.series,
            status="active").first()
        if existing is not None:
            if commit and existing.decision == SO.STATUS_PROPOSED:
                # Undecided: refresh the figure. Decided: leave the person alone.
                existing.projected_monthly_savings = \
                    opportunity.projected_monthly_savings
                existing.confidence = opportunity.confidence
                existing.evidence = opportunity.evidence
                existing.save(update_fields=["projected_monthly_savings", "confidence",
                                             "evidence", "updated_at"])
            kept += 1
            continue
        if commit:
            opportunity.save()
        created += 1
    return {"proposed": len(proposals), "created": created, "existing": kept,
            "committed": bool(commit), "engine_version": ENGINE_VERSION}


def ranked(user, *, limit=None):
    """Open opportunities, easiest-largest first."""
    from apps.finance.models import SavingsOpportunity as SO

    open_ones = [o for o in SO.objects.filter(user=user, status="active")
                 .select_related("series") if o.is_open]
    open_ones.sort(key=ease_score, reverse=True)
    return open_ones[:limit] if limit else open_ones


def largest_controllable_cost(user):
    """The single answer to "what is my largest cost that I can control easily?"."""
    candidates = ranked(user)
    if not candidates:
        return {
            "answer": None,
            "reason": "no_controllable_cost_identified",
            "missing": _what_is_missing(user),
        }
    best = candidates[0]
    return {
        "answer": {
            "title": best.title,
            "monthly": str(best.projected_monthly_savings),
            "annual": str(best.projected_monthly_savings * 12),
            "kind": best.kind, "effort": best.effort,
            "disruption": best.disruption, "confidence": best.confidence,
            "rationale": best.rationale, "evidence": best.evidence,
        },
        "runners_up": [
            {"title": o.title, "monthly": str(o.projected_monthly_savings),
             "effort": o.effort, "confidence": o.confidence}
            for o in candidates[1:4]],
        "engine_version": ENGINE_VERSION,
    }


def find_amount(user, target):
    """Assemble compatible opportunities reaching `target` a month, or say how short.

    Compatible means one per series: proposing that a person both cancel AND renegotiate
    the same subscription would count the same money twice.
    """
    target = Decimal(str(target))
    candidates = [o for o in ranked(user) if o.reduces_spending]

    chosen, used_series, total = [], set(), ZERO
    for opportunity in candidates:
        key = opportunity.series_id or f"payee:{opportunity.payee}"
        if key in used_series:
            continue
        used_series.add(key)
        chosen.append(opportunity)
        total += opportunity.projected_monthly_savings
        if total >= target:
            break

    reached = total >= target
    return {
        "target": str(target),
        "found": str(total),
        "reached": reached,
        "shortfall": str(target - total) if not reached else "0.00",
        "plan": [{
            "title": o.title, "monthly": str(o.projected_monthly_savings),
            "kind": o.kind, "effort": o.effort, "disruption": o.disruption,
            "confidence": o.confidence, "evidence": o.evidence,
        } for o in chosen],
        "missing": [] if reached else _what_is_missing(user),
        "note": (None if reached else
                 "This is what WLJ can support with evidence today. The gap is not a "
                 "statement that no further saving exists — it is a statement that "
                 "WLJ cannot yet point to one."),
        "engine_version": ENGINE_VERSION,
    }


def _what_is_missing(user):
    """Precisely what the person could supply to get a better answer."""
    from apps.finance.models import RecurringSeries as RS
    from apps.finance.models import SpendingClassification as SC

    missing = []
    candidates = RS.objects.filter(user=user, status="active",
                                   review_state=RS.REVIEW_CANDIDATE).count()
    confirmed = RS.objects.filter(user=user, status="active",
                                  review_state=RS.REVIEW_CONFIRMED).count()
    classified = SC.objects.filter(user=user, status="active").count()

    if not confirmed and candidates:
        missing.append({
            "what": "confirm_recurring_series",
            "detail": f"{candidates} recurring series have been detected but none "
                      f"confirmed. WLJ will not build a savings plan on its own guesses.",
        })
    elif not confirmed:
        missing.append({
            "what": "recurring_detection",
            "detail": "No recurring series are known yet. Run detection, then confirm "
                      "the ones that are real.",
        })
    if not classified:
        missing.append({
            "what": "controllability_classification",
            "detail": "Nothing has been marked cancellable, negotiable or reducible. "
                      "WLJ will not decide on its own what you can live without.",
        })
    return missing
