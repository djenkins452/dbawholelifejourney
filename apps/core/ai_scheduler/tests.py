"""
ISE — Tests for the Intelligence Scheduler Engine.

Tests cover:
- ScheduledIntelligenceTask model
- Scheduler registry
- Scheduler engine (cycle execution)
- Task runners (DBE, GLOE, PGE wrappers)
- Management command
"""

from datetime import timedelta
from io import StringIO
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.core.ai_scheduler.scheduler_engine import (
    _ensure_task_records,
    _execute_task,
    run_scheduler_cycle,
)
from apps.core.ai_scheduler.scheduler_models import ScheduledIntelligenceTask
from apps.core.ai_scheduler.scheduler_registry import (
    SCHEDULED_TASKS,
    get_registered_tasks,
    get_task_function,
)
from apps.core.ai_scheduler.scheduler_runner import (
    run_daily_briefings,
    run_guidance_refresh,
    run_learning_profile_updates,
)
from apps.users.models import User


def _create_test_user(email="isetest@example.com", ai_enabled=True):
    """Create a test user with required setup."""
    from apps.users.models import TermsAcceptance

    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.ai_enabled = ai_enabled
    user.preferences.save()
    return user


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------


class ScheduledIntelligenceTaskModelTest(TestCase):
    """Tests for ScheduledIntelligenceTask model."""

    def test_create_task(self):
        task = ScheduledIntelligenceTask.objects.create(
            task_name="test_task",
            run_interval_seconds=3600,
        )
        self.assertEqual(task.task_name, "test_task")
        self.assertEqual(task.last_status, "pending")
        self.assertTrue(task.is_active)

    def test_str_representation(self):
        task = ScheduledIntelligenceTask.objects.create(
            task_name="my_task",
            run_interval_seconds=86400,
        )
        self.assertIn("my_task", str(task))
        self.assertIn("pending", str(task))

    def test_unique_task_name(self):
        ScheduledIntelligenceTask.objects.create(task_name="unique_task")
        with self.assertRaises(Exception):
            ScheduledIntelligenceTask.objects.create(task_name="unique_task")

    def test_is_due_when_next_run_in_past(self):
        task = ScheduledIntelligenceTask.objects.create(
            task_name="due_task",
            next_run_at=timezone.now() - timedelta(minutes=5),
        )
        self.assertTrue(task.is_due)

    def test_not_due_when_next_run_in_future(self):
        task = ScheduledIntelligenceTask.objects.create(
            task_name="future_task",
            next_run_at=timezone.now() + timedelta(hours=1),
        )
        self.assertFalse(task.is_due)

    def test_not_due_when_inactive(self):
        task = ScheduledIntelligenceTask.objects.create(
            task_name="inactive_task",
            next_run_at=timezone.now() - timedelta(minutes=5),
            is_active=False,
        )
        self.assertFalse(task.is_due)

    def test_default_values(self):
        task = ScheduledIntelligenceTask.objects.create(task_name="defaults")
        self.assertEqual(task.run_count, 0)
        self.assertEqual(task.last_error, "")
        self.assertEqual(task.description, "")


# ---------------------------------------------------------------------------
# Registry Tests
# ---------------------------------------------------------------------------


class SchedulerRegistryTest(TestCase):
    """Tests for the scheduler registry."""

    def test_registered_tasks_exist(self):
        tasks = get_registered_tasks()
        self.assertIn("generate_daily_briefings", tasks)
        self.assertIn("update_learning_profiles", tasks)
        self.assertIn("refresh_guidance", tasks)

    def test_registered_tasks_have_required_fields(self):
        for name, config in SCHEDULED_TASKS.items():
            self.assertIn("function_path", config, f"{name} missing function_path")
            self.assertIn("interval_seconds", config, f"{name} missing interval_seconds")
            self.assertGreater(config["interval_seconds"], 0)

    def test_get_task_function_valid(self):
        func = get_task_function("generate_daily_briefings")
        self.assertIsNotNone(func)
        self.assertTrue(callable(func))

    def test_get_task_function_unknown(self):
        func = get_task_function("nonexistent_task")
        self.assertIsNone(func)

    def test_get_registered_tasks_returns_copy(self):
        tasks = get_registered_tasks()
        tasks["new_key"] = "test"
        # Original should not be modified
        self.assertNotIn("new_key", SCHEDULED_TASKS)


# ---------------------------------------------------------------------------
# Engine Tests
# ---------------------------------------------------------------------------


