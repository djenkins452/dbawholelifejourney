# ==============================================================================
# File: apps/admin_console/services.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Service functions for admin console task management
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01 (Prepopulate Phase Dropdown 1-20)
# ==============================================================================

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional

from django.utils import timezone

from .models import AdminProjectPhase, AdminTask, AdminActivityLog


# ==============================================================================
# System State Snapshot (Phase 9 - Session Bootstrapping)
# ==============================================================================

@dataclass
class SystemStateSnapshot:
    """
    Read-only snapshot of system state at a point in time.

    This structure captures the minimal information needed for session
    bootstrapping. It is built once per request and reused by other
    admin endpoints if needed. It is NOT persisted to the database.
    """
    # Active phase info (None if no active phase)
    active_phase_number: Optional[int]
    active_phase_name: Optional[str]
    active_phase_status: Optional[str]

    # Active phase objective
    active_phase_objective: Optional[str]

    # Task counts for active phase only
    open_tasks_count: int
    blocked_tasks_count: int

    # Timestamp when snapshot was built
    last_updated: datetime


# Request-scope storage key for snapshot
_REQUEST_SNAPSHOT_KEY = '_admin_system_state_snapshot'


def get_system_state_snapshot(request=None) -> SystemStateSnapshot:
    """
    Get or build the system state snapshot for the current request.

    If a request object is provided, the snapshot is cached on the request
    and reused for subsequent calls within the same request. This ensures
    the snapshot is built once per request.

    If no request is provided, builds and returns a fresh snapshot without
    caching.

    Args:
        request: Optional Django request object for request-scope caching

    Returns:
        SystemStateSnapshot with current system state
    """
    if request is not None:
        # Check if snapshot already cached on request
        cached = getattr(request, _REQUEST_SNAPSHOT_KEY, None)
        if cached is not None:
            return cached

        # Build and cache
        snapshot = build_system_state_snapshot()
        setattr(request, _REQUEST_SNAPSHOT_KEY, snapshot)
        return snapshot

    # No request provided - build fresh snapshot
    return build_system_state_snapshot()


def build_system_state_snapshot() -> SystemStateSnapshot:
    """
    Build a read-only snapshot of the current system state.

    This function:
    - Reads the active phase using existing logic
    - Counts tasks for the active phase by status
    - Returns a populated SystemStateSnapshot
    - Does NOT mutate any data

    Note: Prefer using get_system_state_snapshot(request) for request-scope
    caching. Use this function directly only when building a fresh snapshot
    is explicitly needed.

    Returns:
        SystemStateSnapshot with current system state
    """
    active_phase = get_active_phase()

    if active_phase:
        # Count tasks for active phase only
        phase_tasks = AdminTask.objects.filter(phase=active_phase)

        # Open tasks = anything not done and not blocked
        open_tasks_count = phase_tasks.filter(
            status__in=['backlog', 'ready', 'in_progress']
        ).count()

        # Blocked tasks
        blocked_tasks_count = phase_tasks.filter(status='blocked').count()

        return SystemStateSnapshot(
            active_phase_number=active_phase.phase_number,
            active_phase_name=active_phase.name,
            active_phase_status=active_phase.status,
            active_phase_objective=active_phase.objective,
            open_tasks_count=open_tasks_count,
            blocked_tasks_count=blocked_tasks_count,
            last_updated=timezone.now()
        )
    else:
        # No active phase - return null-safe values
        return SystemStateSnapshot(
            active_phase_number=None,
            active_phase_name=None,
            active_phase_status=None,
            active_phase_objective=None,
            open_tasks_count=0,
            blocked_tasks_count=0,
            last_updated=timezone.now()
        )


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


# ==============================================================================
# Phase 8 - Phase Auto-Unlock
# ==============================================================================

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


# ==============================================================================
# Phase 10 - Hardening & Fail-Safes
# ==============================================================================

# Safe threshold for task in_progress - 24 hours
TASK_IN_PROGRESS_THRESHOLD_HOURS = 24


@dataclass
class SystemIssue:
    """Represents a detected system issue."""
    issue_type: str  # 'no_active_phase', 'multiple_active_phases', 'stuck_phase', 'stuck_task'
    severity: str  # 'critical', 'warning'
    description: str
    affected_ids: List[int] = field(default_factory=list)


