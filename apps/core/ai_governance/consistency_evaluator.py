"""
Phase 5 — Consistency Evaluator.

Compares declared importance (GovernanceProfile) vs observed behavior
to compute DriftPressure — an internal signal that drives strategy
selection. DriftPressure is NEVER shown to the user.

DriftPressure Formula:
    (MissRate × ImportanceWeight)
  + GoalImpactScore
  + TimeSensitivity
  + CapacityAvailability
  - RecentResponsiveness

Public API:
    - compute_drift_pressure(user, module_key) -> DriftPressureResult
    - compute_all_drift_pressures(user) -> list[DriftPressureResult]
    - get_miss_rate(user, module_key, days=7) -> float
"""

import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)


class DriftPressureResult:
    """Result of a drift pressure computation."""
    __slots__ = (
        'module_key', 'display_name', 'commitment_level',
        'drift_pressure', 'miss_rate', 'importance_weight',
        'goal_impact', 'time_sensitivity', 'capacity_factor',
        'responsiveness', 'strategy',
    )

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def to_dict(self):
        return {slot: getattr(self, slot, None) for slot in self.__slots__}


def compute_drift_pressure(user, module_key, days=7):
    """
    Compute DriftPressure for a single module/area.

    DriftPressure = (MissRate × ImportanceWeight)
                  + GoalImpactScore
                  + TimeSensitivity
                  + CapacityAvailability
                  - RecentResponsiveness

    Returns:
        DriftPressureResult or None if no governance profile exists.
    """
    try:
        from apps.core.ai_governance.models import GovernanceProfile

        profile = GovernanceProfile.objects.filter(
            user=user, module_key=module_key, is_active=True,
        ).first()

        if not profile:
            return None

        # Component 1: MissRate × ImportanceWeight
        miss_rate = get_miss_rate(user, module_key, days=days)
        importance = profile.importance_weight
        weighted_miss = miss_rate * importance

        # Component 2: GoalImpactScore
        goal_impact = _compute_goal_impact(user, profile)

        # Component 3: TimeSensitivity (deadline proximity)
        time_sensitivity = _compute_time_sensitivity(user, profile)

        # Component 4: CapacityAvailability (inversed — low capacity = more pressure)
        capacity_factor = _compute_capacity_factor(user)

        # Component 5: RecentResponsiveness (reduces pressure)
        responsiveness = _compute_responsiveness(user, days=days)

        drift_pressure = (
            weighted_miss
            + goal_impact
            + time_sensitivity
            + capacity_factor
            - responsiveness
        )

        # Clamp to 0-100
        drift_pressure = max(0.0, min(100.0, drift_pressure))

        return DriftPressureResult(
            module_key=module_key,
            display_name=profile.display_name,
            commitment_level=profile.commitment_level,
            drift_pressure=round(drift_pressure, 2),
            miss_rate=round(miss_rate, 3),
            importance_weight=importance,
            goal_impact=round(goal_impact, 2),
            time_sensitivity=round(time_sensitivity, 2),
            capacity_factor=round(capacity_factor, 2),
            responsiveness=round(responsiveness, 2),
            strategy=None,  # Filled by strategy selector
        )

    except Exception as e:
        logger.debug(f"DriftPressure computation failed for {module_key}: {e}")
        return None


def compute_all_drift_pressures(user):
    """
    Compute DriftPressure for all active governance profiles.

    Returns:
        list of DriftPressureResult, sorted by drift_pressure descending.
    """
    try:
        from apps.core.ai_governance.models import GovernanceProfile

        profiles = GovernanceProfile.objects.filter(user=user, is_active=True)
        results = []

        for profile in profiles:
            result = compute_drift_pressure(user, profile.module_key)
            if result:
                results.append(result)

        results.sort(key=lambda r: r.drift_pressure, reverse=True)
        return results

    except Exception as e:
        logger.debug(f"All drift pressures failed: {e}")
        return []


