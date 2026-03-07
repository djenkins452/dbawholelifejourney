# ==============================================================================
# File: situational_awareness.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: v8 Situational Awareness Summary — deterministic behavioral
#              pattern builder for the Chief of Staff pipeline.
#              Computes momentum, drift, one-off sensitivity, and emotional
#              context from recent user data (7-14 day windows).
#              All computations are DB queries + math — no LLM calls.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-07
# ==============================================================================
"""
Situational Awareness Summary (v8)

Transforms the CoS from state-aware to pattern-aware by synthesizing
recent behavioral data into a compact context block.

Public API:
    build_situational_awareness(user) -> dict
    format_situational_awareness_injection(sa_data) -> str
"""

import logging
from datetime import timedelta
from typing import Optional

from django.utils import timezone

logger = logging.getLogger(__name__)

# ── Pattern classification thresholds ──
CONSISTENT_THRESHOLD = 5   # 5-7 of 7 days = consistent
MIXED_THRESHOLD = 3        # 3-4 of 7 days = mixed
# 0-2 of 7 days = slipping

# ── Fatigue / distress keyword sets ──
FATIGUE_KEYWORDS = frozenset({
    'tired', 'exhausted', 'fatigue', 'fatigued',
    'burnt out', 'burnout', 'burn out',
})
DISTRESS_KEYWORDS = frozenset({
    'overwhelmed', 'stressed', 'grief', 'grieving',
    'struggling', 'depressed', 'anxious', 'anxiety',
    'hopeless', 'breaking down',
})

# ── Mood score mapping (matches executive_briefing.py) ──
MOOD_SCORES = {
    'great': 5,
    'good': 4,
    'okay': 3,
    'low': 2,
    'difficult': 1,
}

# ── Workout / bike ride keyword detection ──
WORKOUT_KEYWORDS = frozenset({
    'workout', 'exercise', 'gym', 'training', 'lift',
    'strength', 'cardio', 'crossfit', 'weight training',
})
BIKE_KEYWORDS = frozenset({
    'bike', 'cycling', 'ride', 'bicycle', 'biking',
})

# ── Journal-related goal keywords (for accountability gate) ──
JOURNAL_GOAL_KEYWORDS = frozenset({
    'journal', 'journaling', 'writing', 'reflection',
    'diary', 'gratitude',
})


def _classify_consistency(days_active, window=7):
    """Classify a domain's consistency over the evaluation window."""
    if days_active >= CONSISTENT_THRESHOLD:
        return 'consistent'
    elif days_active >= MIXED_THRESHOLD:
        return 'mixed'
    else:
        return 'slipping'


def _has_proven_priority(user, domain_keywords):
    """
    Check if user has an active goal/habit matching this domain.
    Only returns True when accountability framing is justified.
    """
    try:
        from apps.purpose.models import HabitGoal
        active_goals = HabitGoal.objects.filter(
            user=user,
            status='active',
        ).values_list('name', flat=True)
        name_lower_set = {n.lower() for n in active_goals}
        return any(
            kw in name
            for kw in domain_keywords
            for name in name_lower_set
        )
    except Exception:
        return False


def _get_workout_pattern(user, today):
    """Compute workout consistency from DailyHealthSummary (7-day window)."""
    try:
        from apps.health.models import DailyHealthSummary
        week_ago = today - timedelta(days=7)
        summaries = DailyHealthSummary.objects.filter(
            user=user,
            summary_date__gte=week_ago,
            summary_date__lt=today,  # Exclude today — incomplete
        )
        days_with_workout = summaries.filter(workout_count__gt=0).count()
        total_days = summaries.count()

        if total_days == 0:
            return None

        classification = _classify_consistency(days_with_workout)
        return {
            'domain': 'workout',
            'days_active': days_with_workout,
            'total_days': min(total_days, 7),
            'classification': classification,
            'line': f"Workout pattern: {days_with_workout} of {min(total_days, 7)} days — {classification}",
        }
    except Exception as e:
        logger.debug("SA: workout pattern unavailable: %s", e)
        return None


