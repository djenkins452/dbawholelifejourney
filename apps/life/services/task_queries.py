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

from datetime import date

from apps.life.models import Task


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
            from django.utils import timezone
            as_of = timezone.localdate()
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
        """Tasks completed on a specific date."""
        return Task.objects.filter(
            user=user,
            completion_status='completed',
            completed_at__date=on_date,
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
    def non_negotiable_at_risk(cls, user, skip_threshold=2):
        """Non-negotiable tasks with consecutive skips >= threshold."""
        return cls.pending(user).filter(
            commitment_level='non_negotiable',
            skip_streak__gte=skip_threshold,
        )

    @classmethod
    def routines_for_date(cls, user, target_date):
        """Routine tasks due on a specific date, ordered by scheduled time."""
        return Task.objects.filter(
            user=user,
            is_routine=True,
            due_date=target_date,
        ).order_by('scheduled_time', 'title')
