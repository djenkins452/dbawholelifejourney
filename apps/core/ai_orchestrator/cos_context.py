"""
Whole Life Journey — CoS Context Builder (Phase 4 — Executive Context)

Project: Whole Life Journey
Path: apps/core/ai_orchestrator/cos_context.py
Purpose: Assemble full Chief of Staff context for every LLM interaction

Description:
    Builds a comprehensive context dict that reflects the user's current
    operational state. This context is injected into every LLM request
    so the assistant always operates with full situational awareness.

    Phase 4 additions:
    - Executive context object with strategic summary
    - Active insights/predictions summary
    - Relationship signals
    - Journal mood trends
    - Health signals
    - Open loops (unfinished goals, friction gates)
    - Feedback loop profiles (engagement, effectiveness)
    - Learned user profile injection
    - Executive tone mode selection

    The context is assembled from live engine queries — never cached
    stale data. All engine calls are wrapped in try/except for graceful
    degradation.

Public API:
    - build_cos_context(user) -> dict
    - build_executive_context(user) -> dict  (Phase 4)
    - format_cos_system_injection(context) -> str

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import datetime
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.conf import settings
from django.db import close_old_connections, connection
from django.utils import timezone

logger = logging.getLogger(__name__)

# Max worker threads for parallel context assembly
_PARALLEL_MAX_WORKERS = 6


# =========================================================================
# Context Builder Functions (each runs independently in its own thread)
# =========================================================================

def _build_blueprint_and_governance(user, prefs):
    """Build blueprint state, governance profile, and persona profile."""
    result = {}
    try:
        from apps.core.blueprint import engine as blueprint_engine
        blueprint = blueprint_engine.get_blueprint(user)
        explanation = blueprint_engine.explain_blueprint(user)
        result['blueprint_state'] = {
            'operating_style': getattr(blueprint, 'operating_style', 'balanced'),
            'interruption_tolerance': getattr(blueprint, 'interruption_tolerance', 'medium'),
            'auto_architect_enabled': getattr(blueprint, 'auto_architect_enabled', True),
            'pillars_ranked': explanation.get('pillars_ranked', []),
            'tier1_protected': explanation.get('tier1_protected', []),
            'override_policy': getattr(blueprint, 'override_policy', 'confirm'),
            'version': getattr(blueprint, 'version', 1),
        }
        result['protected_tiers'] = explanation.get('tier1_protected', [])
        result['governance_profile'] = {
            'accountability_style': getattr(blueprint, 'accountability_style', 'standard'),
            'question_frequency': getattr(blueprint, 'question_frequency', 'medium'),
            'sensitivity_tags': getattr(blueprint, 'sensitivity_tags', []) or [],
            'relationship_suggestions': getattr(blueprint, 'relationship_suggestions_enabled', False),
            'event_reflections': getattr(blueprint, 'event_reflections_enabled', True),
            'calibration_complete': getattr(blueprint, 'calibration_complete', False),
            'calibration_day': getattr(blueprint, 'calibration_day', 0),
        }
    except Exception as e:
        logger.debug("CoS context: blueprint unavailable: %s", e)

    try:
        from apps.core.ai_persona.persona_registry import get_persona_profile
        persona_key = getattr(prefs, 'ai_coaching_style', 'supportive')
        profile = get_persona_profile(persona_key)
        result['persona_profile'] = {
            'key': persona_key,
            'name': profile.get('name', persona_key),
            'tone': profile.get('tone', 'calm'),
        }
    except Exception:
        result['persona_profile'] = {'key': 'supportive', 'name': 'Supportive', 'tone': 'calm'}

    return result


def _build_plan_and_alignment(user):
    """Build today's plan, capacity, alignment, drift, and forecast."""
    result = {}

    # Today's plan + capacity
    try:
        from apps.core.blueprint import architecture_engine
        today = timezone.localdate()
        plan = architecture_engine.get_todays_plan(user)
        if plan:
            blocks = list(plan.blocks.all().order_by('start_time'))
            total_minutes = 0
            tier_counts = {1: 0, 2: 0, 3: 0, 4: 0}
            completed = 0
            block_summaries = []
            for b in blocks:
                if b.start_time and b.end_time:
                    s = datetime.datetime.combine(today, b.start_time)
                    e = datetime.datetime.combine(today, b.end_time)
                    d = (e - s).total_seconds() / 60
                    if d > 0:
                        total_minutes += d
                tier_counts[b.tier] = tier_counts.get(b.tier, 0) + 1
                if b.is_completed:
                    completed += 1
                block_summaries.append({
                    'title': b.title,
                    'tier': b.tier,
                    'start': b.start_time.strftime('%H:%M') if b.start_time else '',
                    'end': b.end_time.strftime('%H:%M') if b.end_time else '',
                    'completed': b.is_completed,
                    'locked': b.is_locked,
                })

            waking_minutes = 16 * 60
            result['capacity_snapshot'] = {
                'total_blocks': len(blocks),
                'completed_blocks': completed,
                'capacity_pct': min(100, round(total_minutes / waking_minutes * 100)),
                'tier_distribution': tier_counts,
                'scheduled_minutes': round(total_minutes),
            }
            result['today_blocks_summary'] = block_summaries
            result['risk_warnings'] = plan.risk_warnings or []
    except Exception as e:
        logger.debug("CoS context: plan unavailable: %s", e)

    # Alignment score
    try:
        from apps.core.blueprint.alignment_engine import compute_alignment_score
        alignment = compute_alignment_score(user)
        result['alignment_score'] = round(alignment.score)
        result['alignment_grade'] = alignment.grade
    except Exception as e:
        logger.debug("CoS context: alignment engine unavailable: %s", e)

    # Drift + prediction
    try:
        from apps.core.blueprint import drift_engine
        summary = drift_engine.get_drift_summary(user, days=7)
        score = summary.get('average_score', 0)
        result['drift_score'] = round(score)
        if result.get('alignment_score', 100) == 100 and score > 0:
            result['alignment_score'] = round(100 - score)
        prediction = summary.get('latest_prediction', {})
        result['drift_probability'] = {
            'probability_24h': round(prediction.get('probability_24h', 0) * 100),
            'probability_72h': round(prediction.get('probability_72h', 0) * 100),
            'factors': prediction.get('factors', {}),
        }
    except Exception as e:
        logger.debug("CoS context: drift unavailable: %s", e)

    # Tomorrow forecast load
    try:
        from apps.core.blueprint.models import ArchitecturePlan
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        tmr_plan = ArchitecturePlan.get_active_for_date(user, tomorrow)
        if tmr_plan:
            tmr_blocks = list(tmr_plan.blocks.all())
            tmr_minutes = 0
            for b in tmr_blocks:
                if b.start_time and b.end_time:
                    s = datetime.datetime.combine(tomorrow, b.start_time)
                    e = datetime.datetime.combine(tomorrow, b.end_time)
                    d = (e - s).total_seconds() / 60
                    if d > 0:
                        tmr_minutes += d
            result['forecast_load_24h'] = min(100, round(tmr_minutes / (16 * 60) * 100))
    except Exception:
        pass

    return result


def _build_pressure_and_deadlines(user):
    """Build pressure, protective briefing, deadlines, and overrides."""
    result = {}

    # Weekly pressure forecast
    try:
        from apps.core.blueprint.weekly_pressure import compute_weekly_pressure
        from apps.core.blueprint.human_language import translate_weekly_pressure
        pressure_data = compute_weekly_pressure(user)
        result['weekly_pressure'] = {
            'avg_load': pressure_data.get('avg_load', 0),
            'peak_day': pressure_data.get('peak_day', ''),
            'peak_load': pressure_data.get('peak_load', 0),
            'heavy_days': pressure_data.get('heavy_days', []),
            'light_days': pressure_data.get('light_days', []),
            'opportunity_windows': pressure_data.get('opportunity_windows', [])[:3],
            'summary': translate_weekly_pressure(pressure_data),
        }
    except Exception:
        pass

    # Composite Pressure Index
    try:
        from apps.core.blueprint.pressure_models import PressureSnapshot
        pressure_snapshot = PressureSnapshot.latest_for_user(user)
        if pressure_snapshot:
            result['pressure_snapshot'] = {
                'pressure_index': pressure_snapshot.pressure_index,
                'density_score': pressure_snapshot.density_score,
                'compression_score': pressure_snapshot.compression_score,
                'breach_risk_score': pressure_snapshot.breach_risk_score,
                'erosion_score': pressure_snapshot.erosion_score,
                'collision_score': pressure_snapshot.collision_score,
                'horizon_days': pressure_snapshot.horizon_days,
                'computed_at': pressure_snapshot.computed_at.isoformat(),
            }
    except Exception:
        pass

    # Protective briefing
    try:
        from apps.core.blueprint.protective_engine import get_protective_briefing
        result['protective_briefing'] = get_protective_briefing(user)
    except Exception:
        pass

    # Deadline snapshot
    try:
        from apps.core.blueprint.models import DeadlineSnapshot
        snapshot = DeadlineSnapshot.latest_for_user(user)
        if snapshot and not snapshot.is_stale():
            result['deadline_snapshot'] = {
                'due_24h': snapshot.due_24h,
                'due_72h': snapshot.due_72h,
                'due_7d': snapshot.due_7d,
                'collision_flags': snapshot.collision_flags,
                'computed_at': snapshot.computed_at.isoformat(),
            }
        elif snapshot and snapshot.is_stale():
            result['deadline_snapshot'] = {
                'stale': True,
                'computed_at': snapshot.computed_at.isoformat(),
            }
    except Exception:
        pass

    # Override frequency (14d) — from SAE truth layer
    try:
        from apps.core.ai_state.state_engine import get_state_value
        result['override_frequency_14d'] = get_state_value(
            user, 'intervention.override_frequency_14d', 0
        )
    except Exception:
        pass

    return result


def _build_health_and_vitals(user):
    """Build health signals, medication, fasting, and transformation metrics."""
    result = {}

    # Transformation metrics
    try:
        from apps.core.ai_state.state_engine import get_state_value
        result['transformation_metrics'] = {
            'weight_current': get_state_value(user, 'health.weight_current'),
            'weight_trend': get_state_value(user, 'health.weight_trend'),
            'active_goals': get_state_value(user, 'goals.active_goal_count', 0),
        }
    except Exception:
        pass

    # Active fast status
    try:
        from apps.health.models import FastingSession
        active_fast = FastingSession.objects.filter(
            user=user, is_active=True,
        ).first()
        if active_fast:
            result['active_fast_status'] = {
                'active': True,
                'started_at': active_fast.start_time.isoformat() if active_fast.start_time else '',
                'target_hours': getattr(active_fast, 'target_hours', 0),
            }
    except Exception:
        pass

    # Medication adherence (schedule-based, not just today's logs)
    try:
        from apps.health.medicine_utils import calculate_medicine_adherence
        today = timezone.localdate()
        week_ago = today - timezone.timedelta(days=7)
        adh = calculate_medicine_adherence(user, week_ago, today)
        if adh["expected_doses"] > 0:
            result['medication_adherence_state'] = {
                'total_scheduled': adh["expected_doses"],
                'taken_today': adh["taken_doses"],
                'adherence_pct': adh["adherence_rate"] or 0,
            }
    except Exception:
        logger.error("CoS context: medication adherence failed", exc_info=True)

    # Pending medication details (names, times, status)
    try:
        from apps.health.models import Medicine, MedicineLog
        from apps.core.utils import get_user_now
        user_now = get_user_now(user)
        med_today = user_now.date()
        current_time = user_now.time()
        day_of_week = str(med_today.weekday())  # 0=Monday, 6=Sunday

        active_meds = Medicine.objects.filter(
            user=user, medicine_status=Medicine.STATUS_ACTIVE,
        ).exclude(status='deleted').prefetch_related('schedules')

        pending_meds = []
        for med in active_meds:
            for sched in med.schedules.filter(is_active=True):
                # Check if this schedule applies to today
                if sched.days_of_week and day_of_week not in sched.days_of_week.split(','):
                    continue

                taken = MedicineLog.objects.filter(
                    medicine=med,
                    schedule=sched,
                    scheduled_date=med_today,
                    log_status__in=['taken', 'late'],
                ).exists()

                if taken:
                    med_status = 'taken'
                elif sched.scheduled_time and sched.scheduled_time > current_time:
                    med_status = 'upcoming'
                else:
                    med_status = 'overdue'

                time_str = ''
                if sched.scheduled_time:
                    time_str = sched.scheduled_time.strftime('%I:%M %p').lstrip('0')

                pending_meds.append({
                    'name': med.name,
                    'dose': med.dose or '',
                    'scheduled_time': time_str,
                    'time_of_day': sched.time_of_day or '',
                    'status': med_status,
                })

        if pending_meds:
            result['pending_medications'] = pending_meds
    except Exception:
        logger.error("CoS context: pending medication details failed", exc_info=True)

    # Health signals
    try:
        from apps.core.ai_state.state_engine import get_state_value
        health_signals = {
            'sleep_avg_7d': get_state_value(user, 'health.sleep_avg_hours_7d'),
            'sleep_trend': get_state_value(user, 'health.sleep_trend', 'stable'),
            'workout_count_7d': get_state_value(user, 'fitness.workouts_7d', 0),
            'steps_avg_7d': get_state_value(user, 'health.steps_avg_7d'),
        }

        from datetime import timedelta
        week_ago = timezone.localdate() - timedelta(days=7)

        # Weight — from SAE truth layer
        try:
            weight_current = get_state_value(user, 'health.weight_current')
            if weight_current is not None:
                health_signals['weight_current'] = round(float(weight_current), 1)
                health_signals['weight_unit'] = get_state_value(user, 'health.weight_unit', 'lb')
                last_entry = get_state_value(user, 'health.last_weight_entry')
                if last_entry:
                    health_signals['weight_date'] = last_entry[:10]
                weight_trend = get_state_value(user, 'health.weight_trend')
                if weight_trend:
                    health_signals['weight_trend'] = weight_trend

            # Weight goal from SAE
            weight_goal = get_state_value(user, 'health.weight_goal')
            if weight_goal is not None:
                health_signals['weight_goal'] = float(weight_goal)
                health_signals['weight_goal_unit'] = get_state_value(user, 'health.weight_goal_unit', 'lb')
                wg_target = get_state_value(user, 'health.weight_goal_target_date')
                if wg_target:
                    health_signals['weight_goal_target_date'] = str(wg_target)
                wg_remaining = get_state_value(user, 'health.weight_goal_remaining')
                if wg_remaining is not None:
                    health_signals['weight_goal_remaining'] = wg_remaining
                    health_signals['weight_goal_on_track'] = get_state_value(user, 'health.weight_goal_on_track')
        except Exception:
            pass

        # Vitals and workout signals — from SAE truth layer
        try:
            hr_avg = get_state_value(user, 'health.heart_rate_avg_7d')
            if hr_avg:
                health_signals['heart_rate_avg_7d'] = round(float(hr_avg))

            bp_sys = get_state_value(user, 'health.bp_systolic')
            bp_dia = get_state_value(user, 'health.bp_diastolic')
            if bp_sys and bp_dia:
                health_signals['bp_latest'] = f"{bp_sys}/{bp_dia}"

            glucose_avg = get_state_value(user, 'health.glucose_avg_7d')
            if glucose_avg:
                health_signals['glucose_avg_7d'] = round(float(glucose_avg))

            spo2_avg = get_state_value(user, 'health.blood_oxygen_avg_7d')
            if spo2_avg:
                health_signals['blood_oxygen_avg_7d'] = round(float(spo2_avg), 1)

            if not health_signals.get('steps_avg_7d'):
                steps = get_state_value(user, 'health.steps_avg_7d')
                if steps:
                    health_signals['steps_avg_7d'] = int(steps)

            if not health_signals.get('sleep_avg_7d'):
                sleep_min = get_state_value(user, 'health.sleep_avg_duration_7d')
                if sleep_min:
                    health_signals['sleep_avg_7d'] = round(float(sleep_min) / 60, 1)

            # Fitness signals from SAE
            from apps.core.ai_state.state_engine import get_module_state
            fitness = get_module_state(user, 'fitness') or {}
            workout_count = fitness.get('workouts_7d', 0)
            if workout_count > 0:
                health_signals['workout_count_7d'] = workout_count
                if fitness.get('workout_calories_7d'):
                    health_signals['workout_calories_7d'] = fitness['workout_calories_7d']
                if fitness.get('workout_minutes_7d'):
                    health_signals['workout_minutes_7d'] = fitness['workout_minutes_7d']
                if fitness.get('workout_avg_hr_7d'):
                    health_signals['workout_avg_hr_7d'] = fitness['workout_avg_hr_7d']
                if fitness.get('workout_distance_7d'):
                    health_signals['workout_distance_7d'] = fitness['workout_distance_7d']
                if fitness.get('recent_workouts'):
                    health_signals['recent_workouts'] = fitness['recent_workouts']

            # Per-exercise progress (plateau detection, e1RM trends)
            exercise_progress = fitness.get('exercise_progress', [])
            if exercise_progress:
                health_signals['exercise_progress'] = exercise_progress

            hr_events = get_state_value(user, 'health.heart_rate_events_7d')
            if hr_events and hr_events > 0:
                health_signals['heart_rate_events_7d'] = hr_events

        except Exception:
            pass

        result['health_signals'] = health_signals
    except Exception:
        result['health_signals'] = {}

    # Health Intelligence Engine — multi-week trends, scores, patterns
    try:
        from apps.health.services.cos_health_context import (
            build_cos_health_intelligence,
            build_cos_health_summary_text,
        )
        intel = build_cos_health_intelligence(user)
        # Protein intelligence (LBM-aware targets)
        protein_intel = intel.get('protein_intelligence', {})
        protein_data = {}
        if protein_intel:
            protein_data = {
                'target_g': protein_intel.get('target_g'),
                'method': protein_intel.get('method'),
                'lbm': protein_intel.get('lean_body_mass'),
                'workout_day': protein_intel.get('workout_day', False),
                'multiplier': protein_intel.get('multiplier'),
                # Weekly evaluation (7-day average vs daily target)
                'protein_avg_7d': protein_intel.get('protein_avg_7d'),
                'protein_consistency_pct': protein_intel.get('protein_consistency_pct'),
                'protein_gap_g': protein_intel.get('protein_gap_g'),
                'protein_avg_ratio': protein_intel.get('protein_avg_ratio'),
            }

        result['health_intelligence'] = {
            'baseline_ready': intel.get('baseline_ready', False),
            'health_score': intel.get('scores', {}).get('health_score'),
            'recovery_score': intel.get('scores', {}).get('recovery_score'),
            'recovery_status': (
                intel.get('scores', {}).get('recovery_drivers', {}).get('status')
            ),
            'strengths': intel.get('strengths', [])[:3],
            'weaknesses': intel.get('weaknesses', [])[:3],
            'risk_flags': [
                r.get('message', '') for r in intel.get('risk_flags', [])[:3]
            ],
            'top_recommendation': intel.get('top_recommendation', ''),
            # Strip raw protein fields from trends_7d so the LLM cannot
            # compute its own protein math from individual-day averages.
            # The pre-calculated protein_avg_7d in the 'protein' block is
            # the ONLY weekly protein number the LLM should see.
            'trends_7d': {
                k: v for k, v in intel.get('trends_7d', {}).items()
                if not k.startswith('protein')
            },
            'correlations': [
                {
                    'signals': f"{c['signal_a']} ↔ {c['signal_b']}",
                    'interpretation': c.get('interpretation', ''),
                }
                for c in intel.get('correlations', [])[:2]
            ],
            'protein': protein_data,
            'body_comp': intel.get('body_comp_intelligence', {}),
            'last_computed': intel.get('body_comp_intelligence', {}).get('last_computed', ''),
        }
        result['health_intelligence_summary'] = build_cos_health_summary_text(user)
    except ImportError:
        pass  # Module not yet deployed
    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            "Failed to build health intelligence for CoS", exc_info=True,
        )

    return result


def _build_calendar_events(user):
    """Build calendar events for today."""
    result = {}
    try:
        from apps.calendar_engine.models import CalendarEvent
        from apps.core.utils import get_user_now, get_user_today

        user_now = get_user_now(user)
        today_start = user_now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = user_now.replace(hour=23, minute=59, second=59, microsecond=0)

        events = CalendarEvent.objects.filter(
            user=user,
            start_dt__lte=today_end,
            end_dt__gte=today_start,
            status__in=['scheduled', 'completed'],
        ).order_by('start_dt')[:12]

        event_summaries = []
        for ev in events:
            actual_status = ev.status  # 'scheduled', 'completed', 'canceled'

            if actual_status == 'completed':
                time_status = 'completed'
            elif ev.end_dt <= user_now:
                time_status = 'past'
            elif ev.start_dt <= user_now <= ev.end_dt:
                time_status = 'in_progress'
            elif ev.start_dt <= user_now + datetime.timedelta(hours=1):
                time_status = 'upcoming_soon'
            else:
                time_status = 'upcoming'

            # Overdue = past its time AND not completed
            is_overdue = (
                ev.end_dt <= user_now
                and actual_status != 'completed'
            )

            _local_start = ev.start_dt.astimezone(user_now.tzinfo)
            _local_end = ev.end_dt.astimezone(user_now.tzinfo)
            event_summaries.append({
                'title': ev.title,
                'start': _local_start.strftime('%I:%M %p').lstrip('0'),
                'end': _local_end.strftime('%I:%M %p').lstrip('0'),
                'domain': ev.domain.name if ev.domain else '',
                'is_protected': ev.is_protected,
                'time_status': time_status,
                'is_overdue': is_overdue,
                'actual_status': actual_status,
            })
        result['calendar_events_today'] = event_summaries
    except Exception as e:
        logger.debug("CoS context: calendar events unavailable: %s", e)

    return result


def _build_intelligence_signals(user):
    """Build insights, predictions, guidance, and correlations."""
    result = {}

    # Track which intelligence sources loaded successfully
    _sources_loaded = []
    _sources_failed = []

    # Active PIE insights — freshness window prevents stale insights
    # (e.g. a "strength plateau" from 2 weeks ago) from polluting CoS.
    # Critical/warning insights get a longer window than info-level.
    try:
        from datetime import timedelta as _td

        from django.utils import timezone as _tz

        from apps.core.ai_insights.models import Insight

        _insight_cutoff = _tz.now() - _td(hours=72)
        recent_insights = Insight.objects.filter(
            user=user, status__in=["new", "read"],
            created_at__gte=_insight_cutoff,
        ).order_by("-created_at")[:5]
        result['active_insights'] = [
            {
                'type': i.insight_type,
                'severity': i.severity,
                'title': i.title,
                'message': i.message,
                'explain_why': i.explain_why,
                'module': i.module,
                'confidence': round(i.confidence_score, 2),
            }
            for i in recent_insights
        ]
        _sources_loaded.append('PIE')
    except Exception as e:
        logger.warning("Intelligence signal failed (PIE): %s", e, exc_info=True)
        result['active_insights'] = []
        _sources_failed.append('PIE')

    # Active PRIE predictions
    try:
        from apps.core.ai_predictions.models import Prediction
        active_predictions = Prediction.objects.filter(
            user=user, status="active",
        ).order_by("-confidence_score")[:5]
        result['active_predictions'] = [
            {
                'type': p.prediction_type,
                'module': p.module,
                'value': p.predicted_value,
                'confidence': round(p.confidence_score, 2),
                'explanation': p.explanation,
                'predicted_date': p.predicted_date.strftime('%b %d')
                if p.predicted_date else None,
            }
            for p in active_predictions
        ]
        _sources_loaded.append('PRIE')
    except Exception as e:
        logger.warning("Intelligence signal failed (PRIE): %s", e, exc_info=True)
        result['active_predictions'] = []
        _sources_failed.append('PRIE')

    # Active PGE guidance
    try:
        from apps.core.ai_guidance.models import GuidanceItem
        now = timezone.now()
        active_guidance = GuidanceItem.objects.filter(
            user=user,
            is_active=True,
            dismissed_at__isnull=True,
        ).exclude(
            snoozed_until__gt=now,
        ).order_by("priority", "-created_at")[:5]
        result['active_guidance'] = [
            {
                'title': g.title,
                'message': g.message,
                'priority': g.priority,
                'module': g.module,
                'guidance_type': g.guidance_type,
                'source': g.source,
            }
            for g in active_guidance
        ]
        _sources_loaded.append('PGE')
    except Exception as e:
        logger.warning("Intelligence signal failed (PGE): %s", e, exc_info=True)
        result['active_guidance'] = []
        _sources_failed.append('PGE')

    # Active CDCE correlations
    try:
        from apps.core.ai_cross_domain.models import DomainCorrelation
        active_correlations = DomainCorrelation.objects.filter(
            user=user, status='active',
        ).order_by('-strength_score')[:5]
        result['cross_domain_correlations'] = [
            {
                'type': c.correlation_type,
                'strength': c.strength,
                'score': round(c.strength_score, 2),
                'direction': c.direction,
                'narrative': c.narrative,
                'evidence': c.evidence_summary,
                'domains': [c.domain_a, c.domain_b],
            }
            for c in active_correlations
        ]
        _sources_loaded.append('CDCE')
    except Exception as e:
        logger.warning("Intelligence signal failed (CDCE): %s", e, exc_info=True)
        result['cross_domain_correlations'] = []
        _sources_failed.append('CDCE')

    # Intelligence status — tells Beth whether she has full or degraded awareness
    if not _sources_failed:
        result['intelligence_status'] = 'full'
    elif len(_sources_failed) >= 3:
        result['intelligence_status'] = 'degraded'
    else:
        result['intelligence_status'] = 'partial'
    result['intelligence_sources_failed'] = _sources_failed

    # Journal content intelligence (themes, concerns, sentiment trajectory)
    try:
        from apps.journal.services.content_intelligence import analyze_journal_for_cos
        result['journal_intelligence'] = analyze_journal_for_cos(user)
    except ImportError:
        result['journal_intelligence'] = {}
    except Exception as e:
        logger.warning("Journal intelligence failed: %s", e, exc_info=True)
        result['journal_intelligence'] = {}

    # Domain registry coverage summary (for system awareness)
    try:
        from apps.core.domain_registry import registry
        result['domain_coverage'] = registry.get_coverage_summary()
    except ImportError:
        result['domain_coverage'] = []
    except Exception:
        result['domain_coverage'] = []

    return result


