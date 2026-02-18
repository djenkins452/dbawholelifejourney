"""
Whole Life Journey - Intervention Engine

Project: Whole Life Journey
Path: apps/core/blueprint/intervention_engine.py
Purpose: Escalation levels, friction gates, and respectful challenge language

Description:
    Implements the escalation system that governs how aggressively the assistant
    intervenes based on context:

    Level 0: Silent (log only)
    Level 1: Nudge (panel line)
    Level 2: Ping (assistant opens/starts conversation)
    Level 3: Interrupt (in-app modal + optional push)
    Level 4: Friction gate (confirm action)

    Uses persona system for tone variation and E3 for evidence in friction gates.

Public API:
    - determine_escalation_level(user, trigger_type, context) -> int
    - create_intervention(user, level, trigger_type, message, **kwargs) -> InterventionLog
    - create_friction_gate(user, behavior_key, action_description, consequence) -> dict
    - get_pending_interventions(user) -> QuerySet
    - record_intervention_response(intervention_id, response) -> InterventionLog

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import logging

from django.utils import timezone

from . import engine as blueprint_engine
from .models import InterventionLog

logger = logging.getLogger(__name__)


# =============================================================================
# ESCALATION RULES
# =============================================================================

# Trigger type → base escalation level
TRIGGER_BASE_LEVELS = {
    'tier1_violation': InterventionLog.LEVEL_FRICTION_GATE,  # Level 4
    'tier1_approaching_deadline': InterventionLog.LEVEL_INTERRUPT,  # Level 3
    'tier2_conflict': InterventionLog.LEVEL_PING,  # Level 2
    'drift_spike': InterventionLog.LEVEL_PING,  # Level 2
    'repeated_miss': InterventionLog.LEVEL_INTERRUPT,  # Level 3
    'approaching_deadline': InterventionLog.LEVEL_NUDGE,  # Level 1
    'schedule_deviation': InterventionLog.LEVEL_NUDGE,  # Level 1
    'architecture_ready': InterventionLog.LEVEL_NUDGE,  # Level 1
    'briefing_ready': InterventionLog.LEVEL_NUDGE,  # Level 1
    'curveball_impact': InterventionLog.LEVEL_PING,  # Level 2
    'idle_during_focus': InterventionLog.LEVEL_NUDGE,  # Level 1
    'high_drift_probability': InterventionLog.LEVEL_PING,  # Level 2
}


# =============================================================================
# PUBLIC API
# =============================================================================


def determine_escalation_level(user, trigger_type, context=None):
    """
    Determine the appropriate escalation level based on trigger, blueprint,
    and interruption tolerance.

    Args:
        user: The user
        trigger_type: String key matching TRIGGER_BASE_LEVELS
        context: Optional dict with additional context (tier, severity, etc.)

    Returns:
        int: Escalation level 0-4
    """
    context = context or {}
    blueprint = blueprint_engine.get_blueprint(user)

    # Start with base level for trigger type
    base_level = TRIGGER_BASE_LEVELS.get(trigger_type, InterventionLog.LEVEL_NUDGE)

    # Adjust based on interruption tolerance
    tolerance = blueprint.interruption_tolerance
    if tolerance == 'low':
        # Reduce by 1 level (but never below 0, and never reduce friction gates)
        if base_level < InterventionLog.LEVEL_FRICTION_GATE:
            base_level = max(0, base_level - 1)
    elif tolerance == 'high':
        # Increase by 1 level (but cap at level 3 for non-friction triggers)
        if base_level < InterventionLog.LEVEL_INTERRUPT:
            base_level = min(InterventionLog.LEVEL_INTERRUPT, base_level + 1)

    # Tier-based overrides
    tier = context.get('tier')
    if tier == 1:
        # Tier 1 violations ALWAYS get friction gate regardless of tolerance
        base_level = max(base_level, InterventionLog.LEVEL_FRICTION_GATE)

    # Severity boost
    severity = context.get('severity', 0.5)
    if severity >= 0.8 and base_level < InterventionLog.LEVEL_INTERRUPT:
        base_level = InterventionLog.LEVEL_INTERRUPT

    return base_level


def create_intervention(user, level, trigger_type, message, behavior_key='',
                        evidence=None, delivered_via='in_app'):
    """
    Create an intervention log entry and optionally trigger delivery.

    Args:
        user: The user
        level: Escalation level 0-4
        trigger_type: What triggered this
        message: The intervention message
        behavior_key: Associated behavior
        evidence: E3 evidence dict
        delivered_via: Delivery channel

    Returns:
        InterventionLog
    """
    # Apply persona rendering to message
    rendered_message = _render_with_persona(user, message, level)

    intervention = InterventionLog.objects.create(
        user=user,
        level=level,
        trigger_type=trigger_type,
        behavior_key=behavior_key,
        message=rendered_message,
        evidence=evidence or {},
        delivered_via=delivered_via,
    )

    # Trigger delivery based on level
    if level >= InterventionLog.LEVEL_PING:
        _trigger_delivery(user, intervention)

    logger.info(
        "Intervention created: L%d %s for %s via %s",
        level, trigger_type, user.email, delivered_via,
    )

    return intervention


def create_friction_gate(user, behavior_key, action_description, consequence,
                         adherence_projection=None, evidence=None):
    """
    Create a friction gate intervention with full E3 evidence.

    This is used when a Tier 1 behavior is at risk. The gate asks the user
    to confirm before proceeding.

    Args:
        user: The user
        behavior_key: The behavior being impacted
        action_description: What the user is about to do
        consequence: What happens if they proceed
        adherence_projection: Optional projected adherence % after this action
        evidence: Additional E3 evidence

    Returns:
        dict suitable for rendering a friction gate modal
    """
    blueprint = blueprint_engine.get_blueprint(user)
    from . import priority_engine

    # Compute identity cost
    cost = priority_engine.compute_identity_cost(blueprint, behavior_key)

    # Build the gate message
    gate_message = _build_friction_gate_message(
        user, behavior_key, action_description, consequence,
        adherence_projection, cost,
    )

    # Create the intervention
    gate_evidence = {
        'behavior_key': behavior_key,
        'action': action_description,
        'consequence': consequence,
        'identity_cost': cost.cost,
        'adherence_projection': adherence_projection,
        'pillar_weight': cost.pillar_weight,
        **(evidence or {}),
    }

    intervention = create_intervention(
        user=user,
        level=InterventionLog.LEVEL_FRICTION_GATE,
        trigger_type='tier1_violation',
        message=gate_message,
        behavior_key=behavior_key,
        evidence=gate_evidence,
        delivered_via='modal',
    )

    return {
        'intervention_id': intervention.pk,
        'message': gate_message,
        'identity_cost': cost.cost,
        'adherence_projection': adherence_projection,
        'evidence': gate_evidence,
        'options': [
            {'key': 'proceeded', 'label': 'Proceed', 'style': 'danger'},
            {'key': 'accepted', 'label': 'Keep going', 'style': 'primary'},
            {'key': 'adjusted', 'label': 'Adjust plan', 'style': 'secondary'},
        ],
    }


def get_pending_interventions(user, level_min=None):
    """Get unresponded interventions for a user."""
    qs = InterventionLog.objects.filter(
        user=user,
        user_response=InterventionLog.RESPONSE_PENDING,
    )
    if level_min is not None:
        qs = qs.filter(level__gte=level_min)
    return qs


def record_intervention_response(intervention_id, response, user=None):
    """
    Record the user's response to an intervention.

    Args:
        intervention_id: PK of the InterventionLog
        response: One of InterventionLog.RESPONSE_* constants
        user: Optional user for security validation

    Returns:
        InterventionLog or None
    """
    try:
        filters = {'pk': intervention_id}
        if user:
            filters['user'] = user
        intervention = InterventionLog.objects.get(**filters)
    except InterventionLog.DoesNotExist:
        return None

    intervention.record_response(response)

    # If user proceeded through friction gate, record for GLOE learning
    if (intervention.level == InterventionLog.LEVEL_FRICTION_GATE
            and response == InterventionLog.RESPONSE_PROCEEDED):
        _record_friction_override(intervention)

    logger.info(
        "Intervention %d response: %s (L%d, %s)",
        intervention_id, response, intervention.level, intervention.trigger_type,
    )

    return intervention


# =============================================================================
# INTERNAL HELPERS
# =============================================================================


def _render_with_persona(user, message, level):
    """Apply persona rendering to an intervention message."""
    try:
        from apps.core.ai_persona.persona_engine import render_with_persona

        # Map level to message type
        message_type_map = {
            0: 'info',
            1: 'nudge',
            2: 'warning',
            3: 'warning',
            4: 'warning',
        }
        msg_type = message_type_map.get(level, 'info')

        return render_with_persona(
            user, message, msg_type,
            domain='blueprint',
            priority=max(1, 5 - level),  # Higher level = higher priority
            severity=level / 4.0,
        )
    except Exception:
        return message


def _build_friction_gate_message(user, behavior_key, action_description,
                                 consequence, adherence_projection, identity_cost):
    """Build the friction gate confirmation message."""
    parts = []

    # What
    parts.append(f"You're about to: {action_description}")

    # Why it matters
    parts.append(f"This impacts: {behavior_key.replace('_', ' ').title()}")

    # Evidence
    if adherence_projection is not None:
        parts.append(
            f"Weekly adherence projection drops to {adherence_projection:.0f}%."
        )

    # Consequence
    parts.append(f"Consequence: {consequence}")

    # Identity cost
    if identity_cost.cost > 30:
        parts.append(f"Identity cost: {identity_cost.cost:.0f}/100")

    return " ".join(parts)


def _trigger_delivery(user, intervention):
    """Trigger delivery through DNE for ping/interrupt level interventions."""
    try:
        from apps.core.ai_delivery.delivery_engine import deliver_single

        # Only deliver if DNE is configured
        deliver_single(user, 'blueprint', intervention)
    except Exception as e:
        logger.warning("Could not trigger DNE delivery: %s", e)


def _record_friction_override(intervention):
    """Record that a user overrode a friction gate for learning purposes."""
    try:
        from apps.core.ai_guidance_learning.learning_engine import log_learning_event

        # Create a synthetic guidance event for GLOE
        log_learning_event(
            user=intervention.user,
            guidance_item=None,
            event_type='friction_overridden',
        )
    except Exception as e:
        logger.debug("Could not record friction override in GLOE: %s", e)
