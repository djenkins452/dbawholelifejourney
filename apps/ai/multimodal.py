# ==============================================================================
# File: apps/ai/multimodal.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Multimodal Truth — WLJ's deterministic side of "an arrival path, not a
#              pipeline." OpenAI perceives; WLJ accepts structured CANDIDATES and runs them
#              through the EXISTING truth/action spine.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-11
# ==============================================================================
"""
Multimodal Truth — WLJ's deterministic contributions.

Architecture: an uploaded image/PDF/doc is a new way the model ARRIVES at the SAME intents
and truth reads it already emits. WLJ never interprets pixels. OpenAI extracts candidate
facts/actions (as existing named-intent tool calls tagged with `source_artifact_id` +
`confidence`); WLJ:
  • stores the artifact for provenance + dedup (`store_artifact`),
  • validates the candidate payload deterministically (`validate_weight`, …),
  • detects duplicates (`find_duplicate_weight` + artifact-hash dedup),
  • decides confirmation by POLICY (`requires_confirmation`) — perception uncertainty raises
    the bar; the model never decides,
  • links the resolved record back to the artifact (`link_artifact`).

NO OCR, NO image parsing, NO new intelligence. Everything downstream (execute_intent → UAIO →
audit) is reused. This module is pure and deterministic.
"""

import base64
import hashlib
import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)


# ── Upload ingestion (chat → artifact + perception payload) ──────────────────
def ingest_uploads(user, *, image_data=None, image_mime_type=None, images_list=None):
    """Normalize a chat turn's image uploads into (images, attachments).

    `images`      — list of (base64, mime) tuples the model PERCEIVES this turn.
    `attachments` — list of {artifact_id, content_type, kind} for every stored artifact
                    (provenance-ready). WLJ stores each artifact by content hash BEFORE the
                    model runs, so the artifact_id exists regardless of sync/streaming and can
                    be surfaced into Current Context so the model can cite `source_artifact_id`.

    WLJ never inspects pixels — it only hashes bytes for identity/dedup. Never raises."""
    raw = []
    if images_list:
        raw = [(b64, mime) for (b64, mime) in images_list if b64 and mime]
    elif image_data and image_mime_type:
        raw = [(image_data, image_mime_type)]

    images, attachments = [], []
    for b64, mime in raw:
        images.append((b64, mime))
        try:
            data = base64.b64decode(b64)
        except Exception:  # pragma: no cover - defensive; still surface the image to the model
            data = None
        artifact, _created = store_artifact(user, data=data, content_type=mime, kind="image")
        if artifact is not None:
            attachments.append({
                "artifact_id": artifact.id,
                "content_type": mime,
                "kind": "image",
            })
            # Perception audit line — every artifact the model is about to perceive
            # is recorded (id + content hash + type), so perception is observable
            # and traceable. (A fully queryable perception-as-truth-request audit
            # row is sequenced to the Phase 1 universal-spine milestone.)
            logger.info(
                "multimodal.perceive user=%s artifact=%s sha=%s type=%s kind=image",
                getattr(user, "id", None), artifact.id,
                (artifact.sha256 or "")[:12], mime,
            )
            # Queue durable persistence of the ORIGINAL bytes to object storage in
            # the BACKGROUND — never write to storage on the request path
            # (docs/WLJ_MULTIMODAL_INTAKE_ARCHITECTURE.md §3–§4). safe_enqueue is
            # non-blocking; retrieval tolerates the `pending` window. We enqueue
            # only when bytes exist and the artifact is not already durably stored
            # (idempotent across re-uploads of the same content).
            if data and not artifact.is_durably_stored:
                _queue_artifact_persistence(artifact.id, b64)
    return images, attachments


def _queue_artifact_persistence(artifact_id, b64):
    """Non-blocking enqueue of durable artifact storage. Never raises."""
    try:
        from apps.ai.tasks import persist_artifact_bytes
        from apps.core.celery_utils import safe_enqueue
        safe_enqueue(persist_artifact_bytes, artifact_id, b64)
    except Exception:  # pragma: no cover - defensive; storage is eventual, never blocks a turn
        logger.warning("multimodal._queue_artifact_persistence failed", exc_info=True)


# ── Conversation integrity (the transcript keeps what the user submitted) ────
def attach_images_to_message(message, images):
    """Persist the user's uploaded images ONTO their conversation message so the transcript
    stays a faithful record of what actually happened, independent of the artifact/processing
    lifecycle. `images` is a list of (base64, mime).

    Conversation lifecycle ≠ artifact lifecycle: the MultimodalArtifact may resolve into
    deterministic truth (a WeightEntry) and its bytes may expire for processing/storage
    reasons, but the conversation message keeps the image the user actually sent. Mirrors the
    legacy chat persistence (first image in the message's legacy fields, additional images as
    MessageImage rows, 72h retention — the platform-wide chat-image retention policy). Applies
    to any attachment modality (images/PDFs/screenshots/receipts). Never raises."""
    if not message or not images:
        return
    try:
        from datetime import timedelta

        from django.utils import timezone

        from apps.ai.models import MessageImage
        expires = timezone.now() + timedelta(hours=72)
        first_b64, first_mime = images[0]
        message.image_data = first_b64
        message.image_mime_type = first_mime
        message.image_expires_at = expires
        message.save(update_fields=["image_data", "image_mime_type", "image_expires_at"])
        for idx, (b64, mime) in enumerate(images[1:]):
            MessageImage.objects.create(
                message=message, image_data=b64, image_mime_type=mime,
                image_expires_at=expires, order=idx,
            )
    except Exception:  # pragma: no cover - defensive; transcript persistence must never break a turn
        logger.warning("multimodal.attach_images_to_message failed", exc_info=True)


