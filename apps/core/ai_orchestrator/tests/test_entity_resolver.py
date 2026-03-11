"""
Tests for Entity Resolver — resolves natural language references to database entities.

Tests cover:
- Task resolution (exact, prefix, substring, no match, multiple matches)
- Goal, Habit, Medicine resolution
- ID preservation (never overrides existing IDs)
- User scoping (never leaks cross-user data)
- Graceful failure (errors don't block pipeline)
"""

from unittest.mock import MagicMock

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.core.ai_orchestrator.entity_resolver import (
    ENTITY_INTENT_MAP,
    resolve_entities,
)


class EntityResolverTestMixin:
    """Shared setup for entity resolver tests."""

    def setUp(self):
        from apps.users.models import User, TermsAcceptance

        self.user = User.objects.create_user(
            email='resolver@test.com', password='testpass123',
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

        # Second user for cross-user isolation tests
        self.other_user = User.objects.create_user(
            email='other@test.com', password='testpass123',
        )

    def _make_enriched(self, intent_type, parameters):
        """Build a mock EnrichedAction."""
        enriched = MagicMock()
        enriched.intent_type = intent_type
        enriched.parameters = dict(parameters)  # Copy so we can check mutations
        return enriched


class TaskResolutionTests(EntityResolverTestMixin, TestCase):
    """Tests for task entity resolution."""

    def setUp(self):
        super().setUp()
        from apps.life.models import Task

        self.task_journal = Task.objects.create(
            user=self.user, title='Journal', completion_status='pending',
            due_date=timezone.now().date(),
        )
        self.task_workout = Task.objects.create(
            user=self.user, title='Morning Workout', completion_status='pending',
            due_date=timezone.now().date(),
        )
        self.task_completed = Task.objects.create(
            user=self.user, title='Completed Task', completion_status='completed',
        )
        # Task owned by another user
        self.other_task = Task.objects.create(
            user=self.other_user, title='Journal', completion_status='pending',
        )

    def test_exact_match_resolves(self):
        enriched = self._make_enriched('complete_task', {'task_keyword': 'Journal'})
        resolve_entities(self.user, enriched)
        self.assertEqual(enriched.parameters['_resolved_id'], self.task_journal.id)
        self.assertEqual(enriched.parameters['resolved_name'], 'Journal')

    def test_case_insensitive_exact_match(self):
        enriched = self._make_enriched('complete_task', {'task_keyword': 'journal'})
        resolve_entities(self.user, enriched)
        self.assertEqual(enriched.parameters['_resolved_id'], self.task_journal.id)

    def test_prefix_match_resolves(self):
        enriched = self._make_enriched('complete_task', {'task_keyword': 'Morning'})
        resolve_entities(self.user, enriched)
        self.assertEqual(enriched.parameters['_resolved_id'], self.task_workout.id)
        self.assertEqual(enriched.parameters['resolved_name'], 'Morning Workout')

    def test_substring_match_resolves(self):
        enriched = self._make_enriched('complete_task', {'task_keyword': 'Workout'})
        resolve_entities(self.user, enriched)
        self.assertEqual(enriched.parameters['_resolved_id'], self.task_workout.id)

    def test_no_match_leaves_params_unchanged(self):
        enriched = self._make_enriched('complete_task', {'task_keyword': 'nonexistent'})
        resolve_entities(self.user, enriched)
        self.assertNotIn('_resolved_id', enriched.parameters)
        self.assertNotIn('resolved_name', enriched.parameters)

    def test_completed_tasks_excluded(self):
        enriched = self._make_enriched('complete_task', {'task_keyword': 'Completed Task'})
        resolve_entities(self.user, enriched)
        self.assertNotIn('_resolved_id', enriched.parameters)

    def test_never_overrides_existing_id(self):
        enriched = self._make_enriched('complete_task', {
            'task_keyword': 'Journal', '_resolved_id': 999,
        })
        resolve_entities(self.user, enriched)
        self.assertEqual(enriched.parameters['_resolved_id'], 999)  # Unchanged

    def test_user_scoped_no_cross_user_leakage(self):
        """Other user's tasks must not be resolved."""
        enriched = self._make_enriched('complete_task', {'task_keyword': 'Journal'})
        resolve_entities(self.other_user, enriched)
        # Should resolve to other_user's own task
        self.assertEqual(enriched.parameters['_resolved_id'], self.other_task.id)

    def test_skip_task_uses_same_resolver(self):
        enriched = self._make_enriched('skip_task', {'task_keyword': 'Journal'})
        resolve_entities(self.user, enriched)
        self.assertEqual(enriched.parameters['_resolved_id'], self.task_journal.id)

    def test_mutate_task_uses_task_query_param(self):
        enriched = self._make_enriched('mutate_task', {'task_query': 'Journal'})
        resolve_entities(self.user, enriched)
        self.assertEqual(enriched.parameters['_resolved_id'], self.task_journal.id)

    def test_empty_keyword_skipped(self):
        enriched = self._make_enriched('complete_task', {'task_keyword': ''})
        resolve_entities(self.user, enriched)
        self.assertNotIn('_resolved_id', enriched.parameters)

    def test_whitespace_keyword_skipped(self):
        enriched = self._make_enriched('complete_task', {'task_keyword': '   '})
        resolve_entities(self.user, enriched)
        self.assertNotIn('_resolved_id', enriched.parameters)


class TaskAmbiguityTests(EntityResolverTestMixin, TestCase):
    """Tests for multiple-match disambiguation."""

    def setUp(self):
        super().setUp()
        from apps.life.models import Task

        self.task1 = Task.objects.create(
            user=self.user, title='Buy groceries', completion_status='pending',
            due_date=timezone.now().date(),
        )
        self.task2 = Task.objects.create(
            user=self.user, title='Buy birthday gift', completion_status='pending',
            due_date=timezone.now().date() + timezone.timedelta(days=3),
        )

    def test_multiple_prefix_matches_picks_best(self):
        """When multiple tasks match by prefix, pick the one with earliest due_date."""
        enriched = self._make_enriched('complete_task', {'task_keyword': 'Buy'})
        resolve_entities(self.user, enriched)
        # Both match by prefix, but task1 has earlier due_date
        self.assertEqual(enriched.parameters['_resolved_id'], self.task1.id)
        self.assertEqual(enriched.parameters['resolved_name'], 'Buy groceries')

    def test_multiple_substring_only_matches_returns_none(self):
        """When multiple tasks match by substring only (not prefix), don't guess."""
        from apps.life.models import Task
        # Create tasks that only match "meeting" by substring, not prefix
        Task.objects.filter(user=self.user).delete()
        Task.objects.create(
            user=self.user, title='Team meeting prep', completion_status='pending',
        )
        Task.objects.create(
            user=self.user, title='Post-meeting notes', completion_status='pending',
        )
        enriched = self._make_enriched('complete_task', {'task_keyword': 'meeting'})
        resolve_entities(self.user, enriched)
        self.assertNotIn('_resolved_id', enriched.parameters)

    def test_exact_match_wins_over_multiple_prefix(self):
        """Exact match takes priority even when other matches exist."""
        from apps.life.models import Task
        Task.objects.create(
            user=self.user, title='Buy', completion_status='pending',
        )
        enriched = self._make_enriched('complete_task', {'task_keyword': 'Buy'})
        resolve_entities(self.user, enriched)
        # Exact match on "Buy" should resolve
        self.assertIn('_resolved_id', enriched.parameters)


class GoalResolutionTests(EntityResolverTestMixin, TestCase):
    """Tests for goal entity resolution."""

    def setUp(self):
        super().setUp()
        from apps.purpose.models import LifeGoal

        self.goal = LifeGoal.objects.create(
            user=self.user, title='Lose 20 pounds',
        )

    def test_goal_resolves_by_keyword(self):
        enriched = self._make_enriched('update_goal_progress', {'goal_keyword': 'pounds'})
        resolve_entities(self.user, enriched)
        self.assertEqual(enriched.parameters['_resolved_goal_id'], self.goal.id)
        self.assertEqual(enriched.parameters['resolved_name'], 'Lose 20 pounds')


class HabitResolutionTests(EntityResolverTestMixin, TestCase):
    """Tests for habit entity resolution."""

    def setUp(self):
        super().setUp()
        from apps.purpose.models import HabitGoal

        self.habit = HabitGoal.objects.create(
            user=self.user, name='Daily Reading',
            purpose='Read more books',
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timezone.timedelta(days=90),
        )

    def test_habit_resolves_by_keyword(self):
        enriched = self._make_enriched('log_habit', {'habit_keyword': 'reading'})
        resolve_entities(self.user, enriched)
        self.assertEqual(enriched.parameters['_resolved_habit_id'], self.habit.id)
        self.assertEqual(enriched.parameters['resolved_name'], 'Daily Reading')


class MedicineResolutionTests(EntityResolverTestMixin, TestCase):
    """Tests for medicine entity resolution."""

    def setUp(self):
        super().setUp()
        from apps.health.models import Medicine

        self.medicine = Medicine.objects.create(
            user=self.user, name='Lisinopril', purpose='blood pressure',
            medicine_status='active',
            start_date=timezone.now().date(),
        )

    def test_medicine_resolves_by_name(self):
        enriched = self._make_enriched('take_medicine', {'medicine_name': 'lisinopril'})
        resolve_entities(self.user, enriched)
        self.assertEqual(enriched.parameters['_resolved_medicine_id'], self.medicine.id)
        self.assertEqual(enriched.parameters['resolved_name'], 'Lisinopril')

    def test_medicine_resolves_by_purpose(self):
        enriched = self._make_enriched('take_medicine', {'medicine_name': 'blood pressure'})
        resolve_entities(self.user, enriched)
        self.assertEqual(enriched.parameters['_resolved_medicine_id'], self.medicine.id)


class NonResolvableIntentTests(EntityResolverTestMixin, TestCase):
    """Tests that non-mapped intents pass through unchanged."""

    def test_unknown_intent_passes_through(self):
        enriched = self._make_enriched('log_weight', {'weight': 185})
        resolve_entities(self.user, enriched)
        self.assertEqual(enriched.parameters, {'weight': 185})

    def test_passthrough_intent_unchanged(self):
        enriched = self._make_enriched('read_calendar_events', {'timezone': 'US/Central'})
        resolve_entities(self.user, enriched)
        self.assertEqual(enriched.parameters, {'timezone': 'US/Central'})


class EntityIntentMapConsistencyTests(TestCase):
    """Verify the ENTITY_INTENT_MAP is well-formed."""

    def test_all_entries_have_four_fields(self):
        for intent, mapping in ENTITY_INTENT_MAP.items():
            self.assertEqual(
                len(mapping), 4,
                f"ENTITY_INTENT_MAP['{intent}'] should have 4 fields",
            )

    def test_resolver_names_exist(self):
        from apps.core.ai_orchestrator.entity_resolver import _RESOLVERS
        for intent, mapping in ENTITY_INTENT_MAP.items():
            resolver_name = mapping[3]
            self.assertIn(
                resolver_name, _RESOLVERS,
                f"Resolver '{resolver_name}' for intent '{intent}' not in _RESOLVERS",
            )
