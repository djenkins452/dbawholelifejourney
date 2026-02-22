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

from django.utils import timezone

logger = logging.getLogger(__name__)


def build_cos_context(user):
    """
    Assemble the full Chief of Staff operational context.

    Queries all relevant engines and assembles a structured dict
    that represents the user's current operational state.

    Args:
        user: Django User instance.

    Returns:
        dict — Comprehensive CoS context.
    """
    context = {
        '_user': user,  # Internal ref for priority injection in format_cos_system_injection
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
    }

    prefs = user.preferences

    # Module permissions
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

    # Blueprint state
    try:
        from apps.core.blueprint import engine as blueprint_engine
        blueprint = blueprint_engine.get_blueprint(user)
        explanation = blueprint_engine.explain_blueprint(user)
        context['blueprint_state'] = {
            'operating_style': getattr(blueprint, 'operating_style', 'balanced'),
            'interruption_tolerance': getattr(blueprint, 'interruption_tolerance', 'medium'),
            'auto_architect_enabled': getattr(blueprint, 'auto_architect_enabled', True),
            'pillars_ranked': explanation.get('pillars_ranked', []),
            'tier1_protected': explanation.get('tier1_protected', []),
            'override_policy': getattr(blueprint, 'override_policy', 'confirm'),
            'version': getattr(blueprint, 'version', 1),
        }
        context['protected_tiers'] = explanation.get('tier1_protected', [])
    except Exception as e:
        logger.debug("CoS context: blueprint unavailable: %s", e)

    # Today's plan + capacity
    try:
        from apps.core.blueprint import architecture_engine
        from apps.core.blueprint.models import ArchitecturePlan
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
            context['capacity_snapshot'] = {
                'total_blocks': len(blocks),
                'completed_blocks': completed,
                'capacity_pct': min(100, round(total_minutes / waking_minutes * 100)),
                'tier_distribution': tier_counts,
                'scheduled_minutes': round(total_minutes),
            }
            context['today_blocks_summary'] = block_summaries
            context['risk_warnings'] = plan.risk_warnings or []
    except Exception as e:
        logger.debug("CoS context: plan unavailable: %s", e)

    # Alignment score (weighted by tier)
    try:
        from apps.core.blueprint.alignment_engine import compute_alignment_score
        alignment = compute_alignment_score(user)
        context['alignment_score'] = round(alignment.score)
        context['alignment_grade'] = alignment.grade
    except Exception as e:
        logger.debug("CoS context: alignment engine unavailable: %s", e)

    # Drift + prediction
    try:
        from apps.core.blueprint import drift_engine
        summary = drift_engine.get_drift_summary(user, days=7)
        score = summary.get('average_score', 0)
        context['drift_score'] = round(score)
        # Only override alignment if alignment engine didn't run
        if context.get('alignment_score', 100) == 100 and score > 0:
            context['alignment_score'] = round(100 - score)
        prediction = summary.get('latest_prediction', {})
        context['drift_probability'] = {
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
            context['forecast_load_24h'] = min(100, round(tmr_minutes / (16 * 60) * 100))
    except Exception:
        pass

    # Weekly pressure forecast
    try:
        from apps.core.blueprint.weekly_pressure import compute_weekly_pressure
        from apps.core.blueprint.human_language import translate_weekly_pressure
        pressure_data = compute_weekly_pressure(user)
        context['weekly_pressure'] = {
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

    # Override frequency (14d)
    try:
        from apps.core.blueprint.models import InterventionLog
        fourteen_days_ago = timezone.now() - datetime.timedelta(days=14)
        overrides = InterventionLog.objects.filter(
            user=user,
            user_response='proceeded',
            created_at__gte=fourteen_days_ago,
        ).count()
        context['override_frequency_14d'] = overrides
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
            'relationship_suggestions': getattr(bp, 'relationship_suggestions_enabled', False),
            'event_reflections': getattr(bp, 'event_reflections_enabled', True),
            'calibration_complete': getattr(bp, 'calibration_complete', False),
            'calibration_day': getattr(bp, 'calibration_day', 0),
        }
    except Exception:
        context['governance_profile'] = {}

    # Persona profile
    try:
        from apps.core.ai_persona.persona_registry import get_persona_profile
        persona_key = getattr(prefs, 'ai_coaching_style', 'supportive')
        profile = get_persona_profile(persona_key)
        context['persona_profile'] = {
            'key': persona_key,
            'name': profile.get('name', persona_key),
            'tone': profile.get('tone', 'calm'),
        }
    except Exception:
        context['persona_profile'] = {'key': 'supportive', 'name': 'Supportive', 'tone': 'calm'}

    # Transformation metrics (from SAE)
    try:
        from apps.core.ai_state.state_engine import get_state_value
        context['transformation_metrics'] = {
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
            user=user,
            is_active=True,
        ).first()
        if active_fast:
            context['active_fast_status'] = {
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
            context['medication_adherence_state'] = {
                'total_scheduled': total,
                'taken_today': taken,
                'adherence_pct': round(taken / total * 100),
            }
    except Exception:
        pass

    # Calendar events today — gives CoS full schedule awareness
    try:
        from apps.calendar_engine.models import CalendarEvent
        from apps.core.utils import get_user_now, get_user_today

        user_now = get_user_now(user)
        today = get_user_today(user)
        today_start = user_now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = user_now.replace(hour=23, minute=59, second=59, microsecond=0)

        events = CalendarEvent.objects.filter(
            user=user,
            start_dt__lte=today_end,
            end_dt__gte=today_start,
            status='scheduled',
        ).order_by('start_dt')[:12]  # Cap at 12 to limit tokens

        event_summaries = []
        for ev in events:
            # Compute time-relative status
            if ev.end_dt <= user_now:
                time_status = 'past'
            elif ev.start_dt <= user_now <= ev.end_dt:
                time_status = 'in_progress'
            elif ev.start_dt <= user_now + datetime.timedelta(hours=1):
                time_status = 'upcoming_soon'
            else:
                time_status = 'upcoming'

            # Check if overdue (start time passed but not completed)
            is_overdue = ev.start_dt < user_now and time_status == 'past'

            event_summaries.append({
                'title': ev.title,
                'start': ev.start_dt.strftime('%I:%M %p').lstrip('0'),
                'end': ev.end_dt.strftime('%I:%M %p').lstrip('0'),
                'domain': ev.domain.name if ev.domain else '',
                'is_protected': ev.is_protected,
                'time_status': time_status,
                'is_overdue': is_overdue,
            })
        context['calendar_events_today'] = event_summaries
    except Exception as e:
        logger.debug("CoS context: calendar events unavailable: %s", e)

    # =====================================================================
    # PHASE 4 — EXECUTIVE CONTEXT SIGNALS
    # =====================================================================

    # Active PIE insights summary
    try:
        from apps.core.ai_insights.models import Insight
        recent_insights = Insight.objects.filter(
            user=user, status__in=["new", "read"],
        ).order_by("-created_at")[:5]
        context['active_insights'] = [
            {
                'type': i.insight_type,
                'severity': i.severity,
                'title': i.title,
                'module': i.module,
            }
            for i in recent_insights
        ]
    except Exception:
        context['active_insights'] = []

    # Active PRIE predictions summary
    try:
        from apps.core.ai_predictions.models import Prediction
        active_predictions = Prediction.objects.filter(
            user=user, status="active",
        ).order_by("-confidence_score")[:5]
        context['active_predictions'] = [
            {
                'type': p.prediction_type,
                'module': p.module,
                'value': p.predicted_value,
                'confidence': round(p.confidence_score, 2),
            }
            for p in active_predictions
        ]
    except Exception:
        context['active_predictions'] = []

    # Relationship signals
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
        context['relationship_signals'] = rel_signals
    except Exception:
        context['relationship_signals'] = []

    # Journal mood trends
    try:
        from apps.core.ai_state.state_engine import get_state_value
        context['mood_status'] = {
            'trend': get_state_value(user, 'journal.mood_trend', 'stable'),
            'avg_7d': get_state_value(user, 'journal.mood_avg_7d'),
            'entries_7d': get_state_value(user, 'journal.entries_7d', 0),
        }
    except Exception:
        context['mood_status'] = {}

    # Health signals — pull from state engine AND direct model queries for comprehensive data
    try:
        from apps.core.ai_state.state_engine import get_state_value
        health_signals = {
            'sleep_avg_7d': get_state_value(user, 'health.sleep_avg_hours_7d'),
            'sleep_trend': get_state_value(user, 'health.sleep_trend', 'stable'),
            'workout_count_7d': get_state_value(user, 'fitness.workouts_7d', 0),
            'steps_avg_7d': get_state_value(user, 'health.steps_avg_7d'),
        }

        # Supplement with direct model queries for data the state engine may not track yet
        from datetime import timedelta
        week_ago = timezone.localdate() - timedelta(days=7)

        try:
            from django.db.models import Avg, Sum
            from apps.health.models import (
                HeartRateEntry, BloodPressureEntry, GlucoseEntry,
                BloodOxygenEntry, StepsEntry, SleepEntry,
            )

            # Heart rate average
            hr_avg = HeartRateEntry.objects.filter(
                user=user, recorded_at__date__gte=week_ago
            ).aggregate(avg=Avg('bpm'))['avg']
            if hr_avg:
                health_signals['heart_rate_avg_7d'] = round(float(hr_avg))

            # Blood pressure latest
            latest_bp = BloodPressureEntry.objects.filter(
                user=user, recorded_at__date__gte=week_ago
            ).order_by('-recorded_at').first()
            if latest_bp:
                health_signals['bp_latest'] = f"{latest_bp.systolic}/{latest_bp.diastolic}"

            # Glucose average
            glucose_avg = GlucoseEntry.objects.filter(
                user=user, recorded_at__date__gte=week_ago
            ).aggregate(avg=Avg('value'))['avg']
            if glucose_avg:
                health_signals['glucose_avg_7d'] = round(float(glucose_avg))

            # Blood oxygen average
            spo2_avg = BloodOxygenEntry.objects.filter(
                user=user, recorded_at__date__gte=week_ago
            ).aggregate(avg=Avg('spo2'))['avg']
            if spo2_avg:
                health_signals['blood_oxygen_avg_7d'] = round(float(spo2_avg), 1)

            # Steps average (fallback if state engine doesn't have it)
            if not health_signals.get('steps_avg_7d'):
                steps_avg = StepsEntry.objects.filter(
                    user=user, logged_date__gte=week_ago
                ).aggregate(avg=Avg('count'))['avg']
                if steps_avg:
                    health_signals['steps_avg_7d'] = int(steps_avg)

            # Sleep average (fallback if state engine doesn't have it)
            if not health_signals.get('sleep_avg_7d'):
                sleep_avg = SleepEntry.objects.filter(
                    user=user, sleep_date__gte=week_ago
                ).aggregate(avg=Avg('asleep_duration_minutes'))['avg']
                if sleep_avg:
                    health_signals['sleep_avg_7d'] = round(float(sleep_avg) / 60, 1)

            # Workouts — full detail (count, calories, duration, distance, HR)
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
                # Recent workout names for context
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

            # Heart rate events (clinically important)
            from apps.health.models import HeartRateEventEntry
            hr_events = HeartRateEventEntry.objects.filter(
                user=user, recorded_at__date__gte=week_ago
            ).count()
            if hr_events > 0:
                health_signals['heart_rate_events_7d'] = hr_events

        except Exception:
            pass  # Direct queries are supplementary — don't break context if they fail

        context['health_signals'] = health_signals
    except Exception:
        context['health_signals'] = {}

    # Open loops (unfinished goals, friction gates)
    try:
        from apps.purpose.models import LifeGoal
        overdue_goals = LifeGoal.objects.filter(
            user=user, status="active",
            target_date__lt=timezone.localdate(),
        ).count()
        context['open_loops'] = {
            'overdue_goals': overdue_goals,
        }
        # Add pending friction gates
        from apps.core.blueprint.models import InterventionLog
        pending_gates = InterventionLog.objects.filter(
            user=user, level=4, user_response='pending',
        ).count()
        context['open_loops']['pending_friction_gates'] = pending_gates
    except Exception:
        context['open_loops'] = {}

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
        context['feedback_profiles'] = {
            'insight_engagement': ie_profile.engagement_score if ie_profile else 0.5,
            'briefing_open_rate': be_profile.open_rate if be_profile else 0.0,
            'preferred_briefing_length': be_profile.preferred_length if be_profile else 'standard',
            'intervention_effectiveness': iv_profile.effectiveness_score if iv_profile else 0.5,
            'escalation_modifier': iv_profile.escalation_speed_modifier if iv_profile else 0.0,
        }
    except Exception:
        context['feedback_profiles'] = {}

    # Learned profile injection
    try:
        from apps.core.ai_learning.learning_extractor import get_profile_system_prompt
        context['learned_profile_prompt'] = get_profile_system_prompt(user)
    except Exception:
        context['learned_profile_prompt'] = ''

    # Executive tone mode (Phase 4 Step 5)
    context['executive_tone_mode'] = _determine_tone_mode(user, context)

    # Phase 5: Governance strategy injection
    try:
        from apps.core.ai_governance.strategy_selector import build_strategy_system_injection
        context['governance_strategy_prompt'] = build_strategy_system_injection(user)
    except Exception as e:
        logger.debug("CoS context: governance strategy unavailable: %s", e)
        context['governance_strategy_prompt'] = ''

    # Approaching life events (next 14 days)
    try:
        from apps.life.models import SignificantEvent, LifeEvent
        from apps.core.utils import get_user_today
        today = get_user_today(user)
        approaching_events = []

        # Significant recurring events (birthdays, anniversaries, memorials)
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
                            years = years  # this year's occurrence
                        event_info['years'] = years
                    approaching_events.append(event_info)
            except Exception:
                continue

        # One-time life events in the next 14 days
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

        # Sort by soonest first, cap at 5
        approaching_events.sort(key=lambda e: e['days_until'])
        context['approaching_life_events'] = approaching_events[:5]
    except Exception as e:
        logger.debug("CoS context: life events unavailable: %s", e)
        context['approaching_life_events'] = []

    return context


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
    lines.append("=== SITUATIONAL AWARENESS ===")
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

    # Active insights (things worth mentioning)
    insights = context.get('active_insights', [])
    if insights:
        lines.append("")
        lines.append("Notable Insights:")
        for i in insights[:5]:
            lines.append(f"  - {i['title']} ({i['module']})")

    # Active predictions (things to watch)
    predictions = context.get('active_predictions', [])
    if predictions:
        lines.append("Predictions:")
        for p in predictions[:3]:
            lines.append(f"  - {p['type']}: {p['value']}")

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
        "STRATEGIC EXECUTIVE — Lead with clarity and calm authority. "
        "Surface what matters, filter noise, reference the governance layer. "
        "No fluff, no over-questioning. Be present, grounded, strategic."
    ),
    'direct_accountability': (
        "DIRECT ACCOUNTABILITY — The user is drifting. Be direct. "
        "Name missed commitments. Challenge when necessary. "
        "No sugarcoating, but stay respectful. Reference specific evidence."
    ),
    'reflective_support': (
        "REFLECTIVE SUPPORT — The user's emotional state needs attention. "
        "Lead with empathy. Ask reflective questions. Encourage without pushing. "
        "Validate feelings before pivoting to action."
    ),
}


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
    pressure = context.get('weekly_pressure', {}).get('avg_load', 0)

    if drift >= 50:
        return f"Significant drift ({drift}/100). Realignment needed."
    if pressure >= 80:
        return f"High pressure week ({pressure}%). Protect priorities."
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
    """Pressure and load signals."""
    indicators = []
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
    """Relationship health summary."""
    signals = context.get('relationship_signals', [])
    drifting = [r for r in signals if r.get('drifting')]
    healthy = [r for r in signals if not r.get('drifting')]
    return {
        'total_tracked': len(signals),
        'drifting': [r['name'] for r in drifting[:3]],
        'healthy': [r['name'] for r in healthy[:3]],
    }


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
            {'title': ev.title, 'start': ev.start_dt.strftime('%I:%M %p').lstrip('0')}
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


def format_learning_mode_injection(context):
    """
    Format the reduced Learning Mode context as a system prompt injection.

    This is a lighter version of format_cos_system_injection() that excludes
    executive briefing, insights, predictions, and UAL narrative blocks.

    Args:
        context: dict from build_learning_mode_context()

    Returns:
        str — formatted system injection block.
    """
    lines = []
    lines.append("=== LEARNING MODE AWARENESS ===")
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

    lines.append("")
    lines.append("=== END LEARNING MODE AWARENESS ===")

    return '\n'.join(lines)
