# ==============================================================================
# File: apps/ai/tests/test_acceptance_factual_trust.py
# Description: Deep suite — FACTUAL-TRUST acceptance categories (Architecture Laws
#   0/1/2/4/5). Pure-function evaluation tests (no DB, no OpenAI): Intent, Truth,
#   Freshness, Deterministic Retrieval, Stability, Regression. "Beth earns the
#   right to reason by first earning the right to be trusted."
# ==============================================================================
from django.test import SimpleTestCase

from apps.ai.chatgpt_cos import acceptance_rules as ar


def _q(key):
    return next(q for q in ar.QUESTIONS if q["key"] == key)


def _crit(spec, fails):
    return any(ar.is_critical_rule(r, spec) for r in fails)


class CategoryCoverageTests(SimpleTestCase):
    def test_all_six_categories_present_and_critical(self):
        cats = {q["category"] for q in ar.FACTUAL_TRUST_QUESTIONS}
        self.assertEqual(cats, {"intent", "truth", "freshness", "deterministic",
                                "stability", "regression"})
        # Every factual-trust question is release-blocking.
        for q in ar.FACTUAL_TRUST_QUESTIONS:
            self.assertEqual(q["criticality"], "critical", q["key"])
        # They live in the Deep tier and the 'factual' suite.
        for q in ar.FACTUAL_TRUST_QUESTIONS:
            self.assertEqual(q["depth"], "deep", q["key"])
            self.assertEqual(ar.suite_of(q), "factual", q["key"])


class IntentTests(SimpleTestCase):
    """Law 0 — answer the question actually asked."""
    def test_wrong_domain_answer_is_critical(self):
        spec = _q("intent_workout")  # "Did I workout today?"
        fails = ar.evaluate(spec, "You slept 6.9 hours last night.")  # answered SLEEP
        self.assertTrue(_crit(spec, fails))
        self.assertTrue(any(f.startswith("forbidden") for f in fails))
        self.assertTrue(any(f.startswith("missing_required_any") for f in fails))

    def test_correct_domain_answer_passes(self):
        spec = _q("intent_workout")
        self.assertEqual(ar.evaluate(spec, "You haven't worked out today — no workout logged."), [])


class TruthTests(SimpleTestCase):
    """Law 1/2 — cite a value, or honestly say it isn't available."""
    def test_value_or_honest_absence_passes_vague_fails(self):
        spec = _q("truth_weight")
        self.assertEqual(ar.evaluate(spec, "You weigh 285.9 lb."), [])
        self.assertEqual(ar.evaluate(spec, "I don't have today's weight yet."), [])
        fails = ar.evaluate(spec, "Your weight is doing fine.")
        self.assertIn("gate_value", fails)
        self.assertTrue(_crit(spec, fails))


class FreshnessTests(SimpleTestCase):
    """Law 1 — distinguish current / stale / pending / partial / missing."""
    def test_pending_must_acknowledge_no_data(self):
        spec = _q("fresh_pending")
        self.assertTrue(_crit(spec, ar.evaluate(spec, "You slept 6.9 hours.")))  # stale-as-current
        self.assertEqual(ar.evaluate(spec, "I don't have last night's sleep yet — Apple Health hasn't synced."), [])

    def test_current_must_cite_value(self):
        spec = _q("fresh_current")
        self.assertEqual(ar.evaluate(spec, "You slept 7.2 hours last night."), [])
        self.assertIn("gate_value", ar.evaluate(spec, "You slept well."))

    def test_partial_and_missing_states(self):
        self.assertEqual(ar.evaluate(_q("fresh_partial"),
                         "I only have part of today's steps so far — still syncing."), [])
        self.assertEqual(ar.evaluate(_q("fresh_missing"),
                         "I have no sleep data recorded for last night."), [])

    def test_all_five_states_declared(self):
        states = {_q(k)["freshness_expect"] for k in
                  ("fresh_current", "fresh_stale", "fresh_pending", "fresh_partial", "fresh_missing")}
        self.assertEqual(states, {"current", "stale", "pending", "partial", "missing"})

    def test_state_matrix_is_deterministic_only_excluded_from_live_run(self):
        # CERTIFICATION FIX: the per-state matrix cannot be set up by the read-only
        # live harness, so it must NOT appear in the live deep run (validated in the
        # deterministic gate). The coherent honesty checks DO run live.
        live_keys = {q["key"] for q in ar.questions_for("full", "deep")}
        for k in ("fresh_current", "fresh_stale", "fresh_pending", "fresh_partial",
                  "fresh_missing"):
            self.assertNotIn(k, live_keys)                 # excluded from live
            self.assertTrue(_q(k)["deterministic_only"])   # but kept as a fixture
        self.assertIn("fresh_sleep_honest", live_keys)     # coherent live check present
        self.assertIn("fresh_steps_honest", live_keys)


