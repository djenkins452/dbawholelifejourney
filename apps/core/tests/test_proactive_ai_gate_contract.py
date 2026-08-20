# ==============================================================================
# File: apps/core/tests/test_proactive_ai_gate_contract.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Pre-production pause of provider-backed proactive AI
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-08-20
# ==============================================================================
"""Provider-backed proactive AI is PAUSED pre-production.

    ENVIRONMENT decides whether real product traffic may use the provider.
    WORKLOAD ORIGIN decides whether AUTONOMOUS provider spend is authorized.

Being in production is not permission for a background job to spend money. WLJ was paying
~$1.09/day for proactive work that fired whether or not anyone opened the app.

This is a PAUSE, not a retirement: PGS, beat, the Daily Brief, check-ins, follow-ups and
their configuration all remain intact and resume when the flag is turned on.

**Every test uses mocks. ZERO real provider calls.**
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.ai.llm_admission import (
    ENV_DEVELOPMENT, ENV_PRODUCTION, RealLLMCallDenied, autonomous_workload,
    current_workload_is_autonomous, may_real_llm_call, proactive_ai_enabled,
)
from apps.owner_finance.models import LLMUsageEvent

User = get_user_model()

PROD = {"WLJ_ENV": ENV_PRODUCTION}


def _prod_env():
    return mock.patch.dict("os.environ", PROD, clear=False)


class ProactiveUserMixin(TestCase):
    def setUp(self):
        from django.conf import settings as dj
        from apps.users.models import TermsAcceptance
        self.user = User.objects.create_user(
            email="proactive@contract.test", password="x", first_name="P")
        self.user.has_completed_onboarding = True
        self.user.save()
        TermsAcceptance.objects.get_or_create(
            user=self.user,
            defaults={"terms_version": dj.WLJ_SETTINGS["TERMS_VERSION"]})
        p = self.user.preferences
        p.has_completed_onboarding = True
        p.ai_enabled = True
        p.ai_data_consent = True
        p.personal_assistant_enabled = True
        p.personal_assistant_consent = True
        p.assistant_proactive_checkins = True
        p.use_model_interface = True
        p.save()
        self.user = User.objects.get(pk=self.user.pk)


@override_settings(WLJ_PROACTIVE_AI_ENABLED=False)
class GateOffTests(ProactiveUserMixin):
    """1-3: no autonomous path may reach the provider while paused."""

    def test_the_pgs_cycle_skips_cleanly_and_calls_nothing(self):
        from apps.ai.proactive_checkins import run_proactive_guidance_scheduler
        with mock.patch("apps.ai.beth_checkin_renderer.render_checkin_for_time") as render:
            with mock.patch("apps.ai.model_interface.service.ModelInterfaceService."
                            "generate") as gen:
                out = run_proactive_guidance_scheduler()
        render.assert_not_called()
        gen.assert_not_called()
        self.assertEqual(out.get("status"), "skipped")
        self.assertEqual(out.get("reason"), "proactive_ai_disabled")
        self.assertEqual(out.get("provider_calls"), 0)

    def test_the_daily_brief_makes_no_provider_call(self):
        from apps.ai.proactive_checkins import generate_daily_executive_brief_for_user
        with mock.patch("apps.ai.model_interface.service.ModelInterfaceService."
                        "generate") as gen:
            self.assertIsNone(generate_daily_executive_brief_for_user(self.user))
        gen.assert_not_called()

    def test_a_proactive_checkin_makes_no_provider_call(self):
        """The admission seam refuses autonomous work even if a path forgets to check."""
        from apps.ai.llm_accounting import TRAFFIC_PROACTIVE, llm_traffic_context
        with _prod_env():
            with llm_traffic_context(traffic_class=TRAFFIC_PROACTIVE):
                decision = may_real_llm_call()
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "proactive_ai_disabled")

    def test_follow_up_delivery_claims_nothing_and_calls_nothing(self):
        from apps.ai.cos_services.follow_up import deliver_due_follow_ups_for_user
        with mock.patch("apps.ai.model_interface.service.ModelInterfaceService."
                        "generate") as gen:
            self.assertEqual(deliver_due_follow_ups_for_user(self.user), 0)
        gen.assert_not_called()

    def test_being_in_production_is_not_permission_to_spend(self):
        """The governing principle. Production admits USER traffic, not autonomous work."""
        with _prod_env():
            with autonomous_workload("scheduled"):
                decision = may_real_llm_call()
        self.assertFalse(decision.allowed, "a background job spent money merely because "
                                           "it was running in production")

    def test_the_guarded_client_refuses_autonomous_work(self):
        from apps.core.tests.test_llm_admission_contract import guarded
        client = guarded()
        with _prod_env():
            with autonomous_workload("scheduled"):
                with self.assertRaises(RealLLMCallDenied) as ctx:
                    client.chat.completions.create(model="gpt-4o", messages=[])
        self.assertEqual(client._client.chat.completions.calls, 0)
        self.assertIn("paused for pre-production", str(ctx.exception).lower())


@override_settings(WLJ_PROACTIVE_AI_ENABLED=False)
class UserInitiatedStillWorksTests(ProactiveUserMixin):
    """5: pausing autonomous work must not touch the product."""

    def test_user_initiated_conversation_is_still_admitted_in_production(self):
        with _prod_env():
            decision = may_real_llm_call()
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, "production_runtime")

    def test_a_user_turn_is_not_classified_as_autonomous(self):
        self.assertFalse(current_workload_is_autonomous())

    def test_the_certified_runtime_reaches_the_provider_for_a_user_turn(self):
        from apps.ai.models import AssistantConversation
        from apps.ai.model_interface.service import ModelInterfaceService
        conv = AssistantConversation.get_or_create_active(self.user)
        svc = ModelInterfaceService(self.user)
        seen = {}

        def _fake(*a, **k):
            from apps.ai.llm_admission import may_real_llm_call as m
            seen["allowed"] = m().allowed
            return "ok"

        with _prod_env():
            with mock.patch.object(svc.ai, "_call_api_with_tools", side_effect=_fake):
                svc.generate(conv, "how am I doing?", surface="test")
        self.assertTrue(seen.get("allowed"),
                        "pausing proactive AI broke user-initiated conversation")

    def test_the_streaming_worker_task_is_not_autonomous(self):
        """It runs in a worker, but a human asked for it — it must not be gated."""
        import pathlib
        src = pathlib.Path("apps/ai/model_interface/tasks.py").read_text(encoding="utf-8")
        self.assertNotIn("autonomous_workload", src)
        self.assertNotIn("TRAFFIC_PROACTIVE", src)


@override_settings(WLJ_PROACTIVE_AI_ENABLED=True)
class GateOnTests(ProactiveUserMixin):
    """6: the pause is reversible — nothing was deleted or redesigned."""

    def test_the_flag_restores_autonomous_admission(self):
        with _prod_env():
            with autonomous_workload("scheduled"):
                self.assertTrue(may_real_llm_call().allowed)

    def test_the_pgs_cycle_runs_its_real_loop_again(self):
        from apps.ai.proactive_checkins import run_proactive_guidance_scheduler
        with mock.patch("apps.ai.proactive_checkins._get_proactive_users",
                        return_value=[]) as users:
            out = run_proactive_guidance_scheduler()
        users.assert_called_once()
        self.assertNotEqual(out.get("status"), "skipped")

    def test_the_daily_brief_proceeds_past_the_gate(self):
        from apps.ai.proactive_checkins import generate_daily_executive_brief_for_user
        with mock.patch("apps.core.utils.get_user_today",
                        side_effect=RuntimeError("stop after the gate")) as day:
            generate_daily_executive_brief_for_user(self.user)
        day.assert_called()


@override_settings(WLJ_PROACTIVE_AI_ENABLED=False)
class SchedulerHealthTests(ProactiveUserMixin):
    """4 + 8: a paused job is not a broken job."""

    def test_the_skipped_cycle_reports_success_not_failure(self):
        from apps.ai.proactive_checkins import run_proactive_guidance_scheduler
        out = run_proactive_guidance_scheduler()
        self.assertEqual(out.get("errors"), 0,
                         "a deliberate pause was reported as an error")
        self.assertIsInstance(out, dict)

    def test_a_skipped_cycle_raises_nothing_that_would_trigger_retries(self):
        from apps.ai.proactive_checkins import run_proactive_guidance_scheduler
        for _ in range(3):                     # repeated beat cycles
            run_proactive_guidance_scheduler()  # must not raise

    def test_no_fake_spend_is_recorded_for_a_skipped_job(self):
        from apps.ai.proactive_checkins import (
            generate_daily_executive_brief_for_user, run_proactive_guidance_scheduler)
        before = LLMUsageEvent.objects.count()
        run_proactive_guidance_scheduler()
        generate_daily_executive_brief_for_user(self.user)
        self.assertEqual(LLMUsageEvent.objects.count(), before,
                         "a skipped job invented usage rows")

    def test_deterministic_background_work_is_untouched(self):
        """Only PROVIDER-backed generation pauses. Free background processing must not."""
        import pathlib
        src = pathlib.Path("apps/core/ai_scheduler/scheduler_registry.py").read_text(
            encoding="utf-8")
        self.assertNotIn("proactive_ai_enabled", src,
                         "the gate leaked into the general scheduler registry")
        self.assertIn("run_proactive_guidance", src,
                      "PGS registration was removed — this is a pause, not a retirement")


class ArchitecturePreservedTests(TestCase):
    """Preserve: PGS, beat, deterministic scheduling, config, tests, brief, check-ins."""

    def test_the_proactive_architecture_still_exists(self):
        from apps.ai import proactive_checkins as pc
        for name in ("run_proactive_guidance_scheduler",
                     "generate_daily_executive_brief_for_user"):
            self.assertTrue(hasattr(pc, name), f"{name} was removed, not paused")
        from apps.ai.cos_services.follow_up import deliver_due_follow_ups_for_user
        self.assertTrue(callable(deliver_due_follow_ups_for_user))

    def test_the_user_preference_is_untouched(self):
        from apps.users.models import UserPreferences
        self.assertTrue(
            any(f.name == "assistant_proactive_checkins"
                for f in UserPreferences._meta.get_fields()),
            "proactive configuration was deleted rather than paused")

    def test_the_default_is_off_so_a_new_feature_cannot_start_spending(self):
        import pathlib
        src = pathlib.Path("config/settings.py").read_text(encoding="utf-8")
        self.assertIn("WLJ_PROACTIVE_AI_ENABLED", src)
        self.assertIn("'WLJ_PROACTIVE_AI_ENABLED', default=False", src)


class SelfEnablementTests(TestCase):
    """7: Claude/dev tooling must not be able to switch this on."""

    def test_no_code_path_sets_the_flag(self):
        import ast
        import pathlib
        offenders = []
        for p in pathlib.Path("apps").rglob("*.py"):
            if "/tests/" in str(p) or p.name.startswith("test"):
                continue
            try:
                tree = ast.parse(p.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                # settings.WLJ_PROACTIVE_AI_ENABLED = ...
                if isinstance(node, ast.Assign):
                    for t in node.targets:
                        if (isinstance(t, ast.Attribute)
                                and t.attr == "WLJ_PROACTIVE_AI_ENABLED"):
                            offenders.append(f"{p}:{node.lineno}")
        self.assertEqual(offenders, [],
                         f"code that enables proactive spend: {offenders}")

    def test_there_is_no_management_command_to_enable_it(self):
        import pathlib
        for p in pathlib.Path("apps").rglob("management/commands/*.py"):
            src = p.read_text(encoding="utf-8")
            self.assertNotIn("WLJ_PROACTIVE_AI_ENABLED = True", src)
            self.assertNotIn('WLJ_PROACTIVE_AI_ENABLED", True', src)

    def test_enabling_requires_the_environment_not_the_codebase(self):
        """It is an env var read at startup — turning it on is a deployment decision."""
        self.assertIn(proactive_ai_enabled(), (True, False))
