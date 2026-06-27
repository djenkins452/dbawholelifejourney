# ==============================================================================
# File: apps/admin_console/tests/test_beth_acceptance_upgrade.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Tests for the Beth Acceptance Center upgrade — expanded bank, depth
#   levels, failure categories, root-cause grouping, grading, banned categories,
#   distinctiveness, boundary routing, and UI controls/grade. No real OpenAI.
# ==============================================================================
from types import SimpleNamespace

from django.test import TestCase
from django.urls import reverse

from apps.ai.chatgpt_cos import acceptance_rules as ar
from apps.ai.chatgpt_cos import acceptance_service as svc
from apps.admin_console.models import AcceptanceRun, AcceptanceResult
from apps.admin_console.tests.test_admin_console import AdminTestMixin


class QuestionBankTests(TestCase):
    def test_bank_is_large_and_structured(self):
        self.assertGreater(len(ar.QUESTIONS), 40)
        for q in ar.QUESTIONS:
            self.assertIn(q["depth"], ar.DEPTHS)
            self.assertIn("key", q)
            self.assertIn("text", q)

    def test_depth_levels_nest(self):
        smoke = ar.questions_for(depth="smoke")
        full = ar.questions_for(depth="full")
        deep = ar.questions_for(depth="deep")
        self.assertLess(len(smoke), len(full))
        self.assertLess(len(full), len(deep))
        # smoke is a subset of full is a subset of deep
        sk = {q["key"] for q in smoke}
        self.assertTrue(sk.issubset({q["key"] for q in full}))
        self.assertTrue({q["key"] for q in full}.issubset({q["key"] for q in deep}))

    def test_smoke_is_a_fast_gate(self):
        self.assertLessEqual(len(ar.questions_for(depth="smoke")), 16)

    def test_suite_and_depth_filtering(self):
        goals_deep = ar.questions_for("goals", "deep")
        self.assertTrue(all(ar.suite_of(q) == "goals" for q in goals_deep))
        self.assertGreater(len(goals_deep), len(ar.questions_for("goals", "smoke")))

    def test_general_and_boundary_present(self):
        self.assertTrue(any(q["domain"] == "general" for q in ar.QUESTIONS))
        self.assertTrue(any(q["key"].startswith("bnd_") for q in ar.QUESTIONS))


class BannedCategoryTests(TestCase):
    def test_coaching_system_deflection_all_banned(self):
        self.assertTrue(ar.banned_hits("Just maintain momentum."))
        self.assertTrue(ar.banned_hits("Per the source of truth state builder."))
        self.assertTrue(ar.banned_hits("Check your dashboard for details."))

    def test_category_mapping(self):
        self.assertEqual(ar.banned_category("maintain momentum"), "coaching")
        self.assertEqual(ar.banned_category("source of truth"), "system_language")
        self.assertEqual(ar.banned_category("check your dashboard"), "deflection")

    def test_system_and_deflection_are_critical(self):
        self.assertTrue(ar.is_critical_rule("banned_phrase:source of truth"))
        self.assertTrue(ar.is_critical_rule("banned_phrase:check your dashboard"))
        self.assertFalse(ar.is_critical_rule("banned_phrase:maintain momentum"))


class GradingTests(TestCase):
    def test_grades(self):
        self.assertEqual(ar.grade(96, 0), "GREEN")
        self.assertEqual(ar.grade(90, 0), "YELLOW")
        self.assertEqual(ar.grade(80, 0), "RED")
        self.assertEqual(ar.grade(100, 1), "RED")     # any critical -> RED

    def test_categorize_rule(self):
        self.assertEqual(ar.categorize_rule("banned_phrase:x"), "banned_phrase")
        self.assertEqual(ar.categorize_rule("wrong_domain(...)"), "wrong_domain")
        self.assertEqual(ar.categorize_rule("gate_evidence"), "response_quality")
        self.assertEqual(ar.categorize_rule("empty"), "empty_response")

    def test_critical_rules(self):
        self.assertTrue(ar.is_critical_rule("empty"))
        self.assertTrue(ar.is_critical_rule("wrong_domain(intent=x)"))
        self.assertTrue(ar.is_critical_rule("duplicate_answer"))
        self.assertFalse(ar.is_critical_rule("gate_actionable"))


class EvaluatorBoundaryTests(TestCase):
    def test_personal_question_routed_to_general_is_wrong_domain(self):
        spec = next(q for q in ar.QUESTIONS if q["key"] == "bnd_my_weight")
        fails = ar.evaluate(spec, "Your weight is 248 lb.", intent=None,
                            lane="general_conversation")
        self.assertTrue(any("wrong_domain" in f for f in fails))

    def test_general_question_must_be_general_lane(self):
        spec = next(q for q in ar.QUESTIONS if q["key"] == "gen_lincoln")
        ok = ar.evaluate(spec, "Lincoln was the 16th US president.",
                         intent=None, lane="general_conversation")
        self.assertEqual(ok, [])

    def test_evening_checkin_forbidden_morning_item(self):
        spec = next(q for q in ar.QUESTIONS if q["key"] == "checkin_agenda")
        fails = ar.evaluate(spec, "Next up: Workout. Begin workout now.")
        self.assertTrue(any(f.startswith("forbidden") for f in fails))