def _build_people_and_mood(user):
    """Build relationship signals and mood status."""
    result = {}

    try:
        # Phase R1: Use new canonical Person model for relationship signals
        from apps.relationships.models import Person
        from apps.relationships.services import RelationshipAnalyticsService

        top_people = RelationshipAnalyticsService.top_interacted(user, limit=10)
        rel_signals = []
        for person in top_people:
            days_since = RelationshipAnalyticsService.days_since_last_interaction(person)
            breakdown = RelationshipAnalyticsService.context_breakdown(person)
            rel_signals.append({
                'name': person.get_display_name(),
                'relationship_type': person.relationship_type,
                'days_since_contact': days_since,
                'drifting': days_since is not None and days_since > 14,
                'interaction_count': person.interaction_count,
                'context_distribution': breakdown,
            })
        result['relationship_signals'] = rel_signals
    except ImportError:
        # Fallback to legacy ai_relationships if new app not available
        try:
            from apps.core.ai_relationships.models import Relationship
            relationships = Relationship.objects.filter(
                user=user, importance_tier__lte=2,
            ).select_related("person")[:5]
            rel_signals = []
            for rel in relationships:
                days_since = None
                if rel.last_interaction:
                    days_since = (timezone.now() - rel.last_interaction).days
                rel_signals.append({
                    'name': rel.person.display_name if rel.person else 'Unknown',
                    'tier': rel.importance_tier,
                    'days_since_contact': days_since,
                    'drifting': days_since is not None and days_since > 14,
                })
            result['relationship_signals'] = rel_signals
        except Exception:
            result['relationship_signals'] = []
    except Exception as e:
        logger.warning("CoS context: relationship signals unavailable: %s", e)
        result['relationship_signals'] = []

    # Phase R2: Relational health score and structured payload
    try:
        from apps.relationships.services import RelationalHealthService
        health = RelationalHealthService.compute_health(user)
        result['relational_health'] = {
            'relational_health_score': health.get('score'),
            'stale_relationships_count': health.get('stale_relationships_count', 0),
            'top_anchor_persons': health.get('top_anchor_persons', []),
            'imbalance_flags': [
                {
                    'person': f['display_name'],
                    'dominant_context': f['dominant_context'],
                    'percentage': f['percentage'],
                }
                for f in health.get('imbalance_flags', [])
            ],
        }
    except ImportError:
        result['relational_health'] = {}
    except Exception as e:
        logger.warning("CoS context: relational health unavailable: %s", e)
        result['relational_health'] = {}

    try:
        from apps.core.ai_state.state_engine import get_state_value
        result['mood_status'] = {
            'trend': get_state_value(user, 'journal.mood_trend', 'stable'),
            'avg_7d': get_state_value(user, 'journal.mood_avg_7d'),
            'entries_7d': get_state_value(user, 'journal.entries_7d', 0),
        }
    except Exception:
        result['mood_status'] = {}

    return result


def _build_loops_and_events(user):
    """Build open loops, life events, feedback profiles, and learned profile."""
    result = {}

    # Open loops — from SAE truth layer
    try:
        from apps.core.ai_state.state_engine import get_state_value
        overdue_goals = get_state_value(user, 'goals.overdue_goal_count', 0)
        pending_gates = get_state_value(user, 'intervention.pending_friction_gates', 0)
        result['open_loops'] = {
            'overdue_goals': overdue_goals,
            'pending_friction_gates': pending_gates,
        }
    except Exception:
        result['open_loops'] = {}

    # Approaching life events — from SAE truth layer
    try:
        from apps.core.ai_state.state_engine import get_state_value
        result['approaching_life_events'] = get_state_value(
            user, 'life_events.approaching_events', []
        )
    except Exception as e:
        logger.debug("CoS context: life events unavailable: %s", e)
        result['approaching_life_events'] = []

    # Feedback loop profiles — from SAE truth layer
    try:
        from apps.core.ai_state.state_engine import get_module_state
        feedback = get_module_state(user, 'feedback') or {}
        result['feedback_profiles'] = {
            'insight_engagement': feedback.get('insight_engagement', 0.5),
            'briefing_open_rate': feedback.get('briefing_open_rate', 0.0),
            'preferred_briefing_length': feedback.get('preferred_briefing_length', 'standard'),
            'intervention_effectiveness': feedback.get('intervention_effectiveness', 0.5),
            'escalation_modifier': feedback.get('escalation_modifier', 0.0),
        }
    except Exception:
        result['feedback_profiles'] = {}

    # Learned profile injection
    try:
        from apps.core.ai_learning.learning_extractor import get_profile_system_prompt
        result['learned_profile_prompt'] = get_profile_system_prompt(user)
    except Exception:
        result['learned_profile_prompt'] = ''

    # Navigable pages
    try:
        from apps.core.ai_orchestrator.url_resolver import get_navigable_pages
        result['navigable_pages'] = get_navigable_pages()
    except Exception:
        result['navigable_pages'] = []

    return result


def _build_strategy_and_signals(user):
    """Build governance strategy, trajectory signals, and decision branches."""
    result = {}

    try:
        from apps.core.ai_governance.strategy_selector import build_strategy_system_injection
        result['governance_strategy_prompt'] = build_strategy_system_injection(user)
    except Exception as e:
        logger.debug("CoS context: governance strategy unavailable: %s", e)
        result['governance_strategy_prompt'] = ''

    try:
        result['trajectory_signals'] = _build_trajectory_signals(user)
    except Exception as e:
        logger.debug("CoS context: trajectory signals unavailable: %s", e)
        result['trajectory_signals'] = {}

    try:
        result['decision_branch_signals'] = _build_decision_branch_signals(user)
    except Exception as e:
        logger.debug("CoS context: decision branch signals unavailable: %s", e)
        result['decision_branch_signals'] = {}

    return result


def _build_recent_image_analyses(user):
    """Build recent image analysis context — from SAE truth layer."""
    try:
        from apps.core.ai_state.state_engine import get_state_value

        analyses = get_state_value(user, 'scan.recent_analyses', [])
        if not analyses:
            return {}
        return {'recent_image_analyses': analyses}
    except Exception as e:
        logger.debug("CoS context: image analyses unavailable: %s", e)
        return {}


def _build_meals_context(user):
    """Build meal intelligence context for CoS awareness."""
    try:
        from apps.meals.models import HouseholdMembership
        from apps.meals.services.activation import get_activation_status
        from django.utils import timezone as tz

        membership = HouseholdMembership.objects.filter(user=user).select_related("household").first()
        if not membership:
            return {}

        household = membership.household
        today = tz.now().date()

        # Activation check
        activation = get_activation_status(user, household)

        if not activation.is_ready:
            return {
                'meals_context': {
                    'activated': False,
                    'setup_needed': True,
                    'pantry_count': activation.pantry_count,
                    'pantry_required': activation.pantry_required,
                    'recipe_count': activation.recipe_count,
                    'recipe_required': activation.recipe_required,
                    'setup_url': '/meals/setup/',
                    'household_name': household.name,
                }
            }

        # Pantry summary — from SAE truth layer
        from apps.core.ai_state.state_engine import get_state_value
        pantry_count = get_state_value(user, 'meals.pantry_item_count', 0)
        expiring = get_state_value(user, 'meals.expiring_item_names', [])

        # Today's plan — from SAE truth layer
        has_dinner = get_state_value(user, 'meals.has_dinner_planned', False)
        dinner_recipe = get_state_value(user, 'meals.dinner_recipe') if has_dinner else None

        # Phase 12: Pantry scan confidence drift
        pantry_scan_data = {}
        try:
            from apps.meals.services.pantry_photo_detection import pantry_scan_session_service
            drift = pantry_scan_session_service.calculate_confidence_drift(household)
            pantry_scan_data = {
                'overall_pantry_confidence': drift.get('overall_confidence', 0),
                'days_since_last_scan': drift.get('days_since_last_scan'),
                'items_unconfirmed': drift.get('low_confidence_items', 0),
            }
        except Exception as e:
            logger.debug("CoS: pantry scan data unavailable: %s", e)

        return {
            'meals_context': {
                'activated': True,
                'pantry_items_tracked': pantry_count,
                'expiring_soon': list(expiring),
                'dinner_planned': dinner_recipe,
                'household_name': household.name,
                **pantry_scan_data,
            }
        }
    except Exception as e:
        logger.debug("CoS context: meals unavailable: %s", e)
        return {}


def _build_faith_context(user):
    """Build faith module context — from SAE truth layer."""
    try:
        from apps.core.ai_state.state_engine import get_state_value

        faith = get_state_value(user, 'faith', {}) or {}

        active_prayers = faith.get('unanswered_prayers', 0)
        answered_prayers = faith.get('answered_prayers', 0)
        recent_prayers = faith.get('recent_prayer_titles', [])
        urgent_count = faith.get('urgent_prayers', 0)

        result = {
            'faith_summary': {
                'active_prayers': active_prayers,
                'answered_prayers': answered_prayers,
                'urgent_prayers': urgent_count,
                'recent_prayer_titles': recent_prayers,
            }
        }

        # Bible reading progress
        reading_streak = faith.get('reading_streak', 0)
        bible_plan = faith.get('bible_plan_name', '')
        if reading_streak or bible_plan:
            result['faith_summary']['bible_reading'] = {
                'plan': bible_plan,
                'streak_days': reading_streak,
            }

        return result

    except Exception as e:
        logger.debug("CoS context: faith unavailable: %s", e)
        return {}


# =========================================================================
# Phase 7.3: Additional Domain Context Builders
# =========================================================================


def _build_finance_context(user):
    """Build finance module context — budgets, goals, recent activity."""
    try:
        from datetime import timedelta as td
        now = timezone.now()
        result = {}

        try:
            from apps.finance.models import FinancialGoal, Budget
        except ImportError:
            return {}

        # Active financial goals
        active_goals = FinancialGoal.objects.filter(
            user=user, goal_status='active',
        ).order_by('target_date')[:5]

        if active_goals:
            goals_data = []
            for g in active_goals:
                progress = 0
                if g.target_amount and g.target_amount > 0:
                    progress = round(
                        float(g.current_amount or 0) / float(g.target_amount) * 100, 1
                    )
                goals_data.append({
                    'name': g.name,
                    'type': g.goal_type,
                    'target': float(g.target_amount or 0),
                    'current': float(g.current_amount or 0),
                    'progress_pct': progress,
                    'target_date': g.target_date.strftime('%b %d')
                    if g.target_date else None,
                })
            result['finance_goals'] = goals_data

        # Current month budget status
        first_of_month = now.date().replace(day=1)
        budgets = Budget.objects.filter(
            user=user, month=first_of_month,
        ).select_related('category')[:10]

        if budgets:
            budget_data = []
            for b in budgets:
                cat_name = b.category.name if b.category else 'Uncategorized'
                budgeted = float(b.budgeted_amount or 0)
                spent = float(getattr(b, 'spent_amount', 0) or 0)
                pct = round(spent / budgeted * 100, 1) if budgeted > 0 else 0
                if pct >= 80:  # Only surface budgets near/over limit
                    budget_data.append({
                        'category': cat_name,
                        'budgeted': budgeted,
                        'spent': spent,
                        'percent_used': pct,
                        'over_budget': pct > 100,
                    })
            if budget_data:
                result['finance_budgets_alert'] = budget_data

        return result

    except Exception as e:
        logger.debug("CoS context: finance unavailable: %s", e)
        return {}


def _build_brain_training_context(user):
    """Build brain training context — recent sessions, streaks."""
    try:
        try:
            from apps.brain_training.models import UserOverallStats, DailyStats
        except ImportError:
            return {}

        result = {}

        # Overall stats
        overall = UserOverallStats.objects.filter(user=user).first()
        if overall:
            result['brain_training'] = {
                'total_sessions': overall.total_sessions,
                'total_completed': overall.total_completed,
                'current_streak': overall.current_streak,
                'favorite_game': (
                    overall.favorite_game.name
                    if overall.favorite_game else None
                ),
            }

        # Recent daily stats (last 7 days)
        from datetime import timedelta as td
        cutoff = timezone.now().date() - td(days=7)
        recent_days = DailyStats.objects.filter(
            user=user, date__gte=cutoff,
        ).order_by('-date')[:7]
        if recent_days:
            result.setdefault('brain_training', {})['recent_days'] = [
                {
                    'date': d.date.strftime('%b %d'),
                    'sessions': d.sessions_completed,
                    'best_score': d.best_score,
                }
                for d in recent_days
            ]

        return result

    except Exception as e:
        logger.debug("CoS context: brain_training unavailable: %s", e)
        return {}


def _build_capture_context(user):
    """Build capture context — unprocessed captures, recent entries."""
    try:
        try:
            from apps.capture.models import CaptureEntry, PendingCapture
        except ImportError:
            return {}

        result = {}

        # Pending/unprocessed captures
        pending_count = PendingCapture.objects.filter(
            user=user, status__in=['pending', 'uploading'],
        ).count()

        # Recent ready entries (last 7 days)
        from datetime import timedelta as td
        cutoff = timezone.now() - td(days=7)
        ready_entries = CaptureEntry.objects.filter(
            user=user, status='ready', created_at__gte=cutoff,
        ).order_by('-created_at')[:5]

        if pending_count or ready_entries:
            result['capture_status'] = {
                'pending_uploads': pending_count,
                'recent_captures': [
                    {
                        'title': e.title[:60] if e.title else 'Untitled',
                        'category': e.category,
                        'date': e.created_at.strftime('%b %d'),
                    }
                    for e in ready_entries
                ],
            }

        return result

    except Exception as e:
        logger.debug("CoS context: capture unavailable: %s", e)
        return {}


def _build_medical_context(user):
    """Build medical context — recent labs, abnormal results."""
    try:
        try:
            from apps.medical.models import LabResult, LabPanel
        except ImportError:
            return {}

        result = {}
        from datetime import timedelta as td
        cutoff = timezone.now() - td(days=90)

        # Recent abnormal results (last 90 days)
        abnormal = LabResult.objects.filter(
            user=user,
            collected_at__gte=cutoff,
            abnormal_flag__in=['L', 'H', 'LL', 'HH', 'A'],
        ).select_related('canonical_test').order_by('-collected_at')[:5]

        if abnormal:
            result['medical_alerts'] = [
                {
                    'test': r.canonical_test.short_name if r.canonical_test else 'Unknown',
                    'value': str(r.value_text)[:20],
                    'flag': r.abnormal_flag,
                    'date': r.collected_at.strftime('%b %d') if r.collected_at else None,
                }
                for r in abnormal
            ]

        # Recent lab panels
        panels = LabPanel.objects.filter(
            user=user, collected_at__gte=cutoff,
        ).order_by('-collected_at')[:3]
        if panels:
            result['recent_lab_panels'] = [
                {
                    'type': p.panel_type,
                    'name': p.name[:40] if p.name else p.panel_type,
                    'date': p.collected_at.strftime('%b %d') if p.collected_at else None,
                }
                for p in panels
            ]

        return result

    except Exception as e:
        logger.debug("CoS context: medical unavailable: %s", e)
        return {}


def _build_purpose_context(user):
    """Build purpose context — life goals, habit progress, streaks."""
    try:
        try:
            from apps.purpose.models import LifeGoal, HabitGoal, HabitEntry
        except ImportError:
            return {}

        result = {}
        from datetime import timedelta as td
        today = timezone.now().date()

        # Active life goals
        life_goals = LifeGoal.objects.filter(
            user=user, status='active',
        ).order_by('target_date')[:5]

        if life_goals:
            result['life_goals'] = [
                {
                    'name': g.name,
                    'target_date': g.target_date.strftime('%b %d')
                    if g.target_date else None,
                    'days_until': (g.target_date - today).days
                    if g.target_date else None,
                }
                for g in life_goals
            ]

        # Active habits with completion rates (last 7 days)
        habits = HabitGoal.objects.filter(
            user=user, status='active',
        )[:10]

        if habits:
            week_ago = today - td(days=7)
            habit_data = []
            for h in habits:
                entries_7d = HabitEntry.objects.filter(
                    goal=h, date__gte=week_ago, completed=True,
                ).count()
                target_7d = h.sessions_per_week if h.sessions_per_week else 7
                rate = round(entries_7d / target_7d * 100, 0) if target_7d > 0 else 0
                habit_data.append({
                    'name': h.name,
                    'completion_rate_7d': min(rate, 100),
                    'entries_7d': entries_7d,
                    'target_weekly': target_7d,
                })
            result['habit_progress'] = habit_data

        return result

    except Exception as e:
        logger.debug("CoS context: purpose unavailable: %s", e)
        return {}


# Registry of parallel builder functions.
# Each takes (user, prefs) or (user,) and returns a dict of context updates.
_PARALLEL_BUILDERS = [
    lambda user, prefs: _build_blueprint_and_governance(user, prefs),
    lambda user, prefs: _build_plan_and_alignment(user),
    lambda user, prefs: _build_pressure_and_deadlines(user),
    lambda user, prefs: _build_health_and_vitals(user),
    lambda user, prefs: _build_calendar_events(user),
    lambda user, prefs: _build_intelligence_signals(user),
    lambda user, prefs: _build_people_and_mood(user),
    lambda user, prefs: _build_loops_and_events(user),
    lambda user, prefs: _build_strategy_and_signals(user),
    lambda user, prefs: _build_recent_image_analyses(user),
    lambda user, prefs: _build_meals_context(user),
    lambda user, prefs: _build_faith_context(user),
    # Phase 7.3: Additional domain context builders
    lambda user, prefs: _build_finance_context(user),
    lambda user, prefs: _build_brain_training_context(user),
    lambda user, prefs: _build_capture_context(user),
    lambda user, prefs: _build_medical_context(user),
    lambda user, prefs: _build_purpose_context(user),
    # v8 SA builder temporarily disabled for production stability debugging.
    # Re-enable after confirming 524 timeout root cause.
    # lambda user, prefs: _build_situational_awareness_context(user),
    # Phase 1: Personal Operating Context — reads pre-computed profile (single DB hit)
    lambda user, prefs: _build_operating_profile(user),
]


def _build_operating_profile(user):
    """
    Read the pre-computed Personal Operating Context for this user.

    This builder does ONE database lookup (no computation). The profile
    is pre-computed nightly by compute_operating_profiles_task. If the
    profile is missing or unreliable, returns empty dict — Beth operates
    exactly as before.

    Returns:
        dict with 'operating_profile' key containing the profile data,
        or empty dict if unavailable.
    """
    try:
        from apps.core.ai_state.models import UserOperatingProfile
        profile = UserOperatingProfile.objects.filter(user=user).first()
        if profile and profile.profile_data:
            return {
                'operating_profile': {
                    'data': profile.profile_data,
                    'sample_days': profile.sample_days,
                    'is_reliable': profile.is_reliable,
                    'last_computed': (
                        profile.last_computed.isoformat()
                        if profile.last_computed else None
                    ),
                },
            }
        return {}
    except Exception as e:
        logger.debug("CoS context: operating profile unavailable: %s", e)
        return {}


def _build_situational_awareness_context(user):
    """v8: Build situational awareness patterns for CoS pipeline."""
    try:
        from apps.ai.situational_awareness import build_situational_awareness
        sa_data = build_situational_awareness(user)
        if sa_data and sa_data.get('lines'):
            return {'situational_awareness': sa_data}
        return {}
    except Exception as e:
        logger.debug("CoS context: situational awareness unavailable: %s", e)
        return {}


def build_cos_context(user):
    """
    Assemble the full Chief of Staff operational context.

    Queries all relevant engines and assembles a structured dict
    that represents the user's current operational state.

    Uses parallel execution via ThreadPoolExecutor to minimize
    context rebuild latency. Falls back to sequential on error.

    Args:
        user: Django User instance.

    Returns:
        dict — Comprehensive CoS context.
    """
    import time as _time
    start = _time.monotonic()

    # Pre-load SAE snapshot so all builders share one DB hit
    try:
        from apps.core.ai_state.state_engine import get_user_state
        user._sae_cache = get_user_state(user)
    except Exception:
        user._sae_cache = None

    context = {
        '_user': user,
        'user_id': user.id,  # Survives cache (no _ prefix) for format_cos_system_injection
        'blueprint_state': {},
        'protected_tiers': [],
        'capacity_snapshot': {},
        'drift_probability': {},
        'forecast_load_24h': 0,
        'forecast_load_72h': 0,
        'override_frequency_14d': 0,
        'persona_profile': {},
        'module_permissions': {},
        'transformation_metrics': {},
        'active_fast_status': {},
        'medication_adherence_state': {},
        'alignment_score': 100,
        'drift_score': 0,
        'risk_warnings': [],
        'today_blocks_summary': [],
        'calendar_events_today': [],
        'deadline_snapshot': {},
    }

    prefs = user.preferences

    # Module permissions (trivial, always inline)
    context['module_permissions'] = {
        'health': prefs.health_enabled,
        'journal': prefs.journal_enabled,
        'faith': prefs.faith_enabled,
        'life': prefs.life_enabled,
        'purpose': prefs.purpose_enabled,
        'finance': prefs.finances_enabled,
        'capture': prefs.capture_enabled,
        'ai': prefs.ai_enabled,
        'personal_assistant': prefs.personal_assistant_enabled,
    }

    # Run all builders — parallel when possible, sequential on SQLite
    # (in-memory SQLite gives each thread a separate empty database)
    _use_threading = 'sqlite' not in settings.DATABASES.get(
        'default', {}
    ).get('ENGINE', '')

    if _use_threading:
        try:
            def _run_builder(builder_fn):
                """Execute a builder in a thread with proper DB connection handling."""
                try:
                    return builder_fn(user, prefs)
                finally:
                    # CRITICAL: Explicitly close this thread's DB connection.
                    # close_old_connections() only closes connections older than
                    # CONN_MAX_AGE (600s) — brand new thread connections stay open
                    # and exhaust the Railway PostgreSQL connection pool.
                    connection.close()

            with ThreadPoolExecutor(max_workers=_PARALLEL_MAX_WORKERS) as executor:
                futures = {
                    executor.submit(_run_builder, b): b
                    for b in _PARALLEL_BUILDERS
                }
                for future in as_completed(futures, timeout=10):
                    try:
                        updates = future.result(timeout=5)
                        if updates:
                            context.update(updates)
                    except Exception as e:
                        logger.debug("Parallel context builder failed: %s", e)

        except Exception as e:
            logger.warning(
                "Parallel context assembly failed, falling back to sequential: %s", e
            )
            for builder in _PARALLEL_BUILDERS:
                try:
                    updates = builder(user, prefs)
                    if updates:
                        context.update(updates)
                except Exception as be:
                    logger.debug("Sequential context builder failed: %s", be)
    else:
        for builder in _PARALLEL_BUILDERS:
            try:
                updates = builder(user, prefs)
                if updates:
                    context.update(updates)
            except Exception as be:
                logger.debug("Sequential context builder failed: %s", be)

    # =====================================================================
    # POST-ASSEMBLY (depends on composed context — must be sequential)
    # =====================================================================

    # Executive tone mode (depends on full context)
    context['executive_tone_mode'] = _determine_tone_mode(user, context)

    # Persistent escalation state (depends on trajectory_signals)
    try:
        from apps.core.blueprint.escalation_engine import resolve_activation_state
        context['trajectory_activation_state'] = resolve_activation_state(
            user,
            context.get('trajectory_signals', {}),
            user_input='',
        )
    except Exception as e:
        logger.debug("CoS context: escalation state unavailable: %s", e)
        context['trajectory_activation_state'] = ACTIVATION_CLEAN

    elapsed_ms = (_time.monotonic() - start) * 1000
    try:
        from apps.ai.readiness_telemetry import log_parallel_build
        log_parallel_build(user.id, elapsed_ms, len(_PARALLEL_BUILDERS))
    except Exception:
        pass

    # Cleanup per-request SAE cache
    user._sae_cache = None

    return context


