"""
Physical Intelligence V2 — Tests.

Tests for:
    - Body Composition Signal (compute_body_composition_trend)
    - Outcome Validation (validate_outcome)
    - Conflict Detection (detect_conflicts)
    - Physical Decision (compute_physical_decision)

Covers the 5 canonical scenarios:
    1. Successful fat loss
    2. Fat loss stall despite compliance
    3. Creatine false weight gain
    4. Overtraining
    5. Recomposition success

Location: apps/health/tests/test_physical_intelligence_v2.py
"""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.health.models import (
    BloodPressureEntry,
    BodyCompositionEntry,
    DailyHealthSummary,
    GlucoseEntry,
    HeartRateEntry,
    TransformationProtocol,
    WeightEntry,
)
from apps.health.services.body_composition_signal import (
    compute_body_composition_trend,
    _measurement_trend,
    _derive_verdict,
)
from apps.health.services.conflict_detection import (
    apply_conflict_corrections,
    detect_conflicts,
)
from apps.health.services.outcome_validation import validate_outcome
from apps.users.models import TermsAcceptance

User = get_user_model()


def create_test_user(email="phys_intel@example.com", password="testpass123"):
    """Create a test user with onboarding + terms completed."""
    user = User.objects.create_user(email=email, password=password)
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


# =========================================================================
# Body Composition Signal Tests
# =========================================================================


class TestBodyCompositionSignal(TestCase):
    """Tests for compute_body_composition_trend()."""

    def setUp(self):
        self.user = create_test_user()
        self.today = date.today()

    def _create_summaries(self, days=14, weight_start=200, weight_delta=-1.0,
                          fat_loss_quality="GOOD", muscle_preservation="HIGH_QUALITY",
                          plateau_status="", recomp_flag=False,
                          muscle_loss_risk_score=20, muscle_loss_risk_level="LOW",
                          fat_loss_speed_pct=None, fat_loss_speed_label="",
                          recovery_score=70, fat_loss_phase="",
                          plateau_risk_label=""):
        """Helper to create DailyHealthSummary entries."""
        for i in range(days):
            d = self.today - timedelta(days=i)
            weight = Decimal(str(weight_start + (weight_delta * i / 7)))
            kwargs = {
                "user": self.user,
                "summary_date": d,
                "baseline_ready": True,
                "weight": weight,
                "fat_loss_quality_label": fat_loss_quality,
                "muscle_preservation_status": muscle_preservation,
                "plateau_status": plateau_status,
                "recomposition_flag_14d": recomp_flag,
                "muscle_loss_risk_score": muscle_loss_risk_score,
                "muscle_loss_risk_level": muscle_loss_risk_level,
                "fat_loss_speed_label": fat_loss_speed_label,
                "recovery_score": recovery_score,
                "fat_loss_phase": fat_loss_phase,
                "plateau_risk_label": plateau_risk_label,
            }
            # Only include nullable decimal fields if they have values
            if fat_loss_speed_pct is not None:
                kwargs["fat_loss_speed_pct_per_week"] = fat_loss_speed_pct
            DailyHealthSummary.objects.create(**kwargs)

    def _create_waist_measurements(self, count=3, start_value=36.0, delta=-0.5):
        """Helper to create waist BodyCompositionEntry records."""
        for i in range(count):
            d = self.today - timedelta(days=i * 7)
            BodyCompositionEntry.objects.create(
                user=self.user,
                metric_name="waist",
                value=Decimal(str(start_value + (delta * i))),
                unit="in",
                measurement_date=d,
                source="manual",
            )

    def test_insufficient_data_no_summaries(self):
        """No DailyHealthSummary → insufficient data."""
        result = compute_body_composition_trend(self.user, self.today)
        self.assertEqual(result["fat_loss_status"], "not_confirmed")
        self.assertEqual(result["confidence"], "low")
        self.assertEqual(result["verdict"], "no_data")

    def test_insufficient_data_no_baseline(self):
        """DailyHealthSummary exists but baseline not ready."""
        DailyHealthSummary.objects.create(
            user=self.user,
            summary_date=self.today,
            baseline_ready=False,
            weight=Decimal("200"),
        )
        result = compute_body_composition_trend(self.user, self.today)
        self.assertEqual(result["verdict"], "no_data")

    def test_fat_loss_confirmed(self):
        """Weight down + waist down + DHS good → confirmed."""
        self._create_summaries(
            days=14, weight_start=200, weight_delta=-2.0,
            fat_loss_quality="GOOD",
        )
        self._create_waist_measurements(count=3, start_value=34.0, delta=0.5)
        # Note: waist entries are created newest first, with delta going backward
        # So waist[0]=34.0 (today), waist[1]=34.5 (7d ago), waist[2]=35.0 (14d ago)
        # This means waist is DECREASING over time (good)

        result = compute_body_composition_trend(self.user, self.today)
        self.assertEqual(result["fat_loss_status"], "confirmed")
        self.assertIn("dhs_fat_loss_good", result["fat_loss_evidence"])

    def test_fat_loss_reversed(self):
        """Weight up + waist up + DHS mixed → reversed."""
        self._create_summaries(
            days=14, weight_start=195, weight_delta=2.0,
            fat_loss_quality="MIXED",
        )
        # Waist increasing
        self._create_waist_measurements(count=3, start_value=36.0, delta=-0.5)
        # waist[0]=36.0 (today), waist[1]=35.5 (7d ago) → increasing

        result = compute_body_composition_trend(self.user, self.today)
        self.assertIn(result["fat_loss_status"], ("not_confirmed", "reversed"))

    def test_muscle_likely_when_recomp_flag(self):
        """Recomposition flag + high preservation → muscle likely."""
        self._create_summaries(
            days=14, fat_loss_quality="GOOD",
            muscle_preservation="HIGH_QUALITY",
            recomp_flag=True, muscle_loss_risk_score=15,
        )
        result = compute_body_composition_trend(self.user, self.today)
        self.assertEqual(result["muscle_gain_status"], "likely")
        self.assertIn("recomp_flag", result["muscle_evidence"])

    def test_muscle_unlikely_when_high_risk(self):
        """High muscle loss risk → muscle unlikely."""
        self._create_summaries(
            days=14, fat_loss_quality="MUSCLE_LOSS_RISK",
            muscle_preservation="MUSCLE_RISK",
            muscle_loss_risk_score=80, muscle_loss_risk_level="HIGH",
        )
        result = compute_body_composition_trend(self.user, self.today)
        self.assertEqual(result["muscle_gain_status"], "unlikely")

    def test_recomposition_detected(self):
        """Fat loss confirmed + muscle likely → recomposition."""
        self._create_summaries(
            days=14, weight_start=192, weight_delta=0,
            fat_loss_quality="GOOD",
            muscle_preservation="HIGH_QUALITY",
            recomp_flag=True, muscle_loss_risk_score=10,
        )
        self._create_waist_measurements(count=3, start_value=33.5, delta=0.5)

        result = compute_body_composition_trend(self.user, self.today)
        self.assertTrue(result["recomposition_status"])
        self.assertEqual(result["verdict"], "recomposition")

    def test_verdict_matrix(self):
        """Test the verdict derivation for key combinations."""
        self.assertEqual(_derive_verdict("confirmed", "likely"), "recomposition")
        self.assertEqual(_derive_verdict("confirmed", "unclear"), "effective_cut")
        self.assertEqual(_derive_verdict("confirmed", "unlikely"), "cut_with_muscle_loss")
        self.assertEqual(_derive_verdict("not_confirmed", "likely"), "effective_bulk")
        self.assertEqual(_derive_verdict("not_confirmed", "unclear"), "spinning_wheels")
        self.assertEqual(_derive_verdict("reversed", "unlikely"), "regression")

    def test_plateau_detection_confirmed(self):
        """Flat weight + DHS plateau → confirmed plateau."""
        self._create_summaries(
            days=28, weight_start=186, weight_delta=0,
            fat_loss_quality="MIXED",
            plateau_status="TRUE_PLATEAU",
        )
        result = compute_body_composition_trend(self.user, self.today)
        self.assertEqual(result["plateau_status"], "confirmed")
        self.assertEqual(result["plateau_type"], "true_plateau")

    def test_confidence_high_with_multiple_sources(self):
        """High confidence when weight + waist + body fat all present."""
        self._create_summaries(days=14, fat_loss_quality="GOOD")
        self._create_waist_measurements(count=3)
        # Muscle measurements
        for metric in ["chest", "arm_right"]:
            for i in range(2):
                BodyCompositionEntry.objects.create(
                    user=self.user,
                    metric_name=metric,
                    value=Decimal("42.0"),
                    unit="in",
                    measurement_date=self.today - timedelta(days=i * 14),
                    source="manual",
                )
        result = compute_body_composition_trend(self.user, self.today)
        self.assertEqual(result["confidence"], "high")

    def test_confidence_low_with_only_weight(self):
        """Low confidence when only weight data available."""
        self._create_summaries(
            days=14, fat_loss_quality="INSUFFICIENT_DATA",
        )
        result = compute_body_composition_trend(self.user, self.today)
        self.assertIn(result["confidence"], ("low", "medium"))


