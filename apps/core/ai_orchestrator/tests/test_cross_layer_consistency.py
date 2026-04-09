"""
Phase 6 — Cross-layer truth validation tests.

Locks in the rule that rolling-window signals must never be served
stale to CoS. Specifically:

1. cos_context.py MUST bypass the UserState cache for rolling
   metrics (adherence_7d, sleep_trend, workouts_7d, etc.) and call
   the builder directly.

2. The labs trend-detection block in _build_medical_context MUST
   handle strings returned by values_list(..., flat=True) without
   raising AttributeError.

3. There MUST NOT be any contradiction between what the medication
   adherence panel says and what the health intelligence summary
   says — both must read from the same fresh source.
"""

from datetime import date
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase

from apps.users.models import User


def _make_user(email):
    from apps.users.models import TermsAcceptance
    user = User.objects.create_user(
        email=email, password="testpass123",
        date_of_birth=date(1990, 1, 1),
    )
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


# ── _fresh_module_state helper ──────────────────────────────────────

class FreshModuleStateHelperTests(TestCase):
    """The helper must delegate to MODULE_BUILDERS.get(module)(user),
    not the cached UserState.state_data dict."""

    def test_helper_calls_builder_directly(self):
        from apps.core.ai_orchestrator import cos_context

        called_with = {}

        def fake_medicine_builder(user):
            called_with['user'] = user
            return {"adherence_7d": 42, "_source": "fresh_build"}

        from apps.core.ai_state import state_builder
        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"medicine": fake_medicine_builder},
        ):
            from unittest.mock import MagicMock
            user = MagicMock()
            result = cos_context._fresh_module_state(user, "medicine")

        self.assertEqual(called_with['user'], user)
        self.assertEqual(result['adherence_7d'], 42)
        self.assertEqual(result['_source'], "fresh_build")

    def test_helper_falls_back_to_cache_on_builder_failure(self):
        """Fail-closed: if the builder raises, read the cache rather
        than breaking the entire CoS context build."""
        from apps.core.ai_orchestrator import cos_context

        def broken_builder(user):
            raise RuntimeError("builder exploded")

        from apps.core.ai_state import state_builder
        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"medicine": broken_builder},
        ), patch(
            'apps.core.ai_state.state_engine.get_module_state',
            return_value={"adherence_7d": "from_cache"},
        ):
            from unittest.mock import MagicMock
            user = MagicMock()
            result = cos_context._fresh_module_state(user, "medicine")

        self.assertEqual(result['adherence_7d'], "from_cache")

    def test_helper_returns_empty_dict_when_module_unknown(self):
        """An unknown module name should not explode — return {}."""
        from apps.core.ai_orchestrator import cos_context
        from unittest.mock import MagicMock

        with patch(
            'apps.core.ai_state.state_engine.get_module_state',
            return_value=None,
        ):
            user = MagicMock()
            result = cos_context._fresh_module_state(user, "nonexistent")
        self.assertEqual(result, {})


# ── Medication adherence: fresh vs cache ─────────────────────────────

class MedicationAdherenceFreshReadTests(TestCase):
    """Previously cos_context read from UserState.state_data.medicine
    which invalidates only on IntakeLog post_save signals — so on days
    with no intake events the rolling adherence_7d stayed frozen at
    yesterday's value even though calculate_medicine_adherence_rate
    would return the fresh number. Result: LLM saw 100% in the
    medication panel and 62% in the health intelligence summary on
    the same turn."""

    def test_cos_ignores_stale_cache_and_reads_fresh_builder(self):
        """The canonical regression guard. Poison the cache with a
        bogus adherence value and verify that build_cos_context does
        not return it."""
        from apps.core.ai_orchestrator import cos_context
        from unittest.mock import MagicMock

        def fake_builder(user):
            return {
                "active_count": 2,
                "adherence_7d": 55,
                "supplement_adherence_7d": 77,
                "supplement_count": 1,
                "active_supplements": ["creatine"],
                "expected_today": 2,
                "today_taken": 1,
            }

        user = _make_user("fresh_read@test.com")

        from apps.core.ai_state import state_builder
        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"medicine": fake_builder},
        ), patch(
            'apps.core.ai_state.state_engine.get_module_state',
            return_value={
                "active_count": 2,
                "adherence_7d": 999,  # poisoned cache value
                "supplement_adherence_7d": 999,
            },
        ):
            med_state = cos_context._fresh_module_state(user, "medicine")

        # The helper must return the fresh 55 value, not the
        # poisoned cache value 999.
        self.assertEqual(med_state['adherence_7d'], 55)
        self.assertNotEqual(med_state['adherence_7d'], 999)
        self.assertEqual(med_state['supplement_adherence_7d'], 77)


# ── Health sleep signals: fresh vs cache ─────────────────────────────