def _get_weight_tracking_pattern(user, today):
    """Compute weight tracking consistency from WeightEntry (7-day window)."""
    try:
        from apps.health.models import WeightEntry
        week_ago = today - timedelta(days=7)
        distinct_dates = (
            WeightEntry.objects.filter(
                user=user,
                recorded_at__date__gte=week_ago,
                recorded_at__date__lt=today,
            )
            .dates('recorded_at', 'day')
            .count()
        )

        if distinct_dates == 0:
            return None

        classification = _classify_consistency(distinct_dates)
        return {
            'domain': 'weight_tracking',
            'days_active': distinct_dates,
            'total_days': 7,
            'classification': classification,
            'line': f"Weight tracking: {distinct_dates} of 7 days — {classification}",
        }
    except Exception as e:
        logger.debug("SA: weight tracking unavailable: %s", e)
        return None


def _get_journal_pattern(user, today):
    """Compute journal consistency from JournalEntry (14-day window)."""
    try:
        from apps.journal.models import JournalEntry
        two_weeks_ago = today - timedelta(days=14)
        week_ago = today - timedelta(days=7)

        # 7-day count for classification
        recent_dates = (
            JournalEntry.objects.filter(
                user=user,
                entry_date__gte=week_ago,
                entry_date__lt=today,
            )
            .values('entry_date')
            .distinct()
            .count()
        )

        # Also check gap — how many days since last entry?
        last_entry = (
            JournalEntry.objects.filter(
                user=user,
                entry_date__lte=today,
            )
            .order_by('-entry_date')
            .values_list('entry_date', flat=True)
            .first()
        )

        if last_entry is None and recent_dates == 0:
            return None  # No journal history at all

        days_since_last = (today - last_entry).days if last_entry else None

        classification = _classify_consistency(recent_dates)

        if days_since_last is not None and days_since_last >= 5 and recent_dates == 0:
            line = f"Journaling: no entries in {days_since_last} days — slipping"
            classification = 'slipping'
        elif recent_dates == 0:
            line = "Journaling: no entries this week — slipping"
            classification = 'slipping'
        else:
            line = f"Journaling: {recent_dates} entries in last 7 days — {classification}"

        # Accountability gate: only flag as drift if proven priority
        has_priority = _has_proven_priority(user, JOURNAL_GOAL_KEYWORDS)

        return {
            'domain': 'journaling',
            'days_active': recent_dates,
            'total_days': 7,
            'classification': classification,
            'has_proven_priority': has_priority,
            'days_since_last': days_since_last,
            'line': line,
        }
    except Exception as e:
        logger.debug("SA: journal pattern unavailable: %s", e)
        return None


def _get_mood_trend(user, today):
    """Compute mood trend from JournalEntry mood field (7-day, weak signal)."""
    try:
        from apps.journal.models import JournalEntry
        week_ago = today - timedelta(days=7)
        moods = list(
            JournalEntry.objects.filter(
                user=user,
                entry_date__gte=week_ago,
                entry_date__lt=today,
                mood__isnull=False,
            )
            .exclude(mood='')
            .values_list('mood', flat=True)
        )

        if len(moods) < 3:
            return None  # Insufficient data — skip

        scores = [MOOD_SCORES.get(m, 3) for m in moods]
        avg_score = sum(scores) / len(scores)

        if avg_score >= 4.0:
            label = 'positive'
        elif avg_score >= 3.0:
            label = 'stable'
        elif avg_score >= 2.0:
            label = 'low'
        else:
            label = 'difficult'

        return {
            'domain': 'mood',
            'avg_score': round(avg_score, 1),
            'entry_count': len(moods),
            'label': label,
            'line': f"Mood trend: {label} (avg {avg_score:.1f}/5 from {len(moods)} entries, weak signal)",
        }
    except Exception as e:
        logger.debug("SA: mood trend unavailable: %s", e)
        return None


def _get_medication_adherence(user):
    """Get medication adherence rate using existing utility."""
    try:
        from apps.health.medicine_utils import calculate_medicine_adherence_rate
        rate = calculate_medicine_adherence_rate(user, days=7)
        if rate is None:
            return None  # No active medications or insufficient data
        return {
            'domain': 'medication',
            'adherence_rate': rate,
            'line': f"Medication adherence: {rate}% (7-day)",
        }
    except Exception as e:
        logger.debug("SA: medication adherence unavailable: %s", e)
        return None


