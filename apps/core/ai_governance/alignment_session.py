"""
Phase 5 — Governance Alignment Session Handler.

Manages the multi-stage conversational alignment process that replaces
the old 14-day calibration trickle. The alignment session runs through
4 natural-language stages, then per-module classification.

Stages:
    1. core_values     — "What does a good day look like?"
    2. success_definition — "When you feel accomplished, what happened?"
    3. chaos_protection — "When things fall apart, what do you protect first?"
    4. top_three       — "If you could only do 3 things tomorrow, what are they?"
    5. module_classification — Per-module: NonNeg / Important / Flexible

Public API:
    - get_alignment_stage(user) -> dict or None
    - record_alignment_response(user, stage, response_text) -> dict
    - build_alignment_system_injection(user) -> str
    - is_alignment_complete(user) -> bool
    - get_default_modules(user) -> list[dict]
"""

import logging

from django.utils import timezone

logger = logging.getLogger(__name__)


# =============================================================================
# ALIGNMENT STAGE DEFINITIONS
# =============================================================================

ALIGNMENT_STAGES = [
    {
        'key': 'core_values',
        'question': (
            "Before I can really help you, I need to understand what matters most. "
            "What does a genuinely good day look like for you? "
            "Not productive — good. What happens on those days?"
        ),
        'purpose': 'Understand what the user values most in daily life',
        'follow_up': (
            "That tells me a lot about what we should protect in your schedule."
        ),
    },
    {
        'key': 'success_definition',
        'question': (
            "When you look back on a week and feel like you nailed it — "
            "what actually happened? What made it feel that way?"
        ),
        'purpose': 'Understand what success means to this person',
        'follow_up': (
            "Good — that's the standard we're aiming for."
        ),
    },
    {
        'key': 'chaos_protection',
        'question': (
            "Now the flip side. When life gets chaotic — deadlines, "
            "unexpected things — what do you refuse to give up? "
            "What's the last thing you'd drop?"
        ),
        'purpose': 'Identify non-negotiable behaviors under pressure',
        'follow_up': (
            "Those become the anchors. Everything else flexes around them."
        ),
    },
    {
        'key': 'top_three',
        'question': (
            "If tomorrow was packed and you could only do 3 things, "
            "what would they be?"
        ),
        'purpose': 'Force-rank the top priorities for schedule protection',
        'follow_up': (
            "Perfect. Those three get protected first, every day."
        ),
    },
]

# Module classification stage is handled separately (per-module loop)

# Default modules to classify, in display order
DEFAULT_MODULE_SET = [
    {'key': 'faith', 'display_name': 'Prayer / Devotion'},
    {'key': 'health.exercise', 'display_name': 'Exercise / Workout'},
    {'key': 'health.nutrition', 'display_name': 'Nutrition / Eating'},
    {'key': 'health.sleep', 'display_name': 'Sleep'},
    {'key': 'journal', 'display_name': 'Journaling / Reflection'},
    {'key': 'purpose', 'display_name': 'Goals / Purpose Work'},
    {'key': 'relationships', 'display_name': 'Family / Relationships'},
    {'key': 'finance', 'display_name': 'Finances'},
    {'key': 'health.weight', 'display_name': 'Weight Management'},
    {'key': 'brain_training', 'display_name': 'Brain Training'},
]


# =============================================================================
# PUBLIC API
# =============================================================================


def get_alignment_stage(user):
    """
    Get the current alignment stage for the user.

    Returns:
        dict with 'stage_key', 'question', 'purpose', 'follow_up', 'stage_number', 'total_stages'
        or None if alignment is complete or not started.
    """
    session = _get_or_create_session(user)
    if not session or session.is_complete:
        return None

    stage_key = session.current_stage
    if stage_key == 'complete':
        return None

    # Conversation stages (1-4)
    for i, stage in enumerate(ALIGNMENT_STAGES):
        if stage['key'] == stage_key:
            return {
                'stage_key': stage_key,
                'question': stage['question'],
                'purpose': stage['purpose'],
                'follow_up': stage['follow_up'],
                'stage_number': i + 1,
                'total_stages': len(ALIGNMENT_STAGES) + 1,  # +1 for module classification
            }

    # Module classification stage
    if stage_key == 'module_classification':
        pending = session.pending_modules or []
        if not pending:
            # All modules classified — complete
            _complete_session(session)
            return None

        next_module = pending[0]
        return {
            'stage_key': 'module_classification',
            'module_key': next_module['key'],
            'module_name': next_module['display_name'],
            'question': (
                f"How important is {next_module['display_name']} to you? "
                "Is it something you'd never skip (non-negotiable), "
                "something that matters but can flex (important), "
                "or something nice to have when there's room (flexible)?"
            ),
            'purpose': f"Classify {next_module['display_name']} commitment level",
            'stage_number': len(ALIGNMENT_STAGES) + 1,
            'total_stages': len(ALIGNMENT_STAGES) + 1,
            'remaining_modules': len(pending),
        }

    return None


