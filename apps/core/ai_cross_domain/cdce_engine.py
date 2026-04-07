"""
CDCE — Cross-Domain Correlation Engine.

Post-execution engine (Phase 3) that discovers statistically significant
relationships between metrics across different life domains.

Examples of correlations CDCE can detect:
  - Sleep < 6.5h → negative mood the next day 78% of the time
  - Fasting compliance drops → workout consistency drops within 3 days
  - Journal entry frequency drops → faith reading streak breaks
  - High habit streak → positive mood distribution

Runs on 6-hour cadence via ISE scheduler.
Uses SAE state snapshots + historical data for statistical analysis.

Project: Whole Life Journey
Path: apps/core/ai_cross_domain/cdce_engine.py
"""

import datetime
import logging

from django.utils import timezone

from apps.core.ai_observability.instrumentation import (
    log_engine_run as _instrument_engine_run,
    log_engine_span,
)

logger = logging.getLogger(__name__)

# Minimum data points to consider a correlation valid
MIN_DATA_POINTS = 7

# Minimum co-occurrence ratio to report
MIN_WEAK_THRESHOLD = 0.30
MIN_MODERATE_THRESHOLD = 0.50
MIN_STRONG_THRESHOLD = 0.70


def _classify_strength(score):
    """Classify correlation strength from a 0-1 score."""
    if score >= MIN_STRONG_THRESHOLD:
        return "strong"
    if score >= MIN_MODERATE_THRESHOLD:
        return "moderate"
    if score >= MIN_WEAK_THRESHOLD:
        return "weak"
    return None  # Below threshold — not reportable


@_instrument_engine_run("CDCE", 3)
def run_cdce(user):
    """
    Main entry point for Cross-Domain Correlation Engine.

    Collects domain signals, runs correlation detectors, stores
    new/updated DomainCorrelation records with deduplication.

    Args:
        user: Django User instance.

    Returns:
        list of DomainCorrelation instances created or updated.
    """
    results = []

    # Collect signals from all domains
    signals = _collect_domain_signals(user)
    if not signals:
        return results

    # Run each detector
    for detector in CORRELATION_DETECTORS:
        try:
            correlations = detector(user, signals)
            if correlations:
                for corr_data in correlations:
                    obj = _store_correlation(user, corr_data)
                    if obj:
                        results.append(obj)
        except Exception as e:
            logger.warning(
                "CDCE: Detector %s failed for user %s: %s",
                getattr(detector, '__name__', '?'), user.id, e,
            )

    if results:
        logger.info(
            "CDCE: Found %d correlation(s) for user %s",
            len(results), user.id,
        )
    return results


@log_engine_span("CDCE", "collect_domain_signals")
def _collect_domain_signals(user):
    """
    Collect cross-domain signals from SAE state + direct queries.

    Returns a dict of domain data or None if insufficient data exists.
    """
    try:
        from apps.core.ai_state.state_engine import get_user_state
        state = get_user_state(user)
    except Exception as e:
        logger.warning("CDCE: SAE state unavailable for user %s: %s", user.id, e)
        return None

    if not state:
        return None

    # Enrich with historical series that SAE doesn't carry
    signals = {
        'health': state.get('health', {}),
        'goals': state.get('goals', {}),
        'habits': state.get('habits', {}),
        'journal': state.get('journal', {}),
        'faith': state.get('faith', {}),
        'nutrition': state.get('nutrition', {}),
        'fasting': state.get('fasting', {}),
        'fitness': state.get('fitness', {}),
        'transformation': state.get('transformation', {}),
    }

    # Pull historical sleep/mood series for time-lagged correlation
    signals['_sleep_mood_series'] = _build_sleep_mood_series(user)
    signals['_exercise_mood_series'] = _build_exercise_mood_series(user)

    return signals


# =========================================================================
# HISTORICAL SERIES BUILDERS
# =========================================================================

