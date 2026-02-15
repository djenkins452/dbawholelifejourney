"""
SAE — State Awareness Engine Tests.

Tests:
- State creation and retrieval
- State updates after data changes (weight, goals, habits, faith, journal)
- Incremental update behavior
- State builder accuracy
- State reader fallback behavior
- State utils (invalidation, age, summary)
- PIE event enrichment
- UAIO integration (auto-activate hook)
"""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.users.models import User


def _create_test_user(email="test@example.com"):
    """Create a test user with required onboarding setup."""
    from apps.users.models import TermsAcceptance

    user = User.objects.create_user(
        email=email, password="testpass123", date_of_birth=date(1990, 1, 1)
    )
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


class TestUserStateModel(TestCase):
    """Test the UserState model."""

    def setUp(self):
        self.user = _create_test_user()

    def test_create_user_state(self):
        from apps.core.ai_state.models import UserState

        state = UserState.objects.create(user=self.user, state_data={})
        self.assertEqual(state.user, self.user)
        self.assertEqual(state.state_data, {})
        self.assertIsNotNone(state.last_updated)
        self.assertIsNotNone(state.created_at)

    def test_one_to_one_constraint(self):
        from django.db import IntegrityError

        from apps.core.ai_state.models import UserState

        UserState.objects.create(user=self.user, state_data={})
        with self.assertRaises(IntegrityError):
            UserState.objects.create(user=self.user, state_data={})

    def test_get_module(self):
        from apps.core.ai_state.models import UserState

        state = UserState.objects.create(
            user=self.user,
            state_data={"health": {"weight_current": 180.0}},
        )
        self.assertEqual(state.get_module("health"), {"weight_current": 180.0})
        self.assertEqual(state.get_module("goals"), {})

    def test_set_module(self):
        from apps.core.ai_state.models import UserState

        state = UserState.objects.create(user=self.user, state_data={})
        state.set_module("health", {"weight_current": 180.0})
        self.assertEqual(state.state_data["health"]["weight_current"], 180.0)

    def test_str_representation(self):
        from apps.core.ai_state.models import UserState

        state = UserState.objects.create(
            user=self.user,
            state_data={"health": {}, "goals": {}},
        )
        self.assertIn("health", str(state))
        self.assertIn("goals", str(state))

    def test_str_empty_state(self):
        from apps.core.ai_state.models import UserState

        state = UserState.objects.create(user=self.user, state_data={})
        self.assertIn("empty", str(state))


class TestStateEngine(TestCase):
    """Test state engine retrieval and rebuild."""

    def setUp(self):
        self.user = _create_test_user()

    def test_get_user_state_creates_on_first_access(self):
        from apps.core.ai_state.models import UserState
        from apps.core.ai_state.state_engine import get_user_state

        self.assertFalse(UserState.objects.filter(user=self.user).exists())
        state = get_user_state(self.user)
        self.assertIsInstance(state, dict)
        self.assertTrue(UserState.objects.filter(user=self.user).exists())

    def test_get_user_state_returns_cached(self):
        from apps.core.ai_state.models import UserState
        from apps.core.ai_state.state_engine import get_user_state

        UserState.objects.create(
            user=self.user,
            state_data={"health": {"weight_current": 175.0}},
        )
        state = get_user_state(self.user)
        self.assertEqual(state["health"]["weight_current"], 175.0)

    def test_get_module_state(self):
        from apps.core.ai_state.models import UserState
        from apps.core.ai_state.state_engine import get_module_state

        UserState.objects.create(
            user=self.user,
            state_data={"health": {"weight_current": 175.0}},
        )
        health = get_module_state(self.user, "health")
        self.assertEqual(health["weight_current"], 175.0)

    def test_get_module_state_alias(self):
        from apps.core.ai_state.models import UserState
        from apps.core.ai_state.state_engine import get_module_state

        UserState.objects.create(
            user=self.user,
            state_data={"goals": {"active_goal_count": 3}},
        )
        # "purpose" is an alias for "goals"
        goals = get_module_state(self.user, "purpose")
        self.assertEqual(goals["active_goal_count"], 3)

    def test_rebuild_user_state(self):
        from apps.core.ai_state.state_engine import rebuild_user_state

        state = rebuild_user_state(self.user)
        self.assertIsInstance(state, dict)
        # Should have the core modules
        self.assertIn("health", state)
        self.assertIn("goals", state)
        self.assertIn("habits", state)
        self.assertIn("faith", state)
        self.assertIn("journal", state)


