"""
Phase 17 — Single Source of Truth Enforcement tests.

Verifies that:
1. Every health domain produces a canonical _status + _status_reason
2. Sleep tile and Needs Attention always agree (no contradiction)
3. Status values are from the allowed set
4. health_priority_service reads _status, not raw thresholds
"""

from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

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


VALID_STATUSES = frozenset({
    'excellent', 'good', 'fair', 'poor', 'no_data',
})


class AllDomainsHaveCanonicalStatusTests(TestCase):
    """Every health domain must produce _status + _status_reason."""

    def setUp(self):
        self.user = _make_user("canonical@test.com")

    def test_all_status_keys_present(self):
        from apps.core.ai_state.state_builder import build_health_state
        state = build_health_state(self.user)

        for domain in (
            'sleep', 'weight', 'bp', 'hr', 'spo2',
            'glucose', 'steps', 'water',
        ):
            status_key = f"{domain}_status"
            reason_key = f"{domain}_status_reason"
            self.assertIn(
                status_key, state,
                f"Missing canonical {status_key} in health state",
            )
            self.assertIn(
                reason_key, state,
                f"Missing canonical {reason_key} in health state",
            )

    def test_all_statuses_are_valid_values(self):
        from apps.core.ai_state.state_builder import build_health_state
        state = build_health_state(self.user)

        for domain in (
            'sleep', 'weight', 'bp', 'hr', 'spo2',
            'glucose', 'steps', 'water',
        ):
            status = state.get(f"{domain}_status")
            self.assertIn(
                status, VALID_STATUSES,
                f"{domain}_status={status!r} not in allowed set",
            )

    def test_all_reasons_are_non_empty_strings(self):
        from apps.core.ai_state.state_builder import build_health_state
        state = build_health_state(self.user)

        for domain in (
            'sleep', 'weight', 'bp', 'hr', 'spo2',
            'glucose', 'steps', 'water',
        ):
            reason = state.get(f"{domain}_status_reason")
            self.assertIsInstance(reason, str)
            self.assertTrue(len(reason) > 0)


class SleepTileAndAttentionAlwaysAgreeTests(TestCase):
    """The sleep contradiction bug: tile said 'Excellent' while
    attention said 'Sleep has been short lately'. Phase 17 resolves
    this by making both read from the same sleep_status."""

    def setUp(self):
        self.user = _make_user("sleep_agree@test.com")

    def _seed_sleep(self, days_ago, minutes, quality=None):
        from apps.health.models import SleepEntry
        wake = timezone.now() - timedelta(days=days_ago)
        bed = wake - timedelta(minutes=minutes)
        SleepEntry.objects.create(
            user=self.user,
            sleep_date=wake.date(),
            bedtime=bed,
            wake_time=wake,
            total_duration_minutes=minutes,
            quality_score=quality,
        )

    def test_short_week_high_quality_last_night_resolves_to_fair(self):
        """Danny's exact scenario: 5.8h last night, quality 87
        ('Excellent' on the model), but 7d avg < 6h. The resolved
        status must be 'fair' — NOT 'excellent'."""
        # Seed 7 nights: short duration but good quality
        for d in range(1, 8):
            self._seed_sleep(d, 330, quality=85)  # 5.5h, quality 85

        from apps.core.ai_state.state_builder import build_health_state
        state = build_health_state(self.user)

        self.assertEqual(state['sleep_status'], 'fair')
        self.assertIn('short', state['sleep_status_reason'].lower())

        # Now check what health_priority_service produces
        from apps.health.services.health_priority_service import (
            _eval_sleep,
        )
        items = _eval_sleep(state, timezone.now())
        if items:
            # The attention item's message must match the SAE reason
            self.assertNotIn("Excellent", items[0].get('title', ''))

    def test_strong_week_resolves_to_excellent(self):
        """7+ hours every night → excellent."""
        for d in range(1, 8):
            self._seed_sleep(d, 450, quality=90)  # 7.5h

        from apps.core.ai_state.state_builder import build_health_state
        state = build_health_state(self.user)

        self.assertEqual(state['sleep_status'], 'excellent')
        self.assertIn('on target', state['sleep_status_reason'].lower())


class SleepLastNightFieldsTests(TestCase):
    """The SAE must provide last-night-specific fields so the tile
    can show the most recent entry without querying the model."""

    def setUp(self):
        self.user = _make_user("sleep_last@test.com")

    def test_last_night_fields_populated(self):
        from apps.health.models import SleepEntry
        wake = timezone.now() - timedelta(hours=2)
        bed = wake - timedelta(hours=6)
        SleepEntry.objects.create(
            user=self.user,
            sleep_date=wake.date(),
            bedtime=bed,
            wake_time=wake,
            total_duration_minutes=360,
            quality_score=75,
        )

        from apps.core.ai_state.state_builder import build_health_state
        state = build_health_state(self.user)

        self.assertEqual(state['sleep_last_night_hours'], 6.0)
        self.assertIsNotNone(state.get('sleep_last_night_quality'))
        self.assertIsNotNone(state.get('sleep_last_night_date'))