class TestMeasurementTrend(TestCase):
    """Tests for the measurement trend utility."""

    def setUp(self):
        self.user = create_test_user(email="trend@example.com")
        self.today = date.today()

    def test_no_data_returns_not_reliable(self):
        delta, ok = _measurement_trend(self.user, "waist", self.today)
        self.assertFalse(ok)
        self.assertEqual(delta, 0.0)

    def test_single_entry_not_reliable(self):
        BodyCompositionEntry.objects.create(
            user=self.user, metric_name="waist",
            value=Decimal("35.0"), unit="in",
            measurement_date=self.today, source="manual",
        )
        delta, ok = _measurement_trend(self.user, "waist", self.today)
        self.assertFalse(ok)

    def test_two_entries_reliable(self):
        for i, val in enumerate([36.0, 35.0]):
            BodyCompositionEntry.objects.create(
                user=self.user, metric_name="waist",
                value=Decimal(str(val)), unit="in",
                measurement_date=self.today - timedelta(days=14 - i * 14),
                source="manual",
            )
        delta, ok = _measurement_trend(self.user, "waist", self.today)
        self.assertTrue(ok)
        self.assertAlmostEqual(delta, -1.0, places=1)

    def test_outlier_rejection(self):
        """Median filter rejects outlier measurements."""
        dates_vals = [
            (self.today - timedelta(days=21), 35.0),
            (self.today - timedelta(days=14), 34.5),
            (self.today - timedelta(days=7), 50.0),  # Outlier
            (self.today, 34.0),
        ]
        for d, v in dates_vals:
            BodyCompositionEntry.objects.create(
                user=self.user, metric_name="waist",
                value=Decimal(str(v)), unit="in",
                measurement_date=d, source="manual",
            )
        delta, ok = _measurement_trend(self.user, "waist", self.today)
        self.assertTrue(ok)
        # Should be about -1.0 (35.0 → 34.0), not influenced by 50.0 outlier
        self.assertLess(delta, 0)
        self.assertGreater(delta, -2.0)


# =========================================================================
# Outcome Validation Tests
# =========================================================================


