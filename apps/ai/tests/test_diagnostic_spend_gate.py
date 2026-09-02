# ==============================================================================
# File: apps/ai/tests/test_diagnostic_spend_gate.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: A diagnostic does not spend money unless a human said how much.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Operator diagnostics fail closed, in production too.

`may_real_llm_call` admits production unconditionally, and that is right — real
customers must never be refused. But an operator endpoint that RUNS in production
inherited that permission, and on 2026-09-02 a verification call to `cos-run` spent
Danny's credits with nobody having authorized it. Being in production is not evidence
that a human asked for this particular call.

So diagnostics declare themselves and default to refused. Authorizing one is explicit,
bounded to a call count, and recorded before the spend happens.
"""
from unittest import mock

from django.test import TestCase, override_settings

from apps.ai.llm_admission import (
    ENV_PRODUCTION,
    DiagnosticBudget,
    admit_or_raise,
    current_diagnostic_budget,
    diagnostic_workload,
    may_real_llm_call,
    RealLLMCallDenied,
)


class ProductionDoesNotExcuseADiagnosticTests(TestCase):
    """The exact hole that cost money."""

    def test_production_still_admits_a_customer(self):
        decision = may_real_llm_call(environment=ENV_PRODUCTION)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, "production_runtime")

    def test_production_refuses_an_unauthorized_diagnostic(self):
        with diagnostic_workload("verifying a deploy"):
            decision = may_real_llm_call(environment=ENV_PRODUCTION)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "diagnostic_not_authorized")

    def test_the_refusal_says_what_to_do_instead(self):
        with diagnostic_workload("verifying a deploy"):
            with self.assertRaises(RealLLMCallDenied) as caught:
                admit_or_raise(operation="cos_run")
        message = str(caught.exception)
        self.assertIn("deterministic fixtures", message)
        self.assertIn("ask Danny", message)

    def test_an_authorized_diagnostic_is_admitted(self):
        with diagnostic_workload("approved check", authorized_calls=1):
            decision = may_real_llm_call(environment=ENV_PRODUCTION)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, "authorized_diagnostic")

    def test_the_budget_is_a_ceiling_not_a_door(self):
        with diagnostic_workload("approved check", authorized_calls=2):
            first = may_real_llm_call(environment=ENV_PRODUCTION)
            second = may_real_llm_call(environment=ENV_PRODUCTION)
            third = may_real_llm_call(environment=ENV_PRODUCTION)
        self.assertTrue(first.allowed)
        self.assertTrue(second.allowed)
        self.assertFalse(third.allowed, "the third call was never authorized")
        self.assertEqual(third.reason, "diagnostic_not_authorized")

    def test_the_gate_is_checked_before_the_production_allow(self):
        """Order matters: after it, production would admit everything."""
        import inspect

        source = inspect.getsource(may_real_llm_call)
        self.assertLess(source.index("current_diagnostic_budget"),
                        source.index("production_runtime"),
                        "the diagnostic gate must precede the production allow")

    def test_the_marker_does_not_leak_out_of_the_block(self):
        with diagnostic_workload("scoped", authorized_calls=1):
            self.assertIsNotNone(current_diagnostic_budget())
        self.assertIsNone(current_diagnostic_budget())
        self.assertTrue(may_real_llm_call(environment=ENV_PRODUCTION).allowed)

    def test_a_development_diagnostic_is_refused_too(self):
        with diagnostic_workload("dev check"):
            self.assertFalse(may_real_llm_call(environment="development").allowed)


class BudgetArithmeticTests(TestCase):
    def test_zero_is_the_default(self):
        self.assertEqual(DiagnosticBudget("r", 0).remaining, 0)
        self.assertFalse(DiagnosticBudget("r", 0).consume())

    def test_negative_and_junk_collapse_to_zero(self):
        for value in (-5, None, 0):
            self.assertEqual(DiagnosticBudget("r", value).authorized, 0)

    def test_it_reports_what_was_actually_spent(self):
        budget = DiagnosticBudget("r", 3, operator="danny")
        budget.consume()
        self.assertEqual(budget.as_audit(),
                         {"reason": "r", "authorized": 3, "spent": 1,
                          "operator": "danny"})


class TheAcceptanceRunnerCarriesTheBudgetTests(TestCase):
    """The gate is useless if the marker does not reach the worker."""

    def test_both_runners_accept_an_authorization(self):
        import inspect

        from apps.core.tasks import (run_cos_acceptance_conversation,
                                     run_cos_acceptance_turn)

        for task in (run_cos_acceptance_turn, run_cos_acceptance_conversation):
            signature = inspect.signature(task)
            self.assertIn("authorized_calls", signature.parameters, task.__name__)
            self.assertEqual(
                signature.parameters["authorized_calls"].default, 0,
                f"{task.__name__} must default to spending nothing")

    def test_both_runners_run_inside_the_gate(self):
        import inspect

        from apps.core import tasks

        for name in ("run_cos_acceptance_turn", "run_cos_acceptance_conversation"):
            source = inspect.getsource(getattr(tasks, name))
            self.assertIn("diagnostic_workload", source, name)
            self.assertIn("authorized_calls=authorized_calls", source, name)


@override_settings(CLAUDE_API_KEY="test-key-for-diagnostics")
class TheEndpointRequiresAnExplicitNumberTests(TestCase):
    URL = "/admin-console/api/claude/cos-run/"

    def setUp(self):
        from django.contrib.auth import get_user_model

        self.user = get_user_model().objects.create_user(
            email="spend@example.com", password="pw" * 8)
        self.headers = {"HTTP_X_CLAUDE_API_KEY": "test-key-for-diagnostics"}

    def _get(self, **params):
        params.setdefault("email", self.user.email)
        params.setdefault("message", "hello")
        with mock.patch("apps.core.celery_utils.safe_enqueue",
                        return_value=True) as enqueue:
            response = self.client.get(self.URL, params, **self.headers)
        return response, enqueue

    def test_the_default_authorizes_nothing(self):
        response, enqueue = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["authorized_calls"], 0)

    def test_the_default_is_passed_to_the_worker(self):
        with mock.patch("apps.core.tasks.run_cos_acceptance_turn"), \
                mock.patch("apps.core.celery_utils.safe_enqueue",
                           return_value=True) as enqueue:
            self.client.get(self.URL, {"email": self.user.email, "message": "hi"},
                            **self.headers)
        self.assertEqual(enqueue.call_args[0][-1], 0,
                         "the worker must be told it may not spend")

    def test_authorizing_requires_naming_who_agreed(self):
        response, _ = self._get(authorize_paid_calls="1")
        self.assertEqual(response.status_code, 400)
        self.assertIn("authorized_by", response.json()["error"])

    def test_an_authorized_run_passes_the_budget_through(self):
        with mock.patch("apps.core.celery_utils.safe_enqueue",
                        return_value=True) as enqueue:
            response = self.client.get(
                self.URL, {"email": self.user.email, "message": "hi",
                           "authorize_paid_calls": "2", "authorized_by": "danny"},
                **self.headers)
        self.assertEqual(response.json()["authorized_calls"], 2)
        self.assertEqual(enqueue.call_args[0][-1], 2)

    def test_it_refuses_an_unreasonable_number(self):
        response, _ = self._get(authorize_paid_calls="500", authorized_by="danny")
        self.assertEqual(response.status_code, 400)

    def test_it_refuses_nonsense(self):
        response, _ = self._get(authorize_paid_calls="lots", authorized_by="danny")
        self.assertEqual(response.status_code, 400)

    def test_authorizing_writes_an_audit_record_before_the_run(self):
        from apps.security.models import SecurityAuditLog

        with mock.patch("apps.core.celery_utils.safe_enqueue", return_value=True):
            self.client.get(
                self.URL, {"email": self.user.email, "message": "hi",
                           "authorize_paid_calls": "1", "authorized_by": "danny"},
                **self.headers)
        row = SecurityAuditLog.objects.filter(resource_id="cos-run").first()
        self.assertIsNotNone(row)
        self.assertEqual(row.details["authorized_paid_calls"], 1)
        self.assertEqual(row.details["authorized_by"], "danny")

    def test_an_unauthorized_run_writes_no_authorization_record(self):
        from apps.security.models import SecurityAuditLog

        self._get()
        self.assertFalse(SecurityAuditLog.objects.filter(resource_id="cos-run").exists())

    def test_the_audit_record_does_not_store_the_whole_address(self):
        from apps.security.models import SecurityAuditLog

        with mock.patch("apps.core.celery_utils.safe_enqueue", return_value=True):
            self.client.get(
                self.URL, {"email": self.user.email, "message": "hi",
                           "authorize_paid_calls": "1", "authorized_by": "danny"},
                **self.headers)
        blob = str(SecurityAuditLog.objects.filter(resource_id="cos-run").first().details)
        self.assertNotIn("spend@example.com", blob)
        self.assertIn("example.com", blob)
