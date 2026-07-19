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
