# ==============================================================================
# File: apps/life/services/task_queries.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Canonical task query service. All consumers (dashboard, CoS
#              context, situation computer, state builder) MUST use these
#              methods instead of ad-hoc QuerySets. This eliminates filter
#              divergence (e.g., status vs completion_status, is_complete
#              vs completion_status='completed').
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-15
# ==============================================================================
"""
Canonical task queries.

Every method returns a QuerySet (not evaluated) so callers can chain
additional filters, slice, or aggregate as needed. The SoftDeleteManager
on Task.objects already filters status='active', so these methods never
add redundant .exclude(status='deleted') or .filter(status='active').

Usage:
    from apps.life.services.task_queries import TaskQueries

    qs = TaskQueries.pending(user)           # all pending tasks
    qs = TaskQueries.overdue(user, today)    # pending + past due_date
    qs = TaskQueries.completed_on(user, dt)  # completed on a specific date
    count = TaskQueries.pending(user).count()
    titles = list(TaskQueries.pending(user).values_list('title', flat=True)[:15])
"""

import logging
from datetime import date

from apps.life.models import Task

logger = logging.getLogger(__name__)


def _user_today(user):
    """The USER's local calendar day, via the one canonical authority.

    USER-LOCAL (2026-07-23): these day queries defaulted to `timezone.localdate()` —
    the SERVER date (settings.TIME_ZONE = UTC) — while their docstrings claimed "user
    timezone". Runtime-proven at 8 PM Pacific (03:00 UTC the next day):
    `due_today(user)` returned TOMORROW's task and `overdue(user)` flagged TODAY's task
    as overdue. Real consumers relied on that default, including the CoS executive
    context (`executive_interpretation`) and `situation_computer`. "Due today" and
    "overdue" are judgements about the USER's calendar, never the server's.
    """
    from apps.core.truth.calendar_day import today as _cal_today
    return _cal_today(user)


class TaskQueries:
    """Canonical, deterministic task queries. No instance state — all classmethods."""

    @classmethod
    def pending(cls, user):
        """Active, non-completed, non-skipped tasks. Matches Organize page default."""
        return Task.objects.filter(
            user=user,
            completion_status='pending',
        )

    @classmethod
    def overdue(cls, user, as_of=None):
        """Pending tasks whose due_date is strictly before `as_of` (default: today)."""
        if as_of is None:
            as_of = _user_today(user)
        return cls.pending(user).filter(
            due_date__isnull=False,
            due_date__lt=as_of,
        )

    @classmethod
    def due_within(cls, user, deadline):
        """Pending tasks due on or before `deadline` (datetime or date)."""
        return cls.pending(user).filter(
            due_date__isnull=False,
            due_date__lte=deadline,
        )

    @classmethod
    def completed_on(cls, user, on_date):
        """Tasks whose COMPLETION TIMESTAMP falls on `on_date` (a HISTORY/momentum concept —
        "what did I finish on this calendar day"). NOT occurrence-scoped: for a recurring
        task this includes a PRIOR occurrence finished within this day's clock window (e.g.
        yesterday's occurrence completed after midnight). Use `completed_due_on` for today's
        EXECUTION state; use this only for history/momentum."""
        return Task.objects.filter(
            user=user,
            completion_status='completed',
            completed_at__date=on_date,
        )

    @classmethod
    def completed_due_on(cls, user, on_date):
        """Today's-execution completion: the OCCURRENCE DUE on `on_date` that is completed —
        i.e. "is today's occurrence done?". Occurrence-scoped by `due_date`, NOT by the
        completion timestamp, so a prior occurrence completed late (in today's clock window)
        is NEVER attributed to today's execution nor allowed to mask today's own occurrence.
        Historical recurring completions belong to their own due-day, not today's."""
        return Task.objects.filter(
            user=user,
            completion_status='completed',
            due_date=on_date,
        )

    @classmethod
    def completed_since(cls, user, since_dt):
        """Tasks completed after a specific datetime."""
        return Task.objects.filter(
            user=user,
            completion_status='completed',
            completed_at__gt=since_dt,
        )

    @classmethod
    def completed_between(cls, user, start_date, end_date):
        """Tasks whose completion timestamp's local date is within
        [start_date, end_date] inclusive (history/momentum)."""
        return Task.objects.filter(
            user=user,
            completion_status='completed',
            completed_at__date__range=(start_date, end_date),
        )

    @classmethod
    def non_negotiable_at_risk(cls, user, skip_threshold=2):
        """Foundational tasks with consecutive skips >= threshold."""
        return cls.pending(user).filter(
            commitment_level='foundational',
            skip_streak__gte=skip_threshold,
        )

    @classmethod
    def due_today(cls, user, as_of=None):
        """Pending tasks due today (user timezone)."""
        if as_of is None:
            as_of = _user_today(user)
        return cls.pending(user).filter(due_date=as_of)

    @classmethod
    def due_tomorrow(cls, user, as_of=None):
        """Pending tasks due tomorrow (user timezone)."""
        if as_of is None:
            as_of = _user_today(user)
        from datetime import timedelta
        return cls.pending(user).filter(due_date=as_of + timedelta(days=1))

    @classmethod
    def due_future(cls, user, as_of=None):
        """Pending tasks due after tomorrow (user timezone)."""
        if as_of is None:
            as_of = _user_today(user)
        from datetime import timedelta
        return cls.pending(user).filter(
            due_date__isnull=False,
            due_date__gt=as_of + timedelta(days=1),
        )

    @classmethod
    def no_due_date(cls, user):
        """Pending tasks with no due date."""
        return cls.pending(user).filter(due_date__isnull=True)

    @classmethod
    def routines_for_date(cls, user, target_date):
        """Routine tasks due on a specific date, ordered by scheduled time."""
        return Task.objects.filter(
            user=user,
            is_routine=True,
            due_date=target_date,
        ).order_by('scheduled_time', 'title')


def refresh_stale_priorities(user):
    """
    Refresh task priorities that have become stale overnight.

    Priority is stored in the DB at save time, so tasks due "soon" yesterday
    still show "soon" today instead of "now". This does a lightweight bulk
    update for the current user's pending tasks whose stored priority
    doesn't match the calculated value.

    Call this before any priority-based query (Organize page, SAE build,
    CoS context, executive briefing) to ensure all consumers see the same
    priority buckets.
    """
    from apps.core.utils import get_user_today

    user_today = get_user_today(user)
    stale_tasks = Task.objects.filter(
        user=user,
        completion_status='pending',
        due_date__isnull=False,
    ).exclude(due_date=None)

    updated = 0
    for task in stale_tasks.only('id', 'due_date', 'priority'):
        new_priority = task.calculate_priority(user_today=user_today)
        if task.priority != new_priority:
            Task.objects.filter(pk=task.pk).update(priority=new_priority)
            updated += 1

    if updated:
        logger.debug("Refreshed %d stale task priorities for user %s", updated, user.pk)