def detect_system_issues() -> List[SystemIssue]:
    """
    Detect stuck states in the project system.

    Evaluates the following conditions:
    A) No active phase exists
    B) More than one phase is marked "in_progress"
    C) A phase is "in_progress" but has:
       - zero tasks AND
       - no next phase unlocked
    D) A task is "in_progress" longer than the safe threshold

    Returns:
        List of SystemIssue objects (empty list if none detected)

    This function is read-only and does NOT mutate data.
    """
    issues = []

    # Get all phases in_progress
    active_phases = list(AdminProjectPhase.objects.filter(status='in_progress'))

    # A) No active phase exists
    if len(active_phases) == 0:
        # Only flag if there are incomplete phases (not all complete)
        incomplete_phases = AdminProjectPhase.objects.exclude(status='complete').exists()
        if incomplete_phases:
            issues.append(SystemIssue(
                issue_type='no_active_phase',
                severity='critical',
                description='No active phase exists. The project system has no phase marked as in_progress.',
                affected_ids=[]
            ))

    # B) More than one phase is marked "in_progress"
    elif len(active_phases) > 1:
        issues.append(SystemIssue(
            issue_type='multiple_active_phases',
            severity='critical',
            description=f'{len(active_phases)} phases are marked as in_progress. Only one phase should be active.',
            affected_ids=[p.pk for p in active_phases]
        ))

    # C) A phase is "in_progress" but has zero tasks AND no next phase unlocked
    for phase in active_phases:
        task_count = AdminTask.objects.filter(phase=phase).count()
        if task_count == 0:
            # Check if there's a next phase that's unlocked (in_progress or complete)
            next_phase = get_next_phase(phase)
            if next_phase is None or next_phase.status == 'not_started':
                issues.append(SystemIssue(
                    issue_type='stuck_phase',
                    severity='warning',
                    description=(
                        f'Phase {phase.phase_number} ("{phase.name}") is in_progress '
                        f'but has zero tasks and no next phase is unlocked.'
                    ),
                    affected_ids=[phase.pk]
                ))

    # D) A task is "in_progress" longer than the safe threshold
    threshold_time = timezone.now() - timedelta(hours=TASK_IN_PROGRESS_THRESHOLD_HOURS)
    stuck_tasks = AdminTask.objects.filter(
        status='in_progress',
        updated_at__lt=threshold_time
    )
    for task in stuck_tasks:
        hours_stuck = (timezone.now() - task.updated_at).total_seconds() / 3600
        issues.append(SystemIssue(
            issue_type='stuck_task',
            severity='warning',
            description=(
                f'Task "{task.title}" (ID: {task.pk}) has been in_progress '
                f'for {hours_stuck:.1f} hours (threshold: {TASK_IN_PROGRESS_THRESHOLD_HOURS}h).'
            ),
            affected_ids=[task.pk]
        ))

    return issues


def reset_active_phase(phase_id: int, created_by: str = 'human') -> AdminProjectPhase:
    """
    Force exactly one phase to "in_progress".

    This is an admin override that:
    - Sets the specified phase to in_progress
    - Sets all other non-complete phases to not_started
    - Logs the override action

    Args:
        phase_id: The ID of the phase to set as active
        created_by: 'human' or 'claude' for activity log

    Returns:
        The phase that was set to in_progress

    Raises:
        AdminProjectPhase.DoesNotExist: If phase_id is invalid
    """
    phase = AdminProjectPhase.objects.get(pk=phase_id)

    # Use the existing override method which handles:
    # - Setting this phase to in_progress
    # - Setting other non-complete phases to not_started
    phase.set_in_progress_with_override()

    # Log the override action
    reference_task = AdminTask.objects.filter(phase=phase).first()
    if reference_task:
        AdminActivityLog.objects.create(
            task=reference_task,
            action=(
                f"[ADMIN OVERRIDE] Active phase reset to Phase {phase.phase_number} "
                f"('{phase.name}'). All other non-complete phases set to not_started."
            ),
            created_by=created_by
        )

    return phase


def force_unblock_task(task_id: int, reason: str, created_by: str = 'human') -> AdminTask:
    """
    Move a task from "blocked" to "ready".

    This is an admin override that:
    - Changes task status from blocked to ready
    - Clears the blocked_reason and blocking_task
    - Logs the override action with the provided reason

    Args:
        task_id: The ID of the task to unblock
        reason: Required explanation of why the task is being force-unblocked
        created_by: 'human' or 'claude' for activity log

    Returns:
        The unblocked task

    Raises:
        AdminTask.DoesNotExist: If task_id is invalid
        ValueError: If task is not in blocked status
        ValueError: If reason is empty
    """
    if not reason or not reason.strip():
        raise ValueError("A reason is required to force-unblock a task.")

    task = AdminTask.objects.get(pk=task_id)

    if task.status != 'blocked':
        raise ValueError(
            f"Cannot force-unblock task. Task is '{task.status}', not 'blocked'."
        )

    old_blocked_reason = task.blocked_reason
    old_blocking_task_id = task.blocking_task_id

    # Update task
    task.status = 'ready'
    task.blocked_reason = ''
    task.blocking_task = None
    task.save()

    # Log the override
    AdminActivityLog.objects.create(
        task=task,
        action=(
            f"[ADMIN OVERRIDE] Task force-unblocked from 'blocked' to 'ready'. "
            f"Previous blocked_reason: '{old_blocked_reason}'. "
            f"Previous blocking_task_id: {old_blocking_task_id}. "
            f"Override reason: {reason}"
        ),
        created_by=created_by
    )

    return task


