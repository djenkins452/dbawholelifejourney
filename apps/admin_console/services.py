# ==============================================================================
# File: apps/admin_console/services.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Service functions for admin console task management
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01
# ==============================================================================

from .models import AdminProjectPhase, AdminTask


def get_active_phase():
    """
    Get the currently active project phase.

    Returns the phase with status='in_progress', or None if no active phase.
    """
    return AdminProjectPhase.objects.filter(status='in_progress').first()


def get_next_tasks(limit=5):
    """
    Get the next tasks to work on from the active phase.

    Queries tasks where:
    - phase = active phase
    - status IN ('ready', 'backlog')

    Orders by:
    1. priority ASC (lower number = higher priority)
    2. created_at ASC (older tasks first)

    Args:
        limit: Maximum number of tasks to return (default 5)

    Returns:
        QuerySet of AdminTask objects, or empty queryset if no active phase
    """
    active_phase = get_active_phase()

    if not active_phase:
        return AdminTask.objects.none()

    return AdminTask.objects.filter(
        phase=active_phase,
        status__in=['ready', 'backlog']
    ).order_by('priority', 'created_at')[:limit]
