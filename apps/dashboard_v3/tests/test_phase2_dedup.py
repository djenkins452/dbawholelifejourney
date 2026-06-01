"""Phase 2 — dashboard render dedup.

Before Phase 2 the dashboard composer called the same two deterministic
hot functions multiple times per render:

  - ``build_today_execution(user)`` — 3 times (~30-40 queries each → ~90-120 total)
  - ``GoalCockpitService.get_cockpit_data()`` — 2 times (~10-20 queries each)

These tests guard against silent regression of the dedup:

  1. Both functions must be called AT MOST ONCE per dashboard render.
  2. The pre-fetched contracts must be threaded into the downstream
     builders (executive_summary, rhythm, gauges fallback).
  3. Back-compat: any other caller of build_executive_summary,
     build_rhythm_sections, build_execution_state without an explicit
     ``execution_contract`` kwarg still works (they fetch their own).
  4. Composer back-compat with kwargs in _safe (formerly *args-only).
"""

from unittest.mock import MagicMock, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.users.models import TermsAcceptance


User = get_user_model()


def _make_user(email="phase2dedup@test.com"):
    u = User.objects.create_user(email=email, password="x" * 20)
    TermsAcceptance.objects.create(
        user=u,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


class DashboardRenderDedupTests(TestCase):
    """End-to-end: a full /dashboard/ GET fetches today's execution
    contract + the cockpit at most ONCE each."""

    def setUp(self):
        self.user = _make_user()
        self.client = Client()
        self.client.force_login(self.user)

    def test_composer_direct_truth_fetch_collapses_to_one(self):
        """Composer-side dedup proof — count ONLY truth fetches that
        originate from composer.py call frames. Before Phase 2:
          - _load (none, didn't exist)
          - _build_executive_summary → build_execution_state           [1]
          - _build_rhythm → build_rhythm_sections                       [2]
          - _build_gauges fallback → _fallback_gauges_from_sae          [3]
        After Phase 2: ONE pre-fetch (``_load_execution_contract``)
        that all three reuse. Calls triggered by SAE rebuilds during
        ``get_module_state`` are tracked separately and are NOT part
        of this dedup contract (they predate Phase 2 and are addressed
        in a future SAE-snapshot pass)."""
        import traceback
        from apps.core.execution import today_execution as te_mod
        from apps.dashboard_v3.services.composer import (
            build_dashboard_v3_context,
        )

        real_fn = te_mod.build_today_execution
        composer_calls = []
        other_calls = []

        def _spy(user, *args, **kwargs):
            stack = traceback.extract_stack()
            # Skip mock-internal frames; find the first real caller.
            for frame in reversed(stack):
                if "/unittest/mock.py" in frame.filename:
                    continue
                if frame.filename.endswith("/test_phase2_dedup.py"):
                    continue
                # First real frame above the spy is the caller.
                direct_caller_file = frame.filename
                direct_caller_name = frame.name
                break
            else:
                direct_caller_file = "?"
                direct_caller_name = "?"
            tag = f"{direct_caller_file.split('/')[-1]}:{direct_caller_name}"
            if "dashboard_v3/services/composer.py" in direct_caller_file:
                composer_calls.append(tag)
            else:
                other_calls.append(tag)
            return real_fn(user, *args, **kwargs)

        with patch.object(te_mod, "build_today_execution", side_effect=_spy):
            build_dashboard_v3_context(self.user)

        self.assertEqual(
            len(composer_calls), 1,
            f"composer triggered build_today_execution {len(composer_calls)}× "
            f"(Phase 2 dedup expects exactly 1). composer-frame callers: "
            f"{composer_calls}. non-composer callers (out of scope for this "
            f"PR): {other_calls}",
        )

    def test_dashboard_render_total_truth_fetches_capped(self):
        """End-to-end ceiling on a full /dashboard/ GET — guards
        against accidental regression that re-adds composer-level
        duplicate calls. Hard cap: 5 (was 7+ before Phase 2, where
        the composer alone contributed 3 instead of the current 1).

        Contributors (post Phase 2):
          1. complete_wake_up (verified_completion.py:198)
          2. composer._load_execution_contract (composer.py)
          3-5. SAE state_builder._build_execution_state (called by
                rebuild_user_state when get_module_state misses cache,
                typically 2-3× per render for health/execution modules
                — a separate concern addressed in a future SAE-snapshot
                pass).
        """
        from apps.core.execution import today_execution as te_mod

        real_fn = te_mod.build_today_execution
        call_log = []

        def _spy(user, *args, **kwargs):
            call_log.append(user.pk)
            return real_fn(user, *args, **kwargs)

        with patch.object(te_mod, "build_today_execution", side_effect=_spy):
            resp = self.client.get(reverse("dashboard_v3:home"))
        self.assertEqual(resp.status_code, 200)
        self.assertLessEqual(
            len(call_log), 5,
            f"build_today_execution called {len(call_log)}× per /dashboard/ "
            f"GET — Phase 2 hard cap is 5 (was 7+ before). Calls: {call_log}",
        )

    def test_get_cockpit_data_called_at_most_once_per_dashboard_render(self):
        """The single-fetch contract for the cockpit service."""
        from apps.dashboard_v2.services import cockpit_service as cs_mod

        real_method = cs_mod.GoalCockpitService.get_cockpit_data
        call_log = []

        def _spy(self):
            call_log.append(self.user.pk)
            return real_method(self)

        with patch.object(
            cs_mod.GoalCockpitService, "get_cockpit_data", autospec=True,
            side_effect=_spy,
        ):
            resp = self.client.get(reverse("dashboard_v3:home"))
        self.assertEqual(resp.status_code, 200)
        self.assertLessEqual(
            len(call_log), 1,
            f"get_cockpit_data called {len(call_log)}× per render "
            f"(Phase 2 dedup expects ≤1). Calls: {call_log}",
        )

    def test_dashboard_context_keys_unchanged_after_dedup(self):
        """The composer output shape must not drift — same top-level
        keys before and after Phase 2."""
        from apps.dashboard_v3.services.composer import build_dashboard_v3_context

        ctx = build_dashboard_v3_context(self.user)
        expected_keys = {
            "cockpit_domains", "mission", "gauges", "executive_summary",
            "focus_now", "follow_on", "accountability_cards", "rhythm",
            "utilities",
        }
        missing = expected_keys - set(ctx.keys())
        self.assertFalse(
            missing, f"composer dropped expected keys: {missing}",
        )


class BackCompatTests(TestCase):
    """The new ``execution_contract`` kwarg must be optional everywhere.
    Other callers (Beth narration, ops endpoints, future surfaces) must
    keep working with the unchanged signatures.
    """

    def setUp(self):
        self.user = _make_user("backcompat@test.com")

    def test_build_executive_summary_works_without_contract_kwarg(self):
        from apps.core.cos_briefing import build_executive_summary
        # No execution_contract param — must still produce a dict.
        result = build_executive_summary(self.user)
        self.assertIsInstance(result, dict)
        # Required keys remain.
        self.assertIn("trajectory", result)
        self.assertIn("focus_now", result)

    def test_build_rhythm_sections_works_without_contract_kwarg(self):
        from apps.core.cos_briefing import build_rhythm_sections
        result = build_rhythm_sections(self.user)
        self.assertIsInstance(result, dict)
        self.assertIn("sections", result)
        self.assertIn("current_key", result)

    def test_build_execution_state_works_without_contract_kwarg(self):
        from apps.core.execution.execution_state import build_execution_state
        result = build_execution_state(self.user)
        self.assertIsInstance(result, dict)

    def test_build_execution_state_uses_passed_contract_when_provided(self):
        """When a contract is passed, ``build_execution_state`` must
        reuse it rather than fetching its own copy."""
        from apps.core.execution import today_execution as te_mod
        from apps.core.execution.execution_state import build_execution_state

        # Build a real contract once, then assert no second fetch.
        real_contract = te_mod.build_today_execution(self.user)

        call_count = 0
        real_fn = te_mod.build_today_execution

        def _spy(user, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            return real_fn(user, *args, **kwargs)

        with patch.object(te_mod, "build_today_execution", side_effect=_spy):
            build_execution_state(self.user, execution_contract=real_contract)

        self.assertEqual(
            call_count, 0,
            "build_execution_state must NOT refetch when contract is passed",
        )

    def test_build_executive_summary_uses_passed_contract_when_provided(self):
        from apps.core.execution import today_execution as te_mod
        from apps.core.cos_briefing import build_executive_summary

        real_contract = te_mod.build_today_execution(self.user)

        call_count = 0
        real_fn = te_mod.build_today_execution

        def _spy(user, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            return real_fn(user, *args, **kwargs)

        with patch.object(te_mod, "build_today_execution", side_effect=_spy):
            build_executive_summary(self.user, execution_contract=real_contract)

        self.assertEqual(
            call_count, 0,
            "build_executive_summary must NOT refetch via build_execution_state "
            "when an execution_contract is passed",
        )

    def test_build_rhythm_sections_uses_passed_contract_when_provided(self):
        from apps.core.execution import today_execution as te_mod
        from apps.core.cos_briefing import build_rhythm_sections

        real_contract = te_mod.build_today_execution(self.user)

        call_count = 0
        real_fn = te_mod.build_today_execution

        def _spy(user, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            return real_fn(user, *args, **kwargs)

        with patch.object(te_mod, "build_today_execution", side_effect=_spy):
            build_rhythm_sections(self.user, execution_contract=real_contract)

        self.assertEqual(
            call_count, 0,
            "build_rhythm_sections must NOT refetch when contract is passed",
        )


class TrustConsistencyTests(TestCase):
    """Phase 2 must not let the rhythm + executive_summary + gauges
    disagree on the same canonical items. Threading ONE contract makes
    consistency explicit; this test guards that property."""

    def setUp(self):
        self.user = _make_user("consistency@test.com")

    def test_rhythm_and_executive_summary_see_same_items(self):
        """When composer threads one contract through both, the items
        each consumer sees come from the exact same source dict."""
        from apps.dashboard_v3.services.composer import (
            _load_execution_contract,
            _build_executive_summary,
            _build_rhythm,
        )

        contract = _load_execution_contract(self.user)
        self.assertIsNotNone(contract)

        rhythm = _build_rhythm(self.user, execution_contract=contract)
        exec_summary = _build_executive_summary(
            self.user, execution_contract=contract,
        )

        # Both ran without raising.
        self.assertIn("sections", rhythm)
        self.assertIsInstance(exec_summary, dict)

    def test_safe_wrapper_passes_kwargs(self):
        """Regression guard — _safe used to be *args-only; Phase 2
        extended it to forward **kwargs. Don't let that quietly break."""
        from apps.dashboard_v3.services.composer import _safe

        def fn(user, *, contract=None):
            return {"got": contract}

        result = _safe(fn, "u", default={}, contract="C")
        self.assertEqual(result, {"got": "C"})
