# ==============================================================================
# File: test_task_matching.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Tests for literal-first task matching and stateful clarification.
#              Ensures exact matches win over substring, clarification state
#              resolves without re-searching, and infinite loops are prevented.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-02
# ==============================================================================

from datetime import time

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

LOCMEM_CACHE = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'task-matching-test',
    }
}

from apps.ai.action_handlers import ActionHandler
from apps.ai.intent_service import IntentService, IntentResult
from apps.life.models import Task
from apps.users.models import User


class TestResolveTasksByQuery(TestCase):
    """Test the _resolve_tasks_by_query() literal-first matching method."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='matching@example.com',
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

        # Create tasks with overlapping names
        today = timezone.now().date()
        self.task_workout = Task.objects.create(
            user=self.user, title="Workout", due_date=today,
        )
        self.task_post_workout = Task.objects.create(
            user=self.user, title="Post-Workout Stretch", due_date=today,
        )
        self.task_grocery_run = Task.objects.create(
            user=self.user, title="Grocery run", due_date=today,
        )
        self.task_grocery_list = Task.objects.create(
            user=self.user, title="Grocery list review", due_date=today,
        )

    def test_exact_match_wins_over_substring(self):
        """'Workout' should match only the task titled 'Workout', not 'Post-Workout Stretch'."""
        tasks, tier = self.handler._resolve_tasks_by_query("Workout")
        self.assertEqual(tier, 'exact')
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].id, self.task_workout.id)

    def test_exact_match_case_insensitive(self):
        """Exact match should be case-insensitive."""
        tasks, tier = self.handler._resolve_tasks_by_query("workout")
        self.assertEqual(tier, 'exact')
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].id, self.task_workout.id)

    def test_prefix_match_when_no_exact(self):
        """'Grocery' should prefix-match both Grocery tasks."""
        tasks, tier = self.handler._resolve_tasks_by_query("Grocery")
        self.assertEqual(tier, 'prefix')
        self.assertEqual(len(tasks), 2)
        titles = {t.title for t in tasks}
        self.assertIn("Grocery run", titles)
        self.assertIn("Grocery list review", titles)

    def test_substring_fallback(self):
        """When no exact or prefix match, fall back to substring."""
        tasks, tier = self.handler._resolve_tasks_by_query("Stretch")
        self.assertEqual(tier, 'substring')
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].id, self.task_post_workout.id)

    def test_no_match_returns_empty(self):
        """Query with no match returns empty list."""
        tasks, tier = self.handler._resolve_tasks_by_query("nonexistent")
        self.assertEqual(len(tasks), 0)
        self.assertEqual(tier, 'substring')

    def test_completed_tasks_excluded_by_default(self):
        """Completed tasks are excluded by default."""
        self.task_workout.completion_status = 'completed'
        self.task_workout.save(update_fields=['completion_status'])
        tasks, tier = self.handler._resolve_tasks_by_query("Workout")
        # Should not find the completed "Workout", should fall through to substring
        # which picks up "Post-Workout Stretch"
        self.assertNotIn(self.task_workout.id, [t.id for t in tasks])


class TestExactMatchBypassesClarification(TestCase):
    """Exact match should result in a single task — no 'Which one?' needed."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='bypass@example.com',
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

        today = timezone.now().date()
        self.task_workout = Task.objects.create(
            user=self.user, title="Workout", due_date=today,
        )
        self.task_post_workout = Task.objects.create(
            user=self.user, title="Post-Workout Stretch", due_date=today,
        )

    def test_mutate_exact_match_succeeds_without_clarification(self):
        """mutate_task('Workout') should succeed, not ask 'Which one?'."""
        result = self.handler.handle_mutate_task(
            action="update",
            task_query="Workout",
            new_due_date="tomorrow",
        )
        self.assertTrue(result.success, f"Expected success but got: {result.message}")
        self.assertNotEqual(result.error, 'multiple_matches')

    def test_complete_exact_match_succeeds_without_clarification(self):
        """complete_task('Workout') should succeed, not ask 'Which one?'."""
        result = self.handler.handle_complete_task(task_keyword="Workout")
        self.assertTrue(result.success, f"Expected success but got: {result.message}")


