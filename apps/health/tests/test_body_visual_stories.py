# ==============================================================================
# File: apps/health/tests/test_body_visual_stories.py
# Project: Whole Life Journey
# Description: Executive Visual Story facts — Body Shape + Limb Development. Verifies the
#              honest Visual Truth states (changed / stable / current-only / missing /
#              stale / low-confidence) and left/right balance. Pure; runs without a DB.
# ==============================================================================
from datetime import date, timedelta

from django.test import SimpleTestCase

from apps.health.services.body_visual_stories import (
    build_body_shape,
    build_limb_development,
    region_fact,
)


def _snap(**over):
    """A body-composition snapshot shaped like build_body_composition_snapshot()."""
    today = date(2026, 7, 13)
    base = {
        "latest_date": today, "previous_date": today - timedelta(days=30), "days_between": 30,
        "latest": {}, "previous": {}, "units": {}, "delta": {}, "delta_pct": {},
        "latest_date_per_metric": {}, "previous_date_per_metric": {},
    }
    base.update(over)
    return base


class RegionFactStateTests(SimpleTestCase):
    def test_missing_when_not_tracked(self):
        f = region_fact(_snap(), "waist")
        self.assertEqual(f["state"], "missing")
        self.assertIsNone(f["current"])

    def test_current_only_when_no_prior(self):
        s = _snap(latest={"waist": 34.0}, previous={"waist": None}, delta={"waist": None},
                  units={"waist": "in"},
                  latest_date_per_metric={"waist": date(2026, 7, 10)})
        f = region_fact(s, "waist")
        self.assertEqual(f["state"], "current_only")
        self.assertEqual(f["current"], 34.0)
        self.assertIsNone(f["comparison"])

    def test_changed_when_delta_clears_noise(self):
        s = _snap(latest={"waist": 34.0}, previous={"waist": 36.0}, delta={"waist": -2.0},
                  delta_pct={"waist": -5.6}, units={"waist": "in"},
                  latest_date_per_metric={"waist": date(2026, 7, 10)},
                  previous_date_per_metric={"waist": date(2026, 6, 10)})
        f = region_fact(s, "waist")
        self.assertEqual(f["state"], "changed")
        self.assertEqual(f["direction"], "down")
        self.assertEqual(f["magnitude"], 2.0)
        self.assertFalse(f["low_confidence"])

    def test_stable_when_delta_within_noise(self):
        # waist noise threshold is 0.25; a 0.1" move is not a real change.
        s = _snap(latest={"waist": 34.0}, previous={"waist": 34.1}, delta={"waist": -0.1},
                  units={"waist": "in"},
                  latest_date_per_metric={"waist": date(2026, 7, 10)},
                  previous_date_per_metric={"waist": date(2026, 6, 10)})
        self.assertEqual(region_fact(s, "waist")["state"], "stable")

    def test_stale_flag_when_latest_is_old(self):
        old = date(2026, 1, 1)  # > 60 days before today (2026-07-13)
        s = _snap(latest={"waist": 34.0}, previous={"waist": None}, delta={"waist": None},
                  units={"waist": "in"}, latest_date_per_metric={"waist": old})
        f = region_fact(s, "waist")
        self.assertTrue(f["stale"])
        self.assertEqual(f["state"], "current_only")

    def test_low_confidence_when_comparison_is_stale(self):
        old = date(2026, 1, 1)
        s = _snap(latest={"waist": 34.0}, previous={"waist": 36.0}, delta={"waist": -2.0},
                  units={"waist": "in"},
                  latest_date_per_metric={"waist": old},
                  previous_date_per_metric={"waist": date(2025, 12, 1)})
        f = region_fact(s, "waist")
        self.assertEqual(f["state"], "changed")
        self.assertTrue(f["low_confidence"])


