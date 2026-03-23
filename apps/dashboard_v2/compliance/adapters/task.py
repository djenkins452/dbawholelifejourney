"""
Task domain adapter — evaluates Task model into canonical ComplianceEvent rows.

Task rules:
- due today + completed → completed
- due today + pending → missed (only after day ends, but we mark as overdue intra-day)
- overdue (past due date, still pending) → overdue
- no due date + open → excluded (not_expected)
- skipped → skipped
- recurring expected today → same as due today
- rescheduled → only if rescheduling is explicit

Does NOT count routine tasks (is_routine=True) — those go through the routine adapter.
"""

import logging
from datetime import timedelta

from apps.dashboard_v2.compliance.constants import (
    ACTUAL_COMPLETED,
    ACTUAL_NONE,
    ACTUAL_OPEN,
    ACTUAL_SKIPPED,
    BUCKET_TASK,
    DOMAIN_TASK,
    FINAL_COMPLETED,
    FINAL_MISSED,
    FINAL_NOT_EXPECTED,
    FINAL_OVERDUE,
    FINAL_SKIPPED,
    REASON_COMPLETED_TODAY,
    REASON_EXPLICIT_SKIP,
    REASON_NO_DUE_DATE,
    REASON_NO_LOG,
    REASON_ON_TIME,
    REASON_OVERDUE_DUE_DATE,
    SOURCE_TASK,
)

logger = logging.getLogger(__name__)


def evaluate_task(user, start_date, end_date):
    """
    Produce ComplianceEvent dicts for task domain.

    Evaluates non-routine tasks with due dates in the range,
    plus overdue tasks from before the range.
    """
    try:
        from apps.life.models import Task

        # Tasks due within the evaluation window
        due_tasks = Task.objects.filter(
            user=user,
            is_routine=False,
            due_date__gte=start_date,
            due_date__lte=end_date,
        ).exclude(status="deleted")

        events = []
        for task in due_tasks:
            events.append(_build_task_event(user, task, task.due_date))

        # Also include overdue tasks (due before start_date, still pending)
        overdue_tasks = Task.objects.filter(
            user=user,
            is_routine=False,
            due_date__lt=start_date,
            completion_status="pending",
        ).exclude(status="deleted")

        for task in overdue_tasks:
            # Show on the first day of the window as overdue
            events.append(_build_overdue_event(user, task, start_date))

        return events
    except Exception:
        logger.error("Task compliance adapter failed", exc_info=True)
        return []


def _build_task_event(user, task, event_date):
    """Build a ComplianceEvent dict for a task due on event_date."""
    label = task.title or "Untitled Task"

    base = {
        "user": user,
        "event_date": event_date,
        "domain": DOMAIN_TASK,
        "scoring_bucket": BUCKET_TASK,
        "item_type": "Task",
        "item_id": task.id,
        "item_label": label,
        "expected_at": task.scheduled_time if hasattr(task, "scheduled_time") else None,
        "expected": True,
        "source_system": SOURCE_TASK,
    }

    if task.completion_status == "completed":
        base.update({
            "actual_status": ACTUAL_COMPLETED,
            "final_status": FINAL_COMPLETED,
            "reason_code": REASON_COMPLETED_TODAY,
            "reason_detail": {"completed_at": str(task.completed_at) if task.completed_at else None},
        })
    elif task.completion_status == "skipped":
        base.update({
            "actual_status": ACTUAL_SKIPPED,
            "final_status": FINAL_SKIPPED,
            "reason_code": REASON_EXPLICIT_SKIP,
            "reason_detail": {},
        })
    else:
        # Still pending
        base.update({
            "actual_status": ACTUAL_OPEN,
            "final_status": FINAL_MISSED,
            "reason_code": REASON_NO_LOG,
            "reason_detail": {},
        })

    return base


def _build_overdue_event(user, task, display_date):
    """Build a ComplianceEvent dict for an overdue task."""
    label = task.title or "Untitled Task"

    return {
        "user": user,
        "event_date": display_date,
        "domain": DOMAIN_TASK,
        "scoring_bucket": BUCKET_TASK,
        "item_type": "Task",
        "item_id": task.id,
        "item_label": label,
        "expected_at": None,
        "expected": True,
        "source_system": SOURCE_TASK,
        "actual_status": ACTUAL_OPEN,
        "final_status": FINAL_OVERDUE,
        "reason_code": REASON_OVERDUE_DUE_DATE,
        "reason_detail": {"original_due_date": str(task.due_date)},
    }