class TestMultipleMatchesReturnsCandidates(TestCase):
    """When multiple matches ARE found, the response includes candidate IDs."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='candidates@example.com',
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

        today = timezone.now().date()
        # Two tasks with the same title — can't be disambiguated by matching alone
        self.task_a = Task.objects.create(
            user=self.user, title="Work meeting", due_date=today,
        )
        self.task_b = Task.objects.create(
            user=self.user, title="Work review", due_date=today,
        )

    def test_mutate_multiple_matches_includes_candidates(self):
        """multiple_matches should include candidates with IDs."""
        result = self.handler.handle_mutate_task(
            action="update",
            task_query="Work",
            new_due_date="tomorrow",
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error, 'multiple_matches')
        self.assertIsNotNone(result.created_object)
        candidates = result.created_object.get('candidates')
        self.assertIsNotNone(candidates)
        self.assertEqual(len(candidates), 2)
        ids = {c['id'] for c in candidates}
        self.assertIn(self.task_a.id, ids)
        self.assertIn(self.task_b.id, ids)

    def test_complete_multiple_matches_includes_candidates(self):
        """complete_task multiple_matches should include candidates."""
        result = self.handler.handle_complete_task(task_keyword="Work")
        self.assertFalse(result.success)
        self.assertEqual(result.error, 'multiple_matches')
        self.assertIsNotNone(result.created_object)
        self.assertTrue(len(result.created_object['candidates']) >= 2)


@override_settings(CACHES=LOCMEM_CACHE)
class TestClarificationState(TestCase):
    """Test pending clarification state storage, retrieval, and resolution."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='clarify@example.com',
            password='testpass123',
            first_name='Test',
        )
        prefs = self.user.preferences
        prefs.ai_enabled = True
        prefs.ai_data_consent = True
        prefs.personal_assistant_enabled = True
        prefs.personal_assistant_consent = True
        prefs.save()

        self.intent_service = IntentService()

        # Create tasks for resolution
        today = timezone.now().date()
        self.task_a = Task.objects.create(
            user=self.user, title="Work meeting", due_date=today,
        )
        self.task_b = Task.objects.create(
            user=self.user, title="Work review", due_date=today,
        )

        self.candidates = [
            {'id': self.task_a.id, 'title': 'Work meeting'},
            {'id': self.task_b.id, 'title': 'Work review'},
        ]

        # Clear any cached state
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_store_and_retrieve(self):
        """Store and retrieve pending clarification."""
        self.intent_service.store_pending_clarification(
            self.user,
            intent_type='mutate_task',
            parameters={'action': 'update', 'task_query': 'Work', 'new_due_date': 'tomorrow'},
            candidates=self.candidates,
        )
        pending = self.intent_service.get_pending_clarification(self.user)
        self.assertIsNotNone(pending)
        self.assertEqual(pending['intent_type'], 'mutate_task')
        self.assertEqual(len(pending['candidates']), 2)

    def test_clear_state(self):
        """Clear removes pending state."""
        self.intent_service.store_pending_clarification(
            self.user, 'mutate_task', {}, self.candidates,
        )
        self.intent_service.clear_pending_clarification(self.user)
        self.assertIsNone(self.intent_service.get_pending_clarification(self.user))

    def test_resolve_exact_match(self):
        """User says exact candidate title → resolves correctly."""
        self.intent_service.store_pending_clarification(
            self.user,
            intent_type='mutate_task',
            parameters={'action': 'update', 'task_query': 'Work', 'new_due_date': 'tomorrow'},
            candidates=self.candidates,
        )
        result = self.intent_service.resolve_clarification(self.user, "Work meeting")
        self.assertIsNotNone(result)
        self.assertTrue(result.success)
        # State should be cleared after resolution
        self.assertIsNone(self.intent_service.get_pending_clarification(self.user))

    def test_resolve_number_selection(self):
        """User says '1' → resolves to first candidate."""
        self.intent_service.store_pending_clarification(
            self.user,
            intent_type='mutate_task',
            parameters={'action': 'update', 'task_query': 'Work', 'new_due_date': 'tomorrow'},
            candidates=self.candidates,
        )
        result = self.intent_service.resolve_clarification(self.user, "1")
        self.assertIsNotNone(result)
        self.assertTrue(result.success)

    def test_resolve_ordinal_selection(self):
        """User says 'the second one' → resolves to second candidate."""
        self.intent_service.store_pending_clarification(
            self.user,
            intent_type='mutate_task',
            parameters={'action': 'update', 'task_query': 'Work', 'new_due_date': 'tomorrow'},
            candidates=self.candidates,
        )
        result = self.intent_service.resolve_clarification(self.user, "the second one")
        self.assertIsNotNone(result)
        self.assertTrue(result.success)

    def test_resolve_substring_match(self):
        """User says 'meeting' → matches 'Work meeting'."""
        self.intent_service.store_pending_clarification(
            self.user,
            intent_type='mutate_task',
            parameters={'action': 'update', 'task_query': 'Work', 'new_due_date': 'tomorrow'},
            candidates=self.candidates,
        )
        result = self.intent_service.resolve_clarification(self.user, "meeting")
        self.assertIsNotNone(result)
        self.assertTrue(result.success)

    def test_resolve_no_match_returns_none(self):
        """Unrecognized response returns None (state preserved for re-show)."""
        self.intent_service.store_pending_clarification(
            self.user,
            intent_type='mutate_task',
            parameters={'action': 'update', 'task_query': 'Work', 'new_due_date': 'tomorrow'},
            candidates=self.candidates,
        )
        result = self.intent_service.resolve_clarification(self.user, "nonsense xyz")
        self.assertIsNone(result)
        # State should still exist (not cleared on failure)
        self.assertIsNotNone(self.intent_service.get_pending_clarification(self.user))

    def test_state_clears_after_successful_resolution(self):
        """After successful resolution, pending state is gone (prevents loops)."""
        self.intent_service.store_pending_clarification(
            self.user,
            intent_type='complete_task',
            parameters={'task_keyword': 'Work'},
            candidates=self.candidates,
        )
        result = self.intent_service.resolve_clarification(self.user, "Work meeting")
        self.assertIsNotNone(result)
        # Verify state is gone
        self.assertIsNone(self.intent_service.get_pending_clarification(self.user))

    def test_no_pending_state_returns_none(self):
        """resolve_clarification with no pending state returns None gracefully."""
        result = self.intent_service.resolve_clarification(self.user, "anything")
        self.assertIsNone(result)


class TestResolvedIdBypass(TestCase):
    """Test that _resolved_id bypasses search and fetches by PK directly."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='resolvedid@example.com',
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

        today = timezone.now().date()
        self.task = Task.objects.create(
            user=self.user, title="Unique Task", due_date=today,
        )

    def test_mutate_with_resolved_id(self):
        """_resolved_id should fetch exact task by PK."""
        result = self.handler.handle_mutate_task(
            action="update",
            task_query="doesn't matter",
            new_due_date="tomorrow",
            _resolved_id=self.task.id,
        )
        self.assertTrue(result.success)
        self.task.refresh_from_db()
        # Verify the task was actually updated

    def test_complete_with_resolved_id(self):
        """_resolved_id should complete the exact task by PK."""
        result = self.handler.handle_complete_task(
            task_keyword="doesn't matter",
            _resolved_id=self.task.id,
        )
        self.assertTrue(result.success)
        self.task.refresh_from_db()
        self.assertTrue(self.task.is_completed)

    def test_resolved_id_nonexistent(self):
        """_resolved_id pointing to nonexistent task returns error."""
        result = self.handler.handle_mutate_task(
            action="update",
            task_query="x",
            new_due_date="tomorrow",
            _resolved_id=99999,
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error, 'task_not_found')
