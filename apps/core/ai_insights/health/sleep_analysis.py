# ==============================================================================
# File: sleep_analysis.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Deterministic sleep data analysis for PIE health interpretation.
#              Pure math against clinical reference ranges — no LLM calls.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-10
# ==============================================================================
"""
Sleep Analysis — Deterministic interpretation of sleep screenshot data.

Evaluates:
  1. Sleep duration adequacy (vs 7-9 hour range)
  2. Sleep stage distribution (REM, deep, core percentages)
  3. Sleep cycle completion (total / 90 min)
  4. User context connections (wake time, training, goals)

Returns structured analysis dict for CoS prompt injection.
Also registered as a PIE rule for event-driven execution.
"""

import logging

from apps.core.ai_insights.base_rules import BaseInsightRule
from apps.core.ai_insights.health.reference_ranges import (
    MEDICAL_DISCLAIMER,
    MIN_ACCEPTABLE_CYCLES,
    OPTIMAL_CYCLES,
    SLEEP_CYCLE_MINUTES,
    SLEEP_DURATION_MAX,
    SLEEP_DURATION_MILD_DEFICIT,
    SLEEP_DURATION_MIN,
    SLEEP_DURATION_SEVERE_DEFICIT,
    SLEEP_STAGES,
)
from apps.core.ai_insights.models import build_dedupe_key
from apps.core.ai_insights.rule_registry import register

logger = logging.getLogger(__name__)


# ── Standalone Analysis Function ─────────────────────────────────────

