"""
Treatment Intelligence — canonical treatment state (Sprint 10).

A COMPOSITION layer over Medication Intelligence and the other health domains. It
GROUPS and READS canonical truth (Intakes, the MedicationEvent ledger, the cached
medication-observation bundle, and live domain metrics) into treatment-plan state
for Beth and the Treatment dashboard.

It NEVER:
  - owns or recomputes medication state, history, or adherence,
  - duplicates provider/pharmacy/prescription/condition truth,
  - infers treatment effectiveness or makes a clinical claim.

Deterministic only — no predictions, no recommendations, no causation.
"""

import logging
from datetime import timedelta

logger = logging.getLogger(__name__)


def _metric_value(user, metric_key):
    """Read the CURRENT value of a goal's tracked metric from its canonical domain
    owner (no storage, no recompute). Returns a display string or None. Defensive:
    any domain hiccup yields None ("not recorded") rather than an error."""
    from apps.core.utils import get_user_today
    try:
        if metric_key == "weight":
            from apps.health.models import WeightEntry
            w = WeightEntry.objects.filter(user=user).order_by("-recorded_at").first()
            return f"{w.value} {w.unit}" if w else None
        if metric_key == "a1c":
            from apps.medical.models import LabResult
            lab = (
                LabResult.objects.filter(user=user, raw_test_name__icontains="a1c")
                .order_by("-collected_at").first()
            )
            if not lab:
                return None
            val = lab.value_numeric if lab.value_numeric is not None else lab.value_text
            return f"{val}{(' ' + lab.unit) if lab.unit else ''}".strip() if val is not None else None
        if metric_key == "glucose_avg":
            from django.db.models import Avg
            from apps.health.models import GlucoseEntry
            a = GlucoseEntry.objects.filter(
                user=user,
                recorded_at__date__gte=get_user_today(user) - timedelta(days=30),
            ).aggregate(a=Avg("value"))["a"]
            return f"{round(a)} avg (30d)" if a else None
        if metric_key == "fasting_glucose":
            from apps.health.models import GlucoseEntry
            g = (
                GlucoseEntry.objects.filter(user=user, context="fasting")
                .order_by("-recorded_at").first()
                or GlucoseEntry.objects.filter(user=user).order_by("-recorded_at").first()
            )
            return f"{g.value} {g.unit}" if g else None
        if metric_key == "blood_pressure":
            from apps.health.models import BloodPressureEntry
            bp = BloodPressureEntry.objects.filter(user=user).order_by("-recorded_at").first()
            if not bp:
                return None
            sys = getattr(bp, "systolic", None)
            dia = getattr(bp, "diastolic", None)
            return f"{sys}/{dia}" if sys and dia else None
    except Exception:
        logger.debug("metric read failed for %s", metric_key, exc_info=True)
    return None


def _plan_state(user, plan, narrations):
    """Compose one treatment plan into deterministic state."""
    from apps.health.models import Intake, MedicationEvent

    intakes = list(plan.intakes.all())
    medications = [
        i.name for i in intakes if i.intake_type == Intake.INTAKE_TYPE_MEDICATION
    ]
    supplements = [
        i.name for i in intakes if i.intake_type == Intake.INTAKE_TYPE_SUPPLEMENT
    ]

    goals = []
    watching = []
    for g in plan.goals.all():
        current = _metric_value(user, g.metric_key) if g.metric_key else None
        goals.append({
            "name": g.name,
            "metric": g.get_metric_key_display() if g.metric_key else "",
            "direction": g.direction,
            "target": g.target_value,
            "current_value": current,  # READ from canonical domain
        })
        if g.metric_key:
            watching.append({
                "metric": g.get_metric_key_display(),
                "current_value": current if current is not None else "Not recorded",
            })

    # Recent changes — READ the ledger filtered to this plan's intakes (no recompute).
    recent_changes = []
    if intakes:
        from apps.core.utils import get_user_today
        cutoff = get_user_today(user) - timedelta(days=90)
        events = (
            MedicationEvent.objects.filter(
                user=user, intake__in=intakes, effective_date__gte=cutoff,
            ).exclude(event_type="tracking_began")
            .select_related("intake").order_by("-effective_date")[:10]
        )
        recent_changes = [
            {
                "date": e.effective_date.isoformat(),
                "medicine": e.intake.name,
                "change": e.get_event_type_display(),
            }
            for e in events
        ]

    # Medication observations relevant to this plan's medications (composed; from
    # the cached bundle — never recomputed). Observations are user-scoped; we
    # surface those whose evidence touches one of this plan's intakes, plus any
    # physician-discussion ones.
    plan_obs = [
        n for n in narrations
        if n["physician_discussion"] or _touches_plan(n, set(medications + supplements))
    ]

    return {
        "id": plan.id,
        "name": plan.name,
        "condition": plan.condition.name if plan.condition_id else (plan.health_focus or ""),
        "goal_narrative": plan.goal_narrative,
        "provider": plan.primary_provider.name if plan.primary_provider_id else "",
        "started_date": plan.started_date.isoformat() if plan.started_date else None,
        "status": plan.plan_status,
        "medications": medications,
        "supplements": supplements,
        "goals": goals,
        "watching": watching,
        "recent_changes": recent_changes,
        "observations": plan_obs,
        "summary": _plan_summary(plan.name, medications, supplements, goals),
    }