def _build_sleep_mood_series(user, lookback_days=30):
    """
    Build aligned daily series of (sleep_hours, next_day_mood_score).

    Returns list of dicts: [{'date': date, 'sleep_hours': float, 'mood_score': int}, ...]
    Mood score: 5=great, 4=good, 3=neutral/okay, 2=bad/low, 1=terrible
    """
    series = []
    try:
        from apps.health.models import SleepEntry
        from apps.journal.models import JournalEntry

        cutoff = timezone.now().date() - datetime.timedelta(days=lookback_days)

        # Sleep entries indexed by date
        sleep_by_date = {}
        sleeps = SleepEntry.objects.filter(
            user=user, recorded_at__date__gte=cutoff,
        ).values('recorded_at__date', 'hours')
        for s in sleeps:
            d = s['recorded_at__date']
            sleep_by_date[d] = s['hours']

        # Journal mood indexed by date
        mood_map = _get_mood_score_map()
        mood_by_date = {}
        entries = JournalEntry.objects.filter(
            user=user, created_at__date__gte=cutoff,
        ).exclude(mood='').values('created_at__date', 'mood')
        for e in entries:
            d = e['created_at__date']
            score = mood_map.get(e['mood'].lower(), 0)
            if score > 0:
                mood_by_date[d] = score

        # Align: sleep on day N → mood on day N+1
        for sleep_date, sleep_hours in sleep_by_date.items():
            next_day = sleep_date + datetime.timedelta(days=1)
            if next_day in mood_by_date:
                series.append({
                    'date': sleep_date,
                    'sleep_hours': float(sleep_hours),
                    'mood_score': mood_by_date[next_day],
                })
    except Exception as e:
        logger.debug("CDCE: sleep_mood_series build failed: %s", e)

    return series


def _build_exercise_mood_series(user, lookback_days=30):
    """
    Build aligned daily series of (exercised_bool, next_day_mood_score).

    Returns list of dicts: [{'date': date, 'exercised': bool, 'mood_score': int}, ...]
    """
    series = []
    try:
        from apps.health.models import Workout
        from apps.journal.models import JournalEntry

        cutoff = timezone.now().date() - datetime.timedelta(days=lookback_days)

        # Workout days
        workout_dates = set(
            Workout.objects.filter(
                user=user, date__gte=cutoff,
            ).values_list('date', flat=True).distinct()
        )

        # Journal mood indexed by date
        mood_map = _get_mood_score_map()
        mood_by_date = {}
        entries = JournalEntry.objects.filter(
            user=user, created_at__date__gte=cutoff,
        ).exclude(mood='').values('created_at__date', 'mood')
        for e in entries:
            d = e['created_at__date']
            score = mood_map.get(e['mood'].lower(), 0)
            if score > 0:
                mood_by_date[d] = score

        # Align: exercise on day N → mood on day N+1
        all_dates = set()
        all_dates.update(workout_dates)
        # Include non-workout dates too for comparison
        for d in mood_by_date:
            prev = d - datetime.timedelta(days=1)
            if prev >= cutoff:
                all_dates.add(prev)

        for d in sorted(all_dates):
            next_day = d + datetime.timedelta(days=1)
            if next_day in mood_by_date:
                series.append({
                    'date': d,
                    'exercised': d in workout_dates,
                    'mood_score': mood_by_date[next_day],
                })
    except Exception as e:
        logger.debug("CDCE: exercise_mood_series build failed: %s", e)

    return series


def _get_mood_score_map():
    """Map mood strings to numeric scores (5=best, 1=worst)."""
    return {
        'great': 5, 'amazing': 5, 'wonderful': 5, 'excellent': 5,
        'good': 4, 'happy': 4, 'positive': 4, 'blessed': 4,
        'okay': 3, 'neutral': 3, 'fine': 3, 'alright': 3,
        'bad': 2, 'low': 2, 'down': 2, 'sad': 2, 'stressed': 2,
        'terrible': 1, 'awful': 1, 'horrible': 1, 'depressed': 1,
    }


# =========================================================================
# CORRELATION DETECTORS
# =========================================================================