def _get_fatigue_signals(user):
    """
    Scan recent user messages for fatigue/distress keywords.
    ONLY scans user-authored messages to prevent feedback loops.
    Counts at conversation level to avoid over-counting.
    """
    try:
        from apps.ai.models import AssistantMessage
        cutoff = timezone.now() - timedelta(days=14)

        user_messages = (
            AssistantMessage.objects.filter(
                conversation__user=user,
                role='user',  # Only user messages — never assistant/system
                created_at__gte=cutoff,
            )
            .values('conversation_id', 'content')
        )

        # Group by conversation to count at conversation level
        conversations_with_fatigue = set()
        conversations_with_distress = set()
        all_conversation_ids = set()

        for msg in user_messages:
            conv_id = msg['conversation_id']
            all_conversation_ids.add(conv_id)
            content_lower = msg['content'].lower()

            if any(kw in content_lower for kw in FATIGUE_KEYWORDS):
                conversations_with_fatigue.add(conv_id)
            if any(kw in content_lower for kw in DISTRESS_KEYWORDS):
                conversations_with_distress.add(conv_id)

        total_conversations = len(all_conversation_ids)
        if total_conversations == 0:
            return None

        fatigue_count = len(conversations_with_fatigue)
        distress_count = len(conversations_with_distress)

        # Determine emotional context level
        if distress_count >= 2:
            emotional_context = 'distress'
            line = (
                f"Emotional context: user has expressed distress-related "
                f"language in {distress_count} recent conversations"
            )
        elif fatigue_count >= 2:
            emotional_context = 'fatigue'
            line = (
                f"Fatigue signal: mentioned tiredness/fatigue in "
                f"{fatigue_count} of {total_conversations} recent conversations"
            )
        else:
            return None  # Not enough signal to flag

        return {
            'emotional_context': emotional_context,
            'fatigue_count': fatigue_count,
            'distress_count': distress_count,
            'total_conversations': total_conversations,
            'line': line,
        }
    except Exception as e:
        logger.debug("SA: fatigue signal scan unavailable: %s", e)
        return None


def _get_goal_streaks(user):
    """Get streak data for top active goals."""
    try:
        from apps.purpose.models import HabitGoal
        from apps.purpose.services.streak_service import get_streak_data

        active_goals = (
            HabitGoal.objects.filter(
                user=user,
                status='active',
            )
            .order_by('-end_date')[:5]
        )

        streak_lines = []
        for goal in active_goals:
            try:
                streak = get_streak_data(goal)
                if streak.current > 0:
                    risk_note = " (at risk)" if streak.at_risk else ""
                    streak_lines.append(
                        f"  {goal.name}: {streak.current}-day streak{risk_note}"
                    )
                elif streak.longest > 0:
                    streak_lines.append(
                        f"  {goal.name}: streak broken (longest was {streak.longest} days)"
                    )
            except Exception:
                continue

        if not streak_lines:
            return None

        return {
            'domain': 'goal_streaks',
            'lines': streak_lines,
            'line': "Goal streaks:\n" + "\n".join(streak_lines),
        }
    except Exception as e:
        logger.debug("SA: goal streaks unavailable: %s", e)
        return None


# =============================================================================
# PUBLIC API
# =============================================================================