def _format_health_intelligence_block(health_intel, context):
    """
    Format health intelligence as a LOCKED VALUES block for CoS injection.

    This block contains system-calculated, authoritative health metrics
    that the LLM must use verbatim — never generate its own ranges or estimates.

    Args:
        health_intel: dict from build_cos_health_intelligence() (subset stored in context)
        context: full CoS context dict (for protein_intelligence, etc.)

    Returns:
        str — formatted health intelligence block.
    """
    lines = []
    lines.append("=== HEALTH INTELLIGENCE (SYSTEM-CALCULATED — USE THESE EXACT VALUES) ===")
    lines.append("")
    lines.append(
        "MANDATORY: The values below are calculated by the WLJ Health Intelligence "
        "Engine from the user's ACTUAL data. When the user asks about ANY health "
        "metric listed here, you MUST quote THESE EXACT numbers. "
        "NEVER substitute generic ranges, textbook values, or LLM-generated estimates. "
        "If a value is missing below, say 'I don't have that data right now.'"
    )
    lines.append("")

    # ── HEALTH INTELLIGENCE STATUS (top-level enum snapshot) ──
    # These are the AUTHORITATIVE enum values from DailyHealthSummary.
    # When user asks for health intelligence status, fat loss phase, plateau
    # risk, or muscle preservation — respond with ONLY these enum values.
    # If user says "keep it short" respond in exactly this 4-line format:
    #   Fat loss phase: <ENUM>
    #   Plateau risk: <ENUM>
    #   Muscle preservation: <ENUM>
    #   Last updated: <date/time>
    body_comp = health_intel.get('body_comp', {})
    _hi_phase = body_comp.get('fat_loss_phase') or 'UNKNOWN (awaiting data)'
    _hi_plateau = body_comp.get('plateau_risk_label') or 'UNKNOWN (awaiting data)'
    _hi_muscle = body_comp.get('muscle_preservation_status') or 'UNKNOWN (awaiting data)'
    _hi_conf = body_comp.get('phase_confidence')
    _hi_date = body_comp.get('phase_start_date') or ''
    # Use last_computed from the DHS if available, otherwise summary_date
    _hi_updated = health_intel.get('last_computed') or ''

    lines.append("  HEALTH INTELLIGENCE STATUS (enum snapshot — QUOTE VERBATIM):")
    lines.append(f"    fat_loss_phase: {_hi_phase}")
    if _hi_conf:
        lines.append(f"    phase_confidence: {_hi_conf}%")
    lines.append(f"    plateau_risk_label: {_hi_plateau}")
    lines.append(f"    muscle_preservation_status: {_hi_muscle}")
    if _hi_updated:
        lines.append(f"    last_updated: {_hi_updated}")
    lines.append("")
    lines.append(
        "  STRICT RULE: When user asks 'What is my fat loss phase / plateau risk / "
        "muscle preservation?' — respond with ONLY the enum values above. "
        "Valid fat_loss_phase: RAPID_INITIAL_LOSS, STABLE_FAT_LOSS, RECOMPOSITION, PLATEAU, REBOUND_RISK. "
        "Valid plateau_risk_label: LOW, RISING, HIGH. "
        "Valid muscle_preservation_status: HIGH_QUALITY, MODERATE_QUALITY, MUSCLE_RISK. "
        "Do NOT paraphrase enums (e.g., 'stable' is NOT valid for muscle_preservation_status). "
        "If user says 'keep it short', output ONLY 4 lines: the 3 enum fields + last_updated. "
        "No schedule, no sleep, no suggestions, no extra content."
    )
    lines.append("")

    # Scores
    hs = health_intel.get('health_score')
    rs = health_intel.get('recovery_score')
    if hs is not None:
        lines.append(f"  Health Score: {hs}/100")
    if rs is not None:
        status = health_intel.get('recovery_status', '')
        status_str = f" ({status})" if status else ""
        lines.append(f"  Recovery Score: {rs}/100{status_str}")

    # Protein intelligence (LBM-aware targets)
    protein_intel = context.get('health_intelligence', {}).get('protein', {})
    # Also check for protein_intelligence at top level (from _build_health_and_vitals)
    if not protein_intel:
        # Try to get from the full health intelligence
        _user = context.get('_user')
        if _user:
            try:
                from apps.health.services.protein_service import ProteinService
                from django.utils import timezone as _tz
                _today = _tz.localdate()
                target_info = ProteinService.calculate_target(_user, _today)
                if target_info:
                    protein_intel = target_info
            except Exception:
                pass

    if protein_intel:
        lines.append("")
        lines.append("  PROTEIN TARGET (locked — do not estimate):")
        target_g = protein_intel.get('target_g')
        method = protein_intel.get('method', '')
        lbm = protein_intel.get('lbm')
        workout_day = protein_intel.get('workout_day', False)
        multiplier = protein_intel.get('multiplier')

        if target_g is not None:
            target_val = float(target_g) if not isinstance(target_g, float) else target_g
            lines.append(f"    Daily target: {target_val:.0f}g")
        if method:
            method_label = {
                'lean_body_mass': 'Based on lean body mass',
                'body_weight': 'Based on body weight',
                'override': 'User-set override',
            }.get(method, method)
            lines.append(f"    Method: {method_label}")
        if lbm is not None:
            lines.append(f"    Lean body mass: {float(lbm):.1f} lbs")
        if multiplier:
            lines.append(f"    Multiplier: {float(multiplier)}g per lb LBM")
        day_type = "workout day" if workout_day else "rest day"
        lines.append(f"    Day type: {day_type}")

        # Weekly protein evaluation (7-day average — THIS is what CoS must
        # use when answering "how's my protein this week?" questions)
        p_avg_7d = protein_intel.get('protein_avg_7d')
        p_gap_g = protein_intel.get('protein_gap_g')
        p_consistency = protein_intel.get('protein_consistency_pct')
        p_avg_ratio = protein_intel.get('protein_avg_ratio')
        if p_avg_7d is not None:
            lines.append("")
            lines.append("  PROTEIN WEEKLY EVALUATION (locked — use these for weekly questions):")
            pct = round(p_avg_ratio * 100) if p_avg_ratio else "?"
            lines.append(f"    7-day average intake: {p_avg_7d:.0f}g/day")
            lines.append(f"    % of daily target: {pct}%")
            if p_gap_g is not None and p_gap_g > 0:
                lines.append(f"    Daily gap: {p_gap_g:.0f}g below target")
            elif p_gap_g is not None and p_gap_g <= 0:
                lines.append(f"    Status: exceeding target by {abs(p_gap_g):.0f}g/day")
            if p_consistency is not None:
                lines.append(f"    Days hitting 80%+ target: {p_consistency:.0f}% of days")

    # Body composition intelligence (locked — pre-computed at rollup time)
    body_comp = health_intel.get('body_comp', {})
    if body_comp and body_comp.get('fat_loss_quality_label'):
        lines.append("")
        lines.append("  BODY COMPOSITION (locked — use these exact values):")

        # 14d deltas — pull from body_comp_drivers if available
        drivers = body_comp.get('body_comp_drivers', {})

        fl_label = body_comp.get('fat_loss_quality_label')
        fl_ratio = body_comp.get('fat_loss_ratio_14d')
        ratio_str = f" (ratio {fl_ratio:.2f})" if fl_ratio else ""
        lines.append(f"    Fat loss quality: {fl_label}{ratio_str}")

        if body_comp.get('recomposition_flag_14d'):
            lines.append("    Recomposition: Yes — fat decreasing, lean mass increasing")
        else:
            lines.append("    Recomposition: No")

        plateau = body_comp.get('plateau_status')
        if plateau and plateau != 'INSUFFICIENT_DATA':
            lines.append(f"    Plateau status: {plateau}")

        speed_label = body_comp.get('fat_loss_speed_label')
        speed_pct = body_comp.get('fat_loss_speed_pct_per_week')
        if speed_label and speed_label != 'INSUFFICIENT_DATA':
            speed_str = f" ({speed_pct:.1f}%/week)" if speed_pct else ""
            lines.append(f"    Fat loss speed: {speed_label}{speed_str}")

        risk_level = body_comp.get('muscle_loss_risk_level')
        risk_score = body_comp.get('muscle_loss_risk_score')
        if risk_level:
            score_str = f" (score {risk_score})" if risk_score is not None else ""
            lines.append(f"    Muscle loss risk: {risk_level}{score_str}")

        fat_mass = body_comp.get('fat_mass')
        if fat_mass:
            lines.append(f"    Current fat mass: {fat_mass:.1f} lbs")

        # Plateau early warning
        pr_label = body_comp.get('plateau_risk_label')
        pr_score = body_comp.get('plateau_risk_score')
        pr_window = body_comp.get('plateau_prediction_window_days')
        if pr_label and pr_label != 'LOW':
            window_str = f", est. {pr_window} days" if pr_window is not None else ""
            lines.append(f"    Plateau risk: {pr_label} (score {pr_score}{window_str})")

        # Fat loss phase
        phase = body_comp.get('fat_loss_phase')
        phase_conf = body_comp.get('phase_confidence')
        if phase:
            conf_str = f" ({phase_conf}% confidence)" if phase_conf else ""
            lines.append(f"    Fat loss phase: {phase}{conf_str}")

        # Muscle preservation
        mp_status = body_comp.get('muscle_preservation_status')
        if mp_status and mp_status != 'INSUFFICIENT_DATA':
            lines.append(f"    Muscle preservation: {mp_status}")

    # Trends summary
    summary_text = context.get('health_intelligence_summary', '')
    if summary_text:
        lines.append("")
        lines.append(f"  Intelligence summary: {summary_text}")

    # Strengths / weaknesses / risks
    strengths = health_intel.get('strengths', [])
    weaknesses = health_intel.get('weaknesses', [])
    risk_flags = health_intel.get('risk_flags', [])

    if strengths:
        lines.append(f"  Strengths: {'; '.join(strengths[:3])}")
    if weaknesses:
        lines.append(f"  Watch areas: {'; '.join(weaknesses[:3])}")
    if risk_flags:
        flags = risk_flags if isinstance(risk_flags[0], str) else [
            r.get('message', str(r)) for r in risk_flags
        ]
        lines.append(f"  Risk flags: {'; '.join(flags[:3])}")

    # Top recommendation
    rec = health_intel.get('top_recommendation', '')
    if rec:
        lines.append(f"  Focus: {rec}")

    # Correlations
    correlations = health_intel.get('correlations', [])
    if correlations:
        for c in correlations[:2]:
            interp = c.get('interpretation', '')
            if interp:
                lines.append(f"  Pattern: {interp}")

    lines.append("")
    lines.append("=== END HEALTH INTELLIGENCE ===")
    return '\n'.join(lines)


def _build_daily_scan_brief(context):
    """
    Build a structured daily scan brief for proactive intelligence.

    Summarizes the user's day in 4 categories:
    1. Completed — what's been done today
    2. Outstanding — what's overdue or not started
    3. Time-sensitive — what's coming in the next 4-6 hours
    4. Risk flags — patterns, drift, missed items

    Returns:
        str — formatted brief, or "" if insufficient data.
    """
    brief_lines = ["--- DAILY SCAN BRIEF ---"]
    has_content = False

    # 1. COMPLETED today
    completed_items = []
    blocks = context.get('today_blocks_summary', [])
    for b in blocks:
        if b.get('completed'):
            completed_items.append(b['title'])
    cal_events = context.get('calendar_events_today', [])
    for ev in cal_events:
        if ev.get('actual_status') == 'completed':
            completed_items.append(ev['title'])

    # Medication taken (with names if available)
    med = context.get('medication_adherence_state', {})
    pending_meds = context.get('pending_medications', [])
    taken = med.get('taken_today', 0)
    total_sched = med.get('total_scheduled', 0)
    taken_names = [m['name'] for m in pending_meds if m.get('status') == 'taken']
    if taken_names:
        completed_items.append(f"Medications: {', '.join(taken_names)}")
    elif taken > 0:
        completed_items.append(f"Medications: {taken}/{total_sched} taken")

    if completed_items:
        brief_lines.append(f"COMPLETED: {', '.join(completed_items[:6])}")
        has_content = True

    # 2. OUTSTANDING (overdue or not started)
    outstanding_items = []
    for b in blocks:
        if not b.get('completed') and not b.get('locked'):
            outstanding_items.append(b['title'])
    for ev in cal_events:
        if ev.get('is_overdue'):
            outstanding_items.append(f"{ev['title']} [OVERDUE]")

    # Missed/overdue medication doses (with names)
    overdue_meds = [m for m in pending_meds if m.get('status') == 'overdue']
    upcoming_meds = [m for m in pending_meds if m.get('status') == 'upcoming']
    if overdue_meds:
        med_names = ', '.join(m['name'] for m in overdue_meds)
        outstanding_items.append(f"Medications OVERDUE: {med_names}")
    elif total_sched > 0 and taken < total_sched:
        missed = total_sched - taken
        outstanding_items.append(f"Medications: {missed} dose(s) not yet taken")

    # Overdue goals
    loops = context.get('open_loops', {})
    overdue_goals = loops.get('overdue_goals', 0)
    if overdue_goals:
        outstanding_items.append(f"{overdue_goals} overdue goal(s)")

    if outstanding_items:
        brief_lines.append(f"OUTSTANDING: {', '.join(outstanding_items[:6])}")
        has_content = True

    # 3. TIME-SENSITIVE (upcoming in next 4-6 hours)
    time_sensitive = []
    for ev in cal_events:
        if ev.get('time_status') in ('upcoming_soon', 'in_progress'):
            tag = "[NOW]" if ev['time_status'] == 'in_progress' else "[SOON]"
            time_sensitive.append(f"{ev['title']} {tag}")
    for b in blocks:
        if not b.get('completed') and b.get('locked'):
            time_sensitive.append(f"{b['title']} [LOCKED]")

    # Approaching deadlines
    deadline = context.get('deadline_snapshot', {})
    if deadline.get('due_today'):
        time_sensitive.append(f"{deadline['due_today']} deadline(s) today")

    if time_sensitive:
        brief_lines.append(f"TIME-SENSITIVE: {', '.join(time_sensitive[:5])}")
        has_content = True

    # 4. RISK FLAGS
    risk_flags = []
    drift = context.get('drift_score', 0)
    if drift >= 30:
        risk_flags.append(f"Drift score: {drift}/100")

    # Active warning/critical insights
    insights = context.get('active_insights', [])
    for i in insights:
        if i.get('severity') in ('warning', 'critical'):
            risk_flags.append(i.get('title', i.get('message', '')))

    # Mood trend
    mood = context.get('mood_status', {})
    if mood.get('trend') in ('declining', 'decreasing'):
        risk_flags.append("Mood trend: declining")

    # Medication adherence risk
    adherence_pct = med.get('adherence_pct')
    if adherence_pct is not None and adherence_pct < 70:
        risk_flags.append(f"Medication adherence: {adherence_pct}%")

    if risk_flags:
        brief_lines.append(f"RISK FLAGS: {', '.join(risk_flags[:5])}")
        has_content = True

    if not has_content:
        # Always emit a scan brief — even if empty, signal that the scan ran
        # and no items were found. This prevents the LLM from falling back
        # to generic assistant behavior on greeting messages.
        brief_lines.append(
            "COMPLETED: (no items logged yet today)"
        )
        brief_lines.append(
            "OUTSTANDING: (no scheduled items found)"
        )
        brief_lines.append(
            "Note: Use the detailed operational data below to brief the user. "
            "Check health signals, calendar, and medication data for anything "
            "noteworthy even if it's not in this summary."
        )

    brief_lines.append("--- END SCAN BRIEF ---")
    return '\n'.join(brief_lines)


def _detect_session_mode(user):
    """
    Detect whether the user needs a Daily Brief or Light interaction mode.

    Returns 'daily_brief' if:
      - First CoS interaction of the day, OR
      - 4+ hours since the last assistant message

    Returns 'light' otherwise.
    """
    try:
        from apps.ai.models import AssistantMessage
        from django.utils import timezone as dj_tz
        import datetime as _dt

        now = dj_tz.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Find the most recent non-fallback assistant message for this user.
        # Fallback messages (message_type='fallback') are excluded so they
        # don't suppress the daily briefing on the next real interaction.
        last_msg = (
            AssistantMessage.objects
            .filter(
                conversation__user=user,
                role='assistant',
            )
            .exclude(message_type='fallback')
            .order_by('-created_at')
            .values_list('created_at', flat=True)
            .first()
        )

        if last_msg is None:
            # No prior messages ever — definitely a daily brief
            return 'daily_brief'

        if last_msg < today_start:
            # Last message was before today — first interaction of the day
            return 'daily_brief'

        hours_since = (now - last_msg).total_seconds() / 3600
        if hours_since >= 4:
            # 4+ hours since last interaction
            return 'daily_brief'

        return 'light'
    except Exception:
        # Default to daily_brief if detection fails — it's the safer option
        return 'daily_brief'


def _build_data_state_snapshot(user) -> str:
    """Build a structured data state snapshot showing record counts per domain.

    This tells the LLM exactly which data categories are empty vs populated,
    preventing hallucination of specific items from empty categories.

    v4: Added active_tasks and completed_tasks_today counts. Strengthened
    grounding rules with MUST enforcement. Covers all domains listed in
    the CoS evaluation.
    """
    counts = {}
    try:
        from apps.health.models import (
            WeightEntry, SleepEntry, MedicineLog, Medicine,
            FoodEntry, BloodPressureEntry, WorkoutSession,
        )
        from apps.purpose.models import LifeGoal
        from apps.journal.models import JournalEntry
        from apps.life.models import Task as LifeTask
        from apps.core.utils import get_user_today

        today = get_user_today(user)

        counts['weight_entries'] = WeightEntry.objects.filter(user=user).count()
        counts['sleep_entries'] = SleepEntry.objects.filter(user=user).count()
        counts['active_medications'] = Medicine.objects.filter(user=user).count()
        counts['nutrition_entries'] = FoodEntry.objects.filter(user=user).count()
        counts['blood_pressure_entries'] = BloodPressureEntry.objects.filter(user=user).count()
        counts['workout_sessions'] = WorkoutSession.objects.filter(user=user).count()
        counts['goals_defined'] = LifeGoal.objects.filter(user=user).count()
        counts['journal_entries'] = JournalEntry.objects.filter(user=user).count()
        # v4: Task counts — key for preventing "3 of 5 tasks" hallucination
        counts['active_tasks'] = LifeTask.objects.filter(
            user=user, completion_status='pending'
        ).exclude(status='deleted').count()
        counts['completed_tasks_today'] = LifeTask.objects.filter(
            user=user, completion_status='completed', completed_at__date=today
        ).exclude(status='deleted').count()
        # v5: Non-negotiable skip streak data for commitment tracking
        counts['non_negotiable_skip_streaks'] = LifeTask.objects.filter(
            user=user, commitment_level='non_negotiable',
            skip_streak__gte=2, status='active',
        ).count()
    except Exception as e:
        logger.warning("Failed to build data state snapshot: %s", e)
        return ""

    lines = [
        "========== AUTHORITATIVE DATA STATE ==========",
        "These are the EXACT record counts from the database.",
        "If a domain shows 0 records, you MUST NOT reference specific",
        "items from that domain. Violation = hallucination.",
    ]
    for key, count in counts.items():
        lines.append(f"  {key}: {count}")

    # Build explicit zero-data grounding rules
    zero_domains = [k for k, v in counts.items() if v == 0]
    if zero_domains:
        lines.append("")
        lines.append("ABSOLUTE GROUNDING RULES FOR ZERO-DATA DOMAINS:")
        lines.append(
            "If a domain shows 0 records you MUST NOT reference specific items "
            "from that domain. This is non-negotiable."
        )
        domain_examples = {
            'active_medications': "NEVER say 'medication is due' or 'make sure to take your meds'",
            'weight_entries': "NEVER mention a specific weight value or weight trend",
            'sleep_entries': "NEVER cite sleep hours or quality scores",
            'nutrition_entries': "NEVER reference meals, calories, or macros logged",
            'blood_pressure_entries': "NEVER cite blood pressure readings",
            'workout_sessions': "NEVER reference specific workout sessions completed",
            'goals_defined': "NEVER reference goals by name or count",
            'journal_entries': "NEVER reference journal entries or mood logs",
            'active_tasks': "NEVER say 'you completed X of Y tasks' or reference task names",
            'completed_tasks_today': "NEVER claim tasks were completed today if count is 0",
            'non_negotiable_skip_streaks': "User has no active non-negotiable skip streaks",
        }
        for domain in zero_domains:
            example = domain_examples.get(domain, f"NEVER reference specific {domain}")
            lines.append(f"  • {domain} = 0 → {example}")
        lines.append(
            "\nYou MAY suggest the user start tracking these domains, "
            "but NEVER imply data exists when it does not."
        )

    # Add non-negotiable skip streak awareness
    nn_streak_count = counts.get('non_negotiable_skip_streaks', 0)
    if nn_streak_count > 0:
        lines.append("")
        lines.append("NON-NEGOTIABLE COMMITMENT AWARENESS:")
        lines.append(
            f"  User has {nn_streak_count} non-negotiable task(s) with consecutive skips (2+). "
            "These are tasks the user considers essential. Approach with supportive coaching, "
            "not judgment. Ask what's blocking them if they bring it up."
        )

    lines.append("========== END DATA STATE ==========")
    return "\n".join(lines)


def _format_operating_profile_injection(profile_data):
    """
    Format the Personal Operating Context as a concise prompt block.

    Converts structured profile_data into behavioral observations
    that Beth can reference when framing guidance. Output is capped at
    ~300-500 tokens. Does NOT inject raw data — only interpreted signals.

    Each dimension is gated by its own confidence threshold (from model
    constants). Language certainty scales with confidence:
      ≥0.80 → "Your data consistently shows…"
      0.60-0.79 → "It looks like…"
      0.40-0.59 → "There may be a pattern where…"

    Args:
        profile_data: dict from UserOperatingProfile.profile_data

    Returns:
        str — formatted profile block, or empty string if nothing to inject.
    """
    from apps.core.ai_state.models import UserOperatingProfile

    gates = UserOperatingProfile.CONFIDENCE_GATES
    sections = []

    # ── Productive Windows ──
    pw = profile_data.get('productive_windows', {})
    pw_conf = pw.get('confidence', 0)
    if pw_conf >= gates.get('productive_windows', 0.60) and pw.get('peak_hours'):
        peak = pw['peak_hours']
        peak_strs = [f"{_hour_label(h)}" for h in peak[:3]]
        qualifier = _confidence_qualifier(pw_conf)
        section = f"{qualifier} peak activity hours are around {', '.join(peak_strs)}"
        if pw.get('low_hours'):
            low_strs = [f"{_hour_label(h)}" for h in pw['low_hours'][:2]]
            section += f", with lower activity around {', '.join(low_strs)}"
        sections.append(section)

    # ── Deferral Patterns ──
    dp = profile_data.get('deferral_patterns', {})
    dp_conf = dp.get('confidence', 0)
    if dp_conf >= gates.get('deferral_patterns', 0.60):
        rate = dp.get('overall_deferral_rate', 0)
        if rate >= 0.15:  # Only mention if deferral is notable
            qualifier = _confidence_qualifier(dp_conf)
            parts = []
            parts.append(
                f"{qualifier} about {rate:.0%} of tasks tend to be skipped rather than completed"
            )
            # Prone modules
            prone = dp.get('prone_modules', [])
            if prone:
                module_strs = [
                    f"{m['module']} (~{m['deferral_rate']:.0%})"
                    for m in prone[:2]
                ]
                parts.append(f"particularly in: {', '.join(module_strs)}")
            # Intervention response
            dismiss_rate = dp.get('intervention_dismiss_rate', 0)
            if dismiss_rate >= 0.3:
                parts.append(
                    f"coaching nudges appear to be dismissed about {dismiss_rate:.0%} "
                    f"of the time"
                )
            sections.append('. '.join(parts))

    # ── Momentum Phase ──
    mp = profile_data.get('momentum_phase', {})
    mp_conf = mp.get('confidence', 0)
    if (
        mp_conf >= gates.get('momentum_phase', 0.40)
        and mp.get('current_phase') != 'insufficient_data'
    ):
        phase = mp['current_phase']
        recent = mp.get('recent_active_days', 0)
        domains = mp.get('active_domain_count', 0)
        qualifier = _confidence_qualifier(mp_conf)

        phase_labels = {
            'building': 'momentum is building — recent activity exceeds the baseline',
            'sustaining': 'activity appears steady and consistent',
            'declining': 'recent activity appears to be below the usual baseline',
            'recovering': 'activity is significantly below normal levels',
        }
        phase_text = phase_labels.get(phase, f"current phase: {phase}")
        section = f"{qualifier} {phase_text}"
        section += f" ({recent}/7 active days this week across {domains} domains)"
        sections.append(section)

    # ── Behavior Drift (if detected) ──
    drift = profile_data.get('behavior_drift', {})
    if drift.get('detected') and drift.get('signals'):
        for signal in drift['signals'][:2]:  # Cap at 2 drift observations
            summary = signal.get('summary', '')
            if summary:
                sections.append(f"Recent shift detected: {summary}")

    if not sections:
        return ""

    # Assemble with Beth directive
    lines = []
    lines.append("=== USER OPERATING PROFILE (behavioral context) ===")
    lines.append("")
    for s in sections:
        lines.append(f"• {s}")
    lines.append("")
    lines.append(
        "HOW TO USE THIS PROFILE:\n"
        "- Frame timing suggestions around observed peak hours\n"
        "- Flag deferral-prone tasks proactively when scheduling\n"
        "- Adjust tone and urgency based on momentum phase\n"
        "- Reference drift observations when coaching on behavioral changes\n"
        "- This profile influences HOW you frame guidance — "
        "it does NOT override task priorities, insights, or predictions\n"
        "\n"
        "LANGUAGE RULE: Behavioral observations are patterns, not diagnoses. "
        "Frame them as observations ('It looks like…', 'Your data suggests…'). "
        "Never state behavioral patterns as definitive facts. "
        "The user's experience of their own behavior is the authority — "
        "these patterns are conversation context, not conclusions."
    )
    lines.append("")
    lines.append("=== END OPERATING PROFILE ===")
    return "\n".join(lines)


def _confidence_qualifier(confidence):
    """
    Return a language qualifier scaled to confidence level.

    Higher confidence → more direct language.
    Lower confidence → more tentative framing.

    This prevents Beth from stating low-confidence patterns as facts,
    while allowing her to be authoritative when the data is strong.
    """
    if confidence >= 0.80:
        return "Your data consistently shows"
    elif confidence >= 0.60:
        return "It looks like"
    else:
        return "There may be a pattern where"


def _hour_label(hour):
    """Convert 24h hour int to readable label. e.g., 14 → '2 PM'."""
    if hour == 0:
        return "12 AM"
    elif hour < 12:
        return f"{hour} AM"
    elif hour == 12:
        return "12 PM"
    else:
        return f"{hour - 12} PM"