class TestOutcomeValidation(TestCase):
    """Tests for validate_outcome()."""

    def setUp(self):
        self.user = create_test_user(email="outcome@example.com")

    def test_cut_working(self):
        """Cut with confirmed fat loss → working."""
        trend = {
            "fat_loss_status": "confirmed",
            "muscle_gain_status": "unclear",
            "verdict": "effective_cut",
            "fat_loss_evidence": ["weight_down", "waist_down"],
            "muscle_evidence": [],
            "fat_loss_rate_lbs_per_week": -1.2,
        }
        result = validate_outcome(self.user, trend, "cut")
        self.assertEqual(result["outcome_status"], "working")

    def test_cut_not_working(self):
        """Cut with spinning wheels → not working."""
        trend = {
            "fat_loss_status": "not_confirmed",
            "muscle_gain_status": "unclear",
            "verdict": "spinning_wheels",
            "fat_loss_evidence": ["weight_flat"],
            "muscle_evidence": [],
            "fat_loss_rate_lbs_per_week": -0.1,
        }
        result = validate_outcome(self.user, trend, "cut")
        self.assertEqual(result["outcome_status"], "not_working")

    def test_cut_partial_with_muscle_loss(self):
        """Cut losing fat but also muscle → partial."""
        trend = {
            "fat_loss_status": "confirmed",
            "muscle_gain_status": "unlikely",
            "verdict": "cut_with_muscle_loss",
            "fat_loss_evidence": ["weight_down"],
            "muscle_evidence": ["high_risk_score"],
            "fat_loss_rate_lbs_per_week": -2.0,
        }
        result = validate_outcome(self.user, trend, "cut")
        self.assertEqual(result["outcome_status"], "partial")

    def test_bulk_working(self):
        """Bulk with muscle gain → working."""
        trend = {
            "fat_loss_status": "reversed",
            "muscle_gain_status": "likely",
            "verdict": "effective_bulk",
            "fat_loss_evidence": [],
            "muscle_evidence": ["measurements_growing"],
            "weight_trend": 2.0,
            "fat_loss_rate_lbs_per_week": None,
        }
        result = validate_outcome(self.user, trend, "bulk")
        self.assertEqual(result["outcome_status"], "working")

    def test_recomp_working(self):
        """Recomp with both dimensions improving → working."""
        trend = {
            "fat_loss_status": "confirmed",
            "muscle_gain_status": "likely",
            "recomposition_status": True,
            "verdict": "recomposition",
            "fat_loss_evidence": ["waist_down"],
            "muscle_evidence": ["recomp_flag"],
            "fat_loss_rate_lbs_per_week": None,
        }
        result = validate_outcome(self.user, trend, "recomposition")
        self.assertEqual(result["outcome_status"], "working")

    def test_maintenance_stable_is_working(self):
        """Maintenance with no changes → working (spinning wheels IS success)."""
        trend = {
            "fat_loss_status": "not_confirmed",
            "muscle_gain_status": "unclear",
            "verdict": "spinning_wheels",
            "fat_loss_evidence": [],
            "muscle_evidence": [],
            "fat_loss_rate_lbs_per_week": 0,
        }
        result = validate_outcome(self.user, trend, "maintenance")
        self.assertEqual(result["outcome_status"], "working")

    def test_no_protocol_returns_unknown(self):
        """No protocol type → unknown outcome."""
        trend = {"verdict": "effective_cut", "fat_loss_evidence": [], "muscle_evidence": []}
        result = validate_outcome(self.user, trend, None)
        self.assertEqual(result["outcome_status"], "unknown")

    def test_trajectory_with_protocol(self):
        """Trajectory computed when protocol has goal weight and target date."""
        protocol = TransformationProtocol.objects.create(
            user=self.user,
            name="Test Cut",
            protocol_type="cut",
            start_date=date.today() - timedelta(days=30),
            target_end_date=date.today() + timedelta(days=60),
            goal_weight=Decimal("185"),
            goal_weight_unit="lb",
            is_active=True,
        )
        WeightEntry.objects.create(
            user=self.user, value=Decimal("195"),
            unit="lb", recorded_at=timezone.now(),
        )
        trend = {
            "fat_loss_status": "confirmed",
            "muscle_gain_status": "unclear",
            "verdict": "effective_cut",
            "fat_loss_evidence": [],
            "muscle_evidence": [],
            "fat_loss_rate_lbs_per_week": -1.5,
        }
        result = validate_outcome(self.user, trend, "cut")
        self.assertIn(result["goal_trajectory"], ("ahead", "on_pace", "behind", "off_track", None))


# =========================================================================
# Conflict Detection Tests
# =========================================================================


