"""Multimodal Truth — the deterministic spine (first slice: scale photo → log_weight).

WLJ never interprets pixels. It stores the artifact (provenance + hash dedup), validates the
EXTRACTED candidate, detects duplicates, applies the confirmation POLICY, executes through the
existing action path, and links provenance. These tests cover WLJ's deterministic half; the
perception half (OpenAI reading the image) is the model's and isn't unit-tested here."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.ai import multimodal
from apps.ai.action_handlers import ActionHandler
from apps.capture.models import MultimodalArtifact
from apps.health.models import WeightEntry

User = get_user_model()


class ArtifactStoreTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="mm@example.com", password="x")

    def test_store_and_artifact_level_dedup(self):
        art1, created1 = multimodal.store_artifact(
            self.user, data=b"scale-photo-bytes", content_type="image/jpeg", kind="scale_photo")
        self.assertTrue(created1)
        self.assertEqual(len(art1.sha256), 64)
        # Same bytes uploaded again → SAME artifact, not a new row (artifact-level dedup).
        art2, created2 = multimodal.store_artifact(
            self.user, data=b"scale-photo-bytes", content_type="image/jpeg")
        self.assertFalse(created2)
        self.assertEqual(art1.id, art2.id)
        self.assertEqual(MultimodalArtifact.objects.filter(user=self.user).count(), 1)

    def test_link_artifact_records_provenance(self):
        art, _ = multimodal.store_artifact(self.user, data=b"x", content_type="image/jpeg")
        multimodal.link_artifact(art.id, intent="log_weight",
                                 object_type="WeightEntry", object_id=42)
        art.refresh_from_db()
        self.assertEqual(art.status, "resolved")
        self.assertEqual(art.resolved_intent, "log_weight")
        self.assertEqual(art.resolved_object_id, 42)


class ValidationAndDedupTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="v@example.com", password="x")

    def test_weight_range_validation(self):
        self.assertTrue(multimodal.validate_weight(182.4, "lb"))
        self.assertTrue(multimodal.validate_weight(82.0, "kg"))
        self.assertFalse(multimodal.validate_weight(9, "lb"))       # implausible low
        self.assertFalse(multimodal.validate_weight(5000, "lb"))    # implausible high
        self.assertFalse(multimodal.validate_weight("abc", "lb"))   # unparseable

    def test_fact_level_duplicate_detection(self):
        WeightEntry.objects.create(user=self.user, value=Decimal("182.4"), unit="lb",
                                   recorded_at=timezone.now())
        self.assertIsNotNone(multimodal.find_duplicate_weight(self.user, 182.4, "lb"))
        self.assertIsNone(multimodal.find_duplicate_weight(self.user, 175.0, "lb"))


class ConfirmationPolicyTests(TestCase):
    def test_non_multimodal_never_forced_to_confirm(self):
        # No artifact => normal typed path, existing behavior.
        self.assertFalse(multimodal.requires_confirmation("log_weight", confidence=0.2))

    def test_clinical_intent_always_confirms_from_image(self):
        self.assertTrue(multimodal.requires_confirmation(
            "log_glucose", confidence=0.99, source_artifact_id=1))

    def test_low_confidence_confirms(self):
        self.assertTrue(multimodal.requires_confirmation(
            "log_weight", confidence=0.4, source_artifact_id=1))

    def test_duplicate_confirms(self):
        self.assertTrue(multimodal.requires_confirmation(
            "log_weight", confidence=0.99, duplicate=True, source_artifact_id=1))

    def test_high_confidence_low_risk_auto_executes(self):
        self.assertFalse(multimodal.requires_confirmation(
            "log_weight", confidence=0.97, duplicate=False, source_artifact_id=1))


class LogWeightMultimodalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="lw@example.com", password="x")
        self.handler = ActionHandler(self.user)
        self.art, _ = multimodal.store_artifact(
            self.user, data=b"scale", content_type="image/jpeg", kind="scale_photo")

    def test_high_confidence_executes_and_links_provenance(self):
        res = self.handler.handle_log_weight(
            value=182.4, unit="lb", source_artifact_id=self.art.id, confidence=0.97)
        self.assertTrue(res.success)
        entry = WeightEntry.objects.get(user=self.user)
        self.assertEqual(float(entry.value), 182.4)
        # Provenance chain: artifact → the WeightEntry it produced.
        self.art.refresh_from_db()
        self.assertEqual(self.art.status, "resolved")
        self.assertEqual(self.art.resolved_object_id, entry.id)

    def test_implausible_extraction_is_rejected_not_stored(self):
        res = self.handler.handle_log_weight(
            value=9, unit="lb", source_artifact_id=self.art.id, confidence=0.99)
        self.assertFalse(res.success)
        self.assertEqual(res.error, "validation_failed")
        self.assertFalse(WeightEntry.objects.filter(user=self.user).exists())

    def test_low_confidence_requires_confirmation_no_write(self):
        res = self.handler.handle_log_weight(
            value=182.4, unit="lb", source_artifact_id=self.art.id, confidence=0.4)
        self.assertFalse(res.success)
        self.assertEqual(res.error, "confirmation_required")
        self.assertFalse(WeightEntry.objects.filter(user=self.user).exists())

    def test_duplicate_requires_confirmation(self):
        WeightEntry.objects.create(user=self.user, value=Decimal("182.4"), unit="lb",
                                   recorded_at=timezone.now())
        res = self.handler.handle_log_weight(
            value=182.4, unit="lb", source_artifact_id=self.art.id, confidence=0.99)
        self.assertFalse(res.success)
        self.assertEqual(res.error, "confirmation_required")
        # No second (duplicate) row written.
        self.assertEqual(WeightEntry.objects.filter(user=self.user).count(), 1)

    def test_typed_path_unaffected(self):
        # No artifact => behaves exactly as before (no forced confirmation).
        res = self.handler.handle_log_weight(value=180.0, unit="lb")
        self.assertTrue(res.success)
        self.assertTrue(WeightEntry.objects.filter(user=self.user).exists())