def format_cos_system_injection(context):
    """
    Format the CoS context as a system prompt injection string.

    This string is prepended to the LLM system prompt so the model
    always has full operational awareness.

    During Learning Mode, delegates to format_learning_mode_injection()
    for a lighter context profile.

    Args:
        context: dict from build_cos_context() or build_learning_mode_context()

    Returns:
        str — formatted system injection block.
    """
    # Learning Mode: use reduced profile
    if context.get('learning_mode'):
        return format_learning_mode_injection(context)

    # Resolve user for cached contexts where _user was stripped.
    # build_cos_context stores user_id (no _ prefix) so it survives caching.
    _cache_hit = '_user' not in context
    if _cache_hit and 'user_id' in context:
        from django.contrib.auth import get_user_model
        _UserModel = get_user_model()
        try:
            context['_user'] = _UserModel.objects.get(id=context['user_id'])
        except _UserModel.DoesNotExist:
            pass

    lines = []

    # ── CoS SITUATION AWARENESS (highest priority) ──
    # Pre-computed by scheduled task every 15 minutes. This is the
    # single most important context block — it tells CoS what to
    # focus on without requiring the LLM to interpret 50+ raw signals.
    _cos_user = context.get('_user')
    _situation_loaded = False
    if _cos_user:
        try:
            from apps.core.ai_state.models import CoSSituationState
            sit = CoSSituationState.objects.filter(user=_cos_user).first()
            if sit and sit.dominant_concern:
                _situation_loaded = True
                lines.append("=== CoS SITUATION AWARENESS (PRE-COMPUTED) ===")
                lines.append("")
                lines.append(
                    f"SITUATION MODE: {sit.get_situation_mode_display()}"
                )
                if sit.opening_sentence:
                    lines.append(
                        f"OPENING FRAME: {sit.opening_sentence}"
                    )
                lines.append(
                    f"DOMINANT CONCERN: {sit.dominant_concern}"
                )
                if sit.top_priority:
                    lines.append(
                        f"TOP PRIORITY: {sit.top_priority}"
                    )
                if sit.changes_since_last_interaction:
                    change_strs = [
                        c.get('what', '') for c in sit.changes_since_last_interaction[:5]
                        if isinstance(c, dict)
                    ]
                    if change_strs:
                        lines.append(
                            f"CHANGES SINCE LAST INTERACTION: {'; '.join(change_strs)}"
                        )
                if sit.escalations:
                    esc_strs = [
                        e.get('description', '') for e in sit.escalations[:3]
                        if isinstance(e, dict)
                    ]
                    if esc_strs:
                        lines.append(
                            f"ESCALATIONS: {'; '.join(esc_strs)}"
                        )
                if sit.resolutions:
                    res_strs = [
                        r.get('description', '') for r in sit.resolutions[:3]
                        if isinstance(r, dict)
                    ]
                    if res_strs:
                        lines.append(
                            f"RESOLUTIONS: {'; '.join(res_strs)}"
                        )
                lines.append(
                    "DIRECTIVE: Your response MUST reference the dominant concern "
                    "above. If the user's question is unrelated, address their "
                    "question first, then briefly acknowledge the concern. "
                    "The opening frame above is a suggested natural-language start."
                )
                lines.append("")
                lines.append("=== END SITUATION AWARENESS ===")
                lines.append("")
            else:
                logger.warning(
                    "COS_SITUATION_EMPTY user=%s — SituationState row %s",
                    context.get('user_id', 'unknown'),
                    'exists_no_concern' if sit else 'missing',
                )
        except Exception as e:
            logger.warning(
                "COS_SITUATION_ERROR user=%s error=%s",
                context.get('user_id', 'unknown'), e,
            )
    else:
        logger.warning(
            "COS_SITUATION_SKIP user=%s — no _user in context (cache bug?)",
            context.get('user_id', 'unknown'),
        )

    logger.info(
        "COS_PROMPT_SITUATION user=%s cache_hit=%s situation_loaded=%s",
        context.get('user_id', 'unknown'), _cache_hit, _situation_loaded,
    )

    lines.append("=== OPERATIONAL INTELLIGENCE ===")
    lines.append("")
    lines.append(
        "CRITICAL DIRECTIVE: You have REAL DATA about this person's day, tasks, "
        "medications, events, goals, and habits below. When they ask about their "
        "day, schedule, status, what to do, what's next, or anything about their "
        "current situation — you MUST respond using THIS SPECIFIC DATA. "
        "NEVER give generic advice (like 'consider your morning routine' or "
        "'think about your schedule') when you have ACTUAL named items. "
        "Reference their tasks by name, their medications by name, their events "
        "by time, their goals by title. You are their Chief of Staff — you KNOW "
        "their world. Act like it."
    )
    lines.append("")
    lines.append(
        "CONTEXT RELEVANCE FILTER: Operational data (schedule, medication status, "
        "task counts, raw health metrics) is REFERENCE MATERIAL — use it when the "
        "user asks or when it directly answers their question. Do NOT attach "
        "schedule updates, medication reminders, or task counts to unrelated "
        "responses.\n"
        "EXCEPTION — INTELLIGENCE SIGNALS: Pattern detections, cross-domain "
        "correlations, trajectory predictions, and drift warnings are PROACTIVE "
        "intelligence. When a meaningful signal exists (warning, critical, or "
        "strong correlation), you SHOULD lead with it briefly, even if the user "
        "didn't ask. This is what a Chief of Staff does — surface what matters."
    )
    lines.append("")
    lines.append(
        "HONESTY RULE: ONLY state facts that appear in the data below. "
        "If a data point is missing from this context, say 'I don't have that "
        "data right now' — NEVER guess, estimate, or echo back a number the user "
        "mentioned as if you looked it up. Wrong data destroys trust. "
        "Saying 'I don't have that' is ALWAYS better than making something up."
    )
    lines.append("")
    lines.append(
        "LINK & LIST FORMATTING: When listing tasks, events, or items, ALWAYS "
        "use a consistent bulleted list with markdown. When referencing an app "
        "page, use a markdown link with the RELATIVE path from the APP NAVIGATION "
        "section below — e.g., [view your tasks](/life/tasks/). "
        "NEVER invent URLs. NEVER use absolute URLs with a domain. "
        "If there is no matching page in APP NAVIGATION, do not include a link."
    )
    lines.append("")
    lines.append(
        "SCHEDULE AWARENESS: You have the user's schedule below for reference. "
        "Use it ONLY when relevant to what the user is asking or during daily "
        "orientation. Do NOT proactively inject schedule information into every "
        "response — only mention schedule items when: (1) the user asks about "
        "their schedule, tasks, or what to do next, (2) you are delivering the "
        "daily orientation, or (3) the user is reporting completion of a scheduled "
        "activity. If the user asks about an unrelated topic (a question, analysis, "
        "or general conversation), do NOT append schedule updates. A good Chief of "
        "Staff knows when to surface information and when to stay focused on "
        "the question at hand."
    )
    lines.append("")

    # ── PART 3: Chief of Staff Reasoning Hierarchy (v6 — operational eval) ──
    lines.append(
        "=== MANDATORY CONTEXT EVALUATION (v7) ===\n"
        "BEFORE generating ANY response, you MUST complete these steps internally:\n"
        "\n"
        "STEP 1 — READ the Data State Snapshot. Note exact counts for every domain.\n"
        "STEP 2 — READ the user's goals and declared priorities.\n"
        "STEP 3 — CHECK tasks due today and overdue tasks.\n"
        "STEP 4 — CHECK time of day and hours remaining.\n"
        "STEP 5 — SCAN for outstanding commitments: workout, routines, habits.\n"
        "STEP 6 — NOTE any missing data domains (no weight, no sleep, no goals, etc.).\n"
        "STEP 7 — READ the Situational Awareness Summary (if present). Note momentum, "
        "drift, one-off sensitive domains, and emotional context.\n"
        "STEP 8 — EVALUATE INTELLIGENCE SIGNALS: Scan the PROACTIVE INTELLIGENCE "
        "section below. Is there a critical insight, elevated drift, strong "
        "correlation, or high-confidence prediction? If yes, determine the SINGLE "
        "most important signal to surface. If multiple signals are related, "
        "synthesize them into one narrative.\n"
        "\n"
        "Only AFTER completing all steps, generate your response using this "
        "reasoning hierarchy:\n"
        "1. Use PROACTIVE INTELLIGENCE first — surface the most important signal\n"
        "2. Use DIRECT USER DATA if available (exact values from context above)\n"
        "3. Use DERIVED INTELLIGENCE (health intelligence summaries, pattern insights)\n"
        "4. Use BEHAVIORAL FORECASTS (completion probabilities, drift risk)\n"
        "5. Use LIFE PRIORITIES and identity context (ranked priorities, non-negotiables)\n"
        "6. Use GENERAL EXPERTISE — BUT ONLY grounded in the user's actual situation\n"
        "7. If information is still missing, ACKNOWLEDGE the gap and suggest tracking\n"
        "\n"
        "CRITICAL: Even when data is sparse, you still have: time of day, "
        "task counts, workout status, goal status, and what\\'s NOT yet logged. "
        "A response like 'You have 1 active task, no workout logged yet, and "
        "no goals defined — the highest-impact move is setting a goal' is "
        "ALWAYS better than generic advice.\n"
        "\n"
        "ANTI-TEMPLATE RULE: If your response could apply to ANY user without "
        "modification, it is generic and MUST be rewritten. Test: does it "
        "reference the user\\'s actual task count, workout status, goal state, "
        "or time context? If not, rewrite it.\n"
        "=== END MANDATORY CONTEXT EVALUATION ==="
    )
    lines.append("")

    # ── PART 4: Strengthened Context Relevance Rule ──
    lines.append(
        "=== CONTEXT RELEVANCE ENFORCEMENT ===\n"
        "Do NOT inject unrelated OPERATIONAL reminders into responses.\n"
        "Examples of violations:\n"
        "  • A question about sleep science → Do NOT append task reminders\n"
        "  • A question about nutrition → Do NOT append medication schedules\n"
        "  • A general knowledge question → Do NOT append schedule updates\n"
        "\n"
        "EXCEPTION — Intelligence signals ARE allowed proactively:\n"
        "  • A 'good morning' greeting → You MAY lead with a meaningful pattern "
        "or drift observation before asking how to help\n"
        "  • A progress update → You MAY connect it to a relevant correlation "
        "or prediction\n"
        "  • Any conversation → You MAY briefly note a critical or warning-level "
        "insight if it affects the user's well-being\n"
        "\n"
        "The distinction: Operational data (task lists, med schedules, raw metrics) "
        "is reference material — use on request. Intelligence signals (patterns, "
        "correlations, drift, predictions) are proactive awareness — surface when "
        "meaningful.\n"
        "=== END CONTEXT RELEVANCE ==="
    )
    lines.append("")

    # ── PART 5: Sparse Data Behavior ──
    lines.append(
        "=== SPARSE DATA BEHAVIOR ===\n"
        "When user data is limited or missing, do NOT fall back to generic responses.\n"
        "Instead, follow this pattern:\n"
        "1. Acknowledge the missing data specifically\n"
        "2. Explain why tracking that data matters for THEIR priorities\n"
        "3. Provide guidance based on their life priorities and available context\n"
        "4. Offer the next best action with a link to the relevant app page\n"
        "\n"
        "Example — BAD: 'I don't have weight data.'\n"
        "Example — GOOD: 'You haven't logged weight yet. Since Health Discipline "
        "is one of your top priorities, getting a baseline weight logged would be "
        "a strong first step. Head to [Weight Tracking](/health/weight/) to start.'\n"
        "=== END SPARSE DATA BEHAVIOR ==="
    )
    lines.append("")

    # Language rules (what terms to avoid)
    try:
        from apps.core.ai_governance.language_rules import build_language_rules_injection
        lang_rules = build_language_rules_injection()
        if lang_rules:
            lines.append(lang_rules)
            lines.append("")
    except Exception:
        pass

    # ── USER-AFFIRMED COMPLETIONS ──
    # When a user states they already completed an activity, suppress all
    # further reminders for that activity type in this conversation.
    # Authority hierarchy: user statement overrides system assumptions.
    affirmed = context.get('affirmed_completions', {})
    if affirmed:
        lines.append("=== USER-AFFIRMED COMPLETIONS ===")
        lines.append("")
        lines.append(
            "The user has STATED they already completed these activities. "
            "Do NOT re-prompt, remind, nudge, or ask about them again in "
            "this conversation. Trust the user's word — they are the "
            "authority on what they have done."
        )
        lines.append("")
        for activity_type, affirmed_at in affirmed.items():
            # Show just the time portion for readability
            time_part = affirmed_at.split('T')[1][:5] if 'T' in affirmed_at else affirmed_at
            lines.append(f"  - {activity_type} (affirmed at {time_part})")
        lines.append("")
        lines.append(
            "If the user explicitly asks you to RECORD or LOG the "
            "completion, use the appropriate intent. But do NOT do so "
            "automatically — only suppress further reminders."
        )
        lines.append("")
        lines.append("=== END USER-AFFIRMED COMPLETIONS ===")
        lines.append("")

    # ── HEALTH SCREENSHOT ANALYSIS (PIE) ──
    # When a health screenshot was analyzed by PIE, inject the structured
    # interpretation so Beth responds with reasoning, not data recitation.
    health_analysis = context.get('health_screenshot_analysis')
    if health_analysis:
        lines.append("=== HEALTH SCREENSHOT ANALYSIS (PIE) ===")
        lines.append("")
        lines.append(f"Summary: {health_analysis.get('summary_insight', '')}")
        lines.append("")
        observations = health_analysis.get('observations', [])
        if observations:
            lines.append("Key Observations:")
            for obs in observations:
                lines.append(f"  - {obs}")
            lines.append("")
        implications = health_analysis.get('implications', [])
        if implications:
            lines.append("What This Means for This Person:")
            for imp in implications:
                lines.append(f"  - {imp}")
            lines.append("")
        recommendation = health_analysis.get('recommendation', '')
        if recommendation:
            lines.append(f"Recommendation: {recommendation}")
            lines.append("")
        lines.append(
            "INSTRUCTION: Use this analysis to give a REASONING response. "
            "Do NOT just repeat numbers — interpret them. Connect every "
            "observation to what it means for this person's health and goals. "
            "Give ONE clear recommendation."
        )
        disclaimer = health_analysis.get('medical_disclaimer', '')
        if disclaimer:
            lines.append(f"\n{disclaimer}")
        lines.append("")
        lines.append("=== END HEALTH SCREENSHOT ANALYSIS ===")
        lines.append("")

    # ── DAILY SCAN BRIEF (structured summary for proactive intelligence) ──
    scan_brief = _build_daily_scan_brief(context)
    if scan_brief:
        lines.append(scan_brief)
        lines.append("")

    # ── SESSION MODE (situation-aware, replaces binary daily_brief/light) ──
    _cos_user = context.get('_user')
    if _cos_user:
        try:
            # Try situation-aware mode first (from CoSSituationState)
            _situation_mode = None
            try:
                from apps.core.ai_state.models import CoSSituationState
                sit = CoSSituationState.objects.filter(user=_cos_user).first()
                if sit:
                    _situation_mode = sit.situation_mode
            except Exception:
                pass

            # Fall back to legacy binary detection if situation model not available
            _legacy_mode = _detect_session_mode(_cos_user)

            _SESSION_MODE_INSTRUCTIONS = {
                CoSSituationState.MODE_MORNING_ORIENTATION: (
                    "SESSION MODE: MORNING ORIENTATION. "
                    "This is the first interaction today or a significant gap. "
                    "Deliver the full Daily Brief naturally: acknowledge progress, "
                    "state outstanding items, identify the most time-sensitive thing, "
                    "suggest one priority focus, and ask one high-leverage question. "
                    "After this message, switch to a lighter conversational mode."
                ),
                CoSSituationState.MODE_MIDDAY_CHECKPOINT: (
                    "SESSION MODE: MIDDAY CHECKPOINT. "
                    "Half the day is done. Briefly acknowledge morning progress, "
                    "highlight what's still pending, and suggest the most impactful "
                    "next action. Keep it concise — the user is mid-flow."
                ),
                CoSSituationState.MODE_AFTERNOON_FOCUS: (
                    "SESSION MODE: AFTERNOON FOCUS. "
                    "Productive hours are winding down. Focus on what can still "
                    "be completed today. Deprioritize non-essentials. If the user "
                    "is on track, acknowledge it briefly and don't over-coach."
                ),
                CoSSituationState.MODE_EVENING_REVIEW: (
                    "SESSION MODE: EVENING REVIEW. "
                    "The day is winding down. Reflect on what was accomplished, "
                    "note what carries over to tomorrow, and offer a brief evening "
                    "check-in. Warm, low-pressure tone."
                ),
                CoSSituationState.MODE_WEEKEND_REFLECTION: (
                    "SESSION MODE: WEEKEND REFLECTION. "
                    "It's the weekend. Keep professional urgency low. Focus on "
                    "personal reflection, relationship time, and recovery. Only "
                    "flag truly time-sensitive items."
                ),
                CoSSituationState.MODE_URGENT_INTERVENTION: (
                    "SESSION MODE: URGENT INTERVENTION. "
                    "A critical signal has been detected (missed medication, "
                    "deadline breach, health alert). Lead with the urgent item "
                    "immediately — do not bury it in a general briefing. Be direct "
                    "and action-oriented."
                ),
                CoSSituationState.MODE_CELEBRATION: (
                    "SESSION MODE: CELEBRATION. "
                    "The user has achieved something noteworthy. Acknowledge it "
                    "genuinely and specifically — name the achievement. Then "
                    "transition naturally to what's next."
                ),
                CoSSituationState.MODE_RECOVERY: (
                    "SESSION MODE: RECOVERY. "
                    "The user is in recovery mode. Reduce expectations, focus on "
                    "essentials only, and use an encouraging but low-pressure tone. "
                    "Protect non-negotiables but defer everything else."
                ),
            }

            if _situation_mode and _situation_mode in _SESSION_MODE_INSTRUCTIONS:
                lines.append(_SESSION_MODE_INSTRUCTIONS[_situation_mode])
            elif _legacy_mode == 'daily_brief':
                lines.append(
                    "SESSION MODE: DAILY ORIENTATION. "
                    "This is the first interaction today or 4+ hours have passed. "
                    "Deliver the full Daily Brief naturally: acknowledge progress, "
                    "state outstanding items, identify the most time-sensitive thing, "
                    "suggest one priority focus, and ask one high-leverage question. "
                    "After this message, switch to LIGHT mode for the rest of the session."
                )
            else:
                lines.append(
                    "SESSION MODE: LIGHT. "
                    "The daily brief has already been delivered this session. "
                    "Respond conversationally — answer questions directly, "
                    "weave in awareness naturally, but do NOT repeat the full orientation. "
                    "Exception: if a consistency violation or drift pattern is detected, "
                    "intervene regardless of session mode."
                )
            lines.append("")
        except Exception:
            pass

    # ── COACHING MODE (adaptive mode for this interaction) ──
    if _cos_user:
        try:
            from apps.cos.services.tone_service import CosToneService
            _tone_svc = CosToneService(_cos_user)
            _coaching_instruction = _tone_svc.build_coaching_mode_injection(
                cos_context=context,
            )
            if _coaching_instruction:
                lines.append(_coaching_instruction)
                lines.append("")
        except Exception:
            pass

    # ── USER OPERATING PROFILE (Personal Operating Context — Phase 1) ──
    # Pre-computed behavioral synthesis. Influences HOW Beth frames guidance,
    # not WHAT she decides. Only injected when sample_days >= 14.
    op_profile = context.get('operating_profile', {})
    if op_profile.get('is_reliable') and op_profile.get('data'):
        try:
            _profile_block = _format_operating_profile_injection(op_profile['data'])
            if _profile_block:
                lines.append(_profile_block)
                lines.append("")
        except Exception:
            logger.debug("CoS context: operating profile injection failed", exc_info=True)

    # What matters to this person (compact)
    bp = context.get('blueprint_state', {})
    protected = context.get('protected_tiers', [])
    if protected:
        lines.append(f"Non-Negotiable Commitments: {', '.join(protected)}")
    pillars = bp.get('pillars_ranked', []) if bp else []
    if pillars:
        lines.append(f"Life Priorities (ranked): {', '.join(pillars)}")

    # Medication (actionable — user needs to know, with names)
    med = context.get('medication_adherence_state', {})
    pending_meds = context.get('pending_medications', [])
    if pending_meds:
        overdue = [m for m in pending_meds if m['status'] == 'overdue']
        upcoming = [m for m in pending_meds if m['status'] == 'upcoming']
        taken_meds = [m for m in pending_meds if m['status'] == 'taken']
        parts = []
        if taken_meds:
            taken_str = ', '.join(m['name'] for m in taken_meds)
            parts.append("Taken: " + taken_str)
        if overdue:
            overdue_items = []
            for m in overdue:
                label = m['name'] + (" (due " + m['scheduled_time'] + ")" if m['scheduled_time'] else "")
                overdue_items.append(label)
            parts.append("OVERDUE: " + ', '.join(overdue_items))
        if upcoming:
            upcoming_items = []
            for m in upcoming:
                label = m['name'] + (" (" + m['scheduled_time'] + ")" if m['scheduled_time'] else "")
                upcoming_items.append(label)
            parts.append("Upcoming: " + ', '.join(upcoming_items))
        lines.append("Medication: " + ' | '.join(parts))
    elif med and med.get('total_scheduled', 0) > 0:
        lines.append(f"Medication: {med.get('taken_today', 0)}/{med.get('total_scheduled', 0)} "
                     f"taken today")

    # Active fast (actionable)
    fast = context.get('active_fast_status', {})
    if fast.get('active'):
        lines.append(f"Active Fast: In progress (target: {fast.get('target_hours', 0)}h)")

    # Today's schedule blocks (with temporal awareness)
    # IMPORTANT: Schedule blocks show what was PLANNED, not necessarily what
    # was DONE. A block in the past without [done] tag was scheduled but may
    # not have been completed. Only blocks explicitly marked [done] are confirmed.
    # NEVER assume a past-time block was completed just because the time has passed.
    blocks = context.get('today_blocks_summary', [])
    if blocks:
        lines.append("")
        lines.append("Today's Schedule (PLANNED blocks — only [done] means completed):")
        now = timezone.localtime()
        current_time = now.time()
        current_block_title = None
        next_block_title = None
        next_block_time = None
        for b in blocks[:8]:
            # Determine temporal status
            if b['completed']:
                status = "[done]"
            elif b['locked']:
                status = "[locked]"
            else:
                status = ""
            # Add NOW/NEXT tags for non-completed blocks
            if not b['completed'] and b['start'] and b['end']:
                try:
                    b_start = datetime.datetime.strptime(b['start'], '%H:%M').time()
                    b_end = datetime.datetime.strptime(b['end'], '%H:%M').time()
                    if b_start <= current_time <= b_end:
                        status = "[NOW]" + (" [locked]" if b['locked'] else "")
                        current_block_title = b['title']
                    elif not current_block_title and not next_block_title and current_time < b_start:
                        status = "[NEXT]" + (" [locked]" if b['locked'] else "")
                        next_block_title = b['title']
                        next_block_time = b['start']
                    elif current_time > b_end:
                        # Past block NOT marked done — explicitly label it
                        status = "[not completed]"
                except (ValueError, TypeError):
                    pass
            lines.append(f"  {b['start']}-{b['end']} {b['title']} {status}")

        # Add explicit current focus section
        if current_block_title:
            lines.append("")
            lines.append(f"RIGHT NOW: User should be doing '{current_block_title}'.")
            if next_block_title:
                lines.append(f"NEXT UP: '{next_block_title}' at {next_block_time}.")
        elif next_block_title:
            lines.append("")
            lines.append(f"NEXT UP: '{next_block_title}' at {next_block_time}.")

    # Calendar events (what's happening today)
    cal_events = context.get('calendar_events_today', [])
    if cal_events:
        lines.append("")
        lines.append("Today's Calendar:")
        for ev in cal_events:
            status_tag = ""
            if ev.get('actual_status') == 'completed':
                status_tag = " [done]"
            elif ev['time_status'] == 'in_progress':
                status_tag = " [NOW]"
            elif ev['time_status'] == 'upcoming_soon':
                status_tag = " [SOON]"
            elif ev['is_overdue']:
                status_tag = " [MISSED]"
            ev_protected = " (protected)" if ev.get('is_protected') else ""
            lines.append(
                f"  {ev['start']}-{ev['end']} {ev['title']}"
                f"{ev_protected}{status_tag}"
            )

    # ── PROACTIVE INTELLIGENCE SIGNALS ──
    # These are pattern-level findings from the intelligence engines.
    # Unlike operational data (schedule, meds, tasks), intelligence signals
    # should be surfaced PROACTIVELY when they are meaningful.

    # Intelligence status — tells CoS if awareness is complete or degraded
    intel_status = context.get('intelligence_status', 'full')
    if intel_status == 'degraded':
        lines.append("")
        lines.append(
            "INTELLIGENCE STATUS: DEGRADED — Some intelligence engines failed to "
            "load. Pattern data may be incomplete. Avoid strong conclusions about "
            "trends or correlations in this session. Stick to direct observational "
            "data (schedule, medications, tasks)."
        )
    elif intel_status == 'partial':
        failed = context.get('intelligence_sources_failed', [])
        lines.append("")
        lines.append(
            f"INTELLIGENCE STATUS: PARTIAL — {', '.join(failed)} unavailable. "
            "Other intelligence sources are active."
        )

    # Collect all signals for priority-ranked synthesis
    insights = context.get('active_insights', [])
    predictions = context.get('active_predictions', [])
    guidance = context.get('active_guidance', [])
    correlations = context.get('cross_domain_correlations', [])
    drift = context.get('drift_score', 0)

    has_any_intelligence = (
        insights or predictions or guidance or correlations or drift >= 30
    )

    if has_any_intelligence:
        lines.append("")
        lines.append(
            "=== PROACTIVE INTELLIGENCE (surface the most important signal) ===\n"
            "You are a Chief of Staff reviewing a life dashboard. BEFORE responding "
            "to ANY message, evaluate the intelligence signals below and determine "
            "if one warrants proactive mention.\n"
            "\n"
            "PRIORITY ORDER (surface the SINGLE most important signal):\n"
            "  1. CRITICAL health or compliance risk (severity=critical)\n"
            "  2. High drift (score >= 40) — the user is sliding off track\n"
            "  3. Strong cross-domain correlations — connected life patterns\n"
            "  4. High-confidence predictions — trajectory concerns\n"
            "  5. Warning-level insights — emerging patterns worth noting\n"
            "  6. Guidance recommendations — suggested next actions\n"
            "\n"
            "HOW TO SURFACE intelligence:\n"
            "  - Lead with ONE synthesized insight, not a list of signals\n"
            "  - Connect related signals into a narrative (e.g., sleep decline "
            "+ missed workouts + mood drop = one story, not three bullet points)\n"
            "  - Keep it brief — one or two sentences, then move to the user's topic\n"
            "  - Frame observations as patterns, not commands: "
            "'I'm noticing...' not 'You need to...'\n"
            "  - If the user's message is urgent or emotional, address THEIR "
            "concern first, then weave in the intelligence naturally\n"
            "\n"
            "WHEN TO HOLD BACK:\n"
            "  - Only positive/info-level signals with no warnings → skip proactive mention\n"
            "  - User is in the middle of a focused task or deep conversation → "
            "don't interrupt with unrelated patterns\n"
            "  - Intelligence is 'degraded' → don't speculate\n"
            "=== END PROACTIVE INTELLIGENCE DIRECTIVE ==="
        )

    # Active insights — pattern detections from PIE
    if insights:
        lines.append("")
        lines.append("DETECTED PATTERNS (PIE):")
        for i in insights[:5]:
            severity_prefix = ""
            if i.get('severity') == 'critical':
                severity_prefix = "[CRITICAL] "
            elif i.get('severity') == 'warning':
                severity_prefix = "[WARNING] "
            elif i.get('severity') == 'positive':
                severity_prefix = "[POSITIVE] "
            msg = i.get('message') or i.get('title', '')
            why = i.get('explain_why', '')
            if msg and why:
                lines.append(f"  - {severity_prefix}{msg} ({why})")
            elif msg:
                lines.append(f"  - {severity_prefix}{msg}")

    # Active predictions — trajectory outlook from PRIE
    if predictions:
        lines.append("")
        lines.append("TRAJECTORY OUTLOOK (PRIE):")
        for p in predictions[:3]:
            explanation = p.get('explanation', '')
            date_str = p.get('predicted_date', '')
            conf = p.get('confidence', 0)
            if explanation:
                conf_label = "high" if conf >= 0.7 else "moderate" if conf >= 0.4 else "low"
                date_note = f" (by {date_str})" if date_str else ""
                lines.append(f"  - {explanation}{date_note} [{conf_label} confidence]")
            else:
                lines.append(f"  - {p['type']}: {p['value']}")

    # Active guidance — recommended actions from PGE
    if guidance:
        lines.append("")
        lines.append("RECOMMENDED ACTIONS (PGE):")
        for g in guidance[:3]:
            msg = g.get('message') or g.get('title', '')
            if msg:
                lines.append(f"  - {msg}")

    # Cross-domain correlations — discovered patterns from CDCE
    if correlations:
        lines.append("")
        lines.append("CROSS-DOMAIN PATTERNS (CDCE):")
        for c in correlations[:4]:
            strength_tag = ""
            if c.get('strength') == 'strong':
                strength_tag = "[STRONG] "
            elif c.get('strength') == 'moderate':
                strength_tag = "[MODERATE] "
            narrative = c.get('narrative', '')
            if narrative:
                lines.append(f"  - {strength_tag}{narrative}")

    # Relationship signals (people to reconnect with)
    rel_signals = context.get('relationship_signals', [])
    drifting = [r for r in rel_signals if r.get('drifting')]
    if drifting:
        names = ', '.join(r['name'] for r in drifting[:3])
        lines.append(f"Haven't connected with: {names}")

    # Mood (only if notable)
    mood = context.get('mood_status', {})
    if mood.get('trend') and mood['trend'] != 'stable':
        lines.append(f"Mood Trend: {mood['trend']}")

    # Journal content intelligence
    journal_intel = context.get('journal_intelligence', {})
    if journal_intel and journal_intel.get('entry_count_14d', 0) > 0:
        themes = journal_intel.get('themes_14d', [])
        concerns = journal_intel.get('concerns_14d', [])
        trajectory = journal_intel.get('sentiment_trajectory', {})

        if themes or concerns or trajectory.get('direction') not in (None, 'insufficient_data'):
            lines.append("")
            lines.append("JOURNAL INTELLIGENCE (14-day analysis — reference when discussing mood, patterns, or well-being):")
            if themes:
                theme_list = ', '.join(f"{t['theme']} ({t['strength']})" for t in themes[:4])
                lines.append(f"  Life themes: {theme_list}")
            if concerns:
                concern_list = ', '.join(f"{c['term']} ({c['entries']} entries)" for c in concerns[:3])
                lines.append(f"  Recurring concerns: {concern_list}")
            if trajectory.get('direction') and trajectory['direction'] != 'insufficient_data':
                direction = trajectory['direction']
                lines.append(f"  Sentiment trajectory: {direction}")
                if trajectory.get('mood_distribution'):
                    moods = ', '.join(f"{k}: {v}" for k, v in trajectory['mood_distribution'].items())
                    lines.append(f"  Mood distribution: {moods}")

    # Health signals — ALWAYS include so CoS has awareness of user's health data
    health_sig = context.get('health_signals', {})
    if health_sig:
        health_lines = []
        # Weight
        weight_current = health_sig.get('weight_current')
        if weight_current:
            unit = health_sig.get('weight_unit', 'lb')
            trend = health_sig.get('weight_trend')
            weight_date = health_sig.get('weight_date')
            weight_str = f"Weight: {weight_current} {unit}"
            if weight_date:
                weight_str += f" (as of {weight_date})"
            if trend and trend not in ('stable', 'insufficient_data'):
                weight_str += f", trend: {trend}"
            elif trend == 'stable':
                weight_str += ", trend: stable"
            health_lines.append(weight_str)
            # Weight goal
            weight_goal = health_sig.get('weight_goal')
            if weight_goal:
                g_unit = health_sig.get('weight_goal_unit', unit)
                goal_str = f"Weight Goal: {weight_goal} {g_unit}"
                target_date = health_sig.get('weight_goal_target_date')
                if target_date:
                    goal_str += f" by {target_date}"
                remaining = health_sig.get('weight_goal_remaining')
                if remaining is not None:
                    goal_str += f" ({abs(remaining)} {g_unit} to go)"
                health_lines.append(goal_str)
        sleep = health_sig.get('sleep_avg_7d')
        if sleep:
            label = f"{sleep:.1f}h avg" + (" (low)" if sleep < 6.5 else "")
            health_lines.append(f"Sleep: {label}")
        steps = health_sig.get('steps_avg_7d')
        if steps:
            health_lines.append(f"Steps: {steps:,} avg/day")
        hr = health_sig.get('heart_rate_avg_7d')
        if hr:
            health_lines.append(f"Heart Rate: {hr} bpm avg")
        bp = health_sig.get('bp_latest')
        if bp:
            health_lines.append(f"Blood Pressure: {bp}")
        glucose = health_sig.get('glucose_avg_7d')
        if glucose:
            health_lines.append(f"Glucose: {glucose} mg/dL avg")
        spo2 = health_sig.get('blood_oxygen_avg_7d')
        if spo2:
            health_lines.append(f"Blood Oxygen: {spo2}%")
        workouts = health_sig.get('workout_count_7d')
        if workouts:
            workout_parts = [f"Workouts: {workouts} this week"]
            if health_sig.get('workout_calories_7d'):
                workout_parts.append(f"{health_sig['workout_calories_7d']:,} cal burned")
            if health_sig.get('workout_minutes_7d'):
                workout_parts.append(f"{health_sig['workout_minutes_7d']} min total")
            if health_sig.get('workout_avg_hr_7d'):
                workout_parts.append(f"{health_sig['workout_avg_hr_7d']} bpm avg")
            if health_sig.get('workout_distance_7d'):
                workout_parts.append(f"{health_sig['workout_distance_7d']} mi")
            health_lines.append(', '.join(workout_parts))
            # Recent workout names
            recent_workouts = health_sig.get('recent_workouts', [])
            for rw in recent_workouts:
                name = rw.get('name') or rw.get('type') or 'Workout'
                rw_parts = [name]
                if rw.get('date'):
                    rw_parts[0] = f"{name} ({rw['date']})"
                if rw.get('calories'):
                    rw_parts.append(f"{rw['calories']} cal")
                if rw.get('avg_hr'):
                    rw_parts.append(f"{rw['avg_hr']} bpm")
                health_lines.append(f"    - {', '.join(rw_parts)}")
        hr_events = health_sig.get('heart_rate_events_7d')
        if hr_events:
            health_lines.append(f"Heart Rate Events: {hr_events} this week")
        if health_lines:
            lines.append("")
            lines.append("Health Signals (7-day):")
            for hl in health_lines:
                lines.append(f"  {hl}")

    # Per-exercise strength progress — exercise-specific trends and plateau status
    exercise_progress = health_sig.get('exercise_progress', []) if health_sig else []
    if exercise_progress:
        lines.append("")
        lines.append(
            "EXERCISE PROGRESS (30-day, use when discussing specific exercises or workout progress):"
        )
        for ep in exercise_progress:
            name = ep.get('exercise', 'Unknown')
            status = ep.get('status', 'unknown')
            trend = ep.get('trend', 'unknown')
            sets_30d = ep.get('sets_30d', 0)
            prs = ep.get('prs_30d', 0)
            best_e1rm = ep.get('best_e1rm')
            recent_e1rm = ep.get('recent_e1rm')

            # Build a concise one-line summary per exercise
            status_labels = {
                'improving': '↑ improving',
                'plateau': '→ plateau',
                'regressing': '↓ regressing',
                'new': '★ new',
            }
            status_label = status_labels.get(status, status)

            parts = [f"{name}: {status_label}"]
            if recent_e1rm:
                parts.append(f"e1RM {recent_e1rm:.0f}")
            if prs > 0:
                parts.append(f"{prs} PR{'s' if prs != 1 else ''} this month")
            parts.append(f"{sets_30d} sets / 30d")
            lines.append(f"  {' | '.join(parts)}")

    # Health Intelligence Engine — system-calculated scores, protein, trends
    # These are the AUTHORITATIVE values CoS MUST use (never LLM guesses)
    health_intel = context.get('health_intelligence', {})
    if health_intel:
        lines.append("")
        lines.append(_format_health_intelligence_block(health_intel, context))

    # Approaching life events
    life_events = context.get('approaching_life_events', [])
    if life_events:
        lines.append("")
        lines.append("Approaching Life Events:")
        for ev in life_events:
            day_label = "today" if ev['days_until'] == 0 else (
                "tomorrow" if ev['days_until'] == 1 else
                f"in {ev['days_until']} days"
            )
            parts = [f"  {ev['title']} ({day_label})"]
            if ev.get('person'):
                parts.append(f"— {ev['person']}")
            if ev.get('years'):
                parts.append(f"({ev['years']} years)")
            lines.append(' '.join(parts))

    # Open loops (things to address)
    loops = context.get('open_loops', {})
    if loops.get('overdue_goals'):
        lines.append(f"Overdue Goals: {loops['overdue_goals']}")

    # Phase 4: Composite Pressure Index — only highlight when notable
    pressure_snap = context.get('pressure_snapshot', {})
    if pressure_snap:
        cpi = pressure_snap.get('pressure_index', 0)
        if cpi > 90:
            lines.append("")
            lines.append(
                "LOAD STATUS: Critical. Your schedule is at maximum capacity "
                "with multiple converging demands. Protect what matters most — "
                "everything else can wait."
            )
        elif cpi > 80:
            lines.append("")
            lines.append(
                "LOAD STATUS: High. You're carrying a heavy load this week. "
                "Consider deferring non-essential commitments and protecting "
                "recovery time."
            )
        elif cpi > 60:
            lines.append("")
            lines.append(
                "LOAD STATUS: Elevated. Your week is busier than usual. "
                "Stay aware of your energy levels and watch for compression "
                "around your key commitments."
            )

    # Phase 5: Protective Briefing (advisory, human language only)
    protective = context.get('protective_briefing', {})
    if protective:
        load_status = protective.get('load_status', 'Normal')
        recs = protective.get('recommendations', [])
        upcoming = protective.get('upcoming_alerts', [])

        if load_status != 'Normal' or recs or upcoming:
            lines.append("")
            lines.append(f"Load Status: {load_status}")

            if recs:
                lines.append("Active Advisories:")
                for r in recs[:3]:
                    lines.append(f"  - {r['title']}: {r['message']}")

            if upcoming:
                lines.append("Upcoming Reminders:")
                for a in upcoming[:3]:
                    lines.append(f"  - {a['message']}")

    # Module permissions (what NOT to reference)
    mods = context.get('module_permissions', {})
    disabled = [k for k, v in mods.items() if not v]
    if disabled:
        lines.append(f"Disabled Modules (do not reference): {', '.join(disabled)}")

    # Governance strategy (how to approach this person right now)
    strategy_block = context.get('governance_strategy_prompt', '')
    if strategy_block:
        lines.append("")
        lines.append(strategy_block)

    # Executive tone mode (Phase 4 — how the CoS should approach this person)
    tone_mode = context.get('executive_tone_mode', '')
    if tone_mode:
        tone_text = TONE_MODE_INSTRUCTIONS.get(tone_mode, '')
        if tone_text:
            lines.append("")
            lines.append(f"EXECUTIVE TONE: {tone_text}")

    # Phase 1: Declared user priorities — from SAE truth layer
    try:
        from apps.core.ai_state.state_engine import get_state_value as _gsv
        priorities = _gsv(context.get('_user'), 'governance.declared_priorities', []) if context.get('_user') else []
        if priorities:
            lines.append("")
            lines.append("Declared Priorities:")
            for p in priorities[:10]:
                sub = f".{p['sub_module']}" if p.get('sub_module') else ""
                level = p.get('level', '')
                reason_text = p.get('reason', '')
                reason = f" — {reason_text[:100]}" if reason_text else ""
                lines.append(f"  {p['module']}{sub}: {level}{reason}")
    except Exception:
        pass

    # NOTE: learned_profile_prompt is intentionally NOT rendered here.
    # It is injected as a separate priority layer in personal_assistant.py
    # (Layer 5) to avoid duplication in the situational awareness block.

    # Phase 2: Cognitive Precision Framework
    # Injected into every non-learning-mode interaction.
    # The LLM self-selects depth based on request complexity.
    lines.append("")
    lines.append(COGNITIVE_PRECISION_FRAMEWORK.strip())

    # Phase 3: Trajectory Precision Layer (Tiered Activation)
    # Activation state determines which framework variant is injected:
    # - CLEAN: Phase 2 only, no trajectory framework.
    # - EARLY_EROSION: Soft observational probe, no horizon modeling.
    # - STRUCTURAL_DRIFT: Full framework + trajectory signals.
    activation_state = context.get('trajectory_activation_state', ACTIVATION_CLEAN)
    trajectory = context.get('trajectory_signals', {})

    if activation_state == ACTIVATION_STRUCTURAL_DRIFT:
        # Full trajectory framework + validated signal block
        lines.append("")
        lines.append(TRAJECTORY_PRECISION_FRAMEWORK.strip())
        if trajectory:
            traj_block = _format_trajectory_injection(trajectory)
            if traj_block:
                lines.append("")
                lines.append(traj_block)
    elif activation_state == ACTIVATION_EARLY_EROSION:
        # Soft probe only — no full framework, no horizon modeling
        lines.append("")
        lines.append(EARLY_EROSION_FRAMEWORK.strip())

    # Phase 5A: Executive Commitment Contract (ECC) injection
    # Sits between tier evaluation and R5 escalation.
    # Only injects if there are active (pending) commitments in session.
    ecc_commitments = context.get('ecc_active_commitments', [])
    if ecc_commitments:
        try:
            from apps.core.ai_orchestrator.commitment_contract import format_ecc_injection
            ecc_block = format_ecc_injection(ecc_commitments)
            if ecc_block:
                lines.append("")
                lines.append(ecc_block)
        except Exception:
            pass

    # Phase 4 R1: Decision Branch Modeling (conditional injection)
    # Evaluates AFTER Phase 3 tier determination, BEFORE final render.
    # Only activates when decision branch gate conditions are met.
    db_gate = context.get('decision_branch_gate', {})
    if db_gate.get('active'):
        db_block = _format_decision_branch_injection(db_gate, activation_state)
        if db_block:
            lines.append("")
            lines.append(db_block)

    # Faith & Prayer context
    faith = context.get('faith_summary', {})
    if faith and (faith.get('active_prayers', 0) > 0 or faith.get('answered_prayers', 0) > 0):
        lines.append("")
        lines.append("FAITH & PRAYER:")
        lines.append(f"  Active prayer requests: {faith['active_prayers']}")
        lines.append(f"  Answered prayers: {faith['answered_prayers']}")
        if faith.get('urgent_prayers'):
            lines.append(f"  Urgent: {faith['urgent_prayers']}")
        if faith.get('recent_prayer_titles'):
            lines.append("  Recent prayers: " + ", ".join(faith['recent_prayer_titles']))
        bible = faith.get('bible_reading')
        if bible:
            if bible.get('plan'):
                lines.append(f"  Bible reading plan: {bible['plan']}")
            if bible.get('streak_days'):
                lines.append(f"  Reading streak: {bible['streak_days']} days")

    # Phase 7.3: Finance context
    finance_goals = context.get('finance_goals', [])
    finance_budgets = context.get('finance_budgets_alert', [])
    if finance_goals or finance_budgets:
        lines.append("")
        lines.append("FINANCE:")
        for fg in finance_goals[:3]:
            date_str = f" (by {fg['target_date']})" if fg.get('target_date') else ""
            lines.append(
                f"  Goal: {fg['name']} — ${fg['current']:.0f}/${fg['target']:.0f} "
                f"({fg['progress_pct']}%){date_str}"
            )
        for fb in finance_budgets[:3]:
            over = " [OVER BUDGET]" if fb.get('over_budget') else ""
            lines.append(
                f"  Budget: {fb['category']} — ${fb['spent']:.0f}/${fb['budgeted']:.0f} "
                f"({fb['percent_used']}%){over}"
            )

    # Phase 7.3: Purpose context (goals, habits)
    life_goals = context.get('life_goals', [])
    habit_progress = context.get('habit_progress', [])
    if life_goals or habit_progress:
        lines.append("")
        lines.append("GOALS & HABITS:")
        for lg in life_goals[:3]:
            days_str = ""
            if lg.get('days_until') is not None:
                if lg['days_until'] <= 7:
                    days_str = f" [DUE IN {lg['days_until']}d]"
                elif lg['days_until'] <= 30:
                    days_str = f" (due {lg.get('target_date', '')})"
            lines.append(f"  Life Goal: {lg['name']}{days_str}")
        for hp in habit_progress[:5]:
            rate = hp['completion_rate_7d']
            status = "✓ on track" if rate >= 80 else ("needs attention" if rate < 50 else "")
            lines.append(
                f"  Habit: {hp['name']} — {hp['entries_7d']}/{hp['target_weekly']} "
                f"this week ({rate:.0f}%) {status}"
            )

    # Phase 7.3: Brain training context
    brain = context.get('brain_training', {})
    if brain and brain.get('current_streak', 0) > 0:
        lines.append("")
        lines.append(
            f"Brain Training: {brain['current_streak']}-day streak, "
            f"{brain.get('total_completed', 0)} sessions completed"
        )
        if brain.get('favorite_game'):
            lines.append(f"  Favorite: {brain['favorite_game']}")

    # Phase 7.3: Capture context
    capture = context.get('capture_status', {})
    if capture and (capture.get('pending_uploads', 0) > 0 or capture.get('recent_captures')):
        lines.append("")
        pending = capture.get('pending_uploads', 0)
        recent = capture.get('recent_captures', [])
        if pending:
            lines.append(f"Captures: {pending} pending upload(s)")
        if recent:
            lines.append(f"Recent captures: {len(recent)} in last 7 days")

    # Phase 7.3: Medical context
    medical_alerts = context.get('medical_alerts', [])
    if medical_alerts:
        lines.append("")
        lines.append("MEDICAL ALERTS (recent abnormal lab results):")
        for ma in medical_alerts[:3]:
            lines.append(
                f"  {ma['test']}: {ma['value']} [{ma['flag']}] ({ma.get('date', '')})"
            )

    # Navigable pages — URL awareness for directing users to app pages
    pages = context.get('navigable_pages', [])
    if pages:
        lines.append("")
        lines.append(
            "APP NAVIGATION — This app is https://wholelifejourney.com. "
            "When directing the user to a page, use markdown links with these "
            "RELATIVE paths (not absolute URLs). Example: [Tasks](/life/tasks/) "
            "NEVER invent URLs — only use paths listed here:"
        )
        for p in pages:
            lines.append(f"  - [{p['name']}]({p['url']})")

    # ================================================================
    # COS-CX: Context Intelligence Expansion (Phases CX1-CX6)
    # Always-on specificity, lead signal, goal gaps, temporal matching,
    # and behavioral forecast. All fail-safe with empty-string fallback.
    # ================================================================
    _cx_user = context.get('_user')
    if _cx_user:
        try:
            from apps.core.utils import get_user_now
            _cx_now = get_user_now(_cx_user)

            # CX1: Always-on specificity (named items in every response)
            try:
                from apps.cos.context.specificity_block import build_specificity_block
                _cx_specificity = build_specificity_block(_cx_user, _cx_now)
                if _cx_specificity:
                    lines.append("")
                    lines.append(_cx_specificity)
            except Exception:
                _cx_specificity = ""

            # CX3: Goal behavior gap analysis
            _cx_gaps_data = []
            try:
                from apps.cos.intelligence.goal_gap_analyzer import (
                    analyze_goal_behavior_gaps,
                    format_goal_gaps_block,
                )
                _cx_gaps_data = analyze_goal_behavior_gaps(_cx_user, _cx_now)
                _cx_gaps_block = format_goal_gaps_block(_cx_gaps_data)
                if _cx_gaps_block:
                    lines.append("")
                    lines.append(_cx_gaps_block)
                # Store gaps in context for signal prioritizer
                context['goal_behavior_gaps'] = _cx_gaps_data
            except Exception:
                pass

            # CX2: Lead signal prioritizer (single most important thing)
            try:
                from apps.cos.context.signal_prioritizer import compute_lead_signal
                _cx_lead = compute_lead_signal(
                    _cx_user, _cx_specificity, _cx_now, cos_context=context
                )
                if _cx_lead:
                    lines.append("")
                    lines.append(_cx_lead)
            except Exception:
                pass

            # CX4: Temporal execution matching (task → free window)
            try:
                from apps.cos.context.temporal_matcher import compute_execution_windows
                _cx_windows = compute_execution_windows(
                    _cx_user, _cx_now, cos_context=context
                )
                if _cx_windows:
                    lines.append("")
                    lines.append(_cx_windows)
            except Exception:
                pass

            # CX6: Behavioral forecast (tomorrow's completion probabilities)
            try:
                from apps.cos.intelligence.behavior_forecast import compute_behavior_forecast
                _cx_forecast = compute_behavior_forecast(
                    _cx_user, _cx_now, cos_context=context
                )
                if _cx_forecast:
                    lines.append("")
                    lines.append(_cx_forecast)
            except Exception:
                pass

        except Exception:
            pass  # CX block must never break CoS

    # Recent image analyses — visual context from uploaded images
    image_analyses = context.get('recent_image_analyses', [])
    if image_analyses:
        lines.append("")
        lines.append(
            "RECENT IMAGE CONTEXT (reference when user asks about photos or related items):"
        )
        for ia in image_analyses:
            tags_str = ""
            if ia.get('tags'):
                tags_str = " " + " ".join(f"#{t}" for t in ia['tags'][:3])
            lines.append(f"  - [{ia['source']}] {ia['summary']}{tags_str}")

    # Consistency protection alerts (immediate intervention patterns)
    _cp_user = context.get('_user')
    if _cp_user:
        try:
            from apps.cos.services.pattern_service import CosPatternService
            _cp_svc = CosPatternService(_cp_user)
            _cp_violations = _cp_svc.detect_consistency_violations(days=14)
            if _cp_violations:
                _cp_block = _cp_svc.format_consistency_violations_for_injection(
                    _cp_violations
                )
                if _cp_block:
                    lines.append("")
                    lines.append(_cp_block)
        except Exception:
            pass  # Consistency protection must never break CoS

    # ── v8: Situational Awareness Summary ──
    sa_data = context.get('situational_awareness')
    if sa_data and sa_data.get('lines'):
        try:
            from apps.ai.situational_awareness import (
                format_situational_awareness_injection,
            )
            sa_block = format_situational_awareness_injection(sa_data)
            if sa_block:
                lines.append("")
                lines.append(sa_block)
        except Exception:
            pass  # SA must never break CoS

    # ── v4 PART 4: Data State Snapshot (FINAL POSITION — highest recency weight) ──
    # Moved to END of prompt so the model weights it more heavily.
    # Contains exact DB record counts and ABSOLUTE grounding rules.
    _cos_user_final = context.get('_user')
    if _cos_user_final:
        try:
            snapshot = _build_data_state_snapshot(_cos_user_final)
            if snapshot:
                lines.append("")
                lines.append(snapshot)
        except Exception:
            pass  # Snapshot must never break CoS

    # ── v6: Consolidated CoS Operational Rules ──
    lines.append("")
    lines.append(
        "=== CHIEF OF STAFF OPERATIONAL RULES (v6) ===\n"
        "\n"
        "--- RULE 1: NO GENERIC PRODUCTIVITY ADVICE ---\n"
        "Generic productivity templates are FORBIDDEN when user context exists.\n"
        "FORBIDDEN examples:\n"
        "  - Eisenhower Matrix / urgency-importance grid\n"
        "  - Pomodoro Technique\n"
        "  - 'Time block your day'\n"
        "  - 'Create a morning routine'\n"
        "  - 'Set daily objectives'\n"
        "  - 'Review your priorities' (without naming them)\n"
        "  - 'Start with your most important task' (without naming it)\n"
        "  - 'Try to get 7-9 hours of sleep'\n"
        "\n"
        "INSTEAD, use the user's actual data:\n"
        "  GOOD: 'You have 1 active task and your workout is still outstanding. "
        "With 6 hours until bedtime, I\\'d handle the task first, then get "
        "your workout in.'\n"
        "  GOOD: 'I don\\'t see any goals logged yet. That\\'s the highest-impact "
        "first step — head to [Goals](/purpose/goals/) to define what you\\'re "
        "working toward.'\n"
        "\n"
        "--- RULE 2: CHIEF OF STAFF VOICE ---\n"
        "You are the user's Chief of Staff — a strategic operational partner.\n"
        "Speak as a trusted advisor who KNOWS this person and their situation.\n"
        "\n"
        "GOOD tone:\n"
        "  'Danny — here\\'s the situation.'\n"
        "  'Looking at your data, the biggest gap is...'\n"
        "  'My recommendation: ...'\n"
        "  'Based on your priorities, I\\'d focus on...'\n"
        "\n"
        "FORBIDDEN phrases (never use these):\n"
        "  'I\\'m here to assist you'\n"
        "  'How can I help you today?'\n"
        "  'As an AI assistant...'\n"
        "  'I\\'d be happy to help'\n"
        "  'That\\'s a great question!'\n"
        "  'Let me help you with that'\n"
        "  'I\\'m unable to access your personal data'\n"
        "  'I don\\'t have access to your records'\n"
        "  'I can\\'t retrieve your information'\n"
        "\n"
        "--- RULE 3: MISSING DATA FRAMING ---\n"
        "You have FULL ACCESS to all user data. If data is missing, it\\'s "
        "because the user hasn\\'t logged it yet — NOT because you can\\'t "
        "access it.\n"
        "Pattern: 'I don\\'t see [X] logged yet.' + actionable link.\n"
        "Examples:\n"
        "  'I don\\'t see any weight data logged yet. Start tracking at "
        "[Weight Tracking](/health/weight/).'\n"
        "  'No sleep entries recorded yet. Log a few nights and I can "
        "analyze your patterns at [Sleep Tracker](/health/sleep/).'\n"
        "  'You haven\\'t set up goals yet. Head to [Goals](/purpose/goals/) "
        "to define what matters most.'\n"
        "\n"
        "--- RULE 4: DECISION MODE ---\n"
        "When the user asks a decision question ('should I...', 'do you think "
        "I should...', 'is it a good idea to...', 'what do you recommend', "
        "'should I push through or...'), you MUST enter DECISION MODE.\n"
        "\n"
        "DECISION MODE response structure:\n"
        "1. SITUATION — State what you see in the data (brief, 1-2 sentences)\n"
        "2. ASSESSMENT — Evaluate the decision using context and priorities\n"
        "3. RECOMMENDATION — Make a clear, direct recommendation\n"
        "4. NEXT STEP — Offer A/B/C options if appropriate\n"
        "\n"
        "CRITICAL: You MUST make a recommendation. Do NOT mirror the question "
        "back. Do NOT end with 'How does that sound?' or 'What do you think?' "
        "without first stating your recommendation.\n"
        "\n"
        "Example:\n"
        "  Q: 'I\\'m tired. Should I still work out today?'\n"
        "  A: 'Danny — here\\'s the situation. Your workout is outstanding "
        "and you\\'ve been consistent this week. Being tired doesn\\'t mean "
        "you should skip it — but you can adjust intensity. My recommendation: "
        "do a lighter session to protect the streak. A) Full workout, "
        "B) Reduced intensity session, C) Active recovery walk.'\n"
        "\n"
        "Workout = non-negotiable core discipline. Protect it.\n"
        "Bike ride = extra/optional bonus. Can be deferred.\n"
        "Maintenance reminders (charge watch, etc.) = minor, not major obligations.\n"
        "\n"
        "--- RULE 5: OPERATIONAL BRIEFING FORMAT ---\n"
        "For advisory / planning / check-in style questions ('how should I "
        "structure my day', 'what should I focus on', 'what\\'s the situation', "
        "'if you were my chief of staff'), use this priority order:\n"
        "\n"
        "1. Goals (user\\'s declared priorities and objectives)\n"
        "2. Goal-supporting actions (habits, routines that serve the goals)\n"
        "3. Tasks due today\n"
        "4. Overdue tasks\n"
        "5. Maintenance reminders (only if relevant)\n"
        "6. Large upcoming obligations (only if strategically important)\n"
        "\n"
        "Then close with ONE clear recommendation and optional A/B/C choices.\n"
        "\n"
        "Task display rules:\n"
        "- Focus on TODAY\\'s tasks first\n"
        "- Include overdue tasks\n"
        "- Only mention future tasks if large/strategically important\n"
        "- Do NOT clutter with minor future items\n"
        "- Keep it concise and operational — no fluff\n"
        "\n"
        "--- RULE 6: KNOWLEDGE RESPONSE GROUNDING ---\n"
        "When the user asks a knowledge question about their body, metrics, "
        "or routines:\n"
        "1. Acknowledge what user-specific data is missing\n"
        "2. Provide the general knowledge answer\n"
        "3. Explain what would allow a more personalized answer\n"
        "\n"
        "Example:\n"
        "  Q: 'What protein target should someone my size use?'\n"
        "  A: 'I don\\'t have your weight logged yet, so I can\\'t calculate "
        "your exact target. Generally, 0.7-1.0g per pound of body weight is "
        "a good starting point. Log your weight at [Weight Tracking]"
        "(/health/weight/) and I\\'ll give you a precise number based on "
        "your lean body mass.'\n"
        "\n"
        "=== END CHIEF OF STAFF OPERATIONAL RULES ==="
    )

    lines.append("")
    lines.append("=== END SITUATIONAL AWARENESS ===")
    lines.append("")

    result = '\n'.join(lines)

    # Token budget telemetry — log prompt size for monitoring
    # Approximate: 1 token ~= 4 chars for English text
    approx_tokens = len(result) // 4
    if approx_tokens > 6000:
        logger.warning(
            "COS_PROMPT_BUDGET user=%s tokens~=%d (exceeds 6000 soft limit)",
            context.get('user_id', 'unknown'), approx_tokens,
        )
    else:
        logger.debug(
            "COS_PROMPT_BUDGET user=%s tokens~=%d",
            context.get('user_id', 'unknown'), approx_tokens,
        )

    return result