class TestStateUpdater(TestCase):
    """Test incremental state updates."""

    def setUp(self):
        self.user = _create_test_user()

    def test_update_user_state_health(self):
        from apps.core.ai_state.models import UserState
        from apps.core.ai_state.state_updater import update_user_state

        update_user_state(self.user, "health")
        state_obj = UserState.objects.get(user=self.user)
        self.assertIn("health", state_obj.state_data)

    def test_update_user_state_goals(self):
        from apps.core.ai_state.state_updater import update_user_state

        update_user_state(self.user, "goals")
        from apps.core.ai_state.models import UserState

        state_obj = UserState.objects.get(user=self.user)
        self.assertIn("goals", state_obj.state_data)

    def test_update_user_state_purpose_alias(self):
        """'purpose' module should update 'goals' state key."""
        from apps.core.ai_state.models import UserState
        from apps.core.ai_state.state_updater import update_user_state

        update_user_state(self.user, "purpose")
        state_obj = UserState.objects.get(user=self.user)
        self.assertIn("goals", state_obj.state_data)

    def test_incremental_update_preserves_other_modules(self):
        """Updating one module should not wipe other modules."""
        from apps.core.ai_state.models import UserState
        from apps.core.ai_state.state_updater import update_user_state

        # Build initial full state
        update_user_state(self.user, "health")
        update_user_state(self.user, "goals")

        state_obj = UserState.objects.get(user=self.user)
        self.assertIn("health", state_obj.state_data)
        self.assertIn("goals", state_obj.state_data)

        # Update just health — goals should remain
        update_user_state(self.user, "health")
        state_obj.refresh_from_db()
        self.assertIn("health", state_obj.state_data)
        self.assertIn("goals", state_obj.state_data)

    def test_unknown_module_no_error(self):
        """Unknown module should log debug and not crash."""
        from apps.core.ai_state.state_updater import update_user_state

        # Should not raise
        update_user_state(self.user, "unknown_module")