def recheck_phase_completion(phase_id: int, created_by: str = 'human'):
    """
    Re-run phase completion check safely.

    This is an admin override that:
    - Re-evaluates the phase completion logic
    - If phase is complete, marks it and unlocks next phase
    - Logs the recheck action

    Args:
        phase_id: The ID of the phase to recheck
        created_by: 'human' or 'claude' for activity log

    Returns:
        Tuple of (was_completed: bool, unlocked_phase: AdminProjectPhase or None)

    Raises:
        AdminProjectPhase.DoesNotExist: If phase_id is invalid
    """
    phase = AdminProjectPhase.objects.get(pk=phase_id)

    # Log that we're doing a recheck
    reference_task = AdminTask.objects.filter(phase=phase).first()
    if reference_task:
        AdminActivityLog.objects.create(
            task=reference_task,
            action=(
                f"[ADMIN OVERRIDE] Phase completion recheck initiated for "
                f"Phase {phase.phase_number} ('{phase.name}')."
            ),
            created_by=created_by
        )

    # Run the existing completion check
    was_completed, unlocked_phase = check_and_complete_phase(phase, created_by)

    return was_completed, unlocked_phase


# ==============================================================================
# Phase 11.1 - Preflight Guard & Phase Seeding
# ==============================================================================

@dataclass
class PreflightResult:
    """Result of preflight execution check."""
    success: bool
    errors: List[str] = field(default_factory=list)

    def add_error(self, error: str):
        """Add an error message."""
        self.errors.append(error)
        self.success = False


def preflight_execution_check() -> PreflightResult:
    """
    Verify that valid phase and task data exists before execution.

    Checks:
    1. At least one AdminProjectPhase exists
    2. Exactly one phase has status = "in_progress"
    3. At least one AdminTask exists for the active phase

    Returns:
        PreflightResult with success=True if all checks pass,
        or success=False with detailed error messages if any check fails.

    This function is read-only and does NOT mutate data.
    It does NOT raise exceptions - all failures are returned in the result.
    """
    result = PreflightResult(success=True)

    # Check 1: At least one AdminProjectPhase exists
    phase_count = AdminProjectPhase.objects.count()
    if phase_count == 0:
        result.add_error(
            "No AdminProjectPhase records exist. "
            "Run 'python manage.py seed_admin_project_phases' to initialize phase data."
        )
        return result  # Cannot continue without phases

    # Check 2: Exactly one phase has status = "in_progress"
    active_phases = AdminProjectPhase.objects.filter(status='in_progress')
    active_count = active_phases.count()

    if active_count == 0:
        result.add_error(
            "No active phase found. No phase has status='in_progress'. "
            "Use reset_active_phase() to set an active phase."
        )
        return result  # Cannot continue without active phase
    elif active_count > 1:
        phase_numbers = list(active_phases.values_list('phase_number', flat=True))
        result.add_error(
            f"Multiple active phases found: phases {phase_numbers}. "
            f"Exactly one phase should be 'in_progress'. "
            "Use reset_active_phase() to correct this."
        )
        return result  # Cannot continue with multiple active phases

    # Check 3: At least one AdminTask exists for the active phase
    active_phase = active_phases.first()
    task_count = AdminTask.objects.filter(phase=active_phase).count()

    if task_count == 0:
        result.add_error(
            f"No tasks found for active phase {active_phase.phase_number} "
            f"('{active_phase.name}'). At least one task must exist before execution."
        )
        return result

    return result


