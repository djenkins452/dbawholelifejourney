"""
Phase 19.5 — Dashboard/CoS single-source-of-truth parity.

The glucose 7-day summary on the dashboard must equal the canonical
SAE signal ``health.glucose_avg_7d`` that the CoS decision layer
reads via ``get_metric``. Any divergence re-opens the 141 vs 145
bug investigated in Phase 1.

These tests create GlucoseEntry rows, rebuild SAE, and compare the
two sources directly.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.core.ai_state.metric_access import get_metric
from apps.core.ai_state.state_engine import get_state_value, rebuild_user_state
from apps.health.models import GlucoseEntry
from apps.health.views import GlucoseDashboardView
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


def _dashboard_context(user, period=7):
    """Invoke the dashboard view directly — no login/URL layer needed."""
    factory = RequestFactory()
    request = factory.get(f"/health/glucose/?period={period}")
    request.user = user
    view = GlucoseDashboardView()
    view.request = request
    view.kwargs = {}
    return view.get_context_data()


class GlucoseDashboardCanonicalParityTests(TestCase):
    """Dashboard period=7 glucose avg must match SAE canonical."""

    def setUp(self):
        self.user = _make_user("glucose_parity@test.com")
        # Three readings from the last 3 days.
        now = timezone.now()
        for days_ago, value in [(0, 140), (1, 145), (2, 150)]:
            GlucoseEntry.objects.create(
                user=self.user,
                value=Decimal(str(value)),
                unit='mg/dL',
                recorded_at=now - timedelta(days=days_ago),
            )
        # Force SAE state refresh.
        rebuild_user_state(self.user)

    def test_dashboard_avg_matches_sae_glucose_avg_7d(self):
        """The dashboard default (7-day) average must equal the
        canonical SAE signal that CoS reads. Same value, same
        source, every time."""
        ctx = _dashboard_context(self.user, period=7)
        sae = get_metric(self.user, 'health.glucose_avg_7d')

        self.assertIsNotNone(sae, "SAE glucose_avg_7d should be set")
        self.assertIsNotNone(
            ctx['avg_glucose'], "dashboard avg_glucose should be set",
        )
        self.assertEqual(
            ctx['avg_glucose'], sae.value,
            "dashboard period=7 must match SAE canonical value",
        )

    def test_dashboard_records_sae_as_source(self):
        """The dashboard context exposes where the avg came from so
        future audits can verify canonical flow at a glance."""
        ctx = _dashboard_context(self.user, period=7)
        self.assertEqual(
            ctx['avg_glucose_source'],
            'SAE:health.glucose_avg_7d',
        )

    def test_dashboard_uses_raw_for_user_selected_window(self):
        """When the user explicitly selects a non-default period
        (30 / 60 / 90 days), the dashboard falls back to raw
        aggregation. SAE doesn't expose those windows as canonical
        signals yet — the avg_glucose_source makes the path
        explicit."""
        ctx = _dashboard_context(self.user, period=30)
        self.assertIn('avg_glucose', ctx)
        self.assertEqual(
            ctx['avg_glucose_source'],
            'raw:30d_user_selected_window',
        )

    def test_state_engine_and_metric_access_agree(self):
        """Cross-check: `get_state_value` and `get_metric` must
        return the same scalar for the same key. This guards the
        metric-access layer itself."""
        sae_direct = get_state_value(self.user, 'health.glucose_avg_7d')
        sae_via_metric = get_metric(self.user, 'health.glucose_avg_7d')
        self.assertIsNotNone(sae_direct)
        self.assertIsNotNone(sae_via_metric)
        self.assertEqual(sae_direct, sae_via_metric.value)

    def test_repeated_dashboard_reads_are_stable(self):
        """No per-request drift. Reading the dashboard twice in a
        row with no intervening data change must produce the same
        avg — rules out hidden refresh paths."""
        a = _dashboard_context(self.user, period=7)
        b = _dashboard_context(self.user, period=7)
        self.assertEqual(a['avg_glucose'], b['avg_glucose'])
        self.assertEqual(a['avg_glucose_source'], b['avg_glucose_source'])


class GlucoseDashboardNoDataTests(TestCase):
    """When the user has no glucose data, dashboard must show None
    and CoS must also return None — consistent null semantics."""

    def setUp(self):
        self.user = _make_user("glucose_none@test.com")

    def test_both_return_none_when_no_entries(self):
        # No GlucoseEntry rows — both sources should agree on None.
        rebuild_user_state(self.user)
        ctx = _dashboard_context(self.user, period=7)
        sae = get_metric(self.user, 'health.glucose_avg_7d')
        # No entries → dashboard doesn't even populate avg_glucose
        # (the `if glucose_entries.exists()` branch skips).
        self.assertIsNone(ctx.get('avg_glucose'))
        self.assertIsNone(sae)
