"""
Whole Life Journey — CoS Context Builder

Project: Whole Life Journey
Path: apps/core/ai_orchestrator/cos_context.py
Purpose: Assemble full Chief of Staff context for every LLM interaction

Description:
    Builds a comprehensive context dict that reflects the user's current
    operational state. This context is injected into every LLM request
    so the assistant always operates with full situational awareness.

    The context is assembled from live engine queries — never cached
    stale data. All engine calls are wrapped in try/except for graceful
    degradation.

Public API:
    - build_cos_context(user) -> dict
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

    return context


def format_cos_system_injection(context):
    """
    Format the CoS context as a system prompt injection string.

    This string is prepended to the LLM system prompt so the model
    always has full operational awareness.

    Args:
        context: dict from build_cos_context()

    Returns:
        str — formatted system injection block.
    """
    lines = []
    lines.append("=== CHIEF OF STAFF OPERATIONAL CONTEXT ===")
    lines.append("")

    # Blueprint state
    bp = context.get('blueprint_state', {})
    if bp:
        lines.append(f"Operating Style: {bp.get('operating_style', 'balanced')}")
        lines.append(f"Interruption Tolerance: {bp.get('interruption_tolerance', 'medium')}")
        lines.append(f"Override Policy: {bp.get('override_policy', 'confirm')}")
        pillars = bp.get('pillars_ranked', [])
        if pillars:
            lines.append(f"Life Pillars (ranked): {', '.join(pillars)}")

    # Protected behaviors
    protected = context.get('protected_tiers', [])
    if protected:
        lines.append(f"Tier-1 Protected Behaviors: {', '.join(protected)}")

    # Capacity
    cap = context.get('capacity_snapshot', {})
    if cap:
        lines.append(f"Today's Capacity: {cap.get('capacity_pct', 0)}% allocated "
                     f"({cap.get('completed_blocks', 0)}/{cap.get('total_blocks', 0)} blocks completed)")

    # Alignment + Drift
    lines.append(f"Blueprint Alignment: {context.get('alignment_score', 100)}%")
    lines.append(f"Drift Score: {context.get('drift_score', 0)}/100")

    drift_p = context.get('drift_probability', {})
    if drift_p:
        lines.append(f"24h Drift Risk: {drift_p.get('probability_24h', 0)}%")
        lines.append(f"72h Drift Risk: {drift_p.get('probability_72h', 0)}%")

    # Forecast
    f24 = context.get('forecast_load_24h', 0)
    if f24:
        lines.append(f"Tomorrow Load Forecast: {f24}%")

    # Weekly pressure
    weekly = context.get('weekly_pressure', {})
    if weekly:
        lines.append("")
        lines.append("--- WEEKLY PRESSURE ---")
        lines.append(f"Summary: {weekly.get('summary', 'Not computed')}")
        lines.append(f"Average Load: {weekly.get('avg_load', 0)}%")
        peak = weekly.get('peak_day', '')
        if peak:
            lines.append(f"Peak Day: {peak} ({weekly.get('peak_load', 0)}%)")
        heavy = weekly.get('heavy_days', [])
        if heavy:
            lines.append(f"Heavy Days: {', '.join(heavy)}")
        light = weekly.get('light_days', [])
        if light:
            lines.append(f"Light Days: {', '.join(light)}")
        windows = weekly.get('opportunity_windows', [])
        if windows:
            for w in windows[:3]:
                lines.append(
                    f"Opportunity: {w.get('day_name', '')} "
                    f"{w.get('start_time', '')}-{w.get('end_time', '')} "
                    f"({w.get('duration_hours', 0)}h open)"
                )

    # Override frequency
    overrides = context.get('override_frequency_14d', 0)
    if overrides:
        lines.append(f"Override Frequency (14d): {overrides} overrides")

    # Medication
    med = context.get('medication_adherence_state', {})
    if med:
        lines.append(f"Medication: {med.get('taken_today', 0)}/{med.get('total_scheduled', 0)} "
                     f"taken ({med.get('adherence_pct', 0)}%)")

    # Fast
    fast = context.get('active_fast_status', {})
    if fast.get('active'):
        lines.append(f"Active Fast: In progress (target: {fast.get('target_hours', 0)}h)")

    # Today's blocks
    blocks = context.get('today_blocks_summary', [])
    if blocks:
        lines.append("")
        lines.append("Today's Schedule:")
        for b in blocks[:8]:  # Limit to prevent token bloat
            status = "[done]" if b['completed'] else "[locked]" if b['locked'] else ""
            lines.append(f"  {b['start']}-{b['end']} T{b['tier']} {b['title']} {status}")

    # Risk warnings
    warnings = context.get('risk_warnings', [])
    if warnings:
        lines.append("")
        lines.append("Risk Warnings:")
        for w in warnings:
            lines.append(f"  - {w}")

    # Module permissions
    mods = context.get('module_permissions', {})
    disabled = [k for k, v in mods.items() if not v]
    if disabled:
        lines.append(f"Disabled Modules (do not reference): {', '.join(disabled)}")

    lines.append("")
    lines.append("=== END OPERATIONAL CONTEXT ===")
    lines.append("")

    return '\n'.join(lines)
