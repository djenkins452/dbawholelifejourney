"""Measurement Session Capture — the deterministic handler for `log_body_measurements`.

A screenshot/photo/voice/typed set of many body measurements arrives as ONE intent
(the model perceives; WLJ owns truth). These tests exercise the deterministic seam:
validate → skip-absent → always-confirm → (on Import) ONE canonical BodyMeasurementSession
grouping the BodyCompositionEntry rows, with waist-hip ratio DERIVED (never stored) and
artifact-level idempotency. The perception half (OpenAI reading pixels) is the model's and
is not unit-tested.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.action_handlers import ActionHandler
from apps.capture.models import MultimodalArtifact
from apps.health.models import BodyCompositionEntry, BodyMeasurementSession

User = get_user_model()


def _make_user(email):
    from django.conf import settings

    from apps.users.models import TermsAcceptance
    user = User.objects.create_user(email=email, password="x")
    TermsAcceptance.objects.create(
        user=user, terms_version=settings.WLJ_SETTINGS["TERMS_VERSION"])
    prefs = user.preferences
    prefs.has_completed_onboarding = True
    prefs.save()
    return user


# A Renpho-screenshot-shaped payload: 13 populated values + one unmeasured part ('0.00')
# the validator must treat as ABSENT, plus a waist-hip ratio the model should NOT send
# (derived) — included here to prove it is dropped, not stored.
def _renpho_payload():
    return [
        {"metric": "neck", "value": 16.29, "unit": "in", "confidence": 0.98},
        {"metric": "shoulders", "value": 50.43, "unit": "in", "confidence": 0.97},
        {"metric": "arm_left", "value": 16.49, "unit": "in", "confidence": 0.96},
        {"metric": "arm_right", "value": 17.36, "unit": "in", "confidence": 0.96},
        {"metric": "chest", "value": 50.90, "unit": "in", "confidence": 0.95},
        {"metric": "waist", "value": 54.72, "unit": "in", "confidence": 0.99},
        {"metric": "abdomen", "value": 50.94, "unit": "in", "confidence": 0.94},
        {"metric": "hips", "value": 47.16, "unit": "in", "confidence": 0.98},
        {"metric": "thigh_left", "value": 27.04, "unit": "in", "confidence": 0.93},
        {"metric": "thigh_right", "value": 27.48, "unit": "in", "confidence": 0.93},
        {"metric": "calf_left", "value": 17.40, "unit": "in", "confidence": 0.92},
        {"metric": "calf_right", "value": 16.49, "unit": "in", "confidence": 0.55},  # uncertain
        {"metric": "forearm_left", "value": 12.12, "unit": "in", "confidence": 0.9},
        {"metric": "forearm_right", "value": 12.36, "unit": "in", "confidence": 0.9},
        {"metric": "calf_right_custom", "value": "0.00", "unit": "in"},  # bad label + absent
        {"metric": "custom_part_3", "value": "--", "unit": "in"},        # absent
        {"metric": "waist_hip_ratio", "value": 1.16},                    # derived → dropped
    ]


class ConfirmationGateTests(TestCase):
    def setUp(self):
        self.user = _make_user("cap-confirm@example.com")
        self.handler = ActionHandler(self.user)
        self.artifact = MultimodalArtifact.objects.create(
            user=self.user, sha256="deadbeef", content_type="image/png", kind="image")

    def test_first_call_confirms_and_writes_nothing(self):
        res = self.handler.handle_log_body_measurements(
            measurements=_renpho_payload(), source="Renpho Screenshot",
            measured_at="2026-07-19T09:49:23", source_artifact_id=self.artifact.id,
        )
        self.assertFalse(res.success)
        self.assertEqual(res.error, "confirmation_required")
        d = res.confirmation_detail
        self.assertEqual(d["renderer"], "body_measurement_session")
        # 14 real values pass; the two absent parts + bad label + WHR are excluded.
        self.assertEqual(d["count"], 14)
        self.assertEqual(len(d["measurements"]), 14)
        # WHR derived for display only (54.72 / 47.16 ≈ 1.16), never a stored measurement.
        self.assertAlmostEqual(d["derived"]["waist_hip_ratio"], 1.16, places=2)
        self.assertNotIn("waist_hip_ratio", {m["metric"] for m in d["measurements"]})
        # Low-confidence value is flagged for the reviewer.
        cr = next(m for m in d["measurements"] if m["metric"] == "calf_right")
        self.assertTrue(cr["uncertain"])
        # NOTHING was written on the confirmation turn.
        self.assertEqual(BodyMeasurementSession.objects.filter(user=self.user).count(), 0)
        self.assertEqual(BodyCompositionEntry.objects.filter(user=self.user).count(), 0)


class ImportWriteTests(TestCase):
    def setUp(self):
        self.user = _make_user("cap-import@example.com")
        self.handler = ActionHandler(self.user)
        self.artifact = MultimodalArtifact.objects.create(
            user=self.user, sha256="cafebabe", content_type="image/png", kind="image")

    def test_confirmed_import_writes_one_session_and_entries(self):
        res = self.handler.handle_log_body_measurements(
            measurements=_renpho_payload(), source="Renpho Screenshot",
            measured_at="2026-07-19T09:49:23", source_artifact_id=self.artifact.id,
            confirmed=True,
        )
        self.assertTrue(res.success, res.message)
        # Exactly ONE canonical session grouping all 14 entries.
        sessions = BodyMeasurementSession.objects.filter(user=self.user)
        self.assertEqual(sessions.count(), 1)
        session = sessions.first()
        self.assertEqual(session.source, "renpho")
        entries = BodyCompositionEntry.objects.filter(user=self.user)
        self.assertEqual(entries.count(), 14)
        self.assertTrue(all(e.session_id == session.id for e in entries))
        # Waist stored as canonical truth; WHR NOT stored anywhere.
        waist = entries.get(metric_name="waist")
        self.assertEqual(waist.value, Decimal("54.72"))
        self.assertFalse(entries.filter(metric_name__icontains="ratio").exists())
        self.assertFalse(entries.filter(metric_name="waist_hip_ratio").exists())
        # Provenance: the screenshot resolved to the session.
        self.artifact.refresh_from_db()
        self.assertEqual(self.artifact.status, "resolved")
        self.assertEqual(self.artifact.resolved_object_type, "BodyMeasurementSession")
        self.assertEqual(self.artifact.resolved_object_id, session.id)

    def test_same_artifact_reimport_is_idempotent(self):
        common = dict(measurements=_renpho_payload(), source="Renpho Screenshot",
                      measured_at="2026-07-19T09:49:23",
                      source_artifact_id=self.artifact.id, confirmed=True)
        self.handler.handle_log_body_measurements(**common)
        res2 = self.handler.handle_log_body_measurements(**common)
        self.assertTrue(res2.success)
        self.assertIn("duplicate_of_artifact", res2.created_object)
        self.assertEqual(BodyMeasurementSession.objects.filter(user=self.user).count(), 1)
        self.assertEqual(BodyCompositionEntry.objects.filter(user=self.user).count(), 14)

    def test_all_absent_returns_validation_error(self):
        res = self.handler.handle_log_body_measurements(
            measurements=[{"metric": "waist", "value": "--"},
                          {"metric": "hips", "value": "0.00"}],
            source="Renpho Screenshot", confirmed=True,
        )
        self.assertFalse(res.success)
        self.assertEqual(res.error, "validation_failed")
        self.assertEqual(BodyMeasurementSession.objects.filter(user=self.user).count(), 0)


class LabelNormalizationTests(TestCase):
    """Regression for the 2026-07-19 Shoulder defect: device screens show SINGULAR labels
    ('Shoulder', 'Hip') but WLJ's canonical metrics are PLURAL — the singular must map, and a
    genuinely unrecognized label must SURFACE, never silently vanish."""

    def setUp(self):
        self.user = _make_user("cap-normalize@example.com")
        self.handler = ActionHandler(self.user)
        # An artifact-sourced import (screenshot) is what triggers the confirmation review;
        # a typed/voice set (no artifact) writes directly.
        self.artifact = MultimodalArtifact.objects.create(
            user=self.user, sha256="feed0001", content_type="image/png", kind="image")

    def test_singular_shoulder_and_hip_are_imported(self):
        res = self.handler.handle_log_body_measurements(
            measurements=[
                {"metric": "Shoulder", "value": 50.43, "unit": "in"},  # screenshot's exact label
                {"metric": "Hip", "value": 47.16, "unit": "in"},
                {"metric": "waist", "value": 54.72, "unit": "in"},
            ],
            source="Renpho Screenshot", confirmed=True,
        )
        self.assertTrue(res.success, res.message)
        metrics = set(
            BodyCompositionEntry.objects.filter(user=self.user)
            .values_list("metric_name", flat=True)
        )
        self.assertIn("shoulders", metrics)   # was DROPPED before the fix
        self.assertIn("hips", metrics)

    def test_unrecognized_label_surfaces_in_skipped_not_silently_dropped(self):
        res = self.handler.handle_log_body_measurements(
            measurements=[
                {"metric": "knee", "value": 15.0, "unit": "in"},   # no such canonical metric
                {"metric": "waist", "value": 54.72, "unit": "in"},
            ],
            source="Renpho Screenshot", source_artifact_id=self.artifact.id,  # → confirmation payload
        )
        self.assertEqual(res.error, "confirmation_required")
        skipped = res.confirmation_detail["skipped"]
        self.assertTrue(any(s.get("label") == "knee" and s.get("reason") == "unrecognized_metric"
                            for s in skipped),
                        "unrecognized 'knee' must be surfaced in skipped, never silently dropped")

    def test_waist_hip_ratio_is_skipped_quietly_not_flagged(self):
        res = self.handler.handle_log_body_measurements(
            measurements=[
                {"metric": "waist_hip_ratio", "value": 1.16},   # derived — never stored
                {"metric": "waist", "value": 54.72, "unit": "in"},
                {"metric": "hips", "value": 47.16, "unit": "in"},
            ],
            source="Renpho Screenshot", source_artifact_id=self.artifact.id,
        )
        self.assertEqual(res.error, "confirmation_required")
        # WHR is a DERIVED skip: absent from both validated measurements AND the skipped list.
        self.assertNotIn("waist_hip_ratio",
                         {mm["metric"] for mm in res.confirmation_detail["measurements"]})
        self.assertFalse(any("ratio" in str(s.get("label", "")).lower()
                             for s in res.confirmation_detail["skipped"]))
        # …but it IS surfaced as the derived display value.
        self.assertAlmostEqual(res.confirmation_detail["derived"]["waist_hip_ratio"], 1.16, places=2)


class CoSReadbackTests(TestCase):
    """After import, the canonical truth surface answers 'what are my current measurements?'"""

    def setUp(self):
        self.user = _make_user("cap-readback@example.com")
        self.handler = ActionHandler(self.user)

    def test_imported_session_is_visible_to_body_measurement_truth(self):
        self.handler.handle_log_body_measurements(
            measurements=_renpho_payload(), source="Renpho Screenshot",
            measured_at="2026-07-19T09:49:23", confirmed=True,
        )
        from apps.health.services.body_measurement_queries import BodyMeasurementQueries
        result = BodyMeasurementQueries.describe(self.user)
        self.assertIsNotNone(result)


class ConfirmationSummaryTests(TestCase):
    """The confirmation reports RESULTS, not intentions: exactly what perception found and
    precisely what will and will NOT be saved (and why) BEFORE anything is written. Never a
    silently-dropped value. (The generic multimodal-import confirmation pattern.)"""

    def setUp(self):
        self.user = _make_user("cap-summary@example.com")
        self.handler = ActionHandler(self.user)
        self.artifact = MultimodalArtifact.objects.create(
            user=self.user, sha256="5umm0001", content_type="image/png", kind="image")

    def test_summary_lists_recognized_skipped_counts_and_reasons(self):
        res = self.handler.handle_log_body_measurements(
            measurements=[
                {"metric": "Shoulder", "value": 50.43, "unit": "in"},  # first-class metric now
                {"metric": "chest", "value": 50.90, "unit": "in"},
                {"metric": "waist", "value": 54.72, "unit": "in"},
                {"metric": "hips", "value": 47.16, "unit": "in"},
                {"metric": "knee", "value": 15.0, "unit": "in"},       # unrecognized → surfaced
            ],
            source="Renpho Screenshot", source_artifact_id=self.artifact.id,
        )
        self.assertEqual(res.error, "confirmation_required")
        msg = res.message
        # Exactly what perception found, per line (with formatted values).
        self.assertIn("Measurements recognized:", msg)
        self.assertIn('✓ Shoulders — 50.43"', msg)  # a normal importable measurement now
        self.assertIn('✓ Waist — 54.72"', msg)
        self.assertIn("⚠ knee", msg)                # unrecognized surfaced, never hidden
        # Exactly what will and won't import.
        self.assertIn("• 5 recognized", msg)
        self.assertIn("• 4 can be imported", msg)
        self.assertIn("• 1 cannot be imported", msg)
        # WHY it can't import.
        self.assertIn("Skipped:", msg)
        self.assertIn("doesn't have a place to store", msg)
        # Derived WHR shown for display (never stored separately).
        self.assertIn("waist-hip ratio", msg)
        # And nothing was written on the confirmation turn.
        self.assertEqual(BodyMeasurementSession.objects.filter(user=self.user).count(), 0)

    def test_all_recognized_reads_n_imported_zero_skipped(self):
        """End state with Shoulder first-class: a clean set reads N recognized / N imported /
        0 skipped, with no Skipped section."""
        res = self.handler.handle_log_body_measurements(
            measurements=[
                {"metric": "Shoulder", "value": 50.43, "unit": "in"},
                {"metric": "chest", "value": 50.90, "unit": "in"},
                {"metric": "waist", "value": 54.72, "unit": "in"},
            ],
            source="Renpho Screenshot", source_artifact_id=self.artifact.id,
        )
        self.assertEqual(res.error, "confirmation_required")
        self.assertIn("• 3 recognized", res.message)
        self.assertIn("• 3 can be imported", res.message)
        self.assertIn("• 0 cannot be imported", res.message)
        self.assertNotIn("Skipped:", res.message)
        self.assertIn("Import these 3 measurements?", res.message)


class DeterministicConfirmReplayTests(TestCase):
    """A bare-'yes'/'Import' reply resolves through the deterministic crud bridge, NOT a model
    re-call. That replay must forward confirmed=True for data-confirm imports or the handler's
    own data gate re-fires and the import silently never persists."""

    def setUp(self):
        self.user = _make_user("cap-replay@example.com")

    def test_yes_after_confirmation_actually_persists_the_session(self):
        from apps.ai.intent_service import IntentService
        svc = IntentService()
        # Simulate the state after the first turn returned confirmation_required: the CoS bridge
        # stored the pending action with the ORIGINAL tool params (no `confirmed`).
        svc.store_pending_crud_action(self.user, {
            "intent_type": "log_body_measurements",
            "parameters": {
                "measurements": [
                    {"metric": "waist", "value": 54.72, "unit": "in"},
                    {"metric": "hips", "value": 47.16, "unit": "in"},
                ],
                "source": "Renpho Screenshot",
            },
            "original_intent": "log_body_measurements",
            "confirmation_message": "Import these 2 measurements?",
        })
        result = svc.handle_crud_confirmation(self.user, "yes")
        self.assertIsNotNone(result)
        self.assertTrue(getattr(result, "success", False),
                        getattr(result, "message", "no message"))
        # The confirmed import actually wrote the canonical session (did NOT re-gate/loop).
        self.assertEqual(BodyMeasurementSession.objects.filter(user=self.user).count(), 1)
        self.assertEqual(BodyCompositionEntry.objects.filter(user=self.user).count(), 2)
