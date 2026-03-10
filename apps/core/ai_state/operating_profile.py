"""
Personal Operating Context — Profile Computation Service.

Project: Whole Life Journey
Path: apps/core/ai_state/operating_profile.py
Purpose: Compute behavioral synthesis from existing activity data

Description:
    Analyzes the last 30 days of user activity and produces a structured
    behavioral profile stored in UserOperatingProfile. This runs as a
    nightly batch job — never during conversation.

    Phase 1 dimensions:
    1. PRODUCTIVE WINDOWS — when the user is most active
    2. DEFERRAL PATTERNS — which tasks the user tends to delay
    3. MOMENTUM PHASE — current behavioral trajectory

    Design rules:
    - Read from existing data only (no new tracking)
    - Store structured signals, not narrative text
    - Beth generates the narrative at conversation time
    - Graceful degradation if any data source is unavailable

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import logging
from collections import Counter, defaultdict
from datetime import timedelta

from django.db.models import Avg, Count, Q
from django.utils import timezone

logger = logging.getLogger(__name__)

# ── Constants ──
WINDOW_DAYS = 30
MIN_CONFIDENCE_DAYS = 14


def compute_user_operating_profile(user):
    """
    Compute the full operating profile for a single user.

    Analyzes the last 30 days and produces structured behavioral
    dimensions. Stores result in UserOperatingProfile.

    Args:
        user: Django User instance.

    Returns:
        UserOperatingProfile instance (saved), or None on fatal error.
    """
    from apps.core.ai_state.models import UserOperatingProfile

    now = timezone.now()
    window_start = now - timedelta(days=WINDOW_DAYS)

    # Compute each dimension independently — each can fail without
    # blocking the others
    profile_data = {}
    sample_days = 0

    # 1. Productive Windows
    try:
        pw_result = _compute_productive_windows(user, window_start, now)
        if pw_result:
            profile_data['productive_windows'] = pw_result
            sample_days = max(sample_days, pw_result.get('sample_days', 0))
    except Exception:
        logger.error(
            "Operating profile: productive_windows failed for user=%s",
            user.id, exc_info=True,
        )

    # 2. Deferral Patterns
    try:
        dp_result = _compute_deferral_patterns(user, window_start, now)
        if dp_result:
            profile_data['deferral_patterns'] = dp_result
            sample_days = max(sample_days, dp_result.get('sample_days', 0))
    except Exception:
        logger.error(
            "Operating profile: deferral_patterns failed for user=%s",
            user.id, exc_info=True,
        )

    # 3. Momentum Phase
    try:
        mp_result = _compute_momentum_phase(user, window_start, now)
        if mp_result:
            profile_data['momentum_phase'] = mp_result
            sample_days = max(sample_days, mp_result.get('sample_days', 0))
    except Exception:
        logger.error(
            "Operating profile: momentum_phase failed for user=%s",
            user.id, exc_info=True,
        )

    # Persist
    try:
        profile, created = UserOperatingProfile.objects.update_or_create(
            user=user,
            defaults={
                'profile_data': profile_data,
                'sample_days': sample_days,
                'last_computed': now,
                'version': UserOperatingProfile.SCHEMA_VERSION,
            },
        )
        return profile
    except Exception:
        logger.error(
            "Operating profile: failed to save for user=%s",
            user.id, exc_info=True,
        )
        return None


# =========================================================================
# Dimension 1: Productive Windows
# =========================================================================

def _compute_productive_windows(user, window_start, now):
    """
    Determine when the user is most active and productive.

    Analyzes task completion times, workout times, and journal entry
    times to identify peak and low productivity hours.

    Returns:
        dict with peak_hours, low_hours, sample_days, confidence.
    """
    hour_completions = Counter()
    total_events = 0
    active_dates = set()

    # Task completions (hour of day when they completed tasks)
    try:
        from apps.life.models import Task
        completed_tasks = Task.objects.filter(
            user=user,
            completion_status='completed',
            completed_at__gte=window_start,
            completed_at__lte=now,
        ).values_list('completed_at', flat=True)

        for dt in completed_tasks:
            local_dt = timezone.localtime(dt)
            hour_completions[local_dt.hour] += 1
            active_dates.add(local_dt.date())
            total_events += 1
    except Exception:
        logger.debug("Operating profile: task completion data unavailable", exc_info=True)

    # Workout sessions (start time)
    try:
        from apps.health.models import WorkoutSession
        workouts = WorkoutSession.objects.filter(
            user=user,
            date__gte=window_start.date(),
            date__lte=now.date(),
        ).exclude(started_at__isnull=True).values_list('started_at', flat=True)

        for dt in workouts:
            local_dt = timezone.localtime(dt)
            hour_completions[local_dt.hour] += 1
            active_dates.add(local_dt.date())
            total_events += 1
    except Exception:
        logger.debug("Operating profile: workout data unavailable", exc_info=True)

    # Journal entries (created_at as proxy for writing time)
    try:
        from apps.journal.models import JournalEntry
        entries = JournalEntry.objects.filter(
            user=user,
            created_at__gte=window_start,
            created_at__lte=now,
        ).values_list('created_at', flat=True)

        for dt in entries:
            local_dt = timezone.localtime(dt)
            hour_completions[local_dt.hour] += 1
            active_dates.add(local_dt.date())
            total_events += 1
    except Exception:
        logger.debug("Operating profile: journal data unavailable", exc_info=True)

    # Habit entries (date-based, no timestamp — count the date only)
    try:
        from apps.purpose.models import HabitEntry
        habit_dates = HabitEntry.objects.filter(
            goal__user=user,
            completed=True,
            date__gte=window_start.date(),
            date__lte=now.date(),
        ).values_list('date', flat=True)

        for d in habit_dates:
            active_dates.add(d)
    except Exception:
        logger.debug("Operating profile: habit data unavailable", exc_info=True)

    sample_days = len(active_dates)

    if total_events < 5:
        # Not enough timestamped events to identify windows
        return {
            'peak_hours': [],
            'low_hours': [],
            'sample_days': sample_days,
            'total_events': total_events,
            'confidence': 0.0,
        }

    # Find peak hours (top 3 most active) and low hours (bottom 3 among waking hours)
    # Only consider waking hours (6am-11pm)
    waking_hours = range(6, 23)
    waking_counts = {h: hour_completions.get(h, 0) for h in waking_hours}

    sorted_hours = sorted(waking_counts.items(), key=lambda x: x[1], reverse=True)
    peak_hours = [h for h, c in sorted_hours[:3] if c > 0]

    # Low hours: waking hours with fewest completions (but only if we have
    # enough data to distinguish signal from noise)
    if sample_days >= 7 and total_events >= 15:
        low_hours = [h for h, c in sorted_hours[-3:] if c == 0 or c <= 1]
    else:
        low_hours = []

    # Confidence: based on sample size and event density
    confidence = min(1.0, (sample_days / MIN_CONFIDENCE_DAYS) * (min(total_events, 50) / 50))

    return {
        'peak_hours': peak_hours,
        'low_hours': low_hours,
        'sample_days': sample_days,
        'total_events': total_events,
        'confidence': round(confidence, 2),
    }


# =========================================================================
# Dimension 2: Deferral Patterns
# =========================================================================

def _compute_deferral_patterns(user, window_start, now):
    """
    Identify which types of tasks the user tends to defer or skip.

    Analyzes task completion vs skipping, intervention dismissals,
    and skip streaks to find deferral-prone categories.

    Returns:
        dict with deferral_rate, prone_modules, skip_streak_avg,
        intervention_dismiss_rate, sample_days, confidence.
    """
    from apps.life.models import Task

    # Get all tasks with activity in the window
    tasks_in_window = Task.objects.filter(
        user=user,
        created_at__gte=window_start,
    ).exclude(completion_status='pending')

    total_resolved = tasks_in_window.count()
    if total_resolved == 0:
        return {
            'overall_deferral_rate': 0.0,
            'prone_modules': [],
            'prone_commitment_levels': [],
            'avg_skip_streak': 0.0,
            'intervention_dismiss_rate': 0.0,
            'sample_days': 0,
            'confidence': 0.0,
        }

    completed_count = tasks_in_window.filter(completion_status='completed').count()
    skipped_count = tasks_in_window.filter(completion_status='skipped').count()

    overall_deferral_rate = round(skipped_count / total_resolved, 2) if total_resolved > 0 else 0.0

    # Deferral by module
    module_stats = (
        tasks_in_window
        .exclude(module='')
        .values('module')
        .annotate(
            total=Count('id'),
            skipped=Count('id', filter=Q(completion_status='skipped')),
        )
    )
    prone_modules = []
    for ms in module_stats:
        if ms['total'] >= 3:  # Need minimum sample
            rate = ms['skipped'] / ms['total']
            if rate >= 0.3:  # 30%+ skip rate = deferral-prone
                prone_modules.append({
                    'module': ms['module'],
                    'deferral_rate': round(rate, 2),
                    'sample_size': ms['total'],
                })
    prone_modules.sort(key=lambda x: x['deferral_rate'], reverse=True)

    # Deferral by commitment level
    commitment_stats = (
        tasks_in_window
        .values('commitment_level')
        .annotate(
            total=Count('id'),
            skipped=Count('id', filter=Q(completion_status='skipped')),
        )
    )
    prone_commitment_levels = []
    for cs in commitment_stats:
        if cs['total'] >= 3:
            rate = cs['skipped'] / cs['total']
            if rate >= 0.2:  # 20%+ for commitment levels
                prone_commitment_levels.append({
                    'level': cs['commitment_level'],
                    'deferral_rate': round(rate, 2),
                    'sample_size': cs['total'],
                })

    # Average skip streak (across all tasks that have been skipped)
    skip_streak_data = (
        Task.objects.filter(
            user=user,
            skip_streak__gt=0,
        ).aggregate(avg_streak=Avg('skip_streak'))
    )
    avg_skip_streak = round(skip_streak_data['avg_streak'] or 0, 1)

    # Intervention dismissal rate (from InterventionLog)
    intervention_dismiss_rate = 0.0
    try:
        from apps.core.blueprint.models import InterventionLog
        interventions = InterventionLog.objects.filter(
            user=user,
            created_at__gte=window_start,
        ).exclude(user_response='pending')

        total_interventions = interventions.count()
        if total_interventions >= 3:
            dismissed = interventions.filter(
                user_response__in=['dismissed', 'proceeded']
            ).count()
            intervention_dismiss_rate = round(dismissed / total_interventions, 2)
    except Exception:
        logger.debug("Operating profile: intervention data unavailable", exc_info=True)

    # Sample days = days with at least one task resolved
    active_dates = set()
    for dt in tasks_in_window.values_list('completed_at', flat=True):
        if dt:
            active_dates.add(timezone.localtime(dt).date())
    sample_days = len(active_dates)

    confidence = min(1.0, (total_resolved / 20) * (sample_days / MIN_CONFIDENCE_DAYS))

    return {
        'overall_deferral_rate': overall_deferral_rate,
        'prone_modules': prone_modules[:3],  # Top 3
        'prone_commitment_levels': prone_commitment_levels,
        'avg_skip_streak': avg_skip_streak,
        'intervention_dismiss_rate': intervention_dismiss_rate,
        'total_tasks_resolved': total_resolved,
        'completed_count': completed_count,
        'skipped_count': skipped_count,
        'sample_days': sample_days,
        'confidence': round(min(confidence, 1.0), 2),
    }


# =========================================================================
# Dimension 3: Momentum Phase
# =========================================================================

def _compute_momentum_phase(user, window_start, now):
    """
    Determine the user's current behavioral momentum.

    Compares recent (last 7 days) activity levels against the
    30-day baseline to detect acceleration, sustaining, or declining
    patterns.

    Returns:
        dict with current_phase, active_domain_count, trend,
        recent_vs_baseline ratio, sample_days, confidence.
    """
    seven_days_ago = now - timedelta(days=7)

    # Count active days in full window vs recent window
    recent_dates = set()
    baseline_dates = set()

    # Task activity
    try:
        from apps.life.models import Task
        task_dates = Task.objects.filter(
            user=user,
            completion_status='completed',
            completed_at__gte=window_start,
            completed_at__lte=now,
        ).values_list('completed_at', flat=True)

        for dt in task_dates:
            d = timezone.localtime(dt).date()
            if dt >= seven_days_ago:
                recent_dates.add(d)
            baseline_dates.add(d)
    except Exception:
        logger.debug("Operating profile: task data unavailable for momentum", exc_info=True)

    # Workout activity
    try:
        from apps.health.models import WorkoutSession
        workout_dates = WorkoutSession.objects.filter(
            user=user,
            date__gte=window_start.date(),
            date__lte=now.date(),
        ).values_list('date', flat=True)

        for d in workout_dates:
            if d >= seven_days_ago.date():
                recent_dates.add(d)
            baseline_dates.add(d)
    except Exception:
        logger.debug("Operating profile: workout data unavailable for momentum", exc_info=True)

    # Journal activity
    try:
        from apps.journal.models import JournalEntry
        journal_dates = JournalEntry.objects.filter(
            user=user,
            created_at__gte=window_start,
            created_at__lte=now,
        ).values_list('created_at', flat=True)

        for dt in journal_dates:
            d = timezone.localtime(dt).date()
            if dt >= seven_days_ago:
                recent_dates.add(d)
            baseline_dates.add(d)
    except Exception:
        logger.debug("Operating profile: journal data unavailable for momentum", exc_info=True)

    # Habit activity
    try:
        from apps.purpose.models import HabitEntry
        habit_dates = HabitEntry.objects.filter(
            goal__user=user,
            completed=True,
            date__gte=window_start.date(),
            date__lte=now.date(),
        ).values_list('date', flat=True)

        for d in habit_dates:
            if d >= seven_days_ago.date():
                recent_dates.add(d)
            baseline_dates.add(d)
    except Exception:
        logger.debug("Operating profile: habit data unavailable for momentum", exc_info=True)

    sample_days = len(baseline_dates)

    if sample_days < 3:
        return {
            'current_phase': 'insufficient_data',
            'trend': 'unknown',
            'recent_active_days': len(recent_dates),
            'baseline_active_days': sample_days,
            'recent_vs_baseline_ratio': 0.0,
            'active_domain_count': 0,
            'sample_days': sample_days,
            'confidence': 0.0,
        }

    # Compare recent 7-day activity rate vs 30-day baseline rate
    baseline_rate = sample_days / WINDOW_DAYS  # e.g., 20/30 = 0.67
    recent_rate = len(recent_dates) / 7  # e.g., 5/7 = 0.71

    if baseline_rate > 0:
        ratio = recent_rate / baseline_rate
    else:
        ratio = 0.0

    # Count active domains in last 7 days
    active_domains = _count_active_domains(user, seven_days_ago, now)

    # Determine phase
    if ratio >= 1.15:
        phase = 'building'  # Recent activity exceeds baseline by 15%+
        trend = 'accelerating'
    elif ratio >= 0.85:
        phase = 'sustaining'  # Within ±15% of baseline
        trend = 'steady'
    elif ratio >= 0.5:
        phase = 'declining'  # Recent activity 50-85% of baseline
        trend = 'slowing'
    else:
        phase = 'recovering'  # Recent activity less than 50% of baseline
        trend = 'low'

    # Confidence
    confidence = min(1.0, (sample_days / MIN_CONFIDENCE_DAYS) * min(ratio + 0.3, 1.0))

    return {
        'current_phase': phase,
        'trend': trend,
        'recent_active_days': len(recent_dates),
        'baseline_active_days': sample_days,
        'recent_vs_baseline_ratio': round(ratio, 2),
        'active_domain_count': active_domains,
        'sample_days': sample_days,
        'confidence': round(min(confidence, 1.0), 2),
    }


def _count_active_domains(user, start, end):
    """Count how many distinct domains the user has been active in recently."""
    domains = set()

    try:
        from apps.life.models import Task
        if Task.objects.filter(
            user=user, completion_status='completed',
            completed_at__gte=start, completed_at__lte=end,
        ).exists():
            domains.add('tasks')
    except Exception:
        pass

    try:
        from apps.health.models import WorkoutSession
        if WorkoutSession.objects.filter(
            user=user, date__gte=start.date(), date__lte=end.date(),
        ).exists():
            domains.add('fitness')
    except Exception:
        pass

    try:
        from apps.journal.models import JournalEntry
        if JournalEntry.objects.filter(
            user=user, created_at__gte=start, created_at__lte=end,
        ).exists():
            domains.add('journal')
    except Exception:
        pass

    try:
        from apps.purpose.models import HabitEntry
        if HabitEntry.objects.filter(
            goal__user=user, completed=True,
            date__gte=start.date(), date__lte=end.date(),
        ).exists():
            domains.add('habits')
    except Exception:
        pass

    try:
        from apps.health.models import MedicineLog
        if MedicineLog.objects.filter(
            user=user, logged_datetime__gte=start, logged_datetime__lte=end,
        ).exists():
            domains.add('health')
    except Exception:
        pass

    return len(domains)


# =========================================================================
# Batch Computation (called by Celery task)
# =========================================================================

def recompute_all_profiles():
    """
    Recompute UserOperatingProfile for all active AI users.

    Called by the nightly Celery Beat task. Iterates over users
    with AI enabled and sufficient recent activity.

    Returns:
        dict with counts: computed, skipped, errors.
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()
    thirty_days_ago = timezone.now() - timedelta(days=WINDOW_DAYS)

    # Only compute for users who:
    # 1. Have AI enabled (they interact with Beth)
    # 2. Have been active in the last 30 days
    active_users = (
        User.objects
        .filter(
            preferences__ai_enabled=True,
            last_login__gte=thirty_days_ago,
        )
        .select_related('preferences')
        .iterator()
    )

    computed = 0
    skipped = 0
    errors = 0

    for user in active_users:
        try:
            result = compute_user_operating_profile(user)
            if result:
                computed += 1
            else:
                skipped += 1
        except Exception:
            errors += 1
            logger.error(
                "Operating profile: recompute failed for user=%s",
                user.id, exc_info=True,
            )

    logger.info(
        "Operating profile batch complete: computed=%d, skipped=%d, errors=%d",
        computed, skipped, errors,
    )
    return {'computed': computed, 'skipped': skipped, 'errors': errors}
