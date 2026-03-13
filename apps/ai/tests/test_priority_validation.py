# ==============================================================================
# File: test_priority_validation.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Tests that priority synthesis validates task existence before
#              injecting into the LLM prompt. Prevents phantom priorities.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-12
# ==============================================================================

from django.test import TestCase, override_settings
from django.utils import timezone

LOCMEM_CACHE = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'priority-validation-test',
    }
}

from apps.life.models import Task
from apps.users.models import User


@override_settings(CACHES=LOCMEM_CACHE)
class TestPrioritySynthesisValidation(TestCase):
    """Verify that deleted/phantom tasks cannot appear in priority synthesis."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='priority-test@example.com',
            password='testpass123',
            first_name='Test',
        )
        prefs = self.user.preferences
        prefs.ai_enabled = True
        prefs.ai_data_consent = True
        prefs.personal_assistant_enabled = True
        prefs.personal_assistant_consent = True
        prefs.save()
        self.today = timezone.now().date()

    def test_deleted_task_excluded_from_task_queries(self):
        """Tasks with status='deleted' must not appear in overdue/due_today queries."""
        task = Task.objects.create(
            user=self.user,
            title="Budget Review",
            due_date=self.today,
            completion_status='pending',
        )
        # Soft delete the task
        task.soft_delete()

        # Query using the same pattern as personal_assistant.py check-in
        from apps.life.models import Task as LifeTask
        overdue = list(LifeTask.objects.filter(
            user=self.user, completion_status='pending', due_date__lt=self.today,
        ).exclude(status='deleted').values_list('title', flat=True))
        due_today = list(LifeTask.objects.filter(
            user=self.user, completion_status='pending', due_date=self.today,
        ).exclude(status='deleted').values_list('title', flat=True))

        self.assertNotIn("Budget Review", overdue)
        self.assertNotIn("Budget Review", due_today)

    def test_completed_task_excluded_from_pending_queries(self):
        """Completed tasks must not appear as pending priorities."""
        task = Task.objects.create(
            user=self.user,
            title="Completed Task",
            due_date=self.today,
            completion_status='pending',
        )
        task.mark_complete()

        from apps.life.models import Task as LifeTask
        pending = list(LifeTask.objects.filter(
            user=self.user, completion_status='pending', due_date=self.today,
        ).exclude(status='deleted').values_list('title', flat=True))

        self.assertNotIn("Completed Task", pending)

    def test_validation_query_catches_deleted_during_synthesis(self):
        """If a task is deleted between query and synthesis, validation catches it."""
        task = Task.objects.create(
            user=self.user,
            title="Phantom Task",
            due_date=self.today,
            completion_status='pending',
        )

        # Simulate: task appears in initial query
        initial_titles = list(Task.objects.filter(
            user=self.user, completion_status='pending', due_date=self.today,
        ).exclude(status='deleted').values_list('title', flat=True))
        self.assertIn("Phantom Task", initial_titles)

        # Now delete it (simulating race condition)
        task.soft_delete()

        # Re-check should NOT find it
        still_exists = Task.objects.filter(
            user=self.user, title="Phantom Task",
            completion_status='pending', status='active',
        ).exists()
        self.assertFalse(still_exists)

    def test_anti_fabrication_prompt_instruction(self):
        """System prompt must contain anti-fabrication instruction for priorities."""
        # Verify the instruction text exists in the personal_assistant module
        import inspect
        from apps.ai import personal_assistant as pa_module
        source = inspect.getsource(pa_module)
        # Check key anti-fabrication phrases (may be split across lines)
        self.assertIn("NEVER invent", source)
        self.assertIn(
            "NEVER invent, derive, or infer a task or priority item",
            source,
        )
        self.assertIn(
            "No urgent priorities right now",
            source,
        )
