"""Conversation State — active-artifact CONTINUITY (production defect 2026-07-20).

An uploaded artifact must remain the active conversational artifact across follow-ups —
not merely a reference, but RE-PERCEIVABLE — until Conversation State legitimately expires
or is superseded. Reproduces the French's-mustard failure ("How many ounces is it?" →
"the image isn't available") at the deterministic layer for image / video / PDF, and proves
the fix: `active_artifact_ids` exposes the active artifact, and re-perception works during
the durable-storage-pending window via the short-lived bytes cache.
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from apps.ai.models import AssistantConversation
from apps.ai.model_interface import conversation_state as cs
from apps.ai import multimodal as mm
from apps.capture.models import MultimodalArtifact

User = get_user_model()
_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="


class ArtifactContinuityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="artcont@example.com", password="x")
        self.conv = AssistantConversation.objects.create(user=self.user, session_type="chat")

    def _art(self, kind, ct, sha):
        return MultimodalArtifact.objects.create(
            user=self.user, source_conversation_id=self.conv.id, kind=kind,
            content_type=ct, status="resolved", sha256=sha)

    # --- the active artifact is exposed for re-delivery (image / video / pdf) --------
    def test_uploaded_image_is_the_active_artifact(self):
        art = self._art("image", "image/png", "sha-img")
        cs.record_turn(self.conv, attachments=[{"artifact_id": art.id, "kind": "image"}])
        self.assertEqual(cs.active_artifact_ids(self.conv), [art.id])

    def test_uploaded_video_is_the_active_artifact(self):
        art = self._art("video", "video/mp4", "sha-vid")
        cs.record_turn(self.conv, attachments=[{"artifact_id": art.id, "kind": "video"}])
        self.assertEqual(cs.active_artifact_ids(self.conv), [art.id])

    def test_uploaded_pdf_is_the_active_artifact(self):
        art = self._art("document", "application/pdf", "sha-pdf")
        cs.record_turn(self.conv, attachments=[{"artifact_id": art.id, "kind": "document",
                                                "filename": "manual.pdf"}])
        self.assertEqual(cs.active_artifact_ids(self.conv), [art.id])

    # --- re-perception works while durable storage is still PENDING (bytes cache) ----
    def test_image_reperceivable_from_cache_when_storage_pending(self):
        art = self._art("image", "image/png", "sha-cache")
        self.assertFalse(art.is_durably_stored)          # async storage not done yet
        mm._cache_artifact_bytes(art.id, _PNG_B64, "image/png")
        imgs = mm.perceive_images_for_artifacts(self.user, [art.id])
        self.assertEqual(len(imgs), 1, "active image must be re-perceivable from the cache")
        self.assertEqual(imgs[0][0], _PNG_B64)

    def test_no_cache_no_storage_yields_no_bytes(self):
        art = self._art("image", "image/png", "sha-nocache")
        cache.delete(mm._artbytes_key(art.id))
        self.assertEqual(mm.perceive_images_for_artifacts(self.user, [art.id]), [])

    # --- continuity ends only on supersession / expiry -------------------------------
    def test_active_artifact_cleared_when_superseded(self):
        art = self._art("image", "image/png", "sha-sup")
        cs.record_turn(self.conv, attachments=[{"artifact_id": art.id, "kind": "image"}])
        cs.record_turn(self.conv, retrieved_subject={
            "kind": "entity", "ref": "Dad's health", "label": "Dad's health"})
        self.assertEqual(cs.active_artifact_ids(self.conv), [],
                         "a new subject supersedes the active artifact")

    def test_active_artifact_survives_follow_ups_until_backstop(self):
        art = self._art("image", "image/png", "sha-surv")
        cs.record_turn(self.conv, attachments=[{"artifact_id": art.id, "kind": "image"}])
        for _ in range(5):                               # five text-only follow-ups
            cs.record_turn(self.conv, attachments=None)
        self.assertEqual(cs.active_artifact_ids(self.conv), [art.id],
                         "the artifact must stay available across a normal follow-up thread")