class TestConflictDetection(TestCase):
    """Tests for detect_conflicts()."""

    def setUp(self):
        self.user = create_test_user(email="conflict@example.com")

    def test_compliant_but_stalled(self):
        """High compliance + not_working + plateau → compliant_but_stalled."""
        signals = {
            "nutrition_score": 85,
            "training_score": 90,
            "recovery_score": 70,
        }
        trend = {
            "verdict": "spinning_wheels",
            "plateau_status": "confirmed",
            "fat_loss_status": "not_confirmed",
            "muscle_gain_status": "unclear",
        }
        outcome = {"outcome_status": "not_working"}

        conflicts = detect_conflicts(self.user, signals, trend, outcome)
        types = [c["type"] for c in conflicts]
        self.assertIn("compliant_but_stalled", types)

    def test_compliant_but_stalled_not_triggered_when_low_compliance(self):
        """Low compliance + not_working → no compliant_but_stalled."""
        signals = {
            "nutrition_score": 50,
            "training_score": 90,
            "recovery_score": 70,
        }
        trend = {
            "verdict": "spinning_wheels",
            "plateau_status": "confirmed",
        }
        outcome = {"outcome_status": "not_working"}

        conflicts = detect_conflicts(self.user, signals, trend, outcome)
        types = [c["type"] for c in conflicts]
        self.assertNotIn("compliant_but_stalled", types)

    def test_overtraining_detected(self):
        """High training + low recovery + poor muscle → overtraining."""
        signals = {
            "nutrition_score": 85,
            "training_score": 95,
            "recovery_score": 30,
        }
        trend = {
            "muscle_gain_status": "unlikely",
            "verdict": "regression",
        }
        outcome = {"outcome_status": "not_working"}

        conflicts = detect_conflicts(self.user, signals, trend, outcome)
        types = [c["type"] for c in conflicts]
        self.assertIn("overtraining", types)
        # Overtraining should be severity=critical, sorted first
        self.assertEqual(conflicts[0]["type"], "overtraining")

    def test_recomp_hidden_positive(self):
        """Recomposition detected → positive conflict."""
        signals = {"nutrition_score": 85, "training_score": 85, "recovery_score": 75}
        trend = {
            "recomposition_status": True,
            "verdict": "recomposition",
            "muscle_gain_status": "likely",
        }
        outcome = {"outcome_status": "working"}

        conflicts = detect_conflicts(self.user, signals, trend, outcome)
        positive = [c for c in conflicts if c.get("positive")]
        self.assertTrue(len(positive) > 0)
        self.assertEqual(positive[0]["type"], "recomp_hidden")

    def test_sleep_sabotage(self):
        """Good nutrition/training + bad sleep + low recovery."""
        signals = {
            "nutrition_score": 80,
            "training_score": 80,
            "recovery_score": 40,
            "sleep_hours": 5.5,
        }
        trend = {"muscle_gain_status": "unclear", "verdict": "spinning_wheels"}
        outcome = {"outcome_status": "not_working"}

        conflicts = detect_conflicts(self.user, signals, trend, outcome)
        types = [c["type"] for c in conflicts]
        self.assertIn("sleep_sabotage", types)

    def test_max_two_conflicts(self):
        """Never more than 2 conflicts returned."""
        signals = {
            "nutrition_score": 85, "training_score": 95,
            "recovery_score": 30, "sleep_hours": 5.0,
        }
        trend = {
            "recomposition_status": True, "verdict": "recomposition",
            "muscle_gain_status": "unlikely",
            "plateau_status": "confirmed",
            "fat_loss_status": "not_confirmed",
        }
        outcome = {"outcome_status": "not_working"}

        conflicts = detect_conflicts(self.user, signals, trend, outcome)
        self.assertLessEqual(len(conflicts), 2)

    def test_conflict_correction_creatine(self):
        """Positive creatine conflict corrects outcome from not_working to working."""
        outcome = {
            "outcome_status": "not_working",
            "outcome_evidence": ["weight_up"],
        }
        conflicts = [
            {
                "type": "creatine_weight_gain",
                "positive": True,
                "description": "test",
                "resolution": "test",
                "severity": "medium",
            }
        ]
        corrected = apply_conflict_corrections(outcome, conflicts)
        self.assertEqual(corrected["outcome_status"], "working")
        self.assertIn("creatine_masking_scale", corrected["outcome_evidence"])

    def test_conflict_correction_recomp(self):
        """Positive recomp conflict corrects outcome."""
        outcome = {
            "outcome_status": "not_working",
            "outcome_evidence": [],
        }
        conflicts = [
            {
                "type": "recomp_hidden",
                "positive": True,
                "description": "test",
                "resolution": "test",
                "severity": "low",
            }
        ]
        corrected = apply_conflict_corrections(outcome, conflicts)
        self.assertEqual(corrected["outcome_status"], "working")


# =========================================================================
# Physical Decision Integration Tests
# =========================================================================


