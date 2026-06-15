"""Tests for CoS coherence guards — Phase 1 (observe-only).

These are PURE unit tests (no DB): every detector is exercised via its
optional pre-computed inputs (entity_set / canonical), so the only DB-touching
paths (build_canonical_entity_set, get_canonical_nutrition) are covered with
patched data sources. The Phase 1 contract under test: detectors DETECT and
return findings but the wiring never alters Beth's output.
"""

from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.ai import cos_coherence_guards as g


class _StubUser:
    id = 42


USER = _StubUser()


@override_settings(WLJ_BETH_COHERENCE_DIAG_ENABLED=True)
class CountCoherenceTests(SimpleTestCase):
    def test_coherent_counts_no_findings(self):
        # 25 total, 19 done → 6 remaining, 6 listed.
        findings = g.check_count_coherence(
            USER, routine_total=25, routine_done=19,
            pending_names=["a", "b", "c", "d", "e", "f"],
        )
        self.assertEqual(findings, [])

    def test_count_list_mismatch_flagged(self):
        # The incident: 19/25 (=6 remaining) but only 5 items listed.
        findings = g.check_count_coherence(
            USER, routine_total=25, routine_done=19,
            pending_names=["a", "b", "c", "d", "e"],
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["type"], "count_list_mismatch")
        self.assertEqual(findings[0]["stated_remaining"], 6)
        self.assertEqual(findings[0]["listed_items"], 5)

    def test_impossible_med_counts_flagged(self):
        findings = g.check_count_coherence(
            USER, routine_total=0, routine_done=0, pending_names=[],
            meds_expected=2, meds_taken=3, meds_skipped=0,
        )
        self.assertTrue(any(f["type"] == "count_impossible" for f in findings))

    def test_meds_coherent_no_findings(self):
        findings = g.check_count_coherence(
            USER, routine_total=0, routine_done=0, pending_names=[],
            meds_expected=3, meds_taken=2, meds_skipped=1,
        )
        self.assertEqual(findings, [])

    @override_settings(WLJ_BETH_COHERENCE_DIAG_ENABLED=False)
    def test_disabled_returns_empty(self):
        findings = g.check_count_coherence(
            USER, routine_total=25, routine_done=19, pending_names=["a"],
        )
        self.assertEqual(findings, [])


@override_settings(WLJ_BETH_COHERENCE_DIAG_ENABLED=True)
class EntityHallucinationTests(SimpleTestCase):
    def test_invented_group_label_flagged(self):
        findings = g.detect_operational_entity_hallucination(
            USER,
            "You still have your Nightly Medications to take before bed.",
            entity_set={"metformin hcl er", "magnesium glycinate"},
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["type"], "invented_group_label")
        self.assertEqual(findings[0]["phrase"].lower(), "nightly medications")

    def test_real_entity_label_not_flagged(self):
        # If a real entity literally carries that label, it's allowed.
        findings = g.detect_operational_entity_hallucination(
            USER,
            "Take your Morning Vitamins.",
            entity_set={"morning vitamins"},
        )
        self.assertEqual(findings, [])

    def test_individual_med_names_not_flagged(self):
        findings = g.detect_operational_entity_hallucination(
            USER,
            "Take Metformin HCL ER and Magnesium glycinate tonight.",
            entity_set={"metformin hcl er", "magnesium glycinate"},
        )
        self.assertEqual(findings, [])

    def test_variants_matched(self):
        for phrase in ("evening meds", "bedtime pills", "AM supplements",
                       "daily medications"):
            findings = g.detect_operational_entity_hallucination(
                USER, f"Remember your {phrase}.", entity_set=set(),
            )
            self.assertEqual(len(findings), 1, phrase)

    @override_settings(WLJ_BETH_COHERENCE_DIAG_ENABLED=False)
    def test_disabled_returns_empty(self):
        findings = g.detect_operational_entity_hallucination(
            USER, "Your Nightly Medications.", entity_set=set(),
        )
        self.assertEqual(findings, [])


@override_settings(WLJ_BETH_COHERENCE_DIAG_ENABLED=True)
class CalorieDivergenceTests(SimpleTestCase):
    def _canon(self, compliance):
        return {
            "available": True,
            "compliance_pct": compliance,
            "pct_under_target": max(0.0, 100.0 - compliance),
            "pct_over_target": max(0.0, compliance - 100.0),
        }

    def test_divergent_calorie_pct_flagged(self):
        # Canonical: 78% compliance → 22% under. Beth says 26% under.
        findings = g.detect_calorie_divergence(
            USER,
            "Your calories are 26% under target today.",
            canonical=self._canon(78.0),
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["type"], "calorie_pct_divergence")
        self.assertEqual(findings[0]["stated_pct"], 26.0)
        self.assertEqual(findings[0]["canonical_pct"], 22.0)

    def test_matching_calorie_pct_not_flagged(self):
        findings = g.detect_calorie_divergence(
            USER,
            "Your calories are 22% under target today.",
            canonical=self._canon(78.0),
        )
        self.assertEqual(findings, [])

    def test_within_tolerance_not_flagged(self):
        # 22% canonical vs 24% stated → exactly 2pp, within tolerance.
        findings = g.detect_calorie_divergence(
            USER,
            "Calories about 24% under target.",
            canonical=self._canon(78.0),
        )
        self.assertEqual(findings, [])

    def test_non_calorie_percentage_ignored(self):
        findings = g.detect_calorie_divergence(
            USER,
            "Your protein is 26% under target.",
            canonical=self._canon(78.0),
        )
        self.assertEqual(findings, [])

    def test_unavailable_canonical_no_findings(self):
        findings = g.detect_calorie_divergence(
            USER,
            "Your calories are 26% under target.",
            canonical={"available": False},
        )
        self.assertEqual(findings, [])


