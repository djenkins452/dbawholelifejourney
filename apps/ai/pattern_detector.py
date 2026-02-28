# ==============================================================================
# File: pattern_detector.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Cross-domain behavioral pattern detection for CoS. Analyzes
#              journal, health, tasks, and faith data to detect recurring
#              patterns and surface them for conversational awareness.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-28
# ==============================================================================
"""
CoS Behavioral Pattern Detection Service

Detects statistical patterns in user behavior across domains:
  - Time-of-day patterns (journaling at 10pm, exercising at 6am)
  - Adherence patterns (80% faith plan compliance, 40% exercise)
  - Emotional patterns (mood dips on specific days)
  - Frequency patterns (journals 5x/week, exercises 3x/week)
  - Correlation patterns (journals more when stressed about work)

Patterns are stored in BehavioralPattern model and injected into
CoS system prompt for conversational awareness.

Public API:
  - detect_patterns(user) -> list[BehavioralPattern]
  - get_pattern_context_block(user) -> str
  - confirm_pattern(user, pattern_id, confirmed) -> bool
"""

import logging
from collections import Counter, defaultdict
from datetime import timedelta
from typing import List, Optional

from django.db.models import Count
from django.utils import timezone

logger = logging.getLogger(__name__)

# Minimum data points for pattern detection
MIN_DATA_POINTS = 5
# Minimum consistency for a pattern to be considered
MIN_CONSISTENCY = 0.60
# How far back to look for patterns
LOOKBACK_DAYS = 56  # 8 weeks


def detect_patterns(user) -> list:
    """
    Run all pattern detectors for a user.

    Returns list of newly created or updated BehavioralPattern instances.
    """
    from .models import BehavioralPattern

    results = []

    try:
        results.extend(_detect_journal_time_patterns(user))
    except Exception as e:
        logger.debug("Journal time pattern detection failed: %s", e)

    try:
        results.extend(_detect_journal_frequency_patterns(user))
    except Exception as e:
        logger.debug("Journal frequency pattern detection failed: %s", e)

    try:
        results.extend(_detect_emotion_patterns(user))
    except Exception as e:
        logger.debug("Emotion pattern detection failed: %s", e)

    try:
        results.extend(_detect_task_patterns(user))
    except Exception as e:
        logger.debug("Task pattern detection failed: %s", e)

    try:
        results.extend(_detect_health_patterns(user))
    except Exception as e:
        logger.debug("Health pattern detection failed: %s", e)

    try:
        results.extend(_detect_faith_patterns(user))
    except Exception as e:
        logger.debug("Faith pattern detection failed: %s", e)

    return results


def get_pattern_context_block(user) -> str:
    """
    Build the system prompt injection block for active behavioral patterns.

    Returns empty string if no patterns detected.
    """
    from .models import BehavioralPattern

    patterns = BehavioralPattern.objects.filter(
        user=user,
        is_active=True,
        confidence__gte=0.5,
    ).exclude(
        user_confirmed=False,  # Exclude patterns the user denied
    ).order_by('-confidence')[:8]

    if not patterns:
        return ""

    confirmed_lines = []
    pending_lines = []

    for p in patterns:
        line = f"  [{p.get_domain_display()}] {p.description} (confidence: {round(p.confidence * 100)}%)"
        if p.user_confirmed is True:
            confirmed_lines.append(line)
        elif p.user_confirmed is None:
            pending_lines.append(line)

    blocks = []
    if confirmed_lines:
        blocks.append(
            "CONFIRMED BEHAVIORAL PATTERNS (user has verified these):\n"
            + "\n".join(confirmed_lines)
        )
    if pending_lines:
        blocks.append(
            "DETECTED PATTERNS (not yet confirmed — mention naturally when relevant, "
            "ask if the user recognizes the pattern):\n"
            + "\n".join(pending_lines)
        )

    if not blocks:
        return ""

    return "\n\n" + "\n\n".join(blocks) + "\n"