def seed_admin_project_phases(created_by: str = 'claude') -> dict:
    """
    Seed the AdminProjectPhase table with phases 1-11 if empty.

    This function is idempotent and safe to run multiple times:
    - If phases already exist, does nothing
    - If table is empty, creates phases 1-11 with minimal names
    - Phase 1 is set to 'in_progress', all others to 'not_started'

    Logs an AdminActivityLog entry when seeding occurs (requires at least
    one task to exist, otherwise logs to console only).

    Args:
        created_by: 'human' or 'claude' for activity log (default: 'claude')

    Returns:
        dict with:
        - 'seeded': bool - True if phases were created, False if already existed
        - 'phase_count': int - Number of phases that now exist
        - 'message': str - Description of what happened
    """
    import os

    existing_count = AdminProjectPhase.objects.count()

    if existing_count > 0:
        return {
            'seeded': False,
            'phase_count': existing_count,
            'message': f'Phases already exist ({existing_count} phases). No seeding performed.'
        }

    # Define the 11 phases with minimal names
    phases_data = [
        (1, 'Phase 1', 'Initial phase setup'),
        (2, 'Phase 2', 'Phase 2 objectives'),
        (3, 'Phase 3', 'Phase 3 objectives'),
        (4, 'Phase 4', 'Phase 4 objectives'),
        (5, 'Phase 5', 'Phase 5 objectives'),
        (6, 'Phase 6', 'Phase 6 objectives'),
        (7, 'Phase 7', 'Phase 7 objectives'),
        (8, 'Phase 8', 'Phase 8 objectives'),
        (9, 'Phase 9', 'Phase 9 objectives'),
        (10, 'Phase 10', 'Phase 10 objectives'),
        (11, 'Phase 11', 'Phase 11 objectives'),
    ]

    created_phases = []
    for phase_number, name, objective in phases_data:
        status = 'in_progress' if phase_number == 1 else 'not_started'
        phase = AdminProjectPhase.objects.create(
            phase_number=phase_number,
            name=name,
            objective=objective,
            status=status
        )
        created_phases.append(phase)

    # Determine environment info for logging
    environment = os.environ.get('RAILWAY_ENVIRONMENT', 'unknown')
    if environment == 'unknown':
        environment = 'development' if os.environ.get('DEBUG', 'False').lower() == 'true' else 'production'

    # Try to create an activity log entry
    # We need a task to log against, but tasks don't exist yet during initial seeding
    # So we log to console if no tasks exist
    log_message = (
        f"[PHASE SEEDING] AdminProjectPhase data initialized with 11 phases. "
        f"Phase 1 set to 'in_progress'. Environment: {environment}."
    )

    # Check if any task exists (from any phase) to log against
    any_task = AdminTask.objects.first()
    if any_task:
        AdminActivityLog.objects.create(
            task=any_task,
            action=log_message,
            created_by=created_by
        )

    return {
        'seeded': True,
        'phase_count': len(created_phases),
        'message': log_message
    }


def ensure_project_phases_exist(max_phase: int = 20) -> dict:
    """
    Ensure AdminProjectPhase records exist for phase_number 1 through max_phase.

    This function is idempotent and safe to run multiple times:
    - For each phase 1 through max_phase:
      - If phase already exists: DO NOT overwrite name, objective, or status
      - If phase does not exist: Create with default name "Phase X" and status based on rules
    - Phase 1 status is set to "in_progress" ONLY IF no phase is currently in_progress
    - All other new phases are set to "not_started"
    - Never deletes phases
    - Never overwrites existing phase data

    This is suitable for production and safe to call on every startup.

    Args:
        max_phase: Maximum phase number to ensure exists (default 20)

    Returns:
        dict with:
        - 'created_count': int - Number of new phases created
        - 'existing_count': int - Number of phases that already existed
        - 'total_count': int - Total phases now in database
        - 'message': str - Description of what happened
    """
    created_count = 0
    existing_count = 0

    # Check if any phase is currently in_progress
    has_active_phase = AdminProjectPhase.objects.filter(status='in_progress').exists()

    for phase_number in range(1, max_phase + 1):
        # Check if phase already exists
        existing_phase = AdminProjectPhase.objects.filter(phase_number=phase_number).first()

        if existing_phase:
            # Phase exists - DO NOT modify it
            existing_count += 1
        else:
            # Phase does not exist - create it
            # Determine status:
            # - Phase 1 gets "in_progress" only if no phase is currently active
            # - All others get "not_started"
            if phase_number == 1 and not has_active_phase:
                status = 'in_progress'
                has_active_phase = True  # Mark that we now have an active phase
            else:
                status = 'not_started'

            AdminProjectPhase.objects.create(
                phase_number=phase_number,
                name=f'Phase {phase_number}',
                objective=f'Phase {phase_number} objectives',
                status=status
            )
            created_count += 1

    total_count = AdminProjectPhase.objects.count()

    if created_count > 0:
        message = f'Created {created_count} new phase(s). {existing_count} phase(s) already existed. Total: {total_count} phases.'
    else:
        message = f'All {existing_count} phases already exist. No new phases created.'

    return {
        'created_count': created_count,
        'existing_count': existing_count,
        'total_count': total_count,
        'message': message
    }
