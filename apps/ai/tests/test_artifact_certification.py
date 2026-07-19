"""
Artifacts-as-Truth CERTIFICATION SUITE (Milestone B6).

Automated customer-truth scenarios — certifies the DETERMINISTIC behavior behind
each customer capability (the layer WLJ owns; the model's narration is separate).
Every case is phrased as the customer intent it certifies. If one of these breaks,
a customer-facing trust behavior has regressed.

Certifies: same-turn PDF follow-up · multi-turn PDF follow-up · cross-conversation
PDF · cross-conversation audio · prior-image renewed perception · prior-video
transcript+frames · most-recent · date-scoped · ambiguous-match · owner isolation
· provenance · conversation linkage · domain linkage.
"""
import base64
import tempfile
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.ai.cos_services.domain_entity import get_domain_entity
from apps.ai.multimodal import (
    attachments_from_ids,
    conversation_artifacts_context,
    link_artifacts_to_conversation,
    perceive_images_for_artifacts,
    store_artifact,
)
from apps.capture.models import MultimodalArtifact
from apps.capture.services.artifact_queries import ArtifactQueries

User = get_user_model()
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40


def _mk(user, **kw):
    d = dict(sha256=kw.pop("sha", "x" * 64), content_type="application/pdf",
             kind="document", perception_status=MultimodalArtifact.PERCEPTION_DONE)
    d.update(kw)
    return MultimodalArtifact.objects.create(user=user, **d)


def _entity_blob(env):
    """Flatten an entity envelope to a searchable string for content assertions."""
    return str(env)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="wlj-cert-"))