def get_miss_rate(user, module_key, days=7):
    """
    Calculate the miss rate for a module over the last N days.

    Miss rate = (expected occurrences - actual completions) / expected occurrences

    Checks NonNegotiables, habit completions, and scheduled block completion.

    Returns:
        float 0.0-1.0 (0 = no misses, 1 = all missed)
    """
    try:
        cutoff = timezone.now() - timedelta(days=days)

        # Check NonNegotiable completion via ScheduledBlock
        from apps.core.blueprint.models import NonNegotiable, ScheduledBlock

        # Find non-negotiables for this module
        nns = NonNegotiable.objects.filter(
            blueprint__user=user,
            module_key=module_key,
            is_active=True,
        )

        if not nns.exists():
            # Fall back to habit/goal tracking
            return _get_habit_miss_rate(user, module_key, days)

        expected = 0
        completed = 0
        today = timezone.localdate()

        for nn in nns:
            for day_offset in range(days):
                check_date = today - timedelta(days=day_offset)
                if nn.is_applicable_today(check_date):
                    expected += 1
                    # Check if completed via ScheduledBlock
                    block_done = ScheduledBlock.objects.filter(
                        plan__user=user,
                        plan__date=check_date,
                        behavior_key=nn.behavior_key,
                        is_completed=True,
                    ).exists()
                    if block_done:
                        completed += 1

        if expected == 0:
            return 0.0

        return (expected - completed) / expected

    except Exception as e:
        logger.debug(f"Miss rate calculation failed: {e}")
        return 0.0


def _get_habit_miss_rate(user, module_key, days):
    """Fallback miss rate from habit tracking."""
    try:
        from apps.core.ai_state.state_engine import get_state_value
        completion = get_state_value(user, f'{module_key}.completion_rate', None)
        if completion is not None:
            return 1.0 - min(1.0, float(completion))

        # Global habit rate
        avg = get_state_value(user, 'habits.avg_completion_rate', None)
        if avg is not None:
            return 1.0 - min(1.0, float(avg))

        return 0.0
    except Exception:
        return 0.0


def _compute_goal_impact(user, profile):
    """
    Score based on goal proximity and status.

    Returns 0-30 points.
    """
    try:
        from apps.purpose.models import LifeGoal

        tied_ids = profile.tied_goal_ids or []
        if not tied_ids:
            # Check for active goals in this module
            goals = LifeGoal.objects.filter(
                user=user,
                status='active',
                target_date__isnull=False,
            )[:5]
        else:
            goals = LifeGoal.objects.filter(id__in=tied_ids, status='active')

        if not goals.exists():
            return 0.0

        score = 0.0
        today = timezone.localdate()
        for goal in goals:
            if goal.target_date and goal.target_date <= today:
                score += 15.0  # Overdue
            elif goal.target_date:
                days_left = (goal.target_date - today).days
                if days_left <= 7:
                    score += 10.0
                elif days_left <= 30:
                    score += 5.0

        return min(30.0, score)
    except Exception:
        return 0.0


def _compute_time_sensitivity(user, profile):
    """
    Time-based urgency factor.

    Returns 0-15 points.
    """
    if profile.commitment_level == 'non_negotiable':
        return 10.0  # Always time-sensitive
    if profile.commitment_level == 'important':
        return 5.0
    return 0.0


def _compute_capacity_factor(user):
    """
    Capacity pressure — high capacity usage = more drift pressure.

    Returns 0-20 points.
    """
    try:
        import datetime as dt
        from apps.core.blueprint.models import ArchitecturePlan

        today = timezone.localdate()
        plan = ArchitecturePlan.get_active_for_date(user, today)
        if not plan:
            return 0.0

        blocks = list(plan.blocks.all())
        total_minutes = 0
        for b in blocks:
            if b.start_time and b.end_time:
                s = dt.datetime.combine(today, b.start_time)
                e = dt.datetime.combine(today, b.end_time)
                d = (e - s).total_seconds() / 60
                if d > 0:
                    total_minutes += d

        waking_minutes = 16 * 60
        capacity_pct = min(100, round(total_minutes / waking_minutes * 100))

        # >80% capacity = 20 points, <50% = 0
        if capacity_pct >= 80:
            return 20.0
        elif capacity_pct >= 60:
            return 10.0
        return 0.0
    except Exception:
        return 0.0


def _compute_responsiveness(user, days=7):
    """
    How responsive the user has been to interventions recently.

    Returns 0-25 points (subtracted from drift pressure).
    """
    try:
        from apps.core.blueprint.models import InterventionLog
        cutoff = timezone.now() - timedelta(days=days)

        interventions = InterventionLog.objects.filter(
            user=user,
            created_at__gte=cutoff,
            user_response__in=['accepted', 'adjusted'],
        )
        total = InterventionLog.objects.filter(
            user=user,
            created_at__gte=cutoff,
        ).exclude(user_response='pending').count()

        if total == 0:
            return 10.0  # No interventions = neutral

        acceptance_rate = interventions.count() / total
        return acceptance_rate * 25.0
    except Exception:
        return 10.0
