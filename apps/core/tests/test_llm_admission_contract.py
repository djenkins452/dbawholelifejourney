# ==============================================================================
# File: apps/core/tests/test_llm_admission_contract.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Real-LLM Cost Governor — admission, budget, classification, bypass
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-08-20
# ==============================================================================
"""The cost governor's contract.

    NO EXPLICIT AUTHORIZATION  ->  NO REAL PROVIDER CALL.
    AUTHORIZATION              ->  HARD FINITE BUDGET  ->  FAIL CLOSED AT ZERO.

**Every test here uses a fake client. ZERO real provider calls.** We do not spend money to
prove that code prevents spending money — and a test that reached the network would itself
be the bug it is meant to catch.
"""

import ast
import pathlib
from unittest import mock

from django.test import SimpleTestCase, TestCase, TransactionTestCase
from django.utils import timezone

from apps.ai.llm_admission import (
    ENV_DEVELOPMENT, ENV_PRODUCTION, FLAG_ALLOW, FLAG_RUN_ID, GuardedOpenAIClient,
    RealLLMCallDenied, build_guarded_client, current_environment, may_real_llm_call,
)
from apps.ai.models import RealLLMAuthorization

REPO = pathlib.Path(__file__).resolve().parents[3]


class FakeCompletions:
    """Stands in for the SDK. Counts calls; never touches a network."""

    def __init__(self):
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        return {"ok": True}


class FakeClient:
    def __init__(self):
        self.chat = mock.Mock()
        self.chat.completions = FakeCompletions()
        self.embeddings = FakeCompletions()
        self.models = mock.Mock()


def guarded():
    return GuardedOpenAIClient(FakeClient())


def _dev_env(**extra):
    env = {"WLJ_ENV": ENV_DEVELOPMENT}
    env.update(extra)
    return mock.patch.dict("os.environ", env, clear=False)


def _no_auth_env():
    """Development with the authorization variables definitively absent."""
    return mock.patch.dict(
        "os.environ", {"WLJ_ENV": ENV_DEVELOPMENT, FLAG_ALLOW: "", FLAG_RUN_ID: ""},
        clear=False)