class TestHealthStateBuilder(TestCase):
    """Test health state builder accuracy."""

    def setUp(self):
        self.user = _create_test_user()

    def test_empty_health_state(self):
        from apps.core.ai_state.state_builder import build_health_state

        state = build_health_state(self.user)
        self.assertIsInstance(state, dict)
        # No weight entries → no weight keys
        self.assertNotIn("weight_current", state)

    def test_weight_entry_reflected_in_state(self):
        from apps.health.models import WeightEntry

        from apps.core.ai_state.state_builder import build_health_state

        WeightEntry.objects.create(
            user=self.user, value=Decimal("180.5"), unit="lb"
        )
        state = build_health_state(self.user)
        self.assertEqual(state["weight_current"], 180.5)
        self.assertEqual(state["weight_unit"], "lb")
        self.assertIn("last_weight_entry", state)

    def test_weight_trend_increasing(self):
        from apps.health.models import WeightEntry

        from apps.core.ai_state.state_builder import build_health_state

        # Create older entry
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("170.0"),
            unit="lb",
            recorded_at=timezone.now() - timedelta(days=35),
        )
        # Create newer entry
        WeightEntry.objects.create(
            user=self.user, value=Decimal("180.0"), unit="lb"
        )
        state = build_health_state(self.user)
        self.assertEqual(state["weight_trend"], "increasing")

    def test_weight_trend_decreasing(self):
        from apps.health.models import WeightEntry

        from apps.core.ai_state.state_builder import build_health_state

        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("190.0"),
            unit="lb",
            recorded_at=timezone.now() - timedelta(days=35),
        )
        WeightEntry.objects.create(
            user=self.user, value=Decimal("180.0"), unit="lb"
        )
        state = build_health_state(self.user)
        self.assertEqual(state["weight_trend"], "decreasing")

    def test_weight_trend_stable(self):
        from apps.health.models import WeightEntry

        from apps.core.ai_state.state_builder import build_health_state

        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("180.0"),
            unit="lb",
            recorded_at=timezone.now() - timedelta(days=35),
        )
        WeightEntry.objects.create(
            user=self.user, value=Decimal("180.2"), unit="lb"
        )
        state = build_health_state(self.user)
        self.assertEqual(state["weight_trend"], "stable")

    def test_body_fat_in_state(self):
        from apps.health.models import BodyCompositionEntry

        from apps.core.ai_state.state_builder import build_health_state

        BodyCompositionEntry.objects.create(
            user=self.user,
            metric_name="body_fat_pct",
            value=Decimal("22.5"),
            unit="%",
            measurement_date=date.today(),
        )
        state = build_health_state(self.user)
        self.assertEqual(state["body_fat_current"], 22.5)

    def test_weight_entries_90d_count(self):
        from apps.health.models import WeightEntry

        from apps.core.ai_state.state_builder import build_health_state

        for i in range(5):
            WeightEntry.objects.create(
                user=self.user,
                value=Decimal("180.0"),
                unit="lb",
                recorded_at=timezone.now() - timedelta(days=i * 10),
            )
        state = build_health_state(self.user)
        self.assertEqual(state["weight_entries_90d"], 5)


class TestGoalStateBuilder(TestCase):
    """Test goal state builder accuracy."""

    def setUp(self):
        self.user = _create_test_user()

    def test_no_goals(self):
        from apps.core.ai_state.state_builder import build_goal_state

        state = build_goal_state(self.user)
        self.assertEqual(state["active_goal_count"], 0)

    def test_active_goals_counted(self):
        from apps.purpose.models import LifeGoal

        from apps.core.ai_state.state_builder import build_goal_state

        LifeGoal.objects.create(
            user=self.user,
            title="Test Goal 1",
            status="active",
            target_date=date.today() + timedelta(days=30),
        )
        LifeGoal.objects.create(
            user=self.user, title="Test Goal 2", status="active"
        )
        LifeGoal.objects.create(
            user=self.user, title="Done Goal", status="completed"
        )

        state = build_goal_state(self.user)
        self.assertEqual(state["active_goal_count"], 2)

    def test_next_deadline(self):
        from apps.purpose.models import LifeGoal

        from apps.core.ai_state.state_builder import build_goal_state

        target = date.today() + timedelta(days=15)
        LifeGoal.objects.create(
            user=self.user,
            title="Urgent Goal",
            status="active",
            target_date=target,
        )
        LifeGoal.objects.create(
            user=self.user,
            title="Later Goal",
            status="active",
            target_date=date.today() + timedelta(days=60),
        )

        state = build_goal_state(self.user)
        self.assertEqual(state["next_deadline"], target.isoformat())

    def test_milestone_completion_rate(self):
        from apps.purpose.models import GoalMilestone, LifeGoal

        from apps.core.ai_state.state_builder import build_goal_state

        goal = LifeGoal.objects.create(
            user=self.user, title="Test", status="active"
        )
        GoalMilestone.objects.create(
            goal=goal, title="M1", completed=True, completed_date=date.today()
        )
        GoalMilestone.objects.create(goal=goal, title="M2", completed=False)

        state = build_goal_state(self.user)
        self.assertEqual(state["completion_rate"], 0.5)
        self.assertEqual(state["total_milestones"], 2)
        self.assertEqual(state["completed_milestones"], 1)


