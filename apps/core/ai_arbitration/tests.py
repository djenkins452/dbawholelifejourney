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
"""
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone

from apps.core.ai_arbitration.scenario_classifier import (
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

    def _make_scenario(self, dominant, secondaries=None, scores=None):
        return {
            "dominant_scenario": dominant,
            "secondary_scenarios": secondaries or [],
            "scenario_scores": scores or {},
            "confidence": 0.8,
        }

    def _make_signals(self):
        return {
            "health_signals": {
                "medications_scheduled": 3,
                "medications_taken": 1,
                "medications_missed": 2,
                "sleep_duration_minutes": 300,
                "sleep_target_minutes": 480,
            },
            "mood_signals": {"mood_trend": "falling"},
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

    def test_time_critical_gives_directive(self):
        scenario = self._make_scenario(TIME_CRITICAL)
        strengths = {"calendar_urgency": 0.8, "deadline_pressure": 0.6}
        result = decide_intervention(
            scenario, [], strengths, self._make_signals()
        )
        self.assertEqual(result["intervention_style"], DIRECTIVE)

    def test_health_critical_gives_protective(self):
        scenario = self._make_scenario(HEALTH_CRITICAL)
        strengths = {"medication_risk": 0.8, "sleep_deficit": 0.6}
        result = decide_intervention(
            scenario, [], strengths, self._make_signals()
        )
        self.assertEqual(result["intervention_style"], PROTECTIVE)

    def test_drift_critical_gives_accountability(self):
        scenario = self._make_scenario(DRIFT_CRITICAL)
        strengths = {"drift_severity": 0.7, "non_negotiable_miss": 0.6}
        result = decide_intervention(
            scenario, [], strengths, self._make_signals()
        )
        self.assertEqual(result["intervention_style"], ACCOUNTABILITY)

    def test_mood_critical_gives_supportive(self):
        scenario = self._make_scenario(MOOD_CRITICAL)
        strengths = {"mood_decline": 0.8, "emotional_load": 0.6}
        result = decide_intervention(
            scenario, [], strengths, self._make_signals()
        )
        self.assertEqual(result["intervention_style"], SUPPORTIVE)

    def test_relationship_critical_gives_strategic(self):
        scenario = self._make_scenario(RELATIONSHIP_CRITICAL)
        strengths = {"relationship_event": 0.7}
        signals = self._make_signals()
        signals["upcoming_events"]["significant_next_7d"] = [
            {"title": "Mom's Birthday", "type": "birthday",
             "person": "Mom", "days_until": 2, "years": 65}
        ]
        result = decide_intervention(scenario, [], strengths, signals)
        self.assertEqual(result["intervention_style"], STRATEGIC)

    def test_stable_gives_execution(self):
        scenario = self._make_scenario(STABLE_EXECUTION)
        result = decide_intervention(
            scenario, [], {}, self._make_signals()
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
            scenario, composites, strengths, self._make_signals()
        )
        self.assertEqual(result["intervention_style"], PROTECTIVE)
        self.assertEqual(result["primary_composite"], "LOW_CAPACITY_DAY")

    def test_max_three_surfaced(self):
        """Never more than 3 surfaced items."""
        scenario = self._make_scenario(HEALTH_CRITICAL)
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
            scenario, [], strengths, self._make_signals()
        )
        self.assertLessEqual(len(result["surfaced_items"]), 3)

    def test_suppressed_items_tracked(self):
        """Items beyond top 3 are suppressed."""
        scenario = self._make_scenario(HEALTH_CRITICAL)
        strengths = {
            "medication_risk": 0.9,
            "sleep_deficit": 0.8,
            "drift_severity": 0.7,
            "mood_decline": 0.6,
            "deadline_pressure": 0.5,
        }
        result = decide_intervention(
            scenario, [], strengths, self._make_signals()
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
            scenario, [], strengths, self._make_signals()
        )
        self.assertEqual(result["intervention_style"], SUPPORTIVE)
        # Check that mood-related items are surfaced, not deadline
        surfaced_cats = [s["category"] for s in result["surfaced_items"]]
        self.assertIn("SUPPORTIVE", surfaced_cats)


class NarrativeEngineTests(TestCase):
    """Test executive narrative generation."""

    def _make_signals(self, **overrides):
        base = {
            "health_signals": {
                "sleep_duration_minutes": 420,
                "sleep_target_minutes": 480,
                "medications_missed": 0,
                "medications_scheduled": 2,
                "medications_taken": 2,
            },
            "mood_signals": {
                "mood_trend": "stable",
                "health_keywords_in_journal": [],
            },
            "schedule_signals": {
                "capacity_pct": 60,
                "next_4h_events": [],
            },
            "drift_signals": {
                "drift_score": 10,
                "non_negotiables_missed": 0,
            },
            "relational_signals": {
                "drifting_relationships": [],
            },
            "upcoming_events": {
                "significant_next_7d": [],
                "overdue_tasks": 0,
                "approaching_deadlines": 0,
            },
            "time_context": {
                "time_of_day": "morning",
            },
        }
        for k, v in overrides.items():
            if isinstance(v, dict) and k in base:
                base[k].update(v)
            else:
                base[k] = v
        return base

    def test_stable_execution_narrative(self):
        """Clean day → execution framing."""
        scenario = {
            "dominant_scenario": STABLE_EXECUTION,
            "secondary_scenarios": [],
            "scenario_scores": {},
        }
        intervention = {
            "intervention_style": EXECUTION,
            "style_description": "Clean execution day.",
            "surfaced_items": [],
            "suppressed_items": [],
            "primary_composite": None,
        }
        narrative = build_narrative(
            scenario, [], intervention, self._make_signals()
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
        signals = self._make_signals(
            health_signals={"medications_missed": 2, "sleep_duration_minutes": 300,
                            "sleep_target_minutes": 480}
        )
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
        signals = self._make_signals(
            health_signals={"sleep_duration_minutes": 300, "sleep_target_minutes": 480},
            schedule_signals={"capacity_pct": 87},
        )
        narrative = build_narrative(scenario, composites, intervention, signals)
        self.assertIn("LOW_CAPACITY_DAY", narrative)
        self.assertIn("protection", narrative.lower())

    def test_relationship_event_narrative(self):
        """Relationship event → surfaces person and timeline."""
        scenario = {
            "dominant_scenario": RELATIONSHIP_CRITICAL,
            "secondary_scenarios": [],
            "scenario_scores": {},
        }
        intervention = {
            "intervention_style": STRATEGIC,
            "style_description": "Forward planning.",
            "surfaced_items": [],
            "suppressed_items": [],
            "primary_composite": "RELATIONAL_OPPORTUNITY",
        }
        signals = self._make_signals(
            upcoming_events={
                "significant_next_7d": [
                    {"title": "Mom's Birthday", "type": "birthday",
                     "person": "Mom", "days_until": 2, "years": 65},
                ],
                "overdue_tasks": 0,
                "approaching_deadlines": 0,
            }
        )
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
            scenario, [], intervention, self._make_signals()
        )
        self.assertIn("SUPPRESS", narrative)
        self.assertIn("Deadline", narrative)

    def test_narrative_unify_instruction_present(self):
        """Narrative always includes unification instruction."""
        scenario = {
            "dominant_scenario": STABLE_EXECUTION,
            "secondary_scenarios": [],
            "scenario_scores": {},
        }
        intervention = {
            "intervention_style": EXECUTION,
            "style_description": "Execute.",
            "surfaced_items": [],
            "suppressed_items": [],
            "primary_composite": None,
        }
        narrative = build_narrative(
            scenario, [], intervention, self._make_signals()
        )
        self.assertIn("Unify your response", narrative)
        self.assertIn("Do NOT list separate reminders", narrative)


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
        mock_collect.return_value = {
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

        from apps.core.ai_arbitration import run_arbitration
        result = run_arbitration(user)

        self.assertTrue(result.success)
        self.assertEqual(result.dominant_scenario, STABLE_EXECUTION)
        self.assertEqual(result.intervention_style, EXECUTION)
        self.assertIn("EXECUTIVE JUDGMENT", result.narrative_injection)

    @patch("apps.core.ai_arbitration.signal_collector.collect_signals")
    def test_full_pipeline_health_critical(self, mock_collect):
        """Full pipeline with health signals → HEALTH_CRITICAL."""
        user = self._create_user()
        mock_collect.return_value = {
            "time_context": {"time_of_day": "morning", "hour": 9},
            "health_signals": {
                "medications_scheduled": 3,
                "medications_taken": 0,
                "medications_missed": 3,
                "sleep_duration_minutes": 240,
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
                "medication_risk": 1.0,
                "sleep_deficit": 0.5,
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
    def test_decision_logged(self, mock_collect):
        """Arbitration decisions are logged to the database."""
        user = self._create_user()
        mock_collect.return_value = {
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

        from apps.core.ai_arbitration import run_arbitration
        from apps.core.ai_arbitration.models import ArbitrationDecisionLog

        result = run_arbitration(user)
        self.assertTrue(result.success)

        logs = ArbitrationDecisionLog.objects.filter(user=user)
        self.assertEqual(logs.count(), 1)
        log = logs.first()
        self.assertEqual(log.dominant_scenario, STABLE_EXECUTION)
        self.assertEqual(log.intervention_style, EXECUTION)


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