class ArtifactCertification(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="cert@ex.com", password="x")
        self.other = User.objects.create_user(email="other@ex.com", password="x")

    # 1. Same-turn PDF follow-up — the just-uploaded PDF's text is available to answer.
    def test_cert_same_turn_pdf(self):
        a = _mk(self.user, sha="a" * 64, original_filename="policy.pdf",
                extracted_text="Deductible: $1,500. Emergency care covered.")
        surfaced = attachments_from_ids(self.user, [a.id])
        self.assertIn("Deductible: $1,500", surfaced[0]["text"])

    # 2. Multi-turn PDF follow-up — after uploading, a later turn still finds it.
    def test_cert_multi_turn_pdf(self):
        a = _mk(self.user, sha="a" * 64, original_filename="policy.pdf",
                extracted_text="Deductible: $1,500")
        link_artifacts_to_conversation(500, [a.id])
        # Turn 2: it is surfaced as a prior upload in THIS conversation…
        prior = conversation_artifacts_context(self.user, 500)
        self.assertEqual(prior[0]["filename"], "policy.pdf")
        # …and retrievable for the actual content.
        env = get_domain_entity(self.user, "artifacts", name="policy")
        self.assertEqual(env["status"], "ready")
        self.assertIn("Deductible", _entity_blob(env))

    # 3. Cross-conversation PDF retrieval — from a brand-new conversation.
    def test_cert_cross_conversation_pdf(self):
        _mk(self.user, sha="a" * 64, original_filename="labs.pdf",
            extracted_text="MRI IMPRESSION: mild degenerative changes.",
            source_conversation_id=1)
        env = get_domain_entity(self.user, "artifacts", name="MRI")   # different conversation
        self.assertEqual(env["status"], "ready")
        self.assertIn("degenerative changes", _entity_blob(env))

    # 4. Cross-conversation AUDIO retrieval — the transcript is retrievable.
    def test_cert_cross_conversation_audio(self):
        _mk(self.user, sha="a" * 64, kind="audio", content_type="audio/mpeg",
            original_filename="note.m4a", extracted_text="Call the pharmacy about the refill.")
        env = get_domain_entity(self.user, "artifacts", name="pharmacy")
        self.assertEqual(env["status"], "ready")
        self.assertIn("refill", _entity_blob(env))

    # 5. Prior-IMAGE retrieval with RENEWED perception — the pixels come back.
    def test_cert_prior_image_reperception(self):
        name = default_storage.save("multimodal/x/pic.png", ContentFile(PNG))
        a = _mk(self.user, sha="a" * 64, kind="image", content_type="image/png",
                original_filename="progress.png", perception_status="none",
                storage_ref=name, storage_status=MultimodalArtifact.STORAGE_STORED)
        imgs = perceive_images_for_artifacts(self.user, [a.id])
        self.assertEqual(len(imgs), 1)
        self.assertEqual(base64.b64decode(imgs[0][0]), PNG)   # actual bytes re-delivered

    # 6. Prior-VIDEO retrieval — transcript (text) + frames (pixels).
    def test_cert_prior_video_transcript_and_frames(self):
        frames = [{"t": 0.5, "b64": base64.b64encode(b"f0").decode()}]
        a = _mk(self.user, sha="a" * 64, kind="video", content_type="video/mp4",
                original_filename="swing.mp4",
                extracted_text="[Audio transcript]\nkeep your head down", frames=frames)
        env = get_domain_entity(self.user, "artifacts", name="swing")
        self.assertIn("head down", _entity_blob(env))              # transcript
        self.assertEqual(len(perceive_images_for_artifacts(self.user, [a.id])), 1)  # frames

    # 7. Most-recent artifact retrieval.
    def test_cert_most_recent(self):
        old = _mk(self.user, sha="a" * 64, original_filename="old.pdf")
        MultimodalArtifact.objects.filter(id=old.id).update(
            created_at=timezone.now() - timedelta(days=10))
        _mk(self.user, sha="b" * 64, original_filename="new.pdf")
        self.assertEqual(ArtifactQueries.last_uploaded(self.user).original_filename, "new.pdf")

    # 8. Date-scoped retrieval ("from last month" resolves to start/end upstream).
    def test_cert_date_scoped(self):
        old = _mk(self.user, sha="a" * 64, original_filename="old.pdf")
        MultimodalArtifact.objects.filter(id=old.id).update(
            created_at=timezone.now() - timedelta(days=60))
        _mk(self.user, sha="b" * 64, original_filename="recent.pdf")
        start = (timezone.now() - timedelta(days=30)).date().isoformat()
        env = get_domain_entity(self.user, "artifacts", entity_type="document",
                                filters={"start": start})
        self.assertIn("recent.pdf", _entity_blob(env))
        self.assertNotIn("old.pdf", _entity_blob(env))

    # 9. Ambiguous match — multiple candidates are ALL returned (model then clarifies).
    def test_cert_ambiguous_match(self):
        _mk(self.user, sha="a" * 64, original_filename="lab_jan.pdf", extracted_text="lab report jan")
        _mk(self.user, sha="b" * 64, original_filename="lab_feb.pdf", extracted_text="lab report feb")
        hits = ArtifactQueries.search(self.user, "lab report")
        self.assertEqual(len(hits), 2)   # both surfaced, not one confidently picked

    # 10. Owner isolation — another user's artifact is never returned.
    def test_cert_owner_isolation(self):
        _mk(self.other, sha="a" * 64, original_filename="theirs.pdf", extracted_text="secret MRI")
        env = get_domain_entity(self.user, "artifacts", name="MRI")
        self.assertEqual(env["status"], "empty")
        self.assertEqual(perceive_images_for_artifacts(self.user, [1]), [])

    # 11. Provenance — the retrieved entity says which file, from where.
    def test_cert_provenance(self):
        _mk(self.user, sha="a" * 64, original_filename="lab.pdf",
            extracted_text="x", source_conversation_id=42)
        env = get_domain_entity(self.user, "artifacts", name="lab")
        blob = _entity_blob(env)
        self.assertIn("lab.pdf", blob)
        self.assertIn("42", blob)                    # source conversation
        self.assertIn("perception_status", blob)

    # 12. Conversation linkage — first-conversation is remembered, surfaced, scoped.
    def test_cert_conversation_linkage(self):
        a = _mk(self.user, sha="a" * 64, original_filename="c.pdf")
        link_artifacts_to_conversation(900, [a.id])
        a.refresh_from_db()
        self.assertEqual(a.source_conversation_id, 900)
        self.assertEqual(len(conversation_artifacts_context(self.user, 900)), 1)
        self.assertEqual(conversation_artifacts_context(self.user, 901), [])

    # 13. Domain linkage — association tokens are stored and retrievable.
    def test_cert_domain_linkage(self):
        a, _ = store_artifact(self.user, data=b"receipt-bytes", content_type="application/pdf",
                              kind="document", associations=["meal:12", "project:5", "junk"])
        self.assertEqual(sorted(a.associations), ["meal:12", "project:5"])  # 'junk' rejected
        hits = ArtifactQueries.by_association(self.user, "project:5")
        self.assertEqual(len(hits), 1)
        env = get_domain_entity(self.user, "artifacts", entity_type="artifact",
                                filters={"associated_with": "meal:12"})
        self.assertEqual(env["status"], "ready")
