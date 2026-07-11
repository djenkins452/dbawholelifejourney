"""Multimodal wiring (slice 1b) — the LIVE end-to-end path for the scale photo.

Slice 1 built the deterministic spine (store/validate/dedup/confirm/link — see
`test_multimodal.py`). Slice 1b connects that spine to the model-interface chat runtime so a
real uploaded scale photo produces a `log_weight` write in production:

  chat view → CoSGateway → ModelInterfaceRuntime.respond
    → multimodal.ingest_uploads (store artifact + perception payload)
    → generate(images=…, attachments=…)            [sync AND streaming]
    → Current Context carries the artifact as the turn's attachment
    → model calls log_weight(value, unit, source_artifact_id, confidence)
    → action_execution → handle_log_weight → validate → dedup → confirm POLICY
    → (bound confirmation round-trip) → WeightEntry + provenance link + audit

The perception half (OpenAI actually reading the pixels) is the model's and is NOT unit-tested;
these tests mock generation where the model would run and exercise every deterministic seam the
live turn depends on.
"""
import base64
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.ai import multimodal
from apps.ai.cos_gateway import CoSGateway, SURFACE_CHAT, SURFACE_CHAT_STREAM
from apps.ai.cos_gateway.envelope import RUNTIME_MODEL_INTERFACE
from apps.ai.cos_gateway.runtime import ModelInterfaceRuntime
from apps.ai.cos_services import action_interface
from apps.ai.cos_services.action_execution import execute_action
from apps.ai.cos_services.current_context import get_current_context_baseline
from apps.capture.models import MultimodalArtifact
from apps.health.models import WeightEntry

User = get_user_model()

_PNG_BYTES = b"\x89PNG\r\n\x1a\nfake-scale-photo"
_PNG_B64 = base64.b64encode(_PNG_BYTES).decode("utf-8")


def _make_user(email):
    from django.conf import settings

    from apps.users.models import TermsAcceptance
    user = User.objects.create_user(email=email, password="x")
    TermsAcceptance.objects.create(
        user=user, terms_version=settings.WLJ_SETTINGS["TERMS_VERSION"])
    prefs = user.preferences
    prefs.use_model_interface = True
    prefs.has_completed_onboarding = True
    # Personal-assistant prerequisites so the chat endpoints run (not the enable-gate).
    prefs.ai_enabled = True
    prefs.ai_data_consent = True
    prefs.personal_assistant_enabled = True
    prefs.personal_assistant_consent = True
    prefs.save()
    return user


class RuntimeWiringTests(TestCase):
    """Images reach the model-interface runtime and are stored as artifacts (sync + stream)."""

    def setUp(self):
        self.user = _make_user("mmwire@example.com")

    def test_1_and_15_model_interface_owns_image_turn_not_legacy(self):
        # For a use_model_interface user the gateway resolves the model-interface runtime —
        # image turns are NEVER routed to legacy Beth.
        runtime = CoSGateway.resolve_runtime(self.user)
        self.assertEqual(runtime.name, RUNTIME_MODEL_INTERFACE)

    def test_1_image_reaches_generate_sync(self):
        with mock.patch(
            "apps.ai.model_interface.service.ModelInterfaceService.generate",
            return_value={"answer": "Logged.", "tools_called": ["log_weight"]},
        ) as gen:
            ModelInterfaceRuntime().respond(
                user=self.user, surface=SURFACE_CHAT, message="log my weight",
                images_list=[(_PNG_B64, "image/png")],
            )
        self.assertTrue(gen.called)
        _, kwargs = gen.call_args
        self.assertTrue(kwargs.get("images"), "generate must receive the image payload")
        self.assertEqual(kwargs["images"][0][0], _PNG_B64)
        self.assertTrue(kwargs.get("attachments"), "generate must receive the attachment(s)")
        self.assertIn("artifact_id", kwargs["attachments"][0])

    def test_2_artifact_created_on_upload(self):
        with mock.patch(
            "apps.ai.model_interface.service.ModelInterfaceService.generate",
            return_value={"answer": "ok", "tools_called": []},
        ):
            ModelInterfaceRuntime().respond(
                user=self.user, surface=SURFACE_CHAT, message="here is my scale",
                image_data=_PNG_B64, image_mime_type="image/png",
            )
        art = MultimodalArtifact.objects.filter(user=self.user).first()
        self.assertIsNotNone(art)
        self.assertEqual(art.content_type, "image/png")
        self.assertEqual(len(art.sha256), 64)

    def test_13_streaming_passes_images_and_attachments(self):
        with mock.patch(
            "apps.ai.model_interface.tasks.run_model_interface_generation.delay",
        ) as delay:
            ModelInterfaceRuntime().respond(
                user=self.user, surface=SURFACE_CHAT_STREAM, message="log it",
                stream=True, image_data=_PNG_B64, image_mime_type="image/png",
            )
        self.assertTrue(delay.called)
        _, kwargs = delay.call_args
        self.assertTrue(kwargs.get("images"))
        self.assertTrue(kwargs.get("attachments"))
        self.assertIn("artifact_id", kwargs["attachments"][0])
        # The artifact is stored BEFORE the async task, so provenance exists regardless of path.
        self.assertEqual(MultimodalArtifact.objects.filter(user=self.user).count(), 1)

    def test_ingest_uploads_dedups_and_returns_payload(self):
        images, attachments = multimodal.ingest_uploads(
            self.user, image_data=_PNG_B64, image_mime_type="image/png")
        self.assertEqual(images, [(_PNG_B64, "image/png")])
        self.assertEqual(len(attachments), 1)
        # Same bytes again → SAME artifact row (artifact-level dedup), still one attachment.
        images2, attachments2 = multimodal.ingest_uploads(
            self.user, image_data=_PNG_B64, image_mime_type="image/png")
        self.assertEqual(attachments2[0]["artifact_id"], attachments[0]["artifact_id"])
        self.assertEqual(MultimodalArtifact.objects.filter(user=self.user).count(), 1)


