"""
Whole Life Journey — Priority Weighting Questions (Hierarchical Drill-Down)

Project: Whole Life Journey
Path: apps/core/blueprint/priority_questions.py
Purpose: Hierarchical priority question tree for Learning Mode onboarding

Description:
    During Learning Mode, CoS asks "What matters most to you day to day?"
    then drills down module-by-module based on what the user selects.

    If user selects Health:
        → Physical vs Cognitive
        → Physical → Weight / Vitals / Sleep / Activity / Nutrition / Fasting / Meds
        → Cognitive → Focus / Mental health / Brain training / Journal insight

    Conversation adapts to how many modules are selected.
    Labels use user-facing language (never "tier" or "weight").

    Questions are injected into the Learning Mode system prompt, not
    displayed as UI forms. CoS asks ONE question at a time.

Public API:
    - get_priority_question_tree() -> dict
    - build_priority_onboarding_injection(user) -> str
    - get_next_priority_question(user) -> dict or None

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import logging

logger = logging.getLogger(__name__)


# =============================================================================
# PRIORITY QUESTION TREE
# =============================================================================

# Top-level modules the user can select
TOP_LEVEL_MODULES = [
    {'key': 'health', 'label': 'Health & Body', 'has_drill_down': True},
    {'key': 'faith', 'label': 'Faith & Spiritual Growth', 'has_drill_down': False},
    {'key': 'purpose', 'label': 'Goals & Purpose', 'has_drill_down': False},
    {'key': 'journal', 'label': 'Journaling & Reflection', 'has_drill_down': False},
    {'key': 'life', 'label': 'Tasks & Organization', 'has_drill_down': False},
    {'key': 'finance', 'label': 'Finances', 'has_drill_down': False},
]

# Health drill-down: Physical vs Cognitive
HEALTH_CATEGORIES = [
    {'key': 'physical', 'label': 'Physical Health'},
    {'key': 'cognitive', 'label': 'Mental & Cognitive Health'},
]

# Physical health sub-areas
HEALTH_PHYSICAL_AREAS = [
    {'key': 'health.weight', 'label': 'Weight & Body Composition'},
    {'key': 'health.vitals', 'label': 'Vitals (Heart Rate, Blood Pressure, Glucose)'},
    {'key': 'health.sleep', 'label': 'Sleep'},
    {'key': 'health.activity', 'label': 'Activity & Exercise'},
    {'key': 'health.nutrition', 'label': 'Nutrition & Food Tracking'},
    {'key': 'health.fasting', 'label': 'Fasting'},
    {'key': 'health.medications', 'label': 'Medications'},
]

# Cognitive health sub-areas
HEALTH_COGNITIVE_AREAS = [
    {'key': 'health.cognitive.focus', 'label': 'Focus & Productivity'},
    {'key': 'health.cognitive.mental_health', 'label': 'Mental Health & Mood'},
    {'key': 'health.cognitive.brain_training', 'label': 'Brain Training'},
    {'key': 'health.cognitive.journal_insight', 'label': 'Journal-Based Self-Insight'},
]

# Priority level options — user-facing language only
PRIORITY_LEVELS = [
    {'value': 1, 'label': "This is essential — I'd never want to let this slide"},
    {'value': 2, 'label': "This is important to me, but I have some flexibility"},
    {'value': 3, 'label': "This is nice to have — it can flex when things get busy"},
]


def get_priority_question_tree():
    """Return the full priority question tree structure."""
    return {
        'top_level': TOP_LEVEL_MODULES,
        'health_categories': HEALTH_CATEGORIES,
        'health_physical': HEALTH_PHYSICAL_AREAS,
        'health_cognitive': HEALTH_COGNITIVE_AREAS,
        'priority_levels': PRIORITY_LEVELS,
    }


def build_priority_onboarding_injection(user):
    """
    Build system prompt injection for priority onboarding during Learning Mode.

    Determines where the user is in the priority drill-down and generates
    the appropriate question prompt.

    Args:
        user: Django User instance.

    Returns:
        str — System prompt injection for priority questions, or empty string.
    """
    try:
        from apps.core.blueprint.models import (
            PersonalOperatingBlueprint,
            UserPriorityProfile,
        )
        blueprint = PersonalOperatingBlueprint.get_or_create_for_user(user)
    except Exception:
        return ''

    overrides = blueprint.governance_overrides or {}
    priority_state = overrides.get('priority_onboarding_state', {})

    # Check if priority onboarding has been triggered
    if not priority_state.get('active', False):
        return ''

    # Determine current phase
    phase = priority_state.get('phase', 'top_level')
    selected_modules = priority_state.get('selected_modules', [])

    lines = [
        "## PRIORITY ONBOARDING — WHAT MATTERS MOST",
        "",
    ]

    if phase == 'top_level':
        lines.append(
            "Ask the user: 'What matters most to you day to day?' "
            "Help them identify which areas of their life they want you to "
            "pay attention to. Options include:"
        )
        prefs = _get_enabled_modules(user)
        for mod in TOP_LEVEL_MODULES:
            if mod['key'] in prefs:
                lines.append(f"  - {mod['label']}")
        lines.append("")
        lines.append(
            "Let them share naturally. Don't present this as a checklist. "
            "Based on what they say, identify which modules they care about."
        )

    elif phase == 'health_category':
        lines.append(
            "The user selected Health as important. Ask them: "
            "'When it comes to health, what matters more to you right now — "
            "the physical side (weight, exercise, sleep, nutrition) or the "
            "mental side (focus, mood, brain training)?'"
        )
        lines.append("They might say both — that's fine. Note what they say.")

    elif phase == 'health_physical_detail':
        lines.append(
            "The user cares about physical health. Go deeper: "
            "'Of these areas, which ones are truly essential to you and which "
            "are more flexible?'"
        )
        for area in HEALTH_PHYSICAL_AREAS:
            lines.append(f"  - {area['label']}")
        lines.append("")
        lines.append(
            "For each area they mention, understand if it's essential to them "
            "or more of a nice-to-have. Use their own words, not 'tier' language."
        )

    elif phase == 'health_cognitive_detail':
        lines.append(
            "The user cares about cognitive/mental health. Ask: "
            "'Which of these matter most to you?'"
        )
        for area in HEALTH_COGNITIVE_AREAS:
            lines.append(f"  - {area['label']}")

    elif phase == 'module_priority':
        current_module = priority_state.get('current_module', '')
        mod_label = next(
            (m['label'] for m in TOP_LEVEL_MODULES if m['key'] == current_module),
            current_module,
        )
        lines.append(
            f"Now ask about {mod_label}: 'How important is {mod_label.lower()} "
            f"to you? Is it something you'd never want to let slide, "
            f"something important but flexible, or more of a nice-to-have?'"
        )
        lines.append("")
        lines.append("Also ask: 'Why does this matter to you?' — store the reason.")

    elif phase == 'complete':
        lines.append(
            "Priority onboarding is complete. Summarize what you've learned "
            "about their priorities and confirm: 'Here's how I understand "
            "what matters most to you. Is this right?'"
        )

    lines.append("")
    lines.append(
        "RULES: One question at a time. Wait for response. "
        "Don't dump the whole tree at once. Adapt based on their answers."
    )

    return '\n'.join(lines)


def start_priority_onboarding(user):
    """
    Initialize priority onboarding state.

    Called when entering Learning Mode or when CoS detects no priorities exist.

    Returns:
        bool — True if started.
    """
    try:
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        blueprint = PersonalOperatingBlueprint.get_or_create_for_user(user)
        overrides = blueprint.governance_overrides or {}
        overrides['priority_onboarding_state'] = {
            'active': True,
            'phase': 'top_level',
            'selected_modules': [],
            'current_module': '',
        }
        blueprint.governance_overrides = overrides
        blueprint.save(update_fields=['governance_overrides', 'updated_at'])
        return True
    except Exception as e:
        logger.error("Failed to start priority onboarding: %s", e)
        return False


def advance_priority_phase(user, phase, **kwargs):
    """
    Advance priority onboarding to the next phase.

    Args:
        user: Django User instance.
        phase: New phase name.
        **kwargs: Additional state to merge.

    Returns:
        bool — True if advanced.
    """
    try:
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        blueprint = PersonalOperatingBlueprint.get_or_create_for_user(user)
        overrides = blueprint.governance_overrides or {}
        state = overrides.get('priority_onboarding_state', {})
        state['phase'] = phase
        state.update(kwargs)
        overrides['priority_onboarding_state'] = state
        blueprint.governance_overrides = overrides
        blueprint.save(update_fields=['governance_overrides', 'updated_at'])
        return True
    except Exception as e:
        logger.error("Failed to advance priority phase: %s", e)
        return False


def complete_priority_onboarding(user):
    """
    Mark priority onboarding as complete.

    Returns:
        bool — True if completed.
    """
    try:
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        blueprint = PersonalOperatingBlueprint.get_or_create_for_user(user)
        overrides = blueprint.governance_overrides or {}
        state = overrides.get('priority_onboarding_state', {})
        state['active'] = False
        state['phase'] = 'complete'
        overrides['priority_onboarding_state'] = state
        blueprint.governance_overrides = overrides
        blueprint.save(update_fields=['governance_overrides', 'updated_at'])
        return True
    except Exception as e:
        logger.error("Failed to complete priority onboarding: %s", e)
        return False


def _get_enabled_modules(user):
    """Get set of enabled module keys for this user."""
    try:
        prefs = user.preferences
        enabled = set()
        if prefs.health_enabled:
            enabled.add('health')
        if prefs.faith_enabled:
            enabled.add('faith')
        if prefs.purpose_enabled:
            enabled.add('purpose')
        if prefs.journal_enabled:
            enabled.add('journal')
        if prefs.life_enabled:
            enabled.add('life')
        if prefs.finances_enabled:
            enabled.add('finance')
        return enabled
    except Exception:
        return set()