# =========================================================================
# PHASE 4 — EXECUTIVE CONTEXT BUILDER
# =========================================================================

# Executive tone mode instructions
TONE_MODE_INSTRUCTIONS = {
    'strategic_executive': (
        "STRATEGIC EXECUTIVE — Calm authority. Surface what matters, filter noise. "
        "Explain the reasoning, then state the directive. "
        "No hedging, no over-questioning, no filler."
    ),
    'direct_accountability': (
        "DIRECT ACCOUNTABILITY — The user is drifting from commitments. "
        "Name the specific evidence. Explain why it matters to their stated priorities. "
        "Then state what needs to happen. No sugarcoating, no moralizing."
    ),
    'reflective_support': (
        "REFLECTIVE SUPPORT — The user's emotional state needs attention. "
        "Acknowledge what you observe. Ask one reflective question if needed. "
        "Then offer a concrete next step. Stay grounded — no over-validation."
    ),
}


# =========================================================================
# PHASE 2 — COGNITIVE PRECISION LAYER
# =========================================================================

COGNITIVE_PRECISION_FRAMEWORK = """
--- COGNITIVE PRECISION ---

## FRAMEWORK APPLICATION

Self-select response depth based on the user's request:

- INFORMATIONAL (e.g., "What's my next event?", "How many steps today?"):
  Answer directly. No framework. No structure beyond what's natural.

- DECISION / TRADE-OFF / PRIORITY CONFLICT / STRATEGIC EVALUATION:
  Apply the structured decision framework below.

## STRUCTURED DECISION FRAMEWORK

When the user's request involves a decision, trade-off, schedule conflict,
priority question, or strategic evaluation, respond using this structure:

1. Situation Summary
   One concise paragraph. No filler. No emotional mirroring.

2. Priority Alignment Check
   Reference the user's declared priorities and non-negotiable commitments.
   State whether alignment or conflict exists.

3. Trade-Off Model
   Model short-term gain vs long-term cost.
   Include second-order effects when relevant:
   - Momentum decay (will this break a streak or stall progress?)
   - Cognitive switching cost (will this fragment focus or create context loss?)
   - Identity reinforcement or erosion (does this align with who they say they are?)
   - Recovery difficulty (how hard is it to get back on track after this choice?)
   Do not remain at surface-level cost framing. Name the real cost.

4. Pattern Signal (if applicable)
   If behavior appears recurring, state it calmly with evidence.
   If isolated, say so.

5. Recommendation
   Explanation first. Then a clear directive.
   Format: "Given this, proceed with X." or "Given this, protect Y and reschedule Z now."

6. Enforcement (non-negotiable conflicts only)
   If the choice would override a non-negotiable commitment:
   - Require immediate rescheduling, OR
   - Require explicit confirmation before proceeding.

## NON-NEGOTIABLE OVERRIDE PROTOCOL

When a user chooses to violate a declared non-negotiable commitment, this is
not a negotiation. It is a procedural override event. Respond with this
exact structure:

1. State the contradiction: "[Action] contradicts [specific non-negotiable]."
2. Name the cost: identity erosion, streak loss, priority inversion — be specific.
3. Provide the corrective minimum: the smallest action that preserves the commitment.
4. If the user insists after hearing the cost and corrective minimum, state:
   "Proceeding requires explicit override acknowledgment.
    This will be logged as a priority inversion event."

Rules for override posture:
- No emotional tone. No conversational softening.
- No "if you still want to" or "it's your choice."
- No framing as debate or negotiation.
- This is governance. State the facts, name the cost, offer the minimum, require acknowledgment.

## SYSTEM CHALLENGE CONTAINMENT

When the user challenges the system itself — calls it rigid, controlling,
dismisses priority logic, or attempts philosophical debate about the structure:

Do NOT defend the system, explain philosophy, justify logging, or enter
conceptual discussion. These are containment triggers, not conversation topics.

Respond with this structure only:
1. Re-anchor: "Current structure reflects your declared priorities."
2. Offer recalibration: "If priorities have changed, initiate recalibration."
3. Close: "Otherwise, today's action stands as logged."

No trailing questions. No debate tone. No philosophical language.
Governance posture only. Then stop.

## RESPONSE DISCIPLINE

Do not end with "What do you want to do?"
If user choice is required, frame it with consequences:
  "If you choose X, we reschedule Y now."

## AUTHORITY POSTURE

Use blended authority: explanation first, then declarative instruction.
Do not over-apologize, hedge excessively, default to neutrality, or moralize.

## COMPRESSION

Responses must be tight, structured, and intentional.
If the question is small, keep structure lightweight.
If the question is strategic, use the full framework.
No rambling. No padding. No motivational filler.

## MICRO-COMPRESSION

Prefer high-density statements over multi-phrase explanations.
- "Execution flexes. Commitment does not." over "Execution is flexible — timing, duration, format, intensity all adjust."
- "Five misses rewrites the default." over "After five missed sessions, the habit threshold resets."
- Fewer words, same precision. Cut any sentence that restates what the previous one said.

## IDENTITY PRECISION

When referencing commitments, habits, or behavioral patterns, use identity-based
framing rather than consistency language.
- "This reinforces who you said you are." — not "This helps maintain consistency."
- "You declared this non-negotiable because it defines you." — not "This is important to your routine."
- "Skipping erodes the identity you built." — not "Skipping breaks the streak."
Connect choices to the person, not the system.

## LANGUAGE DENSITY

Avoid neutral abstraction phrases:
- "The distinction matters" — just state the distinction.
- "That's information" — state what the information means.
- "This is about" — state the thing directly.
- "The real issue is" — state the issue.
Replace explanation of what you're doing with doing it.

--- END COGNITIVE PRECISION ---
"""