def _touches_plan(narration, plan_intake_names):
    """Deterministic: does a narration's title mention one of the plan's intakes?"""
    title = (narration.get("title", "") + " " + narration.get("summary", "")).lower()
    return any(name.lower() in title for name in plan_intake_names if name)


def _plan_summary(name, medications, supplements, goals):
    parts = []
    if medications:
        parts.append(f"{len(medications)} medication{'s' if len(medications) != 1 else ''}")
    if supplements:
        parts.append(f"{len(supplements)} supplement{'s' if len(supplements) != 1 else ''}")
    if goals:
        parts.append(f"{len(goals)} goal{'s' if len(goals) != 1 else ''}")
    body = ", ".join(parts) if parts else "no linked therapies or goals yet"
    return f"{name}: {body}."


def build_treatment_state(user):
    """Canonical treatment state (Sprint 10E). Beth consumes this — never raw models.

    Composes active treatment plans with their related medications/supplements,
    goals, tracked outcomes (live from canonical domains), recent changes (from the
    ledger), and approved medication observations (from the cached bundle).
    """
    from apps.health.models import TreatmentPlan

    # Approved medication narrations — composed, cached (Sprint 9A). Never recomputed.
    narrations = []
    try:
        from apps.health.observations.bundle import get_observation_bundle
        narrations = get_observation_bundle(user)["narrations"]
    except Exception:
        logger.debug("treatment state: observation bundle read failed", exc_info=True)

    plans = (
        TreatmentPlan.objects.filter(user=user, plan_status=TreatmentPlan.STATUS_ACTIVE)
        .select_related("condition", "primary_provider")
        .prefetch_related("intakes", "goals")
    )
    active_plans = []
    for plan in plans:
        try:
            active_plans.append(_plan_state(user, plan, narrations))
        except Exception:
            logger.warning("treatment state: plan %s failed", plan.id, exc_info=True)

    return {
        "active_plans": active_plans,
        "plan_count": len(active_plans),
        "has_plans": bool(active_plans),
    }


# ── Treatment Intelligence telemetry (Sprint 10H) ─────────────────────────────

TI_OPS_KEY = "wlj:ops:treatment_intelligence"
TI_OPS_TTL = 60 * 60 * 25


def compute_treatment_intelligence_ops():
    """Aggregate Treatment Intelligence ops metrics → snapshot (Ops Wall
    convention). Background-intended; light aggregate queries."""
    from django.core.cache import cache
    from django.utils import timezone
    from django.db.models import Count, Q
    from apps.health.models import TreatmentPlan

    active = TreatmentPlan.objects.filter(plan_status=TreatmentPlan.STATUS_ACTIVE)
    total = active.count()
    no_goals = active.annotate(n=Count("goals")).filter(n=0).count()
    no_intakes = active.annotate(n=Count("intakes")).filter(n=0).count()
    no_metrics = active.annotate(
        metric_goals=Count("goals", filter=~Q(goals__metric_key=""))
    ).filter(metric_goals=0).count()

    snapshot = {
        "computed_at": timezone.now().isoformat(),
        "active_plans": total,
        "plans_without_goals": no_goals,
        "plans_without_interventions": no_intakes,
        "plans_without_linked_metrics": no_metrics,
    }
    cache.set(TI_OPS_KEY, snapshot, TI_OPS_TTL)
    return snapshot


def get_treatment_intelligence_ops():
    """Read-only Ops Wall snapshot; None until populated (no request-path compute)."""
    from django.core.cache import cache
    return cache.get(TI_OPS_KEY)