class TestHabitStateBuilder(TestCase):
    """Test habit state builder accuracy."""

    def setUp(self):
        self.user = _create_test_user()

    def test_no_habits(self):
        from apps.core.ai_state.state_builder import build_habit_state

        state = build_habit_state(self.user)
        self.assertEqual(state["active_habit_count"], 0)

    def test_active_habits_counted(self):
        from apps.purpose.models import HabitGoal

        from apps.core.ai_state.state_builder import build_habit_state

        HabitGoal.objects.create(
            user=self.user,
            name="Exercise",
            purpose="Stay healthy",
            status="active",
            start_date=date.today() - timedelta(days=30),
            end_date=date.today() + timedelta(days=30),
        )
        HabitGoal.objects.create(
            user=self.user,
            name="Read",
            purpose="Grow mentally",
            status="active",
            start_date=date.today() - timedelta(days=30),
            end_date=date.today() + timedelta(days=30),
        )

        state = build_habit_state(self.user)
        self.assertEqual(state["active_habit_count"], 2)

    def test_habit_streak_and_activity(self):
        from apps.purpose.models import HabitEntry, HabitGoal

        from apps.core.ai_state.state_builder import build_habit_state

        habit = HabitGoal.objects.create(
            user=self.user,
            name="Exercise",
            purpose="Stay healthy",
            status="active",
            start_date=date.today() - timedelta(days=30),
            end_date=date.today() + timedelta(days=30),
        )
        # Create entries for the last 3 days
        for i in range(3):
            HabitEntry.objects.create(
                goal=habit,
                date=date.today() - timedelta(days=i),
                completed=True,
            )

        state = build_habit_state(self.user)
        self.assertEqual(state["longest_streak"], 3)
        self.assertEqual(state["last_activity"], date.today().isoformat())


class TestFaithStateBuilder(TestCase):
    """Test faith state builder accuracy."""

    def setUp(self):
        self.user = _create_test_user()

    def test_empty_faith_state(self):
        from apps.core.ai_state.state_builder import build_faith_state

        state = build_faith_state(self.user)
        self.assertEqual(state["active_reading_plans"], 0)
        self.assertEqual(state["reading_streak"], 0)
        self.assertEqual(state["unanswered_prayers"], 0)

    def test_prayer_requests_counted(self):
        from apps.faith.models import PrayerRequest

        from apps.core.ai_state.state_builder import build_faith_state

        PrayerRequest.objects.create(
            user=self.user, title="Prayer 1", is_answered=False
        )
        PrayerRequest.objects.create(
            user=self.user, title="Prayer 2", is_answered=False
        )
        PrayerRequest.objects.create(
            user=self.user, title="Prayer 3", is_answered=True
        )

        state = build_faith_state(self.user)
        self.assertEqual(state["unanswered_prayers"], 2)


class TestJournalStateBuilder(TestCase):
    """Test journal state builder accuracy."""

    def setUp(self):
        self.user = _create_test_user()

    def test_empty_journal_state(self):
        from apps.core.ai_state.state_builder import build_journal_state

        state = build_journal_state(self.user)
        self.assertNotIn("last_entry", state)
        self.assertEqual(state["entry_frequency"], 0.0)
        self.assertEqual(state["entries_30d"], 0)

    def test_journal_entry_reflected(self):
        from apps.journal.models import JournalEntry

        from apps.core.ai_state.state_builder import build_journal_state

        JournalEntry.objects.create(
            user=self.user,
            title="Test Entry",
            body="Today was a great day.",
            entry_date=date.today(),
            mood="great",
        )

        state = build_journal_state(self.user)
        self.assertEqual(state["last_entry"], date.today().isoformat())
        self.assertEqual(state["last_mood"], "great")
        self.assertEqual(state["days_since_entry"], 0)
        self.assertEqual(state["entries_30d"], 1)

    def test_journal_frequency(self):
        from apps.journal.models import JournalEntry

        from apps.core.ai_state.state_builder import build_journal_state

        for i in range(10):
            JournalEntry.objects.create(
                user=self.user,
                title=f"Entry {i}",
                body="Content",
                entry_date=date.today() - timedelta(days=i * 3),
            )

        state = build_journal_state(self.user)
        self.assertEqual(state["entries_30d"], 10)
        # ~10 entries in 30 days = ~2.3 per week
        self.assertGreater(state["entry_frequency"], 2.0)