def detect_sleep_mood(user, signals):
    """
    Detect: Low sleep → negative mood the next day.

    Uses time-lagged alignment (sleep day N → mood day N+1).
    """
    series = signals.get('_sleep_mood_series', [])
    if len(series) < MIN_DATA_POINTS:
        return []

    # Split into low-sleep and normal-sleep groups
    low_sleep_moods = [s['mood_score'] for s in series if s['sleep_hours'] < 6.5]
    normal_sleep_moods = [s['mood_score'] for s in series if s['sleep_hours'] >= 6.5]

    if len(low_sleep_moods) < 3 or len(normal_sleep_moods) < 3:
        return []

    avg_low = sum(low_sleep_moods) / len(low_sleep_moods)
    avg_normal = sum(normal_sleep_moods) / len(normal_sleep_moods)

    # Calculate co-occurrence: what % of low-sleep days have mood <= 3 (neutral or worse)?
    negative_after_low = sum(1 for m in low_sleep_moods if m <= 3)
    co_occurrence = negative_after_low / len(low_sleep_moods)

    strength = _classify_strength(co_occurrence)
    if not strength:
        return []

    direction = "inverse" if avg_low < avg_normal else "positive"

    return [{
        'domain_a': 'health',
        'domain_b': 'journal',
        'correlation_type': 'sleep_mood',
        'strength': strength,
        'strength_score': round(co_occurrence, 3),
        'direction': direction,
        'narrative': (
            f"When sleep drops below 6.5h, mood is negative the next day "
            f"{co_occurrence:.0%} of the time "
            f"(avg mood {avg_low:.1f}/5 vs {avg_normal:.1f}/5 after normal sleep)."
        ),
        'evidence_summary': (
            f"{negative_after_low} of {len(low_sleep_moods)} low-sleep days "
            f"had neutral-or-worse mood the next day."
        ),
        'evidence': {
            'low_sleep_days': len(low_sleep_moods),
            'normal_sleep_days': len(normal_sleep_moods),
            'avg_mood_after_low': round(avg_low, 2),
            'avg_mood_after_normal': round(avg_normal, 2),
            'co_occurrence_rate': round(co_occurrence, 3),
        },
        'data_points': len(series),
        'window_label': '30d',
    }]


def detect_exercise_mood(user, signals):
    """
    Detect: Exercise → improved mood the next day.

    Compares mood scores after exercise days vs rest days.
    """
    series = signals.get('_exercise_mood_series', [])
    if len(series) < MIN_DATA_POINTS:
        return []

    exercise_moods = [s['mood_score'] for s in series if s['exercised']]
    rest_moods = [s['mood_score'] for s in series if not s['exercised']]

    if len(exercise_moods) < 3 or len(rest_moods) < 3:
        return []

    avg_exercise = sum(exercise_moods) / len(exercise_moods)
    avg_rest = sum(rest_moods) / len(rest_moods)

    # Co-occurrence: what % of exercise days have mood >= 4 (good or better)?
    positive_after_exercise = sum(1 for m in exercise_moods if m >= 4)
    co_occurrence = positive_after_exercise / len(exercise_moods)

    strength = _classify_strength(co_occurrence)
    if not strength:
        return []

    return [{
        'domain_a': 'health',
        'domain_b': 'journal',
        'correlation_type': 'exercise_mood',
        'strength': strength,
        'strength_score': round(co_occurrence, 3),
        'direction': 'positive',
        'narrative': (
            f"After exercise days, mood is positive the next day "
            f"{co_occurrence:.0%} of the time "
            f"(avg mood {avg_exercise:.1f}/5 vs {avg_rest:.1f}/5 after rest days)."
        ),
        'evidence_summary': (
            f"{positive_after_exercise} of {len(exercise_moods)} exercise days "
            f"had good-or-better mood the next day."
        ),
        'evidence': {
            'exercise_days': len(exercise_moods),
            'rest_days': len(rest_moods),
            'avg_mood_after_exercise': round(avg_exercise, 2),
            'avg_mood_after_rest': round(avg_rest, 2),
            'co_occurrence_rate': round(co_occurrence, 3),
        },
        'data_points': len(series),
        'window_label': '30d',
    }]


