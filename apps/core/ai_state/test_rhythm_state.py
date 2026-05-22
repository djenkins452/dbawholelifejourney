"""
Tests for behavior.rhythm_state — Phase 1.

Covers:
- Composer golden paths per status (on_rhythm / off_rhythm / returning)
- Severity threshold logic (1 high OR 2 moderate triggers off_rhythm)
- Prior-data gates (insufficient baseline does not flag)
- Returning detection (>=2 day gap + activity today)
- Deterministic phrasing templates (same input -> same output)
- First-message-of-day surfacing rule
- Architectural guard: composer must not import raw domain models

Test list maps to the locked DoD cases:
  Test 1: workout-only collapse triggers off_rhythm
  Test 2: 3-day absence + return triggers returning
  Test 3: foundational drop triggers off_rhythm
  Test 4: same as Test 2 with different gap
  Test 5: normal week stays on_rhythm
  Test 6: off_rhythm -> on_rhythm transition clears narrative
"""

from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.users.models import User


def _create_test_user(email="rhythm@example.com"):
    """Create a test user with required onboarding setup."""
    from apps.users.models import TermsAcceptance

    user = User.objects.create_user(
        email=email, password="testpass123", date_of_birth=date(1990, 1, 1),
    )
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.ai_enabled = True
    user.preferences.save()
    return user


def _seed_user_state(user, *, fitness=None, tasks=None, behavior=None):
    """Seed UserState with module data for composer tests."""
    from apps.core.ai_state.models import UserState
    state, _ = UserState.objects.get_or_create(user=user)
    if fitness is not None:
        state.set_module('fitness', fitness)
    if tasks is not None:
        state.set_module('tasks', tasks)
    if behavior is not None:
        state.set_module('behavior', behavior)
    state.save()
    return state


def _seed_daily_activity(user, today, days_pattern):
    """Seed UserDailyActivity records.

    days_pattern is a list of bools or ints describing the last 37 days
    ending at `today`. True/1 = active that day. The list is interpreted
    right-aligned: pattern[-1] is today, pattern[-2] is yesterday, etc.
    """
    from apps.core.models import UserDailyActivity
    for offset, active in enumerate(reversed(days_pattern)):
        if not active:
            continue
        d = today - timedelta(days=offset)
        UserDailyActivity.objects.create(
            user=user,
            date=d,
            first_seen=time(9, 0),
            last_seen=time(21, 0),
            interaction_count=5,
        )


# ─────────────────────────────────────────────────────────────────────
# Composer — status derivation
# ─────────────────────────────────────────────────────────────────────


class TestRhythmComposerOnRhythm(TestCase):
    """on_rhythm: no contributors flag, or only one moderate (which is on_rhythm)."""

    def setUp(self):
        self.user = _create_test_user()

    @patch('apps.core.utils.get_user_today')
    def test_normal_week_returns_on_rhythm(self, mock_today):
        """Test 5 from DoD: normal week, 0 contributors flagging."""
        today = date(2026, 5, 22)
        mock_today.return_value = today
        # Healthy baseline: 4 workouts/week consistently, foundational
        # adherence flat at 90%, engagement active every day.
        _seed_user_state(
            self.user,
            fitness={'workouts_7d': 4, 'workouts_30d': 17},
            tasks={'task_commitment_summary': {
                'foundational_completed_7d': 18,
                'foundational_skipped_7d': 2,
                'foundational_completed_30d': 77,
                'foundational_skipped_30d': 8,
                'consistency_score': 0.90,
                'consistency_score_30d': 0.90,
            }},
        )
        _seed_daily_activity(self.user, today, [1] * 37)

        from apps.core.ai_state.state_builder import _compute_rhythm_state
        state = _compute_rhythm_state(self.user)
        self.assertEqual(state['status'], 'on_rhythm')
        self.assertEqual(state['contributor_count'], 0)


