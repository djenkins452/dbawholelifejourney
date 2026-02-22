"""
Whole Life Journey — Priority Conflict Detector

Project: Whole Life Journey
Path: apps/core/blueprint/priority_conflict_detector.py
Purpose: Detect conflicts between declared priorities and actual behavior

Description:
    Compares UserPriorityProfile declarations against 7-day behavior patterns
    from SAE state data. Produces conflict signals with tier-appropriate
    response framing.

    Phase 1 response framing:
    - Tier 1 (Non-Negotiable): Direct accountability tone
    - Tier 2/3 (Important/Flexible): Curious reflection tone

    Does NOT modify UAL, tier1_protected_behaviors, or NonNegotiable.
    Feeds conflicts into existing governance tone pipeline.

    Respects partial task progress: progress_percentage > 0 counts as
    "worked on", not "missed".

Public API:
    - detect_priority_conflicts(user) -> list[PriorityConflict]
    - get_conflict_prompt_injection(user) -> str

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import List, Optional

from django.utils import timezone

logger = logging.getLogger(__name__)


@dataclass
class PriorityConflict:
    """A detected conflict between declared priority and observed behavior."""
    module_key: str
    sub_module_key: str
    declared_level: int          # 1=Non-Negotiable, 2=Important, 3=Flexible
    declared_weight: float
    declared_reason: str
    behavior_signal: str         # Description of observed behavior gap
    severity: str                # 'high' (tier1), 'medium' (tier2), 'low' (tier3)
    response_tone: str           # 'accountability' or 'reflection'
    evidence: dict               # Raw data supporting the conflict


def detect_priority_conflicts(user) -> List[PriorityConflict]:
    """
    Compare declared priorities against 7-day behavior patterns.

    Returns a list of PriorityConflict objects where the user's behavior
    doesn't match what they declared as important.

    This function reads from SAE (state engine) and direct model queries.
    It does NOT write anything — purely observational.

    Respects partial task progress: tasks with progress_percentage > 0
    are treated as "worked on", not "missed".

    Args:
        user: Django User instance.

    Returns:
        List of PriorityConflict instances, sorted by severity (high first).
    """
    try:
        from apps.core.blueprint.models import UserPriorityProfile
        priorities = UserPriorityProfile.objects.filter(user=user)
    except Exception:
        return []

    if not priorities.exists():
        return []

    conflicts = []
    week_ago = timezone.now() - timedelta(days=7)

    for priority in priorities:
        conflict = _check_module_behavior(user, priority, week_ago)
        if conflict:
            conflicts.append(conflict)

    # Sort: high severity first
    severity_order = {'high': 0, 'medium': 1, 'low': 2}
    conflicts.sort(key=lambda c: severity_order.get(c.severity, 3))

    return conflicts


def get_conflict_prompt_injection(user) -> str:
    """
    Build a prompt injection block for detected priority conflicts.

    Used by the CoS context builder to inject conflict awareness
    into the assistant system prompt.

    Args:
        user: Django User instance.

    Returns:
        str — Formatted conflict block, or empty string if no conflicts.
    """
    conflicts = detect_priority_conflicts(user)
    if not conflicts:
        return ''

    lines = ["--- PRIORITY ALIGNMENT SIGNALS ---"]

    for c in conflicts[:5]:  # Cap at 5 to limit prompt tokens
        if c.response_tone == 'accountability':
            lines.append(
                f"[ACCOUNTABILITY] {c.module_key}: {c.behavior_signal} "
                f"(declared: {_level_label(c.declared_level)})"
            )
            if c.declared_reason:
                lines.append(f"  User's reason: \"{c.declared_reason[:150]}\"")
        else:
            lines.append(
                f"[REFLECTION] {c.module_key}: {c.behavior_signal} "
                f"(declared: {_level_label(c.declared_level)})"
            )

    lines.append("")
    lines.append(
        "For accountability items: Be direct but respectful. "
        "Name the gap. Reference their stated reason."
    )
    lines.append(
        "For reflection items: Be curious, not accusatory. "
        "Ask what's going on. Explore, don't judge."
    )
    lines.append("--- END PRIORITY ALIGNMENT ---")

    return '\n'.join(lines)


# =============================================================================
# MODULE-SPECIFIC BEHAVIOR CHECKS
# =============================================================================


def _check_module_behavior(user, priority, since) -> Optional[PriorityConflict]:
    """
    Check if a specific priority declaration has a matching behavior gap.

    Dispatches to module-specific checkers. Returns None if no conflict.
    """
    module = priority.module_key
    sub = priority.sub_module_key

    checkers = {
        'health': _check_health_behavior,
        'faith': _check_faith_behavior,
        'purpose': _check_purpose_behavior,
        'journal': _check_journal_behavior,
    }

    checker = checkers.get(module)
    if checker:
        return checker(user, priority, since)

    return None


def _check_health_behavior(user, priority, since) -> Optional[PriorityConflict]:
    """Check health module behavior against declared priority."""
    sub = priority.sub_module_key
    evidence = {}

    try:
        if sub in ('health.weight', 'health.physical.weight', ''):
            from apps.health.models import WeightEntry
            count = WeightEntry.objects.filter(
                user=user, recorded_at__gte=since
            ).count()
            evidence['weight_entries_7d'] = count
            if count == 0 and priority.declared_priority_level <= 2:
                return _make_conflict(
                    priority, "No weight logged in 7 days", evidence
                )

        if sub in ('health.activity', 'health.physical.activity', ''):
            from apps.health.models import WorkoutSession
            count = WorkoutSession.objects.filter(
                user=user, date__gte=since.date()
            ).count()
            evidence['workouts_7d'] = count
            if count == 0 and priority.declared_priority_level == 1:
                return _make_conflict(
                    priority, "No workouts logged in 7 days", evidence
                )
            if count <= 1 and priority.declared_priority_level == 1:
                return _make_conflict(
                    priority, f"Only {count} workout in 7 days", evidence
                )

        if sub in ('health.sleep', 'health.physical.sleep', ''):
            from apps.health.models import SleepEntry
            count = SleepEntry.objects.filter(
                user=user, sleep_date__gte=since.date()
            ).count()
            evidence['sleep_entries_7d'] = count
            if count == 0 and priority.declared_priority_level <= 2:
                return _make_conflict(
                    priority, "No sleep tracked in 7 days", evidence
                )

        if sub in ('health.medications', 'health.physical.medications', ''):
            from apps.health.models import Medicine
            active_meds = Medicine.objects.filter(user=user, is_active=True).count()
            if active_meds > 0:
                # Check recent adherence via medicine logs
                from apps.health.models import MedicineLog
                log_count = MedicineLog.objects.filter(
                    user=user, taken_at__gte=since
                ).count()
                expected = active_meds * 7  # rough expected
                if expected > 0:
                    adherence = log_count / expected
                    evidence['adherence_rate_7d'] = round(adherence, 2)
                    if adherence < 0.5 and priority.declared_priority_level == 1:
                        return _make_conflict(
                            priority,
                            f"Medication adherence at {round(adherence * 100)}% this week",
                            evidence,
                        )

        if sub in ('health.nutrition', 'health.physical.nutrition', ''):
            from apps.health.models import FoodEntry
            count = FoodEntry.objects.filter(
                user=user, date__gte=since.date()
            ).count()
            evidence['food_entries_7d'] = count
            if count == 0 and priority.declared_priority_level <= 2:
                return _make_conflict(
                    priority, "No nutrition tracked in 7 days", evidence
                )

        if sub in ('health.fasting', 'health.physical.fasting', ''):
            from apps.health.models import FastingWindow
            count = FastingWindow.objects.filter(
                user=user, start_time__gte=since
            ).count()
            evidence['fasts_7d'] = count
            if count == 0 and priority.declared_priority_level <= 2:
                return _make_conflict(
                    priority, "No fasting logged in 7 days", evidence
                )

    except Exception as e:
        logger.debug("Health conflict check error: %s", e)

    return None


def _check_faith_behavior(user, priority, since) -> Optional[PriorityConflict]:
    """Check faith module behavior."""
    evidence = {}
    try:
        from apps.faith.models import PrayerRequest
        prayer_count = PrayerRequest.objects.filter(
            user=user, created_at__gte=since
        ).count()
        evidence['prayer_activity_7d'] = prayer_count

        from apps.faith.models import UserReadingPlan
        active_plans = UserReadingPlan.objects.filter(
            user=user, status='active'
        ).count()
        evidence['active_reading_plans'] = active_plans

        # If faith is non-negotiable but no activity
        if (prayer_count == 0 and active_plans == 0
                and priority.declared_priority_level == 1):
            return _make_conflict(
                priority, "No faith activity in 7 days", evidence
            )
    except Exception as e:
        logger.debug("Faith conflict check error: %s", e)

    return None


def _check_purpose_behavior(user, priority, since) -> Optional[PriorityConflict]:
    """Check purpose/goals module behavior."""
    evidence = {}
    try:
        from apps.purpose.models import LifeGoal
        active_goals = LifeGoal.objects.filter(
            user=user, status='active'
        ).count()
        evidence['active_goals'] = active_goals

        # Check for overdue goals
        overdue = LifeGoal.objects.filter(
            user=user, status='active',
            target_date__lt=timezone.localdate(),
        ).count()
        evidence['overdue_goals'] = overdue

        if overdue > 0 and priority.declared_priority_level == 1:
            return _make_conflict(
                priority, f"{overdue} overdue goals", evidence
            )

        # Check task progress — respect partial progress
        from apps.life.models import Task
        active_tasks = Task.objects.filter(
            user=user, is_completed=False,
        )
        total_active = active_tasks.count()
        # Tasks with progress > 0 count as "worked on"
        worked_on = active_tasks.filter(progress_percentage__gt=0).count()
        untouched = total_active - worked_on
        evidence['active_tasks'] = total_active
        evidence['worked_on'] = worked_on
        evidence['untouched'] = untouched

        overdue_tasks = active_tasks.filter(
            due_date__lt=timezone.localdate(),
            progress_percentage=0,  # Only flag if truly untouched
        ).count()
        evidence['overdue_untouched_tasks'] = overdue_tasks

        if overdue_tasks > 3 and priority.declared_priority_level <= 2:
            return _make_conflict(
                priority,
                f"{overdue_tasks} overdue tasks with no progress",
                evidence,
            )

    except Exception as e:
        logger.debug("Purpose conflict check error: %s", e)

    return None


def _check_journal_behavior(user, priority, since) -> Optional[PriorityConflict]:
    """Check journal module behavior."""
    evidence = {}
    try:
        from apps.journal.models import JournalEntry
        count = JournalEntry.objects.filter(
            user=user, entry_date__gte=since.date()
        ).count()
        evidence['entries_7d'] = count

        if count == 0 and priority.declared_priority_level == 1:
            return _make_conflict(
                priority, "No journal entries in 7 days", evidence
            )
    except Exception as e:
        logger.debug("Journal conflict check error: %s", e)

    return None


# =============================================================================
# HELPERS
# =============================================================================


def _make_conflict(priority, signal, evidence) -> PriorityConflict:
    """Create a PriorityConflict from a priority and behavior signal."""
    level = priority.declared_priority_level

    if level == 1:
        severity = 'high'
        tone = 'accountability'
    elif level == 2:
        severity = 'medium'
        tone = 'reflection'
    else:
        severity = 'low'
        tone = 'reflection'

    return PriorityConflict(
        module_key=priority.module_key,
        sub_module_key=priority.sub_module_key,
        declared_level=level,
        declared_weight=float(priority.importance_weight),
        declared_reason=priority.declared_reason or '',
        behavior_signal=signal,
        severity=severity,
        response_tone=tone,
        evidence=evidence,
    )


def _level_label(level: int) -> str:
    """Human-readable label for priority level (internal use only)."""
    return {
        1: 'Non-Negotiable',
        2: 'Important',
        3: 'Flexible',
    }.get(level, 'Unknown')
