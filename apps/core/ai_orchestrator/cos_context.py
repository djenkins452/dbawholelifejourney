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

from django.db import close_old_connections
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

    # Override frequency (14d)
    try:
        from apps.core.blueprint.models import InterventionLog
        fourteen_days_ago = timezone.now() - datetime.timedelta(days=14)
        overrides = InterventionLog.objects.filter(
            user=user,
            user_response='proceeded',
            created_at__gte=fourteen_days_ago,
        ).count()
        result['override_frequency_14d'] = overrides
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

    # Medication adherence
    try:
        from apps.health.models import MedicineSchedule
        today = timezone.localdate()
        schedules = MedicineSchedule.objects.filter(
            user=user, is_active=True,
        )
        taken = 0
        total = 0
        for sched in schedules:
            total += 1
            if hasattr(sched, 'logs'):
                if sched.logs.filter(taken_at__date=today).exists():
                    taken += 1
        if total > 0:
            result['medication_adherence_state'] = {
                'total_scheduled': total,
                'taken_today': taken,
                'adherence_pct': round(taken / total * 100),
            }
    except Exception:
        pass

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

        # Weight — direct DB query (state cache can be stale)
        try:
            from apps.health.models import WeightEntry, HealthProfile
            latest_weight = (
                WeightEntry.objects.filter(user=user)
                .order_by('-recorded_at')
                .first()
            )
            if latest_weight:
                health_signals['weight_current'] = round(float(latest_weight.value), 1)
                health_signals['weight_unit'] = latest_weight.unit or 'lb'
                health_signals['weight_date'] = str(latest_weight.recorded_at.date())
                # Trend: compare to 30 days ago
                cutoff_30d = timezone.now() - timedelta(days=30)
                older_weight = (
                    WeightEntry.objects.filter(user=user, recorded_at__lte=cutoff_30d)
                    .order_by('-recorded_at')
                    .values_list('value', flat=True)
                    .first()
                )
                if older_weight is not None:
                    diff = float(latest_weight.value) - float(older_weight)
                    if abs(diff) < 0.5:
                        health_signals['weight_trend'] = 'stable'
                    elif diff > 0:
                        health_signals['weight_trend'] = 'increasing'
                    else:
                        health_signals['weight_trend'] = 'decreasing'

            # Weight goal from HealthProfile
            hp = HealthProfile.objects.filter(user=user).first()
            if hp and hp.has_weight_goal:
                health_signals['weight_goal'] = float(hp.weight_goal)
                health_signals['weight_goal_unit'] = hp.weight_goal_unit
                if hp.weight_goal_target_date:
                    health_signals['weight_goal_target_date'] = str(hp.weight_goal_target_date)
                progress = hp.get_weight_progress()
                if progress and progress.get('remaining') is not None:
                    health_signals['weight_goal_remaining'] = progress['remaining']
                    health_signals['weight_goal_on_track'] = progress.get('on_track')
        except Exception:
            pass

        try:
            from django.db.models import Avg, Sum
            from apps.health.models import (
                HeartRateEntry, BloodPressureEntry, GlucoseEntry,
                BloodOxygenEntry, StepsEntry, SleepEntry,
            )

            hr_avg = HeartRateEntry.objects.filter(
                user=user, recorded_at__date__gte=week_ago
            ).aggregate(avg=Avg('bpm'))['avg']
            if hr_avg:
                health_signals['heart_rate_avg_7d'] = round(float(hr_avg))

            latest_bp = BloodPressureEntry.objects.filter(
                user=user, recorded_at__date__gte=week_ago
            ).order_by('-recorded_at').first()
            if latest_bp:
                health_signals['bp_latest'] = f"{latest_bp.systolic}/{latest_bp.diastolic}"

            glucose_avg = GlucoseEntry.objects.filter(
                user=user, recorded_at__date__gte=week_ago
            ).aggregate(avg=Avg('value'))['avg']
            if glucose_avg:
                health_signals['glucose_avg_7d'] = round(float(glucose_avg))

            spo2_avg = BloodOxygenEntry.objects.filter(
                user=user, recorded_at__date__gte=week_ago
            ).aggregate(avg=Avg('spo2'))['avg']
            if spo2_avg:
                health_signals['blood_oxygen_avg_7d'] = round(float(spo2_avg), 1)

            if not health_signals.get('steps_avg_7d'):
                steps_avg = StepsEntry.objects.filter(
                    user=user, logged_date__gte=week_ago
                ).aggregate(avg=Avg('count'))['avg']
                if steps_avg:
                    health_signals['steps_avg_7d'] = int(steps_avg)

            if not health_signals.get('sleep_avg_7d'):
                sleep_avg = SleepEntry.objects.filter(
                    user=user, sleep_date__gte=week_ago
                ).aggregate(avg=Avg('asleep_duration_minutes'))['avg']
                if sleep_avg:
                    health_signals['sleep_avg_7d'] = round(float(sleep_avg) / 60, 1)

            from apps.health.models import WorkoutSession
            workout_qs = WorkoutSession.objects.filter(
                user=user, date__gte=week_ago
            )
            workout_count = workout_qs.count()
            if workout_count > 0:
                health_signals['workout_count_7d'] = workout_count
                workout_agg = workout_qs.aggregate(
                    total_cal=Sum('calories_burned'),
                    total_min=Sum('duration_minutes'),
                    avg_hr=Avg('avg_heart_rate'),
                    total_dist=Sum('distance_miles'),
                )
                if workout_agg['total_cal']:
                    health_signals['workout_calories_7d'] = workout_agg['total_cal']
                if workout_agg['total_min']:
                    health_signals['workout_minutes_7d'] = workout_agg['total_min']
                if workout_agg['avg_hr']:
                    health_signals['workout_avg_hr_7d'] = round(float(workout_agg['avg_hr']))
                if workout_agg['total_dist']:
                    health_signals['workout_distance_7d'] = round(float(workout_agg['total_dist']), 1)
                recent_workouts = workout_qs.order_by('-date')[:3]
                health_signals['recent_workouts'] = [
                    {
                        'name': w.name,
                        'type': w.workout_type,
                        'date': str(w.date),
                        'minutes': w.duration_minutes,
                        'calories': w.calories_burned,
                        'avg_hr': w.avg_heart_rate,
                    }
                    for w in recent_workouts
                ]

            from apps.health.models import HeartRateEventEntry
            hr_events = HeartRateEventEntry.objects.filter(
                user=user, recorded_at__date__gte=week_ago
            ).count()
            if hr_events > 0:
                health_signals['heart_rate_events_7d'] = hr_events

        except Exception:
            pass  # Direct queries are supplementary

        result['health_signals'] = health_signals
    except Exception:
        result['health_signals'] = {}

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
            status='scheduled',
        ).order_by('start_dt')[:12]

        event_summaries = []
        for ev in events:
            if ev.end_dt <= user_now:
                time_status = 'past'
            elif ev.start_dt <= user_now <= ev.end_dt:
                time_status = 'in_progress'
            elif ev.start_dt <= user_now + datetime.timedelta(hours=1):
                time_status = 'upcoming_soon'
            else:
                time_status = 'upcoming'

            is_overdue = ev.start_dt < user_now and time_status == 'past'

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
            })
        result['calendar_events_today'] = event_summaries
    except Exception as e:
        logger.debug("CoS context: calendar events unavailable: %s", e)

    return result