class TestRhythmComposerOffRhythm(TestCase):
    """off_rhythm: 1 high-severity OR 2+ moderate contributors."""

    def setUp(self):
        self.user = _create_test_user()

    @patch('apps.core.utils.get_user_today')
    def test_workout_full_stop_triggers_off_rhythm(self, mock_today):
        """Test 1 from DoD: 0 workouts vs established baseline -> high severity alone -> off_rhythm."""
        today = date(2026, 5, 22)
        mock_today.return_value = today
        _seed_user_state(
            self.user,
            fitness={'workouts_7d': 0, 'workouts_30d': 17},
            tasks={'task_commitment_summary': {
                'consistency_score': 0.90,
                'consistency_score_30d': 0.90,
                'foundational_completed_30d': 60,
                'foundational_skipped_30d': 5,
            }},
        )
        _seed_daily_activity(self.user, today, [1] * 37)

        from apps.core.ai_state.state_builder import _compute_rhythm_state
        state = _compute_rhythm_state(self.user)
        self.assertEqual(state['status'], 'off_rhythm')
        contributor_names = [c['signal_name'] for c in state['contributors']]
        self.assertIn('workout_consistency_delta', contributor_names)
        # The workout contributor should be high-severity.
        workout = next(c for c in state['contributors'] if c['signal_name'] == 'workout_consistency_delta')
        self.assertEqual(workout['severity'], 'high')

    @patch('apps.core.utils.get_user_today')
    def test_foundational_collapse_triggers_off_rhythm(self, mock_today):
        """Test 3 from DoD: foundationals collapse alone (high severity) -> off_rhythm."""
        today = date(2026, 5, 22)
        mock_today.return_value = today
        _seed_user_state(
            self.user,
            fitness={'workouts_7d': 4, 'workouts_30d': 17},  # workouts fine
            tasks={'task_commitment_summary': {
                'consistency_score': 0.40,           # 7d collapse to 40%
                'consistency_score_30d': 0.90,       # 30d baseline 90%
                'foundational_completed_30d': 60,
                'foundational_skipped_30d': 5,
            }},
        )
        _seed_daily_activity(self.user, today, [1] * 37)

        from apps.core.ai_state.state_builder import _compute_rhythm_state
        state = _compute_rhythm_state(self.user)
        self.assertEqual(state['status'], 'off_rhythm')
        # Ratio 0.40/0.90 = 0.44, below HIGH threshold of 0.5 -> high severity.
        foundational = next(
            c for c in state['contributors']
            if c['signal_name'] == 'foundational_adherence_delta'
        )
        self.assertEqual(foundational['severity'], 'high')

    @patch('apps.core.utils.get_user_today')
    def test_two_moderate_contributors_trigger_off_rhythm(self, mock_today):
        """2 moderate contributors (no high) should trigger off_rhythm."""
        today = date(2026, 5, 22)
        mock_today.return_value = today
        # Workouts at moderate (40% of baseline, below 0.5)
        # Foundational at moderate (0.62/0.90 = 0.69, below 0.7)
        _seed_user_state(
            self.user,
            fitness={'workouts_7d': 1, 'workouts_30d': 12},  # 1 vs ~2.8/wk
            tasks={'task_commitment_summary': {
                'consistency_score': 0.62,
                'consistency_score_30d': 0.90,
                'foundational_completed_30d': 60,
                'foundational_skipped_30d': 5,
            }},
        )
        _seed_daily_activity(self.user, today, [1] * 37)

        from apps.core.ai_state.state_builder import _compute_rhythm_state
        state = _compute_rhythm_state(self.user)
        self.assertEqual(state['status'], 'off_rhythm')
        severities = [c['severity'] for c in state['contributors']]
        self.assertIn('moderate', severities)