class EnsureTaskRecordsTest(TestCase):
    """Tests for _ensure_task_records."""

    def test_creates_records_for_registered_tasks(self):
        _ensure_task_records()
        for task_name in SCHEDULED_TASKS:
            self.assertTrue(
                ScheduledIntelligenceTask.objects.filter(task_name=task_name).exists()
            )

    def test_idempotent(self):
        _ensure_task_records()
        count1 = ScheduledIntelligenceTask.objects.count()
        _ensure_task_records()
        count2 = ScheduledIntelligenceTask.objects.count()
        self.assertEqual(count1, count2)

    def test_preserves_existing_records(self):
        ScheduledIntelligenceTask.objects.create(
            task_name="generate_daily_briefings",
            run_interval_seconds=999,
            description="Custom",
        )
        _ensure_task_records()
        task = ScheduledIntelligenceTask.objects.get(task_name="generate_daily_briefings")
        # Existing record should not be overwritten
        self.assertEqual(task.run_interval_seconds, 999)


class ExecuteTaskTest(TestCase):
    """Tests for _execute_task."""

    def test_successful_execution(self):
        task = ScheduledIntelligenceTask.objects.create(
            task_name="generate_daily_briefings",
            next_run_at=timezone.now() - timedelta(minutes=5),
        )
        now = timezone.now()

        with patch(
            "apps.core.ai_scheduler.scheduler_engine.get_task_function"
        ) as mock_get:
            mock_func = MagicMock(return_value={"generated": 1})
            mock_get.return_value = mock_func

            result = _execute_task(task, now)

        self.assertTrue(result)
        task.refresh_from_db()
        self.assertEqual(task.last_status, "success")
        self.assertEqual(task.run_count, 1)
        self.assertEqual(task.last_error, "")

    def test_failed_execution(self):
        task = ScheduledIntelligenceTask.objects.create(
            task_name="generate_daily_briefings",
            next_run_at=timezone.now() - timedelta(minutes=5),
        )
        now = timezone.now()

        with patch(
            "apps.core.ai_scheduler.scheduler_engine.get_task_function"
        ) as mock_get:
            mock_func = MagicMock(side_effect=RuntimeError("Engine crashed"))
            mock_get.return_value = mock_func

            result = _execute_task(task, now)

        self.assertFalse(result)
        task.refresh_from_db()
        self.assertEqual(task.last_status, "failed")
        self.assertIn("Engine crashed", task.last_error)
        # Still advances next_run_at to prevent infinite loops
        self.assertGreater(task.next_run_at, now)

    def test_missing_function(self):
        task = ScheduledIntelligenceTask.objects.create(
            task_name="nonexistent_task",
            next_run_at=timezone.now() - timedelta(minutes=5),
        )
        now = timezone.now()

        result = _execute_task(task, now)

        self.assertFalse(result)
        task.refresh_from_db()
        self.assertEqual(task.last_status, "failed")
        self.assertIn("No function registered", task.last_error)

    def test_next_run_at_advanced(self):
        task = ScheduledIntelligenceTask.objects.create(
            task_name="generate_daily_briefings",
            run_interval_seconds=3600,
            next_run_at=timezone.now() - timedelta(minutes=5),
        )
        now = timezone.now()

        with patch(
            "apps.core.ai_scheduler.scheduler_engine.get_task_function"
        ) as mock_get:
            mock_get.return_value = MagicMock(return_value={})
            _execute_task(task, now)

        task.refresh_from_db()
        expected_next = now + timedelta(seconds=3600)
        self.assertAlmostEqual(
            task.next_run_at.timestamp(),
            expected_next.timestamp(),
            delta=1,
        )


class RunSchedulerCycleTest(TestCase):
    """Tests for run_scheduler_cycle."""

    def test_executes_due_tasks(self):
        with patch(
            "apps.core.ai_scheduler.scheduler_engine._execute_task"
        ) as mock_exec:
            mock_exec.return_value = True
            _ensure_task_records()

            # Make all tasks due
            ScheduledIntelligenceTask.objects.update(
                next_run_at=timezone.now() - timedelta(minutes=1)
            )

            result = run_scheduler_cycle()

        self.assertGreater(result["executed"], 0)

    def test_skips_future_tasks(self):
        _ensure_task_records()
        # Push all tasks into the future
        ScheduledIntelligenceTask.objects.update(
            next_run_at=timezone.now() + timedelta(hours=24)
        )

        with patch(
            "apps.core.ai_scheduler.scheduler_engine._execute_task"
        ) as mock_exec:
            result = run_scheduler_cycle()

        mock_exec.assert_not_called()
        self.assertEqual(result["executed"], 0)
        self.assertGreater(result["skipped"], 0)

    def test_skips_inactive_tasks(self):
        _ensure_task_records()
        ScheduledIntelligenceTask.objects.update(is_active=False)

        with patch(
            "apps.core.ai_scheduler.scheduler_engine._execute_task"
        ) as mock_exec:
            result = run_scheduler_cycle()

        mock_exec.assert_not_called()

    def test_returns_result_counts(self):
        result = run_scheduler_cycle()
        self.assertIn("executed", result)
        self.assertIn("skipped", result)
        self.assertIn("failed", result)