# =========================================================================
# PHASE 3 — STRATEGIC MODELING LAYER (Trajectory Precision)
# =========================================================================

TRAJECTORY_PRECISION_FRAMEWORK = """
--- TRAJECTORY PRECISION ---

## LAYER 1 — CONTEXTUAL PATTERN SURFACING

When trajectory signals indicate a recurring pattern on a specific commitment:
- Same commitment renegotiated ≥3 times within 10 days
- OR corrective minimum compressed ≥3 times within 10 days
- OR repeated identity downshift language detected ("just a workout", "only this once", etc.)

Surface ONLY when that commitment is discussed again. Structure:

1. Pattern statement (no soft language):
   "You've renegotiated this three times in ten days."

2. 72-hour trajectory projection (concrete, behavioral):
   "At this rate, the next 72 hours continue erosion."

3. 30-day directional framing (identity shift):
   "Thirty days of this pattern shifts you from disciplined to intermittent."

4. Directive. One sentence. No trailing question.

No charts. No emotional commentary. No filler.

## LAYER 2 — DRIFT ALERT

When trajectory signals indicate Tier 1 drift:
- Tier 1 commitment skipped ≥2 times in 7 days
- OR 2 consecutive Tier 1 skips
- OR corrective minimum downgraded repeatedly AND progress trend negative

Surface immediately during that interaction. Rate limit: once per commitment per 7 days.

Structure:
1. "Tier 1 drift detected."
2. Cost framing — identity erosion + momentum loss. Be specific.
3. Short corrective directive.

Do not repeat without new behavioral evidence.

## LAYER 3 — WEEKLY TRAJECTORY FRAMING

Surface ONLY during weekly planning, strategic review, or explicit reflection moments.

Exactly 3 items:
1. One strengthening pattern (what's working)
2. One drift risk pattern (what's eroding)
3. One identity reinforcement statement

Keep under 8 sentences total. No motivational tone. No analytics summary.

## HORIZON MODELING RULES

For all trajectory surfacing:
- 72-hour horizon: concrete and behavioral. What happens in the next 3 days if this continues.
- 30-day horizon: directional identity shift. Who you become if this persists.
- Do not forecast beyond 30 days.

## TRAJECTORY TONE

- High-density language.
- No "I've noticed…"
- No "It seems…"
- No defensive framing.
- No motivational energy.
- No coaching tone.
- Executive trajectory correction only.

--- END TRAJECTORY PRECISION ---
"""


def build_executive_context(user):
    """
    Build the unified Executive Context Object.

    Aggregates all intelligence signals into a single strategic summary.
    This is the primary intelligence injected into the assistant system prompt.

    Returns:
        dict — ExecutiveContextObject
    """
    context = build_cos_context(user)

    # Build the strategic summary object
    executive = {
        'strategic_state_summary': _build_strategic_summary(context),
        'risk_flags': _build_risk_flags(context),
        'momentum_indicators': _build_momentum_indicators(context),
        'pressure_indicators': _build_pressure_indicators(context),
        'relational_status': _build_relational_status(context),
        'health_status': _build_health_status(context),
        'focus_conflicts': _build_focus_conflicts(context),
        'recommended_focus_for_today': _build_focus_recommendation(context),
        'noise_items': _build_noise_items(context),
        'governance_tier': context.get('governance_profile', {}).get(
            'accountability_style', 'standard'
        ),
        'intervention_level': _get_current_intervention_level(context),
        'tone_mode': context.get('executive_tone_mode', 'strategic_executive'),
    }

    # Merge with full operational context
    context['executive'] = executive
    return context


def _determine_tone_mode(user, context):
    """
    Select the executive tone mode based on current signals.

    Modes:
    - strategic_executive: Default calm authority
    - direct_accountability: High drift → be direct
    - reflective_support: High mood volatility → be empathetic
    """
    drift_score = context.get('drift_score', 0)
    mood = context.get('mood_status', {})
    mood_trend = mood.get('trend', 'stable')
    weekly = context.get('weekly_pressure', {})
    pressure_avg = weekly.get('avg_load', 0) if weekly else 0

    # High drift → Direct Accountability
    if drift_score >= 40:
        return 'direct_accountability'

    # Declining mood → Reflective Support
    if mood_trend in ('declining', 'decreasing'):
        return 'reflective_support'

    # High pressure → Strategic Executive (stay calm, lead clearly)
    return 'strategic_executive'


def _build_strategic_summary(context):
    """One-sentence strategic state summary."""
    alignment = context.get('alignment_score', 100)
    drift = context.get('drift_score', 0)

    # Phase 4: Use Composite Pressure Index when available, fall back to weekly load
    cpi = context.get('pressure_snapshot', {}).get('pressure_index', 0)
    pressure = cpi if cpi > 0 else context.get('weekly_pressure', {}).get('avg_load', 0)

    if drift >= 50:
        return f"Significant drift ({drift}/100). Realignment needed."
    if pressure >= 80:
        return f"High pressure week (index {pressure}). Protect priorities."
    if alignment >= 85:
        return f"Strong alignment ({alignment}%). Maintain momentum."
    return f"Alignment at {alignment}%, drift at {drift}/100. Steady course."


def _build_risk_flags(context):
    """Extract active risk flags."""
    flags = list(context.get('risk_warnings', []))
    insights = context.get('active_insights', [])
    for i in insights:
        if i['severity'] in ('warning', 'critical'):
            flags.append(f"[{i['severity']}] {i['title']}")
    loops = context.get('open_loops', {})
    if loops.get('overdue_goals', 0) > 2:
        flags.append(f"{loops['overdue_goals']} overdue goals")
    return flags[:8]


def _build_momentum_indicators(context):
    """Positive momentum signals."""
    indicators = []
    alignment = context.get('alignment_score', 0)
    if alignment >= 80:
        indicators.append(f"Blueprint alignment: {alignment}%")
    cap = context.get('capacity_snapshot', {})
    completed = cap.get('completed_blocks', 0)
    total = cap.get('total_blocks', 0)
    if total > 0 and completed / total >= 0.5:
        indicators.append(f"Schedule execution: {completed}/{total} blocks done")
    insights = context.get('active_insights', [])
    for i in insights:
        if i['severity'] == 'positive':
            indicators.append(i['title'])
    return indicators[:5]


def _build_pressure_indicators(context):
    """Pressure and load signals, including Phase 4 Composite Pressure Index."""
    indicators = []

    # Phase 4: CPI-based pressure indicator (preferred source)
    pressure_snap = context.get('pressure_snapshot', {})
    cpi = pressure_snap.get('pressure_index', 0)
    if cpi > 90:
        indicators.append(f"Composite Pressure: Critical ({cpi}/100)")
    elif cpi > 80:
        indicators.append(f"Composite Pressure: High ({cpi}/100)")
    elif cpi > 60:
        indicators.append(f"Composite Pressure: Elevated ({cpi}/100)")

    # Weekly load indicators (complementary)
    weekly = context.get('weekly_pressure', {})
    if weekly.get('avg_load', 0) >= 70:
        indicators.append(f"Weekly load: {weekly['avg_load']}%")
    if weekly.get('heavy_days'):
        indicators.append(f"Heavy days: {', '.join(weekly['heavy_days'][:3])}")
    f24 = context.get('forecast_load_24h', 0)
    if f24 >= 80:
        indicators.append(f"Tomorrow: {f24}% capacity")
    return indicators


def _build_relational_status(context):
    """Relationship health summary (Phase R2 enhanced)."""
    signals = context.get('relationship_signals', [])
    drifting = [r for r in signals if r.get('drifting')]
    healthy = [r for r in signals if not r.get('drifting')]

    # Phase R2: Include health score and imbalance data
    rh = context.get('relational_health', {})
    status = {
        'total_tracked': len(signals),
        'drifting': [r['name'] for r in drifting[:3]],
        'healthy': [r['name'] for r in healthy[:3]],
    }
    if rh.get('relational_health_score') is not None:
        status['health_score'] = rh['relational_health_score']
        status['stale_count'] = rh.get('stale_relationships_count', 0)
        status['anchors'] = rh.get('top_anchor_persons', [])[:3]
        if rh.get('imbalance_flags'):
            status['imbalances'] = [
                f"{f['person']}: {f['percentage']}% {f['dominant_context']}"
                for f in rh['imbalance_flags'][:2]
            ]
    return status


def _build_health_status(context):
    """Health signal summary."""
    health = context.get('health_signals', {})
    med = context.get('medication_adherence_state', {})
    fast = context.get('active_fast_status', {})
    status = {}
    if health.get('sleep_avg_7d'):
        status['sleep'] = f"{health['sleep_avg_7d']:.1f}h avg"
    if health.get('workout_count_7d'):
        status['workouts_7d'] = health['workout_count_7d']
    if med.get('adherence_pct') is not None:
        status['med_adherence'] = f"{med['adherence_pct']}%"
    if fast.get('active'):
        status['fasting'] = True
    return status


def _build_focus_conflicts(context):
    """Detect scheduling or priority conflicts."""
    conflicts = []
    loops = context.get('open_loops', {})
    if loops.get('overdue_goals', 0) > 0 and loops.get('pending_friction_gates', 0) > 0:
        conflicts.append("Overdue goals with pending friction gates — unresolved tension")
    drift = context.get('drift_score', 0)
    cap = context.get('capacity_snapshot', {})
    if drift >= 30 and cap.get('capacity_pct', 0) >= 80:
        conflicts.append("High drift with full schedule — no room to recover")
    return conflicts


def _build_focus_recommendation(context):
    """Single directive for today's focus."""
    drift = context.get('drift_score', 0)
    if drift >= 50:
        return "Realign with Tier-1 behaviors. Everything else is secondary."
    loops = context.get('open_loops', {})
    if loops.get('overdue_goals', 0) > 2:
        return "Address overdue goals. Close open loops before adding new commitments."
    insights = context.get('active_insights', [])
    critical = [i for i in insights if i['severity'] == 'critical']
    if critical:
        return f"Address critical insight: {critical[0]['title']}"
    return "Execute today's architecture plan. Protect Tier-1 blocks."


def _build_noise_items(context):
    """Items that can be safely deprioritized."""
    noise = []
    insights = context.get('active_insights', [])
    for i in insights:
        if i['severity'] == 'info':
            noise.append(i['title'])
    return noise[:3]


def _get_current_intervention_level(context):
    """Get the current intervention level from drift."""
    drift = context.get('drift_score', 0)
    if drift >= 70:
        return 4  # friction gate
    if drift >= 50:
        return 3  # interrupt
    if drift >= 30:
        return 2  # ping
    if drift >= 15:
        return 1  # nudge
    return 0  # silent


# =========================================================================
# PHASE 3 — TRAJECTORY SIGNAL BUILDER
# =========================================================================


def _source_integrity_gate(source_name, queryset_fn, min_records=1):
    """
    Source-Integrity Gate for trajectory signals.

    Verifies a data source is importable and returns non-trivial volume
    before allowing trajectory computation. Fails closed — returns None
    on any failure rather than fabricating data.

    Args:
        source_name: str — identifier for logging/placeholder output.
        queryset_fn: callable — returns (queryset_or_data, record_count).
            Must handle its own imports internally.
        min_records: int — minimum record count to consider source valid.

    Returns:
        (data, count) on success, or None if insufficient/unavailable.
    """
    try:
        data, count = queryset_fn()
        if count < min_records:
            return None
        return data, count
    except Exception as e:
        logger.debug("Source-Integrity Gate [%s]: %s", source_name, e)
        return None


def _build_trajectory_signals(user):
    """
    Build trajectory-relevant signals from SAE truth layer.

    Source-Integrity Gate applied via SAE state presence checks.
    Read-only — no writes, no side effects.

    Reads from:
    - SAE intervention state: renegotiation patterns, override frequency
    - SAE governance state: drift frequency
    - SAE health state: progress trend

    Returns:
        dict — trajectory signals for prompt injection.
    """
    from apps.core.ai_state.state_engine import get_module_state, get_state_value

    signals = {
        'renegotiation_patterns': [],
        'tier1_skip_patterns': [],
        'consecutive_tier1_skips': 0,
        'override_count_10d': 0,
        'drift_scenario_count_14d': 0,
        'progress_trend_negative': False,
        'insufficient': [],
    }

    # --- Renegotiation patterns (Layer 1) from SAE ---
    intervention = get_module_state(user, 'intervention') or {}

    reneg_patterns = intervention.get('renegotiation_patterns', [])
    if reneg_patterns:
        signals['renegotiation_patterns'] = reneg_patterns
        signals['override_count_10d'] = intervention.get('override_count_10d', 0)
    else:
        signals['insufficient'].append('renegotiation')

    # --- Tier 1 skip patterns (Layer 2) from SAE ---
    tier1_patterns = intervention.get('tier1_skip_patterns', [])
    if tier1_patterns:
        signals['tier1_skip_patterns'] = tier1_patterns
        signals['consecutive_tier1_skips'] = intervention.get('consecutive_tier1_skips', 0)
    else:
        signals['insufficient'].append('tier1_skips')

    # --- Drift scenario frequency from SAE governance ---
    drift_count = get_state_value(user, 'governance.drift_scenario_count_14d', 0)
    if drift_count > 0:
        signals['drift_scenario_count_14d'] = drift_count
    else:
        signals['insufficient'].append('drift_frequency')

    # --- Progress trend (supports Layer 2 corrective minimum detection) ---
    weight_trend = get_state_value(user, 'health.weight_trend', 'stable')
    alignment_trend = get_state_value(user, 'alignment.trend', 'stable')
    signals['progress_trend_negative'] = (
        weight_trend in ('increasing',)
        or alignment_trend in ('declining', 'decreasing')
    )

    return signals


def _format_trajectory_injection(signals):
    """
    Format trajectory signals as a compact prompt injection block.

    Source-Integrity Gate enforced:
    - Only emits validated signals that cleared minimum thresholds
    - Insufficient signals produce compact placeholders (no narrative)
    - Deterministic, micro-compressed output

    Args:
        signals: dict from _build_trajectory_signals()

    Returns:
        str — formatted trajectory signal block, or empty string.
    """
    renegotiations = signals.get('renegotiation_patterns', [])
    tier1_skips = signals.get('tier1_skip_patterns', [])
    consecutive = signals.get('consecutive_tier1_skips', 0)
    drift_14d = signals.get('drift_scenario_count_14d', 0)
    overrides_10d = signals.get('override_count_10d', 0)
    progress_negative = signals.get('progress_trend_negative', False)
    insufficient = signals.get('insufficient', [])

    # Check for any validated signals OR insufficient placeholders
    has_validated = (
        renegotiations
        or tier1_skips
        or consecutive >= 2
        or drift_14d >= 2
        or overrides_10d >= 3
    )
    if not has_validated and not insufficient:
        return ''

    lines = ["--- TRAJECTORY SIGNALS ---"]

    # Validated signals
    if renegotiations:
        for r in renegotiations:
            lines.append(
                f"RENEGOTIATION: {r['behavior']} overridden {r['count']}x "
                f"in {r['window_days']} days"
            )

    if tier1_skips:
        for s in tier1_skips:
            lines.append(
                f"TIER1_SKIP: {s['behavior']} skipped {s['count']}x "
                f"in {s['window_days']} days"
            )

    if consecutive >= 2:
        lines.append(f"CONSECUTIVE_TIER1_SKIPS: {consecutive} consecutive days")

    if drift_14d >= 2:
        lines.append(f"DRIFT_FREQUENCY: {drift_14d} drift-critical days in 14 days")

    if overrides_10d >= 3:
        lines.append(f"OVERRIDE_RATE: {overrides_10d} overrides in 10 days")

    if progress_negative:
        lines.append("PROGRESS_TREND: negative")

    # Insufficient signal placeholders (compact, no narrative)
    for sig in insufficient:
        lines.append(f"INSUFFICIENT SIGNAL: {sig}")

    lines.append("--- END TRAJECTORY SIGNALS ---")
    return '\n'.join(lines)


# =========================================================================
# PHASE 4 R1 — DECISION BRANCH MODELING
# =========================================================================

# Decision-indicating keywords — user expresses a pending decision.
# Must co-occur with alignment-impacting context to activate.
# Organized by detection category for maintainability.
_DECISION_INDICATORS = (
    # Deliberation
    'should i',
    'thinking about',
    'considering',
    'debating whether',
    'not sure if i should',
    'torn between',
    'trying to decide',
    'would it be better',
    # Skip / cancel
    'skip today',
    'skip this',
    'cancel',
    'swap',
    # Deferral-by-action
    'push it',
    'push this',
    'push the',
    'move it to',
    'move it',
    'moved it',
    'move this',
    'moved this',
    'reschedule',
    'rescheduling',
    'shift this',
    'shift it',
    'defer',
    'postpone',
    # Explicit delay
    'decide later',
    'later tonight',
    'later this week',
    'later this month',
    'not happening this',
    'ill deal with it later',
    'ill handle it later',
    'ill get to it later',
    # Time-based abandonment
    'restart next month',
    'restart later',
    'restart next week',
    'start over next month',
    'start over later',
    'supposed to start',
    'was supposed to',
    # Repeated-deferral acknowledgement
    'it never happens',
    'never actually',
    'keep saying',
    'keep pushing',
    'keep putting it off',
    # Commitment withdrawal
    'stop tracking',
    'stop working on',
    'drop it',
    'drop this',
    'drop the goal',
    'pause this',
    'pause the goal',
    'shelve this',
    'scrap it',
    # Renegotiation acknowledgement
    'renegotiating this',
    'renegotiated this',
    'moved it again',
    'again and again',
    # Flat refusal (gate still requires alignment target)
    'not doing it tonight',
    'not doing this',
    'im not doing it',
)