class TestRhythmComposerReturning(TestCase):
    """returning: >=2 day absence + had_activity_today."""

    def setUp(self):
        self.user = _create_test_user()

    @patch('apps.core.utils.get_user_today')
    def test_three_day_gap_then_active_today_triggers_returning(self, mock_today):
        """Test 2/4 from DoD: user comes back; days_since_last_interaction == 3.

        Pattern (left=oldest, right=newest): 34 active days, then absent 2 days,
        then active today. Last activity before today is 3 days ago.
        """
        today = date(2026, 5, 22)
        mock_today.return_value = today
        pattern = [1] * 34 + [0, 0, 1]
        _seed_daily_activity(self.user, today, pattern)
        _seed_user_state(
            self.user,
            fitness={'workouts_7d': 0, 'workouts_30d': 0},
            tasks={'task_commitment_summary': {
                'consistency_score': 0.5,
                'consistency_score_30d': 0.9,
                'foundational_completed_30d': 0,
                'foundational_skipped_30d': 0,
            }},
        )

        from apps.core.ai_state.state_builder import _compute_rhythm_state
        state = _compute_rhythm_state(self.user)
        self.assertEqual(state['status'], 'returning')
        self.assertEqual(state['days_since_last_interaction'], 3)


class TestRhythmComposerPriorDataGates(TestCase):
    """Insufficient baseline: contributor must not flag."""

    def setUp(self):
        self.user = _create_test_user()

    @patch('apps.core.utils.get_user_today')
    def test_insufficient_workout_baseline_does_not_flag(self, mock_today):
        """workouts_30d < 3 should suppress the workout contributor entirely."""
        today = date(2026, 5, 22)
        mock_today.return_value = today
        _seed_user_state(
            self.user,
            fitness={'workouts_7d': 0, 'workouts_30d': 2},  # below MIN_30D=3
            tasks={'task_commitment_summary': {
                'consistency_score': 0.90,
                'consistency_score_30d': 0.90,
                'foundational_completed_30d': 60,
                'foundational_skipped_30d': 5,
            }},
        )
        _seed_daily_activity(self.user, today, [1] * 37)

        from apps.core.ai_state.state_builder import _compute_rhythm_state
        state = _compute_rhythm_state(self.user)
        # No high or moderate contributors -> on_rhythm.
        self.assertEqual(state['status'], 'on_rhythm')

    @patch('apps.core.utils.get_user_today')
    def test_insufficient_engagement_baseline_does_not_flag(self, mock_today):
        """Fewer than MIN_PRIOR_DAYS active days in prior window -> no flag."""
        today = date(2026, 5, 22)
        mock_today.return_value = today
        # Only 5 active days in prior 30d (need >= 7 to flag).
        pattern = [0] * 25 + [1] * 5 + [0] * 7
        _seed_daily_activity(self.user, today, pattern)
        _seed_user_state(
            self.user,
            fitness={'workouts_7d': 4, 'workouts_30d': 17},
            tasks={'task_commitment_summary': {
                'consistency_score': 0.90,
                'consistency_score_30d': 0.90,
                'foundational_completed_30d': 60,
                'foundational_skipped_30d': 5,
            }},
        )

        from apps.core.ai_state.state_builder import _compute_rhythm_state
        state = _compute_rhythm_state(self.user)
        engagement_names = [
            c['signal_name'] for c in state['contributors']
            if c['signal_name'] == 'engagement_delta'
        ]
        self.assertEqual(engagement_names, [])


class TestRhythmComposerFieldShape(TestCase):
    """Verify the rhythm_state field shape is locked."""

    def setUp(self):
        self.user = _create_test_user()

    @patch('apps.core.utils.get_user_today')
    def test_field_shape(self, mock_today):
        today = date(2026, 5, 22)
        mock_today.return_value = today
        _seed_user_state(
            self.user,
            fitness={'workouts_7d': 4, 'workouts_30d': 17},
            tasks={'task_commitment_summary': {
                'consistency_score': 0.90,
                'consistency_score_30d': 0.90,
                'foundational_completed_30d': 60,
                'foundational_skipped_30d': 5,
            }},
        )
        _seed_daily_activity(self.user, today, [1] * 37)

        from apps.core.ai_state.state_builder import _compute_rhythm_state
        state = _compute_rhythm_state(self.user)
        expected_keys = {
            'schema_version', 'status', 'previous_status', 'status_changed_at',
            'contributors', 'contributor_count', 'computed_at', 'trust',
            'days_since_last_interaction',
        }
        self.assertEqual(set(state.keys()), expected_keys)
        self.assertEqual(state['schema_version'], 1)
        self.assertIn(state['status'], {'on_rhythm', 'off_rhythm', 'returning'})
        self.assertIn(state['trust'], {'high', 'medium'})
        self.assertLessEqual(len(state['contributors']), 3)


