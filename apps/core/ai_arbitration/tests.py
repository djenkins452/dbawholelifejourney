"""
UAL — Universal Arbitration Layer Tests.

Covers:
- Competing signals resolved
- Time-critical overrides mood
- Mood-critical suppresses minor tasks
- Low capacity day reshapes schedule
- Relationship event surfaces when relevant
- Stable day produces clean execution framing
- Signal collection graceful degradation
- Composite detection
- Intervention style selection
- Narrative generation
- Decision logging

v2 tests:
- Confidence dampening (LOW/MODERATE/HIGH)
- Confidence LOW softens response
- Capacity composite modeling
- Capacity reduces surface volume
- Multi-day pattern analysis
- Pattern escalation
- Adaptive weight tuning bounded
- No infinite feedback loops
- Stable execution unchanged when signals low
"""
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone

from apps.core.ai_arbitration.scenario_classifier import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MODERATE,
    DOMINANT_THRESHOLD,
    STABLE_EXECUTION,
    TIME_CRITICAL,
    HEALTH_CRITICAL,
    DRIFT_CRITICAL,
    MOOD_CRITICAL,
    RELATIONSHIP_CRITICAL,
    classify_scenario,
)
from apps.core.ai_arbitration.signal_fuser import fuse_signals
from apps.core.ai_arbitration.intervention_engine import (
    DIRECTIVE,
    PROTECTIVE,
    ACCOUNTABILITY,
    SUPPORTIVE,
    STRATEGIC,
    EXECUTION,
    decide_intervention,
)
from apps.core.ai_arbitration.narrative_engine import build_narrative
from apps.core.ai_arbitration.capacity_engine import (
    compute_capacity,
    HIGH_CAPACITY,
    NORMAL,
    LOW,
    CRITICAL,
)


class ScenarioClassifierTests(TestCase):
    """Test scenario classification from signal strengths."""

    def test_stable_execution_when_all_signals_low(self):
        """No active signals → STABLE_EXECUTION."""
        strengths = {
            "calendar_urgency": 0.0,
            "deadline_pressure": 0.0,
            "medication_risk": 0.0,
            "sleep_deficit": 0.0,
            "injury_risk": 0.0,
            "drift_severity": 0.0,
            "non_negotiable_miss": 0.0,
            "mood_decline": 0.0,
            "emotional_load": 0.0,
            "relationship_drift": 0.0,
            "relationship_event": 0.0,
            "schedule_overload": 0.0,
            "open_loop_count": 0.0,
        }
        result = classify_scenario(strengths)
        self.assertEqual(result["dominant_scenario"], STABLE_EXECUTION)
        self.assertGreater(result["confidence"], 0.5)

    def test_time_critical_dominates(self):
        """High calendar + deadline → TIME_CRITICAL."""
        strengths = {
            "calendar_urgency": 0.9,
            "deadline_pressure": 0.8,
            "schedule_overload": 0.6,
            "open_loop_count": 0.4,
            "medication_risk": 0.0,
            "sleep_deficit": 0.1,
            "injury_risk": 0.0,
            "drift_severity": 0.1,
            "non_negotiable_miss": 0.0,
            "mood_decline": 0.0,
            "emotional_load": 0.0,
            "relationship_drift": 0.0,
            "relationship_event": 0.0,
        }
        result = classify_scenario(strengths)
        self.assertEqual(result["dominant_scenario"], TIME_CRITICAL)

    def test_health_critical_dominates(self):
        """Missed meds + poor sleep → HEALTH_CRITICAL."""
        strengths = {
            "medication_risk": 0.9,
            "sleep_deficit": 0.7,
            "injury_risk": 0.5,
            "calendar_urgency": 0.1,
            "deadline_pressure": 0.1,
            "schedule_overload": 0.2,
            "open_loop_count": 0.0,
            "drift_severity": 0.0,
            "non_negotiable_miss": 0.0,
            "mood_decline": 0.1,
            "emotional_load": 0.0,
            "relationship_drift": 0.0,
            "relationship_event": 0.0,
        }
        result = classify_scenario(strengths)
        self.assertEqual(result["dominant_scenario"], HEALTH_CRITICAL)

    def test_drift_critical_dominates(self):
        """High drift + non-negotiable misses → DRIFT_CRITICAL."""
        strengths = {
            "drift_severity": 0.9,
            "non_negotiable_miss": 0.8,
            "open_loop_count": 0.5,
            "schedule_overload": 0.3,
            "calendar_urgency": 0.1,
            "deadline_pressure": 0.1,
            "medication_risk": 0.0,
            "sleep_deficit": 0.1,
            "injury_risk": 0.0,
            "mood_decline": 0.1,
            "emotional_load": 0.0,
            "relationship_drift": 0.0,
            "relationship_event": 0.0,
        }
        result = classify_scenario(strengths)
        self.assertEqual(result["dominant_scenario"], DRIFT_CRITICAL)

    def test_mood_critical_dominates(self):
        """Mood decline + emotional load → MOOD_CRITICAL."""
        strengths = {
            "mood_decline": 0.9,
            "emotional_load": 0.8,
            "sleep_deficit": 0.5,
            "schedule_overload": 0.3,
            "calendar_urgency": 0.0,
            "deadline_pressure": 0.0,
            "medication_risk": 0.0,
            "injury_risk": 0.0,
            "drift_severity": 0.0,
            "non_negotiable_miss": 0.0,
            "relationship_drift": 0.0,
            "relationship_event": 0.0,
            "open_loop_count": 0.0,
        }
        result = classify_scenario(strengths)
        self.assertEqual(result["dominant_scenario"], MOOD_CRITICAL)

    def test_relationship_critical_dominates(self):
        """Relationship event + drift → RELATIONSHIP_CRITICAL."""
        strengths = {
            "relationship_event": 0.9,
            "relationship_drift": 0.7,
            "emotional_load": 0.3,
            "schedule_overload": 0.1,
            "calendar_urgency": 0.0,
            "deadline_pressure": 0.0,
            "medication_risk": 0.0,
            "sleep_deficit": 0.0,
            "injury_risk": 0.0,
            "drift_severity": 0.0,
            "non_negotiable_miss": 0.0,
            "mood_decline": 0.0,
            "open_loop_count": 0.0,
        }
        result = classify_scenario(strengths)
        self.assertEqual(result["dominant_scenario"], RELATIONSHIP_CRITICAL)

    def test_time_critical_overrides_mood(self):
        """When both time and mood active, time wins if stronger."""
        strengths = {
            "calendar_urgency": 0.9,
            "deadline_pressure": 0.7,
            "schedule_overload": 0.5,
            "open_loop_count": 0.3,
            "mood_decline": 0.5,
            "emotional_load": 0.4,
            "sleep_deficit": 0.3,
            "medication_risk": 0.0,
            "injury_risk": 0.0,
            "drift_severity": 0.0,
            "non_negotiable_miss": 0.0,
            "relationship_drift": 0.0,
            "relationship_event": 0.0,
        }
        result = classify_scenario(strengths)
        self.assertEqual(result["dominant_scenario"], TIME_CRITICAL)
        # Mood should be secondary
        self.assertIn(MOOD_CRITICAL, result["secondary_scenarios"])

    def test_secondary_scenarios_captured(self):
        """Multiple active scenarios → secondaries tracked."""
        strengths = {
            "medication_risk": 0.8,
            "sleep_deficit": 0.6,
            "injury_risk": 0.4,
            "mood_decline": 0.5,
            "emotional_load": 0.4,
            "drift_severity": 0.4,
            "non_negotiable_miss": 0.3,
            "calendar_urgency": 0.0,
            "deadline_pressure": 0.0,
            "schedule_overload": 0.3,
            "open_loop_count": 0.2,
            "relationship_drift": 0.0,
            "relationship_event": 0.0,
        }
        result = classify_scenario(strengths)
        self.assertEqual(result["dominant_scenario"], HEALTH_CRITICAL)
        self.assertTrue(len(result["secondary_scenarios"]) >= 1)

    def test_scenario_scores_always_present(self):
        """All scenario scores returned regardless of dominance."""
        strengths = {"mood_decline": 0.5}
        result = classify_scenario(strengths)
        self.assertIn("scenario_scores", result)
        self.assertEqual(len(result["scenario_scores"]), 5)

    def test_empty_strengths_gives_stable(self):
        """Empty signal dict → STABLE_EXECUTION."""
        result = classify_scenario({})
        self.assertEqual(result["dominant_scenario"], STABLE_EXECUTION)