class TestStateReader(TestCase):
    """Test state reader (PRIE integration)."""

    def setUp(self):
        self.user = _create_test_user()

    def test_queryset_types_return_none(self):
        """Time-series data types should return None (fall back to DB)."""
        from apps.core.ai_state.state_reader import get_cached_data

        result = get_cached_data(self.user, "health", "weight_entries")
        self.assertIsNone(result)

        result = get_cached_data(self.user, "health", "body_fat_entries")
        self.assertIsNone(result)

        result = get_cached_data(self.user, "medical", "lab_results")
        self.assertIsNone(result)

    def test_active_goals_returns_none(self):
        """Active goals data type should fall back to DB (needs QuerySet)."""
        from apps.core.ai_state.state_reader import get_cached_data

        result = get_cached_data(self.user, "goals", "active_goals")
        self.assertIsNone(result)

    def test_unknown_type_returns_none(self):
        from apps.core.ai_state.state_reader import get_cached_data

        result = get_cached_data(self.user, "health", "unknown_type")
        self.assertIsNone(result)


class TestStateUtils(TestCase):
    """Test state utility functions."""

    def setUp(self):
        self.user = _create_test_user()

    def test_get_state_age_no_state(self):
        from apps.core.ai_state.state_utils import get_state_age_seconds

        age = get_state_age_seconds(self.user)
        self.assertIsNone(age)

    def test_get_state_age_with_state(self):
        from apps.core.ai_state.models import UserState
        from apps.core.ai_state.state_utils import get_state_age_seconds

        UserState.objects.create(user=self.user, state_data={})
        age = get_state_age_seconds(self.user)
        self.assertIsNotNone(age)
        self.assertLess(age, 5.0)  # Should be very recent

    def test_invalidate_state_module(self):
        from apps.core.ai_state.models import UserState
        from apps.core.ai_state.state_utils import invalidate_state

        UserState.objects.create(
            user=self.user,
            state_data={"health": {"weight_current": 180.0}, "goals": {}},
        )
        invalidate_state(self.user, module="health")

        state_obj = UserState.objects.get(user=self.user)
        self.assertNotIn("health", state_obj.state_data)
        self.assertIn("goals", state_obj.state_data)

    def test_invalidate_state_all(self):
        from apps.core.ai_state.models import UserState
        from apps.core.ai_state.state_utils import invalidate_state

        UserState.objects.create(
            user=self.user,
            state_data={"health": {}, "goals": {}},
        )
        invalidate_state(self.user)

        state_obj = UserState.objects.get(user=self.user)
        self.assertEqual(state_obj.state_data, {})

    def test_get_state_summary(self):
        from apps.core.ai_state.models import UserState
        from apps.core.ai_state.state_utils import get_state_summary

        UserState.objects.create(
            user=self.user,
            state_data={
                "health": {"weight_current": 180.0, "weight_trend": "stable"},
                "goals": {"active_goal_count": 3},
            },
        )
        summary = get_state_summary(self.user)
        self.assertEqual(summary["health"]["fields"], 2)
        self.assertEqual(summary["goals"]["fields"], 1)


class TestPIEIntegration(TestCase):
    """Test SAE integration with PIE insight engine."""

    def setUp(self):
        self.user = _create_test_user()

    def test_event_enrichment_adds_state(self):
        from apps.core.ai_insights.insight_engine import _enrich_event_with_state

        event = {"event_type": "record_created", "module": "health"}
        enriched = _enrich_event_with_state(self.user, event)

        # Should have user_state key
        self.assertIn("user_state", enriched)
        self.assertIsInstance(enriched["user_state"], dict)
        # Original event keys preserved
        self.assertEqual(enriched["event_type"], "record_created")
        self.assertEqual(enriched["module"], "health")

    def test_event_enrichment_does_not_mutate_original(self):
        from apps.core.ai_insights.insight_engine import _enrich_event_with_state

        event = {"event_type": "test", "module": "health"}
        enriched = _enrich_event_with_state(self.user, event)

        # Original event should not be mutated
        self.assertNotIn("user_state", event)
        self.assertIn("user_state", enriched)


