"""
Phase 4 CoS — Intervention Effectiveness Tracker.

Tracks if interventions resolved drift. Calibrates escalation speed.

Public API:
    - evaluate_intervention_effectiveness(user) -> None
    - get_intervention_effectiveness(user) -> InterventionEffectivenessProfile
    - get_escalation_speed_modifier(user) -> float
"""

import logging
from datetime import timedelta

from django.db.models import Avg, Count, Q
from django.utils import timezone

from apps.core.ai_feedback.models import InterventionEffectivenessProfile

logger = logging.getLogger(__name__)


def evaluate_intervention_effectiveness(user):
    """
    Evaluate effectiveness of recent interventions.

    For each responded intervention in the last 30 days:
    - Check if drift score decreased within 24h after response
    - Update effectiveness profile

    Called daily by ISE scheduler.
    """
    try:
        from apps.core.blueprint.models import DriftScore, InterventionLog

        thirty_days_ago = timezone.now() - timedelta(days=30)
        interventions = InterventionLog.objects.filter(
            user=user,
            created_at__gte=thirty_days_ago,
            responded_at__isnull=False,
        )

        total = interventions.count()
        if total == 0:
            return

        accepted = interventions.filter(user_response="accepted").count()
        dismissed = interventions.filter(user_response="dismissed").count()
        drift_resolved = 0

        for intervention in interventions.filter(
            user_response__in=["accepted", "adjusted"],
        ):
            # Check if drift improved within 24h
            response_date = intervention.responded_at.date()
            next_day = response_date + timedelta(days=1)

            before_score = DriftScore.objects.filter(
                user=user,
                date=response_date,
            ).values_list("score", flat=True).first()

            after_score = DriftScore.objects.filter(
                user=user,
                date=next_day,
            ).values_list("score", flat=True).first()

            if before_score is not None and after_score is not None:
                if after_score < before_score:
                    drift_resolved += 1

        # Compute avg response time
        from django.db.models import F
        avg_resp = interventions.filter(
            responded_at__isnull=False,
        ).annotate(
            resp_seconds=F("responded_at") - F("created_at"),
        )

        # Manual computation since F-expression duration is tricky
        resp_times = []
        for i in interventions.filter(responded_at__isnull=False):
            delta = (i.responded_at - i.created_at).total_seconds()
            resp_times.append(delta)
        avg_response = sum(resp_times) / len(resp_times) if resp_times else 0.0

        # Update profile
        _update_effectiveness_profile(
            user, total, accepted, dismissed,
            drift_resolved, avg_response,
        )

    except Exception as e:
        logger.error(
            f"InterventionTracker: Failed for user {user.id}: {e}",
            exc_info=True,
        )


def get_intervention_effectiveness(user):
    """Get or create the intervention effectiveness profile."""
    profile, _ = InterventionEffectivenessProfile.objects.get_or_create(user=user)
    return profile


def get_escalation_speed_modifier(user):
    """
    Get the escalation speed modifier.

    Returns:
        float: Negative = slower escalation (responsive user),
               Positive = faster escalation (non-responsive user).
    """
    try:
        profile = InterventionEffectivenessProfile.objects.filter(
            user=user,
        ).first()
        if profile and profile.total_interventions >= 3:
            return profile.escalation_speed_modifier
    except Exception:
        pass
    return 0.0


def _update_effectiveness_profile(
    user, total, accepted, dismissed, drift_resolved, avg_response_seconds
):
    """Update the aggregate effectiveness profile."""
    profile, _ = InterventionEffectivenessProfile.objects.get_or_create(user=user)

    profile.total_interventions = total
    profile.total_accepted = accepted
    profile.total_dismissed = dismissed
    profile.total_drift_resolved = drift_resolved
    profile.avg_response_time_seconds = round(avg_response_seconds, 1)

    # Effectiveness score
    if total > 0:
        acceptance_rate = accepted / total
        resolution_rate = drift_resolved / max(accepted, 1)
        profile.effectiveness_score = round(
            (0.6 * acceptance_rate + 0.4 * resolution_rate), 4
        )
    else:
        profile.effectiveness_score = 0.5

    # Escalation speed modifier
    if total >= 3:
        if profile.effectiveness_score >= 0.7:
            # Responsive user — slow down escalation
            profile.escalation_speed_modifier = -0.3
        elif profile.effectiveness_score >= 0.4:
            profile.escalation_speed_modifier = 0.0
        else:
            # Non-responsive — escalate faster
            profile.escalation_speed_modifier = 0.3

    profile.save()
