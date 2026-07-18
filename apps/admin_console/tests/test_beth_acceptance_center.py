# ==============================================================================
# File: apps/admin_console/tests/test_beth_acceptance_center.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Tests for the Beth Acceptance Center (models, shared runner with a
#   MOCKED Beth/OpenAI, and the admin-only views). No real OpenAI calls.
# ==============================================================================
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.admin_console.models import AcceptanceRun, AcceptanceResult
from apps.admin_console.tests.test_admin_console import AdminTestMixin

User = get_user_model()


def _mk_user(email, staff=False):
    # lightweight user for model/service tests (no client/middleware involved)
    from apps.users.models import TermsAcceptance
    u = User.objects.create_user(email=email, password="x", is_staff=staff)
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


def _fake_ask(text):
    """Injected asker (deterministic, no OpenAI): a gold France-progress answer, else
    a stub. Mirrors the (answer, evidence) contract of the production gateway asker."""
    if "progressing" in text:
        answer = (
            "'France 2027 Family 18K Mission' is in its weight-loss foundation "
            "phase and on pace — weight trending down, workouts on schedule. The next "
            "milestone is a return to running base. Today's lever: complete "
            "today's scheduled workout.")
    else:
        answer = "ok"
    return answer, {"runtime_used": "test"}


class AcceptanceModelTests(TestCase):
    def test_run_and_result_creation_and_score(self):
        u = _mk_user("owner1@example.com", staff=True)
        run = AcceptanceRun.objects.create(suite_name="goals", target_user=u,
                                           total_count=2, pass_count=1, fail_count=1,
                                           score_percent=50, status="completed")
        AcceptanceResult.objects.create(run=run, question_key="goal_progress",
                                        passed=True, sort_order=0)
        AcceptanceResult.objects.create(run=run, question_key="goal_risk",
                                        passed=False, failed_rules=["gate_actionable"],
                                        sort_order=1)
        self.assertEqual(run.results.count(), 2)
        self.assertFalse(run.is_green)
        self.assertEqual(run.status_color, "#ef4444")     # completed with failures
        self.assertEqual(AcceptanceResult.objects.filter(run=run, passed=False).count(), 1)


class AcceptanceServiceTests(TestCase):
    def test_execute_run_persists_results_and_prompts(self):
        from apps.ai.chatgpt_cos.acceptance_service import execute_run
        u = _mk_user("owner2@example.com", staff=True)
        run = AcceptanceRun.objects.create(suite_name="goals", target_user=u,
                                           created_by=u, status="running")
        execute_run(run, evening=False, ask=_fake_ask)
        run.refresh_from_db()
        self.assertEqual(run.status, "completed")
        self.assertEqual(run.total_count, run.results.count())
        self.assertGreater(run.total_count, 0)
        # at least the progress question passes; stub answers fail their gates
        self.assertGreaterEqual(run.pass_count, 1)
        self.assertGreaterEqual(run.fail_count, 1)
        self.assertEqual(run.pass_count + run.fail_count, run.total_count)
        # prompts generated and reference failures + routing metadata
        self.assertIn("FAILED QUESTIONS", run.chatgpt_review_prompt)
        self.assertIn("FAILING QUESTIONS", run.claude_fix_prompt)
        self.assertIn("FAILURE SUMMARY BY CATEGORY", run.chatgpt_review_prompt)
        self.assertIn("Do not stop for approval unless", run.claude_fix_prompt)

    def test_suite_filtering(self):
        from apps.ai.chatgpt_cos.acceptance_rules import questions_for
        self.assertTrue(all(q["domain"] == "health"
                            for q in questions_for("health")))
        self.assertGreater(len(questions_for("full")), len(questions_for("health")))

    def test_no_chat_history_polluted(self):
        # the throwaway conversation is deleted after the run
        from apps.ai.chatgpt_cos.acceptance_service import execute_run
        from apps.ai.models import AssistantConversation
        u = _mk_user("owner3@example.com", staff=True)
        run = AcceptanceRun.objects.create(suite_name="health", target_user=u, status="running")
        before = AssistantConversation.objects.filter(user=u).count()
        execute_run(run, evening=False, ask=_fake_ask)
        self.assertEqual(AssistantConversation.objects.filter(user=u).count(), before)


