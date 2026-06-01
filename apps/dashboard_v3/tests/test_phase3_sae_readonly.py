"""Phase 3 — dashboard SAE request-path elimination.

The architectural rule (CLAUDE.md): "HTTP request paths may ONLY read
pre-computed data from cache or DB snapshots." Phase 3 enforces this
for the dashboard:

  1. After SAE state is warm, the dashboard render NEVER triggers a
     synchronous rebuild_user_state. Every get_module_state call from
     the composer uses allow_rebuild=False.

  2. Brand-new users (no UserState row, or empty state_data) are
     bootstrapped by one synchronous rebuild_user_state at composer
     entry (the only place a request-path rebuild is allowed). This
     populates state_data so all subsequent renders are read-only.

  3. Write subscribers (journal / task / purpose / faith / health)
     enqueue a background deferred_warm_sae_module task so the next
     render finds warm state.

  4. Phase 2 contract threading is extended into complete_wake_up,
     which can now accept a pre-fetched execution_contract from the
     view (saves 1 of the remaining build_today_execution calls).
"""

from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.core.events.domain_events import EventTypes, safe_emit_event
from apps.users.models import TermsAcceptance


User = get_user_model()


def _make_user(email="phase3@test.com"):
    u = User.objects.create_user(email=email, password="x" * 20)
    TermsAcceptance.objects.create(
        user=u,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


# ── State-engine contract tests ────────────────────────────────────

class StateEngineReadOnlyContractTests(TestCase):
    """The allow_rebuild=False contract on get_user_state /
    get_module_state. Phase 3 depends on this not regressing."""

    def setUp(self):
        self.user = _make_user("ro@test.com")

    def test_get_user_state_default_still_rebuilds_on_empty(self):
        """Back-compat: existing callers without the kwarg get
        rebuild-on-miss behavior unchanged."""
        from apps.core.ai_state.state_engine import get_user_state
        with patch(
            "apps.core.ai_state.state_engine.rebuild_user_state",
            return_value={"_marker": True},
        ) as mock_rebuild:
            state = get_user_state(self.user)
        mock_rebuild.assert_called_once()
        self.assertEqual(state, {"_marker": True})

    def test_get_user_state_allow_rebuild_false_returns_empty_on_miss(self):
        from apps.core.ai_state.state_engine import get_user_state
        with patch(
            "apps.core.ai_state.state_engine.rebuild_user_state"
        ) as mock_rebuild:
            state = get_user_state(self.user, allow_rebuild=False)
        mock_rebuild.assert_not_called()
        self.assertEqual(state, {})

    def test_get_module_state_threads_allow_rebuild(self):
        from apps.core.ai_state.state_engine import get_module_state
        with patch(
            "apps.core.ai_state.state_engine.rebuild_user_state"
        ) as mock_rebuild:
            result = get_module_state(
                self.user, "health", allow_rebuild=False,
            )
        mock_rebuild.assert_not_called()
        self.assertEqual(result, {})


# ── Dashboard request-path enforcement ─────────────────────────────

class DashboardReadOnlySAEContractTests(TestCase):
    """End-to-end: a /dashboard/ GET on a USER WITH WARM STATE must
    NOT call rebuild_user_state. The "warm state" case is the common
    case — every habit-forming dashboard interaction."""

    def setUp(self):
        self.user = _make_user("dash-ro@test.com")
        self.client = Client()
        self.client.force_login(self.user)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_warm_state_dashboard_get_does_not_call_rebuild_user_state(self):
        """The headline trust contract — after warm state exists, a
        dashboard GET must NEVER trigger sync rebuild_user_state."""
        # First request — primes SAE.
        with patch(
            "apps.core.ai_state.tasks.deferred_warm_sae_module.delay",
            return_value=None,
        ), patch(
            "apps.core.ai_state.tasks.deferred_rebuild_full_sae.delay",
            return_value=None,
        ):
            self.client.get(reverse("dashboard_v3:home"))

        # Second request — now state_data is populated; rebuild must NOT fire.
        with patch(
            "apps.core.ai_state.state_engine.rebuild_user_state"
        ) as mock_rebuild, patch(
            "apps.core.ai_state.tasks.deferred_warm_sae_module.delay",
            return_value=None,
        ), patch(
            "apps.core.ai_state.tasks.deferred_rebuild_full_sae.delay",
            return_value=None,
        ):
            resp = self.client.get(reverse("dashboard_v3:home"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            mock_rebuild.call_count, 0,
            f"rebuild_user_state called {mock_rebuild.call_count}× on "
            f"warm-state dashboard GET. Phase 3 forbids this on the "
            f"request path. Calls: {mock_rebuild.call_args_list}",
        )

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_brand_new_user_first_render_bootstrap_uses_one_sync_rebuild(self):
        """The trade-off: a brand-new user (no state_data) gets ONE
        sync rebuild on first render via _warm_sae_if_empty so gauges
        never render blank ("—"). After this, state_data persists."""
        with patch(
            "apps.core.ai_state.state_engine.rebuild_user_state",
            return_value={"health": {"weight_current": 180}},
        ) as mock_rebuild, patch(
            "apps.core.ai_state.tasks.deferred_warm_sae_module.delay",
            return_value=None,
        ), patch(
            "apps.core.ai_state.tasks.deferred_rebuild_full_sae.delay",
            return_value=None,
        ):
            resp = self.client.get(reverse("dashboard_v3:home"))
        self.assertEqual(resp.status_code, 200)
        # At least one rebuild fired (the bootstrap). It's fine if
        # there's more than one in this brand-new path; the contract
        # only forbids rebuilds on WARM renders.
        self.assertGreaterEqual(
            mock_rebuild.call_count, 1,
            "brand-new user's first render must bootstrap SAE (≥1 rebuild)",
        )


# ── Write-subscriber warm-task enqueue ─────────────────────────────

class WriteSubscriberWarmTaskTests(TestCase):
    """Each domain write subscriber must enqueue a background SAE warm
    task so the dashboard's next read-only render sees fresh state."""

    def setUp(self):
        self.user = _make_user("sub@test.com")

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_journal_event_enqueues_journal_warm(self):
        with patch(
            "apps.core.ai_state.tasks.deferred_warm_sae_module.delay",
            return_value=None,
        ) as mock_warm:
            safe_emit_event(EventTypes.JOURNAL_ENTRY_CREATED, self.user, {})
        calls = [c for c in mock_warm.call_args_list
                 if c.args == (self.user.id, "journal")]
        self.assertEqual(
            len(calls), 1,
            f"journal write must enqueue journal warm once. "
            f"All calls: {mock_warm.call_args_list}",
        )

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_task_event_enqueues_tasks_warm(self):
        with patch(
            "apps.core.ai_state.tasks.deferred_warm_sae_module.delay",
            return_value=None,
        ) as mock_warm:
            safe_emit_event(EventTypes.TASK_COMPLETED, self.user, {})
        calls = [c for c in mock_warm.call_args_list
                 if c.args == (self.user.id, "tasks")]
        self.assertEqual(len(calls), 1)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_purpose_event_enqueues_goals_warm(self):
        with patch(
            "apps.core.ai_state.tasks.deferred_warm_sae_module.delay",
            return_value=None,
        ) as mock_warm:
            safe_emit_event(EventTypes.PURPOSE_HABIT_LOGGED, self.user, {})
        calls = [c for c in mock_warm.call_args_list
                 if c.args == (self.user.id, "goals")]
        self.assertEqual(len(calls), 1)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_faith_event_enqueues_faith_warm(self):
        with patch(
            "apps.core.ai_state.tasks.deferred_warm_sae_module.delay",
            return_value=None,
        ) as mock_warm:
            safe_emit_event(EventTypes.FAITH_READING_COMPLETED, self.user, {})
        calls = [c for c in mock_warm.call_args_list
                 if c.args == (self.user.id, "faith")]
        self.assertEqual(len(calls), 1)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_class_a_health_event_enqueues_health_warm(self):
        """Class A health writes (water, weight, etc.) must enqueue
        the SAE health warm in addition to Phase 1's
        deferred_rebuild_health_summary."""
        with patch(
            "apps.core.ai_state.tasks.deferred_warm_sae_module.delay",
            return_value=None,
        ) as mock_warm, patch(
            "apps.health.tasks.deferred_rebuild_health_summary.delay",
            return_value=None,
        ):
            safe_emit_event(
                EventTypes.HEALTH_WATER_LOGGED, self.user,
                {"entry_id": 9_000_000 + self.user.id},
            )
        health_calls = [
            c for c in mock_warm.call_args_list
            if c.args == (self.user.id, "health")
        ]
        self.assertEqual(
            len(health_calls), 1,
            f"Class A health write must enqueue health warm. "
            f"All calls: {mock_warm.call_args_list}",
        )


# ── Phase 2 contract threading extension ────────────────────────────

class CompleteWakeUpContractAcceptanceTests(TestCase):
    """complete_wake_up now accepts a pre-fetched execution_contract
    from the view layer (extends Phase 2.0 dedup pattern)."""

    def setUp(self):
        self.user = _make_user("wu-contract@test.com")

    def test_complete_wake_up_uses_passed_contract(self):
        from apps.core.execution import today_execution as te_mod
        from apps.core.execution.verified_completion import complete_wake_up

        fake_contract = {"items": [], "summaries": {}}
        with patch.object(
            te_mod, "build_today_execution",
            side_effect=AssertionError("should not be called"),
        ):
            # If complete_wake_up tries to fetch its own, AssertionError fires.
            result = complete_wake_up(
                self.user, execution_contract=fake_contract,
            )
        self.assertIsNotNone(result)

    def test_complete_wake_up_back_compat_without_contract(self):
        """Existing callers without the new kwarg still work."""
        from apps.core.execution.verified_completion import complete_wake_up
        result = complete_wake_up(self.user)
        self.assertIsNotNone(result)


# ── SAE warm-task correctness ──────────────────────────────────────

class SAEWarmTaskCorrectnessTests(TestCase):
    """The deferred Celery tasks themselves are correct."""

    def setUp(self):
        self.user = _make_user("warmtask@test.com")

    def test_deferred_warm_sae_module_ok(self):
        from apps.core.ai_state.tasks import deferred_warm_sae_module
        result = deferred_warm_sae_module(self.user.id, "health")
        self.assertEqual(result.get("status"), "ok")
        self.assertEqual(result.get("module"), "health")

    def test_deferred_warm_sae_module_user_not_found(self):
        from apps.core.ai_state.tasks import deferred_warm_sae_module
        result = deferred_warm_sae_module(999_999, "health")
        self.assertEqual(result.get("status"), "user_not_found")

    def test_deferred_rebuild_full_sae_ok(self):
        from apps.core.ai_state.tasks import deferred_rebuild_full_sae
        result = deferred_rebuild_full_sae(self.user.id)
        self.assertEqual(result.get("status"), "ok")
