"""Tests for the HealthBriefing thresholds registry."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

from django.test import SimpleTestCase

from apps.core.health_briefing.thresholds import (
    DEFAULT_PROFILE_KEY,
    ThresholdProfile,
    get_profile,
    profile_keys,
)


class ProfileLookupTests(SimpleTestCase):
    def test_default_key_constant(self):
        self.assertEqual(DEFAULT_PROFILE_KEY, "default")

    def test_get_default_profile(self):
        p = get_profile()
        self.assertIsInstance(p, ThresholdProfile)

    def test_get_explicit_default(self):
        self.assertIs(get_profile(), get_profile(DEFAULT_PROFILE_KEY))

    def test_unknown_key_falls_back_to_default(self):
        # Phase 6 will add per-user keys; before then, fallback must be
        # the default profile, not None or raise.
        fallback = get_profile("nonexistent_profile_t1d")
        self.assertIs(fallback, get_profile())

    def test_profile_keys_includes_default(self):
        self.assertIn(DEFAULT_PROFILE_KEY, profile_keys())

    def test_profile_keys_v1_has_only_default(self):
        # Locked Phase 0: v1 ships only the default key. Adding more
        # before Phase 6 would silently change composer behavior.
        self.assertEqual(profile_keys(), ("default",))


class DefaultProfileValuesTests(SimpleTestCase):
    """Pin the v1 numeric values so unintended drift fails loudly."""

    def setUp(self):
        self.p = get_profile()

    def test_glucose_tir_band_is_ada_default(self):
        self.assertEqual(self.p.glucose_targets.tir_low_mg_dl, 70)
        self.assertEqual(self.p.glucose_targets.tir_high_mg_dl, 180)

    def test_acute_glucose_cut_points(self):
        a = self.p.acute_glucose
        self.assertEqual(a.critical_low_mg_dl, 54)
        self.assertEqual(a.low_mg_dl, 70)
        self.assertEqual(a.high_mg_dl, 250)
        self.assertEqual(a.critical_high_mg_dl, 300)

    def test_acute_glucose_ordering_is_sane(self):
        a = self.p.acute_glucose
        self.assertLess(a.critical_low_mg_dl, a.low_mg_dl)
        self.assertLess(a.low_mg_dl, a.high_mg_dl)
        self.assertLess(a.high_mg_dl, a.critical_high_mg_dl)

    def test_glucose_tir_inside_acute_band(self):
        # TIR low/high must sit inside the acute band; otherwise
        # in-range readings would also count as acute alerts.
        a = self.p.acute_glucose
        t = self.p.glucose_targets
        self.assertGreaterEqual(t.tir_low_mg_dl, a.low_mg_dl)
        self.assertLessEqual(t.tir_high_mg_dl, a.high_mg_dl)

    def test_staleness_horizons(self):
        s = self.p.staleness_seconds
        self.assertEqual(s.latest_glucose, 6 * 3600)
        self.assertEqual(s.weight_current, 7 * 86400)
        self.assertEqual(s.hba1c, 120 * 86400)

    def test_staleness_ordering_is_sane(self):
        # CGM should expire faster than weight, which expires faster
        # than HbA1c. These are clinical facts; flag drift.
        s = self.p.staleness_seconds
        self.assertLess(s.latest_glucose, s.weight_current)
        self.assertLess(s.weight_current, s.hba1c)

    def test_trend_magnitude_ordering(self):
        t = self.p.trend_magnitude
        self.assertLess(t.flat_max, t.moderate_min)
        self.assertLess(t.moderate_min, t.strong_min)

    def test_confidence_floors_in_unit_interval(self):
        c = self.p.confidence_floors
        for value in (c.single_source_cap, c.narration_floor, c.sufficient_data_floor):
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)

    def test_sufficient_data_floor_below_narration_floor(self):
        # Narration requires more confidence than mere sufficiency.
        c = self.p.confidence_floors
        self.assertLess(c.sufficient_data_floor, c.narration_floor)

    def test_coverage_minimums_scale_with_window(self):
        cov = self.p.coverage_minimums
        self.assertLess(cov.glucose_min_readings_7d, cov.glucose_min_readings_30d)
        self.assertLess(cov.glucose_min_readings_30d, cov.glucose_min_readings_90d)


class ImmutabilityTests(SimpleTestCase):
    def test_profile_is_frozen(self):
        p = get_profile()
        with self.assertRaises(FrozenInstanceError):
            p.glucose_targets = None  # type: ignore[misc]

    def test_nested_dataclass_is_frozen(self):
        p = get_profile()
        with self.assertRaises(FrozenInstanceError):
            p.glucose_targets.tir_low_mg_dl = 0  # type: ignore[misc]
