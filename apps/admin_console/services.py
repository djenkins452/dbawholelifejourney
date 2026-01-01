# ==============================================================================
# File: apps/admin_console/services.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Service functions for admin console task management
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01
# ==============================================================================

from .models import AdminProjectPhase, AdminTask, AdminActivityLog


# Valid blocker categories (per Phase 5 spec)
BLOCKER_CATEGORIES = ['infra', 'business']

# Blocker criteria - at least one must be true to create a blocker
BLOCKER_CRITERIA = [
    'missing_config',      # Required configuration or environment variable is missing
    'external_account',    # An external account, credential, or API key is required
    'manual_setup',        # A manual setup step must be completed by a human
    'business_decision',   # A business rule or decision is required to proceed
]


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


def is_valid_blocker_reason(blocker_reason):
    """
    Check if a blocker reason is valid.

    A blocker exists ONLY when one or more of the following is true:
    - Required configuration or environment variable is missing
    - An external account, credential, or API key is required
    - A manual setup step must be completed by a human
    - A business rule or decision is required to proceed

    Args:
        blocker_reason: String describing why this is a blocker, should indicate
                       which blocker criteria applies

    Returns:
        True if the reason indicates a valid blocker condition
    """
    if not blocker_reason:
        return False

    # The blocker_reason should describe what criteria applies
    # We accept any non-empty reason, but the caller is responsible for
    # ensuring it meets the blocker criteria
    return True


def create_blocker_task(
    blocked_task,
    title,
    description,
    category='infra',
    effort='S',
    created_by='claude'
):
    """
    Create a blocker task and mark the original task as blocked.

    This function implements Phase 5 Blocker Task Creation:
    1. Creates a new AdminTask representing the blocker
    2. Updates the original task to status='blocked' with reference to blocker
    3. Logs activity for both tasks

    Args:
        blocked_task: The AdminTask being blocked
        title: Short, action-oriented description of what must be done
        description: Must include:
                    - What task was being worked on
                    - What specifically caused the block
                    - What is required to unblock the work
        category: 'infra' or 'business' only (default: 'infra')
        effort: 'S' or 'M' (default: 'S')
        created_by: 'claude' or 'human' (default: 'claude')

    Returns:
        Tuple of (blocker_task, blocked_task, blocker_log, blocked_log)

    Raises:
        ValueError: If category is not 'infra' or 'business'
        ValueError: If blocked_task is not in 'in_progress' status
    """
    # Validate category
    if category not in BLOCKER_CATEGORIES:
        raise ValueError(
            f"Blocker category must be one of {BLOCKER_CATEGORIES}, got '{category}'"
        )

    # Validate effort
    if effort not in ['S', 'M']:
        raise ValueError(
            f"Blocker effort must be 'S' or 'M', got '{effort}'"
        )

    # Validate blocked task status
    if blocked_task.status != 'in_progress':
        raise ValueError(
            f"Can only create blocker for 'in_progress' task, "
            f"task '{blocked_task.title}' is '{blocked_task.status}'"
        )

    # Create the blocker task
    # Priority should be equal to or higher (lower number) than blocked task
    blocker_priority = min(blocked_task.priority, blocked_task.priority)

    blocker_task = AdminTask.objects.create(
        title=title,
        description=description,
        category=category,
        priority=blocker_priority,
        status='ready',
        effort=effort,
        phase=blocked_task.phase,
        created_by=created_by
    )

    # Create activity log for blocker task creation
    blocker_log = AdminActivityLog.objects.create(
        task=blocker_task,
        action=(
            f"Blocker task created. "
            f"Blocking task: '{blocked_task.title}' (ID: {blocked_task.pk}). "
            f"Reason: {description[:200]}"
        ),
        created_by=created_by
    )

    # Update the original task to blocked status
    blocked_reason = f"Blocked by: {title} (Task ID: {blocker_task.pk})"
    blocked_task.status = 'blocked'
    blocked_task.blocked_reason = blocked_reason
    blocked_task.blocking_task = blocker_task
    blocked_task.save()

    # Create activity log for blocked task
    blocked_log = AdminActivityLog.objects.create(
        task=blocked_task,
        action=(
            f"Task blocked. "
            f"Blocker task created: '{title}' (ID: {blocker_task.pk}). "
            f"Reason: {description[:200]}"
        ),
        created_by=created_by
    )

    return blocker_task, blocked_task, blocker_log, blocked_log


def get_blocked_tasks(phase=None):
    """
    Get all currently blocked tasks.

    Args:
        phase: Optional phase to filter by. If None, returns all blocked tasks.

    Returns:
        QuerySet of blocked AdminTask objects
    """
    queryset = AdminTask.objects.filter(status='blocked')
    if phase:
        queryset = queryset.filter(phase=phase)
    return queryset.order_by('priority', 'created_at')


def get_blocker_tasks(phase=None):
    """
    Get all tasks that are blocking other tasks.

    Args:
        phase: Optional phase to filter by. If None, returns all blocker tasks.

    Returns:
        QuerySet of AdminTask objects that have blocked tasks
    """
    queryset = AdminTask.objects.filter(blocks__isnull=False).distinct()
    if phase:
        queryset = queryset.filter(phase=phase)
    return queryset.order_by('priority', 'created_at')
