"""
Centralized Completion Service — SINGLE SOURCE OF TRUTH.

Every system that needs to know "is X completed?" MUST call this service.
No direct ORM .exists() checks, no inference, no time-based completion.

Completion is determined ONLY by domain truth:
  - Workout: WorkoutQueries.is_completed_on() (completed_at, exercises, or duration)
  - Journal: JournalQueries.has_entry_on() (entry exists)
  - Faith:   FaithQueries (reading progress or faith task completed)
  - Task:    completion_status == 'completed'
  - Routine:  RoutineLog with log_status in (completed, completed_late)
  - Medication: IntakeLog with log_status == 'taken' for all scheduled doses
  - Nutrition:  FoodEntry exists for date (at least one food logged)

INVARIANTS (enforced at runtime):
  - Completion NEVER derived from time
  - Completion NEVER derived from signals
  - Completion NEVER cascaded from group/parent
  - Completion NEVER inferred from partial existence
"""
import logging
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)


# =========================================================================
# Domain Completion Checks — Canonical API
# =========================================================================


def is_workout_complete(user, target_date: date) -> bool:
    """
    Is the user's workout complete on this date?

    Truth: WorkoutSession with completed_at set, exercises logged,
    or duration_minutes set. A merely-started session is NOT complete.
    """
    try:
        from apps.health.services.workout_queries import WorkoutQueries
        return WorkoutQueries.is_completed_on(user, target_date)
    except ImportError:
        return False


def is_journal_complete(user, target_date: date) -> bool:
    """
    Has the user journaled on this date?

    Truth: JournalEntry exists for user+date.
    """
    try:
        from apps.journal.services.journal_queries import JournalQueries
        return JournalQueries.has_entry_on(user, target_date)
    except ImportError:
        return False


def is_bible_reading_complete(user, target_date: date) -> bool:
    """
    Has the user completed Bible reading on this date?

    Truth: UserReadingProgress with is_completed=True for date.
    """
    try:
        from apps.faith.services.faith_queries import FaithQueries
        return FaithQueries.has_reading_on(user, target_date)
    except ImportError:
        return False


def is_prayer_complete(user, target_date: date) -> bool:
    """
    Has the user completed prayer on this date?

    Truth: Faith-domain Task with completion_status='completed' for date,
    OR routine bridge from execution truth engine.
    """
    try:
        from apps.core.execution.execution_truth_engine import get_execution_truth
        truth = get_execution_truth(user, target_date)
        return truth['domains']['faith'].get('prayer_completed', False)
    except Exception:
        return False


def is_medication_complete(user, target_date: date) -> bool:
    """
    Are all scheduled medications taken on this date?

    Truth: Every scheduled IntakeLog has log_status='taken' for all
    active intake schedules due on this date.
    """
    try:
        from apps.core.execution.execution_truth_engine import get_execution_truth
        truth = get_execution_truth(user, target_date)
        return truth.get('medications', {}).get('all_taken', False)
    except Exception:
        return False


def is_nutrition_logged(user, target_date: date) -> bool:
    """
    Has the user logged any food on this date?

    Truth: FoodEntry exists for user+date.
    """
    try:
        from apps.health.models import FoodEntry
        return FoodEntry.objects.filter(
            user=user, logged_date=target_date,
        ).exists()
    except ImportError:
        return False


def is_task_complete(task) -> bool:
    """
    Is this specific task complete?

    Truth: task.completion_status == 'completed'.
    """
    return getattr(task, 'completion_status', '') == 'completed'


def is_routine_item_complete(user, schedule_id: int, target_date: date) -> bool:
    """
    Is a specific routine schedule item complete on this date?

    Truth: RoutineLog exists with log_status in (completed, completed_late).
    """
    try:
        from apps.life.models import RoutineLog
        return RoutineLog.objects.filter(
            user=user,
            schedule_id=schedule_id,
            scheduled_date=target_date,
            log_status__in=['completed', 'completed_late'],
        ).exists()
    except ImportError:
        return False


# =========================================================================
# Invariant Enforcement — Runtime Protection
# =========================================================================


def validate_completion_invariants(user, target_date: date) -> list:
    """
    Check for impossible states where completion flags disagree with
    underlying data. Returns list of violations (empty = clean).

    This should be called during check-ins, briefings, and signal
    aggregation to catch regressions early.

    Each violation is a dict: {domain, message, severity}
    """
    violations = []

    try:
        from apps.core.execution.execution_truth_engine import get_execution_truth
        truth = get_execution_truth(user, target_date)
    except Exception as e:
        logger.warning("Completion invariant check failed: %s", e)
        return [{'domain': 'system', 'message': str(e), 'severity': 'error'}]

    # Workout invariant: if execution truth says complete, WorkoutSession must exist
    workout_truth = truth['domains']['workout']['completed']
    if workout_truth:
        workout_real = is_workout_complete(user, target_date)
        if not workout_real:
            v = {
                'domain': 'workout',
                'message': (
                    f"INVARIANT VIOLATION: Execution truth says workout complete "
                    f"but WorkoutQueries.is_completed_on() returns False"
                ),
                'severity': 'critical',
            }
            violations.append(v)
            logger.critical(
                "COMPLETION_INVARIANT_VIOLATION user=%s date=%s domain=workout",
                user.id, target_date,
            )

    # Journal invariant
    journal_truth = truth['domains']['journal']['completed']
    if journal_truth:
        journal_real = is_journal_complete(user, target_date)
        if not journal_real:
            v = {
                'domain': 'journal',
                'message': (
                    f"INVARIANT VIOLATION: Execution truth says journal complete "
                    f"but JournalQueries.has_entry_on() returns False"
                ),
                'severity': 'critical',
            }
            violations.append(v)
            logger.critical(
                "COMPLETION_INVARIANT_VIOLATION user=%s date=%s domain=journal",
                user.id, target_date,
            )

    # Medication invariant: if truth says all_taken, verify
    meds = truth.get('medications', {})
    if meds.get('all_taken') and meds.get('expected', 0) > 0:
        taken = meds.get('taken', 0)
        expected = meds.get('expected', 0)
        if taken < expected:
            v = {
                'domain': 'medication',
                'message': (
                    f"INVARIANT VIOLATION: all_taken=True but "
                    f"taken={taken} < expected={expected}"
                ),
                'severity': 'critical',
            }
            violations.append(v)
            logger.critical(
                "COMPLETION_INVARIANT_VIOLATION user=%s date=%s domain=medication "
                "taken=%d expected=%d",
                user.id, target_date, taken, expected,
            )

    # Routine invariant: completed count should not exceed total
    routines = truth.get('routines', {})
    completed = routines.get('completed', 0)
    total = routines.get('total', 0)
    if completed > total and total > 0:
        v = {
            'domain': 'routine',
            'message': (
                f"INVARIANT VIOLATION: routine completed={completed} > total={total}"
            ),
            'severity': 'warning',
        }
        violations.append(v)
        logger.warning(
            "COMPLETION_INVARIANT_VIOLATION user=%s date=%s domain=routine "
            "completed=%d > total=%d",
            user.id, target_date, completed, total,
        )

    return violations
