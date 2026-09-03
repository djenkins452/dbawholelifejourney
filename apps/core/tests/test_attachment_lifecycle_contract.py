# ==============================================================================
# File: apps/core/tests/test_attachment_lifecycle_contract.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: A past upload may be history; it may never be presented as the present
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-09-03
# ==============================================================================
"""Production, 2026-09-03. "Mark Charge Watch complete."

The Chief of Staff began: "I'm unable to identify individuals in images, but I can help
with the tasks you mentioned." Nothing was attached to that message. The image was from
the previous day.

The forensic answer was not a model failure and not a conversation_state failure — that
authority had correctly expired hours earlier. Prior uploads were assembled into
`current_context.conversation_artifacts`, and Current Context is, by its own definition,
what is true RIGHT NOW: the clock, the screen, this turn's files. A WLJ conversation never
rolls over — Danny's has been conversation 14 since July — so ten artifacts going back
weeks sat permanently in the present tense with nothing marking them as past.

Stale DATA delivered as current, not stale instruction. The fix is therefore structural
and general: nothing under Current Context may describe a prior turn. History lives in its
own section, states its own age, and stays retrievable.

These tests certify the CLASS. No image type, no task name, no wording is special-cased,
and no provider is called.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.ai.model_interface import conversation_state as cs
from apps.ai.model_interface import telemetry as tel
from apps.ai.models import AssistantConversation
from apps.capture.models import MultimodalArtifact

User = get_user_model()


def _artifact(user, conversation, *, days_ago=0, kind="image", filename="photo.jpg"):
    art = MultimodalArtifact.objects.create(
        user=user, kind=kind, original_filename=filename,
        content_type="image/jpeg", source_conversation_id=conversation.id)
    if days_ago:
        stamp = timezone.now() - timedelta(days=days_ago)
        MultimodalArtifact.objects.filter(pk=art.pk).update(created_at=stamp)
        art.refresh_from_db()
    return art


class Harness(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="att@contract.test", password="x")
        self.conv = AssistantConversation.get_or_create_active(self.user)

    def _svc(self):
        from apps.ai.model_interface.service import ModelInterfaceService
        return ModelInterfaceService(self.user)

    def _context(self, **kw):
        return self._svc().build_standing_context(conversation=self.conv, **kw)


class CurrentContextIsOnlyEverNowTests(Harness):
    """The invariant, stated as a property of the envelope rather than a rule in prose."""

    def test_a_prior_upload_never_appears_under_current_context(self):
        _artifact(self.user, self.conv, days_ago=1)
        current = self._context().get("current_context") or {}
        self.assertNotIn("conversation_artifacts", current,
                         "a previous day's upload is being presented as present")
        self.assertNotIn("attachments", current,
                         "nothing was attached to this turn")

    def test_no_artifact_bearing_key_of_any_name_leaks_into_current_context(self):
        """Certifies the CLASS, not the one key: any future 'recent_images',
        'last_upload', 'pending_files' under Current Context fails here too."""
        _artifact(self.user, self.conv, days_ago=3)
        state = tel.attachment_state(self._context())
        self.assertEqual(state["stray_current_context_file_keys"], [],
                         "a file-bearing key was added to Current Context")

    def test_this_turns_upload_IS_current_and_still_reaches_the_model(self):
        """The fix must not cost the capability it was protecting."""
        art = _artifact(self.user, self.conv)
        ctx = self._context(attachments=[{"artifact_id": art.id, "kind": "image",
                                          "filename": "photo.jpg"}])
        atts = (ctx.get("current_context") or {}).get("attachments") or []
        self.assertEqual([a["artifact_id"] for a in atts], [art.id])

    def test_this_turns_upload_is_not_also_listed_as_history(self):
        art = _artifact(self.user, self.conv)
        ctx = self._context(attachments=[{"artifact_id": art.id, "kind": "image",
                                          "filename": "photo.jpg"}])
        ids = [f["artifact_id"] for f in
               ((ctx.get("artifact_history") or {}).get("files") or [])]
        self.assertNotIn(art.id, ids, "the current upload was duplicated into history")


class HistoryStatesThatItIsHistoryTests(Harness):
    """Retrievable, and honest about what it is."""

    def test_prior_uploads_are_carried_in_their_own_historical_section(self):
        _artifact(self.user, self.conv, days_ago=1, filename="yesterday.jpg")
        history = self._context().get("artifact_history") or {}
        self.assertEqual(history.get("status"), "historical")
        self.assertFalse(history.get("attached_to_current_turn"))
        self.assertEqual(history.get("count"), 1)

    def test_every_file_states_its_own_age(self):
        _artifact(self.user, self.conv, days_ago=4)
        f = ((self._context().get("artifact_history") or {}).get("files") or [])[0]
        self.assertEqual(f["days_ago"], 4)
        self.assertFalse(f["attached_to_current_turn"])
        self.assertIn("uploaded_on", f)

    def test_history_remains_retrievable_rather_than_discarded(self):
        """WLJ keeps what is retrievable; it never decides for the model that an old file
        stopped mattering."""
        art = _artifact(self.user, self.conv, days_ago=40)
        history = self._context().get("artifact_history") or {}
        self.assertIn("get_entity", history.get("retrieve_with", ""))
        self.assertEqual([f["artifact_id"] for f in history["files"]], [art.id])

    def test_a_conversation_with_no_uploads_carries_no_history_section(self):
        self.assertNotIn("artifact_history", self._context())


class LifecycleRegressionTests(Harness):
    """The exact production sequence, as a class:

    image-assisted interaction → lifecycle completed → later unrelated turn →
    CURRENT SITUATION contains no active attachment → nothing model-facing represents
    the old file as current.
    """

    def _current_situation(self, ctx):
        return self._svc()._current_situation(ctx)

    def test_completed_image_lifecycle_then_an_unrelated_later_turn(self):
        art = _artifact(self.user, self.conv, filename="label.jpg")

        # A — the image arrives and is the live subject.
        cs.record_turn(self.conv, attachments=[
            {"artifact_id": art.id, "kind": "image", "filename": "label.jpg"}])
        self.assertTrue((cs.read(self.conv) or {}).get("active_subject"))

        # B — the write it fed succeeds; the lifecycle is complete.
        cs.record_completed_action(self.conv, tool_name="log_food",
                                   summary="Logged it.", target="Food A")
        self.assertIsNone((cs.read(self.conv) or {}).get("active_subject"))

        # C — a later, unrelated turn with nothing attached.
        MultimodalArtifact.objects.filter(pk=art.pk).update(
            created_at=timezone.now() - timedelta(days=1))
        ctx = self._context()

        situation = self._current_situation(ctx)
        self.assertNotIn("label.jpg", situation,
                         "the completed image resurfaced in CURRENT SITUATION")
        self.assertNotIn("ATTACHED THIS TURN", situation)

        current = ctx.get("current_context") or {}
        self.assertNotIn("attachments", current)
        self.assertNotIn("conversation_artifacts", current)

        state = tel.attachment_state(ctx)
        self.assertEqual(state["attached_this_turn"], 0)
        self.assertFalse(state["active_subject_is_artifact"])
        self.assertEqual(state["stray_current_context_file_keys"], [])
        self.assertTrue(state["history_is_marked_historical"],
                        "the old file is present but not declared historical")

    def test_the_old_file_is_still_findable_on_that_later_turn(self):
        """Not represented as current is not the same as hidden."""
        art = _artifact(self.user, self.conv, days_ago=1, filename="label.jpg")
        cs.record_turn(self.conv, attachments=[
            {"artifact_id": art.id, "kind": "image", "filename": "label.jpg"}])
        cs.record_completed_action(self.conv, tool_name="log_food",
                                   summary="Logged it.", target="Food A")
        history = self._context().get("artifact_history") or {}
        self.assertEqual([f["artifact_id"] for f in history["files"]], [art.id])


class Phase2Tests(Harness):
    """Phase 2 judges evidence. A list of past uploads is not evidence."""

    def test_artifact_history_is_declared_away_not_silently_lost(self):
        from apps.ai.model_interface import synthesis
        _artifact(self.user, self.conv, days_ago=2)
        coverage = synthesis.orientation_coverage(self._context())
        self.assertIn("artifact_history", coverage["intentionally_omitted"])
        self.assertEqual(coverage["silently_lost"], [])

    def test_artifact_history_never_reaches_the_phase2_orientation(self):
        from apps.ai.model_interface import synthesis
        _artifact(self.user, self.conv, days_ago=2, filename="stale.jpg")
        self.assertNotIn("stale.jpg",
                         synthesis.build_orientation(self._context()))


class TelemetryShapeTests(SimpleTestCase):
    """The counters that make this class visible in one line, forever."""

    def test_an_empty_envelope_reads_as_nothing_attached(self):
        state = tel.attachment_state({})
        self.assertEqual(state["attached_this_turn"], 0)
        self.assertEqual(state["historical_files"], 0)
        self.assertFalse(state["active_subject_is_artifact"])

    def test_a_stray_file_key_under_current_context_is_reported_by_name(self):
        state = tel.attachment_state(
            {"current_context": {"recent_images": [1, 2], "clock": {}}})
        self.assertEqual(state["stray_current_context_file_keys"], ["recent_images"])

    def test_the_counters_carry_no_filename_or_content(self):
        import json
        blob = json.dumps(tel.attachment_state({
            "current_context": {"attachments": [
                {"artifact_id": 1, "filename": "SECRET-NAME.jpg"}]},
            "artifact_history": {"status": "historical", "count": 2, "files": [
                {"filename": "OTHER-SECRET.jpg", "preview": "PRIVATE TEXT"}]},
        }))
        for leak in ("SECRET-NAME", "OTHER-SECRET", "PRIVATE TEXT"):
            self.assertNotIn(leak, blob)