def _build_intelligence_signals(user):
    """Build insights, predictions, guidance, and correlations."""
    result = {}

    # Active PIE insights
    try:
        from apps.core.ai_insights.models import Insight
        recent_insights = Insight.objects.filter(
            user=user, status__in=["new", "read"],
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
    except Exception:
        result['active_insights'] = []

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
    except Exception:
        result['active_predictions'] = []

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
    except Exception:
        result['active_guidance'] = []

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
    except Exception:
        result['cross_domain_correlations'] = []

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

    # Open loops
    try:
        from apps.purpose.models import LifeGoal
        overdue_goals = LifeGoal.objects.filter(
            user=user, status="active",
            target_date__lt=timezone.localdate(),
        ).count()
        result['open_loops'] = {
            'overdue_goals': overdue_goals,
        }
        from apps.core.blueprint.models import InterventionLog
        pending_gates = InterventionLog.objects.filter(
            user=user, level=4, user_response='pending',
        ).count()
        result['open_loops']['pending_friction_gates'] = pending_gates
    except Exception:
        result['open_loops'] = {}

    # Approaching life events (next 14 days)
    try:
        from apps.life.models import SignificantEvent, LifeEvent
        from apps.core.utils import get_user_today
        today = get_user_today(user)
        approaching_events = []

        for event in SignificantEvent.objects.filter(user=user):
            try:
                days_until = event.days_until_next(today)
                if days_until is not None and days_until <= 14:
                    event_info = {
                        'title': event.title,
                        'type': event.event_type,
                        'days_until': days_until,
                        'person': event.person_name or '',
                    }
                    if event.original_year:
                        years = today.year - event.original_year
                        if days_until > 0:
                            years = years
                        event_info['years'] = years
                    approaching_events.append(event_info)
            except Exception:
                continue

        from datetime import timedelta
        cutoff = today + timedelta(days=14)
        for event in LifeEvent.objects.filter(
            user=user, start_date__gte=today, start_date__lte=cutoff
        ).exclude(status='deleted').order_by('start_date')[:10]:
            days_until = (event.start_date - today).days
            approaching_events.append({
                'title': event.title,
                'type': event.event_type if hasattr(event, 'event_type') else 'event',
                'days_until': days_until,
                'person': '',
            })

        approaching_events.sort(key=lambda e: e['days_until'])
        result['approaching_life_events'] = approaching_events[:5]
    except Exception as e:
        logger.debug("CoS context: life events unavailable: %s", e)
        result['approaching_life_events'] = []

    # Feedback loop profiles
    try:
        from apps.core.ai_feedback.models import (
            BriefingEngagementProfile,
            InsightEngagementProfile,
            InterventionEffectivenessProfile,
        )
        ie_profile = InsightEngagementProfile.objects.filter(user=user).first()
        be_profile = BriefingEngagementProfile.objects.filter(user=user).first()
        iv_profile = InterventionEffectivenessProfile.objects.filter(user=user).first()
        result['feedback_profiles'] = {
            'insight_engagement': ie_profile.engagement_score if ie_profile else 0.5,
            'briefing_open_rate': be_profile.open_rate if be_profile else 0.0,
            'preferred_briefing_length': be_profile.preferred_length if be_profile else 'standard',
            'intervention_effectiveness': iv_profile.effectiveness_score if iv_profile else 0.5,
            'escalation_modifier': iv_profile.escalation_speed_modifier if iv_profile else 0.0,
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
    """Build recent image analysis context for CoS injection."""
    import datetime

    from django.utils import timezone

    try:
        from apps.scan.models import ImageAnalysis

        lookback = timezone.now() - datetime.timedelta(days=7)
        analyses = ImageAnalysis.objects.filter(
            user=user,
            status='completed',
            created_at__gte=lookback,
        ).order_by('-created_at')[:10]

        if not analyses:
            return {}

        return {
            'recent_image_analyses': [
                {
                    'summary': a.summary,
                    'category': a.category,
                    'source': a.get_source_type_display(),
                    'when': a.created_at.isoformat(),
                    'tags': a.relevance_tags[:5] if a.relevance_tags else [],
                }
                for a in analyses
            ]
        }
    except Exception as e:
        logger.debug("CoS context: image analyses unavailable: %s", e)
        return {}


def _build_meals_context(user):
    """Build meal intelligence context for CoS awareness."""
    try:
        from apps.meals.models import HouseholdMembership, MealPlanEntry, PantryItem
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

        # Pantry summary
        pantry_count = PantryItem.objects.filter(household=household, quantity__gt=0).count()
        expiring = PantryItem.objects.filter(
            household=household, quantity__gt=0,
            expiration_date_estimated__lte=today + tz.timedelta(days=3),
            expiration_date_estimated__gte=today,
        ).values_list("ingredient__canonical_name", flat=True)[:5]

        # Today's plan
        dinner_entry = MealPlanEntry.objects.filter(
            meal_plan__household=household, date=today, meal_type="dinner",
        ).select_related("recipe").first()

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
                'dinner_planned': dinner_entry.recipe.title if dinner_entry else None,
                'household_name': household.name,
                **pantry_scan_data,
            }
        }
    except Exception as e:
        logger.debug("CoS context: meals unavailable: %s", e)
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
]


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

    context = {
        '_user': user,
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

    # Run all builders in parallel
    try:
        def _run_builder(builder_fn):
            """Execute a builder in a thread with proper DB connection handling."""
            close_old_connections()
            try:
                return builder_fn(user, prefs)
            finally:
                close_old_connections()

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

    return context


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
        if ev.get('time_status') == 'past' and not ev.get('is_overdue'):
            completed_items.append(ev['title'])

    # Medication taken
    med = context.get('medication_adherence_state', {})
    taken = med.get('taken_today', 0)
    total_sched = med.get('total_scheduled', 0)
    if taken > 0:
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

    # Missed medication doses
    if total_sched > 0 and taken < total_sched:
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

    lines = []
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
        "HONESTY RULE: ONLY state facts that appear in the data below. "
        "If a data point is missing from this context, say 'I don't have that "
        "data right now' — NEVER guess, estimate, or echo back a number the user "
        "mentioned as if you looked it up. Wrong data destroys trust. "
        "Saying 'I don't have that' is ALWAYS better than making something up."
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

    # ── DAILY SCAN BRIEF (structured summary for proactive intelligence) ──
    scan_brief = _build_daily_scan_brief(context)
    if scan_brief:
        lines.append(scan_brief)
        lines.append("")

    # ── COACHING MODE (adaptive mode for this interaction) ──
    _cos_user = context.get('_user')
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

    # What matters to this person (compact)
    bp = context.get('blueprint_state', {})
    protected = context.get('protected_tiers', [])
    if protected:
        lines.append(f"Non-Negotiable Commitments: {', '.join(protected)}")
    pillars = bp.get('pillars_ranked', []) if bp else []
    if pillars:
        lines.append(f"Life Priorities (ranked): {', '.join(pillars)}")

    # Medication (actionable — user needs to know)
    med = context.get('medication_adherence_state', {})
    if med and med.get('total_scheduled', 0) > 0:
        lines.append(f"Medication: {med.get('taken_today', 0)}/{med.get('total_scheduled', 0)} "
                     f"taken today")

    # Active fast (actionable)
    fast = context.get('active_fast_status', {})
    if fast.get('active'):
        lines.append(f"Active Fast: In progress (target: {fast.get('target_hours', 0)}h)")

    # Today's schedule blocks
    blocks = context.get('today_blocks_summary', [])
    if blocks:
        lines.append("")
        lines.append("Today's Schedule:")
        for b in blocks[:8]:
            status = "[done]" if b['completed'] else "[locked]" if b['locked'] else ""
            lines.append(f"  {b['start']}-{b['end']} {b['title']} {status}")

    # Calendar events (what's happening today)
    cal_events = context.get('calendar_events_today', [])
    if cal_events:
        lines.append("")
        lines.append("Today's Calendar:")
        for ev in cal_events:
            status_tag = ""
            if ev['time_status'] == 'in_progress':
                status_tag = " [NOW]"
            elif ev['time_status'] == 'upcoming_soon':
                status_tag = " [SOON]"
            elif ev['is_overdue']:
                status_tag = " [MISSED]"
            elif ev['time_status'] == 'past':
                status_tag = " [done]"
            ev_protected = " (protected)" if ev.get('is_protected') else ""
            lines.append(
                f"  {ev['start']}-{ev['end']} {ev['title']}"
                f"{ev_protected}{status_tag}"
            )

    # Key signals — only include things the CoS should mention or act on
    # (Skip raw scores/percentages that don't help the conversation)

    # Active insights — coaching-level narratives from PIE
    insights = context.get('active_insights', [])
    if insights:
        lines.append("")
        lines.append("ACTIVE PATTERNS (weave into responses when the user asks about progress or habits):")
        for i in insights[:5]:
            severity_prefix = ""
            if i.get('severity') == 'critical':
                severity_prefix = "[IMPORTANT] "
            elif i.get('severity') == 'warning':
                severity_prefix = "[Watch] "
            elif i.get('severity') == 'positive':
                severity_prefix = "[Positive] "
            msg = i.get('message') or i.get('title', '')
            why = i.get('explain_why', '')
            if msg and why:
                lines.append(f"  - {severity_prefix}{msg} ({why})")
            elif msg:
                lines.append(f"  - {severity_prefix}{msg}")

    # Active predictions — trajectory outlook from PRIE
    predictions = context.get('active_predictions', [])
    if predictions:
        lines.append("")
        lines.append("TRAJECTORY OUTLOOK (mention proactively when user asks about progress or goals):")
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
    guidance = context.get('active_guidance', [])
    if guidance:
        lines.append("")
        lines.append("RECOMMENDED ACTIONS (suggest when the user asks what to do or needs direction):")
        for g in guidance[:3]:
            msg = g.get('message') or g.get('title', '')
            if msg:
                lines.append(f"  - {msg}")

    # Cross-domain correlations — discovered patterns from CDCE
    correlations = context.get('cross_domain_correlations', [])
    if correlations:
        lines.append("")
        lines.append(
            "CROSS-DOMAIN PATTERNS (reference when domains overlap in conversation):"
        )
        for c in correlations[:4]:
            strength_tag = ""
            if c.get('strength') == 'strong':
                strength_tag = "[Strong] "
            elif c.get('strength') == 'moderate':
                strength_tag = "[Moderate] "
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

    # Phase 1: Declared user priorities (from UserPriorityProfile)
    try:
        from apps.core.blueprint.models import UserPriorityProfile
        priorities = UserPriorityProfile.objects.filter(
            user=context.get('_user'),
        ) if context.get('_user') else None
        if priorities and priorities.exists():
            lines.append("")
            lines.append("Declared Priorities:")
            for p in priorities[:10]:
                sub = f".{p.sub_module_key}" if p.sub_module_key else ""
                level = p.get_declared_priority_level_display()
                reason = f" — {p.declared_reason[:100]}" if p.declared_reason else ""
                lines.append(f"  {p.module_key}{sub}: {level}{reason}")
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

    # Navigable pages — URL awareness for directing users to app pages
    pages = context.get('navigable_pages', [])
    if pages:
        lines.append("")
        lines.append(
            "APP NAVIGATION (use these URLs when directing the user to a page):"
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

    lines.append("")
    lines.append("=== END SITUATIONAL AWARENESS ===")
    lines.append("")

    return '\n'.join(lines)


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
    Build trajectory-relevant signals from existing data sources.

    Source-Integrity Gate applied to every signal source:
    - Each source verified importable and returns non-trivial volume
    - Insufficient sources produce compact placeholder, not fabricated data
    - Read-only — no writes, no side effects

    Uses ONLY existing models — no new data structures:
    - InterventionLog: renegotiation patterns, override frequency
    - ScenarioHistory: drift frequency
    - State engine: progress trend

    Returns:
        dict — trajectory signals for prompt injection.
    """
    signals = {
        'renegotiation_patterns': [],
        'tier1_skip_patterns': [],
        'consecutive_tier1_skips': 0,
        'override_count_10d': 0,
        'drift_scenario_count_14d': 0,
        'progress_trend_negative': False,
        'insufficient': [],  # Compact placeholders for unavailable signals
    }

    ten_days_ago = timezone.now() - datetime.timedelta(days=10)
    seven_days_ago = timezone.now() - datetime.timedelta(days=7)
    fourteen_days_ago = timezone.now() - datetime.timedelta(days=14)

    # --- Renegotiation patterns (Layer 1) ---
    # Gate: require ≥1 record to compute, ≥3 per behavior to trigger pattern
    def _renegotiation_source():
        from apps.core.blueprint.models import InterventionLog
        from django.db.models import Count

        qs = InterventionLog.objects.filter(
            user=user,
            created_at__gte=ten_days_ago,
            user_response__in=['proceeded', 'dismissed'],
            behavior_key__gt='',
        )
        total = qs.count()
        patterns = list(
            qs.values('behavior_key')
            .annotate(count=Count('id'))
            .filter(count__gte=3)
            .order_by('-count')[:5]
        )
        return patterns, total

    result = _source_integrity_gate('renegotiation', _renegotiation_source, min_records=1)
    if result is not None:
        patterns, _ = result
        for r in patterns:
            signals['renegotiation_patterns'].append({
                'behavior': r['behavior_key'],
                'count': r['count'],
                'window_days': 10,
            })
        # Override count (total proceeded in 10 days)
        try:
            from apps.core.blueprint.models import InterventionLog
            signals['override_count_10d'] = InterventionLog.objects.filter(
                user=user,
                created_at__gte=ten_days_ago,
                user_response='proceeded',
            ).count()
        except Exception:
            pass
    else:
        signals['insufficient'].append('renegotiation')

    # --- Tier 1 skip patterns (Layer 2) ---
    # Gate: require ≥1 record to compute, ≥2 per behavior to trigger alert
    def _tier1_skip_source():
        from apps.core.blueprint.models import InterventionLog

        qs = InterventionLog.objects.filter(
            user=user,
            created_at__gte=seven_days_ago,
            trigger_type__in=['tier1_violation', 'non_negotiable_miss'],
        ).order_by('-created_at')
        records = list(qs.values('behavior_key', 'created_at'))
        return records, len(records)

    result = _source_integrity_gate('tier1_skips', _tier1_skip_source, min_records=1)
    if result is not None:
        records, _ = result
        tier1_by_behavior = {}
        tier1_dates = []
        for rec in records:
            key = rec['behavior_key'] or 'general'
            tier1_by_behavior.setdefault(key, 0)
            tier1_by_behavior[key] += 1
            tier1_dates.append(rec['created_at'].date())

        for bkey, count in tier1_by_behavior.items():
            if count >= 2:
                signals['tier1_skip_patterns'].append({
                    'behavior': bkey,
                    'count': count,
                    'window_days': 7,
                })

        # Consecutive Tier 1 skips
        if tier1_dates:
            unique_dates = sorted(set(tier1_dates), reverse=True)
            consecutive = 1
            for i in range(1, len(unique_dates)):
                if (unique_dates[i - 1] - unique_dates[i]).days <= 1:
                    consecutive += 1
                else:
                    break
            signals['consecutive_tier1_skips'] = consecutive
    else:
        signals['insufficient'].append('tier1_skips')

    # --- Drift scenario frequency (supports Layer 2 + 3) ---
    # Gate: require ≥5 events in 14 days for frequency-based inference
    def _drift_frequency_source():
        from apps.core.ai_arbitration.models import ScenarioHistory
        from datetime import date

        total_events = ScenarioHistory.objects.filter(
            user=user,
            date__gte=date.today() - datetime.timedelta(days=14),
        ).count()
        drift_count = ScenarioHistory.objects.filter(
            user=user,
            date__gte=date.today() - datetime.timedelta(days=14),
            dominant_scenario='DRIFT_CRITICAL',
        ).count()
        return drift_count, total_events

    result = _source_integrity_gate('drift_frequency', _drift_frequency_source, min_records=5)
    if result is not None:
        drift_count, _ = result
        signals['drift_scenario_count_14d'] = drift_count
    else:
        signals['insufficient'].append('drift_frequency')

    # --- Progress trend (supports Layer 2 corrective minimum detection) ---
    def _progress_trend_source():
        from apps.core.ai_state.state_engine import get_state_value
        weight_trend = get_state_value(user, 'health.weight_trend', 'stable')
        alignment_trend = get_state_value(user, 'alignment.trend', 'stable')
        is_negative = (
            weight_trend in ('increasing',)
            or alignment_trend in ('declining', 'decreasing')
        )
        return is_negative, 1  # Always 1 record (state engine always available)

    result = _source_integrity_gate('progress_trend', _progress_trend_source, min_records=1)
    if result is not None:
        is_negative, _ = result
        signals['progress_trend_negative'] = is_negative
    else:
        signals['insufficient'].append('progress_trend')

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

    # Deferral count: distinct days with renegotiations in last 7 days
    try:
        from apps.core.blueprint.models import InterventionLog
        seven_days_ago = timezone.now() - datetime.timedelta(days=7)
        signals['deferrals_7d'] = InterventionLog.objects.filter(
            user=user,
            created_at__gte=seven_days_ago,
            user_response__in=['proceeded', 'dismissed'],
        ).count()
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

    # User declared priorities (from UserPriorityProfile)
    try:
        from apps.core.blueprint.models import UserPriorityProfile
        priorities = UserPriorityProfile.objects.filter(user=user)
        context['user_priorities'] = [
            {
                'module': p.module_key,
                'sub_module': p.sub_module_key,
                'level': p.get_declared_priority_level_display(),
                'weight': float(p.importance_weight),
                'reason': p.declared_reason[:200] if p.declared_reason else '',
            }
            for p in priorities
        ]
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

    # Medication (still important to know during learning)
    med = context.get('medication_adherence_state', {})
    if med.get('total_scheduled', 0) > 0:
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