def record_alignment_response(user, stage_key, response_text, classification=None):
    """
    Record a user's response to an alignment stage question.

    Args:
        user: Django User instance.
        stage_key: str — the stage being answered.
        response_text: str — user's natural language response.
        classification: str — for module_classification stage only:
            'non_negotiable', 'important', or 'flexible'

    Returns:
        dict with 'next_stage' info or 'complete': True
    """
    session = _get_or_create_session(user)
    if not session:
        return {'error': 'No active session'}

    # Record the response
    session.record_response(stage_key, {
        'response': response_text,
        'classification': classification,
        'recorded_at': timezone.now().isoformat(),
    })

    if stage_key == 'module_classification' and classification:
        # Classify this module and move to next
        pending = session.pending_modules or []
        if pending:
            module_info = pending[0]
            _create_governance_profile(
                user, module_info['key'], module_info['display_name'],
                classification, response_text,
            )
            # Remove from pending
            session.pending_modules = pending[1:]
            session.save(update_fields=['pending_modules', 'updated_at'])

            if not session.pending_modules:
                # All classified — complete
                _complete_session(session)
                return {'complete': True}

            next_mod = session.pending_modules[0]
            return {
                'next_stage': 'module_classification',
                'module_key': next_mod['key'],
                'module_name': next_mod['display_name'],
                'remaining': len(session.pending_modules),
            }

    else:
        # Advance to next conversation stage
        session.advance_to_next_stage()

        if session.current_stage == 'module_classification':
            # Initialize pending modules
            modules = get_default_modules(user)
            session.pending_modules = modules
            session.save(update_fields=['pending_modules', 'updated_at'])

        if session.current_stage == 'complete':
            _complete_session(session)
            return {'complete': True}

        next = get_alignment_stage(user)
        if next:
            return {'next_stage': next['stage_key']}
        return {'complete': True}


def build_alignment_system_injection(user):
    """
    Build system prompt instructions for the alignment session.

    If alignment is in progress, returns instructions for the current stage.
    If complete, returns empty string (strategy injection handles ongoing behavior).

    Returns:
        str — system prompt block.
    """
    session = _get_or_create_session(user)
    if not session or session.is_complete:
        return ""

    stage = get_alignment_stage(user)
    if not stage:
        return ""

    lines = ["--- GOVERNANCE ALIGNMENT (IN PROGRESS) ---"]
    lines.append("")
    lines.append(
        "You are in the middle of learning what matters most to this person. "
        "This is a conversational discovery — not a questionnaire."
    )
    lines.append("")

    # Include previous responses as context
    responses = session.responses or {}
    if responses:
        lines.append("What you've learned so far:")
        for key, data in responses.items():
            if isinstance(data, dict) and 'response' in data:
                stage_name = key.replace('_', ' ').title()
                lines.append(f"  - {stage_name}: {data['response'][:200]}")
        lines.append("")

    # Current question
    lines.append(f"CURRENT STAGE: {stage['stage_key']}")
    lines.append(f"ASK THIS NATURALLY: {stage['question']}")

    if stage['stage_key'] == 'module_classification':
        lines.append("")
        lines.append(
            "For module classification, listen for the user's commitment level: "
            "non-negotiable (would never skip), important (matters but can flex), "
            "or flexible (nice to have). Accept their natural language and classify accordingly."
        )
        remaining = stage.get('remaining_modules', 0)
        if remaining > 1:
            lines.append(
                f"After this module, there are {remaining - 1} more to classify. "
                "You can classify multiple at once if the user volunteers them."
            )
        elif remaining == 1:
            # Last module — after classifying, ask about CoS display name
            lines.append(
                "This is the last area to classify. After the user answers, "
                "wrap up the alignment warmly, then ask ONE more thing: "
                "\"One more thing — what would you like to call me? "
                "Some people use a name, others keep 'Chief of Staff'. "
                "Totally up to you.\" "
                "If they give a name, use the set_cos_name function to save it. "
                "If they say 'Chief of Staff' or similar, that's fine — no action needed."
            )

    lines.append("")
    lines.append(
        "RULES: "
        "1. Ask naturally, don't read the question verbatim. "
        "2. Acknowledge their answer before moving on. "
        "3. Use their words back to them. "
        "4. Don't rush — one question at a time. "
        "5. If they give a short answer, ask a brief follow-up. "
        "6. Never use terms like 'governance' or 'drift pressure'."
    )
    lines.append("--- END ALIGNMENT ---")

    return '\n'.join(lines)