def analyze_sleep_data(parsed_data, user_context=None):
    """
    Analyze structured sleep data and return interpretation.

    Args:
        parsed_data: Dict from screenshot_parser with sleep_summary
                     and/or recent_sleep sections.
        user_context: Optional dict from get_health_user_context().

    Returns:
        Dict with: summary_insight, observations, implications,
        recommendation, severity, evidence.
        Returns None if insufficient data.
    """
    if not parsed_data:
        return None

    user_context = user_context or {}
    observations = []
    implications = []

    # Use summary data if available, fall back to recent_sleep
    sleep_data = parsed_data.get('sleep_summary') or parsed_data.get('recent_sleep')
    if not sleep_data:
        return None

    total_key = (
        'average_sleep_minutes' if 'average_sleep_minutes' in sleep_data
        else 'total_sleep_minutes'
    )
    total_minutes = sleep_data.get(total_key)
    if not total_minutes:
        return None

    # ── 1. Duration Assessment ───────────────────────────────────────
    hours = total_minutes / 60
    hours_str = f"{int(hours)}h {int(total_minutes % 60)}m"

    if total_minutes >= SLEEP_DURATION_MIN:
        duration_status = 'adequate'
        observations.append(
            f"Total sleep of {hours_str} is within the healthy "
            f"7-9 hour range"
        )
    elif total_minutes >= SLEEP_DURATION_MILD_DEFICIT:
        duration_status = 'mild_deficit'
        deficit = SLEEP_DURATION_MIN - total_minutes
        observations.append(
            f"Total sleep of {hours_str} is {deficit} minutes below the "
            f"recommended 7-hour minimum"
        )
    elif total_minutes >= SLEEP_DURATION_SEVERE_DEFICIT:
        duration_status = 'moderate_deficit'
        deficit = SLEEP_DURATION_MIN - total_minutes
        observations.append(
            f"Total sleep of {hours_str} shows a moderate deficit — "
            f"{deficit} minutes below the 7-hour minimum"
        )
    else:
        duration_status = 'severe_deficit'
        observations.append(
            f"Total sleep of {hours_str} is significantly below the "
            f"recommended 7-hour minimum"
        )

    # ── 2. Sleep Stage Distribution ──────────────────────────────────
    rem_key = 'average_rem_minutes' if 'average_rem_minutes' in sleep_data else 'rem_minutes'
    deep_key = 'average_deep_minutes' if 'average_deep_minutes' in sleep_data else 'deep_minutes'
    core_key = 'average_core_minutes' if 'average_core_minutes' in sleep_data else 'core_minutes'

    rem_min = sleep_data.get(rem_key)
    deep_min = sleep_data.get(deep_key)
    core_min = sleep_data.get(core_key)

    stage_analysis = {}
    if total_minutes > 0:
        for stage_name, minutes, ref_key in [
            ('REM', rem_min, 'rem'),
            ('Deep', deep_min, 'deep'),
            ('Core/Light', core_min, 'core'),
        ]:
            if minutes is not None:
                pct = round((minutes / total_minutes) * 100, 1)
                ref = SLEEP_STAGES[ref_key]
                stage_analysis[ref_key] = {
                    'minutes': minutes,
                    'pct': pct,
                    'ref_min': ref['min_pct'],
                    'ref_max': ref['max_pct'],
                }

                if pct < ref['min_pct']:
                    observations.append(
                        f"{stage_name} sleep at {pct}% is below the typical "
                        f"{ref['min_pct']}-{ref['max_pct']}% range "
                        f"({ref['function']})"
                    )
                elif pct > ref['max_pct']:
                    observations.append(
                        f"{stage_name} sleep at {pct}% is above the typical "
                        f"{ref['min_pct']}-{ref['max_pct']}% range"
                    )
                else:
                    observations.append(
                        f"{stage_name} sleep at {pct}% is within the optimal "
                        f"{ref['min_pct']}-{ref['max_pct']}% range"
                    )

    # ── 3. Sleep Cycle Completion ────────────────────────────────────
    cycles = round(total_minutes / SLEEP_CYCLE_MINUTES, 1)
    if cycles < MIN_ACCEPTABLE_CYCLES:
        observations.append(
            f"At {hours_str}, you're completing ~{cycles} sleep cycles "
            f"(optimal: {OPTIMAL_CYCLES} cycles of {SLEEP_CYCLE_MINUTES} min)"
        )
    elif cycles < OPTIMAL_CYCLES:
        observations.append(
            f"~{cycles} sleep cycles completed "
            f"(optimal: {OPTIMAL_CYCLES})"
        )

    # ── 4. User Context Connections ──────────────────────────────────
    wake_time = user_context.get('wake_time')
    if wake_time and duration_status != 'adequate':
        # Calculate recommended bedtime
        optimal_minutes = OPTIMAL_CYCLES * SLEEP_CYCLE_MINUTES  # 450 min
        wake_hour = int(wake_time.split(':')[0])
        wake_minute = int(wake_time.split(':')[1])
        total_wake = wake_hour * 60 + wake_minute
        ideal_bed = total_wake - optimal_minutes
        if ideal_bed < 0:
            ideal_bed += 24 * 60
        bed_h = ideal_bed // 60
        bed_m = ideal_bed % 60
        bed_str = f"{bed_h}:{bed_m:02d} PM" if bed_h >= 12 else f"{bed_h}:{bed_m:02d} PM"
        # Format properly
        if bed_h > 12:
            bed_str = f"{bed_h - 12}:{bed_m:02d} PM"
        elif bed_h == 0:
            bed_str = f"12:{bed_m:02d} AM"
        else:
            bed_str = f"{bed_h}:{bed_m:02d} {'PM' if bed_h >= 12 else 'AM'}"

        implications.append(
            f"With a {wake_time} wake time, aiming for "
            f"{OPTIMAL_CYCLES} full cycles means lights out by ~{bed_str}"
        )

    activity_level = user_context.get('activity_level')
    if activity_level in ('very_active', 'highly_active'):
        if deep_min is not None and total_minutes > 0:
            deep_pct = (deep_min / total_minutes) * 100
            if deep_pct < SLEEP_STAGES['deep']['min_pct']:
                implications.append(
                    "With a high activity level, below-average deep sleep "
                    "may slow workout recovery"
                )

    if user_context.get('has_weight_goal'):
        if duration_status in ('moderate_deficit', 'severe_deficit'):
            implications.append(
                "Sleep deficit can increase hunger hormones and reduce "
                "insulin sensitivity, which may slow weight loss progress"
            )

    for fact in user_context.get('health_facts', []):
        fact_lower = fact.lower()
        if 'insulin' in fact_lower or 'diabetes' in fact_lower or 'glucose' in fact_lower:
            if duration_status != 'adequate':
                implications.append(
                    "Short sleep is linked to reduced insulin sensitivity — "
                    "particularly relevant given your health profile"
                )
                break

    for goal in user_context.get('health_goals', []):
        goal_lower = goal.lower()
        if any(kw in goal_lower for kw in ('sleep', 'rest', 'recovery')):
            if duration_status != 'adequate':
                implications.append(
                    f"This affects your goal: \"{goal}\""
                )
                break

    # ── Build Recommendation ─────────────────────────────────────────
    recommendation = _build_recommendation(
        duration_status, cycles, stage_analysis, wake_time,
    )

    # ── Build Summary ────────────────────────────────────────────────
    summary = _build_summary(
        duration_status, stage_analysis, hours_str, cycles,
    )

    # ── Determine Severity ───────────────────────────────────────────
    if duration_status == 'severe_deficit':
        severity = 'warning'
    elif duration_status in ('moderate_deficit', 'mild_deficit'):
        severity = 'info'
    else:
        severity = 'positive'

    return {
        'summary_insight': summary,
        'observations': observations,
        'implications': implications,
        'recommendation': recommendation,
        'severity': severity,
        'medical_disclaimer': MEDICAL_DISCLAIMER,
        'evidence': {
            'total_minutes': total_minutes,
            'cycles': cycles,
            'duration_status': duration_status,
            'stage_analysis': stage_analysis,
            'time_period': parsed_data.get('time_period', 'unknown'),
        },
    }