def build_situational_awareness(user) -> dict:
    """
    Build compact situational awareness summary from recent behavioral data.

    Returns a structured dict with pattern lines, momentum/drift signals,
    one-off sensitive domains, and emotional context.
    All computations are deterministic (DB queries + math, no LLM calls).

    Args:
        user: Django User instance.

    Returns:
        dict with keys: lines, momentum_signals, drift_signals,
        one_off_sensitive_domains, emotional_context.
    """
    result = {
        'lines': [],
        'momentum_signals': [],
        'drift_signals': [],
        'one_off_sensitive_domains': [],
        'emotional_context': 'none',
    }

    try:
        from apps.core.utils import get_user_today
        today = get_user_today(user)
    except Exception:
        today = timezone.now().date()

    # ── 1. Workout consistency ──
    workout = _get_workout_pattern(user, today)
    if workout:
        result['lines'].append(workout['line'])
        if workout['classification'] == 'consistent':
            result['momentum_signals'].append('workout')
            result['one_off_sensitive_domains'].append('workout')
        elif workout['classification'] == 'slipping':
            # Accountability only if workout goal exists
            if _has_proven_priority(user, WORKOUT_KEYWORDS):
                result['drift_signals'].append('workout')

    # ── 2. Weight tracking ──
    weight = _get_weight_tracking_pattern(user, today)
    if weight:
        result['lines'].append(weight['line'])
        if weight['classification'] == 'consistent':
            result['momentum_signals'].append('weight_tracking')
            result['one_off_sensitive_domains'].append('weight_tracking')
        elif weight['classification'] == 'slipping':
            result['drift_signals'].append('weight_tracking')

    # ── 3. Journal consistency ──
    journal = _get_journal_pattern(user, today)
    if journal:
        result['lines'].append(journal['line'])
        if journal['classification'] == 'consistent':
            result['momentum_signals'].append('journaling')
            result['one_off_sensitive_domains'].append('journaling')
        elif journal['classification'] == 'slipping':
            if journal.get('has_proven_priority'):
                result['drift_signals'].append('journaling')

    # ── 4. Mood trend (weak signal) ──
    mood = _get_mood_trend(user, today)
    if mood:
        result['lines'].append(mood['line'])

    # ── 5. Medication adherence ──
    meds = _get_medication_adherence(user)
    if meds:
        result['lines'].append(meds['line'])
        if meds['adherence_rate'] >= 85:
            result['momentum_signals'].append('medication')
        elif meds['adherence_rate'] < 60:
            result['drift_signals'].append('medication')

    # ── 6. Fatigue / distress signals ──
    fatigue = _get_fatigue_signals(user)
    if fatigue:
        result['lines'].append(fatigue['line'])
        result['emotional_context'] = fatigue['emotional_context']

    # ── 7. Goal streaks ──
    streaks = _get_goal_streaks(user)
    if streaks:
        result['lines'].append(streaks['line'])

    return result


def format_situational_awareness_injection(sa_data: dict) -> str:
    """
    Format the SA dict into a compact LLM-ready context block.

    Returns empty string if no meaningful data available.

    Args:
        sa_data: dict from build_situational_awareness().

    Returns:
        Formatted string for injection into CoS system prompt.
    """
    if not sa_data or not sa_data.get('lines'):
        return ''

    lines = []
    lines.append("=== SITUATIONAL AWARENESS SUMMARY (v8) ===")
    lines.append("Recent behavioral patterns (deterministic, from database):")
    lines.append("")

    for data_line in sa_data['lines']:
        lines.append(f"- {data_line}")

    lines.append("")

    # Momentum / drift / one-off labels
    momentum = sa_data.get('momentum_signals', [])
    drift = sa_data.get('drift_signals', [])
    one_off = sa_data.get('one_off_sensitive_domains', [])
    emotional = sa_data.get('emotional_context', 'none')

    if momentum:
        lines.append(f"MOMENTUM: {', '.join(momentum)}")
    if drift:
        lines.append(
            f"DRIFT: {', '.join(drift)} "
            f"(proven priority — accountability appropriate)"
        )
    if one_off:
        lines.append(
            f"ONE-OFF SENSITIVE: {', '.join(one_off)} "
            f"(recently consistent — single miss = gentle nudge)"
        )
    if emotional != 'none':
        lines.append(
            f"EMOTIONAL CONTEXT: {emotional} signals detected — "
            f"reduce pressure, prioritize care"
        )

    lines.append("")
    lines.append("PATTERN-AWARE GUIDANCE RULES:")
    lines.append(
        "1. MOMENTUM domains: reinforce consistency, "
        "do NOT recommend as new improvements"
    )
    lines.append(
        "2. DRIFT in proven-priority domains: accountability nudge, "
        "recommend recommit or deprioritize"
    )
    lines.append(
        "3. ONE-OFF SENSITIVE: if domain is recently consistent but "
        "incomplete today, frame as 'not yet completed' — gentle nudge, "
        "never failure"
    )
    lines.append(
        "4. CORE DISCIPLINE: workout = non-negotiable. "
        "Bike ride = optional extra. Protect core first."
    )
    lines.append(
        "5. EMOTIONAL CONTEXT distress: reduce pressure, "
        "prioritize care and stability"
    )
    lines.append(
        "6. Mood trend is a WEAK signal — "
        "do not anchor major guidance on it alone"
    )
    lines.append("=== END SITUATIONAL AWARENESS ===")

    return "\n".join(lines)