class BodyShapeTests(SimpleTestCase):
    def test_empty_snapshot_is_all_missing(self):
        bs = build_body_shape(None)
        self.assertFalse(bs["has_any"])
        self.assertEqual(bs["counts"]["missing"], 5)

    def test_regions_in_silhouette_order(self):
        bs = build_body_shape(_snap(latest={"neck": 15.0}, units={"neck": "in"},
                                    latest_date_per_metric={"neck": date(2026, 7, 10)}))
        self.assertEqual([r["metric"] for r in bs["regions"]],
                         ["neck", "shoulders", "chest", "waist", "hips"])

    def test_largest_change_is_max_absolute_delta(self):
        # Factual: the region that moved most by |delta|, NOT a verdict about "improvement".
        s = _snap(
            latest={"chest": 42.0, "waist": 34.0, "hips": 40.0},
            previous={"chest": 42.6, "waist": 36.0, "hips": 41.0},
            delta={"chest": -0.6, "waist": -2.0, "hips": -1.0},
            units={"chest": "in", "waist": "in", "hips": "in"},
            latest_date_per_metric={"chest": date(2026, 7, 10), "waist": date(2026, 7, 10),
                                    "hips": date(2026, 7, 10)},
            previous_date_per_metric={"chest": date(2026, 6, 10), "waist": date(2026, 6, 10),
                                      "hips": date(2026, 6, 10)},
        )
        lc = build_body_shape(s)["largest_change"]
        self.assertEqual(lc["metric"], "waist")
        self.assertEqual(lc["magnitude"], 2.0)
        self.assertEqual(lc["direction"], "down")

    def test_largest_change_none_when_nothing_changed(self):
        s = _snap(latest={"waist": 34.0}, previous={"waist": None}, delta={"waist": None},
                  units={"waist": "in"}, latest_date_per_metric={"waist": date(2026, 7, 10)})
        self.assertIsNone(build_body_shape(s)["largest_change"])

    def test_mixed_states_reported_honestly(self):
        s = _snap(
            latest={"neck": 15.0, "chest": 42.0, "waist": 34.0},
            previous={"chest": 42.1, "waist": 36.0},
            delta={"chest": -0.1, "waist": -2.0},
            units={"neck": "in", "chest": "in", "waist": "in"},
            latest_date_per_metric={"neck": date(2026, 7, 10), "chest": date(2026, 7, 10),
                                    "waist": date(2026, 7, 10)},
            previous_date_per_metric={"chest": date(2026, 6, 10), "waist": date(2026, 6, 10)},
        )
        bs = build_body_shape(s)
        by = {r["metric"]: r["state"] for r in bs["regions"]}
        self.assertEqual(by["neck"], "current_only")
        self.assertEqual(by["chest"], "stable")
        self.assertEqual(by["waist"], "changed")
        self.assertEqual(by["shoulders"], "missing")
        self.assertTrue(bs["has_comparison"])


class LimbDevelopmentTests(SimpleTestCase):
    def test_asymmetry_flagged_when_significant(self):
        s = _snap(
            latest={"calf_left": 17.33, "calf_right": 16.33},
            units={"calf_left": "in", "calf_right": "in"},
            latest_date_per_metric={"calf_left": date(2026, 7, 10),
                                    "calf_right": date(2026, 7, 10)},
        )
        ld = build_limb_development(s)
        calf = next(l for l in ld["limbs"] if l["key"] == "calf")
        self.assertEqual(calf["asymmetry"]["diff"], 1.0)
        self.assertEqual(calf["asymmetry"]["larger"], "left")
        self.assertTrue(calf["asymmetry"]["significant"])

    def test_balanced_not_flagged(self):
        s = _snap(latest={"forearm_left": 12.25, "forearm_right": 12.25},
                  units={"forearm_left": "in", "forearm_right": "in"},
                  latest_date_per_metric={"forearm_left": date(2026, 7, 10),
                                          "forearm_right": date(2026, 7, 10)})
        ld = build_limb_development(s)
        fore = next(l for l in ld["limbs"] if l["key"] == "forearm")
        self.assertFalse(fore["asymmetry"]["significant"])

    def test_left_right_different_dates_flagged(self):
        s = _snap(latest={"arm_left": 17.0, "arm_right": 18.0},
                  units={"arm_left": "in", "arm_right": "in"},
                  latest_date_per_metric={"arm_left": date(2026, 7, 10),
                                          "arm_right": date(2026, 7, 1)})
        ld = build_limb_development(s)
        arm = next(l for l in ld["limbs"] if l["key"] == "arm")
        self.assertTrue(arm["asymmetry"]["different_dates"])

    def test_empty_snapshot(self):
        ld = build_limb_development(None)
        self.assertFalse(ld["has_any"])
        self.assertEqual(ld["limbs"], [])
