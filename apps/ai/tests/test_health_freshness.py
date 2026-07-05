"""SAE health freshness — request-path safety contract (updated 2026-07-05).

The `health` module was REMOVED from `ensure_fresh`'s synchronous repair registry
because `build_health_state` is the ~69-query heavy builder, and running it on the
read/chat request thread violates the "no heavy recomputation on the request path"
guarantee. Health snapshot freshness now comes from the write-time async warm
(`enqueue_module_warm(user, "health")`, fired by the health.* event subscribers)
plus the periodic SAME cycle — never a synchronous read-path rebuild.

These tests prove `ensure_fresh(["health"])` NEVER triggers a synchronous rebuild,
even when a newer weight/glucose/sleep row exists. The light manual modules
(journal ~5q, nutrition ~10q) remain eligible and are covered by their own suites.
"""

from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from apps.core.ai_state.state_freshness import ensure_fresh, _MANUAL_MODULE_SOURCES
from apps.core.ai_state.models import UserState

_UPDATE = "apps.core.ai_state.state_updater.update_user_state"


def _user(email):
    from apps.users.models import User
    return User.objects.create_user(email=email, password="x")


def _force_stale(user):
    """Ensure a snapshot exists and force its timestamp into the past."""
    UserState.objects.update_or_create(
        user=user, defaults={"state_data": {"health": {"weight_current": 287.3}}})
    UserState.objects.filter(user=user).update(
        last_updated=timezone.now() - timedelta(hours=2))


class HealthFreshnessRequestPathSafetyTests(TestCase):
    def test_new_weight_does_NOT_trigger_sync_health_rebuild(self):
        """Even with a newer weight row + a stale snapshot, ensure_fresh must
        NOT run the heavy health builder on the request thread."""
        from apps.health.models import WeightEntry
        u = _user("fh_weight@test.com")
        WeightEntry.objects.create(user=u, value=289.9, unit="lb")
        _force_stale(u)
        with mock.patch(_UPDATE) as upd:
            refreshed = ensure_fresh(u, ["health"])
        upd.assert_not_called()
        self.assertNotIn("health", refreshed)

    def test_new_glucose_does_NOT_trigger_sync_health_rebuild(self):
        from apps.health.models import GlucoseEntry
        u = _user("fh_glucose@test.com")
        GlucoseEntry.objects.create(user=u, value=98, unit="mg/dL")
        _force_stale(u)
        with mock.patch(_UPDATE) as upd:
            refreshed = ensure_fresh(u, ["health"])
        upd.assert_not_called()
        self.assertNotIn("health", refreshed)

    def test_health_not_in_sync_repair_registry(self):
        # health is deliberately absent — it is the heavy (~69q) builder and
        # must stay background-only.
        self.assertNotIn("health", _MANUAL_MODULE_SOURCES)

    def test_light_manual_modules_still_registered(self):
        # journal + nutrition are bounded/light and remain eligible.
        self.assertIn("journal", _MANUAL_MODULE_SOURCES)
        self.assertIn("nutrition", _MANUAL_MODULE_SOURCES)

    def test_ensure_health_fresh_wrapper_never_raises(self):
        from apps.ai.cognitive_mode.health_truth import ensure_health_fresh
        u = _user("fh_wrap@test.com")  # no snapshot yet
        ensure_health_fresh(u)  # must not raise (now a cheap no-op)