class TestUAIOIntegration(TestCase):
    """Test SAE auto-activation via UAIO execution engine."""

    def test_sae_import_succeeds(self):
        """The SAE hook in execution_engine.py should now resolve."""
        from apps.core.ai_state.state_updater import update_user_state

        self.assertTrue(callable(update_user_state))

    def test_state_reader_import_succeeds(self):
        """The state reader hook in prediction_engine.py should now resolve."""
        from apps.core.ai_state.state_reader import get_cached_data

        self.assertTrue(callable(get_cached_data))

    def test_update_after_weight_entry(self):
        """Simulate what happens when execution_engine calls update_user_state."""
        from apps.health.models import WeightEntry

        from apps.core.ai_state.models import UserState
        from apps.core.ai_state.state_updater import update_user_state

        user = _create_test_user("uaio@test.com")
        WeightEntry.objects.create(
            user=user, value=Decimal("185.0"), unit="lb"
        )

        update_user_state(user, "health", record_id=1)

        state_obj = UserState.objects.get(user=user)
        health = state_obj.state_data.get("health", {})
        self.assertEqual(health["weight_current"], 185.0)
        self.assertIn("last_weight_entry", health)


class TestAdminRegistration(TestCase):
    """Test admin is properly configured."""

    def test_admin_registered(self):
        from django.contrib.admin.sites import site

        from apps.core.ai_state.models import UserState

        self.assertIn(UserState, site._registry)

    def test_admin_read_only(self):
        from django.contrib.admin.sites import site

        from apps.core.ai_state.models import UserState

        admin_class = site._registry[UserState]
        self.assertFalse(admin_class.has_add_permission(None))
        self.assertFalse(admin_class.has_change_permission(None))
        self.assertFalse(admin_class.has_delete_permission(None))


# ---------------------------------------------------------------------------
# State Authority Compliance Tests
# ---------------------------------------------------------------------------


class TestGetStateValue(TestCase):
    """Test the get_state_value() dot-path accessor."""

    def setUp(self):
        self.user = _create_test_user("state_value@test.com")

    def test_simple_path(self):
        from apps.core.ai_state.models import UserState
        from apps.core.ai_state.state_engine import get_state_value

        UserState.objects.create(
            user=self.user,
            state_data={"health": {"weight_current": 180.5}},
        )
        result = get_state_value(self.user, "health.weight_current")
        self.assertEqual(result, 180.5)

    def test_nested_path(self):
        from apps.core.ai_state.models import UserState
        from apps.core.ai_state.state_engine import get_state_value

        UserState.objects.create(
            user=self.user,
            state_data={
                "journal": {"mood_distribution": {"great": 5, "okay": 3}}
            },
        )
        result = get_state_value(self.user, "journal.mood_distribution.great")
        self.assertEqual(result, 5)

    def test_missing_path_returns_default(self):
        from apps.core.ai_state.models import UserState
        from apps.core.ai_state.state_engine import get_state_value

        UserState.objects.create(
            user=self.user, state_data={"health": {}}
        )
        result = get_state_value(self.user, "health.weight_current", 0)
        self.assertEqual(result, 0)

    def test_missing_module_returns_default(self):
        from apps.core.ai_state.models import UserState
        from apps.core.ai_state.state_engine import get_state_value

        UserState.objects.create(
            user=self.user, state_data={}
        )
        result = get_state_value(self.user, "goals.active_goal_count", 0)
        self.assertEqual(result, 0)

    def test_invalid_path_returns_default(self):
        from apps.core.ai_state.state_engine import get_state_value

        result = get_state_value(self.user, "x", "default")
        self.assertEqual(result, "default")

    def test_module_alias_resolved(self):
        from apps.core.ai_state.models import UserState
        from apps.core.ai_state.state_engine import get_state_value

        UserState.objects.create(
            user=self.user,
            state_data={"goals": {"active_goal_count": 3}},
        )
        # "purpose" should resolve to "goals"
        result = get_state_value(self.user, "purpose.active_goal_count")
        self.assertEqual(result, 3)