@override_settings(WLJ_BETH_COHERENCE_DIAG_ENABLED=True)
class CanonicalNutritionTests(SimpleTestCase):
    def test_computes_under_target(self):
        with patch(
            "apps.core.ai_state.state_builder.build_nutrition_state",
            return_value={
                "enabled": True,
                "daily_calories": 1560.0,
                "calorie_target": 2000,
                "calorie_compliance_pct": 78.0,
            },
        ):
            out = g.get_canonical_nutrition(USER)
        self.assertTrue(out["available"])
        self.assertEqual(out["compliance_pct"], 78.0)
        self.assertEqual(out["pct_under_target"], 22.0)
        self.assertEqual(out["pct_over_target"], 0.0)

    def test_over_target(self):
        with patch(
            "apps.core.ai_state.state_builder.build_nutrition_state",
            return_value={
                "enabled": True,
                "daily_calories": 2300.0,
                "calorie_target": 2000,
                "calorie_compliance_pct": 115.0,
            },
        ):
            out = g.get_canonical_nutrition(USER)
        self.assertEqual(out["pct_over_target"], 15.0)
        self.assertEqual(out["pct_under_target"], 0.0)

    def test_disabled_nutrition_unavailable(self):
        with patch(
            "apps.core.ai_state.state_builder.build_nutrition_state",
            return_value={"enabled": False},
        ):
            out = g.get_canonical_nutrition(USER)
        self.assertFalse(out["available"])


@override_settings(
    WLJ_BETH_COHERENCE_DIAG_ENABLED=True, WLJ_BETH_COUNT_GUARD_ENABLED=True)
class EnforceCountCoherenceTests(SimpleTestCase):
    def test_incoherent_count_claim_failclosed(self):
        # Canonical: 25 total, 19 done → 6 remaining, but only 5 real items.
        text = (
            "You're at 19 of 25 routine items complete. "
            "Keep going — you've got this!"
        )
        out, n = g.enforce_count_coherence(
            text, USER, routine_total=25, routine_done=19,
            pending_names=["Shower", "Stretch", "Vitamins", "Walk", "Read"],
        )
        self.assertEqual(n, 1)
        self.assertNotIn("19 of 25", out)
        self.assertIn("mismatch in your checklist counts", out)
        # Lists the ACTUAL items, invents nothing.
        self.assertIn("Shower", out)
        self.assertIn("Read", out)
        # Untouched sentence preserved.
        self.assertIn("you've got this", out)

    def test_remaining_phrasing_failclosed(self):
        out, n = g.enforce_count_coherence(
            "You have 6 routine items remaining today.",
            USER, routine_total=25, routine_done=19,
            pending_names=["A", "B", "C", "D", "E"],
        )
        self.assertEqual(n, 1)
        self.assertNotIn("6 routine items remaining", out)

    def test_coherent_count_untouched(self):
        # 25 total, 20 done → 5 remaining, 5 listed → natural, no correction.
        text = "You're at 20 of 25 routine items complete. Nice momentum."
        out, n = g.enforce_count_coherence(
            text, USER, routine_total=25, routine_done=20,
            pending_names=["A", "B", "C", "D", "E"],
        )
        self.assertEqual(n, 0)
        self.assertEqual(out, text)

    def test_medication_sentence_not_clobbered(self):
        # Routine counts incoherent, but the count claim is about DOSES.
        text = "You've taken 4 of 6 medication doses today."
        out, n = g.enforce_count_coherence(
            text, USER, routine_total=25, routine_done=19,
            pending_names=["A", "B", "C", "D", "E"],
        )
        self.assertEqual(n, 0)
        self.assertEqual(out, text)

    @override_settings(WLJ_BETH_COUNT_GUARD_ENABLED=False)
    def test_guard_off_observe_only(self):
        text = "You're at 19 of 25 routine items complete."
        out, n = g.enforce_count_coherence(
            text, USER, routine_total=25, routine_done=19,
            pending_names=["A", "B", "C", "D", "E"],
        )
        self.assertEqual(n, 0)
        self.assertEqual(out, text)  # observe-only: not altered


@override_settings(
    WLJ_BETH_COHERENCE_DIAG_ENABLED=True, WLJ_BETH_ENTITY_GUARD_ENABLED=True)
class EnforceEntityHallucinationTests(SimpleTestCase):
    def test_invented_group_label_stripped(self):
        out, n = g.enforce_entity_hallucination(
            "Don't forget your Nightly Medications before bed.",
            USER, entity_set={"metformin hcl er", "magnesium glycinate"},
        )
        self.assertEqual(n, 1)
        self.assertNotIn("Nightly Medications", out)
        self.assertIn("your medications before bed", out)

    def test_real_entity_label_kept(self):
        out, n = g.enforce_entity_hallucination(
            "Take your Morning Vitamins.",
            USER, entity_set={"morning vitamins"},
        )
        self.assertEqual(n, 0)
        self.assertIn("Morning Vitamins", out)

    def test_individual_med_names_untouched(self):
        text = "Take Metformin HCL ER and Magnesium glycinate tonight."
        out, n = g.enforce_entity_hallucination(
            text, USER, entity_set={"metformin hcl er", "magnesium glycinate"},
        )
        self.assertEqual(n, 0)
        self.assertEqual(out, text)

    @override_settings(WLJ_BETH_ENTITY_GUARD_ENABLED=False)
    def test_guard_off_observe_only(self):
        text = "Don't forget your Nightly Medications."
        out, n = g.enforce_entity_hallucination(text, USER, entity_set=set())
        self.assertEqual(n, 0)
        self.assertEqual(out, text)  # observe-only: not altered