# ---------------------------------------------------------------------------
# Runner Tests
# ---------------------------------------------------------------------------


class RunDailyBriefingsTest(TestCase):
    """Tests for run_daily_briefings runner."""

    def test_calls_dbe_for_ai_users(self):
        user = _create_test_user()

        with patch(
            "apps.core.ai_scheduler.scheduler_runner.run_daily_briefings.__module__",
        ):
            pass

        with patch(
            "apps.core.ai_briefing.briefing_engine.generate_daily_briefing"
        ) as mock_gen:
            mock_gen.return_value = MagicMock()
            result = run_daily_briefings()

        self.assertEqual(result["generated"], 1)
        mock_gen.assert_called_once_with(user)

    def test_skips_non_ai_users(self):
        _create_test_user(email="noai@example.com", ai_enabled=False)

        with patch(
            "apps.core.ai_briefing.briefing_engine.generate_daily_briefing"
        ) as mock_gen:
            result = run_daily_briefings()

        mock_gen.assert_not_called()
        self.assertEqual(result["generated"], 0)

    def test_handles_dbe_errors(self):
        _create_test_user()

        with patch(
            "apps.core.ai_briefing.briefing_engine.generate_daily_briefing",
            side_effect=RuntimeError("DBE error"),
        ):
            result = run_daily_briefings()

        self.assertEqual(result["errors"], 1)


class RunLearningProfileUpdatesTest(TestCase):
    """Tests for run_learning_profile_updates runner."""

    def test_calls_gloe_for_ai_users(self):
        user = _create_test_user()

        with patch(
            "apps.core.ai_guidance_learning.learning_engine.update_learning_profile"
        ) as mock_update:
            result = run_learning_profile_updates()

        mock_update.assert_called_once_with(user)
        self.assertEqual(result["updated"], 1)

    def test_handles_gloe_errors(self):
        _create_test_user()

        with patch(
            "apps.core.ai_guidance_learning.learning_engine.update_learning_profile",
            side_effect=RuntimeError("GLOE error"),
        ):
            result = run_learning_profile_updates()

        self.assertEqual(result["errors"], 1)


class RunGuidanceRefreshTest(TestCase):
    """Tests for run_guidance_refresh runner."""

    def test_calls_pge_for_ai_users(self):
        user = _create_test_user()

        with patch(
            "apps.core.ai_guidance.guidance_engine.expire_old_guidance",
            return_value=2,
        ), patch(
            "apps.core.ai_guidance.guidance_engine.generate_guidance",
            return_value=[MagicMock()],
        ) as mock_gen:
            result = run_guidance_refresh()

        mock_gen.assert_called_once_with(user)
        self.assertEqual(result["refreshed"], 1)
        self.assertEqual(result["expired"], 2)

    def test_handles_pge_errors(self):
        _create_test_user()

        with patch(
            "apps.core.ai_guidance.guidance_engine.expire_old_guidance",
            return_value=0,
        ), patch(
            "apps.core.ai_guidance.guidance_engine.generate_guidance",
            side_effect=RuntimeError("PGE error"),
        ):
            result = run_guidance_refresh()

        self.assertEqual(result["errors"], 1)


# ---------------------------------------------------------------------------
# Management Command Tests
# ---------------------------------------------------------------------------


class ManagementCommandTest(TestCase):
    """Tests for run_intelligence_scheduler command."""

    def test_command_runs(self):
        out = StringIO()
        with patch(
            "apps.core.ai_scheduler.scheduler_engine.run_scheduler_cycle",
            return_value={"executed": 0, "skipped": 3, "failed": 0},
        ):
            call_command("run_intelligence_scheduler", stdout=out)

        output = out.getvalue()
        self.assertIn("executed=0", output)
        self.assertIn("skipped=3", output)

    def test_dry_run(self):
        _ensure_task_records()
        out = StringIO()
        call_command("run_intelligence_scheduler", "--dry-run", stdout=out)

        output = out.getvalue()
        self.assertIn("dry run", output)
        self.assertIn("generate_daily_briefings", output)