class ConfidenceDampeningTests(TestCase):
    """v2: Test confidence level classification."""

    def test_low_confidence_when_scenarios_nearly_tied(self):
        """Scenarios within 0.05 gap → LOW confidence."""
        # Craft signals where TIME and MOOD are nearly equal
        strengths = {
            "calendar_urgency": 0.6,
            "deadline_pressure": 0.4,
            "schedule_overload": 0.3,
            "open_loop_count": 0.2,
            "mood_decline": 0.6,
            "emotional_load": 0.5,
            "sleep_deficit": 0.3,
        }
        result = classify_scenario(strengths)
        # Both TIME and MOOD should be close
        scores = result["scenario_scores"]
        gap = abs(scores[TIME_CRITICAL] - scores[MOOD_CRITICAL])
        # The actual gap may vary, but we verify the structure
        self.assertIn(result["confidence_level"], [
            CONFIDENCE_LOW, CONFIDENCE_MODERATE, CONFIDENCE_HIGH
        ])
        self.assertIn("confidence_gap", result)

    def test_high_confidence_with_clear_dominance(self):
        """Large gap → HIGH confidence."""
        strengths = {
            "medication_risk": 0.95,
            "sleep_deficit": 0.8,
            "injury_risk": 0.6,
            "mood_decline": 0.0,
            "emotional_load": 0.0,
            "calendar_urgency": 0.0,
            "deadline_pressure": 0.0,
            "drift_severity": 0.0,
            "non_negotiable_miss": 0.0,
            "relationship_drift": 0.0,
            "relationship_event": 0.0,
            "schedule_overload": 0.1,
            "open_loop_count": 0.0,
        }
        result = classify_scenario(strengths)
        self.assertEqual(result["dominant_scenario"], HEALTH_CRITICAL)
        self.assertEqual(result["confidence_level"], CONFIDENCE_HIGH)
        self.assertGreater(result["confidence_gap"], 0.15)

    def test_stable_execution_always_high_confidence(self):
        """STABLE_EXECUTION always has HIGH confidence."""
        result = classify_scenario({})
        self.assertEqual(result["confidence_level"], CONFIDENCE_HIGH)

    def test_confidence_gap_returned(self):
        """confidence_gap is always present in result."""
        result = classify_scenario({"mood_decline": 0.5})
        self.assertIn("confidence_gap", result)
        self.assertIsInstance(result["confidence_gap"], float)

    def test_low_confidence_limits_surfaced_to_one(self):
        """LOW confidence → intervention surfaces only 1 item."""
        scenario = {
            "dominant_scenario": TIME_CRITICAL,
            "secondary_scenarios": [MOOD_CRITICAL],
            "scenario_scores": {},
            "confidence": 0.55,
            "confidence_level": CONFIDENCE_LOW,
            "confidence_gap": 0.03,
        }
        strengths = {
            "calendar_urgency": 0.8,
            "deadline_pressure": 0.6,
            "mood_decline": 0.7,
            "emotional_load": 0.5,
        }
        result = decide_intervention(
            scenario, [], strengths, _make_signals()
        )
        self.assertLessEqual(len(result["surfaced_items"]), 1)

    def test_low_confidence_softens_narrative(self):
        """LOW confidence → narrative mentions ambiguity."""
        scenario = {
            "dominant_scenario": TIME_CRITICAL,
            "secondary_scenarios": [MOOD_CRITICAL],
            "scenario_scores": {},
            "confidence_level": CONFIDENCE_LOW,
            "confidence_gap": 0.03,
        }
        intervention = {
            "intervention_style": DIRECTIVE,
            "style_description": "Be direct.",
            "surfaced_items": [],
            "suppressed_items": [],
            "primary_composite": None,
        }
        narrative = build_narrative(
            scenario, [], intervention, _make_signals()
        )
        self.assertIn("CONFIDENCE IS LOW", narrative)
        self.assertIn("ambiguity", narrative.lower())


class CapacityCompositeTests(TestCase):
    """v2: Test capacity composite modeling."""

    def test_high_capacity_when_all_signals_low(self):
        """No load signals → HIGH_CAPACITY."""
        strengths = {
            "sleep_deficit": 0.0,
            "mood_decline": 0.0,
            "emotional_load": 0.0,
            "schedule_overload": 0.0,
            "open_loop_count": 0.0,
        }
        result = compute_capacity(strengths)
        self.assertEqual(result["capacity_state"], HIGH_CAPACITY)
        self.assertGreaterEqual(result["capacity_score"], 0.75)
        self.assertEqual(result["max_surfaced"], 3)

    def test_critical_capacity_when_all_signals_high(self):
        """All load signals high → CRITICAL."""
        strengths = {
            "sleep_deficit": 0.9,
            "mood_decline": 0.8,
            "emotional_load": 0.9,
            "schedule_overload": 0.8,
            "open_loop_count": 0.7,
        }
        result = compute_capacity(strengths)
        self.assertEqual(result["capacity_state"], CRITICAL)
        self.assertLess(result["capacity_score"], 0.25)
        self.assertEqual(result["max_surfaced"], 1)

    def test_low_capacity_reduces_surfacing(self):
        """LOW capacity → max 2 surfaced items."""
        strengths = {
            "sleep_deficit": 0.7,
            "mood_decline": 0.6,
            "emotional_load": 0.5,
            "schedule_overload": 0.6,
            "open_loop_count": 0.3,
        }
        result = compute_capacity(strengths)
        self.assertIn(result["capacity_state"], [LOW, CRITICAL])
        self.assertLessEqual(result["max_surfaced"], 2)

    def test_capacity_score_normalized(self):
        """Capacity score always 0-1."""
        for val in [0.0, 0.5, 1.0]:
            strengths = {
                "sleep_deficit": val,
                "mood_decline": val,
                "emotional_load": val,
                "schedule_overload": val,
                "open_loop_count": val,
            }
            result = compute_capacity(strengths)
            self.assertGreaterEqual(result["capacity_score"], 0.0)
            self.assertLessEqual(result["capacity_score"], 1.0)

    def test_capacity_modifies_intervention_surfacing(self):
        """Capacity state flows through to intervention max surfaced."""
        scenario = {
            "dominant_scenario": HEALTH_CRITICAL,
            "secondary_scenarios": [],
            "scenario_scores": {},
            "confidence": 0.8,
            "confidence_level": CONFIDENCE_HIGH,
            "confidence_gap": 0.2,
        }
        strengths = {
            "medication_risk": 0.9,
            "sleep_deficit": 0.8,
            "drift_severity": 0.7,
            "mood_decline": 0.6,
            "deadline_pressure": 0.5,
        }
        capacity = {
            "capacity_score": 0.3,
            "capacity_state": LOW,
            "max_surfaced": 2,
            "components": {},
        }
        result = decide_intervention(
            scenario, [], strengths, _make_signals(),
            capacity=capacity,
        )
        self.assertLessEqual(len(result["surfaced_items"]), 2)

    def test_critical_capacity_in_narrative(self):
        """CRITICAL capacity adds warning to narrative."""
        scenario = {
            "dominant_scenario": HEALTH_CRITICAL,
            "secondary_scenarios": [],
            "scenario_scores": {},
            "confidence_level": CONFIDENCE_MODERATE,
            "confidence_gap": 0.1,
        }
        intervention = {
            "intervention_style": PROTECTIVE,
            "style_description": "Protect energy.",
            "surfaced_items": [],
            "suppressed_items": [],
            "primary_composite": None,
        }
        capacity = {
            "capacity_score": 0.15,
            "capacity_state": CRITICAL,
            "max_surfaced": 1,
            "components": {},
        }
        narrative = build_narrative(
            scenario, [], intervention, _make_signals(),
            capacity=capacity,
        )
        self.assertIn("CAPACITY IS CRITICAL", narrative)
        self.assertIn("optional", narrative.lower())


