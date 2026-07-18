"""Integration tests for the Truth Validation runner (execute_truth_run).

Uses an INJECTED asker (no OpenAI) and a patched deterministic resolver so the run is
exercised end-to-end — send prompt -> resolve expected WLJ object -> deterministic
compare -> persist AcceptanceResult -> finalize — without touching the live model. The
comparison itself is proven separately in test_truth_validation_comparison.
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.admin_console.models import AcceptanceResult, AcceptanceRun
from apps.core.truth.validation.surface import ExpectedObject

User = get_user_model()


def _present_weight(user, prompt):
    # A realistic weight entity: a numeric value+unit and a text source. (The `kind`
    # metadata key is skipped by the flattener; identity here is a real surfaced value.)
    return ExpectedObject(domain="health", provider="health.entity(weight)",
                          present=True, resolved_identity="",
                          selection_rule="Most recent weight (provider order)",
                          entity={"kind": "weight",
                                  "standing": {"value": 185, "unit": "lb"},
                                  "definition": {"source": "Apple Health"}})


def _absent(user, prompt):
    return ExpectedObject(domain="health", provider="health.entity(weight)",
                          present=False, reason="No record.")


class ExecuteTruthRunTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="tv@example.com", password="x")
        cls.user.is_staff = True
        cls.user.save()

    def _run(self, scope_key="body.weigh_in"):
        return AcceptanceRun.objects.create(
            validation_type="truth", suite_name="truth", depth="truth",
            scope_kind="object", scope_key=scope_key,
            target_user=self.user, created_by=self.user, status="running")

    @patch("apps.core.truth.validation.resolve_expected_object", _present_weight)
    def test_object_passes_when_value_present(self):
        from apps.ai.chatgpt_cos.truth_validation_service import execute_truth_run
        run = self._run()
        ask = lambda text: ("You weigh 185 lb, synced from Apple Health.", {})
        execute_truth_run(run, ask=ask)
        run.refresh_from_db()
        self.assertEqual(run.status, "completed")
        self.assertEqual(run.total_count, 1)
        result = run.results.get()
        self.assertTrue(result.passed)
        self.assertFalse(result.is_na)
        self.assertGreaterEqual(result.check_pass_count, 1)
        # a numeric-with-unit check exists and is present
        statuses = {c["label"]: c["status"] for c in result.checks if not c["is_forbidden"]}
        self.assertEqual(statuses.get("value"), "present")

    @patch("apps.core.truth.validation.resolve_expected_object", _present_weight)
    def test_object_fails_and_reports_bug_when_value_missing(self):
        from apps.ai.chatgpt_cos.truth_validation_service import execute_truth_run
        run = self._run()
        ask = lambda text: ("I don't have that information yet.", {})
        execute_truth_run(run, ask=ask)
        run.refresh_from_db()
        self.assertEqual(run.fail_count, 1)
        self.assertLess(run.score_percent, 100)
        bugs = (run.raw_report_json or {}).get("bugs", [])
        self.assertTrue(bugs)
        self.assertEqual(bugs[0]["object"], "body.weigh_in")

    @patch("apps.core.truth.validation.resolve_expected_object", _present_weight)
    def test_mismatch_is_a_contradiction_bug(self):
        from apps.ai.chatgpt_cos.truth_validation_service import execute_truth_run
        run = self._run()
        ask = lambda text: ("You weigh 172 lb.", {})   # contradicts 185
        execute_truth_run(run, ask=ask)
        run.refresh_from_db()
        result = run.results.get()
        self.assertFalse(result.passed)
        self.assertEqual(run.grade, "RED")   # a contradiction can never be GREEN/YELLOW

    @patch("apps.core.truth.validation.resolve_expected_object", _absent)
    def test_absent_record_is_na_not_fail(self):
        from apps.ai.chatgpt_cos.truth_validation_service import execute_truth_run
        run = self._run()
        ask = lambda text: ("I don't see any weigh-ins.", {})
        execute_truth_run(run, ask=ask)
        run.refresh_from_db()
        result = run.results.get()
        self.assertTrue(result.is_na)
        self.assertEqual(run.na_count, 1)
        self.assertEqual(run.fail_count, 0)


def _present_named(user, prompt):
    return ExpectedObject(
        domain="faith", provider="faith.entity(reading_plan)", present=True,
        resolved_identity="Walking With God Through Scripture",
        selection_rule="Current active reading_plan (status='active')",
        resolved_from="Faith → reading_plan", object_status="active",
        entity={"kind": "reading_plan", "identity": "Walking With God Through Scripture",
                "status": "active", "plan": {"current_day": 2}})


class PromptResolutionModeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="tv3@example.com", password="x")

    def _run(self, prompt_mode="resolved"):
        return AcceptanceRun.objects.create(
            validation_type="truth", suite_name="truth", depth="truth",
            scope_kind="object", scope_key="faith.reading_plan", prompt_mode=prompt_mode,
            target_user=self.user, created_by=self.user, status="running")

    @patch("apps.core.truth.validation.resolve_expected_object", _present_named)
    def test_resolved_mode_binds_prompt_to_resolved_object(self):
        from apps.ai.chatgpt_cos.truth_validation_service import execute_truth_run
        sent = {}
        def ask(text):
            sent["text"] = text
            return ("You're on day 2 of Walking With God Through Scripture.", {})
        execute_truth_run(self._run("resolved"), ask=ask)
        # the CoS was asked about the RESOLVED object by name, not "my current Bible study"
        self.assertIn("Walking With God Through Scripture", sent["text"])
        self.assertNotIn("my current Bible study", sent["text"])

    @patch("apps.core.truth.validation.resolve_expected_object", _present_named)
    def test_natural_mode_sends_raw_prompt(self):
        from apps.ai.chatgpt_cos.truth_validation_service import execute_truth_run
        sent = {}
        def ask(text):
            sent["text"] = text
            return ("...", {})
        execute_truth_run(self._run("natural"), ask=ask)
        self.assertEqual(sent["text"], "Tell me everything you know about my current Bible study.")

    @patch("apps.core.truth.validation.resolve_expected_object", _present_named)
    def test_resolution_card_persisted(self):
        from apps.ai.chatgpt_cos.truth_validation_service import execute_truth_run
        run = self._run("resolved")
        execute_truth_run(run, ask=lambda t: ("day 2", {}))
        res = run.results.get().raw_result_json["resolution"]
        self.assertEqual(res["resolved_object"], "Walking With God Through Scripture")
        self.assertEqual(res["status"], "active")
        self.assertIn("active", res["selection_rule"])


class OverrideRecomputeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="tv2@example.com", password="x")

    def test_override_flips_grade_and_records_log(self):
        run = AcceptanceRun.objects.create(validation_type="truth", status="completed",
                                           scope_kind="object", scope_key="x")
        result = AcceptanceResult.objects.create(
            run=run, object_key="x", question_key="x",
            checks=[{"label": "value", "path": "p", "kind": "numeric", "unit": "lb",
                     "expected": "185 lb", "extracted": "", "status": "missing",
                     "is_forbidden": False}],
            check_pass_count=0, check_total=1, passed=False)
        ok = result.apply_override(check_index=0, new_status="present",
                                   reason="answer said 'about 185'", by_user=self.user)
        self.assertTrue(ok)
        result.refresh_from_db()
        self.assertTrue(result.passed)
        self.assertEqual(result.check_pass_count, 1)
        self.assertEqual(len(result.override_log), 1)
        self.assertEqual(result.override_log[0]["to"], "present")