def _build_decision_branch_signals(user):
    """
    Gather signals relevant to decision branch activation.

    Collects:
    - Active goals with deadlines within 14 days
    - Protected time blocks for today
    - Deferred decision count (renegotiations in last 7 days)

    Read-only — no writes, no side effects.

    Returns:
        dict — decision branch signals.
    """
    signals = {
        'goals_within_14d': [],
        'protected_blocks_today': [],
        'deferrals_7d': 0,
    }

    fourteen_days = timezone.localdate() + datetime.timedelta(days=14)
    today = timezone.localdate()

    # Goals with deadlines within 14 days
    try:
        from apps.purpose.models import LifeGoal
        upcoming_goals = LifeGoal.objects.filter(
            user=user,
            status='active',
            target_date__isnull=False,
            target_date__lte=fourteen_days,
            target_date__gte=today,
        ).values('title', 'target_date')[:10]
        for g in upcoming_goals:
            days_left = (g['target_date'] - today).days
            signals['goals_within_14d'].append({
                'title': g['title'],
                'days_remaining': days_left,
            })
    except Exception:
        pass

    # Overdue goals (active, past target_date)
    try:
        from apps.purpose.models import LifeGoal
        overdue = LifeGoal.objects.filter(
            user=user,
            status='active',
            target_date__isnull=False,
            target_date__lt=today,
        ).values('title', 'target_date')[:5]
        for g in overdue:
            days_overdue = (today - g['target_date']).days
            signals['goals_within_14d'].append({
                'title': g['title'],
                'days_remaining': -days_overdue,
            })
    except Exception:
        pass

    # Protected blocks for today
    try:
        from apps.core.blueprint.models import ArchitecturePlan
        plan = ArchitecturePlan.get_active_for_date(user, today)
        if plan:
            protected = plan.blocks.filter(tier=1, is_completed=False)
            for b in protected[:5]:
                signals['protected_blocks_today'].append({
                    'title': b.title,
                    'start': b.start_time.strftime('%H:%M') if b.start_time else '',
                })
    except Exception:
        pass

    # Deferral count — from SAE truth layer
    try:
        from apps.core.ai_state.state_engine import get_state_value
        signals['deferrals_7d'] = get_state_value(
            user, 'intervention.deferrals_7d', 0
        )
    except Exception:
        pass

    return signals


def _normalize_input(text):
    """
    Normalize user input for pattern matching.

    - Lowercase
    - Normalize apostrophes (curly → straight, then strip)
    - Strip punctuation (preserve spaces and apostrophes for contractions)
    - Collapse repeated spaces

    Returns:
        str — normalized text for substring matching.
    """
    if not text:
        return ''
    result = text.lower()
    # Normalize curly apostrophes/quotes to straight
    result = result.replace('\u2019', "'").replace('\u2018', "'")
    result = result.replace('\u201c', '"').replace('\u201d', '"')
    # Normalize contractions: "i'll" → "ill", "it's" → "its", "i'm" → "im"
    # This ensures patterns without apostrophes match contracted forms.
    result = result.replace("'", '')
    # Strip remaining punctuation (keep letters, digits, spaces)
    result = re.sub(r'[^\w\s]', ' ', result)
    # Collapse repeated spaces
    result = re.sub(r'\s+', ' ', result).strip()
    return result


def _detect_decision_language(user_input):
    """
    Detect decision-indicating language in user input.

    Normalizes input before matching. Deterministic substring matching — no NLP.

    Returns:
        list[str] — matched decision indicator phrases (empty if none).
    """
    if not user_input:
        return []
    normalized = _normalize_input(user_input)
    return [d for d in _DECISION_INDICATORS if d in normalized]


def evaluate_decision_branch_gate(context, user_input=''):
    """
    Evaluate whether Decision Branch Modeling should activate.

    Condition A: User expresses a pending decision that impacts:
    - An active goal with deadline ≤14 days
    - A protected time block
    - A known threshold risk pattern

    Condition B: A decision has been deferred ≥2 times within 7 days.

    Both conditions require decision language in user input (Condition A)
    or sufficient deferral history (Condition B).

    Args:
        context: dict from build_cos_context().
        user_input: str — the user's current message.

    Returns:
        dict — {'active': bool, 'reason': str, 'signals': dict}
    """
    db_signals = context.get('decision_branch_signals', {})
    traj_signals = context.get('trajectory_signals', {})

    has_decision_language = bool(_detect_decision_language(user_input))

    # R4: Common passthrough fields for CIM severity evaluation.
    # These are data fields — they do NOT affect gate activation logic.
    _passthrough = {
        'user_input': user_input,
        'deferrals_7d': db_signals.get('deferrals_7d', 0),
    }

    # Condition A: Decision language + alignment-impacting target
    if has_decision_language:
        # Check: goal with deadline ≤14 days
        goals_14d = db_signals.get('goals_within_14d', [])
        if goals_14d:
            return {
                'active': True,
                'reason': 'decision_impacts_goal_deadline',
                'signals': {
                    'goals': goals_14d,
                    'decision_language': True,
                },
                **_passthrough,
            }

        # Check: protected time block today
        protected = db_signals.get('protected_blocks_today', [])
        if protected:
            return {
                'active': True,
                'reason': 'decision_impacts_protected_block',
                'signals': {
                    'protected_blocks': protected,
                    'decision_language': True,
                },
                **_passthrough,
            }

        # Check: threshold risk pattern active
        renegotiations = traj_signals.get('renegotiation_patterns', [])
        tier1_skips = traj_signals.get('tier1_skip_patterns', [])
        consecutive = traj_signals.get('consecutive_tier1_skips', 0)
        if renegotiations or tier1_skips or consecutive >= 2:
            return {
                'active': True,
                'reason': 'decision_during_threshold_risk',
                'signals': {
                    'renegotiations': len(renegotiations),
                    'tier1_skips': len(tier1_skips),
                    'consecutive_skips': consecutive,
                    'decision_language': True,
                },
                **_passthrough,
            }

    # Condition B: Decision deferred ≥2 times in 7 days
    deferrals = db_signals.get('deferrals_7d', 0)
    if deferrals >= 2 and has_decision_language:
        return {
            'active': True,
            'reason': 'repeated_deferral',
            'signals': {
                'deferrals_7d': deferrals,
                'decision_language': True,
            },
            **_passthrough,
        }

    return {'active': False, 'reason': '', 'signals': {}, **_passthrough}


DECISION_BRANCH_FRAMEWORK_CLEAN = """
--- DECISION BRANCH MODELING ---

The user is expressing a decision that impacts an active alignment target.

MODELING RULES:
- Strictly deterministic. Reference only known goals, deadlines, behavioral
  history, renegotiation counts, skip counts, protected blocks, workload density.
- Do NOT predict unknown outcomes, invent projections, estimate numbers,
  assign probabilities, or fabricate timeline forecasts.

OUTPUT STRUCTURE (mandatory):

Decision Branch A — Act
• Immediate operational impact
• Short-term alignment effect
• Threshold containment effect
• Identity reinforcement or erosion vector

Decision Branch B — Delay / Do Not Act
• Immediate relief effect
• Threshold proximity effect
• Drift pressure increase (qualitative only)
• Identity erosion vector (if applicable)

Executive Framing
One-line directive recommendation. No permission language.
No motivational phrasing. No open-ended question.

TONE: Dense. Calm. Authoritative. Minimal wording.
No coaching language. No encouragement language.
Neutral executive modeling. No escalation framing.

--- END DECISION BRANCH MODELING ---
"""

DECISION_BRANCH_FRAMEWORK_EROSION = """
--- DECISION BRANCH MODELING (EROSION CONTAINMENT) ---

The user is expressing a decision that impacts an active alignment target.
Erosion markers are present. Do not authorize deferral.

MODELING RULES:
- Strictly deterministic. Reference only known goals, deadlines, behavioral
  history, renegotiation counts, skip counts, protected blocks, workload density.
- Do NOT predict unknown outcomes, invent projections, estimate numbers,
  assign probabilities, or fabricate timeline forecasts.
- Include erosion containment framing in both branches.

OUTPUT STRUCTURE (mandatory):

Decision Branch A — Act
• Immediate operational impact
• Short-term alignment effect
• Threshold containment effect
• Identity reinforcement or erosion vector

Decision Branch B — Delay / Do Not Act
• Immediate relief effect
• Threshold proximity effect
• Drift pressure increase (qualitative only)
• Identity erosion vector

Executive Framing
One-line directive recommendation. No permission language.
No motivational phrasing. No open-ended question.
Erosion containment is the priority.

TONE: Dense. Calm. Authoritative. Minimal wording.
No coaching language. No encouragement language.
Include erosion containment framing. Do not authorize deferral.

--- END DECISION BRANCH MODELING ---
"""

DECISION_BRANCH_FRAMEWORK_DRIFT = """
--- DECISION BRANCH MODELING (STRUCTURAL DRIFT) ---

The user is expressing a decision that impacts an active alignment target.
Structural drift is active. Integrate with 72h/30d modeling.

MODELING RULES:
- Strictly deterministic. Reference only known goals, deadlines, behavioral
  history, renegotiation counts, skip counts, protected blocks, workload density.
- Do NOT predict unknown outcomes, invent projections, estimate numbers,
  assign probabilities, or fabricate timeline forecasts.
- Integrate branch modeling with existing 72h/30d trajectory modeling.
- Do not override Structural Drift escalation tone.

OUTPUT STRUCTURE (mandatory):

Decision Branch A — Act
• Immediate operational impact
• Short-term alignment effect (72h horizon integration)
• Threshold containment effect
• Identity reinforcement vector (30d horizon integration)

Decision Branch B — Delay / Do Not Act
• Immediate relief effect
• Threshold proximity effect (72h horizon integration)
• Drift pressure increase (qualitative only)
• Identity erosion vector (30d horizon integration)

Executive Framing
One-line directive recommendation. No permission language.
No motivational phrasing. No open-ended question.
Structural drift tone preserved.

TONE: Dense. Calm. Authoritative. Minimal wording.
No coaching language. No encouragement language.
Structural drift escalation tone intact.

--- END DECISION BRANCH MODELING ---
"""


# =========================================================================
# PHASE 4 R5 — ENFORCEMENT ESCALATION LADDER
# =========================================================================

# R5B: Resistance type categories for directive generation.
_RESISTANCE_DEFERRAL = 'deferral'
_RESISTANCE_CANCELLATION = 'cancellation'
_RESISTANCE_ABANDONMENT = 'abandonment'
_RESISTANCE_DELIBERATION = 'deliberation'

# Deferral-action terms for resistance detection.
_DEFERRAL_TERMS = (
    'push', 'move', 'moved', 'defer', 'postpone', 'shift',
    'reschedule', 'rescheduling', 'later',
)


def _extract_directive_subject(gate_result):
    """
    Extract a brief subject reference for the enforcement directive.

    Uses goal title or protected block title from gate signals.
    Titles over 4 words are replaced with a contextual fallback.

    Returns:
        str — lowercase subject reference (e.g. 'test goal', 'the block').
    """
    signals = gate_result.get('signals', {})
    reason = gate_result.get('reason', '')

    if reason == 'decision_impacts_protected_block':
        blocks = signals.get('protected_blocks', [])
        if blocks:
            title = blocks[0].get('title', '').strip()
            if title and len(title.split()) <= 4:
                return title.lower()
        return 'the protected block'

    goals = signals.get('goals', [])
    if goals:
        title = goals[0].get('title', '').strip()
        if title and len(title.split()) <= 4:
            return title.lower()

    return 'the commitment'


def _detect_resistance_type(user_input):
    """
    Detect user's resistance type from input for directive generation.

    Categories: deferral, cancellation, abandonment, deliberation.

    Returns:
        str — resistance type constant.
    """
    if not user_input:
        return _RESISTANCE_DELIBERATION
    normalized = _normalize_input(user_input)

    # Abandonment (most severe)
    if _detect_abandonment_language(user_input):
        return _RESISTANCE_ABANDONMENT

    # Deferral
    if any(t in normalized for t in _DEFERRAL_TERMS):
        return _RESISTANCE_DEFERRAL

    # Cancellation
    if 'cancel' in normalized:
        return _RESISTANCE_CANCELLATION

    return _RESISTANCE_DELIBERATION


def _generate_enforcement_directive(level, gate_result):
    """
    Generate a context-aware Executive Framing directive sentence.

    R5B: Returns a production-ready sentence — no meta-text, no examples,
    no instructional language. Exactly one sentence, ≤12 words target,
    ≤18 words max. Declarative command tone.

    Args:
        level: int 0–3 from _evaluate_enforcement_level().
        gate_result: dict from evaluate_decision_branch_gate().

    Returns:
        str — rendered directive sentence.
    """
    subject = _extract_directive_subject(gate_result)
    resistance = _detect_resistance_type(gate_result.get('user_input', ''))

    # Level 0 — Clarification: neutral execution
    if level == 0:
        if resistance == _RESISTANCE_DELIBERATION:
            return f"Execute {subject} as scheduled."
        return f"Complete {subject} as planned."

    # Level 1 — Reinforcement: firm, boundary introduced
    if level == 1:
        if resistance == _RESISTANCE_DEFERRAL:
            return f"Do not reschedule. Complete {subject} tonight."
        if resistance == _RESISTANCE_CANCELLATION:
            return f"Maintain {subject}. No cancellation."
        return f"No delay. Proceed with {subject}."

    # Level 2 — Containment: boundary-setting
    if level == 2:
        if resistance == _RESISTANCE_DEFERRAL:
            return f"Stop deferring. Execute {subject} today."
        if resistance == _RESISTANCE_CANCELLATION:
            return f"Do not cancel {subject}. Execute as planned."
        if resistance == _RESISTANCE_ABANDONMENT:
            return f"Do not abandon {subject}. Execute today."
        return f"Stop renegotiating. Complete {subject} now."

    # Level 3 — Control Assertion: shortest possible
    if resistance == _RESISTANCE_ABANDONMENT:
        return f"This pattern ends now. Execute {subject}."
    return f"No further delay. Execute {subject}."


def _evaluate_enforcement_level(gate_result, activation_state):
    """
    Determine enforcement level (0–3) for Executive Framing.

    R5: Intra-tier enforcement ladder. Increases directive firmness
    proportional to resistance patterns without changing tiers or
    adding verbosity.

    Level 0 — Clarification: First deferral, no compounding.
    Level 1 — Reinforcement: Single deferral or mild erosion.
    Level 2 — Containment: Repeated deferrals, abandonment, or EARLY_EROSION.
    Level 3 — Control Assertion: Repeated deferrals + abandonment,
              or EARLY_EROSION + repeated deferral.

    STRUCTURAL_DRIFT does NOT automatically force Level 3.

    Args:
        gate_result: dict from evaluate_decision_branch_gate().
        activation_state: str — CLEAN / EARLY_EROSION / STRUCTURAL_DRIFT.

    Returns:
        int — enforcement level 0–3.
    """
    user_input = gate_result.get('user_input', '')
    deferrals_7d = gate_result.get(
        'deferrals_7d', gate_result.get('signals', {}).get('deferrals_7d', 0)
    )
    has_abandonment = bool(_detect_abandonment_language(user_input))
    has_erosion_markers = bool(detect_erosion_markers(user_input))
    is_erosion_tier = activation_state == ACTIVATION_EARLY_EROSION

    # Level 3: Compound resistance patterns
    if deferrals_7d >= 2 and has_abandonment:
        return 3
    if is_erosion_tier and deferrals_7d >= 2:
        return 3
    if has_abandonment and has_erosion_markers:
        return 3

    # Level 2: Containment triggers
    if deferrals_7d >= 2:
        return 2
    if has_abandonment:
        return 2
    if is_erosion_tier:
        return 2
    if gate_result.get('reason') == 'decision_impacts_protected_block':
        return 2

    # Level 1: Mild resistance
    if has_erosion_markers:
        return 1
    # Single deferral-action indicators (push/move/shift/defer/postpone/etc.)
    indicators = _detect_decision_language(user_input)
    _deferral_actions = (
        'push it', 'push this', 'push the', 'move it', 'moved it',
        'move this', 'moved this', 'move it to', 'reschedule',
        'rescheduling', 'shift this', 'shift it', 'defer', 'postpone',
        'decide later', 'later tonight', 'later this week',
        'later this month',
    )
    if any(i in _deferral_actions for i in indicators):
        return 1

    # Level 0: Clean deliberation
    return 0


def _format_decision_branch_injection(gate_result, activation_state):
    """
    Format the decision branch modeling block for prompt injection.

    Selects the tier-appropriate framework variant, conditionally appends
    Cost-of-Inaction modeling (R2), and appends contextual signal data
    for LLM grounding.

    Args:
        gate_result: dict from evaluate_decision_branch_gate().
        activation_state: str — CLEAN / EARLY_EROSION / STRUCTURAL_DRIFT.

    Returns:
        str — formatted decision branch injection, or empty string.
    """
    if not gate_result.get('active'):
        return ''

    # Select tier-appropriate framework
    if activation_state == ACTIVATION_STRUCTURAL_DRIFT:
        framework = DECISION_BRANCH_FRAMEWORK_DRIFT
    elif activation_state == ACTIVATION_EARLY_EROSION:
        framework = DECISION_BRANCH_FRAMEWORK_EROSION
    else:
        framework = DECISION_BRANCH_FRAMEWORK_CLEAN

    # R5/R5B: Generate enforcement-level directive and inject into framework
    enforcement_level = _evaluate_enforcement_level(gate_result, activation_state)
    directive = _generate_enforcement_directive(enforcement_level, gate_result)

    # Replace the Executive Framing block in the framework template.
    # Match the static block that starts with "Executive Framing\n"
    # and ends before "\nTONE:". Replace with the rendered directive.
    framework_text = framework.strip()
    framing_block = f"Executive Framing\n{directive}"
    framework_text = re.sub(
        r'Executive Framing\n.*?(?=\nTONE:)',
        framing_block,
        framework_text,
        flags=re.DOTALL,
    )

    lines = [framework_text]

    # R2: Cost-of-Inaction Modeling (conditional)
    cim_block = _build_cim_injection(gate_result, activation_state)
    if cim_block:
        lines.append("")
        lines.append(cim_block)

    # Append grounding signals
    signals = gate_result.get('signals', {})
    reason = gate_result.get('reason', '')

    signal_lines = ["--- DECISION CONTEXT ---"]

    if reason:
        signal_lines.append(f"ACTIVATION: {reason}")

    goals = signals.get('goals', [])
    if goals:
        for g in goals[:3]:
            days = g['days_remaining']
            if days < 0:
                signal_lines.append(f"GOAL: {g['title']} — {abs(days)} days overdue")
            elif days == 0:
                signal_lines.append(f"GOAL: {g['title']} — due today")
            else:
                signal_lines.append(f"GOAL: {g['title']} — {days} days remaining")

    protected = signals.get('protected_blocks', [])
    if protected:
        for b in protected[:3]:
            signal_lines.append(f"PROTECTED BLOCK: {b['title']} at {b['start']}")

    if signals.get('renegotiations'):
        signal_lines.append(
            f"RENEGOTIATION PATTERNS: {signals['renegotiations']} active"
        )
    if signals.get('tier1_skips'):
        signal_lines.append(
            f"TIER1 SKIP PATTERNS: {signals['tier1_skips']} active"
        )
    if signals.get('consecutive_skips', 0) >= 2:
        signal_lines.append(
            f"CONSECUTIVE SKIPS: {signals['consecutive_skips']} days"
        )
    if signals.get('deferrals_7d', 0) >= 2:
        signal_lines.append(
            f"DEFERRALS: {signals['deferrals_7d']} in 7 days"
        )

    signal_lines.append("--- END DECISION CONTEXT ---")

    lines.append("")
    lines.append('\n'.join(signal_lines))

    return '\n'.join(lines)


# =========================================================================
# PHASE 4 R2 — COST-OF-INACTION MODELING (CIM)
# =========================================================================


# R4: Abandonment phrases — checked against normalized user input.
# Subset of commitment-withdrawal and time-based-abandonment patterns
# that signal intent to disengage from a goal or plan entirely.
_CIM_ABANDONMENT_PHRASES = (
    'stop tracking',
    'stop working on',
    'drop it',
    'drop this',
    'drop the goal',
    'dropping the goal',
    'dropping this',
    'dropping it',
    'dropping the',
    'pause this',
    'pause the goal',
    'shelve this',
    'scrap it',
    'scrap this',
    'restart next month',
    'restart later',
    'restart next week',
    'start over next month',
    'start over later',
    'give up',
    'giving up',
    'not ready to face',
    'walking away',
    'walk away',
)


def _detect_abandonment_language(user_input):
    """
    Detect abandonment language in user input for CIM severity.

    Deterministic substring matching against normalized input.
    Used by CIM severity evaluation — NOT by the decision branch gate.

    Args:
        user_input: str — the user's current message.

    Returns:
        list[str] — matched abandonment phrases (empty if none).
    """
    if not user_input:
        return []
    normalized = _normalize_input(user_input)
    return [p for p in _CIM_ABANDONMENT_PHRASES if p in normalized]


def _evaluate_cim_severity(gate_result, activation_state):
    """
    Evaluate whether Cost-of-Inaction severity reaches Moderate threshold.

    R4: Behavior-driven activation — deadline proximity alone does NOT
    qualify. CIM activates only when compounding or erosion is present.

    Severity is Moderate or Higher if ANY are true:
    - Goal already overdue
    - ≥2 deferrals within 7 days
    - Protected block cancellation involved
    - Abandonment language detected in user input
    - EARLY_EROSION or STRUCTURAL_DRIFT tier active

    Deadline proximity (goal ≤14d) is NOT a standalone severity factor.

    Args:
        gate_result: dict from evaluate_decision_branch_gate().
        activation_state: str — CLEAN / EARLY_EROSION / STRUCTURAL_DRIFT.

    Returns:
        dict — {'moderate': bool, 'factors': list[str],
                 'has_overdue': bool, 'has_deferrals': bool,
                 'has_protected': bool, 'has_abandonment': bool,
                 'has_erosion_or_drift': bool}
    """
    signals = gate_result.get('signals', {})
    factors = []

    # 1. Goal already overdue
    has_overdue = False
    goals = signals.get('goals', [])
    for g in goals:
        if g.get('days_remaining', 0) < 0:
            has_overdue = True
            break
    if has_overdue:
        factors.append('goal_overdue')

    # 2. ≥2 deferrals within 7 days (from gate passthrough or signals)
    deferrals_7d = gate_result.get(
        'deferrals_7d', signals.get('deferrals_7d', 0)
    )
    has_deferrals = deferrals_7d >= 2
    if has_deferrals:
        factors.append('repeated_deferrals')

    # 3. Protected block cancellation
    has_protected = (
        gate_result.get('reason') == 'decision_impacts_protected_block'
        or bool(signals.get('protected_blocks'))
    )
    if has_protected:
        factors.append('protected_block_impact')

    # 4. Abandonment language in user input (R4)
    user_input = gate_result.get('user_input', '')
    has_abandonment = bool(_detect_abandonment_language(user_input))
    if has_abandonment:
        factors.append('abandonment_language')

    # 5 & 6. Erosion or drift tier
    has_erosion_or_drift = activation_state in (
        ACTIVATION_EARLY_EROSION, ACTIVATION_STRUCTURAL_DRIFT,
    )
    if has_erosion_or_drift:
        factors.append('tier_escalated')

    return {
        'moderate': bool(factors),
        'factors': factors,
        'has_overdue': has_overdue,
        'has_deferrals': has_deferrals,
        'has_protected': has_protected,
        'has_abandonment': has_abandonment,
        'has_erosion_or_drift': has_erosion_or_drift,
    }


# CIM instruction blocks — tier-proportional.
# Placed between Decision Branch B and Executive Framing in the LLM prompt.

CIM_BLOCK_CLEAN = """\
After Decision Branch B bullets, append:

Cost of Inaction — 72h Window
• What compresses (concrete: remaining work days, schedule density)
• What compounds (concrete: deferral count, renegotiation proximity)
• What becomes harder (concrete: recovery effort relative to current effort)

{cim_14_30d}
RULES: Deterministic only. Reference known deadlines, deferral counts,
skip counts, protected blocks, workload density. No probabilities.
No speculative language. No emotional framing. No catastrophic language.
Controlled, neutral consequence mapping. No escalation tone.
Keep CIM section to 3–6 lines total."""

CIM_BLOCK_EROSION = """\
After Decision Branch B bullets, append:

Cost of Inaction — 72h Window
• What compresses (concrete: remaining work days, schedule density)
• What compounds (concrete: deferral count, erosion pattern reinforcement)
• What becomes harder (concrete: recovery cost escalation)

{cim_14_30d}
RULES: Deterministic only. Reference known deadlines, deferral counts,
skip counts, protected blocks, workload density. No probabilities.
No speculative language. No emotional framing. Clear compounding language.
No deferral authorization. Keep CIM section to 3–6 lines total."""

CIM_BLOCK_DRIFT = """\
After Decision Branch B bullets, append:

Cost of Inaction — 72h Window
• What compresses (integrate with existing 72h trajectory modeling)
• What compounds (reference existing renegotiation/skip signal data)
• What becomes harder (concrete: recovery cost at current drift rate)

{cim_14_30d}
RULES: Deterministic only. Integrate with existing 72h/30d modeling —
do not duplicate trajectory framework content. Reference known deadlines,
deferral counts, skip counts, protected blocks, workload density.
No probabilities. No speculative language. No intensification beyond
Phase 3 rules. Keep CIM section to 3–6 lines total."""

CIM_14_30D_BLOCK = """\
Cost of Inaction — 14–30 Day Window
• Recovery cost increase (structural, not speculative)
• Threshold proximity escalation (reference known counts vs thresholds)
• Identity erosion reinforcement (directional, not predictive)"""