def confirm_pattern(user, pattern_id: int, confirmed: bool) -> bool:
    """
    Confirm or deny a detected pattern.

    When confirmed: boost confidence to 0.9.
    When denied: drop confidence to 0.2.
    """
    from .models import BehavioralPattern

    try:
        pattern = BehavioralPattern.objects.get(id=pattern_id, user=user)
        pattern.user_confirmed = confirmed
        if confirmed:
            pattern.confidence = max(pattern.confidence, 0.9)
        else:
            pattern.confidence = 0.2
            pattern.is_active = False
        pattern.save(update_fields=['user_confirmed', 'confidence', 'is_active', 'last_confirmed'])
        return True
    except BehavioralPattern.DoesNotExist:
        return False


# =============================================================================
# PATTERN DETECTORS (per domain)
# =============================================================================


def _detect_journal_time_patterns(user) -> list:
    """Detect what time of day the user typically journals."""
    from apps.journal.models import JournalEntry

    cutoff = timezone.now() - timedelta(days=LOOKBACK_DAYS)
    entries = JournalEntry.objects.filter(
        user=user,
        created_at__gte=cutoff,
        is_deleted=False,
    ).values_list('created_at', flat=True)

    if len(entries) < MIN_DATA_POINTS:
        return []

    # Bucket by hour
    hour_counts = Counter()
    for dt in entries:
        hour_counts[dt.hour] += 1

    total = sum(hour_counts.values())
    results = []

    # Find dominant time window (2-hour window)
    for hour in range(24):
        window_count = hour_counts.get(hour, 0) + hour_counts.get((hour + 1) % 24, 0)
        consistency = window_count / total if total > 0 else 0

        if consistency >= MIN_CONSISTENCY and window_count >= MIN_DATA_POINTS:
            # Format time range
            start_h = hour
            end_h = (hour + 2) % 24
            start = f"{start_h % 12 or 12}{'am' if start_h < 12 else 'pm'}"
            end = f"{end_h % 12 or 12}{'am' if end_h < 12 else 'pm'}"

            description = (
                f"You typically journal between {start} and {end} "
                f"({round(consistency * 100)}% of the time over the last "
                f"{LOOKBACK_DAYS // 7} weeks)."
            )

            results.append(_upsert_pattern(
                user=user,
                pattern_type='time_pattern',
                domain='journal',
                description=description,
                confidence=min(0.5 + consistency * 0.4, 0.95),
                evidence=[{
                    'hour_counts': dict(hour_counts),
                    'window': f"{start}-{end}",
                    'total_entries': total,
                }],
            ))
            break  # Only detect the strongest time pattern

    return [r for r in results if r]


def _detect_journal_frequency_patterns(user) -> list:
    """Detect journaling frequency patterns."""
    from apps.journal.models import JournalEntry

    cutoff = timezone.now() - timedelta(days=LOOKBACK_DAYS)
    dates = list(
        JournalEntry.objects.filter(
            user=user,
            created_at__gte=cutoff,
            is_deleted=False,
        ).values_list('entry_date', flat=True).distinct()
    )

    if len(dates) < MIN_DATA_POINTS:
        return []

    # Calculate entries per week
    weeks = LOOKBACK_DAYS // 7
    entries_per_week = len(dates) / weeks if weeks > 0 else 0

    results = []

    if entries_per_week >= 5:
        description = (
            f"You journal an average of {entries_per_week:.1f} times per week — "
            f"that's a strong daily habit."
        )
        confidence = min(0.6 + (entries_per_week / 7) * 0.3, 0.95)
    elif entries_per_week >= 3:
        description = (
            f"You journal about {entries_per_week:.1f} times per week over the "
            f"last {weeks} weeks."
        )
        confidence = 0.6
    else:
        description = (
            f"You journal about {entries_per_week:.1f} times per week. "
            f"Your most active days might show a pattern."
        )
        confidence = 0.5

    # Detect day-of-week patterns
    day_counts = Counter()
    for d in dates:
        day_counts[d.strftime('%A')] += 1

    most_common_day = day_counts.most_common(1)
    if most_common_day:
        day_name, count = most_common_day[0]
        day_pct = count / weeks if weeks > 0 else 0
        if day_pct >= 0.75:
            description += f" You almost always journal on {day_name}s."

    results.append(_upsert_pattern(
        user=user,
        pattern_type='frequency_pattern',
        domain='journal',
        description=description,
        confidence=confidence,
        evidence=[{
            'entries_per_week': round(entries_per_week, 1),
            'total_dates': len(dates),
            'weeks_analyzed': weeks,
            'day_counts': dict(day_counts),
        }],
    ))

    return [r for r in results if r]