class EnvironmentTests(SimpleTestCase):
    def test_local_shell_is_development(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(current_environment(), ENV_DEVELOPMENT)

    def test_railway_build_stamp_means_production(self):
        with mock.patch.dict("os.environ", {"RAILWAY_GIT_COMMIT_SHA": "abc123"}, clear=True):
            self.assertEqual(current_environment(), ENV_PRODUCTION)

    def test_the_railway_default_placeholder_is_not_production(self):
        """`RAILWAY_GIT_COMMIT_SHA` falls back to the literal 'development' off-platform."""
        with mock.patch.dict("os.environ", {"RAILWAY_GIT_COMMIT_SHA": "development"},
                             clear=True):
            self.assertEqual(current_environment(), ENV_DEVELOPMENT)

    def test_explicit_override_wins(self):
        with mock.patch.dict("os.environ",
                             {"WLJ_ENV": "development", "RAILWAY_GIT_COMMIT_SHA": "abc"},
                             clear=True):
            self.assertEqual(current_environment(), ENV_DEVELOPMENT)


class DenyByDefaultTests(TestCase):
    """The headline guarantee. A configured API key is NOT authorization."""

    def test_development_with_a_key_but_no_authorization_is_denied(self):
        client = guarded()
        with _no_auth_env():
            with self.assertRaises(RealLLMCallDenied):
                client.chat.completions.create(model="gpt-4o", messages=[])
        self.assertEqual(client._client.chat.completions.calls, 0,
                         "a denied call still reached the provider")

    def test_authorization_flag_without_a_run_is_denied(self):
        with _dev_env(**{FLAG_ALLOW: "1", FLAG_RUN_ID: ""}):
            self.assertFalse(may_real_llm_call().allowed)

    def test_a_run_without_the_flag_is_denied(self):
        auth = _mint(3)
        with _dev_env(**{FLAG_ALLOW: "", FLAG_RUN_ID: auth.run_id}):
            self.assertFalse(may_real_llm_call().allowed)
        auth.refresh_from_db()
        self.assertEqual(auth.calls_remaining, 3, "a denied call consumed budget")

    def test_an_unknown_run_id_is_denied(self):
        with _dev_env(**{FLAG_ALLOW: "1", FLAG_RUN_ID: "wlj-llm-does-not-exist"}):
            d = may_real_llm_call()
        self.assertFalse(d.allowed)
        self.assertEqual(d.reason, "no_valid_authorization")

    def test_the_denial_message_tells_claude_to_stop_not_to_retry(self):
        with _no_auth_env():
            with self.assertRaises(RealLLMCallDenied) as ctx:
                guarded().chat.completions.create(model="gpt-4o", messages=[])
        msg = str(ctx.exception)
        self.assertIn("NOT authorization", msg)
        self.assertIn("Claude Code must never do this itself", msg)

    def test_embeddings_are_governed_too(self):
        client = guarded()
        with _no_auth_env():
            with self.assertRaises(RealLLMCallDenied):
                client.embeddings.create(model="text-embedding-3-small", input="x")
        self.assertEqual(client._client.embeddings.calls, 0)

    def test_non_billable_attribute_access_is_untouched(self):
        with _no_auth_env():
            self.assertIsNotNone(guarded().models)


class BudgetTests(TestCase):
    def test_a_budget_of_one_admits_exactly_one_call(self):
        auth = _mint(1)
        client = guarded()
        with _dev_env(**{FLAG_ALLOW: "1", FLAG_RUN_ID: auth.run_id}):
            client.chat.completions.create(model="gpt-4o", messages=[])
            with self.assertRaises(RealLLMCallDenied):
                client.chat.completions.create(model="gpt-4o", messages=[])
        self.assertEqual(client._client.chat.completions.calls, 1)

    def test_exhaustion_says_stop_rather_than_suggesting_a_reset(self):
        auth = _mint(1)
        with _dev_env(**{FLAG_ALLOW: "1", FLAG_RUN_ID: auth.run_id}):
            may_real_llm_call()
            with self.assertRaises(RealLLMCallDenied) as ctx:
                guarded().chat.completions.create(model="gpt-4o", messages=[])
        self.assertIn("STOP", str(ctx.exception))
        self.assertIn("Do not reset it", str(ctx.exception))

    def test_a_retry_consumes_another_call(self):
        """Retries are real money — the SDK retrying is not free."""
        auth = _mint(2)
        client = guarded()
        with _dev_env(**{FLAG_ALLOW: "1", FLAG_RUN_ID: auth.run_id}):
            for _ in range(2):
                client.chat.completions.create(model="gpt-4o", messages=[])
            with self.assertRaises(RealLLMCallDenied):
                client.chat.completions.create(model="gpt-4o", messages=[])
        auth.refresh_from_db()
        self.assertEqual(auth.calls_remaining, 0)

    def test_each_tool_loop_continuation_consumes_budget(self):
        """A CoS turn bills 3-9 requests; the budget must count requests, not turns."""
        auth = _mint(3)
        client = guarded()
        with _dev_env(**{FLAG_ALLOW: "1", FLAG_RUN_ID: auth.run_id}):
            for _ in range(3):                       # initial + 2 tool continuations
                client.chat.completions.create(model="gpt-4o", messages=[])
            with self.assertRaises(RealLLMCallDenied):
                client.chat.completions.create(model="gpt-4o", messages=[])
        self.assertEqual(client._client.chat.completions.calls, 3)

    def test_an_expired_authorization_is_refused(self):
        auth = _mint(5)
        RealLLMAuthorization.objects.filter(pk=auth.pk).update(
            expires_at=timezone.now() - timezone.timedelta(minutes=1))
        with _dev_env(**{FLAG_ALLOW: "1", FLAG_RUN_ID: auth.run_id}):
            self.assertFalse(may_real_llm_call().allowed)

    def test_the_budget_store_failing_denies_rather_than_spends(self):
        auth = _mint(5)
        with _dev_env(**{FLAG_ALLOW: "1", FLAG_RUN_ID: auth.run_id}):
            with mock.patch("apps.ai.models.RealLLMAuthorization.objects") as m:
                m.filter.side_effect = RuntimeError("db down")
                d = may_real_llm_call()
        self.assertFalse(d.allowed, "an unreachable budget store permitted spending")


class SharedBudgetTests(TransactionTestCase):
    """Web and worker are separate processes. A process-local counter would let each of
    them believe it owned the whole budget."""

    def test_the_budget_is_not_process_local_state(self):
        """Assert on actual mutable state, not on names: a constant whose name merely
        contains 'budget' is not a counter, and matching identifiers is how earlier scans
        in this repo produced false positives."""
        import apps.ai.llm_admission as mod
        tree = ast.parse(pathlib.Path(mod.__file__).read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
                if isinstance(node.value.value, (int, float)) and not isinstance(
                        node.value.value, bool):
                    names = [t.id for t in node.targets if isinstance(t, ast.Name)]
                    self.fail(f"module-level numeric state {names} — a process-local "
                              f"counter would let each process own the full budget")

    def test_concurrent_consumers_cannot_exceed_the_budget(self):
        """Simulates the race: many consumers, one remaining call."""
        auth = _mint(1)
        results = []
        with _dev_env(**{FLAG_ALLOW: "1", FLAG_RUN_ID: auth.run_id}):
            for _ in range(8):
                results.append(may_real_llm_call().allowed)
        self.assertEqual(sum(results), 1,
                         "more calls were admitted than were ever authorized")

    def test_the_decrement_is_a_single_conditional_update(self):
        """Read-modify-write in Python would be a lost-update race."""
        src = pathlib.Path(
            REPO / "apps/ai/llm_admission.py").read_text(encoding="utf-8")
        self.assertIn("calls_remaining__gt=0", src)
        self.assertIn('F("calls_remaining") - 1', src)


class ProductionTests(TestCase):
    """Do NOT break Danny's actual WLJ."""

    def test_production_customer_traffic_is_admitted_without_any_authorization(self):
        """A real customer's turn never needs a development authorization.

        NARROWED 2026-09-04: the turn must now SAY it is a customer's. Being in production
        used to be enough on its own, and that was the hole — the check-in author made real
        provider calls classified `unattributed` and rode this allow with nobody having
        asked for anything. Absence of attribution is not evidence of a human, so the
        interactive entry points assert `production` for themselves.
        """
        from apps.ai.llm_accounting import TRAFFIC_PRODUCTION, llm_traffic_context
        client = guarded()
        with mock.patch.dict("os.environ", {"WLJ_ENV": ENV_PRODUCTION}, clear=True), \
             llm_traffic_context(traffic_class=TRAFFIC_PRODUCTION):
            client.chat.completions.create(model="gpt-4o", messages=[])
        self.assertEqual(client._client.chat.completions.calls, 1)

    def test_an_unattributed_production_call_is_refused_as_autonomous(self):
        """The check-in incident, as a contract: nobody asserted a human, so nobody did."""
        from apps.ai.llm_admission import may_real_llm_call
        with mock.patch.dict("os.environ", {"WLJ_ENV": ENV_PRODUCTION}, clear=True):
            decision = may_real_llm_call()
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "proactive_ai_disabled")

    def test_production_consumes_no_development_budget(self):
        auth = _mint(1)
        with mock.patch.dict("os.environ",
                             {"WLJ_ENV": ENV_PRODUCTION, FLAG_RUN_ID: auth.run_id},
                             clear=True):
            may_real_llm_call()
        auth.refresh_from_db()
        self.assertEqual(auth.calls_remaining, 1)


class TrafficClassificationTests(TestCase):
    def test_an_unclassified_call_is_not_recorded_as_production(self):
        from apps.owner_finance.models import LLMUsageEvent
        from apps.ai.llm_accounting import record_llm_event
        record_llm_event(model="gpt-4o", prompt_tokens=10, completion_tokens=1)
        ev = LLMUsageEvent.objects.latest("created_at")
        self.assertEqual(ev.traffic_class, LLMUsageEvent.TRAFFIC_UNATTRIBUTED)

    def test_the_model_default_is_unattributed(self):
        from apps.owner_finance.models import LLMUsageEvent
        self.assertEqual(LLMUsageEvent._meta.get_field("traffic_class").default,
                         LLMUsageEvent.TRAFFIC_UNATTRIBUTED)

    def test_the_production_path_asserts_production_explicitly(self):
        src = (REPO / "apps/ai/model_interface/service.py").read_text(encoding="utf-8")
        self.assertIn("TRAFFIC_PRODUCTION", src,
                      "real interactive traffic must name itself now that the default "
                      "is unattributed")


class PricingVisibilityTests(TestCase):
    """A recorded 0 must not mean two different things."""

    def setUp(self):
        from apps.owner_finance.models import LLMPriceBook, ThirdPartyVendor
        vendor, _ = ThirdPartyVendor.objects.get_or_create(name="OpenAI")
        LLMPriceBook.objects.get_or_create(
            vendor=vendor, model_name="gpt-4o",
            effective_start=timezone.now().date() - timezone.timedelta(days=1),
            defaults={"input_cost_per_1m_tokens_usd": "2.50",
                      "output_cost_per_1m_tokens_usd": "10.00", "is_active": True})

    def test_a_priced_model_records_a_known_cost(self):
        from apps.owner_finance.models import LLMUsageEvent
        from apps.ai.llm_accounting import record_llm_event
        record_llm_event(model="gpt-4o", prompt_tokens=1_000_000, completion_tokens=0)
        ev = LLMUsageEvent.objects.latest("created_at")
        self.assertTrue(ev.cost_is_known)
        self.assertGreater(ev.cost_usd, 0)

    def test_an_unpriced_model_is_unknown_not_a_misleading_zero(self):
        from apps.owner_finance.models import LLMUsageEvent
        from apps.ai.llm_accounting import record_llm_event
        record_llm_event(model="some-model-with-no-price", prompt_tokens=999_999,
                         completion_tokens=500)
        ev = LLMUsageEvent.objects.latest("created_at")
        self.assertFalse(ev.cost_is_known,
                         "unpriced spend recorded as though its cost were known")
        self.assertTrue(ev.metadata.get("missing_pricebook"))
        self.assertGreater(ev.input_tokens, 0, "tokens must still be recorded")

    def test_no_price_is_ever_fabricated(self):
        src = (REPO / "apps/owner_finance/services/telemetry.py").read_text(encoding="utf-8")
        self.assertNotIn("DEFAULT_PRICE", src)
        self.assertNotIn("fallback_price", src)


class StructuralBypassTests(SimpleTestCase):
    """CI fails if a new ungoverned provider path appears.

    AST-based, not a prose grep — earlier text scans in this repo produced repeated false
    positives by matching comments and docstrings.
    """

    SEAM = "apps/ai/llm_admission.py"

    def _sources(self):
        for p in sorted((REPO / "apps").rglob("*.py")):
            rel = str(p.relative_to(REPO))
            name = p.name
            if "/tests/" in rel or name.startswith("test") or "tests_" in name:
                continue
            yield rel, p

    def test_no_module_constructs_an_unguarded_openai_client(self):
        offenders = []
        for rel, path in self._sources():
            if rel == self.SEAM:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    fn = node.func
                    name = (fn.id if isinstance(fn, ast.Name)
                            else fn.attr if isinstance(fn, ast.Attribute) else "")
                    if name in ("OpenAI", "AsyncOpenAI"):
                        offenders.append(f"{rel}:{node.lineno}")
        self.assertEqual(offenders, [], (
            "Ungoverned OpenAI client construction found. Every real provider path must go "
            "through apps.ai.llm_admission.build_guarded_client, or it silently bypasses "
            "the cost governor. Offenders: " + ", ".join(offenders)))

    def test_the_seam_still_guards_every_billable_operation(self):
        from apps.ai.llm_admission import BILLABLE_OPERATIONS
        for op in (("chat", "completions", "create"), ("embeddings", "create"),
                   ("audio", "transcriptions", "create"), ("responses", "create")):
            self.assertIn(op, BILLABLE_OPERATIONS)

    def test_the_factory_returns_a_guarded_client_not_a_raw_one(self):
        with mock.patch("apps.ai.llm_admission.OpenAI", create=True):
            with mock.patch.dict("os.environ", {"WLJ_ENV": ENV_DEVELOPMENT}, clear=False):
                client = build_guarded_client(api_key="sk-test-not-real")
        if client is not None:
            self.assertIsInstance(client, GuardedOpenAIClient)

    def test_no_key_returns_none_rather_than_an_ungoverned_client(self):
        from django.test import override_settings
        with override_settings(OPENAI_API_KEY=""):
            self.assertIsNone(build_guarded_client())


class SelfAuthorizationTests(SimpleTestCase):
    """Claude Code must not be able to mint or extend an authorization."""

    def test_minting_requires_an_interactive_terminal(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError
        with mock.patch("sys.stdin.isatty", return_value=False):
            with self.assertRaises(CommandError) as ctx:
                call_command("authorize_real_llm", calls=1, reason="test")
        self.assertIn("interactive terminal", str(ctx.exception))

    def test_there_is_no_command_that_raises_an_existing_budget(self):
        cmds = (REPO / "apps/ai/management/commands")
        for p in cmds.glob("*.py"):
            src = p.read_text(encoding="utf-8")
            self.assertNotIn("calls_remaining=F(", src.replace(
                'F("calls_remaining") - 1', ""))
            self.assertNotIn("calls_authorized +", src)


def _mint(calls, minutes=60):
    import secrets
    return RealLLMAuthorization.objects.create(
        run_id=f"wlj-llm-{secrets.token_hex(6)}",
        reason="contract test",
        calls_authorized=calls,
        calls_remaining=calls,
        expires_at=timezone.now() + timezone.timedelta(minutes=minutes),
    )