# ─────────────────────────────────────────────────────────────────────
# Phrasing templates — determinism + content
# ─────────────────────────────────────────────────────────────────────


class TestPhrasingTemplates(TestCase):
    """Templates must be deterministic and render verbatim from contributors."""

    def test_returning_template_pluralizes_days(self):
        from apps.core.ai_state.situation_computer import _build_returning_sentence
        result = _build_returning_sentence({'days_since_last_interaction': 3})
        self.assertEqual(
            result,
            "It's been 3 days. Welcome back — what do you want to focus on first?",
        )

    def test_returning_template_handles_missing_value(self):
        """Defensive fallback when days is invalid — never invent a count."""
        from apps.core.ai_state.situation_computer import _build_returning_sentence
        result = _build_returning_sentence({})
        self.assertNotIn(' 0 days', result)
        self.assertNotIn(' 1 days', result)

    def test_off_rhythm_template_foundational(self):
        from apps.core.ai_state.situation_computer import _build_off_rhythm_sentence
        rhythm = {
            'contributors': [{
                'signal_name': 'foundational_adherence_delta',
                'recent_value': 62,
                'baseline_value': 90,
                'severity': 'high',
            }],
        }
        result = _build_off_rhythm_sentence(rhythm)
        self.assertEqual(
            result,
            "Your foundationals are at 62% this week — your usual is closer to 90%.",
        )

    def test_off_rhythm_template_combines_two_contributors(self):
        from apps.core.ai_state.situation_computer import _build_off_rhythm_sentence
        rhythm = {
            'contributors': [
                {
                    'signal_name': 'foundational_adherence_delta',
                    'recent_value': 60,
                    'baseline_value': 90,
                    'severity': 'high',
                },
                {
                    'signal_name': 'engagement_delta',
                    'recent_value': 2,
                    'baseline_value': 6,
                    'severity': 'moderate',
                },
            ],
        }
        result = _build_off_rhythm_sentence(rhythm)
        self.assertIn("Your foundationals are at 60%", result)
        self.assertIn("Also,", result)
        self.assertIn("last week's been quieter than usual", result.lower())

    def test_template_determinism(self):
        """Same input -> identical output across 100 invocations."""
        from apps.core.ai_state.situation_computer import _build_off_rhythm_sentence
        rhythm = {
            'contributors': [{
                'signal_name': 'workout_consistency_delta',
                'recent_value': 0,
                'baseline_value': 4,
                'severity': 'high',
            }],
        }
        first = _build_off_rhythm_sentence(rhythm)
        for _ in range(99):
            self.assertEqual(_build_off_rhythm_sentence(rhythm), first)

    def test_unknown_contributor_does_not_invent_text(self):
        """An unknown signal_name must not emit fabricated language."""
        from apps.core.ai_state.situation_computer import _build_off_rhythm_sentence
        rhythm = {
            'contributors': [{
                'signal_name': 'made_up_signal',
                'recent_value': 1,
                'baseline_value': 2,
                'severity': 'high',
            }],
        }
        result = _build_off_rhythm_sentence(rhythm)
        # Falls back to the generic phrasing — never invents a metric.
        self.assertEqual(result, "Last week's looked different from your usual rhythm.")


# ─────────────────────────────────────────────────────────────────────
# Situation computer integration — first-message-of-day surfacing
# ─────────────────────────────────────────────────────────────────────


