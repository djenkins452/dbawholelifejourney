# ==============================================================================
# File: apps/admin_console/services.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Admin console service functions for phase management
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01
# ==============================================================================

from apps.admin_console.models import AdminProjectPhase


def get_active_phase():
    """
    Return the active project phase.

    Behavior:
    - Returns the AdminProjectPhase with status = "in_progress"
    - If none exists, returns the lowest phase_number that is NOT "complete"
      and sets its status to "in_progress"
    - If no phases exist, returns None
    """
    # First, try to find an in_progress phase
    active_phase = AdminProjectPhase.objects.filter(status='in_progress').first()
    if active_phase:
        return active_phase

    # No in_progress phase, find the lowest phase_number that is not complete
    next_phase = AdminProjectPhase.objects.exclude(
        status='complete'
    ).order_by('phase_number').first()

    if next_phase:
        # Set it to in_progress
        next_phase.status = 'in_progress'
        next_phase.save()
        return next_phase

    # No phases exist
    return None
