"""
Deterministic observation rules (Sprint 5C medication, 5D cross-domain).

Every rule is deterministic and evidence-first: it returns Observation objects
with explicit evidence references, or nothing. Cross-domain rules state CHRONOLOGY
and ASSOCIATION only — never causation, never advice. Each cross-domain source is
defensive so a schema difference never breaks the engine.
"""

from datetime import timedelta

from apps.health.observations.core import Observation, ObsType
from apps.health.treatment_timeline import _classify_dose_change


def _evt_ref(e):
    return {
        "type": "MedicationEvent", "id": e.id,
        "summary": f"{e.get_event_type_display()} on {e.effective_date}",
    }


# ── Medication-only observations (5C) ─────────────────────────────────────────

def medication_observations(user):
    from apps.core.utils import get_user_today
    from apps.health.medicine_utils import calculate_medicine_adherence_rate
    from apps.health.models import Intake, MedicationEvent

    today = get_user_today(user)
    obs = []

    # Adherence improving / declining — 7d vs 30d (needs real data both windows).
    a7 = calculate_medicine_adherence_rate(user, days=7)
    a30 = calculate_medicine_adherence_rate(user, days=30)
    if a7 is not None and a30 is not None:
        gap = a7 - a30
        ev = (
            {"type": "adherence", "window_days": 7, "value": a7},
            {"type": "adherence", "window_days": 30, "value": a30},
        )
        if gap >= 10:
            obs.append(Observation(
                ObsType.ADHERENCE_IMPROVING,
                f"Adherence is higher over the last 7 days ({a7}%) than the last 30 ({a30}%).",
                confidence=min(1.0, 0.5 + gap / 100), domains=("medication",),
                window_days=30, evidence=ev,
            ))
        elif gap <= -10:
            obs.append(Observation(
                ObsType.ADHERENCE_DECLINING,
                f"Adherence is lower over the last 7 days ({a7}%) than the last 30 ({a30}%).",
                confidence=min(1.0, 0.5 + abs(gap) / 100), domains=("medication",),
                window_days=30, evidence=ev,
            ))

    # Recent treatment change (14d).
    recent = list(
        MedicationEvent.objects.filter(
            user=user, effective_date__gte=today - timedelta(days=14),
            event_type__in=["dose_changed", "provider_changed", "pharmacy_changed",
                            "discontinued", "paused", "resumed", "frequency_changed"],
        ).select_related("intake")[:10]
    )
    if recent:
        obs.append(Observation(
            ObsType.TREATMENT_RECENTLY_CHANGED,
            f"Your treatment changed {len(recent)} time(s) in the last 14 days.",
            confidence=0.8, domains=("medication",), window_days=14,
            evidence=tuple(_evt_ref(e) for e in recent),
        ))

    # Multiple dose reductions / increases (90d).
    dose_events = list(
        MedicationEvent.objects.filter(
            user=user, event_type="dose_changed",
            effective_date__gte=today - timedelta(days=90),
        ).select_related("intake")
    )
    decs = [e for e in dose_events if _classify_dose_change(e) == "dose_decreased"]
    incs = [e for e in dose_events if _classify_dose_change(e) == "dose_increased"]
    if len(decs) >= 2:
        obs.append(Observation(
            ObsType.MULTIPLE_DOSE_REDUCTIONS,
            f"{len(decs)} dose reductions in the last 90 days.",
            confidence=0.85, domains=("medication",), window_days=90,
            evidence=tuple(_evt_ref(e) for e in decs),
        ))
    if len(incs) >= 2:
        obs.append(Observation(
            ObsType.MULTIPLE_DOSE_INCREASES,
            f"{len(incs)} dose increases in the last 90 days.",
            confidence=0.85, domains=("medication",), window_days=90,
            evidence=tuple(_evt_ref(e) for e in incs),
        ))

    # Stability — last change long ago, with active meds.
    active_count = Intake.objects.filter(
        user=user, intake_status=Intake.STATUS_ACTIVE,
    ).count()
    latest = (
        MedicationEvent.objects.filter(user=user)
        .exclude(event_type="tracking_began")
        .order_by("-effective_date").first()
    )
    if active_count and latest:
        days_since = (today - latest.effective_date).days
        if days_since >= 180:
            obs.append(Observation(
                ObsType.LONG_TERM_STABILITY,
                f"No treatment changes in {days_since} days.",
                confidence=0.7, domains=("medication",), window_days=days_since,
                evidence=(_evt_ref(latest),),
            ))
        elif days_since >= 90:
            obs.append(Observation(
                ObsType.MEDICATION_STABLE,
                f"No treatment changes in {days_since} days.",
                confidence=0.65, domains=("medication",), window_days=days_since,
                evidence=(_evt_ref(latest),),
            ))

    # Recent provider change (30d).
    prov = list(
        MedicationEvent.objects.filter(
            user=user, event_type="provider_changed",
            effective_date__gte=today - timedelta(days=30),
        ).select_related("intake")
    )
    if prov:
        obs.append(Observation(
            ObsType.RECENT_PROVIDER_CHANGE,
            "A prescriber change was recorded in the last 30 days.",
            confidence=0.75, domains=("medication",), window_days=30,
            evidence=tuple(_evt_ref(e) for e in prov),
        ))

    # Recent refill pattern (30d, ≥2).
    refills = list(
        MedicationEvent.objects.filter(
            user=user, event_type="refill",
            effective_date__gte=today - timedelta(days=30),
        ).select_related("intake")
    )
    if len(refills) >= 2:
        obs.append(Observation(
            ObsType.RECENT_REFILL_PATTERN,
            f"{len(refills)} refills logged in the last 30 days.",
            confidence=0.6, domains=("medication",), window_days=30,
            evidence=tuple(_evt_ref(e) for e in refills),
        ))

    return obs


