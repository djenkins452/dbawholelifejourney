# ==============================================================================
# File: apps/admin_console/services.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Service functions for admin console task management
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01 (Phase 8 - Phase Auto-Unlock)
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


def get_project_metrics():
    """
    Compute project status metrics for admin use.

    Returns a dictionary with:
    - active_phase: The currently active phase number (or None)
    - global: Metrics across all phases (total, completed, remaining, blocked)
    - active_phase_metrics: Metrics for the active phase only
    - tasks_created_by_claude: Count of tasks created by Claude
    - high_priority_remaining_tasks: High priority (priority <= 2) tasks not done

    This function is read-only and does not cache or mutate data.
    """
    active_phase = get_active_phase()

    # Global metrics (all phases)
    all_tasks = AdminTask.objects.all()
    total_tasks = all_tasks.count()
    completed_tasks = all_tasks.filter(status='done').count()
    remaining_tasks = all_tasks.exclude(status='done').count()
    blocked_tasks = all_tasks.filter(status='blocked').count()

    # Active phase metrics
    if active_phase:
        phase_tasks = AdminTask.objects.filter(phase=active_phase)
        total_tasks_in_phase = phase_tasks.count()
        completed_tasks_in_phase = phase_tasks.filter(status='done').count()
        remaining_tasks_in_phase = phase_tasks.exclude(status='done').count()
        blocked_tasks_in_phase = phase_tasks.filter(status='blocked').count()
        active_phase_number = active_phase.phase_number
    else:
        total_tasks_in_phase = 0
        completed_tasks_in_phase = 0
        remaining_tasks_in_phase = 0
        blocked_tasks_in_phase = 0
        active_phase_number = None

    # Optional metrics
    tasks_created_by_claude = all_tasks.filter(created_by='claude').count()
    high_priority_remaining_tasks = all_tasks.filter(
        priority__lte=2
    ).exclude(status='done').count()

    return {
        'active_phase': active_phase_number,
        'global': {
            'total_tasks': total_tasks,
            'completed_tasks': completed_tasks,
            'remaining_tasks': remaining_tasks,
            'blocked_tasks': blocked_tasks,
        },
        'active_phase_metrics': {
            'total_tasks': total_tasks_in_phase,
            'completed_tasks': completed_tasks_in_phase,
            'remaining_tasks': remaining_tasks_in_phase,
            'blocked_tasks': blocked_tasks_in_phase,
        },
        'tasks_created_by_claude': tasks_created_by_claude,
        'high_priority_remaining_tasks': high_priority_remaining_tasks,
    }


def is_phase_complete(phase):
    """
    Check if a phase is complete based on task status.

    A phase is considered COMPLETE when:
    - All AdminTask records for that phase have status = "done"
    - OR no tasks exist for that phase

    Blocked tasks do NOT count as complete.

    Args:
        phase: AdminProjectPhase instance to check

    Returns:
        True if the phase is complete, False otherwise
    """
    tasks = AdminTask.objects.filter(phase=phase)

    # No tasks = complete
    if not tasks.exists():
        return True

    # All tasks must be done
    non_done_tasks = tasks.exclude(status='done')
    return not non_done_tasks.exists()


def get_next_phase(phase):
    """
    Get the next phase by ascending phase_number.

    Args:
        phase: AdminProjectPhase instance

    Returns:
        The next AdminProjectPhase by phase_number, or None if none exists
    """
    return AdminProjectPhase.objects.filter(
        phase_number__gt=phase.phase_number
    ).order_by('phase_number').first()


def unlock_next_phase(completed_phase, created_by='claude'):
    """
    Unlock the next phase after a phase is completed.

    Only unlocks if:
    - A next phase exists (by ascending phase_number)
    - The next phase has status = "not_started"

    Does NOT unlock more than one phase at a time.

    Args:
        completed_phase: AdminProjectPhase that was just completed
        created_by: 'human' or 'claude' for activity log

    Returns:
        The unlocked phase, or None if no phase was unlocked
    """
    next_phase = get_next_phase(completed_phase)

    if not next_phase:
        return None

    if next_phase.status != 'not_started':
        return None

    # Unlock the next phase
    next_phase.status = 'in_progress'
    next_phase.save()

    # Create activity log for the unlock
    # We use a task from the next phase if one exists, otherwise from completed phase
    reference_task = AdminTask.objects.filter(phase=next_phase).first()
    if not reference_task:
        reference_task = AdminTask.objects.filter(phase=completed_phase).first()

    if reference_task:
        AdminActivityLog.objects.create(
            task=reference_task,
            action=(
                f"Phase {next_phase.phase_number} ('{next_phase.name}') unlocked. "
                f"Previous phase {completed_phase.phase_number} ('{completed_phase.name}') completed."
            ),
            created_by=created_by
        )

    return next_phase


def check_and_complete_phase(phase, created_by='claude'):
    """
    Check if a phase is complete and mark it as such.

    This function:
    1. Evaluates tasks for the given phase
    2. If completion rule is met (all tasks done OR no tasks):
       - Sets phase.status = "complete"
       - Writes an AdminActivityLog entry describing phase completion
       - Unlocks the next phase if one exists

    Safety rules:
    - Never auto-complete a phase with blocked tasks
    - Never skip phase numbers
    - Never unlock future phases early

    Args:
        phase: AdminProjectPhase instance to check
        created_by: 'human' or 'claude' for activity log

    Returns:
        Tuple of (phase_completed: bool, unlocked_phase: AdminProjectPhase or None)
    """
    # Check if phase is already complete
    if phase.status == 'complete':
        return (False, None)

    # Check if phase has blocked tasks - never auto-complete with blocked tasks
    blocked_count = AdminTask.objects.filter(phase=phase, status='blocked').count()
    if blocked_count > 0:
        return (False, None)

    # Check if phase is complete
    if not is_phase_complete(phase):
        return (False, None)

    # Mark phase as complete
    phase.status = 'complete'
    phase.save()

    # Create activity log for phase completion
    reference_task = AdminTask.objects.filter(phase=phase).first()
    if reference_task:
        AdminActivityLog.objects.create(
            task=reference_task,
            action=(
                f"Phase {phase.phase_number} ('{phase.name}') completed. "
                f"All tasks in phase are done."
            ),
            created_by=created_by
        )

    # Unlock the next phase
    unlocked_phase = unlock_next_phase(phase, created_by)

    return (True, unlocked_phase)


def on_task_done(task, created_by='claude'):
    """
    Handler to call when a task transitions to 'done' status.

    This triggers the phase completion check and auto-unlock logic.

    Should ONLY be called when a task status transitions to 'done'.
    Should NOT be called on reads or page loads.

    Args:
        task: The AdminTask that was just marked as done
        created_by: 'human' or 'claude' for activity log

    Returns:
        Tuple of (phase_completed: bool, unlocked_phase: AdminProjectPhase or None)
    """
    return check_and_complete_phase(task.phase, created_by)