class TestPhysicalDecision(TestCase):
    """Tests for compute_physical_decision() — the full pipeline."""

    def setUp(self):
        self.user = create_test_user(email="decision@example.com")
        self.today = date.today()

    def _create_baseline(self, days=14, weight=190, recovery=70,
                         fat_loss_quality="GOOD", muscle_preservation="HIGH_QUALITY",
                         muscle_loss_risk_level="LOW", muscle_loss_risk_score=20,
                         fat_loss_speed_label="", plateau_status=""):
        """Create baseline DailyHealthSummary data."""
        for i in range(days):
            d = self.today - timedelta(days=i)
            DailyHealthSummary.objects.create(
                user=self.user,
                summary_date=d,
                baseline_ready=True,
                weight=Decimal(str(weight)),
                recovery_score=recovery,
                fat_loss_quality_label=fat_loss_quality,
                muscle_preservation_status=muscle_preservation,
                muscle_loss_risk_level=muscle_loss_risk_level,
                muscle_loss_risk_score=muscle_loss_risk_score,
                fat_loss_speed_label=fat_loss_speed_label,
                plateau_status=plateau_status,
                fat_loss_phase="",
                plateau_risk_label="",
                sleep_hours=Decimal("7.5"),
                workout_count=1,
            )

    def test_fallback_on_no_data(self):
        """No data → fallback decision."""
        from apps.health.services.physical_decision import compute_physical_decision
        result = compute_physical_decision(self.user, self.today)
        self.assertEqual(result["decision_type"], "on_track")
        self.assertIn("narrative", result)

    def test_health_risk_muscle_loss(self):
        """HIGH muscle loss risk → health_risk decision."""
        from apps.health.services.physical_decision import compute_physical_decision
        self._create_baseline(
            muscle_loss_risk_level="HIGH",
            muscle_loss_risk_score=85,
            fat_loss_quality="MUSCLE_LOSS_RISK",
        )
        result = compute_physical_decision(self.user, self.today)
        self.assertEqual(result["decision_type"], "health_risk")
        self.assertEqual(result["primary_issue"], "muscle_loss_risk")
        self.assertEqual(result["urgency"], "immediate")

    def test_health_risk_severe_fatigue(self):
        """Recovery < 30 → health_risk."""
        from apps.health.services.physical_decision import compute_physical_decision
        self._create_baseline(recovery=25)
        result = compute_physical_decision(self.user, self.today)
        self.assertEqual(result["decision_type"], "health_risk")
        self.assertEqual(result["primary_issue"], "severe_fatigue")

    def test_health_risk_too_fast(self):
        """Fat loss speed TOO_FAST → health_risk."""
        from apps.health.services.physical_decision import compute_physical_decision
        self._create_baseline(fat_loss_speed_label="TOO_FAST")
        result = compute_physical_decision(self.user, self.today)
        self.assertEqual(result["decision_type"], "health_risk")
        self.assertEqual(result["primary_issue"], "extreme_deficit")

    @patch("apps.health.services.physical_decision._gather_signals")
    def test_on_track_when_everything_good(self, mock_signals):
        """Good metrics across the board → on_track."""
        from apps.health.services.physical_decision import compute_physical_decision
        mock_signals.return_value = {
            "nutrition_score": 85,
            "protein_pct": 90,
            "training_score": 85,
            "recovery_score": 75,
            "hydration_pct": 80,
            "sleep_hours": 7.5,
        }
        self._create_baseline()
        result = compute_physical_decision(self.user, self.today)
        self.assertEqual(result["decision_type"], "on_track")

    @patch("apps.health.services.physical_decision._gather_signals")
    def test_nutrition_gap_low_protein(self, mock_signals):
        """Low protein → nutrition decision."""
        from apps.health.services.physical_decision import compute_physical_decision
        mock_signals.return_value = {
            "nutrition_score": 70,
            "protein_pct": 55,
            "training_score": 85,
            "recovery_score": 75,
            "hydration_pct": 80,
            "sleep_hours": 7.5,
        }
        self._create_baseline()
        result = compute_physical_decision(self.user, self.today)
        self.assertEqual(result["decision_type"], "nutrition")
        self.assertEqual(result["primary_issue"], "low_protein")

    @patch("apps.health.services.physical_decision._gather_signals")
    def test_outcome_failure_when_stalled_with_compliance(self, mock_signals):
        """Plateau + good compliance → outcome_failure."""
        from apps.health.services.physical_decision import compute_physical_decision
        mock_signals.return_value = {
            "nutrition_score": 85,
            "protein_pct": 85,
            "training_score": 85,
            "recovery_score": 70,
            "hydration_pct": 75,
            "sleep_hours": 7.0,
        }
        self._create_baseline(plateau_status="TRUE_PLATEAU", fat_loss_quality="MIXED")

        # Need a protocol for outcome validation
        TransformationProtocol.objects.create(
            user=self.user,
            name="Test Cut",
            protocol_type="cut",
            start_date=self.today - timedelta(days=60),
            target_end_date=self.today + timedelta(days=30),
            is_active=True,
        )

        result = compute_physical_decision(self.user, self.today)
        self.assertEqual(result["decision_type"], "outcome_failure")
        self.assertEqual(result["primary_issue"], "protocol_stalled")

    def test_decision_has_all_required_fields(self):
        """Decision dict has all expected keys."""
        from apps.health.services.physical_decision import compute_physical_decision
        self._create_baseline()
        result = compute_physical_decision(self.user, self.today)

        required_keys = [
            "decision_type", "primary_issue", "summary", "urgency",
            "impact", "recommended_action", "action_type",
            "outcome_status", "outcome_evidence",
            "goal_trajectory", "trajectory_detail",
            "body_composition", "conflicts", "has_positive_conflict",
            "confidence", "protocol_type",
            "persistence_days", "messaging_phase",
            "impact_statement", "outcome_risk",
            "narrative",
        ]
        for key in required_keys:
            self.assertIn(key, result, f"Missing key: {key}")

    def test_narrative_not_empty(self):
        """Narrative should always be populated."""
        from apps.health.services.physical_decision import compute_physical_decision
        self._create_baseline()
        result = compute_physical_decision(self.user, self.today)
        self.assertTrue(len(result["narrative"]) > 10)


# =========================================================================
# Full Scenario Tests
# =========================================================================


class TestScenarioSuccessfulFatLoss(TestCase):
    """Scenario 1: Successful fat loss during a cut."""

    def setUp(self):
        self.user = create_test_user(email="success@example.com")
        self.today = date.today()

    @patch("apps.health.services.physical_decision._gather_signals")
    def test_successful_cut(self, mock_signals):
        """Everything working: fat loss confirmed, muscle preserved, on track."""
        from apps.health.services.physical_decision import compute_physical_decision

        mock_signals.return_value = {
            "nutrition_score": 87, "protein_pct": 92,
            "training_score": 85, "recovery_score": 74,
            "hydration_pct": 78, "sleep_hours": 7.2,
        }

        # Create 14 days of declining weight
        for i in range(14):
            d = self.today - timedelta(days=i)
            DailyHealthSummary.objects.create(
                user=self.user, summary_date=d, baseline_ready=True,
                weight=Decimal(str(188.4 + (i * 0.15))),  # Weight was higher in past
                recovery_score=74,
                fat_loss_quality_label="GOOD",
                muscle_preservation_status="HIGH_QUALITY",
                muscle_loss_risk_level="LOW", muscle_loss_risk_score=15,
                fat_loss_speed_pct_per_week=Decimal("0.65"),
                fat_loss_speed_label="SAFE",
                plateau_status="",
                sleep_hours=Decimal("7.2"), workout_count=1,
            )

        # Waist decreasing
        for i, val in [(0, 33.75), (7, 34.0), (14, 34.5)]:
            BodyCompositionEntry.objects.create(
                user=self.user, metric_name="waist",
                value=Decimal(str(val)), unit="in",
                measurement_date=self.today - timedelta(days=i),
                source="manual",
            )

        TransformationProtocol.objects.create(
            user=self.user, name="Cut", protocol_type="cut",
            start_date=self.today - timedelta(days=45),
            target_end_date=self.today + timedelta(days=39),
            goal_weight=Decimal("185"), goal_weight_unit="lb",
            is_active=True,
        )

        result = compute_physical_decision(self.user, self.today)
        self.assertEqual(result["decision_type"], "on_track")
        self.assertIn("working", result.get("narrative", "").lower())