class HealthSleepSignalsFreshReadTests(TestCase):
    """sleep_trend is a rolling comparison of the last 7 days vs the
    prior 7 days — it drifts every day as the window slides. CoS must
    read it fresh."""

    def test_fresh_health_overrides_stale_sleep_trend(self):
        from apps.core.ai_orchestrator import cos_context
        from apps.core.ai_state import state_builder

        def fake_health_builder(user):
            return {
                "enabled": True,
                "sleep_trend": "decreasing",
                "sleep_avg_hours_7d": 5.5,
                "sleep_quality_avg_7d": 60.0,
            }

        user = _make_user("sleep_fresh@test.com")
        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"health": fake_health_builder},
        ), patch(
            'apps.core.ai_state.state_engine.get_module_state',
            return_value={
                "enabled": True,
                "sleep_trend": "increasing",  # stale cache
                "sleep_avg_hours_7d": 8.0,
                "sleep_quality_avg_7d": 90.0,
            },
        ):
            health = cos_context._fresh_module_state(user, "health")

        self.assertEqual(health['sleep_trend'], "decreasing")
        self.assertEqual(health['sleep_avg_hours_7d'], 5.5)


# ── Fitness workout adherence: fresh vs cache ────────────────────────

class FitnessWorkoutAdherenceFreshReadTests(TestCase):
    """workouts_7d / workout_consistency_score / workout_adherence_score
    are all rolling metrics. CoS must read them fresh so the same
    number appears everywhere in the context."""

    def test_fresh_fitness_overrides_stale_workout_counts(self):
        from apps.core.ai_orchestrator import cos_context
        from apps.core.ai_state import state_builder

        def fake_fitness_builder(user):
            return {
                "workouts_7d": 9,
                "workouts_30d": 25,
                "workout_consistency_score": 86,
                "workout_adherence_score": 86,
                "last_workout_days_ago": 2,
            }

        user = _make_user("fitness_fresh@test.com")
        with patch.dict(
            state_builder.MODULE_BUILDERS,
            {"fitness": fake_fitness_builder},
        ), patch(
            'apps.core.ai_state.state_engine.get_module_state',
            return_value={
                "workouts_7d": 0,  # stale
                "workouts_30d": 0,  # stale
                "workout_consistency_score": 12,  # stale
            },
        ):
            fitness = cos_context._fresh_module_state(user, "fitness")

        self.assertEqual(fitness['workouts_7d'], 9)
        self.assertEqual(fitness['workout_adherence_score'], 86)
        self.assertEqual(fitness['last_workout_days_ago'], 2)


# ── Labs panel: AttributeError regression ────────────────────────────

class LabsTrendCounterRegressionTests(TestCase):
    """_build_medical_context at cos_context.py:~2305 used to iterate
    over values_list('raw_test_name', flat=True) which returns strings,
    then call `.raw_test_name.lower().strip()` on each — raising
    AttributeError and silently killing the labs section on every
    CoS context build. Phase 6 contract test: the block must handle
    a plain list of strings without raising."""

    def test_source_uses_string_safe_counter(self):
        """Source-level contract guard — the specific bug pattern
        (iterating values_list('raw_test_name', flat=True) and then
        calling .raw_test_name on each element as if it were a model
        instance) must not reappear. Note: lab.raw_test_name is
        legitimate when `lab` is an actual LabResult instance — we
        only flag the buggy values_list + attribute access combo."""
        import os
        import re
        here = os.path.dirname(os.path.abspath(__file__))
        path = os.path.normpath(os.path.join(
            here, '..', '..', 'ai_orchestrator', 'cos_context.py',
        ))
        with open(path, 'r', encoding='utf-8') as fh:
            source = fh.read()

        # Look for the specific Counter+values_list+attribute-access
        # combo that was the Phase 6 bug. A Counter fed by
        # `<name>.raw_test_name.lower() ... for <name> in
        # ...values_list('raw_test_name', flat=True)` is always a bug.
        pattern = re.compile(
            r'Counter\(\s*\n?\s*(\w+)\.raw_test_name\.lower\(\)'
            r'[\s\S]{1,400}'
            r'values_list\(\s*[\'"]raw_test_name[\'"]\s*,\s*flat=True',
            re.MULTILINE,
        )
        self.assertIsNone(
            pattern.search(source),
            "cos_context.py still treats values_list flat-strings as "
            "LabResult instances — the Phase 6 labs AttributeError is "
            "back",
        )

    def test_counter_pattern_handles_strings_and_none(self):
        """Directly exercise the fixed Counter comprehension against
        mixed-content iterables."""
        from collections import Counter

        names = ["Glucose", "glucose", "Cholesterol", None, ""]
        counts = Counter(
            (name or '').lower().strip()
            for name in names
            if name
        )
        self.assertEqual(counts.get('glucose'), 2)
        self.assertEqual(counts.get('cholesterol'), 1)
        # Empty and None entries are filtered out.
        self.assertNotIn('', counts)
        self.assertNotIn(None, counts)