class HealthPriorityServiceReadsStatusTests(TestCase):
    """health_priority_service must use the canonical _status keys,
    not its own threshold computations."""

    def test_source_reads_sleep_status_not_avg_duration(self):
        """The service source code must reference sleep_status,
        not hardcode < 360 / >= 420 thresholds."""
        import os
        here = os.path.dirname(os.path.abspath(__file__))
        path = os.path.normpath(os.path.join(
            here, '..', '..', 'health', 'services',
            'health_priority_service.py',
        ))
        with open(path, 'r', encoding='utf-8') as fh:
            source = fh.read()

        # The old threshold patterns must be gone
        self.assertNotIn(
            'avg < 360',
            source,
            "health_priority_service still uses raw < 360 threshold "
            "instead of canonical sleep_status",
        )
        self.assertNotIn(
            'avg >= 420',
            source,
            "health_priority_service still uses raw >= 420 threshold "
            "instead of canonical sleep_status",
        )
        # Must reference the canonical status
        self.assertIn('sleep_status', source)


# ══════════════════════════════════════════════════════════════
# HARD ENFORCEMENT: no model-object health references in template
# ══════════════════════════════════════════════════════════════

class TemplateNoModelObjectReferencesTests(TestCase):
    """The health dashboard template must NOT reference raw model
    objects for health domain display. Every health value must come
    from hs.* (SAE state) or ms.* (medicine state)."""

    def _get_template_source(self):
        import os
        here = os.path.dirname(os.path.abspath(__file__))
        path = os.path.normpath(os.path.join(
            here, '..', '..', '..', 'templates', 'health', 'home.html',
        ))
        with open(path, 'r', encoding='utf-8') as fh:
            return fh.read()

    def test_no_latest_sleep_model_access(self):
        src = self._get_template_source()
        self.assertNotIn(
            'latest_sleep.total_hours',
            src,
            "Template still reads latest_sleep.total_hours (raw model)",
        )
        self.assertNotIn(
            'latest_sleep.quality_display',
            src,
            "Template still reads latest_sleep.quality_display (model property)",
        )
        self.assertNotIn(
            'latest_sleep.quality_score',
            src,
            "Template still reads latest_sleep.quality_score (raw model field)",
        )

    def test_no_latest_glucose_model_access(self):
        src = self._get_template_source()
        self.assertNotIn(
            'latest_glucose.value',
            src,
            "Template still reads latest_glucose.value (raw model)",
        )
        self.assertNotIn(
            'latest_glucose.get_context_display',
            src,
            "Template still reads latest_glucose.get_context_display (model method)",
        )

    def test_no_latest_heart_rate_model_access(self):
        src = self._get_template_source()
        self.assertNotIn(
            'latest_heart_rate.bpm',
            src,
            "Template still reads latest_heart_rate.bpm (raw model)",
        )
        self.assertNotIn(
            'latest_heart_rate.get_context_display',
            src,
            "Template still reads latest_heart_rate.get_context_display",
        )

    def test_no_latest_blood_pressure_model_access(self):
        src = self._get_template_source()
        self.assertNotIn(
            'latest_blood_pressure.reading',
            src,
            "Template still reads latest_blood_pressure.reading (raw model)",
        )
        self.assertNotIn(
            'latest_blood_pressure.category_display',
            src,
            "Template still reads latest_blood_pressure.category_display (model method)",
        )

    def test_no_latest_blood_oxygen_model_access(self):
        src = self._get_template_source()
        self.assertNotIn(
            'latest_blood_oxygen.spo2',
            src,
            "Template still reads latest_blood_oxygen.spo2 (raw model)",
        )
        self.assertNotIn(
            'latest_blood_oxygen.category_display',
            src,
            "Template still reads latest_blood_oxygen.category_display",
        )

    def test_no_latest_weight_model_access_for_display(self):
        src = self._get_template_source()
        self.assertNotIn(
            'latest_weight.value',
            src,
            "Template still reads latest_weight.value (raw model)",
        )

    def test_no_view_computed_averages(self):
        """View-computed averages must not appear in the template —
        they must come from SAE state."""
        src = self._get_template_source()
        self.assertNotIn(
            'avg_resting_hr',
            src,
            "Template still uses view-computed avg_resting_hr",
        )
        self.assertNotIn(
            'avg_fasting_glucose',
            src,
            "Template still uses view-computed avg_fasting_glucose",
        )
        self.assertNotIn(
            'avg_systolic',
            src,
            "Template still uses view-computed avg_systolic",
        )
        self.assertNotIn(
            'avg_spo2',
            src,
            "Template still uses view-computed avg_spo2",
        )
