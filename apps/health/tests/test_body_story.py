# ==============================================================================
# File: apps/health/tests/test_body_story.py
# Project: Whole Life Journey
# Description: "Your Body Story" executive-briefing composer — determinism, grounding,
#              and graceful degradation. The composer is pure (operates on the
#              pre-computed build_body_intelligence dict), so these run without a DB.
# ==============================================================================
from datetime import date, datetime, timezone

from django.test import SimpleTestCase

from apps.health.services.body_story_builder import build_body_story


def _bi(**over):
    """A minimal, well-formed build_body_intelligence dict with sane defaults."""
    base = {
        "as_of": date(2026, 7, 13),
        "has_any_data": True,
        "weight": {"count": 30, "current_lb": 185.0, "total_change_lb": -12.0,
                   "first_at": datetime(2026, 5, 11, tzinfo=timezone.utc),
                   "current_at": datetime(2026, 7, 13, tzinfo=timezone.utc)},
        "goal": {"goal": 175.0, "current_weight": 185.0, "remaining": 10.0,
                 "unit": "lb", "progress_percent": 55.0},
        "body_comp": {},
        "snapshot": {},
        "sessions": {"count": 4},
    }
    base.update(over)
    return base


class BodyStoryEmptyStateTests(SimpleTestCase):
    def test_no_data_returns_cold_start_card(self):
        story = build_body_story({"as_of": date(2026, 7, 13), "has_any_data": False})
        self.assertFalse(story["has_signal"])
        self.assertEqual(story["status"]["tone"], "unknown")
        self.assertIn("baseline", story["status"]["label"].lower())
        self.assertTrue(story["narrative"])          # never empty
        self.assertIsNotNone(story["recommendation"])
        self.assertEqual(story["wins"], [])
        self.assertEqual(story["watch_items"], [])

    def test_contract_keys_always_present(self):
        story = build_body_story({"has_any_data": False})
        for key in ("status", "confidence", "narrative", "wins",
                    "watch_items", "recommendation", "has_signal", "as_of"):
            self.assertIn(key, story)


class BodyStoryStatusTests(SimpleTestCase):
    def test_recomposition_leads_as_positive(self):
        story = build_body_story(_bi(body_comp={
            "recomposition_flag_14d": True, "fat_mass_delta_14d": -2.1,
            "lean_mass_delta_14d": 0.8, "phase_confidence": 85,
        }))
        self.assertEqual(story["status"]["label"], "Recomposing")
        self.assertEqual(story["status"]["tone"], "positive")
        titles = [w["title"] for w in story["wins"]]
        self.assertIn("Recomposition underway", titles)

    def test_excellent_quality_status(self):
        story = build_body_story(_bi(body_comp={
            "fat_loss_quality_label": "EXCELLENT", "fat_loss_ratio_14d": 0.95,
            "phase_confidence": 80, "weight_delta_14d": -1.5,
        }))
        self.assertEqual(story["status"]["label"], "Fat loss on track")
        self.assertEqual(story["status"]["tone"], "positive")

    def test_muscle_loss_risk_is_critical_and_needs_attention(self):
        story = build_body_story(_bi(body_comp={
            "fat_loss_quality_label": "MUSCLE_LOSS_RISK",
            "muscle_loss_risk_level": "HIGH", "muscle_loss_risk_score": 72,
            "phase_confidence": 75,
        }))
        self.assertEqual(story["status"]["tone"], "critical")
        self.assertEqual(story["status"]["label"], "Needs attention")
        self.assertTrue(story["watch_items"])
        # Recommendation must be grounded in the muscle-loss lever, not generic.
        self.assertEqual(story["recommendation"]["title"], "Protect your muscle")

    def test_plateau_maps_to_break_the_plateau_recommendation(self):
        story = build_body_story(_bi(body_comp={
            "plateau_status": "TRUE_PLATEAU", "phase_confidence": 85,
            "weight_delta_14d": 0.0,
        }))
        self.assertEqual(story["recommendation"]["title"], "Break the plateau")
        self.assertEqual(story["status"]["tone"], "caution")

    def test_all_clear_holds_the_course(self):
        story = build_body_story(_bi(
            weight={"count": 30, "current_lb": 185.0, "total_change_lb": -12.0},
            body_comp={"fat_loss_quality_label": "GOOD", "phase_confidence": 80,
                       "weight_delta_14d": -1.2},
        ))
        self.assertFalse(story["watch_items"])
        self.assertEqual(story["recommendation"]["title"], "Hold the course")