class TestScenarioFatLossStall(TestCase):
    """Scenario 2: Fat loss stall despite compliance."""

    def setUp(self):
        self.user = create_test_user(email="stall@example.com")
        self.today = date.today()

    @patch("apps.health.services.physical_decision._gather_signals")
    def test_stall_despite_compliance(self, mock_signals):
        """High compliance but weight/waist flat → outcome_failure."""
        from apps.health.services.physical_decision import compute_physical_decision

        mock_signals.return_value = {
            "nutrition_score": 84, "protein_pct": 81,
            "training_score": 80, "recovery_score": 68,
            "hydration_pct": 72, "sleep_hours": 6.8,
        }

        # Flat weight for 21 days
        for i in range(21):
            d = self.today - timedelta(days=i)
            DailyHealthSummary.objects.create(
                user=self.user, summary_date=d, baseline_ready=True,
                weight=Decimal("186.2"),
                recovery_score=68,
                fat_loss_quality_label="MIXED",
                muscle_preservation_status="MODERATE_QUALITY",
                muscle_loss_risk_level="LOW", muscle_loss_risk_score=30,
                fat_loss_speed_pct_per_week=Decimal("0.05"),
                fat_loss_speed_label="SLOW",
                plateau_status="TRUE_PLATEAU",
                plateau_risk_label="HIGH",
                sleep_hours=Decimal("6.8"), workout_count=1,
            )

        TransformationProtocol.objects.create(
            user=self.user, name="Cut", protocol_type="cut",
            start_date=self.today - timedelta(days=56),
            target_end_date=self.today + timedelta(days=42),
            goal_weight=Decimal("180"), goal_weight_unit="lb",
            is_active=True,
        )

        result = compute_physical_decision(self.user, self.today)
        self.assertEqual(result["decision_type"], "outcome_failure")
        self.assertEqual(result["primary_issue"], "protocol_stalled")
        # Narrative should mention strategy, not behavior
        self.assertIn("strategy", result.get("narrative", "").lower())


class TestScenarioOvertraining(TestCase):
    """Scenario 4: Overtraining — training too hard with insufficient recovery."""

    def setUp(self):
        self.user = create_test_user(email="overtrain@example.com")
        self.today = date.today()

    @patch("apps.health.services.physical_decision._gather_signals")
    def test_overtraining_detected(self, mock_signals):
        """High training + very low recovery → health_risk or overtraining conflict."""
        from apps.health.services.physical_decision import compute_physical_decision

        mock_signals.return_value = {
            "nutrition_score": 91, "protein_pct": 88,
            "training_score": 95, "recovery_score": 28,
            "hydration_pct": 65, "sleep_hours": 5.3,
        }

        for i in range(14):
            d = self.today - timedelta(days=i)
            DailyHealthSummary.objects.create(
                user=self.user, summary_date=d, baseline_ready=True,
                weight=Decimal("196"),
                recovery_score=28 + i,  # Getting worse recently
                fat_loss_quality_label="MIXED",
                muscle_preservation_status="MUSCLE_RISK",
                muscle_loss_risk_level="MED", muscle_loss_risk_score=55,
                fat_loss_speed_label="",
                plateau_status="",
                sleep_hours=Decimal("5.3"), workout_count=1,
            )

        result = compute_physical_decision(self.user, self.today)
        # Should fire health_risk (recovery < 30) at tier 0
        self.assertEqual(result["decision_type"], "health_risk")
        self.assertEqual(result["primary_issue"], "severe_fatigue")

        # Should have overtraining conflict
        conflict_types = [c["type"] for c in result.get("conflicts", [])]
        self.assertIn("overtraining", conflict_types)


class TestScenarioRecomposition(TestCase):
    """Scenario 5: Successful recomposition — fat down, muscle up, scale flat."""

    def setUp(self):
        self.user = create_test_user(email="recomp@example.com")
        self.today = date.today()

    @patch("apps.health.services.physical_decision._gather_signals")
    def test_recomp_success(self, mock_signals):
        """Fat loss + muscle gain + flat scale → recomposition detected."""
        from apps.health.services.physical_decision import compute_physical_decision

        mock_signals.return_value = {
            "nutrition_score": 88, "protein_pct": 94,
            "training_score": 90, "recovery_score": 76,
            "hydration_pct": 85, "sleep_hours": 7.5,
        }

        for i in range(14):
            d = self.today - timedelta(days=i)
            DailyHealthSummary.objects.create(
                user=self.user, summary_date=d, baseline_ready=True,
                weight=Decimal("192"),  # Flat
                recovery_score=76,
                fat_loss_quality_label="GOOD",
                muscle_preservation_status="HIGH_QUALITY",
                muscle_loss_risk_level="LOW", muscle_loss_risk_score=10,
                recomposition_flag_14d=True,
                fat_loss_speed_label="",
                plateau_status="RECOMP",
                sleep_hours=Decimal("7.5"), workout_count=1,
            )

        # Waist decreasing
        for i, val in [(0, 33.5), (14, 34.5)]:
            BodyCompositionEntry.objects.create(
                user=self.user, metric_name="waist",
                value=Decimal(str(val)), unit="in",
                measurement_date=self.today - timedelta(days=i),
                source="manual",
            )

        TransformationProtocol.objects.create(
            user=self.user, name="Recomp", protocol_type="recomposition",
            start_date=self.today - timedelta(days=60),
            is_active=True,
        )

        result = compute_physical_decision(self.user, self.today)
        self.assertEqual(result["decision_type"], "on_track")

        # Body composition should show recomposition
        bc = result.get("body_composition", {})
        self.assertTrue(bc.get("recomposition_status"))

        # Should have positive recomp conflict
        positive_conflicts = [
            c for c in result.get("conflicts", []) if c.get("positive")
        ]
        self.assertTrue(len(positive_conflicts) > 0)