def detect_habit_goal_alignment(user, signals):
    """
    Detect: High habit consistency → better goal completion rate.

    Compares habit completion rate to goal milestone completion rate.
    """
    habits = signals.get('habits', {})
    goals = signals.get('goals', {})

    habit_rate = habits.get('avg_completion_rate', 0)
    goal_rate = goals.get('completion_rate', 0)
    active_goals = goals.get('active_goal_count', 0)
    active_habits = habits.get('active_habit_count', 0)

    # Need both domains to have meaningful data
    if active_habits < 1 or active_goals < 1:
        return []
    if habit_rate == 0 and goal_rate == 0:
        return []

    # Check if both are high (positive correlation) or if one is high and other low
    both_high = habit_rate >= 0.7 and goal_rate >= 0.5
    both_low = habit_rate < 0.4 and goal_rate < 0.3
    habit_high_goal_low = habit_rate >= 0.7 and goal_rate < 0.3

    if both_high:
        score = min(habit_rate, goal_rate)
        strength = _classify_strength(score)
        if not strength:
            return []
        return [{
            'domain_a': 'purpose',
            'domain_b': 'purpose',
            'correlation_type': 'habit_goal_alignment',
            'strength': strength,
            'strength_score': round(score, 3),
            'direction': 'positive',
            'narrative': (
                f"Your habit consistency ({habit_rate:.0%}) is driving goal progress "
                f"({goal_rate:.0%} milestones completed). The discipline is paying off."
            ),
            'evidence_summary': (
                f"Habit rate {habit_rate:.0%} with goal completion {goal_rate:.0%} "
                f"across {active_goals} active goal(s)."
            ),
            'evidence': {
                'habit_completion_rate': round(habit_rate, 3),
                'goal_completion_rate': round(goal_rate, 3),
                'active_habits': active_habits,
                'active_goals': active_goals,
            },
            'data_points': active_habits + active_goals,
            'window_label': 'current',
        }]
    elif both_low:
        score = 1.0 - max(habit_rate, goal_rate)  # Inverse — how consistently both are low
        strength = _classify_strength(score)
        if not strength:
            return []
        return [{
            'domain_a': 'purpose',
            'domain_b': 'purpose',
            'correlation_type': 'habit_goal_alignment',
            'strength': strength,
            'strength_score': round(score, 3),
            'direction': 'positive',
            'narrative': (
                f"Both habit consistency ({habit_rate:.0%}) and goal progress "
                f"({goal_rate:.0%}) are low. Rebuilding daily habits may unlock "
                f"goal momentum."
            ),
            'evidence_summary': (
                f"Habit rate {habit_rate:.0%} with goal completion {goal_rate:.0%} — "
                f"both below threshold."
            ),
            'evidence': {
                'habit_completion_rate': round(habit_rate, 3),
                'goal_completion_rate': round(goal_rate, 3),
                'active_habits': active_habits,
                'active_goals': active_goals,
            },
            'data_points': active_habits + active_goals,
            'window_label': 'current',
        }]

    return []


def detect_faith_consistency(user, signals):
    """
    Detect: Faith practice consistency correlates with journaling mood.

    When faith reading streak is high, mood distribution tends positive.
    """
    faith = signals.get('faith', {})
    journal = signals.get('journal', {})

    reading_streak = faith.get('reading_streak', 0)
    mood_dist = journal.get('mood_distribution', {})

    if reading_streak < 3 and not mood_dist:
        return []

    # Calculate positive mood ratio
    total_moods = sum(mood_dist.values()) if mood_dist else 0
    if total_moods < 5:
        return []

    mood_map = _get_mood_score_map()
    positive_moods = 0
    for mood_str, count in mood_dist.items():
        score = mood_map.get(mood_str.lower(), 0)
        if score >= 4:
            positive_moods += count

    positive_ratio = positive_moods / total_moods

    # Strong faith practice + positive moods
    if reading_streak >= 7 and positive_ratio >= 0.5:
        score = min(positive_ratio, reading_streak / 14)  # Cap at 14-day streak
        score = min(score, 1.0)
        strength = _classify_strength(score)
        if not strength:
            return []
        return [{
            'domain_a': 'faith',
            'domain_b': 'journal',
            'correlation_type': 'faith_mood',
            'strength': strength,
            'strength_score': round(score, 3),
            'direction': 'positive',
            'narrative': (
                f"Your {reading_streak}-day faith reading streak coincides with "
                f"{positive_ratio:.0%} positive mood entries. Spiritual consistency "
                f"appears connected to emotional well-being."
            ),
            'evidence_summary': (
                f"{positive_moods} of {total_moods} mood entries are positive "
                f"during a {reading_streak}-day reading streak."
            ),
            'evidence': {
                'reading_streak': reading_streak,
                'positive_moods': positive_moods,
                'total_moods': total_moods,
                'positive_ratio': round(positive_ratio, 3),
            },
            'data_points': total_moods,
            'window_label': '30d',
        }]

    # Broken faith practice + negative moods
    days_since = faith.get('days_since_reading', 0)
    if days_since >= 5 and positive_ratio < 0.3:
        score = min((1.0 - positive_ratio), days_since / 14)
        score = min(score, 1.0)
        strength = _classify_strength(score)
        if not strength:
            return []
        return [{
            'domain_a': 'faith',
            'domain_b': 'journal',
            'correlation_type': 'faith_mood',
            'strength': strength,
            'strength_score': round(score, 3),
            'direction': 'positive',
            'narrative': (
                f"Faith practice has been inactive for {days_since} days, and only "
                f"{positive_ratio:.0%} of mood entries are positive. "
                f"Resuming scripture reading may help emotional outlook."
            ),
            'evidence_summary': (
                f"Only {positive_moods} of {total_moods} mood entries are positive "
                f"with {days_since} days since last reading."
            ),
            'evidence': {
                'days_since_reading': days_since,
                'positive_moods': positive_moods,
                'total_moods': total_moods,
                'positive_ratio': round(positive_ratio, 3),
            },
            'data_points': total_moods,
            'window_label': '30d',
        }]

    return []