class BodyStoryConfidenceTests(SimpleTestCase):
    def test_low_density_is_low_confidence_with_caveat(self):
        story = build_body_story(_bi(
            weight={"count": 2, "current_lb": 185.0, "total_change_lb": -1.0},
            body_comp={}, sessions={"count": 0},
        ))
        self.assertEqual(story["confidence"]["level"], "low")
        self.assertTrue(any("still early" in s or "sharpen" in s for s in story["narrative"]))

    def test_high_density_with_composition_is_high_confidence(self):
        story = build_body_story(_bi(
            weight={"count": 40, "current_lb": 185.0, "total_change_lb": -12.0},
            body_comp={"fat_loss_quality_label": "EXCELLENT", "phase_confidence": 85,
                       "weight_delta_14d": -1.0},
        ))
        self.assertEqual(story["confidence"]["level"], "high")

    def test_confidence_basis_names_the_evidence(self):
        story = build_body_story(_bi())
        self.assertIn("weigh-in", story["confidence"]["basis"])

    def test_confidence_exposes_itemized_factors(self):
        # Structured for the future "Based on: …" expandable list — computed now, not yet
        # rendered. Weigh-ins, composition readings, check-ins, and history span.
        story = build_body_story(_bi(
            weight={"count": 58, "current_lb": 185.0, "total_change_lb": -12.0,
                    "first_at": datetime(2026, 5, 11, tzinfo=timezone.utc),
                    "current_at": datetime(2026, 7, 13, tzinfo=timezone.utc)},
            body_comp={"fat_loss_quality_label": "EXCELLENT", "phase_confidence": 82,
                       "weight_delta_14d": -1.0,
                       "fat_mass_trend_56d": [{"date": "2026-07-0%d" % d, "value": 60 - d}
                                              for d in range(1, 10)]},
            sessions={"count": 4},
        ))
        factors = story["confidence"]["factors"]
        labels = " | ".join(f["label"] for f in factors)
        self.assertIn("58 weigh-ins", labels)
        self.assertIn("9 body-composition readings", labels)
        self.assertIn("4 body check-ins", labels)
        self.assertTrue(any("week" in f["label"] for f in factors))
        # Every factor carries a machine-readable count for future UI.
        self.assertTrue(all("count" in f for f in factors))

    def test_confidence_factors_present_even_when_empty(self):
        self.assertEqual(build_body_story({"has_any_data": False})["confidence"]["factors"], [])


class BodyStoryRankingTests(SimpleTestCase):
    def test_wins_ranked_biggest_first(self):
        # Recomposition (weight 95) must outrank a goal-pace win (weight 50).
        story = build_body_story(_bi(body_comp={
            "recomposition_flag_14d": True, "fat_mass_delta_14d": -2.0,
            "lean_mass_delta_14d": 0.6, "phase_confidence": 85,
        }))
        self.assertEqual(story["wins"][0]["title"], "Recomposition underway")

    def test_watch_ranked_by_severity_first(self):
        # A critical muscle-loss risk must sit above a caution plateau.
        story = build_body_story(_bi(body_comp={
            "muscle_loss_risk_level": "HIGH", "muscle_loss_risk_score": 70,
            "plateau_status": "TRUE_PLATEAU", "phase_confidence": 80,
            "weight_delta_14d": 0.0,
        }))
        self.assertIn("muscle-loss risk", story["watch_items"][0]["title"].lower())
        self.assertEqual(story["watch_items"][0]["tone"], "critical")

    def test_ranking_is_deterministic(self):
        payload = _bi(body_comp={
            "recomposition_flag_14d": True, "fat_loss_quality_label": "EXCELLENT",
            "fat_mass_delta_14d": -2.0, "lean_mass_delta_14d": 0.6,
            "fat_loss_ratio_14d": 0.9, "phase_confidence": 85,
        })
        a = [w["title"] for w in build_body_story(dict(payload))["wins"]]
        b = [w["title"] for w in build_body_story(dict(payload))["wins"]]
        self.assertEqual(a, b)


class BodyStoryDeterminismTests(SimpleTestCase):
    def test_same_input_same_output(self):
        payload = _bi(body_comp={
            "recomposition_flag_14d": True, "fat_mass_delta_14d": -2.1,
            "lean_mass_delta_14d": 0.8, "phase_confidence": 85,
            "muscle_loss_risk_level": "LOW",
        })
        self.assertEqual(build_body_story(dict(payload)), build_body_story(dict(payload)))


class BodyStoryGroundingTests(SimpleTestCase):
    def test_measurement_win_reflects_snapshot(self):
        story = build_body_story(_bi(snapshot={
            "largest_improvement": {"metric": "waist", "label": "Waist", "delta": -2.0},
            "units": {"waist": "in"},
        }))
        joined = " ".join(w["title"] + w["detail"] for w in story["wins"])
        self.assertIn("Waist", joined)

    def test_gaining_against_loss_goal_is_a_watch_item(self):
        story = build_body_story(_bi(body_comp={
            "fat_loss_quality_label": "GAINING", "phase_confidence": 75,
            "weight_delta_14d": 1.4,
        }))
        # Goal is to lose (175 < 185), so gaining is flagged, not celebrated.
        self.assertTrue(any("trending up" in it["title"].lower() for it in story["watch_items"]))


class BodyStoryRobustnessTests(SimpleTestCase):
    def test_malformed_body_comp_does_not_crash(self):
        story = build_body_story(_bi(body_comp={
            "fat_mass_delta_14d": "not-a-number", "fat_loss_ratio_14d": None,
            "recomposition_flag_14d": True,
        }))
        self.assertTrue(story["has_signal"])
        self.assertIn("status", story)