# ── Artifact store (provenance + artifact-level dedup) ───────────────────────
def store_artifact(user, *, data=None, content_type="", kind="", storage_ref=""):
    """Store (or return the existing) artifact, keyed by content hash. Returns
    (artifact, created); created=False means the SAME content was already uploaded
    (artifact-level dedup). `data` is raw bytes — WLJ hashes it for identity/integrity and
    never inspects the content. Never raises."""
    from apps.capture.models import MultimodalArtifact
    sha = hashlib.sha256(data).hexdigest() if data else ""
    try:
        artifact, created = MultimodalArtifact.objects.get_or_create(
            user=user, sha256=sha,
            defaults={"content_type": content_type, "kind": kind,
                      "storage_ref": storage_ref},
        )
        return artifact, created
    except Exception:  # pragma: no cover - defensive
        logger.warning("multimodal.store_artifact failed", exc_info=True)
        return None, False


def artifact_resolved_weight(user, artifact_id):
    """Artifact-level IDEMPOTENCY for weight. If this exact image already produced a LIVE
    WeightEntry, return it — re-submitting the SAME photo can NEVER create a second health
    entry (the same image is one measurement event, not two). This removes the condition that
    let a re-upload become a duplicate, even through a confirmation. Returns the WeightEntry or
    None (nothing resolved, or the entry was since deleted → a fresh log is then legitimate)."""
    if not artifact_id:
        return None
    try:
        from apps.capture.models import MultimodalArtifact
        from apps.health.models import WeightEntry
        art = MultimodalArtifact.objects.filter(
            id=artifact_id, user=user, status="resolved",
            resolved_intent="log_weight", resolved_object_type="WeightEntry",
        ).values_list("resolved_object_id", flat=True).first()
        if not art:
            return None
        return WeightEntry.objects.filter(id=art, user=user, status="active").first()
    except Exception:  # pragma: no cover - defensive
        return None


def link_artifact(artifact_id, *, intent, object_type, object_id):
    """Record the deterministic record an artifact produced (provenance chain). Never raises."""
    if not artifact_id:
        return
    try:
        from apps.capture.models import MultimodalArtifact
        MultimodalArtifact.objects.filter(id=artifact_id).update(
            status="resolved", resolved_intent=intent,
            resolved_object_type=object_type, resolved_object_id=object_id,
        )
    except Exception:  # pragma: no cover - defensive
        logger.debug("multimodal.link_artifact skipped", exc_info=True)


# ── Deterministic validation (WLJ validates the EXTRACTION, never re-extracts) ─
_WEIGHT_RANGE = {"lb": (40.0, 1000.0), "kg": (18.0, 450.0)}


def validate_weight(value, unit):
    """Plausibility gate for a weight candidate. Rejects an implausible extraction so a
    misread photo never becomes truth. Returns True when the value is a plausible weight."""
    lo, hi = _WEIGHT_RANGE.get(unit, _WEIGHT_RANGE["lb"])
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False
    return lo <= v <= hi


def find_duplicate_weight(user, value, unit, *, window_minutes=180):
    """Fact-level dedup: an equal weight already recorded within the window. Returns the
    existing entry or None. WLJ dedups deterministically; the model never does."""
    try:
        from django.utils import timezone

        from apps.health.models import WeightEntry
        cutoff = timezone.now() - timedelta(minutes=window_minutes)
        return WeightEntry.objects.filter(
            user=user, unit=unit, recorded_at__gte=cutoff,
            value=Decimal(str(value)),
        ).first()
    except (InvalidOperation, Exception):  # pragma: no cover - defensive
        return None


# ── Confirmation POLICY (WLJ owns the decision; the model only proposes) ──────
# Intents that write clinical / financial / identity truth ALWAYS confirm from an image —
# perception can misread and these are trust-critical.
_ALWAYS_CONFIRM_INTENTS = frozenset({
    "log_glucose", "log_blood_pressure", "log_labs", "add_medication",
    "log_expense", "add_transaction", "add_contact", "add_insurance_card",
    "add_identity_document",
})
_CONFIDENCE_FLOOR = 0.85


def requires_confirmation(intent, *, confidence=None, duplicate=False,
                          source_artifact_id=None):
    """Deterministic confirmation decision for a multimodal candidate. Confirm when: the
    intent writes clinical/financial/identity truth; OR perception `confidence` is below the
    floor; OR a duplicate is suspected. High-confidence, low-risk, reversible writes may
    auto-execute (with an undo affordance). Non-multimodal calls (no artifact) are unaffected."""
    if not source_artifact_id:
        return False  # normal typed path — existing behavior
    if duplicate:
        return True
    if intent in _ALWAYS_CONFIRM_INTENTS:
        return True
    if confidence is not None:
        try:
            if float(confidence) < _CONFIDENCE_FLOOR:
                return True
        except (TypeError, ValueError):
            return True  # unparseable confidence → be safe, confirm
    return False