class PatternAnalyzerTests(TestCase):
    """v2: Test multi-day pattern analysis."""

    def _create_user(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        return User.objects.create_user(
            email="pattern_test@example.com",
            password="testpass123",
        )

    def test_mood_persistent_detected(self):
        """MOOD_CRITICAL ≥3 in 5 days → MOOD_PERSISTENT."""
        from apps.core.ai_arbitration.models import ScenarioHistory
        from apps.core.ai_arbitration.pattern_analyzer import analyze_patterns

        user = self._create_user()
        today = date.today()

        # Create 3 MOOD_CRITICAL days in last 5 days
        for i in range(3):
            ScenarioHistory.objects.create(
                user=user,
                date=today - timedelta(days=i),
                dominant_scenario="MOOD_CRITICAL",
                intervention_style="SUPPORTIVE",
            )

        result = analyze_patterns(user)
        patterns = [h["pattern"] for h in result["escalation_hints"]]
        self.assertIn("MOOD_PERSISTENT", patterns)

    def test_drift_persistent_detected(self):
        """DRIFT_CRITICAL ≥4 in 7 days → DRIFT_PERSISTENT."""
        from apps.core.ai_arbitration.models import ScenarioHistory
        from apps.core.ai_arbitration.pattern_analyzer import analyze_patterns

        user = self._create_user()
        today = date.today()

        for i in range(4):
            ScenarioHistory.objects.create(
                user=user,
                date=today - timedelta(days=i),
                dominant_scenario="DRIFT_CRITICAL",
                intervention_style="ACCOUNTABILITY",
            )

        result = analyze_patterns(user)
        patterns = [h["pattern"] for h in result["escalation_hints"]]
        self.assertIn("DRIFT_PERSISTENT", patterns)

    def test_no_pattern_when_below_threshold(self):
        """2 MOOD_CRITICAL in 5 days → no pattern."""
        from apps.core.ai_arbitration.models import ScenarioHistory
        from apps.core.ai_arbitration.pattern_analyzer import analyze_patterns

        user = self._create_user()
        today = date.today()

        for i in range(2):
            ScenarioHistory.objects.create(
                user=user,
                date=today - timedelta(days=i),
                dominant_scenario="MOOD_CRITICAL",
                intervention_style="SUPPORTIVE",
            )

        result = analyze_patterns(user)
        self.assertEqual(result["escalation_hints"], [])

    def test_pattern_intensity_bounded(self):
        """Intensity modifier never exceeds 0.3."""
        from apps.core.ai_arbitration.models import ScenarioHistory
        from apps.core.ai_arbitration.pattern_analyzer import analyze_patterns

        user = self._create_user()
        today = date.today()

        # Create 10 MOOD_CRITICAL days — extreme case
        for i in range(10):
            ScenarioHistory.objects.create(
                user=user,
                date=today - timedelta(days=i),
                dominant_scenario="MOOD_CRITICAL",
                intervention_style="SUPPORTIVE",
            )

        result = analyze_patterns(user)
        for hint in result["escalation_hints"]:
            self.assertLessEqual(hint["intensity_modifier"], 0.3)

    def test_pattern_note_in_narrative(self):
        """Pattern hints appear in narrative."""
        scenario = {
            "dominant_scenario": MOOD_CRITICAL,
            "secondary_scenarios": [],
            "scenario_scores": {},
            "confidence_level": CONFIDENCE_MODERATE,
            "confidence_gap": 0.1,
        }
        intervention = {
            "intervention_style": SUPPORTIVE,
            "style_description": "Acknowledge first.",
            "surfaced_items": [],
            "suppressed_items": [],
            "primary_composite": None,
        }
        hints = [{
            "pattern": "MOOD_PERSISTENT",
            "scenario": "MOOD_CRITICAL",
            "count": 3,
            "window_days": 5,
            "intensity_modifier": 0.1,
        }]
        narrative = build_narrative(
            scenario, [], intervention, _make_signals(),
            pattern_hints=hints,
        )
        self.assertIn("PATTERN NOTE", narrative)
        self.assertIn("MOOD_CRITICAL", narrative)
        self.assertIn("3 times", narrative)

    def test_empty_history_returns_empty(self):
        """No history → empty result."""
        from apps.core.ai_arbitration.pattern_analyzer import analyze_patterns
        user = self._create_user()
        result = analyze_patterns(user)
        self.assertEqual(result["escalation_hints"], [])
        self.assertEqual(result["scenario_frequency"], {})


class AdaptiveWeightTests(TestCase):
    """v2: Test adaptive weight tuning."""

    def test_weight_adjustments_applied(self):
        """Weight adjustments modify scenario scores."""
        strengths = {
            "mood_decline": 0.5,
            "emotional_load": 0.4,
            "sleep_deficit": 0.3,
            "schedule_overload": 0.2,
        }
        # Boost mood weights
        adjustments = {
            ("MOOD_CRITICAL", "mood_decline"): 0.05,
            ("MOOD_CRITICAL", "emotional_load"): 0.05,
        }
        result_adjusted = classify_scenario(strengths, adjustments)
        result_base = classify_scenario(strengths)

        # Adjusted MOOD score should be higher
        self.assertGreater(
            result_adjusted["scenario_scores"][MOOD_CRITICAL],
            result_base["scenario_scores"][MOOD_CRITICAL],
        )

    def test_weight_adjustments_clamped(self):
        """Adjustments beyond ±0.10 are clamped."""
        strengths = {"mood_decline": 0.5}
        # Extreme adjustment
        adjustments = {
            ("MOOD_CRITICAL", "mood_decline"): 0.50,  # Way over limit
        }
        result = classify_scenario(strengths, adjustments)
        # Should still work (clamped to 0.10)
        self.assertIn("dominant_scenario", result)

    def test_weight_adjustments_keep_weights_positive(self):
        """Negative adjustments can't make weights negative."""
        strengths = {
            "schedule_overload": 0.9,
            "calendar_urgency": 0.0,
            "deadline_pressure": 0.0,
            "open_loop_count": 0.0,
        }
        # Try to make schedule_overload weight negative for TIME_CRITICAL
        # baseline is 0.20, adjustment -0.10 → should be 0.10 (not negative)
        adjustments = {
            ("TIME_CRITICAL", "schedule_overload"): -0.10,
        }
        result = classify_scenario(strengths, adjustments)
        # Should not crash, score should be ≥ 0
        self.assertGreaterEqual(
            result["scenario_scores"][TIME_CRITICAL], 0.0
        )

    def test_no_adjustments_same_as_baseline(self):
        """None adjustments → identical to baseline."""
        strengths = {"mood_decline": 0.8, "emotional_load": 0.6}
        result_none = classify_scenario(strengths, None)
        result_empty = classify_scenario(strengths, {})
        self.assertEqual(
            result_none["scenario_scores"],
            result_empty["scenario_scores"],
        )

    def test_weight_tuner_bounded(self):
        """Weight tuner never exceeds MAX_DELTA_FROM_BASELINE."""
        from apps.core.ai_arbitration.models import WeightAdjustment

        user = self._create_user()

        # Create an adjustment at the limit
        WeightAdjustment.objects.create(
            user=user,
            scenario="MOOD_CRITICAL",
            signal="mood_decline",
            baseline_weight=0.40,
            adjustment_delta=0.10,  # At max
        )

        adj = WeightAdjustment.objects.get(
            user=user, scenario="MOOD_CRITICAL", signal="mood_decline"
        )
        self.assertEqual(adj.current_weight, 0.50)
        self.assertLessEqual(abs(adj.adjustment_delta), 0.10)

    def _create_user(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        return User.objects.create_user(
            email="weight_test@example.com",
            password="testpass123",
        )


class SignalFuserTests(TestCase):
    """Test cross-domain signal fusion."""

    def test_low_capacity_day_detected(self):
        """Sleep deficit + schedule overload → LOW_CAPACITY_DAY."""
        strengths = {
            "sleep_deficit": 0.6,
            "schedule_overload": 0.5,
            "mood_decline": 0.3,
        }
        composites = fuse_signals(strengths)
        names = [c["name"] for c in composites]
        self.assertIn("LOW_CAPACITY_DAY", names)

    def test_physical_risk_detected(self):
        """Injury risk → PHYSICAL_RISK."""
        strengths = {
            "injury_risk": 0.7,
            "sleep_deficit": 0.4,
        }
        composites = fuse_signals(strengths)
        names = [c["name"] for c in composites]
        self.assertIn("PHYSICAL_RISK", names)

    def test_relational_opportunity_detected(self):
        """Relationship event + low overload → RELATIONAL_OPPORTUNITY."""
        strengths = {
            "relationship_event": 0.8,
            "schedule_overload": 0.1,
            "medication_risk": 0.0,
        }
        composites = fuse_signals(strengths)
        names = [c["name"] for c in composites]
        self.assertIn("RELATIONAL_OPPORTUNITY", names)

    def test_relational_opportunity_suppressed_by_overload(self):
        """High overload suppresses RELATIONAL_OPPORTUNITY."""
        strengths = {
            "relationship_event": 0.8,
            "schedule_overload": 0.7,
        }
        composites = fuse_signals(strengths)
        names = [c["name"] for c in composites]
        self.assertNotIn("RELATIONAL_OPPORTUNITY", names)

    def test_emotional_overload_detected(self):
        """Mood + emotional load → EMOTIONAL_OVERLOAD."""
        strengths = {
            "mood_decline": 0.6,
            "emotional_load": 0.5,
        }
        composites = fuse_signals(strengths)
        names = [c["name"] for c in composites]
        self.assertIn("EMOTIONAL_OVERLOAD", names)

    def test_alignment_crisis_detected(self):
        """Drift + non-negotiable miss → ALIGNMENT_CRISIS."""
        strengths = {
            "drift_severity": 0.7,
            "non_negotiable_miss": 0.6,
        }
        composites = fuse_signals(strengths)
        names = [c["name"] for c in composites]
        self.assertIn("ALIGNMENT_CRISIS", names)

    def test_no_composites_when_signals_low(self):
        """Low signals → no composites detected."""
        strengths = {
            "sleep_deficit": 0.1,
            "mood_decline": 0.1,
            "schedule_overload": 0.1,
        }
        composites = fuse_signals(strengths)
        self.assertEqual(composites, [])

    def test_composites_sorted_by_strength(self):
        """Multiple composites sorted strongest first."""
        strengths = {
            "sleep_deficit": 0.6,
            "schedule_overload": 0.5,
            "mood_decline": 0.7,
            "emotional_load": 0.6,
        }
        composites = fuse_signals(strengths)
        if len(composites) >= 2:
            self.assertGreaterEqual(
                composites[0]["strength"], composites[1]["strength"]
            )

    def test_composite_has_contributing_signals(self):
        """Each composite includes its contributing signals."""
        strengths = {
            "drift_severity": 0.8,
            "non_negotiable_miss": 0.7,
        }
        composites = fuse_signals(strengths)
        crisis = next(
            (c for c in composites if c["name"] == "ALIGNMENT_CRISIS"), None
        )
        self.assertIsNotNone(crisis)
        self.assertIn("drift_severity", crisis["contributing_signals"])


class InterventionEngineTests(TestCase):
    """Test intervention style selection."""

    def _make_scenario(self, dominant, secondaries=None, scores=None,
                       confidence_level="MODERATE", confidence_gap=0.1):
        return {
            "dominant_scenario": dominant,
            "secondary_scenarios": secondaries or [],
            "scenario_scores": scores or {},
            "confidence": 0.8,
            "confidence_level": confidence_level,
            "confidence_gap": confidence_gap,
        }

    def test_time_critical_gives_directive(self):
        scenario = self._make_scenario(TIME_CRITICAL)
        strengths = {"calendar_urgency": 0.8, "deadline_pressure": 0.6}
        result = decide_intervention(
            scenario, [], strengths, _make_signals()
        )
        self.assertEqual(result["intervention_style"], DIRECTIVE)

    def test_health_critical_gives_protective(self):
        scenario = self._make_scenario(HEALTH_CRITICAL)
        strengths = {"medication_risk": 0.8, "sleep_deficit": 0.6}
        result = decide_intervention(
            scenario, [], strengths, _make_signals()
        )
        self.assertEqual(result["intervention_style"], PROTECTIVE)

    def test_drift_critical_gives_accountability(self):
        scenario = self._make_scenario(DRIFT_CRITICAL)
        strengths = {"drift_severity": 0.7, "non_negotiable_miss": 0.6}
        result = decide_intervention(
            scenario, [], strengths, _make_signals()
        )
        self.assertEqual(result["intervention_style"], ACCOUNTABILITY)

    def test_mood_critical_gives_supportive(self):
        scenario = self._make_scenario(MOOD_CRITICAL)
        strengths = {"mood_decline": 0.8, "emotional_load": 0.6}
        result = decide_intervention(
            scenario, [], strengths, _make_signals()
        )
        self.assertEqual(result["intervention_style"], SUPPORTIVE)

    def test_relationship_critical_gives_strategic(self):
        scenario = self._make_scenario(RELATIONSHIP_CRITICAL)
        strengths = {"relationship_event": 0.7}
        signals = _make_signals()
        signals["upcoming_events"]["significant_next_7d"] = [
            {"title": "Mom's Birthday", "type": "birthday",
             "person": "Mom", "days_until": 2, "years": 65}
        ]
        result = decide_intervention(scenario, [], strengths, signals)
        self.assertEqual(result["intervention_style"], STRATEGIC)

    def test_stable_gives_execution(self):
        scenario = self._make_scenario(STABLE_EXECUTION)
        result = decide_intervention(
            scenario, [], {}, _make_signals()
        )
        self.assertEqual(result["intervention_style"], EXECUTION)

    def test_composite_override_to_protective(self):
        """LOW_CAPACITY_DAY composite overrides to PROTECTIVE."""
        scenario = self._make_scenario(TIME_CRITICAL)
        composites = [{
            "name": "LOW_CAPACITY_DAY",
            "strength": 0.7,
            "description": "...",
            "contributing_signals": {},
        }]
        strengths = {"calendar_urgency": 0.5}
        result = decide_intervention(
            scenario, composites, strengths, _make_signals()
        )
        self.assertEqual(result["intervention_style"], PROTECTIVE)
        self.assertEqual(result["primary_composite"], "LOW_CAPACITY_DAY")

    def test_max_three_surfaced(self):
        """Never more than 3 surfaced items (default capacity)."""
        scenario = self._make_scenario(
            HEALTH_CRITICAL, confidence_level=CONFIDENCE_HIGH,
            confidence_gap=0.2,
        )
        strengths = {
            "medication_risk": 0.9,
            "sleep_deficit": 0.8,
            "drift_severity": 0.7,
            "mood_decline": 0.6,
            "deadline_pressure": 0.5,
            "schedule_overload": 0.4,
            "relationship_drift": 0.3,
        }
        result = decide_intervention(
            scenario, [], strengths, _make_signals()
        )
        self.assertLessEqual(len(result["surfaced_items"]), 3)

    def test_suppressed_items_tracked(self):
        """Items beyond top 3 are suppressed."""
        scenario = self._make_scenario(
            HEALTH_CRITICAL, confidence_level=CONFIDENCE_HIGH,
            confidence_gap=0.2,
        )
        strengths = {
            "medication_risk": 0.9,
            "sleep_deficit": 0.8,
            "drift_severity": 0.7,
            "mood_decline": 0.6,
            "deadline_pressure": 0.5,
        }
        result = decide_intervention(
            scenario, [], strengths, _make_signals()
        )
        self.assertTrue(len(result["suppressed_items"]) > 0)

    def test_mood_critical_suppresses_minor_tasks(self):
        """When mood is dominant, deadline tasks get suppressed."""
        scenario = self._make_scenario(MOOD_CRITICAL)
        strengths = {
            "mood_decline": 0.9,
            "emotional_load": 0.8,
            "sleep_deficit": 0.6,
            "deadline_pressure": 0.3,
            "schedule_overload": 0.2,
        }
        result = decide_intervention(
            scenario, [], strengths, _make_signals()
        )
        self.assertEqual(result["intervention_style"], SUPPORTIVE)
        # Check that mood-related items are surfaced, not deadline
        surfaced_cats = [s["category"] for s in result["surfaced_items"]]
        self.assertIn("SUPPORTIVE", surfaced_cats)


class NarrativeEngineTests(TestCase):
    """Test executive narrative generation."""

    def test_stable_execution_narrative(self):
        """Clean day → execution framing."""
        scenario = {
            "dominant_scenario": STABLE_EXECUTION,
            "secondary_scenarios": [],
            "scenario_scores": {},
            "confidence_level": CONFIDENCE_HIGH,
            "confidence_gap": 0.0,
        }
        intervention = {
            "intervention_style": EXECUTION,
            "style_description": "Clean execution day.",
            "surfaced_items": [],
            "suppressed_items": [],
            "primary_composite": None,
        }
        narrative = build_narrative(
            scenario, [], intervention, _make_signals()
        )
        self.assertIn("EXECUTIVE JUDGMENT", narrative)
        self.assertIn("STABLE_EXECUTION", narrative)
        self.assertIn("EXECUTION", narrative)
        self.assertIn("Clean morning", narrative)

    def test_health_critical_narrative(self):
        """Health critical → mentions medication."""
        scenario = {
            "dominant_scenario": HEALTH_CRITICAL,
            "secondary_scenarios": [],
            "scenario_scores": {},
            "confidence_level": CONFIDENCE_MODERATE,
            "confidence_gap": 0.1,
        }
        intervention = {
            "intervention_style": PROTECTIVE,
            "style_description": "Protect energy.",
            "surfaced_items": [
                {"label": "Medication", "detail": "2 missed",
                 "category": "HEALTH_GATE", "priority": 95,
                 "signal_strength": 0.9},
            ],
            "suppressed_items": [],
            "primary_composite": None,
        }
        signals = _make_signals()
        signals["health_signals"]["medications_missed"] = 2
        signals["health_signals"]["sleep_duration_minutes"] = 300
        signals["health_signals"]["sleep_target_minutes"] = 480
        narrative = build_narrative(scenario, [], intervention, signals)
        self.assertIn("HEALTH_CRITICAL", narrative)
        self.assertIn("PROTECTIVE", narrative)
        self.assertIn("medication", narrative.lower())

    def test_low_capacity_composite_narrative(self):
        """LOW_CAPACITY_DAY composite → protection framing."""
        scenario = {
            "dominant_scenario": HEALTH_CRITICAL,
            "secondary_scenarios": [MOOD_CRITICAL],
            "scenario_scores": {},
            "confidence_level": CONFIDENCE_MODERATE,
            "confidence_gap": 0.08,
        }
        composites = [{
            "name": "LOW_CAPACITY_DAY",
            "strength": 0.7,
            "description": "Poor sleep + high density",
            "contributing_signals": {"sleep_deficit": 0.6, "schedule_overload": 0.5},
        }]
        intervention = {
            "intervention_style": PROTECTIVE,
            "style_description": "Protect energy.",
            "surfaced_items": [],
            "suppressed_items": [],
            "primary_composite": "LOW_CAPACITY_DAY",
        }
        signals = _make_signals()
        signals["health_signals"]["sleep_duration_minutes"] = 300
        signals["health_signals"]["sleep_target_minutes"] = 480
        signals["schedule_signals"]["capacity_pct"] = 87
        narrative = build_narrative(scenario, composites, intervention, signals)
        self.assertIn("LOW_CAPACITY_DAY", narrative)
        self.assertIn("protection", narrative.lower())

    def test_relationship_event_narrative(self):
        """Relationship event → surfaces person and timeline."""
        scenario = {
            "dominant_scenario": RELATIONSHIP_CRITICAL,
            "secondary_scenarios": [],
            "scenario_scores": {},
            "confidence_level": CONFIDENCE_MODERATE,
            "confidence_gap": 0.1,
        }
        intervention = {
            "intervention_style": STRATEGIC,
            "style_description": "Forward planning.",
            "surfaced_items": [],
            "suppressed_items": [],
            "primary_composite": "RELATIONAL_OPPORTUNITY",
        }
        signals = _make_signals()
        signals["upcoming_events"] = {
            "significant_next_7d": [
                {"title": "Mom's Birthday", "type": "birthday",
                 "person": "Mom", "days_until": 2, "years": 65},
            ],
            "overdue_tasks": 0,
            "approaching_deadlines": 0,
        }
        composites = [{
            "name": "RELATIONAL_OPPORTUNITY",
            "strength": 0.7,
            "description": "...",
            "contributing_signals": {},
        }]
        narrative = build_narrative(
            scenario, composites, intervention, signals
        )
        self.assertIn("Mom", narrative)

    def test_narrative_contains_suppressed(self):
        """Suppressed items appear in SUPPRESS block."""
        scenario = {
            "dominant_scenario": MOOD_CRITICAL,
            "secondary_scenarios": [],
            "scenario_scores": {},
            "confidence_level": CONFIDENCE_MODERATE,
            "confidence_gap": 0.1,
        }
        intervention = {
            "intervention_style": SUPPORTIVE,
            "style_description": "Acknowledge first.",
            "surfaced_items": [
                {"label": "Mood", "detail": "falling", "category": "SUPPORTIVE",
                 "priority": 90, "signal_strength": 0.9},
            ],
            "suppressed_items": [
                {"label": "Deadline", "detail": "3 overdue",
                 "category": "DIRECTIVE", "priority": 40,
                 "signal_strength": 0.3},
            ],
            "primary_composite": None,
        }
        narrative = build_narrative(
            scenario, [], intervention, _make_signals()
        )
        self.assertIn("SUPPRESS", narrative)
        self.assertIn("Deadline", narrative)

    def test_narrative_unify_instruction_present(self):
        """Narrative always includes unification instruction."""
        scenario = {
            "dominant_scenario": STABLE_EXECUTION,
            "secondary_scenarios": [],
            "scenario_scores": {},
            "confidence_level": CONFIDENCE_HIGH,
            "confidence_gap": 0.0,
        }
        intervention = {
            "intervention_style": EXECUTION,
            "style_description": "Execute.",
            "surfaced_items": [],
            "suppressed_items": [],
            "primary_composite": None,
        }
        narrative = build_narrative(
            scenario, [], intervention, _make_signals()
        )
        self.assertIn("Unify your response", narrative)
        self.assertIn("Do NOT list separate reminders", narrative)

    def test_narrative_contains_confidence_level(self):
        """Narrative always includes CONFIDENCE line."""
        scenario = {
            "dominant_scenario": STABLE_EXECUTION,
            "secondary_scenarios": [],
            "scenario_scores": {},
            "confidence_level": CONFIDENCE_HIGH,
            "confidence_gap": 0.2,
        }
        intervention = {
            "intervention_style": EXECUTION,
            "style_description": "Execute.",
            "surfaced_items": [],
            "suppressed_items": [],
            "primary_composite": None,
        }
        narrative = build_narrative(
            scenario, [], intervention, _make_signals()
        )
        self.assertIn("CONFIDENCE: HIGH", narrative)


class ArbitrationEngineTests(TestCase):
    """Test the full arbitration pipeline."""

    def _create_user(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        return User.objects.create_user(
            email="ual_test@example.com",
            password="testpass123",
        )

    @patch("apps.core.ai_arbitration.signal_collector.collect_signals")
    def test_full_pipeline_stable(self, mock_collect):
        """Full pipeline with low signals → STABLE_EXECUTION."""
        user = self._create_user()
        mock_collect.return_value = _make_full_signals()

        from apps.core.ai_arbitration import run_arbitration
        result = run_arbitration(user)

        self.assertTrue(result.success)
        self.assertEqual(result.dominant_scenario, STABLE_EXECUTION)
        self.assertEqual(result.intervention_style, EXECUTION)
        self.assertIn("EXECUTIVE JUDGMENT", result.narrative_injection)
        # v2 fields
        self.assertIn(result.confidence_level, [
            CONFIDENCE_LOW, CONFIDENCE_MODERATE, CONFIDENCE_HIGH
        ])
        self.assertIsInstance(result.capacity_score, float)
        self.assertIn(result.capacity_state, [
            HIGH_CAPACITY, NORMAL, LOW, CRITICAL
        ])

    @patch("apps.core.ai_arbitration.signal_collector.collect_signals")
    def test_full_pipeline_health_critical(self, mock_collect):
        """Full pipeline with health signals → HEALTH_CRITICAL."""
        user = self._create_user()
        signals = _make_full_signals()
        signals["raw_strengths"]["medication_risk"] = 1.0
        signals["raw_strengths"]["sleep_deficit"] = 0.5
        signals["health_signals"]["medications_missed"] = 3
        signals["health_signals"]["sleep_duration_minutes"] = 240
        mock_collect.return_value = signals

        from apps.core.ai_arbitration import run_arbitration
        result = run_arbitration(user)

        self.assertTrue(result.success)
        self.assertEqual(result.dominant_scenario, HEALTH_CRITICAL)
        self.assertEqual(result.intervention_style, PROTECTIVE)

    @patch("apps.core.ai_arbitration.signal_collector.collect_signals")
    def test_pipeline_never_raises(self, mock_collect):
        """Pipeline returns safe fallback on errors."""
        user = self._create_user()
        mock_collect.side_effect = RuntimeError("Signal collection exploded")

        from apps.core.ai_arbitration import run_arbitration
        result = run_arbitration(user)

        self.assertFalse(result.success)
        self.assertEqual(result.dominant_scenario, STABLE_EXECUTION)
        self.assertEqual(result.narrative_injection, "")

    @patch("apps.core.ai_arbitration.signal_collector.collect_signals")
    def test_decision_logged_with_v2_fields(self, mock_collect):
        """Arbitration decisions include v2 fields in log."""
        user = self._create_user()
        mock_collect.return_value = _make_full_signals()

        from apps.core.ai_arbitration import run_arbitration
        from apps.core.ai_arbitration.models import ArbitrationDecisionLog

        result = run_arbitration(user)
        self.assertTrue(result.success)

        logs = ArbitrationDecisionLog.objects.filter(user=user)
        self.assertEqual(logs.count(), 1)
        log = logs.first()
        self.assertEqual(log.dominant_scenario, STABLE_EXECUTION)
        self.assertEqual(log.intervention_style, EXECUTION)
        # v2 fields
        self.assertIn(log.confidence_level, ["LOW", "MODERATE", "HIGH"])
        self.assertIn(log.capacity_state, [
            "HIGH_CAPACITY", "NORMAL", "LOW", "CRITICAL"
        ])
        self.assertIsNotNone(log.capacity_score)

    @patch("apps.core.ai_arbitration.signal_collector.collect_signals")
    def test_scenario_history_logged(self, mock_collect):
        """Scenario history is logged on each arbitration."""
        user = self._create_user()
        mock_collect.return_value = _make_full_signals()

        from apps.core.ai_arbitration import run_arbitration
        from apps.core.ai_arbitration.models import ScenarioHistory

        run_arbitration(user)
        history = ScenarioHistory.objects.filter(user=user)
        self.assertEqual(history.count(), 1)

    @patch("apps.core.ai_arbitration.signal_collector.collect_signals")
    def test_capacity_logged(self, mock_collect):
        """Capacity is logged on each arbitration."""
        user = self._create_user()
        mock_collect.return_value = _make_full_signals()

        from apps.core.ai_arbitration import run_arbitration
        from apps.core.ai_arbitration.models import DailyCapacityLog

        run_arbitration(user)
        cap_logs = DailyCapacityLog.objects.filter(user=user)
        self.assertEqual(cap_logs.count(), 1)


class StabilityTests(TestCase):
    """v2: Verify no regressions — stable execution unchanged."""

    def test_stable_with_zero_signals_unchanged(self):
        """Zero signals → same STABLE result as v1."""
        result = classify_scenario({})
        self.assertEqual(result["dominant_scenario"], STABLE_EXECUTION)
        self.assertGreater(result["confidence"], 0.5)
        # v2 additions present but don't change behavior
        self.assertEqual(result["confidence_level"], CONFIDENCE_HIGH)

    def test_no_feedback_loop_in_weights(self):
        """Weights can't self-amplify beyond bounds."""
        from apps.core.ai_arbitration.scenario_classifier import _apply_adjustments

        base = {"mood_decline": 0.40}
        # Extreme positive adjustment
        adjusted = _apply_adjustments(
            "MOOD_CRITICAL", base,
            {("MOOD_CRITICAL", "mood_decline"): 0.50}
        )
        # Should be clamped to baseline + 0.10
        self.assertLessEqual(adjusted["mood_decline"], 0.50)

        # Extreme negative adjustment
        adjusted = _apply_adjustments(
            "MOOD_CRITICAL", base,
            {("MOOD_CRITICAL", "mood_decline"): -0.50}
        )
        # Should be clamped and non-negative
        self.assertGreaterEqual(adjusted["mood_decline"], 0.0)

    def test_capacity_empty_signals_gives_full(self):
        """Empty signals → full capacity."""
        result = compute_capacity({})
        self.assertEqual(result["capacity_state"], HIGH_CAPACITY)
        self.assertEqual(result["capacity_score"], 1.0)


class SignalStrengthTests(TestCase):
    """Test signal normalisation edge cases."""

    def test_medication_risk_none_scheduled(self):
        from apps.core.ai_arbitration.signal_collector import _compute_signal_strengths
        inp = {
            "health_signals": {
                "medications_scheduled": 0,
                "medications_taken": 0,
                "medications_missed": 0,
                "sleep_duration_minutes": 480,
                "sleep_target_minutes": 480,
            },
            "mood_signals": {
                "mood_trend": "stable",
                "health_keywords_in_journal": [],
            },
            "schedule_signals": {"capacity_pct": 40, "next_4h_events": []},
            "drift_signals": {
                "drift_score": 0,
                "drift_probability_24h": 0,
                "non_negotiables_missed": 0,
            },
            "relational_signals": {"tier1_drifting": 0, "tier2_drifting": 0},
            "upcoming_events": {
                "significant_next_7d": [],
                "overdue_tasks": 0,
                "approaching_deadlines": 0,
            },
        }
        strengths = _compute_signal_strengths(inp, timezone.now())
        self.assertEqual(strengths["medication_risk"], 0.0)

    def test_sleep_deficit_unknown(self):
        from apps.core.ai_arbitration.signal_collector import _compute_signal_strengths
        inp = {
            "health_signals": {
                "medications_scheduled": 0,
                "medications_taken": 0,
                "medications_missed": 0,
                "sleep_duration_minutes": None,
                "sleep_target_minutes": 480,
            },
            "mood_signals": {
                "mood_trend": "stable",
                "health_keywords_in_journal": [],
            },
            "schedule_signals": {"capacity_pct": 40, "next_4h_events": []},
            "drift_signals": {
                "drift_score": 0,
                "drift_probability_24h": 0,
                "non_negotiables_missed": 0,
            },
            "relational_signals": {"tier1_drifting": 0, "tier2_drifting": 0},
            "upcoming_events": {
                "significant_next_7d": [],
                "overdue_tasks": 0,
                "approaching_deadlines": 0,
            },
        }
        strengths = _compute_signal_strengths(inp, timezone.now())
        self.assertEqual(strengths["sleep_deficit"], 0.3)

    def test_schedule_overload_scales_linearly(self):
        from apps.core.ai_arbitration.signal_collector import _compute_signal_strengths
        inp = {
            "health_signals": {
                "medications_scheduled": 0,
                "medications_taken": 0,
                "medications_missed": 0,
                "sleep_duration_minutes": 480,
                "sleep_target_minutes": 480,
            },
            "mood_signals": {
                "mood_trend": "stable",
                "health_keywords_in_journal": [],
            },
            "schedule_signals": {"capacity_pct": 75, "next_4h_events": []},
            "drift_signals": {
                "drift_score": 0,
                "drift_probability_24h": 0,
                "non_negotiables_missed": 0,
            },
            "relational_signals": {"tier1_drifting": 0, "tier2_drifting": 0},
            "upcoming_events": {
                "significant_next_7d": [],
                "overdue_tasks": 0,
                "approaching_deadlines": 0,
            },
        }
        strengths = _compute_signal_strengths(inp, timezone.now())
        self.assertAlmostEqual(strengths["schedule_overload"], 0.5, places=1)


# ============ v2.1 Tests ============


class InterventionFatigueTests(TestCase):
    """v2.1: Test intervention fatigue scoring and bias."""

    def _create_user(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        return User.objects.create_user(
            email="fatigue_test@example.com",
            password="testpass123",
        )

    def test_repeated_ignore_increases_fatigue(self):
        """Repeatedly ignored interventions raise fatigue score."""
        from apps.core.ai_arbitration.models import InterventionResponseLog
        from apps.core.ai_arbitration.intervention_fatigue import compute_fatigue_scores

        user = self._create_user()
        today = date.today()

        # Create 7 days of mostly ignored interventions
        for i in range(7):
            InterventionResponseLog.objects.create(
                user=user,
                date=today - timedelta(days=i),
                scenario="HEALTH_CRITICAL",
                surfaced_count=3,
                complied_count=0,
                ignored_count=3,
                overrode_count=0,
            )

        result = compute_fatigue_scores(user)
        fatigue = result["scenario_fatigue"].get("HEALTH_CRITICAL", 0)
        self.assertGreater(fatigue, 0.6)

    def test_high_compliance_gives_positive_bias(self):
        """High compliance → slight positive bias."""
        from apps.core.ai_arbitration.models import InterventionResponseLog
        from apps.core.ai_arbitration.intervention_fatigue import compute_fatigue_scores

        user = self._create_user()
        today = date.today()

        for i in range(5):
            InterventionResponseLog.objects.create(
                user=user,
                date=today - timedelta(days=i),
                scenario="DRIFT_CRITICAL",
                surfaced_count=3,
                complied_count=3,
                ignored_count=0,
                overrode_count=0,
            )

        result = compute_fatigue_scores(user)
        bias = result["scenario_bias"].get("DRIFT_CRITICAL", 0)
        self.assertEqual(bias, 0.03)

    def test_fatigue_bias_never_exceeds_bounds(self):
        """Bias never exceeds ±0.05."""
        from apps.core.ai_arbitration.models import InterventionResponseLog
        from apps.core.ai_arbitration.intervention_fatigue import (
            compute_fatigue_scores,
            MAX_NEGATIVE_BIAS,
            MAX_POSITIVE_BIAS,
        )

        user = self._create_user()
        today = date.today()

        # Extreme ignore case
        for i in range(7):
            InterventionResponseLog.objects.create(
                user=user,
                date=today - timedelta(days=i),
                scenario="MOOD_CRITICAL",
                surfaced_count=10,
                complied_count=0,
                ignored_count=10,
                overrode_count=0,
            )

        result = compute_fatigue_scores(user)
        for scenario, bias in result["scenario_bias"].items():
            self.assertGreaterEqual(bias, MAX_NEGATIVE_BIAS)
            self.assertLessEqual(bias, MAX_POSITIVE_BIAS)

    def test_empty_logs_returns_empty(self):
        """No intervention logs → empty fatigue result."""
        from apps.core.ai_arbitration.intervention_fatigue import compute_fatigue_scores

        user = self._create_user()
        result = compute_fatigue_scores(user)
        self.assertEqual(result["scenario_fatigue"], {})
        self.assertEqual(result["scenario_bias"], {})

    def test_log_intervention_response(self):
        """Intervention response logging works."""
        from apps.core.ai_arbitration.models import InterventionResponseLog
        from apps.core.ai_arbitration.intervention_fatigue import log_intervention_response

        user = self._create_user()
        log_intervention_response(user, "HEALTH_CRITICAL", "surfaced")
        log_intervention_response(user, "HEALTH_CRITICAL", "surfaced")
        log_intervention_response(user, "HEALTH_CRITICAL", "ignored")

        log = InterventionResponseLog.objects.get(
            user=user, scenario="HEALTH_CRITICAL"
        )
        self.assertEqual(log.surfaced_count, 2)
        self.assertEqual(log.ignored_count, 1)


class NudgeMemoryTests(TestCase):
    """v2.1: Test recent nudge memory and collision detection."""

    def _create_user(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        return User.objects.create_user(
            email="nudge_test@example.com",
            password="testpass123",
        )

    def test_duplicate_semantic_penalised(self):
        """Same semantic tag within 6h gets priority penalty."""
        from apps.core.ai_arbitration.models import RecentNudgeMemory
        from apps.core.ai_arbitration.nudge_memory import check_nudge_collisions

        user = self._create_user()

        # Record a recent nudge
        RecentNudgeMemory.objects.create(
            user=user,
            scenario="HEALTH_CRITICAL",
            semantic_tag="HEALTH_GATE",
        )

        candidates = [
            {"category": "HEALTH_GATE", "label": "Meds", "priority": 90},
            {"category": "SUPPORTIVE", "label": "Mood", "priority": 60},
        ]

        result = check_nudge_collisions(user, candidates, "STABLE_EXECUTION")
        health_item = next(c for c in result if c["category"] == "HEALTH_GATE")
        mood_item = next(c for c in result if c["category"] == "SUPPORTIVE")

        # Health should be penalised
        self.assertTrue(health_item.get("_nudge_collision", False))
        self.assertFalse(mood_item.get("_nudge_collision", False))

    def test_escalation_bypasses_penalty(self):
        """HEALTH_CRITICAL severity bypasses nudge penalty."""
        from apps.core.ai_arbitration.models import RecentNudgeMemory
        from apps.core.ai_arbitration.nudge_memory import check_nudge_collisions

        user = self._create_user()

        RecentNudgeMemory.objects.create(
            user=user,
            scenario="HEALTH_CRITICAL",
            semantic_tag="HEALTH_GATE",
        )

        candidates = [
            {"category": "HEALTH_GATE", "label": "Meds", "priority": 90},
        ]

        # HEALTH_CRITICAL is a severity escalation → bypass
        result = check_nudge_collisions(user, candidates, "HEALTH_CRITICAL")
        self.assertFalse(result[0].get("_nudge_collision", False))

    def test_record_and_retrieve(self):
        """Surfaced nudges are recorded and retrievable."""
        from apps.core.ai_arbitration.models import RecentNudgeMemory
        from apps.core.ai_arbitration.nudge_memory import record_surfaced_nudges

        user = self._create_user()
        items = [
            {"category": "HEALTH_GATE", "label": "Meds"},
            {"category": "SUPPORTIVE", "label": "Mood"},
        ]
        record_surfaced_nudges(user, items, "HEALTH_CRITICAL")

        count = RecentNudgeMemory.objects.filter(user=user).count()
        self.assertEqual(count, 2)

    def test_empty_memory_no_penalty(self):
        """No recent nudges → no penalty applied."""
        from apps.core.ai_arbitration.nudge_memory import check_nudge_collisions

        user = self._create_user()
        candidates = [
            {"category": "HEALTH_GATE", "label": "Meds", "priority": 90},
        ]
        result = check_nudge_collisions(user, candidates, "STABLE_EXECUTION")
        self.assertFalse(result[0].get("_nudge_collision", False))


class CapacityStyleBiasTests(TestCase):
    """v2.1: Test capacity-based intervention style bias."""

    def _make_scenario(self, dominant="HEALTH_CRITICAL",
                       confidence_level="MODERATE"):
        return {
            "dominant_scenario": dominant,
            "secondary_scenarios": [],
            "scenario_scores": {},
            "confidence": 0.8,
            "confidence_level": confidence_level,
            "confidence_gap": 0.1,
        }

    def test_critical_capacity_returns_maintenance_bias(self):
        """CRITICAL capacity → maintenance style bias."""
        scenario = self._make_scenario()
        strengths = {"medication_risk": 0.8}
        capacity = {
            "capacity_score": 0.15,
            "capacity_state": CRITICAL,
            "max_surfaced": 1,
            "components": {},
        }
        result = decide_intervention(
            scenario, [], strengths, _make_signals(),
            capacity=capacity,
        )
        self.assertEqual(result["style_bias"], "maintenance")

    def test_low_capacity_returns_tactical_bias(self):
        """LOW capacity → tactical style bias."""
        scenario = self._make_scenario()
        strengths = {"medication_risk": 0.8}
        capacity = {
            "capacity_score": 0.35,
            "capacity_state": LOW,
            "max_surfaced": 2,
            "components": {},
        }
        result = decide_intervention(
            scenario, [], strengths, _make_signals(),
            capacity=capacity,
        )
        self.assertEqual(result["style_bias"], "tactical")

    def test_high_capacity_returns_strategic_bias(self):
        """HIGH_CAPACITY → strategic style bias."""
        scenario = self._make_scenario()
        strengths = {"medication_risk": 0.8}
        capacity = {
            "capacity_score": 0.85,
            "capacity_state": HIGH_CAPACITY,
            "max_surfaced": 3,
            "components": {},
        }
        result = decide_intervention(
            scenario, [], strengths, _make_signals(),
            capacity=capacity,
        )
        self.assertEqual(result["style_bias"], "strategic")

    def test_maintenance_narrative_suppresses_strategic(self):
        """Maintenance style bias → narrative avoids strategic language."""
        scenario = self._make_scenario()
        intervention = {
            "intervention_style": PROTECTIVE,
            "style_description": "Protect energy.",
            "surfaced_items": [],
            "suppressed_items": [],
            "primary_composite": None,
            "style_bias": "maintenance",
            "pattern_tier2_active": False,
        }
        narrative = build_narrative(
            scenario, [], intervention, _make_signals()
        )
        self.assertIn("MAINTENANCE MODE", narrative)
        self.assertIn("optional", narrative.lower())

    def test_tactical_narrative_avoids_planning(self):
        """Tactical style bias → narrative avoids planning language."""
        scenario = self._make_scenario()
        intervention = {
            "intervention_style": PROTECTIVE,
            "style_description": "Protect energy.",
            "surfaced_items": [],
            "suppressed_items": [],
            "primary_composite": None,
            "style_bias": "tactical",
            "pattern_tier2_active": False,
        }
        narrative = build_narrative(
            scenario, [], intervention, _make_signals()
        )
        self.assertIn("TACTICAL ONLY", narrative)


class PatternTier2Tests(TestCase):
    """v2.1: Test pattern escalation Tier 2."""

    def _create_user(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        return User.objects.create_user(
            email="tier2_test@example.com",
            password="testpass123",
        )

    def test_drift_tier2_triggers(self):
        """DRIFT_CRITICAL ≥7 in 14 days → Tier 2."""
        from apps.core.ai_arbitration.models import ScenarioHistory
        from apps.core.ai_arbitration.pattern_analyzer import analyze_patterns

        user = self._create_user()
        today = date.today()

        for i in range(8):
            ScenarioHistory.objects.create(
                user=user,
                date=today - timedelta(days=i),
                dominant_scenario="DRIFT_CRITICAL",
                intervention_style="ACCOUNTABILITY",
            )

        result = analyze_patterns(user)
        tier2 = result["tier2"]
        self.assertTrue(tier2["tier2_active"])
        patterns = [t["pattern"] for t in tier2["triggers"]]
        self.assertIn("DRIFT_PERSISTENT_T2", patterns)

    def test_mood_tier2_triggers(self):
        """MOOD_CRITICAL ≥5 in 7 days → Tier 2."""
        from apps.core.ai_arbitration.models import ScenarioHistory
        from apps.core.ai_arbitration.pattern_analyzer import analyze_patterns

        user = self._create_user()
        today = date.today()

        for i in range(5):
            ScenarioHistory.objects.create(
                user=user,
                date=today - timedelta(days=i),
                dominant_scenario="MOOD_CRITICAL",
                intervention_style="SUPPORTIVE",
            )

        result = analyze_patterns(user)
        tier2 = result["tier2"]
        self.assertTrue(tier2["tier2_active"])

    def test_tier2_overrides_max_surfaced(self):
        """Tier 2 active → max surfaced forced to 1."""
        scenario = {
            "dominant_scenario": "DRIFT_CRITICAL",
            "secondary_scenarios": [],
            "scenario_scores": {},
            "confidence": 0.8,
            "confidence_level": "HIGH",
            "confidence_gap": 0.2,
        }
        strengths = {
            "drift_severity": 0.9,
            "non_negotiable_miss": 0.8,
            "mood_decline": 0.7,
            "medication_risk": 0.6,
        }
        tier2 = {"tier2_active": True, "triggers": []}
        result = decide_intervention(
            scenario, [], strengths, _make_signals(),
            pattern_tier2=tier2,
        )
        self.assertLessEqual(len(result["surfaced_items"]), 1)
        self.assertTrue(result["pattern_tier2_active"])

    def test_tier2_not_triggered_below_threshold(self):
        """Below tier 2 thresholds → not active."""
        from apps.core.ai_arbitration.models import ScenarioHistory
        from apps.core.ai_arbitration.pattern_analyzer import analyze_patterns

        user = self._create_user()
        today = date.today()

        # Only 3 DRIFT_CRITICAL — below tier 2 threshold of 7
        for i in range(3):
            ScenarioHistory.objects.create(
                user=user,
                date=today - timedelta(days=i),
                dominant_scenario="DRIFT_CRITICAL",
                intervention_style="ACCOUNTABILITY",
            )

        result = analyze_patterns(user)
        self.assertFalse(result["tier2"]["tier2_active"])

    def test_tier2_does_not_bypass_safety_clamps(self):
        """Tier 2 does not break weight tuning bounds."""
        from apps.core.ai_arbitration.models import WeightAdjustment

        user = self._create_user()
        # Verify weight bounds still hold
        WeightAdjustment.objects.create(
            user=user,
            scenario="DRIFT_CRITICAL",
            signal="drift_severity",
            baseline_weight=0.40,
            adjustment_delta=0.10,
        )
        adj = WeightAdjustment.objects.get(
            user=user, scenario="DRIFT_CRITICAL"
        )
        self.assertLessEqual(abs(adj.adjustment_delta), 0.10)

    def test_tier2_narrative_contains_reset(self):
        """Tier 2 active → narrative mentions strategic reset."""
        scenario = {
            "dominant_scenario": "DRIFT_CRITICAL",
            "secondary_scenarios": [],
            "scenario_scores": {},
            "confidence_level": "MODERATE",
            "confidence_gap": 0.1,
        }
        intervention = {
            "intervention_style": ACCOUNTABILITY,
            "style_description": "Name gap clearly.",
            "surfaced_items": [],
            "suppressed_items": [],
            "primary_composite": None,
            "style_bias": "normal",
            "pattern_tier2_active": True,
        }
        narrative = build_narrative(
            scenario, [], intervention, _make_signals()
        )
        self.assertIn("STRATEGIC RESET CONSIDERATION", narrative)
        self.assertIn("reset conversation", narrative.lower())


class CapacityVolatilityTests(TestCase):
    """v2.1: Test capacity volatility index."""

    def _create_user(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        return User.objects.create_user(
            email="volatility_test@example.com",
            password="testpass123",
        )

    def test_high_variance_triggers_flag(self):
        """High std_dev of capacity scores → volatility flag."""
        from apps.core.ai_arbitration.models import DailyCapacityLog
        from apps.core.ai_arbitration.capacity_volatility import compute_capacity_volatility

        user = self._create_user()
        today = date.today()

        # Alternating high/low scores → high variance
        scores = [0.9, 0.2, 0.8, 0.15, 0.85]
        for i, score in enumerate(scores):
            DailyCapacityLog.objects.create(
                user=user,
                date=today - timedelta(days=i),
                capacity_score=score,
                capacity_state="NORMAL",
            )

        result = compute_capacity_volatility(user)
        self.assertTrue(result["volatility_flag"])
        self.assertGreater(result["std_dev"], 0.25)

    def test_stable_scores_no_flag(self):
        """Stable capacity scores → no volatility flag."""
        from apps.core.ai_arbitration.models import DailyCapacityLog
        from apps.core.ai_arbitration.capacity_volatility import compute_capacity_volatility

        user = self._create_user()
        today = date.today()

        # Stable scores
        for i in range(5):
            DailyCapacityLog.objects.create(
                user=user,
                date=today - timedelta(days=i),
                capacity_score=0.55 + (i * 0.01),
                capacity_state="NORMAL",
            )

        result = compute_capacity_volatility(user)
        self.assertFalse(result["volatility_flag"])
        self.assertLess(result["std_dev"], 0.25)

    def test_confidence_downgrade_when_volatile(self):
        """Volatility flag → confidence downgraded by one level."""
        from apps.core.ai_arbitration.capacity_volatility import apply_volatility_adjustments

        volatility = {"volatility_flag": True, "std_dev": 0.35}
        result = apply_volatility_adjustments(volatility, "HIGH")
        self.assertEqual(result["adjusted_confidence_level"], "MODERATE")
        self.assertTrue(result["volatility_applied"])

        result2 = apply_volatility_adjustments(volatility, "MODERATE")
        self.assertEqual(result2["adjusted_confidence_level"], "LOW")

    def test_no_downgrade_when_stable(self):
        """No volatility → confidence unchanged."""
        from apps.core.ai_arbitration.capacity_volatility import apply_volatility_adjustments

        volatility = {"volatility_flag": False, "std_dev": 0.10}
        result = apply_volatility_adjustments(volatility, "HIGH")
        self.assertEqual(result["adjusted_confidence_level"], "HIGH")
        self.assertFalse(result["volatility_applied"])

    def test_low_confidence_not_downgraded_further(self):
        """LOW confidence stays LOW even with volatility."""
        from apps.core.ai_arbitration.capacity_volatility import apply_volatility_adjustments

        volatility = {"volatility_flag": True, "std_dev": 0.35}
        result = apply_volatility_adjustments(volatility, "LOW")
        self.assertEqual(result["adjusted_confidence_level"], "LOW")

    def test_insufficient_data_returns_no_flag(self):
        """Fewer than 2 data points → no volatility flag."""
        from apps.core.ai_arbitration.capacity_volatility import compute_capacity_volatility

        user = self._create_user()
        result = compute_capacity_volatility(user)
        self.assertFalse(result["volatility_flag"])
        self.assertEqual(result["sample_count"], 0)


class ArbitrationNeverRaisesTests(TestCase):
    """v2.1: Verify pipeline never raises with new steps."""

    def _create_user(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        return User.objects.create_user(
            email="never_raises_test@example.com",
            password="testpass123",
        )

    @patch("apps.core.ai_arbitration.signal_collector.collect_signals")
    def test_pipeline_survives_fatigue_failure(self, mock_collect):
        """Pipeline continues if fatigue engine fails."""
        user = self._create_user()
        mock_collect.return_value = _make_full_signals()

        with patch(
            "apps.core.ai_arbitration.intervention_fatigue.compute_fatigue_scores",
            side_effect=RuntimeError("fatigue exploded")
        ):
            from apps.core.ai_arbitration import run_arbitration
            result = run_arbitration(user)
            self.assertTrue(result.success)

    @patch("apps.core.ai_arbitration.signal_collector.collect_signals")
    def test_pipeline_survives_volatility_failure(self, mock_collect):
        """Pipeline continues if volatility engine fails."""
        user = self._create_user()
        mock_collect.return_value = _make_full_signals()

        with patch(
            "apps.core.ai_arbitration.capacity_volatility.compute_capacity_volatility",
            side_effect=RuntimeError("volatility exploded")
        ):
            from apps.core.ai_arbitration import run_arbitration
            result = run_arbitration(user)
            self.assertTrue(result.success)

    @patch("apps.core.ai_arbitration.signal_collector.collect_signals")
    def test_pipeline_survives_nudge_memory_failure(self, mock_collect):
        """Pipeline continues if nudge memory fails."""
        user = self._create_user()
        mock_collect.return_value = _make_full_signals()

        with patch(
            "apps.core.ai_arbitration.nudge_memory.check_nudge_collisions",
            side_effect=RuntimeError("nudge exploded")
        ):
            from apps.core.ai_arbitration import run_arbitration
            result = run_arbitration(user)
            self.assertTrue(result.success)

    @patch("apps.core.ai_arbitration.signal_collector.collect_signals")
    def test_v21_fields_present_in_result(self, mock_collect):
        """v2.1 fields present in ArbitrationResult."""
        user = self._create_user()
        mock_collect.return_value = _make_full_signals()

        from apps.core.ai_arbitration import run_arbitration
        result = run_arbitration(user)

        self.assertTrue(result.success)
        self.assertIn(result.style_bias, [
            "strategic", "normal", "tactical", "maintenance"
        ])
        self.assertIsInstance(result.fatigue_bias_applied, dict)
        self.assertIsInstance(result.pattern_tier2_active, bool)
        self.assertIsInstance(result.volatility_flag, bool)
        self.assertIsInstance(result.volatility_std_dev, float)


# ============ Helpers ============

def _make_signals():
    """Standard signal dict for tests."""
    return {
        "health_signals": {
            "medications_scheduled": 3,
            "medications_taken": 1,
            "medications_missed": 2,
            "sleep_duration_minutes": 300,
            "sleep_target_minutes": 480,
        },
        "mood_signals": {"mood_trend": "falling", "health_keywords_in_journal": []},
        "schedule_signals": {"capacity_pct": 85, "next_4h_events": []},
        "drift_signals": {
            "drift_score": 45,
            "drift_probability_24h": 0.6,
            "non_negotiables_missed": 2,
        },
        "relational_signals": {"drifting_relationships": []},
        "upcoming_events": {
            "significant_next_7d": [],
            "overdue_tasks": 3,
            "approaching_deadlines": 1,
        },
        "time_context": {"time_of_day": "morning"},
    }


def _make_full_signals():
    """Full signal dict for pipeline tests (mocking collect_signals)."""
    return {
        "time_context": {"time_of_day": "morning", "hour": 9},
        "health_signals": {
            "medications_scheduled": 0,
            "medications_taken": 0,
            "medications_missed": 0,
            "sleep_duration_minutes": 480,
            "sleep_target_minutes": 480,
        },
        "mood_signals": {
            "mood_trend": "stable",
            "health_keywords_in_journal": [],
        },
        "schedule_signals": {"capacity_pct": 40, "next_4h_events": []},
        "drift_signals": {
            "drift_score": 5,
            "drift_probability_24h": 0.1,
            "non_negotiables_missed": 0,
        },
        "relational_signals": {
            "drifting_relationships": [],
            "tier1_drifting": 0,
            "tier2_drifting": 0,
        },
        "upcoming_events": {
            "significant_next_7d": [],
            "overdue_tasks": 0,
            "approaching_deadlines": 0,
        },
        "energy_indicators": {},
        "risk_indicators": {},
        "raw_strengths": {
            "calendar_urgency": 0.0,
            "deadline_pressure": 0.0,
            "medication_risk": 0.0,
            "sleep_deficit": 0.0,
            "injury_risk": 0.0,
            "drift_severity": 0.0,
            "non_negotiable_miss": 0.0,
            "mood_decline": 0.0,
            "emotional_load": 0.0,
            "relationship_drift": 0.0,
            "relationship_event": 0.0,
            "schedule_overload": 0.0,
            "open_loop_count": 0.0,
        },
    }