# =========================================================================
# Vitals Snapshot & Multi-Signal Prioritization Tests
# =========================================================================


class TestVitalsSnapshot(TestCase):
    """Tests for vitals snapshot and multi-signal prioritization."""

    def setUp(self):
        self.user = create_test_user(email="vitals_test@example.com")
        self.today = date.today()

    def _create_summaries(self, days=14, weight_start=200, weight_delta=-1.0,
                          fat_loss_quality="GOOD", muscle_preservation="HIGH_QUALITY",
                          plateau_status="", recomp_flag=False,
                          muscle_loss_risk_score=20, muscle_loss_risk_level="LOW",
                          fat_loss_speed_pct=None, fat_loss_speed_label="",
                          recovery_score=70, fat_loss_phase="",
                          plateau_risk_label=""):
        """Create DailyHealthSummary entries for tests."""
        for i in range(days):
            day = self.today - timedelta(days=days - 1 - i)
            weight = Decimal(str(weight_start + (weight_delta / days) * i))
            DailyHealthSummary.objects.create(
                user=self.user,
                summary_date=day,
                weight=weight,
                baseline_ready=True,
                fat_loss_quality_label=fat_loss_quality,
                fat_loss_speed_pct_per_week=(
                    Decimal(str(fat_loss_speed_pct)) if fat_loss_speed_pct else None
                ),
                fat_loss_speed_label=fat_loss_speed_label,
                recomposition_flag_14d=recomp_flag,
                plateau_status=plateau_status,
                plateau_risk_score=Decimal("0"),
                plateau_risk_label=plateau_risk_label,
                muscle_loss_risk_score=Decimal(str(muscle_loss_risk_score)),
                muscle_loss_risk_level=muscle_loss_risk_level,
                muscle_preservation_status=muscle_preservation,
                fat_loss_phase=fat_loss_phase,
                recovery_score=Decimal(str(recovery_score)),
            )

    def test_single_waist_measurement_no_trend(self):
        """TC1: Only 1 waist measurement → no waist trend in body comp."""
        self._create_summaries()
        BodyCompositionEntry.objects.create(
            user=self.user,
            metric_name="waist",
            value=Decimal("35.0"),
            unit="in",
            measurement_date=self.today,
            source="manual",
        )
        result = compute_body_composition_trend(self.user, self.today)
        # With only 1 measurement, waist_trend must be None
        self.assertIsNone(result.get("waist_trend"))

    def test_single_waist_no_blocking_clarity(self):
        """TC1b: With 1 waist measurement, messaging should not be
        exclusively about waist when other data is available."""
        self._create_summaries()
        BodyCompositionEntry.objects.create(
            user=self.user,
            metric_name="waist",
            value=Decimal("35.0"),
            unit="in",
            measurement_date=self.today,
            source="manual",
        )

        # Create real glucose entries (elevated range)
        for i in range(3):
            GlucoseEntry.objects.create(
                user=self.user,
                value=Decimal("115"),
                unit="mg/dL",
                context="fasting",
                recorded_at=timezone.now() - timedelta(days=i),
            )

        from apps.health.services.physical_decision import compute_physical_decision
        result = compute_physical_decision(self.user, self.today)

        # Glucose alert (elevated) should take priority over waist request
        clarity = result.get("clarity_reason", "")
        self.assertIn("glucose", clarity.lower())

    def test_multiple_body_measurements_no_waist_trend(self):
        """TC2: Multiple body measurements but no waist trend →
        system surfaces available body comp signals."""
        self._create_summaries()
        # Add arm measurements (not waist)
        for i in range(3):
            BodyCompositionEntry.objects.create(
                user=self.user,
                metric_name="arm_left",
                value=Decimal("14.5") + Decimal(str(i * 0.1)),
                unit="in",
                measurement_date=self.today - timedelta(days=i * 7),
                source="manual",
            )

        result = compute_body_composition_trend(self.user, self.today)
        # No waist data → waist_trend should be None
        self.assertIsNone(result.get("waist_trend"))
        # But result should still contain fat_loss and other signals
        self.assertIn("fat_loss_status", result)
        self.assertIn("weight_trend", result)

    def test_glucose_priority_over_waist(self):
        """TC3: Glucose present → glucose insight takes priority over waist."""
        self._create_summaries()

        # Create real glucose entries in diabetic range
        for i in range(5):
            GlucoseEntry.objects.create(
                user=self.user,
                value=Decimal("135"),
                unit="mg/dL",
                context="fasting",
                recorded_at=timezone.now() - timedelta(days=i),
            )

        from apps.health.services.physical_decision import compute_physical_decision
        result = compute_physical_decision(self.user, self.today)

        # Vitals snapshot should include glucose
        vitals = result.get("vitals_snapshot", [])
        glucose_vitals = [v for v in vitals if v["metric"] == "glucose"]
        self.assertTrue(len(glucose_vitals) > 0)
        self.assertEqual(glucose_vitals[0]["status"], "high")

        # Clarity should prioritize glucose over waist
        clarity = result.get("clarity_reason", "")
        self.assertIn("glucose", clarity.lower())
        self.assertNotIn("measure your waist", clarity.lower())

        # ── User-facing copy regression (2026-04-26) ──
        # The card header must label this as a glucose alert (not the
        # generic "Progress Unclear"). Severity must be 'alert' (the
        # data IS clear; this is a health alert, not data uncertainty).
        self.assertEqual(result.get("clarity_label"), "Glucose Alert")
        self.assertEqual(result.get("clarity_severity"), "alert")

        # The reason must NOT contain clinical jargon or system-speak
        # that confuses non-clinicians.
        self.assertNotIn("126 mg/dL", clarity)
        self.assertNotIn("diabetic range", clarity.lower())
        self.assertNotIn("takes priority over", clarity.lower())

        # Phase 1 Signal Rendering Framework: copy is now table-locked
        # in apps/core/signals/signal_renderer.py. Spec contract:
        # one short sentence, one action.
        self.assertEqual(
            clarity, "Your glucose has been running high this week.",
        )

        # The action must be concrete and in-app first (logging).
        action = result.get("clarity_action", "")
        self.assertEqual(
            action,
            "Log your next 3 meals and add a fasting reading tomorrow.",
        )

    def test_all_signals_present_highest_priority(self):
        """TC4: All signals present → highest priority signal displayed."""
        self._create_summaries()

        # Add 2 waist measurements for valid trend
        for i in range(2):
            BodyCompositionEntry.objects.create(
                user=self.user,
                metric_name="waist",
                value=Decimal("35.0") - Decimal(str(i * 0.3)),
                unit="in",
                measurement_date=self.today - timedelta(days=i * 10),
                source="manual",
            )

        # Create real vitals data (all normal ranges)
        for i in range(5):
            GlucoseEntry.objects.create(
                user=self.user,
                value=Decimal("90"),
                unit="mg/dL",
                context="fasting",
                recorded_at=timezone.now() - timedelta(days=i),
            )
            HeartRateEntry.objects.create(
                user=self.user,
                bpm=68,
                context="resting",
                recorded_at=timezone.now() - timedelta(days=i),
            )
        BloodPressureEntry.objects.create(
            user=self.user,
            systolic=118,
            diastolic=76,
            context="resting",
            recorded_at=timezone.now(),
        )

        from apps.health.services.physical_decision import compute_physical_decision
        result = compute_physical_decision(self.user, self.today)

        # Should have vitals snapshot with all 3 metrics
        vitals = result.get("vitals_snapshot", [])
        metrics = [v["metric"] for v in vitals]
        self.assertIn("glucose", metrics)
        self.assertIn("blood_pressure", metrics)
        self.assertIn("heart_rate", metrics)

        # All normal → no vitals alert should dominate
        # Waist should still appear since we have 2 measurements
        bc = result.get("body_composition", {})
        self.assertIsNotNone(bc.get("waist_trend"))

    def test_vitals_snapshot_priority_order(self):
        """Vitals should be ordered: glucose (1), BP (2), HR (3)."""
        from apps.health.services.physical_decision import _build_vitals_snapshot

        signals = {
            "heart_rate_avg_7d": 72,
            "latest_heart_rate": 70,
            "bp_systolic": 120,
            "bp_diastolic": 80,
            "glucose_avg_7d": 95,
            "latest_glucose": 93,
            "latest_glucose_unit": "mg/dL",
        }
        vitals = _build_vitals_snapshot(signals)
        self.assertEqual(len(vitals), 3)
        self.assertEqual(vitals[0]["metric"], "glucose")
        self.assertEqual(vitals[1]["metric"], "blood_pressure")
        self.assertEqual(vitals[2]["metric"], "heart_rate")

    def test_vitals_snapshot_empty_when_no_data(self):
        """No vitals data → empty snapshot."""
        from apps.health.services.physical_decision import _build_vitals_snapshot

        signals = {}
        vitals = _build_vitals_snapshot(signals)
        self.assertEqual(len(vitals), 0)

    def test_vitals_glucose_classification(self):
        """Glucose status classification is correct."""
        from apps.health.services.physical_decision import _build_vitals_snapshot

        # Normal
        vitals = _build_vitals_snapshot({"glucose_avg_7d": 90, "latest_glucose_unit": "mg/dL"})
        self.assertEqual(vitals[0]["status"], "normal")

        # Elevated (pre-diabetic)
        vitals = _build_vitals_snapshot({"glucose_avg_7d": 110, "latest_glucose_unit": "mg/dL"})
        self.assertEqual(vitals[0]["status"], "elevated")

        # High (diabetic range)
        vitals = _build_vitals_snapshot({"glucose_avg_7d": 130, "latest_glucose_unit": "mg/dL"})
        self.assertEqual(vitals[0]["status"], "high")

        # Low (hypoglycemia)
        vitals = _build_vitals_snapshot({"glucose_avg_7d": 65, "latest_glucose_unit": "mg/dL"})
        self.assertEqual(vitals[0]["status"], "low")

    def test_bp_classification(self):
        """Blood pressure status classification matches AHA guidelines."""
        from apps.health.services.physical_decision import _build_vitals_snapshot

        # Normal
        vitals = _build_vitals_snapshot({"bp_systolic": 115, "bp_diastolic": 75})
        bp = [v for v in vitals if v["metric"] == "blood_pressure"][0]
        self.assertEqual(bp["status"], "normal")

        # High
        vitals = _build_vitals_snapshot({"bp_systolic": 145, "bp_diastolic": 95})
        bp = [v for v in vitals if v["metric"] == "blood_pressure"][0]
        self.assertEqual(bp["status"], "high")
