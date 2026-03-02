# ==============================================================================
# File: test_task_end_time.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Tests for task end_time (scheduled_end_time) support across
#              intent schema, action handlers, and mutate_task.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-02
# ==============================================================================

from datetime import date, time

from django.test import TestCase
from django.utils import timezone

from apps.ai.action_handlers import ActionHandler
from apps.ai.intents.life_intents import LIFE_INTENT_TOOLS
from apps.life.models import Task
from apps.users.models import User


class TestCreateTaskEndTimeSchema(TestCase):
    """Verify the create_task intent schema includes end_time."""

    def _get_schema(self, name):
        for tool in LIFE_INTENT_TOOLS:
            if tool["function"]["name"] == name:
                return tool["function"]["parameters"]["properties"]
        self.fail(f"Tool {name} not found in LIFE_INTENT_TOOLS")

    def test_create_task_schema_has_end_time(self):
        props = self._get_schema("create_task")
        self.assertIn("end_time", props)
        self.assertEqual(props["end_time"]["type"], "string")

    def test_mutate_task_schema_has_new_end_time(self):
        props = self._get_schema("mutate_task")
        self.assertIn("new_end_time", props)
        self.assertEqual(props["new_end_time"]["type"], "string")

    def test_create_routine_task_already_has_end_time(self):
        """Routine tasks already supported end_time — verify it didn't regress."""
        props = self._get_schema("create_routine_task")
        self.assertIn("end_time", props)


class TestCreateTaskEndTimeHandler(TestCase):
    """Test handle_create_task with end_time parameter."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='endtime@example.com',
            password='testpass123',
            first_name='Test',
        )
        prefs = self.user.preferences
        prefs.ai_enabled = True
        prefs.ai_data_consent = True
        prefs.personal_assistant_enabled = True
        prefs.personal_assistant_consent = True
        prefs.save()
        self.handler = ActionHandler(self.user)

    def test_create_task_with_time_range(self):
        """'add a task today at 5pm - 6pm' should store both times."""
        result = self.handler.handle_create_task(
            title="Gather Tax Papers",
            due_date="today",
            scheduled_time="17:00",
            end_time="18:00",
        )
        self.assertTrue(result.success)
        task = Task.objects.get(user=self.user, title="Gather Tax Papers")
        self.assertEqual(task.scheduled_time, time(17, 0))
        self.assertEqual(task.scheduled_end_time, time(18, 0))
        self.assertEqual(task.estimated_duration_minutes, 60)

    def test_create_task_time_range_message_shows_both(self):
        """Confirmation message should show '5:00 PM – 6:00 PM' format."""
        result = self.handler.handle_create_task(
            title="Study Time",
            due_date="today",
            scheduled_time="17:00",
            end_time="18:00",
        )
        self.assertTrue(result.success)
        self.assertIn("–", result.message)
        self.assertIn("5:00 PM", result.message)
        self.assertIn("6:00 PM", result.message)

    def test_create_task_without_end_time_still_works(self):
        """Existing behavior (no end_time) should not regress."""
        result = self.handler.handle_create_task(
            title="Quick Errand",
            due_date="today",
            scheduled_time="10:00",
            duration_minutes=30,
        )
        self.assertTrue(result.success)
        task = Task.objects.get(user=self.user, title="Quick Errand")
        self.assertEqual(task.scheduled_time, time(10, 0))
        self.assertIsNone(task.scheduled_end_time)
        self.assertEqual(task.estimated_duration_minutes, 30)

    def test_create_task_end_time_overrides_duration(self):
        """When both end_time and duration_minutes are provided, end_time wins for duration calc."""
        result = self.handler.handle_create_task(
            title="Meeting",
            due_date="today",
            scheduled_time="14:00",
            end_time="15:30",
            # duration_minutes NOT provided — should be auto-computed to 90
        )
        self.assertTrue(result.success)
        task = Task.objects.get(user=self.user, title="Meeting")
        self.assertEqual(task.estimated_duration_minutes, 90)

    def test_create_task_no_time(self):
        """Task with no time should not set scheduled_end_time."""
        result = self.handler.handle_create_task(title="Buy groceries")
        self.assertTrue(result.success)
        task = Task.objects.get(user=self.user, title="Buy groceries")
        self.assertIsNone(task.scheduled_time)
        self.assertIsNone(task.scheduled_end_time)


class TestMutateTaskEndTime(TestCase):
    """Test handle_mutate_task with new_end_time parameter."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='mutateend@example.com',
            password='testpass123',
            first_name='Test',
        )
        prefs = self.user.preferences
        prefs.ai_enabled = True
        prefs.ai_data_consent = True
        prefs.personal_assistant_enabled = True
        prefs.personal_assistant_consent = True
        prefs.save()
        self.handler = ActionHandler(self.user)

        # Create a task with a time range
        self.task = Task.objects.create(
            user=self.user,
            title="Tax Prep",
            due_date=timezone.now().date(),
            scheduled_time=time(17, 0),
            scheduled_end_time=time(18, 0),
            estimated_duration_minutes=60,
        )

    def test_mutate_task_update_end_time(self):
        """Updating end_time should persist to scheduled_end_time."""
        result = self.handler.handle_mutate_task(
            action="update",
            task_query="Tax Prep",
            new_end_time="19:00",
        )
        self.assertTrue(result.success)
        self.task.refresh_from_db()
        self.assertEqual(self.task.scheduled_end_time, time(19, 0))

    def test_mutate_task_update_both_times(self):
        """Updating both start and end time."""
        result = self.handler.handle_mutate_task(
            action="update",
            task_query="Tax Prep",
            new_scheduled_time="16:00",
            new_end_time="17:30",
        )
        self.assertTrue(result.success)
        self.task.refresh_from_db()
        self.assertEqual(self.task.scheduled_time, time(16, 0))
        self.assertEqual(self.task.scheduled_end_time, time(17, 30))
        # Confirm change description includes range
        self.assertIn("–", result.message)

    def test_mutate_task_invalid_end_time(self):
        """Invalid end_time format should return error."""
        result = self.handler.handle_mutate_task(
            action="update",
            task_query="Tax Prep",
            new_end_time="not-a-time",
        )
        self.assertFalse(result.success)
        self.assertIn("couldn't understand", result.message)


class TestTaskSchemaModelParity(TestCase):
    """Verify that key Task model time fields are covered by intent schemas."""

    def test_model_time_fields_in_create_schema(self):
        """Task model's scheduled_time and scheduled_end_time must map to schema fields."""
        schema = None
        for tool in LIFE_INTENT_TOOLS:
            if tool["function"]["name"] == "create_task":
                schema = tool["function"]["parameters"]["properties"]
                break
        self.assertIsNotNone(schema, "create_task schema not found")
        # scheduled_time → scheduled_time
        self.assertIn("scheduled_time", schema)
        # scheduled_end_time → end_time
        self.assertIn("end_time", schema)
        # estimated_duration_minutes → duration_minutes
        self.assertIn("duration_minutes", schema)