class AcceptanceViewTests(AdminTestMixin, TestCase):
    def setUp(self):
        self.staff = self.create_admin(email="bethadmin@example.com")
        self.normal = self.create_user(email="bethuser@example.com")

    def test_center_requires_admin(self):
        self.client.force_login(self.normal)
        resp = self.client.get(reverse("admin_console:beth_acceptance"))
        self.assertIn(resp.status_code, (302, 403))

    def test_center_loads_for_admin(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_console:beth_acceptance"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Beth Acceptance Center")
        self.assertContains(resp, "Run Full Suite")

    def test_center_shows_deterministic_certification_panel(self):
        # The one operational certification view — deterministic (Owner-1) portion.
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_console:beth_acceptance"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Truth Retrieval Certification")
        self.assertContains(resp, "nutrition")           # a domain row renders
        self.assertContains(resp, "Executive Judgment")  # the layered hierarchy is shown

    def test_start_run_creates_run_and_redirects(self):
        self.client.force_login(self.staff)
        with patch("apps.ai.chatgpt_cos.tasks.run_beth_acceptance.delay") as m:
            resp = self.client.post(reverse("admin_console:beth_acceptance_start"),
                                    {"mode": "goals", "evening": "1"})
        self.assertTrue(m.called)
        run = AcceptanceRun.objects.latest("created_at")
        self.assertEqual(run.suite_name, "goals")
        self.assertEqual(run.status, "running")
        self.assertRedirects(resp, reverse("admin_console:beth_acceptance_run",
                                           kwargs={"pk": run.pk}))

    def test_run_detail_shows_results_and_copy_prompts(self):
        run = AcceptanceRun.objects.create(
            suite_name="goals", target_user=self.staff, status="completed",
            total_count=1, pass_count=0, fail_count=1, score_percent=0,
            chatgpt_review_prompt="REVIEW PROMPT BODY",
            claude_fix_prompt="FIX PROMPT BODY")
        AcceptanceResult.objects.create(run=run, question_key="goal_risk",
                                        question_text="What's my biggest goal risk?",
                                        passed=False, failed_rules=["gate_actionable"],
                                        sort_order=0)
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_console:beth_acceptance_run",
                                       kwargs={"pk": run.pk}))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Copy ChatGPT Review Prompt")
        self.assertContains(resp, "Copy Claude Fix Prompt")
        self.assertContains(resp, "REVIEW PROMPT BODY")
        self.assertContains(resp, "gate_actionable")

    def test_run_detail_shows_structured_retrieval_evidence(self):
        # The operator can inspect, per question: runtime, selected tool, provider,
        # tool args, retrieved evidence, and the first failing layer — in the EXISTING
        # result detail (progressive disclosure), no separate page.
        run = AcceptanceRun.objects.create(
            suite_name="health", target_user=self.staff, status="completed",
            total_count=1, pass_count=0, fail_count=1, score_percent=0)
        AcceptanceResult.objects.create(
            run=run, question_key="weight_current",
            question_text="What do I weigh?", passed=False,
            failed_rules=["gate_value"], response_text="I'm not sure.",
            runtime_used="model_interface", selected_tool="get_entity",
            canonical_provider="health",
            tool_arguments={"domain": "health", "entity_type": "measurement"},
            retrieved_records={"status": "empty"},
            retrieval_evidence=[{"tool": "get_entity", "status": "empty",
                                 "args": {"domain": "health"}}],
            first_failing_layer="evidence", sort_order=0)
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_console:beth_acceptance_run",
                                       kwargs={"pk": run.pk}))
        self.assertEqual(resp.status_code, 200)
        # prominent: runtime, provider, and the first failing layer
        self.assertContains(resp, "model_interface")
        self.assertContains(resp, "evidence")            # first_failing_layer
        # expandable technical evidence
        self.assertContains(resp, "Retrieval evidence")
        self.assertContains(resp, "get_entity")          # selected tool / ledger
        self.assertContains(resp, "tool ledger")