def _detect_emotion_patterns(user) -> list:
    """Detect emotional patterns from journal entries."""
    from apps.journal.models import JournalEntry

    cutoff = timezone.now() - timedelta(days=LOOKBACK_DAYS)
    entries = JournalEntry.objects.filter(
        user=user,
        created_at__gte=cutoff,
        is_deleted=False,
    ).prefetch_related('emotions')

    if entries.count() < MIN_DATA_POINTS:
        return []

    # Count emotions
    emotion_counts = Counter()
    total_entries = 0
    for entry in entries:
        emotions = list(entry.emotions.values_list('name', flat=True))
        for emo in emotions:
            emotion_counts[emo] += 1
        if emotions:
            total_entries += 1

    if total_entries < MIN_DATA_POINTS:
        return []

    results = []

    # Top emotions
    top_emotions = emotion_counts.most_common(3)
    if top_emotions:
        emotions_str = ", ".join(
            f"{name} ({round(count / total_entries * 100)}%)"
            for name, count in top_emotions
        )
        description = (
            f"Your most common emotions over the last {LOOKBACK_DAYS // 7} weeks: "
            f"{emotions_str} (out of {total_entries} entries with emotions)."
        )

        results.append(_upsert_pattern(
            user=user,
            pattern_type='emotional_pattern',
            domain='journal',
            description=description,
            confidence=0.7,
            evidence=[{
                'emotion_counts': dict(emotion_counts),
                'total_entries_with_emotions': total_entries,
            }],
        ))

    return [r for r in results if r]


def _detect_task_patterns(user) -> list:
    """Detect task completion patterns."""
    results = []
    try:
        from apps.life.models import Task

        cutoff = timezone.now() - timedelta(days=LOOKBACK_DAYS)
        completed = Task.objects.filter(
            user=user,
            status='done',
            completed_at__gte=cutoff,
        ).values_list('completed_at', flat=True)

        if len(completed) < MIN_DATA_POINTS:
            return []

        # Detect time-of-day completion patterns
        hour_counts = Counter()
        for dt in completed:
            if dt:
                hour_counts[dt.hour] += 1

        total = sum(hour_counts.values())
        if total >= MIN_DATA_POINTS:
            # Find peak productivity window
            best_hour = hour_counts.most_common(1)[0][0] if hour_counts else 12
            window_count = hour_counts.get(best_hour, 0) + hour_counts.get((best_hour + 1) % 24, 0)
            consistency = window_count / total if total > 0 else 0

            if consistency >= 0.3 and window_count >= 3:
                start_h = best_hour
                end_h = (best_hour + 2) % 24
                start = f"{start_h % 12 or 12}{'am' if start_h < 12 else 'pm'}"
                end = f"{end_h % 12 or 12}{'am' if end_h < 12 else 'pm'}"

                description = (
                    f"Your peak task completion window is {start}–{end} "
                    f"({round(consistency * 100)}% of completions in the last "
                    f"{LOOKBACK_DAYS // 7} weeks)."
                )

                results.append(_upsert_pattern(
                    user=user,
                    pattern_type='time_pattern',
                    domain='tasks',
                    description=description,
                    confidence=min(0.5 + consistency * 0.3, 0.85),
                    evidence=[{
                        'hour_counts': dict(hour_counts),
                        'window': f"{start}-{end}",
                        'total_completions': total,
                    }],
                ))

    except ImportError:
        pass

    return [r for r in results if r]