def _build_summary(duration_status, stage_analysis, hours_str, cycles):
    """Build a one-sentence summary insight."""
    # Check if architecture (stages) is healthy
    stages_ok = True
    for key, data in stage_analysis.items():
        if data['pct'] < data['ref_min'] or data['pct'] > data['ref_max']:
            stages_ok = False
            break

    if duration_status == 'adequate' and stages_ok:
        return (
            f"Your sleep looks healthy — {hours_str} with balanced "
            f"stage distribution across ~{cycles} cycles."
        )
    elif duration_status == 'adequate' and not stages_ok:
        low_stages = [
            data for key, data in stage_analysis.items()
            if data['pct'] < data['ref_min']
        ]
        return (
            f"Total sleep duration is healthy at {hours_str}, but your "
            f"sleep stage distribution shows some imbalances."
        )
    elif stages_ok:
        return (
            f"Your sleep architecture is healthy, but total duration of "
            f"{hours_str} (~{cycles} cycles) is below the recommended range."
        )
    else:
        return (
            f"Both sleep duration ({hours_str}) and stage distribution "
            f"need attention for optimal recovery."
        )


def _build_recommendation(duration_status, cycles, stage_analysis, wake_time):
    """Build a single clear recommendation."""
    # Priority 1: Duration deficit
    if duration_status in ('severe_deficit', 'moderate_deficit'):
        extra_min = int((OPTIMAL_CYCLES - cycles) * SLEEP_CYCLE_MINUTES)
        if extra_min > 0:
            return (
                f"Shifting bedtime {extra_min} minutes earlier would add "
                f"approximately {extra_min // SLEEP_CYCLE_MINUTES:.0f} more "
                f"sleep cycle(s) and improve recovery."
            )
        return "Extending sleep duration by 30-60 minutes would help reach the optimal 5-cycle target."

    if duration_status == 'mild_deficit':
        return (
            "Moving bedtime 20-30 minutes earlier would bring you "
            "into the healthy 7-hour range."
        )

    # Priority 2: Stage imbalance
    deep_data = stage_analysis.get('deep')
    if deep_data and deep_data['pct'] < deep_data['ref_min']:
        return (
            "To increase deep sleep: maintain a consistent sleep schedule, "
            "keep the room cool (65-68°F), and avoid alcohol close to bedtime."
        )

    rem_data = stage_analysis.get('rem')
    if rem_data and rem_data['pct'] < rem_data['ref_min']:
        return (
            "To support REM sleep: maintain a consistent wake time, "
            "manage stress before bed, and avoid sleep disruptions in "
            "the second half of the night."
        )

    # Duration and stages are fine
    return (
        "Your sleep is looking good. Maintain your current schedule "
        "for consistent recovery."
    )


# ── PIE Rule Registration ────────────────────────────────────────────

@register
class SleepScreenshotAnalysisRule(BaseInsightRule):
    """
    PIE rule for sleep screenshot analysis.

    Triggered when a health screenshot event with sleep data is fired.
    Produces an Insight with the structured analysis for persistence.
    """

    rule_name = 'sleep_screenshot_analysis'
    module = 'health'
    insight_type = 'sleep_screenshot_analysis'
    min_confidence_to_store = 0.7
    min_confidence_to_notify = 0.85

    def applies(self, user, event):
        return (
            event.get('action') == 'health_screenshot'
            and event.get('context', {}).get('screenshot_type') == 'sleep'
        )

    def evaluate(self, user, event):
        context = event.get('context', {})
        parsed_data = context.get('parsed_data', {})
        user_ctx = context.get('user_context', {})

        analysis = analyze_sleep_data(parsed_data, user_ctx)
        if not analysis:
            return []

        from apps.core.time.system_clock import get_current_time

        now = get_current_time()
        time_period = parsed_data.get('time_period', 'unknown')

        return [
            {
                'severity': analysis['severity'],
                'title': f"Sleep Analysis: {analysis['summary_insight'][:80]}",
                'message': (
                    f"{analysis['summary_insight']}\n\n"
                    + '\n'.join(f"• {o}" for o in analysis['observations'])
                    + ('\n\n' + '\n'.join(f"→ {i}" for i in analysis['implications']) if analysis['implications'] else '')
                    + f"\n\n**Recommendation:** {analysis['recommendation']}"
                    + f"\n{analysis['medical_disclaimer']}"
                ),
                'confidence_score': 0.9,
                'explain_why': (
                    f"Rule: {self.rule_name}. Analyzed sleep screenshot "
                    f"covering {time_period}. Duration status: "
                    f"{analysis['evidence']['duration_status']}. "
                    f"Cycles: {analysis['evidence']['cycles']}."
                ),
                'evidence': analysis['evidence'],
                'dedupe_key': build_dedupe_key(
                    user.id, self.insight_type,
                    now.date(), now.date(),
                ),
            }
        ]