class DeterministicRetrievalTests(SimpleTestCase):
    """Law 4 — a deterministic question never hides behind an AI failure."""
    def test_ai_failure_message_is_critical(self):
        spec = _q("det_steps")
        fails = ar.evaluate(spec, "my external knowledge service is temporarily unavailable right now")
        self.assertIn("openai_failure_message", fails)
        self.assertTrue(_crit(spec, fails))

    def test_deterministic_value_passes(self):
        self.assertEqual(ar.evaluate(_q("det_steps"), "You got 8,123 steps yesterday."), [])

    def test_covers_canonical_domains(self):
        keys = {q["key"] for q in ar.FACTUAL_TRUST_QUESTIONS if q["category"] == "deterministic"}
        for d in ("weight", "sleep", "steps", "calories", "journal", "workouts", "meds", "appts"):
            self.assertIn(f"det_{d}", keys)


class StabilityTests(SimpleTestCase):
    """Law 5 — identical question + unchanged data ⇒ identical facts."""
    def test_divergent_facts_are_critical(self):
        v = ar.stability_violations(["You slept 5.3 hours.", "You slept 6.9 hours."])
        self.assertTrue(v and v[0].startswith("unstable_fact"))
        self.assertTrue(ar.is_critical_rule(v[0]))

    def test_identical_facts_pass(self):
        self.assertEqual(ar.stability_violations(["5.3 hours", "5.3 hours"]), [])
        self.assertEqual(ar.stability_violations(["You weigh 285.9 lb", "Your weight is 285.9 lb"]), [])


class RegressionTests(SimpleTestCase):
    """Every historical bug is a permanent, release-blocking test."""
    def test_wrong_domain_regression(self):
        spec = _q("reg_wrong_domain")
        self.assertTrue(_crit(spec, ar.evaluate(spec, "You slept 6.9 hours.")))
        self.assertEqual(ar.evaluate(spec, "You haven't worked out today."), [])

    def test_deterministic_steps_regression(self):
        spec = _q("reg_det_steps")
        self.assertTrue(_crit(spec, ar.evaluate(spec, "Assistant temporarily unavailable, try again")))
        self.assertEqual(ar.evaluate(spec, "You walked 8,000 steps yesterday."), [])

    def test_stale_sleep_and_contradictory_regressions_are_stability_gated(self):
        self.assertEqual(_q("reg_stale_sleep")["stability_group"], "reg_sleep_stable")
        self.assertEqual(_q("reg_contradictory")["stability_group"], "reg_weight_stable")


class DeepReleaseGateTests(SimpleTestCase):
    """Deep is the factual-trust release gate: any factual-trust critical → RED."""
    def test_single_factual_critical_fails_release(self):
        # One critical (e.g. wrong-question) ⇒ RED regardless of score.
        self.assertEqual(ar.grade(99.0, critical_count=1), "RED")
        self.assertEqual(ar.grade(100.0, critical_count=0), "GREEN")