def _detect_health_patterns(user) -> list:
    """Detect health-related patterns (exercise, weight, etc.)."""
    results = []
    try:
        from apps.health.models import WeightEntry

        cutoff = timezone.now().date() - timedelta(days=LOOKBACK_DAYS)
        weights = list(
            WeightEntry.objects.filter(
                user=user,
                date__gte=cutoff,
                is_deleted=False,
            ).order_by('date').values_list('weight', 'date')
        )

        if len(weights) >= MIN_DATA_POINTS:
            # Detect weight trend
            first_avg = sum(w for w, _ in weights[:3]) / 3
            last_avg = sum(w for w, _ in weights[-3:]) / 3
            diff = last_avg - first_avg

            if abs(diff) >= 1.0:  # At least 1 lb change
                direction = "decreasing" if diff < 0 else "increasing"
                description = (
                    f"Your weight has been {direction} over the last "
                    f"{LOOKBACK_DAYS // 7} weeks "
                    f"(from ~{first_avg:.1f} to ~{last_avg:.1f} lbs, "
                    f"a change of {diff:+.1f} lbs)."
                )

                results.append(_upsert_pattern(
                    user=user,
                    pattern_type='adherence_pattern',
                    domain='health',
                    description=description,
                    confidence=0.7,
                    evidence=[{
                        'first_avg': round(first_avg, 1),
                        'last_avg': round(last_avg, 1),
                        'diff': round(diff, 1),
                        'data_points': len(weights),
                    }],
                ))

    except (ImportError, Exception) as e:
        logger.debug("Health pattern detection skipped: %s", e)

    return [r for r in results if r]


def _detect_faith_patterns(user) -> list:
    """Detect faith-related patterns (reading plan adherence, etc.)."""
    results = []
    try:
        from apps.faith.models import ReadingPlanProgress

        cutoff = timezone.now().date() - timedelta(days=LOOKBACK_DAYS)
        progress = ReadingPlanProgress.objects.filter(
            user=user,
            completed_date__gte=cutoff,
        ).values_list('completed_date', flat=True)

        total_days = len(set(progress))
        weeks = LOOKBACK_DAYS // 7

        if total_days >= MIN_DATA_POINTS:
            days_per_week = total_days / weeks if weeks > 0 else 0
            adherence = min(days_per_week / 7, 1.0)

            description = (
                f"You complete your Bible reading plan about {days_per_week:.1f} "
                f"days per week ({round(adherence * 100)}% adherence over "
                f"{weeks} weeks)."
            )

            results.append(_upsert_pattern(
                user=user,
                pattern_type='adherence_pattern',
                domain='faith',
                description=description,
                confidence=0.65,
                evidence=[{
                    'days_per_week': round(days_per_week, 1),
                    'total_days': total_days,
                    'weeks': weeks,
                    'adherence_pct': round(adherence * 100),
                }],
            ))

    except (ImportError, Exception) as e:
        logger.debug("Faith pattern detection skipped: %s", e)

    return [r for r in results if r]


# =============================================================================
# HELPERS
# =============================================================================


def _upsert_pattern(
    user,
    pattern_type: str,
    domain: str,
    description: str,
    confidence: float,
    evidence: list,
) -> Optional['BehavioralPattern']:
    """
    Create or update a behavioral pattern.

    If a matching pattern exists (same user, type, domain), update it.
    Otherwise, create a new one.
    """
    from .models import BehavioralPattern

    try:
        existing = BehavioralPattern.objects.filter(
            user=user,
            pattern_type=pattern_type,
            domain=domain,
            is_active=True,
        ).first()

        if existing:
            # Update existing pattern
            existing.description = description
            existing.confidence = confidence
            existing.evidence = evidence
            existing.detection_count += 1
            existing.save(update_fields=[
                'description', 'confidence', 'evidence',
                'detection_count', 'last_confirmed',
            ])
            return existing
        else:
            # Create new pattern
            return BehavioralPattern.objects.create(
                user=user,
                pattern_type=pattern_type,
                domain=domain,
                description=description,
                confidence=confidence,
                evidence=evidence,
            )

    except Exception as e:
        logger.warning("Failed to upsert pattern: %s", e)
        return None