def is_alignment_complete(user):
    """Check if user has completed the alignment session."""
    try:
        from apps.core.ai_governance.models import GovernanceAlignmentSession
        session = GovernanceAlignmentSession.objects.filter(user=user).first()
        if not session:
            return False
        return session.is_complete
    except Exception:
        return False


def needs_alignment(user):
    """Check if user needs to go through alignment (no session or incomplete)."""
    try:
        from apps.core.ai_governance.models import (
            GovernanceAlignmentSession,
            GovernanceProfile,
        )
        # If they have governance profiles, alignment is done
        if GovernanceProfile.objects.filter(user=user, is_active=True).exists():
            return False
        # If they have a complete session, alignment is done
        session = GovernanceAlignmentSession.objects.filter(user=user).first()
        if session and session.is_complete:
            return False
        return True
    except Exception:
        return False


def get_default_modules(user):
    """
    Get the list of modules to classify for this user.

    Filters DEFAULT_MODULE_SET by what modules the user has enabled.
    """
    try:
        prefs = user.preferences
        modules = []
        for mod in DEFAULT_MODULE_SET:
            key = mod['key'].split('.')[0]  # Top-level module
            # Check if module is enabled
            enabled_check = {
                'faith': prefs.faith_enabled,
                'health': prefs.health_enabled,
                'journal': prefs.journal_enabled,
                'purpose': prefs.purpose_enabled,
                'relationships': prefs.life_enabled,
                'finance': prefs.finances_enabled,
                'brain_training': getattr(prefs, 'brain_training_enabled', False),
            }
            if enabled_check.get(key, True):
                modules.append(mod)
        return modules
    except Exception:
        return list(DEFAULT_MODULE_SET)


# =============================================================================
# INTERNAL HELPERS
# =============================================================================


def _get_or_create_session(user):
    """Get or create the alignment session for a user."""
    try:
        from apps.core.ai_governance.models import GovernanceAlignmentSession
        session, created = GovernanceAlignmentSession.objects.get_or_create(
            user=user,
            defaults={'current_stage': 'core_values'},
        )
        return session
    except Exception as e:
        logger.debug("Alignment session unavailable: %s", e)
        return None


def _complete_session(session):
    """Mark alignment session as complete."""
    session.is_complete = True
    session.current_stage = 'complete'
    session.completed_at = timezone.now()
    session.save(update_fields=[
        'is_complete', 'current_stage', 'completed_at', 'updated_at',
    ])
    logger.info("Governance alignment completed for user %s", session.user_id)


def _create_governance_profile(user, module_key, display_name, classification, reason):
    """Create or update a GovernanceProfile from alignment classification."""
    try:
        from apps.core.ai_governance.models import GovernanceProfile

        # Map classification to importance weight
        weight_map = {
            'non_negotiable': 2.0,
            'important': 1.0,
            'flexible': 0.3,
        }

        profile, created = GovernanceProfile.objects.update_or_create(
            user=user,
            module_key=module_key,
            defaults={
                'display_name': display_name,
                'commitment_level': classification,
                'importance_weight': weight_map.get(classification, 1.0),
                'declared_reason': reason[:500] if reason else '',
                'is_active': True,
            },
        )

        # If non-negotiable, also check if there's a matching NonNegotiable
        if classification == 'non_negotiable':
            _sync_non_negotiable(user, module_key, display_name)

        return profile

    except Exception as e:
        logger.error("Failed to create governance profile: %s", e)
        return None


def _sync_non_negotiable(user, module_key, display_name):
    """
    Ensure a NonNegotiable record exists for items classified as non-negotiable.
    Only creates if one doesn't already exist.
    """
    try:
        from apps.core.blueprint.models import NonNegotiable, PersonalOperatingBlueprint

        blueprint = PersonalOperatingBlueprint.get_or_create_for_user(user)

        # Check if already exists
        exists = NonNegotiable.objects.filter(
            blueprint=blueprint,
            module_key=module_key,
            is_active=True,
        ).exists()

        if not exists:
            NonNegotiable.objects.create(
                blueprint=blueprint,
                behavior_key=module_key.replace('.', '_'),
                display_name=display_name,
                module_key=module_key,
                frequency='daily',
                is_active=True,
            )
    except Exception as e:
        logger.debug("NonNegotiable sync skipped: %s", e)