def detect_fasting_fitness(user, signals):
    """
    Detect: Fasting compliance and workout consistency co-vary.

    When fasting adherence drops, workout consistency often follows.

    Domain gate: this detector is silently a no-op when fasting is not enabled
    for the user OR fasting compliance is unknown (None). Defaulting missing
    fasting scores to 0 caused false "fasting 0% / workout 43% have dropped"
    correlations for users who never fasted.
    """
    fasting = signals.get('fasting', {})
    fitness = signals.get('fitness', {})

    # Hard gate: skip entirely if fasting is disabled for this user.
    if not fasting.get('enabled', False):
        return []

    fasting_score = fasting.get('fasting_compliance_score')  # may be None
    workout_score = fitness.get('workout_consistency_score')  # may be None
    workouts_7d = fitness.get('workouts_7d', 0)
    fasts_7d = fasting.get('fasts_7d', 0)

    # Both signals must be present (not None) AND have actual activity behind
    # them to be eligible for correlation. None means "unknown" — never "0%".
    if fasting_score is None or workout_score is None:
        return []
    if fasts_7d == 0 or workouts_7d == 0:
        return []

    # Both high — positive correlation
    if fasting_score >= 70 and workout_score >= 80:
        score = min(fasting_score, workout_score) / 100
        strength = _classify_strength(score)
        if not strength:
            return []
        return [{
            'domain_a': 'health',
            'domain_b': 'health',
            'correlation_type': 'fasting_fitness',
            'strength': strength,
            'strength_score': round(score, 3),
            'direction': 'positive',
            'narrative': (
                f"Fasting compliance ({fasting_score:.0f}%) and workout consistency "
                f"({workout_score:.0f}%) are both strong. Your physical discipline "
                f"protocols are reinforcing each other."
            ),
            'evidence_summary': (
                f"Fasting {fasting_score:.0f}% compliance with {fasts_7d} fasts "
                f"and {workouts_7d} workouts this week."
            ),
            'evidence': {
                'fasting_compliance': round(fasting_score, 1),
                'workout_consistency': round(workout_score, 1),
                'fasts_7d': fasts_7d,
                'workouts_7d': workouts_7d,
            },
            'data_points': fasts_7d + workouts_7d,
            'window_label': '7d',
        }]

    # Both dropping — warning correlation. Both fasts_7d and workouts_7d are
    # already guaranteed > 0 above, so the previous OR-clause is removed.
    if fasting_score < 40 and workout_score < 50:
        score = 1.0 - (max(fasting_score, workout_score) / 100)
        strength = _classify_strength(score)
        if not strength:
            return []
        return [{
            'domain_a': 'health',
            'domain_b': 'health',
            'correlation_type': 'fasting_fitness',
            'strength': strength,
            'strength_score': round(score, 3),
            'direction': 'positive',
            'narrative': (
                f"Both fasting ({fasting_score:.0f}%) and workout consistency "
                f"({workout_score:.0f}%) have dropped. These protocols tend to "
                f"decline together — focusing on one may restore the other."
            ),
            'evidence_summary': (
                f"Fasting {fasting_score:.0f}% and workout {workout_score:.0f}% — "
                f"both below threshold."
            ),
            'evidence': {
                'fasting_compliance': round(fasting_score, 1),
                'workout_consistency': round(workout_score, 1),
                'fasts_7d': fasts_7d,
                'workouts_7d': workouts_7d,
            },
            'data_points': fasts_7d + workouts_7d,
            'window_label': '7d',
        }]

    return []


