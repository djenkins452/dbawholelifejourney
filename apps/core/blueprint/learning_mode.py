"""
Whole Life Journey — Learning Mode Utility

Project: Whole Life Journey
Path: apps/core/blueprint/learning_mode.py
Purpose: Central Learning Mode state management for CoS foundational restructure

Description:
    Provides the single source of truth for Learning Mode state. All suppression
    gates (UAIO, PIE, PRIE, action handlers, audit logger) check this module.

    During Learning Mode:
    BLOCKED: UAIO execution, PIE event firing, PRIE predictions, domain writes,
             action-specific audit entries, SAE state writes
    ACTIVE:  SAE reads, AssistantMessage persistence, conversation memory,
             governance evaluation, safety/guardrails, system integrity audit logs,
             SLCME (preference_only context)

    Exit requires structured confirmation — execution remains blocked until
    the user confirms the CoS understanding summary.

Public API:
    - is_learning_mode_active(user) -> bool
    - enter_learning_mode(user) -> bool
    - request_exit_learning_mode(user) -> bool
    - confirm_exit_learning_mode(user) -> bool
    - cancel_exit_learning_mode(user) -> bool
    - is_exit_pending(user) -> bool
    - get_exit_summary(user) -> str or None

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import logging

from django.utils import timezone

logger = logging.getLogger(__name__)


def is_learning_mode_active(user):
    """
    Check if Learning Mode is active for this user.

    Returns True if either:
    - cos_learning_mode_active is True (explicit toggle), OR
    - Calibration is not complete and not paused (initial onboarding)

    This means Learning Mode covers both:
    1. Initial calibration (existing behavior)
    2. User-initiated re-entry via toggle (new Phase 1 capability)
    """
    try:
        blueprint = user.operating_blueprint
    except Exception:
        return False

    # Explicit Learning Mode toggle
    if blueprint.cos_learning_mode_active:
        return True

    # Legacy: calibration-in-progress also counts as Learning Mode
    if not blueprint.calibration_complete:
        overrides = blueprint.governance_overrides or {}
        if not overrides.get('calibration_paused', False):
            return True

    return False


def enter_learning_mode(user):
    """
    Activate Learning Mode. Blocks UAIO execution, PIE, PRIE.

    Can be called at any time — during or after calibration.

    Returns:
        bool — True if activated, False if already active or error.
    """
    try:
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        blueprint = PersonalOperatingBlueprint.get_or_create_for_user(user)

        if blueprint.cos_learning_mode_active:
            return False  # Already active

        blueprint.cos_learning_mode_active = True
        overrides = blueprint.governance_overrides or {}
        overrides['learning_mode_entered_at'] = timezone.now().isoformat()
        overrides.pop('learning_mode_exit_pending', None)
        overrides.pop('learning_mode_exit_summary', None)
        blueprint.governance_overrides = overrides
        blueprint.save(update_fields=[
            'cos_learning_mode_active', 'governance_overrides', 'updated_at',
        ])
        logger.info("Learning Mode entered for %s", user.email)
        return True
    except Exception as e:
        logger.error("Failed to enter Learning Mode for %s: %s", user.email, e)
        return False


def request_exit_learning_mode(user, summary_text=''):
    """
    Request exit from Learning Mode. Sets pending confirmation state.

    Execution remains blocked until confirm_exit_learning_mode() is called.

    Args:
        user: Django User instance.
        summary_text: The structured summary of declared priorities/constraints.

    Returns:
        bool — True if pending state set, False on error.
    """
    try:
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        blueprint = PersonalOperatingBlueprint.get_or_create_for_user(user)

        overrides = blueprint.governance_overrides or {}
        overrides['learning_mode_exit_pending'] = True
        overrides['learning_mode_exit_summary'] = summary_text
        overrides['learning_mode_exit_requested_at'] = timezone.now().isoformat()
        blueprint.governance_overrides = overrides
        # cos_learning_mode_active stays True — execution still blocked
        blueprint.save(update_fields=['governance_overrides', 'updated_at'])
        logger.info("Learning Mode exit requested for %s", user.email)
        return True
    except Exception as e:
        logger.error("Failed to request exit for %s: %s", user.email, e)
        return False


def confirm_exit_learning_mode(user):
    """
    Confirm exit from Learning Mode. Resumes execution.

    Only works when exit is pending (user has seen the summary).

    Returns:
        bool — True if confirmed and deactivated, False otherwise.
    """
    try:
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        blueprint = PersonalOperatingBlueprint.get_or_create_for_user(user)

        overrides = blueprint.governance_overrides or {}
        if not overrides.get('learning_mode_exit_pending', False):
            return False  # No pending exit

        # Deactivate Learning Mode
        blueprint.cos_learning_mode_active = False
        overrides.pop('learning_mode_exit_pending', None)
        overrides.pop('learning_mode_exit_summary', None)
        overrides.pop('learning_mode_exit_requested_at', None)
        overrides['learning_mode_confirmed_at'] = timezone.now().isoformat()
        overrides['learning_mode_last_exited_at'] = timezone.now().isoformat()
        blueprint.governance_overrides = overrides
        blueprint.save(update_fields=[
            'cos_learning_mode_active', 'governance_overrides', 'updated_at',
        ])
        logger.info("Learning Mode exit confirmed for %s", user.email)
        return True
    except Exception as e:
        logger.error("Failed to confirm exit for %s: %s", user.email, e)
        return False


def cancel_exit_learning_mode(user):
    """
    Cancel pending exit — stay in Learning Mode.

    Called when user says "no, that's not right" to the summary.

    Returns:
        bool — True if cancelled, False on error.
    """
    try:
        from apps.core.blueprint.models import PersonalOperatingBlueprint
        blueprint = PersonalOperatingBlueprint.get_or_create_for_user(user)

        overrides = blueprint.governance_overrides or {}
        overrides.pop('learning_mode_exit_pending', None)
        overrides.pop('learning_mode_exit_summary', None)
        overrides.pop('learning_mode_exit_requested_at', None)
        blueprint.governance_overrides = overrides
        blueprint.save(update_fields=['governance_overrides', 'updated_at'])
        logger.info("Learning Mode exit cancelled for %s", user.email)
        return True
    except Exception as e:
        logger.error("Failed to cancel exit for %s: %s", user.email, e)
        return False


def is_exit_pending(user):
    """Check if Learning Mode exit is pending confirmation."""
    try:
        blueprint = user.operating_blueprint
        overrides = blueprint.governance_overrides or {}
        return overrides.get('learning_mode_exit_pending', False)
    except Exception:
        return False


def get_exit_summary(user):
    """Get the pending exit summary text, or None."""
    try:
        blueprint = user.operating_blueprint
        overrides = blueprint.governance_overrides or {}
        return overrides.get('learning_mode_exit_summary')
    except Exception:
        return None