class StreamingViewTransportTests(TestCase):
    """The streaming chat endpoint (the path CoS/model-interface users take) must carry the
    image from the JSON body to the gateway — this is where the first live test dropped it."""

    def setUp(self):
        self.user = _make_user("mmstream@example.com")
        self.client.force_login(self.user)

    def test_streaming_view_forwards_image_to_gateway(self):
        import json as _json

        class _Env:
            stream_job_id = "job-x"
            meta = {"conversation_id": 1}

        with mock.patch("apps.ai.cos_gateway.CoSGateway.respond",
                        return_value=_Env()) as respond, \
                mock.patch("apps.ai.views._chat_relay_stream", return_value=iter([])):
            resp = self.client.post(
                "/assistant/api/chat/stream/",
                data=_json.dumps({
                    "message": "log my weight",
                    "page_context": {},
                    "images": [{"data": _PNG_B64, "mime": "image/png"}],
                }),
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(respond.called)
        _, kwargs = respond.call_args
        # The image reached the gateway (single image → singular fields populated).
        self.assertEqual(kwargs.get("image_data"), _PNG_B64)
        self.assertEqual(kwargs.get("image_mime_type"), "image/png")
        self.assertTrue(kwargs.get("stream"))


class CurrentContextAttachmentTests(TestCase):
    """The artifact is surfaced into Current Context as the turn's attachment/focus."""

    def setUp(self):
        self.user = _make_user("mmctx@example.com")

    def test_3_artifact_id_reaches_current_context(self):
        attachments = [{"artifact_id": 77, "content_type": "image/png", "kind": "image"}]
        baseline = get_current_context_baseline(self.user, attachments=attachments)
        self.assertIn("attachments", baseline)
        self.assertEqual(baseline["attachments"][0]["artifact_id"], 77)

    def test_typed_turn_has_no_attachments_key(self):
        baseline = get_current_context_baseline(self.user)
        self.assertNotIn("attachments", baseline)


class DeterministicActionPathTests(TestCase):
    """The model's proposed candidate routes through the model-interface action path
    (action_interface.request_action → execute_action → handle_log_weight)."""

    def setUp(self):
        self.user = _make_user("mmact@example.com")
        self._seq = 0

    def _art(self):
        # A distinct artifact per call (unique bytes) so artifact-hash dedup never collides
        # across the scenarios in this class.
        self._seq += 1
        art, _ = multimodal.store_artifact(
            self.user, data=f"scale-bytes-{self._seq}".encode(),
            content_type="image/png", kind="image")
        return art

    def test_4_and_5_high_confidence_valid_write(self):
        art = self._art()
        out = action_interface.request_action(
            self.user, "log_weight",
            {"value": 182.4, "unit": "lb",
             "source_artifact_id": art.id, "confidence": 0.96},
        )
        self.assertEqual(out["status"], "ok", out)
        entry = WeightEntry.objects.filter(user=self.user, status="active").first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.value, Decimal("182.4"))

    def test_12_provenance_link_to_created_entry(self):
        art = self._art()
        action_interface.request_action(
            self.user, "log_weight",
            {"value": 175, "unit": "lb", "source_artifact_id": art.id, "confidence": 0.97},
        )
        entry = WeightEntry.objects.filter(user=self.user, status="active").first()
        art.refresh_from_db()
        self.assertEqual(art.status, "resolved")
        self.assertEqual(art.resolved_intent, "log_weight")
        self.assertEqual(art.resolved_object_type, "WeightEntry")
        self.assertEqual(art.resolved_object_id, entry.id)

    def test_6_low_confidence_requires_confirmation(self):
        art = self._art()
        out = action_interface.request_action(
            self.user, "log_weight",
            {"value": 182, "unit": "lb", "source_artifact_id": art.id, "confidence": 0.5},
        )
        self.assertEqual(out["status"], "confirmation_required", out)
        self.assertIn("confirmation", out)
        self.assertIn("confirmation_id", out["confirmation"])
        # No write happened while awaiting confirmation.
        self.assertEqual(WeightEntry.objects.filter(user=self.user, status="active").count(), 0)

    def test_7_confirmation_approval_writes_and_links(self):
        art = self._art()
        out = action_interface.request_action(
            self.user, "log_weight",
            {"value": 199, "unit": "lb", "source_artifact_id": art.id, "confidence": 0.4},
        )
        cid = out["confirmation"]["confirmation_id"]
        resolved = action_interface.resolve_pending_action(self.user, cid, confirm=True)
        self.assertEqual(resolved["status"], "ok", resolved)
        entry = WeightEntry.objects.filter(user=self.user, status="active").first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.value, Decimal("199"))
        art.refresh_from_db()
        self.assertEqual(art.resolved_object_id, entry.id)

    def test_8_confirmation_rejection_no_write(self):
        art = self._art()
        out = action_interface.request_action(
            self.user, "log_weight",
            {"value": 205, "unit": "lb", "source_artifact_id": art.id, "confidence": 0.3},
        )
        cid = out["confirmation"]["confirmation_id"]
        resolved = action_interface.resolve_pending_action(self.user, cid, confirm=False)
        self.assertEqual(resolved["status"], "declined", resolved)
        self.assertEqual(WeightEntry.objects.filter(user=self.user, status="active").count(), 0)

    def test_9_implausible_value_rejected_not_confirmed(self):
        art = self._art()
        out = action_interface.request_action(
            self.user, "log_weight",
            {"value": 4000, "unit": "lb", "source_artifact_id": art.id, "confidence": 0.99},
        )
        # A misread is a validation event — rejected outright, never a confirmation prompt.
        self.assertEqual(out["status"], "error", out)
        self.assertNotEqual(out["status"], "confirmation_required")
        self.assertEqual(WeightEntry.objects.filter(user=self.user, status="active").count(), 0)

    def test_10_artifact_level_duplicate(self):
        a1, c1 = multimodal.store_artifact(self.user, data=b"same", content_type="image/png")
        a2, c2 = multimodal.store_artifact(self.user, data=b"same", content_type="image/png")
        self.assertTrue(c1)
        self.assertFalse(c2)
        self.assertEqual(a1.id, a2.id)

    def test_11_fact_level_duplicate_requires_confirmation(self):
        # An equal weight already recorded a moment ago → the image candidate must confirm.
        WeightEntry.objects.create(
            user=self.user, value=Decimal("182"), unit="lb", recorded_at=timezone.now())
        art = self._art()
        out = action_interface.request_action(
            self.user, "log_weight",
            {"value": 182, "unit": "lb", "source_artifact_id": art.id, "confidence": 0.99},
        )
        self.assertEqual(out["status"], "confirmation_required", out)
        # Still just the one pre-existing entry — no duplicate written.
        self.assertEqual(WeightEntry.objects.filter(user=self.user, status="active").count(), 1)

    def test_14_typed_weight_logging_unchanged(self):
        # No source_artifact_id → the normal typed path: write immediately, never confirm.
        out = action_interface.request_action(
            self.user, "log_weight", {"value": 168, "unit": "lb"},
        )
        self.assertEqual(out["status"], "ok", out)
        entry = WeightEntry.objects.filter(user=self.user, status="active").first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.value, Decimal("168"))

    def test_log_weight_is_allowlisted(self):
        # execute_action gate: log_weight must be enabled for the assistant action path.
        out = execute_action(self.user, "log_weight", {"value": 170, "unit": "lb"})
        self.assertEqual(out["status"], "success", out)