class DistinctivenessTests(TestCase):
    def test_same_answer_different_intent_flagged(self):
        rows = [
            {"key": "a", "intent": "goals_progress", "answer": "France 2027 is on pace today.",
             "distinct_group": "g", "fails": [], "passed": True},
            {"key": "b", "intent": "goal_on_track", "answer": "France 2027 is on pace today.",
             "distinct_group": "g", "fails": [], "passed": True},
        ]
        svc._detect_duplicates(rows)
        self.assertIn("duplicate_answer", rows[1]["fails"])

    def test_same_intent_paraphrases_not_flagged(self):
        rows = [
            {"key": "a", "intent": "goals_progress", "answer": "France 2027 is on pace.",
             "distinct_group": "g", "fails": [], "passed": True},
            {"key": "b", "intent": "goals_progress", "answer": "France 2027 is on pace.",
             "distinct_group": "g", "fails": [], "passed": True},
        ]
        svc._detect_duplicates(rows)
        self.assertNotIn("duplicate_answer", rows[1]["fails"])


class PromptGenerationTests(TestCase):
    def _fake(self):
        run = SimpleNamespace(
            environment="production", git_commit="abc123", suite_name="full",
            depth="full", completed_at="2026-06-26", created_at="2026-06-26",
            score_percent=78, pass_count=14, total_count=18, fail_count=4,
            grade="RED", critical_count=1, warning_count=0, avg_response_ms=1200,
            category_summary={"banned_phrase": 2, "missing_required": 1, "wrong_domain": 1})
        rows = [
            {"key": "goal_why_priority__0", "suite": "goals", "question": "Why?",
             "answer": "lock in consistency", "expected_intent": "goal_why_priority",
             "intent": "goal_why_priority", "lane": None, "openai_called": True,
             "fallback_used": False, "ms": 1200, "fails": ["banned_phrase:lock in consistency"],
             "passed": False, "spec": {"depth": "full"}},
            {"key": "goal_concerns__0", "suite": "goals", "question": "Slipping?",
             "answer": "all good", "expected_intent": "goal_concerns", "intent": "goal_concerns",
             "lane": None, "openai_called": True, "fallback_used": False, "ms": 900,
             "fails": ["missing_required_any:slipping|none"], "passed": False,
             "spec": {"depth": "full"}},
        ]
        return run, rows

    def test_chatgpt_prompt_has_summary_categories(self):
        run, rows = self._fake()
        p = svc.build_chatgpt_review_prompt(run, rows)
        self.assertIn("OVERALL RESULT", p)
        self.assertIn("FAILURE SUMMARY BY CATEGORY", p)
        self.assertIn("RELEASE READINESS", p)
        self.assertIn("systemic", p.lower())

    def test_claude_prompt_groups_root_causes(self):
        run, rows = self._fake()
        p = svc.build_claude_fix_prompt(run, rows)
        self.assertIn("LIKELY ROOT-CAUSE GROUPS", p)
        self.assertIn("coaching language", p.lower())
        self.assertIn("slipping", p.lower())
        self.assertIn("Treat the grouped failures as SYSTEMIC", p)
        self.assertIn("Do not stop for approval unless", p)


class UpgradeUITests(AdminTestMixin, TestCase):
    def setUp(self):
        self.staff = self.create_admin(email="bethup@example.com")

    def test_center_shows_depth_controls(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_console:beth_acceptance"))
        self.assertContains(resp, "Run Smoke Suite")
        self.assertContains(resp, "Run Deep Suite")
        self.assertContains(resp, "Evening mode")

    def test_run_detail_shows_grade_and_failure_summary(self):
        run = AcceptanceRun.objects.create(
            suite_name="full", depth="full", target_user=self.staff, status="completed",
            total_count=10, pass_count=8, fail_count=2, score_percent=80,
            grade="RED", critical_count=1, warning_count=1, avg_response_ms=1500,
            category_summary={"banned_phrase": 1, "wrong_domain": 1},
            chatgpt_review_prompt="REVIEW", claude_fix_prompt="FIX")
        AcceptanceResult.objects.create(run=run, question_key="goal_x", passed=False,
                                        failed_rules=["banned_phrase:x"], is_critical=True,
                                        sort_order=0)
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_console:beth_acceptance_run",
                                       kwargs={"pk": run.pk}))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "RED")
        self.assertContains(resp, "Failure summary by category")
        self.assertContains(resp, "Release readiness")

    def test_history_shows_grade(self):
        AcceptanceRun.objects.create(suite_name="full", depth="smoke",
                                     target_user=self.staff, status="completed",
                                     score_percent=100, grade="GREEN", total_count=12,
                                     pass_count=12)
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_console:beth_acceptance"))
        self.assertContains(resp, "GREEN")
