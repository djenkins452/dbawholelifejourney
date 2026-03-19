"""
Regression tests for _build_data_state_snapshot() in cos_context.py.

Verifies that the AUTHORITATIVE DATA STATE snapshot includes deterministic
completed-task titles and enforces temporal boundaries — only tasks completed
TODAY appear, never historical completions.
"""

from datetime import timedelta

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.users.models import User, TermsAcceptance


class DataStateSnapshotCompletedTasksTest(TestCase):
    """Ensure completed-today task titles are deterministic and temporally correct."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="snapshot_test@test.com", password="testpass123"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

    def _create_task(self, title, completed_at=None):
        """Helper: create a Task, optionally marking it completed at a specific time."""
        from apps.life.models import Task

        task = Task.objects.create(
            user=self.user,
            title=title,
            completion_status='pending',
        )
        if completed_at:
            task.completion_status = 'completed'
            task.completed_at = completed_at
            task.save(update_fields=['completion_status', 'completed_at'])
        return task

    def test_only_today_tasks_appear_in_snapshot(self):
        """Historical completions must NEVER appear in the authoritative snapshot."""
        from apps.core.ai_orchestrator.cos_context import _build_data_state_snapshot

        now = timezone.now()
        today = now
        march_1 = now - timedelta(days=13)  # simulate old completion

        # Task A: completed today
        self._create_task("Prayer Time", completed_at=today)
        # Task B: completed March 1 (old) — must NOT appear
        self._create_task("Move Bins and Boxes in garage", completed_at=march_1)

        snapshot = _build_data_state_snapshot(self.user)

        # Task A should appear
        self.assertIn("Prayer Time", snapshot)
        # Task B must NOT appear
        self.assertNotIn("Move Bins and Boxes in garage", snapshot)

    def test_snapshot_includes_titles_when_tasks_completed(self):
        """When tasks are completed today, their titles must appear in the snapshot."""
        from apps.core.ai_orchestrator.cos_context import _build_data_state_snapshot

        now = timezone.now()
        self._create_task("Morning Workout", completed_at=now)
        self._create_task("Review Budget", completed_at=now)

        snapshot = _build_data_state_snapshot(self.user)

        self.assertIn("COMPLETED TODAY", snapshot)
        self.assertIn("Morning Workout", snapshot)
        self.assertIn("Review Budget", snapshot)
        self.assertIn("completed_tasks_today: 2", snapshot)

    def test_snapshot_includes_grounding_rule(self):
        """The no-inference guardrail must be present when completed tasks exist."""
        from apps.core.ai_orchestrator.cos_context import _build_data_state_snapshot

        self._create_task("Prayer Time", completed_at=timezone.now())

        snapshot = _build_data_state_snapshot(self.user)

        # Execution truth rules prevent Beth from inferring completion
        self.assertIn("EXECUTION TRUTH RULE", snapshot)
        self.assertIn("NEVER infer", snapshot)

    def test_snapshot_no_titles_section_when_zero_completed(self):
        """When no tasks are completed today, no title section should appear."""
        from apps.core.ai_orchestrator.cos_context import _build_data_state_snapshot

        # Only a pending task — not completed
        self._create_task("Pending Task")

        snapshot = _build_data_state_snapshot(self.user)

        self.assertNotIn("COMPLETED TASKS TODAY", snapshot)
        self.assertIn("completed_tasks_today: 0", snapshot)

    def test_snapshot_count_matches_title_list(self):
        """The count and title list must agree — both from the same query."""
        from apps.core.ai_orchestrator.cos_context import _build_data_state_snapshot

        now = timezone.now()
        self._create_task("Task A", completed_at=now)
        self._create_task("Task B", completed_at=now)
        self._create_task("Task C", completed_at=now)
        # Old task — must not inflate count or titles
        self._create_task("Old Task", completed_at=now - timedelta(days=30))

        snapshot = _build_data_state_snapshot(self.user)

        self.assertIn("completed_tasks_today: 3", snapshot)
        self.assertIn("Task A", snapshot)
        self.assertIn("Task B", snapshot)
        self.assertIn("Task C", snapshot)
        self.assertNotIn("Old Task", snapshot)
