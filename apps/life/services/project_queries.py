"""Canonical project queries. Mirrors GoalQueries/TaskQueries.

NOTE: Project inherits SoftDeleteManager (apps/core/models.py), whose get_queryset()
filters status='active'. Project OVERRIDES status with active/paused/completed/archived,
so Project.objects returns ONLY active projects. Any non-active query MUST use
Project.all_objects — the same trap as GoalQueries.completed.
"""
from apps.life.models import Project


class ProjectQueries:
    """Canonical, deterministic project queries. No instance state."""

    @classmethod
    def active(cls, user):
        return Project.objects.filter(user=user, status='active')

    @classmethod
    def by_status(cls, user, status):
        return Project.all_objects.filter(user=user, status=status)

    @classmethod
    def completed(cls, user):
        """Completed projects — all_objects required (see module docstring)."""
        return Project.all_objects.filter(user=user, status='completed')
