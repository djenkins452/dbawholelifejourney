"""
Tests for Artifacts-as-Truth Milestone B1 — conversation linkage + multi-turn.

An artifact remembers the conversation it was first uploaded in; the CoS surfaces
"what you uploaded earlier in THIS conversation" so follow-ups retrieve it
deterministically (no re-attach).
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.multimodal import (
    conversation_artifacts_context,
    link_artifacts_to_conversation,
)
from apps.capture.models import MultimodalArtifact

User = get_user_model()


def _artifact(user, **kw):
    d = dict(sha256=kw.pop("sha", "x" * 64), content_type="application/pdf",
             kind="document", perception_status=MultimodalArtifact.PERCEPTION_DONE,
             extracted_text="Deductible: $1,500. Emergency care covered at 80%.")
    d.update(kw)
    return MultimodalArtifact.objects.create(user=user, **d)


class ConversationLinkTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="c@ex.com", password="x")

    def test_link_sets_first_conversation_only(self):
        a = _artifact(self.user, sha="a" * 64)
        link_artifacts_to_conversation(101, [a.id])
        a.refresh_from_db()
        self.assertEqual(a.source_conversation_id, 101)
        # A later conversation does NOT overwrite the first.
        link_artifacts_to_conversation(202, [a.id])
        a.refresh_from_db()
        self.assertEqual(a.source_conversation_id, 101)

    def test_conversation_context_lists_prior_uploads(self):
        a = _artifact(self.user, sha="a" * 64, original_filename="policy.pdf",
                      source_conversation_id=55)
        _artifact(self.user, sha="b" * 64, original_filename="other.pdf",
                  source_conversation_id=99)  # different conversation
        ctx = conversation_artifacts_context(self.user, 55)
        self.assertEqual(len(ctx), 1)
        self.assertEqual(ctx[0]["filename"], "policy.pdf")
        self.assertTrue(ctx[0]["readable"])
        self.assertIn("Deductible", ctx[0]["preview"])

    def test_excludes_this_turn(self):
        a = _artifact(self.user, sha="a" * 64, source_conversation_id=55)
        b = _artifact(self.user, sha="b" * 64, source_conversation_id=55)
        ctx = conversation_artifacts_context(self.user, 55, exclude_ids=[b.id])
        ids = [c["artifact_id"] for c in ctx]
        self.assertIn(a.id, ids)
        self.assertNotIn(b.id, ids)

    def test_owner_scoped(self):
        other = User.objects.create_user(email="o@ex.com", password="x")
        _artifact(other, sha="a" * 64, source_conversation_id=55)
        self.assertEqual(conversation_artifacts_context(self.user, 55), [])

    def test_pending_shows_processing(self):
        _artifact(self.user, sha="a" * 64, source_conversation_id=55,
                  perception_status=MultimodalArtifact.PERCEPTION_PENDING, extracted_text="")
        ctx = conversation_artifacts_context(self.user, 55)
        self.assertEqual(ctx[0].get("perception"), "processing")
        self.assertNotIn("preview", ctx[0])


class CurrentContextSurfacingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="cc@ex.com", password="x")

    def test_baseline_includes_conversation_artifacts(self):
        from apps.ai.cos_services.current_context import get_current_context_baseline
        from apps.ai.models import AssistantConversation
        conv = AssistantConversation.objects.create(user=self.user)
        _artifact(self.user, sha="a" * 64, original_filename="policy.pdf",
                  source_conversation_id=conv.id)
        baseline = get_current_context_baseline(self.user, conversation=conv)
        self.assertIn("conversation_artifacts", baseline)
        self.assertEqual(baseline["conversation_artifacts"][0]["filename"], "policy.pdf")