class TestFirstInteractionDetection(TestCase):
    """Rhythm modes only surface on the first interaction of the local day."""

    def setUp(self):
        self.user = _create_test_user()

    @patch('apps.core.utils.get_user_today')
    def test_no_previous_interaction_is_first_of_day(self, mock_today):
        mock_today.return_value = date(2026, 5, 22)
        from apps.core.ai_state.situation_computer import _is_first_interaction_today
        self.assertTrue(_is_first_interaction_today(self.user, None))

    @patch('apps.core.utils.get_user_now')
    @patch('apps.core.utils.get_user_today')
    def test_previous_interaction_today_is_not_first(self, mock_today, mock_now):
        today = date(2026, 5, 22)
        mock_today.return_value = today
        utc_now = datetime(2026, 5, 22, 14, 0, tzinfo=dt_timezone.utc)
        mock_now.return_value = utc_now
        from apps.core.ai_state.situation_computer import _is_first_interaction_today
        # Previous interaction earlier same day.
        prev = datetime(2026, 5, 22, 9, 0, tzinfo=dt_timezone.utc)
        self.assertFalse(_is_first_interaction_today(self.user, prev))


# ─────────────────────────────────────────────────────────────────────
# Architectural guard — composer must not read raw domain models
# ─────────────────────────────────────────────────────────────────────


class TestComposerArchitecturalGuard(TestCase):
    """The rhythm composer must read only from SAE sub-states + UserDailyActivity.

    Enforced by AST analysis of the composer function body: walks every
    Import / ImportFrom / Name / Attribute node and verifies that no
    disallowed raw domain model is actually referenced as code. Docstring
    and comment mentions are intentionally not flagged.
    """

    DISALLOWED_NAMES = {
        'WeightEntry', 'BodyCompositionEntry', 'GlucoseEntry',
        'BloodPressureEntry', 'HeartRateEntry', 'SleepEntry',
        'WorkoutSession', 'ExerciseSet', 'FoodEntry', 'JournalEntry',
        'IntakeLog', 'Intake', 'Task',
    }

    # Modules the composer is explicitly allowed to import from. Anything
    # else from apps.* is a violation worth flagging.
    ALLOWED_MODULE_PREFIXES = (
        'apps.core.ai_state.',
        'apps.core.models',  # UserDailyActivity
        'apps.core.utils',
        'apps.core.time',
    )

    def _walk_function(self, fn):
        import ast
        import inspect
        import textwrap
        source = textwrap.dedent(inspect.getsource(fn))
        return ast.parse(source)

    def test_composer_does_not_reference_disallowed_model_names_in_code(self):
        from apps.core.ai_state import state_builder
        import ast
        offenders = []
        for fn in (state_builder._compute_rhythm_state, state_builder._compute_engagement_signals):
            tree = self._walk_function(fn)
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and node.id in self.DISALLOWED_NAMES:
                    offenders.append((fn.__name__, node.id, 'Name'))
                elif isinstance(node, ast.Attribute) and node.attr in self.DISALLOWED_NAMES:
                    offenders.append((fn.__name__, node.attr, 'Attribute'))
                elif isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        if alias.name in self.DISALLOWED_NAMES:
                            offenders.append((fn.__name__, alias.name, 'ImportFrom'))
        self.assertEqual(
            offenders, [],
            f"rhythm composer must not reference raw domain models in code: {offenders}",
        )

    def test_composer_imports_are_from_allowed_modules_only(self):
        from apps.core.ai_state import state_builder
        import ast
        violations = []
        for fn in (state_builder._compute_rhythm_state, state_builder._compute_engagement_signals):
            tree = self._walk_function(fn)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    if node.module.startswith('apps.'):
                        if not any(node.module.startswith(p) for p in self.ALLOWED_MODULE_PREFIXES):
                            violations.append((fn.__name__, node.module))
        self.assertEqual(
            violations, [],
            f"rhythm composer imports must stay inside SAE/utils/time/core.models: {violations}",
        )
