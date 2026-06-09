"""SAE health freshness — fresh-by-design source fix.

Proves ensure_fresh DETECTS staleness and triggers a health rebuild when a newer
weight / glucose / sleep row exists (root cause of the stale-weight regression),
and that the no-new-rows case does NOT rebuild. The rebuild itself
(update_user_state) is mocked so the test doesn't depend on a fully-provisioned
user; the single-source (nutrition/journal) path is covered by the nutrition suite.
"""

from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from apps.core.ai_state.state_freshness import ensure_fresh
from apps.core.ai_state.models import UserState

_UPDATE = "apps.core.ai_state.state_updater.update_user_state"


def _user(email):
    from apps.users.models import User
    return User.objects.create_user(email=email, password="x")


def _force_stale(user):
    """Ensure a snapshot exists and force its timestamp into the past — called
    LAST, after entry creation, so a write-time signal can't un-stale it."""
    UserState.objects.update_or_create(
        user=user, defaults={"state_data": {"health": {"weight_current": 287.3}}})
    UserState.objects.filter(user=user).update(
        last_updated=timezone.now() - timedelta(hours=2))


class HealthFreshnessTests(TestCase):
    def test_new_weight_triggers_health_rebuild(self):
        from apps.health.models import WeightEntry
        u = _user("fh_weight@test.com")
        WeightEntry.objects.create(user=u, value=289.9, unit="lb")
        _force_stale(u)
        with mock.patch(_UPDATE) as upd:
            refreshed = ensure_fresh(u, ["health"])
        upd.assert_called_once_with(u, "health")
        self.assertIn("health", refreshed)

    def test_new_glucose_triggers_health_rebuild(self):
        from apps.health.models import GlucoseEntry
        u = _user("fh_glucose@test.com")
        GlucoseEntry.objects.create(user=u, value=98, unit="mg/dL")
        _force_stale(u)
        with mock.patch(_UPDATE) as upd:
            refreshed = ensure_fresh(u, ["health"])
        self.assertIn("health", refreshed)

    def test_sleep_registered_as_health_source(self):
        # SleepEntry is a registered health freshness source (it flows through
        # the same multi-source loop proven by the weight/glucose tests).
        from apps.core.ai_state.state_freshness import _MANUAL_MODULE_SOURCES
        sources = _MANUAL_MODULE_SOURCES["health"]
        models = [path for path, _ in sources]
        self.assertIn("apps.health.models.WeightEntry", models)
        self.assertIn("apps.health.models.GlucoseEntry", models)
        self.assertIn("apps.health.models.SleepEntry", models)

    def test_no_new_rows_no_rebuild(self):
        u = _user("fh_none@test.com")
        # Snapshot current (last_updated = now); no newer rows.
        UserState.objects.create(user=u, state_data={"health": {"weight_current": 250.0}})
        with mock.patch(_UPDATE) as upd:
            refreshed = ensure_fresh(u, ["health"])
        self.assertNotIn("health", refreshed)
        upd.assert_not_called()

    def test_ensure_health_fresh_wrapper_never_raises(self):
        from apps.ai.cognitive_mode.health_truth import ensure_health_fresh
        u = _user("fh_wrap@test.com")  # no snapshot yet
        ensure_health_fresh(u)  # must not raise