def detect_nutrition_energy(user, signals):
    """
    Detect: Nutrition compliance correlates with transformation momentum.

    When macro compliance drops, overall transformation score follows.
    """
    nutrition = signals.get('nutrition', {})
    transformation = signals.get('transformation', {})

    macro_score = nutrition.get('macro_compliance_score', 0)
    transform_score = transformation.get('transformation_score', 0)
    food_entries_7d = nutrition.get('food_entries_7d', 0)

    if food_entries_7d < 3:
        return []
    if macro_score == 0 and transform_score == 0:
        return []

    # Both strong — nutrition is fueling transformation
    if macro_score >= 70 and transform_score >= 60:
        score = min(macro_score, transform_score) / 100
        strength = _classify_strength(score)
        if not strength:
            return []
        return [{
            'domain_a': 'health',
            'domain_b': 'health',
            'correlation_type': 'nutrition_transformation',
            'strength': strength,
            'strength_score': round(score, 3),
            'direction': 'positive',
            'narrative': (
                f"Nutrition compliance ({macro_score:.0f}%) is supporting your "
                f"transformation score ({transform_score}/100). Stay consistent."
            ),
            'evidence_summary': (
                f"Macro compliance {macro_score:.0f}% with transformation score "
                f"{transform_score}/100 from {food_entries_7d} tracked meals this week."
            ),
            'evidence': {
                'macro_compliance': round(macro_score, 1),
                'transformation_score': transform_score,
                'food_entries_7d': food_entries_7d,
            },
            'data_points': food_entries_7d,
            'window_label': '7d',
        }]

    # Nutrition dropped — transformation struggling
    if macro_score < 40 and transform_score < 40 and food_entries_7d >= 3:
        score = 1.0 - (max(macro_score, transform_score) / 100)
        strength = _classify_strength(score)
        if not strength:
            return []
        return [{
            'domain_a': 'health',
            'domain_b': 'health',
            'correlation_type': 'nutrition_transformation',
            'strength': strength,
            'strength_score': round(score, 3),
            'direction': 'positive',
            'narrative': (
                f"Nutrition compliance ({macro_score:.0f}%) and transformation score "
                f"({transform_score}/100) are both low. Nutrition is often the "
                f"keystone — fixing it tends to lift everything else."
            ),
            'evidence_summary': (
                f"Macro compliance {macro_score:.0f}% with transformation score "
                f"{transform_score}/100."
            ),
            'evidence': {
                'macro_compliance': round(macro_score, 1),
                'transformation_score': transform_score,
                'food_entries_7d': food_entries_7d,
            },
            'data_points': food_entries_7d,
            'window_label': '7d',
        }]

    return []


def detect_momentum_engagement(user, signals):
    """
    Detect: Multi-domain engagement (momentum) correlates with mood.

    When the user is active across many domains, mood tends positive.
    """
    transformation = signals.get('transformation', {})
    journal = signals.get('journal', {})

    momentum = transformation.get('momentum_score', 0)
    mood_dist = journal.get('mood_distribution', {})
    total_moods = sum(mood_dist.values()) if mood_dist else 0

    if momentum == 0 or total_moods < 3:
        return []

    mood_map = _get_mood_score_map()
    positive_moods = 0
    for mood_str, count in mood_dist.items():
        score = mood_map.get(mood_str.lower(), 0)
        if score >= 4:
            positive_moods += count

    positive_ratio = positive_moods / total_moods if total_moods else 0

    # High momentum + positive mood
    if momentum >= 60 and positive_ratio >= 0.5:
        score = min(momentum / 100, positive_ratio)
        strength = _classify_strength(score)
        if not strength:
            return []
        return [{
            'domain_a': 'health',
            'domain_b': 'journal',
            'correlation_type': 'momentum_mood',
            'strength': strength,
            'strength_score': round(score, 3),
            'direction': 'positive',
            'narrative': (
                f"Your multi-domain engagement (momentum {momentum}/100) "
                f"coincides with {positive_ratio:.0%} positive mood entries. "
                f"Staying active across domains supports overall well-being."
            ),
            'evidence_summary': (
                f"Momentum score {momentum}/100 with {positive_moods}/{total_moods} "
                f"positive mood entries."
            ),
            'evidence': {
                'momentum_score': momentum,
                'positive_moods': positive_moods,
                'total_moods': total_moods,
                'positive_ratio': round(positive_ratio, 3),
            },
            'data_points': total_moods,
            'window_label': '30d',
        }]

    return []