def _build_cim_injection(gate_result, activation_state):
    """
    Build Cost-of-Inaction injection block if severity is Moderate+.

    Renders ONLY when Decision Branch is active AND alignment-impact
    severity reaches Moderate threshold. Placed between Branch B
    and Executive Framing in the LLM instruction set.

    Args:
        gate_result: dict from evaluate_decision_branch_gate().
        activation_state: str — CLEAN / EARLY_EROSION / STRUCTURAL_DRIFT.

    Returns:
        str — CIM instruction block, or empty string if severity is Low.
    """
    severity = _evaluate_cim_severity(gate_result, activation_state)
    if not severity['moderate']:
        return ''

    # Determine whether 14–30 day window applies:
    # Include if overdue, repeated deferrals, abandonment language,
    # or erosion/drift tier active.
    include_14_30d = (
        severity['has_overdue']
        or severity['has_deferrals']
        or severity['has_abandonment']
        or severity['has_erosion_or_drift']
    )

    cim_14_30d = CIM_14_30D_BLOCK if include_14_30d else ''

    # Select tier-appropriate CIM block
    if activation_state == ACTIVATION_STRUCTURAL_DRIFT:
        template = CIM_BLOCK_DRIFT
    elif activation_state == ACTIVATION_EARLY_EROSION:
        template = CIM_BLOCK_EROSION
    else:
        template = CIM_BLOCK_CLEAN

    return template.format(cim_14_30d=cim_14_30d).strip()


# =========================================================================
# PHASE 3 — TIERED ACTIVATION
# =========================================================================

# Activation states
ACTIVATION_CLEAN = 'CLEAN'
ACTIVATION_EARLY_EROSION = 'EARLY_EROSION'
ACTIVATION_STRUCTURAL_DRIFT = 'STRUCTURAL_DRIFT'

# Semantic erosion markers — case-insensitive substring match.
# Presence of ANY marker in user input triggers EARLY_EROSION (if no
# threshold-based STRUCTURAL_DRIFT already active).
# All markers stored in normalized form (no apostrophes) since
# _normalize_input() strips apostrophes before matching.
_EROSION_MARKERS = (
    'again',
    'a few',
    'most',
    'not a big deal',
    'ill make it up',
    'next week',
    'next month',
    'looser system',
    'just this once',
    'its fine',
    'not that serious',
    'not happening',
    'ill try next week',
    'ill try next month',
    'when things calm down',
    'not ready yet',
    'not ready to face',
    'someday',
    'eventually',
    'for now',
)


def detect_erosion_markers(user_input):
    """
    Detect semantic erosion markers in user input.

    Normalizes input before matching. Deterministic substring matching — no NLP.

    Args:
        user_input: str — the user's message.

    Returns:
        list[str] — matched erosion marker phrases (empty if none).
    """
    if not user_input:
        return []
    normalized = _normalize_input(user_input)
    return [m for m in _EROSION_MARKERS if m in normalized]


def determine_activation_state(trajectory_signals, user_input=''):
    """
    Determine the Phase 3 tiered activation state.

    Priority:
    1. STRUCTURAL_DRIFT — numeric thresholds met (existing logic).
    2. EARLY_EROSION — no thresholds met, but erosion markers present.
    3. CLEAN — neither condition.

    Threshold-based activation always overrides semantic detection.

    Args:
        trajectory_signals: dict from _build_trajectory_signals().
        user_input: str — the user's current message.

    Returns:
        str — one of ACTIVATION_CLEAN, ACTIVATION_EARLY_EROSION,
               ACTIVATION_STRUCTURAL_DRIFT.
    """
    # Check numeric thresholds (STRUCTURAL_DRIFT)
    renegotiations = trajectory_signals.get('renegotiation_patterns', [])
    tier1_skips = trajectory_signals.get('tier1_skip_patterns', [])
    consecutive = trajectory_signals.get('consecutive_tier1_skips', 0)

    has_structural = (
        bool(renegotiations)       # ≥3 renegotiations on any behavior in 10d
        or bool(tier1_skips)       # ≥2 Tier 1 skips on any behavior in 7d
        or consecutive >= 2        # Consecutive Tier 1 skip days
    )

    if has_structural:
        return ACTIVATION_STRUCTURAL_DRIFT

    # Check semantic erosion markers (EARLY_EROSION)
    if detect_erosion_markers(user_input):
        return ACTIVATION_EARLY_EROSION

    return ACTIVATION_CLEAN


# Tiered framework injections — replaces the monolithic TRAJECTORY_PRECISION_FRAMEWORK
# injection for CLEAN and EARLY_EROSION states. STRUCTURAL_DRIFT still gets the
# full framework.

EARLY_EROSION_FRAMEWORK = """
--- TRAJECTORY AWARENESS (EARLY EROSION) ---

Semantic erosion markers detected in user input. No numeric thresholds met.

RESPONSE POSTURE:
- Observational, proportional tone. No escalation.
- Acknowledge the language pattern without fabricating data.
- Do NOT produce 72-hour projections.
- Do NOT produce 30-day identity projections.
- Do NOT reference drift frequency, renegotiation counts, or skip patterns.
- Do NOT invent numeric evidence.

FORBIDDEN DEFERRAL LANGUAGE — never include in your response:
- "tomorrow", "next week", "Monday", "later", "when I can",
  "make up", "make it up", "catch up", "start fresh".
- Any phrasing that defers action beyond today.
The corrective minimum must be immediate — today, now, this session.

STRUCTURE (when erosion language is relevant to the topic):
1. Name what the language suggests — one sentence.
   Example: "The language suggests this may be trending."
2. State the conditional escalation — one sentence.
   Example: "If this repeats, it becomes structural."
3. Corrective minimum — one sentence. Must be today. Must be concrete.
   Format: "Corrective minimum: [duration/scope] today. [Format note.]"
   Examples:
     - "Corrective minimum: 10 minutes today. Any format."
     - "Corrective minimum: 5 minutes today. One chapter."
     - "Corrective minimum: one entry today. Any length."

If the user's message is not about a commitment (e.g., general question,
weekly review request), ignore erosion markers entirely. They only activate
when the user is discussing a specific behavior or commitment.

Keep 3–5 sentences total. No horizon modeling. No pattern naming.
No motivational tone. Compressed.

--- END TRAJECTORY AWARENESS ---
"""


# =========================================================================
# OUTPUT COMPLIANCE GATE
# =========================================================================

# Negation tokens — if ANY of these appear in the same clause as a
# write-verb match, the match is treated as a denial and skipped.
_NEGATION_TOKENS = frozenset({
    'not', 'no', 'never', 'nothing', 'none',
    "can't", 'cannot', "won't", "wouldn't",
    "isn't", "doesn't", "don't", "didn't",
    "hasn't", "wasn't", "weren't", "shouldn't",
    'without', 'unable',
})

# Write-verb patterns: each entry is (compiled_regex, replacement_builder).
# replacement_builder is a callable(match) -> str that produces the
# counterfactual wording from the match groups.
_WRITE_CLAIM_PATTERNS = [
    # "This will be logged as X" / "has been recorded" / "is saved" / "was stored"
    re.compile(
        r'\b(will be|has been|is being|is now|is|was)\s+'
        r'(logged|recorded|tracked|flagged|noted|persisted|saved|stored)\b',
        re.IGNORECASE,
    ),
    # "Marked as X" / "Marking this as X"
    re.compile(
        r'\b(marked|marking)\s+(?:this\s+)?as\b',
        re.IGNORECASE,
    ),
    # "Logging this as X" / "Recording this" / "Saving this"
    re.compile(
        r'\b(logging|recording|tracking|flagging|noting|persisting|saving|updating)'
        r'\s+this\b',
        re.IGNORECASE,
    ),
    # "I've logged X" / "I recorded X" / "I have saved X"
    re.compile(
        r"\b(I've|I have|I)\s+"
        r'(logged|recorded|tracked|flagged|noted|persisted|saved|stored|updated)\b',
        re.IGNORECASE,
    ),
]


def _extract_clause(text, start, end):
    """
    Extract the clause containing positions [start, end) from text.

    Walks backward/forward to the nearest sentence boundary (. ! ? ;)
    or up to 80 characters, whichever comes first.

    Returns:
        str — the clause text (lowercased for token matching).
    """
    # Walk backward to clause boundary
    clause_start = start
    limit = max(0, start - 80)
    while clause_start > limit:
        ch = text[clause_start - 1]
        if ch in '.!?;:\n':
            break
        clause_start -= 1

    # Walk forward to clause boundary
    clause_end = end
    limit = min(len(text), end + 80)
    while clause_end < limit:
        ch = text[clause_end]
        if ch in '.!?;:\n':
            clause_end += 1  # include the punctuation
            break
        clause_end += 1

    return text[clause_start:clause_end].lower()


def _clause_has_negation(text, start, end):
    """
    Check whether the clause surrounding a match contains a negation token.

    Uses _extract_clause to find the local clause, then tokenizes and
    checks for intersection with _NEGATION_TOKENS.

    Args:
        text: full response text.
        start: match start position.
        end: match end position.

    Returns:
        bool — True if negation found (match should be skipped).
    """
    clause = _extract_clause(text, start, end)
    # Tokenize: split on whitespace and strip punctuation edges
    tokens = set()
    for raw in clause.split():
        # Keep apostrophe-containing contractions intact
        cleaned = raw.strip('.,;:!?"()[]{}')
        if cleaned:
            tokens.add(cleaned)
    return bool(tokens & _NEGATION_TOKENS)


def _build_replacement(match):
    """
    Build counterfactual replacement text for an affirmative write-claim match.

    Dispatches based on which pattern matched, using captured groups.
    Preserves original punctuation and surrounding whitespace.
    """
    full = match.group(0)
    groups = match.groups()

    # Pattern 1: "(will be|has been|is|was) (logged|recorded|...)"
    if len(groups) == 2 and groups[0].lower() in (
        'will be', 'has been', 'is being', 'is now', 'is', 'was',
    ):
        return f'would be {groups[1].lower()}'

    # Pattern 2: "(marked|marking) [this] as"
    if groups[0].lower() in ('marked', 'marking'):
        return 'would be marked as'

    # Pattern 3: "(logging|recording|...) this"
    gerund_verbs = {
        'logging', 'recording', 'tracking', 'flagging',
        'noting', 'persisting', 'saving', 'updating',
    }
    if groups[0].lower() in gerund_verbs:
        return f'would {groups[0].lower()} this'

    # Pattern 4: "(I've|I have|I) (logged|recorded|...)"
    if len(groups) == 2 and groups[0].lower() in ("i've", "i have", "i"):
        # "I have saved" → "I would have saved" (not "I have would have saved")
        # "I've recorded" → "I would have recorded"
        # "I logged" → "I would have logged"
        return f'I would have {groups[1].lower()}'

    # Fallback: return original (should not reach here)
    return full


# -------------------------------------------------------------------------
# Future-promise and mode-naming patterns (gate-level safety net)
# -------------------------------------------------------------------------
# These patterns strip language that the prompt-level rules should prevent,
# but serve as a safety net for when the LLM ignores those instructions.

# Future-promise phrases: "when execution resumes", "once writes are available",
# "when you exit Learning Mode", "will be saved later", etc.
_FUTURE_PROMISE_PATTERNS = [
    # "when/once <execution/writes/Learning Mode> <resumes/ends/available/re-enabled>"
    re.compile(
        r'\b(?:when|once|after|as soon as)\s+'
        r'(?:execution|writes?|write operations?|saving|logging|recording|'
        r'learning mode|the system)\s+'
        r'(?:resumes?|is re-enabled|is enabled|is available|are available|'
        r'are re-enabled|ends?|is lifted|is turned off|comes back|returns?)\b',
        re.IGNORECASE,
    ),
    # "when you exit/leave Learning Mode" / "when you turn off Learning Mode"
    re.compile(
        r'\b(?:when|once|after)\s+you\s+'
        r'(?:exit|leave|turn off|disable|deactivate)\s+'
        r'(?:learning mode|this mode|the current mode)\b',
        re.IGNORECASE,
    ),
    # "will be <saved/logged/recorded/...> later/afterward/when ready"
    re.compile(
        r'\bwill be\s+'
        r'(?:saved|logged|recorded|tracked|flagged|noted|persisted|stored|updated|scheduled)'
        r'\s+(?:later|afterward|afterwards|when ready|when available|when possible)\b',
        re.IGNORECASE,
    ),
    # "I'll <save/log/record/...> this/that/it <later/when/once>"
    re.compile(
        r"\b(?:I'll|I will)\s+"
        r'(?:save|log|record|track|flag|note|persist|store|update|schedule)\s+'
        r'(?:this|that|it)\s+'
        r'(?:later|afterward|afterwards|when|once)\b',
        re.IGNORECASE,
    ),
]

# Learning Mode name references (should never be exposed to user)
_MODE_NAME_PATTERN = re.compile(
    r'\b[Ll]earning\s+[Mm]ode\b',
)


def _strip_future_promises(text):
    """
    Remove future-promise phrases from text.

    Strips the promise clause while preserving surrounding sentence structure.
    For sentence-level promises, removes the entire sentence.
    For clause-level promises (after comma/semicolon), removes the clause.
    """
    result = text
    for pattern in _FUTURE_PROMISE_PATTERNS:
        matches = list(pattern.finditer(result))
        for match in reversed(matches):
            start = match.start()
            end = match.end()

            # Check if the promise is preceded by a comma/semicolon (clause-level)
            # If so, strip from the comma onward to end of sentence
            prefix_start = start
            while prefix_start > 0 and result[prefix_start - 1] in ' \t':
                prefix_start -= 1
            if prefix_start > 0 and result[prefix_start - 1] in ',;':
                # Strip from the comma to end of the promise phrase
                # Also consume trailing punctuation and whitespace
                strip_end = end
                while strip_end < len(result) and result[strip_end] in ' \t':
                    strip_end += 1
                # If the promise continues to end of sentence, consume the period
                if strip_end < len(result) and result[strip_end] in '.!':
                    strip_end += 1
                result = result[:prefix_start - 1].rstrip() + '.' + result[strip_end:]
            else:
                # Promise starts a sentence or clause — remove the full promise phrase
                # Consume trailing punctuation, comma, space
                strip_end = end
                while strip_end < len(result) and result[strip_end] in ' ,;:\t':
                    strip_end += 1
                result = result[:start] + result[strip_end:]

    return result


def _strip_mode_names(text):
    """
    Replace 'Learning Mode' references with neutral phrasing.

    'Learning Mode' is an internal system name the user should never see.
    """
    return _MODE_NAME_PATTERN.sub('the current configuration', text)


def apply_output_compliance_gate(text, writes_suppressed):
    """
    Output Compliance Gate — ensures CoS never implies a write-side effect
    when execution_mode suppresses writes (Learning Mode / writes blocked).

    Language-level guarantee only. No logging, no persistence, no side effects.

    Three-layer gate:
    1. Write-verb tense rewriting (clause-level negation guard)
    2. Future-promise stripping (safety net)
    3. Mode-name scrubbing (safety net)

    Clause-level negation guard (Layer 1):
    - For each write-verb match, extracts the surrounding clause
      (to nearest sentence boundary or ±80 chars).
    - If the clause contains a negation token, the match is a denial
      and is left unchanged.
    - Only affirmative write claims are rewritten to counterfactual.

    When writes are suppressed:
    - Affirmative write claims become counterfactual ("would be logged as X")
    - Future promises stripped ("when execution resumes" → removed)
    - Mode names scrubbed ("Learning Mode" → "the current configuration")
    - Denials/negations pass through unchanged
    - Authority posture preserved — no apologies, no explanations

    When writes are allowed:
    - Returns text unchanged.

    Args:
        text: str — the LLM response text.
        writes_suppressed: bool — True if execution_mode blocks writes.

    Returns:
        str — compliant text.
    """
    if not writes_suppressed:
        return text

    if not text:
        return text

    result = text

    # Layer 1: Write-verb tense rewriting with clause-level negation guard
    for pattern in _WRITE_CLAIM_PATTERNS:
        # Process matches right-to-left so replacements don't shift offsets
        matches = list(pattern.finditer(result))
        for match in reversed(matches):
            if _clause_has_negation(result, match.start(), match.end()):
                continue  # Denial — skip
            replacement = _build_replacement(match)
            result = result[:match.start()] + replacement + result[match.end():]

    # Layer 2: Future-promise stripping
    result = _strip_future_promises(result)

    # Layer 3: Mode-name scrubbing
    result = _strip_mode_names(result)

    return result


# =========================================================================
# PHASE 1 — LEARNING MODE CONTEXT (Reduced Profile)
# =========================================================================


def build_learning_mode_context(user):
    """
    Build a reduced context profile for Learning Mode.

    Includes only what CoS needs to ask informed questions:
    - Module permissions (what's enabled)
    - Blueprint state (pillars, tier1 list, style)
    - Governance profile (accountability, sensitivity)
    - Persona profile (coaching style)
    - Schedule awareness (today's load, calendar, medication, fasting)
    - Health/transformation metrics (for informed questioning)

    Excludes (to prevent prompt bloat and tone drift):
    - Executive context object
    - PIE insights / PRIE predictions
    - UAL narrative blocks / governance strategy prompt
    - Learned profile prompt (avoids circular injection during learning)
    - Weekly pressure / feedback profiles / relationship signals
    - Open loops / risk warnings

    Args:
        user: Django User instance.

    Returns:
        dict — Reduced context for Learning Mode.
    """
    context = {
        'learning_mode': True,
        'module_permissions': {},
        'blueprint_state': {},
        'protected_tiers': [],
        'governance_profile': {},
        'persona_profile': {},
        'capacity_snapshot': {},
        'medication_adherence_state': {},
        'active_fast_status': {},
        'calendar_events_today': [],
        'transformation_metrics': {},
        'health_signals': {},
        'user_priorities': [],
    }

    try:
        prefs = user.preferences
        context['module_permissions'] = {
            'health': prefs.health_enabled,
            'journal': prefs.journal_enabled,
            'faith': prefs.faith_enabled,
            'life': prefs.life_enabled,
            'purpose': prefs.purpose_enabled,
            'finance': prefs.finances_enabled,
            'capture': prefs.capture_enabled,
            'ai': prefs.ai_enabled,
        }
    except Exception:
        pass

    # Blueprint state
    try:
        from apps.core.blueprint import engine as blueprint_engine
        blueprint = blueprint_engine.get_blueprint(user)
        explanation = blueprint_engine.explain_blueprint(user)
        context['blueprint_state'] = {
            'operating_style': getattr(blueprint, 'operating_style', 'balanced'),
            'pillars_ranked': explanation.get('pillars_ranked', []),
            'tier1_protected': explanation.get('tier1_protected', []),
        }
        context['protected_tiers'] = explanation.get('tier1_protected', [])
    except Exception:
        pass

    # Governance profile
    try:
        from apps.core.blueprint import engine as bp_engine
        bp = bp_engine.get_blueprint(user)
        context['governance_profile'] = {
            'accountability_style': getattr(bp, 'accountability_style', 'standard'),
            'question_frequency': getattr(bp, 'question_frequency', 'medium'),
            'sensitivity_tags': getattr(bp, 'sensitivity_tags', []) or [],
        }
    except Exception:
        pass

    # Persona
    try:
        from apps.core.ai_persona.persona_registry import get_persona_profile
        prefs = user.preferences
        persona_key = getattr(prefs, 'ai_coaching_style', 'supportive')
        profile = get_persona_profile(persona_key)
        context['persona_profile'] = {
            'key': persona_key,
            'name': profile.get('name', persona_key),
            'tone': profile.get('tone', 'calm'),
        }
    except Exception:
        pass

    # Schedule awareness (light — just today's load)
    try:
        from apps.core.blueprint import architecture_engine
        plan = architecture_engine.get_todays_plan(user)
        if plan:
            blocks = list(plan.blocks.all().order_by('start_time'))
            context['capacity_snapshot'] = {
                'total_blocks': len(blocks),
                'completed_blocks': sum(1 for b in blocks if b.is_completed),
            }
    except Exception:
        pass

    # Calendar events
    try:
        from apps.calendar_engine.models import CalendarEvent
        from apps.core.utils import get_user_now
        user_now = get_user_now(user)
        today_start = user_now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = user_now.replace(hour=23, minute=59, second=59, microsecond=0)
        events = CalendarEvent.objects.filter(
            user=user, start_dt__lte=today_end, end_dt__gte=today_start,
            status='scheduled',
        ).order_by('start_dt')[:8]
        context['calendar_events_today'] = [
            {'title': ev.title, 'start': ev.start_dt.astimezone(user_now.tzinfo).strftime('%I:%M %p').lstrip('0')}
            for ev in events
        ]
    except Exception:
        pass

    # Medication + fasting (actionable awareness)
    try:
        from apps.health.models import MedicineSchedule
        today = timezone.localdate()
        schedules = MedicineSchedule.objects.filter(user=user, is_active=True)
        total = schedules.count()
        if total > 0:
            taken = sum(
                1 for s in schedules
                if hasattr(s, 'logs') and s.logs.filter(taken_at__date=today).exists()
            )
            context['medication_adherence_state'] = {
                'total_scheduled': total, 'taken_today': taken,
            }
    except Exception:
        pass

    try:
        from apps.health.models import FastingSession
        active_fast = FastingSession.objects.filter(user=user, is_active=True).first()
        if active_fast:
            context['active_fast_status'] = {'active': True}
    except Exception:
        pass

    # Transformation metrics (so CoS can reference user's data)
    try:
        from apps.core.ai_state.state_engine import get_state_value
        context['transformation_metrics'] = {
            'weight_current': get_state_value(user, 'health.weight_current'),
            'weight_trend': get_state_value(user, 'health.weight_trend'),
            'active_goals': get_state_value(user, 'goals.active_goal_count', 0),
        }
    except Exception:
        pass

    # User declared priorities — from SAE truth layer
    try:
        from apps.core.ai_state.state_engine import get_state_value
        context['user_priorities'] = get_state_value(user, 'governance.declared_priorities', [])
    except Exception:
        pass

    return context


# =========================================================================
# WRITE-SUPPRESSED SYSTEM PROMPT CONTRACT
# =========================================================================
# This is the hard behavioral contract injected into the system prompt
# when writes are suppressed. It replaces the post-generation compliance
# gate with generation-time enforcement.

COS_WRITE_SUPPRESSED_CONTRACT = """
--- WRITE-SUPPRESSED CONTRACT ---

ALL write operations are suppressed. This contract is absolute.

FORBIDDEN OUTPUT — never produce any of the following:
- Write verbs in any tense: log, logged, logging, save, saved, saving,
  record, recorded, recording, mark, marked, marking, flag, flagged,
  flagging, update, updated, updating, schedule, scheduled, scheduling,
  set, confirm, noted, note, captured, tracked, persist, calendar.
- Shadow-write language: "intent captured", "queued", "will apply",
  "taking note", "adding to", "putting on", "entering", "filing".
- Future-promise phrasing: when, once, after, until, resumes, available,
  ends, later, "when ready", "after exit", "execution resumes".
- Internal system references: "Learning Mode", "current configuration",
  "write suppression", "execution mode", "the system".
- Apologies or explanations about why writes are unavailable.

WHEN THE USER DEMANDS A WRITE (log/save/record/mark/flag/update/schedule/set/confirm):
Respond with EXACTLY two lines:
Line 1: "Writes are suppressed."
Line 2: A single directive sentence. No time-anchored phrasing (no when/after/once).
Acceptable directives:
  - "Repeat this request in a new session."
  - "Handle this manually; it cannot be applied here."

WHEN THE USER DOES NOT DEMAND A WRITE:
Respond normally. Apply Phase 2/3 cognitive structure.
Do NOT mention suppression, modes, or system state.
Use behavioral directives, identity framing, trajectory precision.
Weekly reviews, accountability, strategic analysis — all function normally.
The only thing suppressed is persistence operations.

--- END WRITE-SUPPRESSED CONTRACT ---
"""


def format_learning_mode_injection(context):
    """
    Format the reduced Learning Mode context as a system prompt injection.

    Uses the WRITE_SUPPRESSED template: hard behavioral contract enforced
    at generation time. No post-processing gate needed.

    Args:
        context: dict from build_learning_mode_context()

    Returns:
        str — formatted system injection block.
    """
    lines = []
    lines.append("=== OPERATIONAL AWARENESS ===")
    lines.append("")

    # What the user has enabled
    mods = context.get('module_permissions', {})
    enabled = [k for k, v in mods.items() if v]
    disabled = [k for k, v in mods.items() if not v]
    if enabled:
        lines.append(f"Enabled Modules: {', '.join(enabled)}")
    if disabled:
        lines.append(f"Disabled Modules (do not reference): {', '.join(disabled)}")

    # Non-negotiables
    protected = context.get('protected_tiers', [])
    if protected:
        lines.append(f"Non-Negotiable Commitments: {', '.join(protected)}")

    bp = context.get('blueprint_state', {})
    pillars = bp.get('pillars_ranked', [])
    if pillars:
        lines.append(f"Life Priorities (ranked): {', '.join(pillars)}")

    # Declared priorities (from UserPriorityProfile)
    priorities = context.get('user_priorities', [])
    if priorities:
        lines.append("")
        lines.append("Declared Priorities:")
        for p in priorities:
            sub = f".{p['sub_module']}" if p['sub_module'] else ""
            reason = f" — {p['reason']}" if p['reason'] else ""
            lines.append(f"  {p['module']}{sub}: {p['level']} (w={p['weight']}){reason}")

    # Medication (still important to know during learning, with names)
    med = context.get('medication_adherence_state', {})
    pending_meds = context.get('pending_medications', [])
    if pending_meds:
        overdue = [m for m in pending_meds if m['status'] == 'overdue']
        upcoming = [m for m in pending_meds if m['status'] == 'upcoming']
        taken_meds = [m for m in pending_meds if m['status'] == 'taken']
        parts = []
        if taken_meds:
            parts.append(f"Taken: {', '.join(m['name'] for m in taken_meds)}")
        if overdue:
            parts.append(f"OVERDUE: {', '.join(m['name'] for m in overdue)}")
        if upcoming:
            parts.append(f"Upcoming: {', '.join(m['name'] for m in upcoming)}")
        lines.append(f"Medication: {' | '.join(parts)}")
    elif med.get('total_scheduled', 0) > 0:
        lines.append(
            f"Medication: {med.get('taken_today', 0)}/{med.get('total_scheduled', 0)} taken today"
        )

    # Active fast
    if context.get('active_fast_status', {}).get('active'):
        lines.append("Active Fast: In progress")

    # Calendar
    cal = context.get('calendar_events_today', [])
    if cal:
        lines.append("")
        lines.append("Today's Calendar:")
        for ev in cal[:6]:
            lines.append(f"  {ev['start']} {ev['title']}")

    # Hard write-suppressed contract
    lines.append("")
    lines.append(COS_WRITE_SUPPRESSED_CONTRACT.strip())

    lines.append("")
    lines.append("=== END OPERATIONAL AWARENESS ===")

    return '\n'.join(lines)