class TestStateAuthorityCompliance(TestCase):
    """
    Verify that SAE state builders produce the fields that
    consumers expect, and that key state paths are authoritative.
    """

    def setUp(self):
        self.user = _create_test_user("compliance@test.com")

    def test_health_builder_produces_expected_fields(self):
        """Health builder must produce weight_current, weight_trend, etc."""
        from decimal import Decimal
        from apps.health.models import WeightEntry
        from apps.core.ai_state.state_builder import build_health_state

        WeightEntry.objects.create(
            user=self.user, value=Decimal("175.0"), unit="lb"
        )
        state = build_health_state(self.user)
        self.assertIn("weight_current", state)
        self.assertIn("weight_unit", state)
        self.assertIn("weight_trend", state)
        self.assertIn("last_weight_entry", state)

    def test_journal_builder_produces_expected_fields(self):
        """Journal builder must produce days_since_entry, entries_30d."""
        from apps.journal.models import JournalEntry
        from apps.core.ai_state.state_builder import build_journal_state

        JournalEntry.objects.create(
            user=self.user,
            title="Test",
            body="Content",
            entry_date=date.today(),
        )
        state = build_journal_state(self.user)
        self.assertIn("last_entry", state)
        self.assertIn("days_since_entry", state)
        self.assertIn("entries_30d", state)
        self.assertIn("entry_frequency", state)

    def test_goals_builder_produces_expected_fields(self):
        """Goals builder must produce active_goal_count."""
        from apps.core.ai_state.state_builder import build_goal_state

        state = build_goal_state(self.user)
        self.assertIn("active_goal_count", state)

    def test_faith_builder_produces_expected_fields(self):
        """Faith builder must produce unanswered_prayers."""
        from apps.core.ai_state.state_builder import build_faith_state

        state = build_faith_state(self.user)
        self.assertIn("unanswered_prayers", state)
        self.assertIn("active_reading_plans", state)
        self.assertIn("reading_streak", state)

    def test_pie_enriches_events_with_sae(self):
        """PIE must enrich events with SAE state — not reconstruct."""
        from apps.core.ai_insights.insight_engine import _enrich_event_with_state

        event = {"event_type": "record_created", "module": "health"}
        enriched = _enrich_event_with_state(self.user, event)
        self.assertIn("user_state", enriched)
        self.assertIsInstance(enriched["user_state"], dict)

    def test_prie_uses_sae_reader(self):
        """PRIE's get_cached_data must be importable from SAE."""
        from apps.core.ai_state.state_reader import get_cached_data

        # Should return None for time-series (falls back to DB — correct)
        result = get_cached_data(self.user, "health", "weight_entries")
        self.assertIsNone(result)

    def test_get_state_value_public_api(self):
        """get_state_value must be importable from the public API."""
        from apps.core.ai_state import get_state_value

        self.assertTrue(callable(get_state_value))


class TestStateGuards(TestCase):
    """Test state guard enforcement helpers."""

    def test_state_first_decorator(self):
        """@state_first should not alter function behavior."""
        from apps.core.ai_state.state_guards import state_first

        @state_first("test reason")
        def sample_func(x):
            return x * 2

        self.assertEqual(sample_func(5), 10)
        self.assertEqual(sample_func._state_first_reason, "test reason")

    def test_require_state_first_is_noop(self):
        """require_state_first is a no-op for documentation."""
        from apps.core.ai_state.state_guards import require_state_first

        # Should not raise
        require_state_first("health.weight_current", "test")
        require_state_first("journal.days_since_entry")