# Registry of all correlation detectors
CORRELATION_DETECTORS = [
    detect_sleep_mood,
    detect_exercise_mood,
    detect_habit_goal_alignment,
    detect_faith_consistency,
    detect_fasting_fitness,
    detect_nutrition_energy,
    detect_momentum_engagement,
]


# =========================================================================
# STORAGE
# =========================================================================

@log_engine_span("CDCE", "store_correlation")
def _store_correlation(user, corr_data):
    """
    Store or update a DomainCorrelation record with deduplication.

    If a correlation with the same dedupe_key already exists and is active,
    updates it. Otherwise creates a new one.

    Returns:
        DomainCorrelation instance or None on failure.
    """
    try:
        from apps.core.ai_cross_domain.models import (
            DomainCorrelation,
            build_correlation_dedupe_key,
        )
        from apps.core.ai_observability.instrumentation import record_decision

        dedupe_key = build_correlation_dedupe_key(
            user.id,
            corr_data['correlation_type'],
            corr_data.get('window_label', 'current'),
        )

        # Check for existing active correlation
        existing = DomainCorrelation.objects.filter(
            user=user,
            dedupe_key=dedupe_key,
            status='active',
        ).first()

        if existing:
            # Update if strength changed significantly
            old_score = existing.strength_score
            new_score = corr_data['strength_score']
            if abs(old_score - new_score) >= 0.05:
                existing.strength = corr_data['strength']
                existing.strength_score = new_score
                existing.narrative = corr_data['narrative']
                existing.evidence_summary = corr_data['evidence_summary']
                existing.evidence = corr_data.get('evidence', {})
                existing.data_points = corr_data.get('data_points', 0)
                existing.direction = corr_data.get('direction', 'positive')
                existing.save()
                logger.debug(
                    "CDCE: Updated correlation %s (%.3f → %.3f) for user %s",
                    corr_data['correlation_type'], old_score, new_score, user.id,
                )
                return existing
            # No significant change — skip
            return None

        # Create new correlation
        obj = DomainCorrelation.objects.create(
            user=user,
            domain_a=corr_data['domain_a'],
            domain_b=corr_data['domain_b'],
            correlation_type=corr_data['correlation_type'],
            strength=corr_data['strength'],
            strength_score=corr_data['strength_score'],
            direction=corr_data.get('direction', 'positive'),
            narrative=corr_data['narrative'],
            evidence_summary=corr_data['evidence_summary'],
            evidence=corr_data.get('evidence', {}),
            data_points=corr_data.get('data_points', 0),
            dedupe_key=dedupe_key,
            status='active',
        )

        # Record observability decision
        record_decision(
            engine_name="CDCE",
            decision_type="correlation_discovered",
            decision=f"NEW {corr_data['correlation_type']} [{corr_data['strength']}]",
            rationale=corr_data['evidence_summary'],
            inputs_summary={
                'domains': [corr_data['domain_a'], corr_data['domain_b']],
                'data_points': corr_data.get('data_points', 0),
            },
            user_id=user.id,
            confidence=corr_data['strength_score'],
        )

        # Proactive push for strong/moderate correlations via DNE
        if corr_data['strength'] in ('strong', 'moderate'):
            try:
                from apps.core.ai_delivery.delivery_engine import deliver_single
                deliver_single(user, "CDCE", obj)
            except Exception:
                pass  # Non-fatal — delivery is best-effort

        return obj

    except Exception as e:
        logger.warning(
            "CDCE: Failed to store correlation '%s' for user %s: %s",
            corr_data.get('correlation_type', '?'), user.id, e,
        )
        return None


# =========================================================================
# LIFECYCLE
# =========================================================================

def expire_stale_correlations(max_age_days=60):
    """
    Expire correlations that haven't been updated in max_age_days.

    Called by scheduler to keep the correlation set fresh.

    Returns:
        int — number of correlations expired.
    """
    try:
        from apps.core.ai_cross_domain.models import DomainCorrelation

        cutoff = timezone.now() - datetime.timedelta(days=max_age_days)
        expired = DomainCorrelation.objects.filter(
            status='active',
            updated_at__lt=cutoff,
        ).update(status='expired')

        if expired:
            logger.info("CDCE: Expired %d stale correlation(s)", expired)
        return expired
    except Exception as e:
        logger.warning("CDCE: Failed to expire stale correlations: %s", e)
        return 0