# ── Cross-domain observations (5D) — chronology + association only ─────────────

def cross_domain_observations(user):
    import logging
    from apps.core.utils import get_user_today
    from apps.health.models import MedicationEvent

    logger = logging.getLogger(__name__)
    today = get_user_today(user)
    obs = []

    anchor = (
        MedicationEvent.objects.filter(user=user, event_type="dose_changed")
        .order_by("-effective_date").first()
    )

    def _safe(fn, *args):
        try:
            fn(*args)
        except Exception:
            logger.debug("Cross-domain observation rule failed", exc_info=True)

    if anchor is not None:
        _safe(_weight_after_change, user, anchor, obs)
        _safe(_glucose_after_change, user, anchor, obs)
    _safe(_exercise_during_treatment, user, today, obs)

    return obs


def _weight_after_change(user, anchor, obs):
    from apps.health.models import WeightEntry
    ad = anchor.effective_date
    before = (
        WeightEntry.objects.filter(
            user=user, recorded_at__date__lt=ad,
            recorded_at__date__gte=ad - timedelta(days=30),
        ).order_by("-recorded_at").first()
    )
    after = (
        WeightEntry.objects.filter(
            user=user, recorded_at__date__gt=ad,
            recorded_at__date__lte=ad + timedelta(days=30),
        ).order_by("-recorded_at").first()
    )
    if before and after and float(after.value) < float(before.value):
        diff = round(float(before.value) - float(after.value), 1)
        obs.append(Observation(
            ObsType.WEIGHT_AFTER_TREATMENT_CHANGE,
            f"Weight was {diff} {after.unit} lower after a treatment change on {ad}.",
            detail="Chronological association only — not a cause.",
            confidence=0.6, domains=("medication", "weight"), window_days=60,
            evidence=(
                _evt_ref(anchor),
                {"type": "WeightEntry", "id": before.id, "value": float(before.value)},
                {"type": "WeightEntry", "id": after.id, "value": float(after.value)},
            ),
        ))


def _glucose_after_change(user, anchor, obs):
    from django.db.models import Avg
    from apps.health.models import GlucoseEntry
    ad = anchor.effective_date
    before = GlucoseEntry.objects.filter(
        user=user, recorded_at__date__lt=ad,
        recorded_at__date__gte=ad - timedelta(days=30),
    ).aggregate(a=Avg("value"))["a"]
    after = GlucoseEntry.objects.filter(
        user=user, recorded_at__date__gt=ad,
        recorded_at__date__lte=ad + timedelta(days=30),
    ).aggregate(a=Avg("value"))["a"]
    if before and after and after < before:
        obs.append(Observation(
            ObsType.GLUCOSE_AFTER_TREATMENT_CHANGE,
            f"Average glucose was lower after a treatment change "
            f"({round(before)} → {round(after)}) around {ad}.",
            detail="Chronological association only — not a cause.",
            confidence=0.6, domains=("medication", "glucose"), window_days=60,
            evidence=(
                _evt_ref(anchor),
                {"type": "glucose_avg", "window_days": 30, "value": round(before, 1), "phase": "before"},
                {"type": "glucose_avg", "window_days": 30, "value": round(after, 1), "phase": "after"},
            ),
        ))


def _exercise_during_treatment(user, today, obs):
    from apps.health.models import WorkoutSession
    recent = WorkoutSession.objects.filter(
        user=user, date__gte=today - timedelta(days=90),
    ).count()
    prior = WorkoutSession.objects.filter(
        user=user, date__gte=today - timedelta(days=180),
        date__lt=today - timedelta(days=90),
    ).count()
    if recent >= 4 and recent > prior:
        obs.append(Observation(
            ObsType.EXERCISE_DURING_TREATMENT,
            f"More workouts in the last 90 days ({recent}) than the prior 90 ({prior}).",
            detail="Chronological association only — not a cause.",
            confidence=0.55, domains=("medication", "workout"), window_days=180,
            evidence=(
                {"type": "workout_count", "window_days": 90, "value": recent, "phase": "recent"},
                {"type": "workout_count", "window_days": 90, "value": prior, "phase": "prior"},
            ),
        ))
