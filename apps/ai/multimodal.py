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


# How much extracted document text to surface INLINE per attachment (the full
# text is stored on the artifact; this bounds what rides in a single turn's
# context). ~60K chars ≈ ~15K tokens — a ~30-page document.
_INLINE_TEXT_CHARS = 60_000


def attachments_from_ids(user, attachment_ids):
    """Resolve pre-uploaded artifact ids (created by the upload endpoint) into the
    attachments-as-data shape the arrival path surfaces to the model. For a
    document that WLJ has deterministically perceived, this includes the extracted
    `text` (bounded) so the model can read/summarize/answer — WLJ decodes, the
    model reasons. USER-SCOPED — the query is the ownership boundary. Never raises."""
    if not attachment_ids:
        return []
    out = []
    try:
        from apps.capture.models import MultimodalArtifact
        rows = MultimodalArtifact.objects.filter(
            id__in=list(attachment_ids), user=user,
        )
        for a in rows:
            item = {
                "artifact_id": a.id,
                "content_type": a.content_type,
                "kind": a.kind,
            }
            if a.page_count:
                item["page_count"] = a.page_count
            # Surface deterministic perception so the model can read documents.
            if a.has_perception:
                text = a.extracted_text or ""
                if len(text) > _INLINE_TEXT_CHARS:
                    item["text"] = text[:_INLINE_TEXT_CHARS]
                    item["text_truncated"] = True
                else:
                    item["text"] = text
            elif a.perception_pending:
                item["perception"] = "processing"   # honest eventual-consistency signal
            elif a.perception_status == MultimodalArtifact.PERCEPTION_UNSUPPORTED:
                item["perception"] = "unreadable"    # e.g. scanned/image-only PDF (OCR later)
            out.append(item)
    except Exception:  # pragma: no cover - defensive; never break a turn
        logger.warning("multimodal.attachments_from_ids failed", exc_info=True)
    return out


def _queue_artifact_perception(artifact_id, b64):
    """Non-blocking enqueue of deterministic text extraction. Never raises."""
    try:
        from apps.ai.tasks import perceive_artifact
        from apps.core.celery_utils import safe_enqueue
        safe_enqueue(perceive_artifact, artifact_id, b64)
    except Exception:  # pragma: no cover - defensive; perception is eventual
        logger.warning("multimodal._queue_artifact_perception failed", exc_info=True)


def perceive_images_for_artifacts(user, artifact_ids, *, max_total=8):
    """Load the VISUAL bytes the model needs to RE-PERCEIVE retrieved artifacts:
    an image artifact's original bytes (from durable storage) and a video
    artifact's sampled frames. Returns [(base64, mime)] — the image-path shape the
    tool loop injects so the model can actually SEE a previously-uploaded
    image/video (not just read metadata). USER-SCOPED; bounded. Never raises."""
    if not artifact_ids:
        return []
    out = []
    try:
        from django.core.files.storage import default_storage

        from apps.capture.models import MultimodalArtifact
        rows = (MultimodalArtifact.objects
                .filter(id__in=list(artifact_ids), user=user)
                .exclude(status="rejected"))
        for a in rows:
            if a.kind == "image" and a.is_durably_stored:
                try:
                    with default_storage.open(a.storage_ref, "rb") as fh:
                        out.append((base64.b64encode(fh.read()).decode("utf-8"),
                                    a.content_type or "image/jpeg"))
                except Exception:
                    logger.warning("perceive_images: image read failed id=%s", a.id)
            elif a.kind == "video":
                for fr in (a.frames or []):
                    b64 = fr.get("b64") if isinstance(fr, dict) else None
                    if b64:
                        out.append((b64, "image/jpeg"))
                        if len(out) >= max_total:
                            return out
            if len(out) >= max_total:
                return out
    except Exception:  # pragma: no cover - defensive; never break a turn
        logger.warning("multimodal.perceive_images_for_artifacts failed", exc_info=True)
    return out


def artifact_ids_from_entity_envelope(raw):
    """Extract artifact ids from a get_domain_entity envelope (single `entity` or a
    list of `entities`), reading each entity's `definition.artifact_id`. Used to
    decide which retrieved artifacts need visual re-delivery. Never raises."""
    ids = []
    if not isinstance(raw, dict):
        return ids
    ents = []
    if isinstance(raw.get("entity"), dict):
        ents = [raw["entity"]]
    elif isinstance(raw.get("entities"), list):
        ents = raw["entities"]
    for e in ents:
        if isinstance(e, dict):
            aid = (e.get("definition") or {}).get("artifact_id")
            if aid:
                ids.append(aid)
    return ids


def link_artifacts_to_conversation(conversation_id, artifact_ids):
    """Record the conversation an artifact was first uploaded/referenced in (only
    sets it once — the FIRST conversation). Enables multi-turn retrieval: the CoS
    surfaces this conversation's artifacts so follow-ups need no re-attach.
    Never raises."""
    if not conversation_id or not artifact_ids:
        return
    try:
        from apps.capture.models import MultimodalArtifact
        (MultimodalArtifact.objects
         .filter(id__in=list(artifact_ids), source_conversation_id__isnull=True)
         .update(source_conversation_id=conversation_id))
    except Exception:  # pragma: no cover - defensive; never break a turn
        logger.warning("multimodal.link_artifacts_to_conversation failed", exc_info=True)


def conversation_artifacts_context(user, conversation_id, *, exclude_ids=(), limit=10):
    """Compact list of artifacts uploaded EARLIER in this conversation (excluding
    this turn's), so the model always knows what it can retrieve for a follow-up.
    Each item is lightweight (id, filename, kind, readable, short preview) — the
    model calls get_entity(domain='artifacts') for the full content. Never raises."""
    if not conversation_id:
        return []
    out = []
    try:
        from apps.capture.models import MultimodalArtifact
        rows = (MultimodalArtifact.objects
                .filter(user=user, source_conversation_id=conversation_id)
                .exclude(id__in=list(exclude_ids) or [])
                .exclude(status="duplicate").exclude(status="rejected")
                .order_by("-created_at")[:limit])
        for a in rows:
            item = {
                "artifact_id": a.id,
                "filename": a.original_filename or None,
                "kind": a.kind or "artifact",
                "content_type": a.content_type,
                "uploaded_at": a.created_at.isoformat(),
                "readable": bool(a.has_perception),
            }
            if a.has_perception and a.extracted_text:
                item["preview"] = a.extracted_text[:280]
            elif a.perception_pending:
                item["perception"] = "processing"
            out.append(item)
    except Exception:  # pragma: no cover - defensive
        logger.warning("multimodal.conversation_artifacts_context failed", exc_info=True)
    return out


def frames_for_attachments(user, attachment_ids, *, max_total=16):
    """Return sampled VIDEO frames as image tuples [(b64, 'image/jpeg')] for the
    referenced video artifacts, so the model can SEE them through the normal image
    path (image_url). WLJ decoded these frames deterministically; the model reasons
    over the visual sequence. USER-SCOPED; bounded. Never raises."""
    if not attachment_ids:
        return []
    out = []
    try:
        from apps.capture.models import MultimodalArtifact
        rows = (MultimodalArtifact.objects
                .filter(id__in=list(attachment_ids), user=user, kind="video")
                .exclude(frames=[]))
        for a in rows:
            for fr in (a.frames or []):
                b64 = fr.get("b64") if isinstance(fr, dict) else None
                if b64:
                    out.append((b64, "image/jpeg"))
                    if len(out) >= max_total:
                        return out
    except Exception:  # pragma: no cover - defensive; never break a turn
        logger.warning("multimodal.frames_for_attachments failed", exc_info=True)
    return out


_ASSOC_RE = None


def _clean_associations(associations):
    """Normalize association tokens to a de-duped list of 'domain:id' strings.
    Rejects anything not shaped like a canonical-entity reference."""
    import re
    global _ASSOC_RE
    if _ASSOC_RE is None:
        _ASSOC_RE = re.compile(r"^[a-z_]+:[A-Za-z0-9_-]+$")
    out = []
    for tok in (associations or []):
        t = str(tok).strip().lower()
        if _ASSOC_RE.match(t) and t not in out:
            out.append(t)
        if len(out) >= 20:
            break
    return out


def store_and_persist_artifact(user, *, data, content_type, kind, original_filename="",
                               associations=None):
    """Shared intake primitive: store an artifact (sha256 dedup + provenance),
    queue durable persistence of its bytes, AND queue deterministic perception
    (text extraction) for perceivable types — all in the background. Used by BOTH
    the chat arrival path and the dedicated upload endpoint, so every attachment
    travels through this same platform; only the perception STEP varies by type.
    Returns (artifact, created). Never blocks; never raises for storage reasons."""
    from apps.ai.perception import is_perceivable

    artifact, created = store_artifact(
        user, data=data, content_type=content_type, kind=kind,
        original_filename=original_filename, associations=associations,
    )
    if artifact is not None and data:
        b64 = base64.b64encode(data).decode("utf-8")
        if not artifact.is_durably_stored:
            _queue_artifact_persistence(artifact.id, b64)
        # Deterministic perception (background). Only enqueue for types we can
        # extract today; others store + surface without text until their
        # extractor lands (perception_status stays 'none').
        if is_perceivable(content_type) and not artifact.has_perception:
            from apps.capture.models import MultimodalArtifact
            if artifact.perception_status != MultimodalArtifact.PERCEPTION_PENDING:
                artifact.perception_status = MultimodalArtifact.PERCEPTION_PENDING
                artifact.save(update_fields=["perception_status"])
            _queue_artifact_perception(artifact.id, b64)
    return artifact, created


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
def store_artifact(user, *, data=None, content_type="", kind="", storage_ref="",
                   original_filename="", associations=None):
    """Store (or return the existing) artifact, keyed by content hash. Returns
    (artifact, created); created=False means the SAME content was already uploaded
    (artifact-level dedup). `data` is raw bytes — WLJ hashes it for identity/integrity and
    never inspects the content. Never raises."""
    from apps.capture.models import MultimodalArtifact
    sha = hashlib.sha256(data).hexdigest() if data else ""
    assoc = _clean_associations(associations)
    try:
        artifact, created = MultimodalArtifact.objects.get_or_create(
            user=user, sha256=sha,
            defaults={"content_type": content_type, "kind": kind,
                      "storage_ref": storage_ref,
                      "original_filename": (original_filename or "")[:255],
                      "associations": assoc},
        )
        # Same content re-uploaded WITH a new association (e.g. attached to a
        # different meal/project) — merge the new links onto the existing artifact.
        if not created and assoc:
            merged = list(dict.fromkeys((artifact.associations or []) + assoc))
            if merged != (artifact.associations or []):
                artifact.associations = merged
                artifact.save(update_fields=["associations"])
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


# ── Body measurement SESSION capture (source-agnostic: screenshot / photo / voice / typed) ─
# WLJ owns the canonical circumference names; the model perceives, WLJ validates the
# extraction, always confirms, then the handler persists ONE grouped session.
_BODY_CIRCUMFERENCE_METRICS = {
    "neck", "shoulders", "chest", "waist", "abdomen", "hips",
    "arm_left", "arm_right", "forearm_left", "forearm_right",
    "thigh_left", "thigh_right", "calf_left", "calf_right",
}
_BODY_PCT_METRICS = {"body_fat_pct", "body_water_pct"}
_BODY_MASS_METRICS = {"lean_mass", "fat_mass", "skeletal_muscle_mass", "bone_mass"}
_BODY_OTHER_METRICS = {"bmr", "metabolic_age", "visceral_fat", "bmi"}
BODY_METRICS = (
    _BODY_CIRCUMFERENCE_METRICS | _BODY_PCT_METRICS | _BODY_MASS_METRICS | _BODY_OTHER_METRICS
)

_SIDE_ALIASES = {"l": "left", "left": "left", "r": "right", "right": "right"}
_PART_ALIASES = {
    "bicep": "arm", "biceps": "arm", "arm": "arm", "forearm": "forearm",
    "thigh": "thigh", "calf": "calf", "calves": "calf",
}
# Whole-word label aliases (WLJ's canonical circumferences are PLURAL for shoulders/hips,
# but device screens show the SINGULAR: 'Shoulder', 'Hip'). Vision emits the on-screen label,
# so without these a real measurement is silently dropped at normalization. (Origin: the
# 2026-07-19 "Shoulder: not measured" defect — screenshot said 'Shoulder', canonical is 'shoulders'.)
_WHOLE_METRIC_ALIASES = {
    "shoulder": "shoulders",
    "hip": "hips",
    "ab": "abdomen", "abs": "abdomen", "stomach": "abdomen", "belly": "abdomen",
    "tummy": "abdomen", "midsection": "abdomen",
    "waist_hip_ratio": None, "whr": None,  # derived on read — intentionally not stored
}


def is_derived_metric(raw):
    """True when a label is a DERIVED quantity WLJ recomputes on read (waist-hip ratio) and
    must NOT be stored — distinct from an UNRECOGNIZED label (which must be surfaced, not
    silently dropped). Lets the caller skip WHR quietly but flag genuinely unknown metrics."""
    if not raw:
        return False
    key = str(raw).strip().lower().replace("-", "_").replace(" ", "_")
    return "whr" in key or "ratio" in key


def normalize_body_metric(raw):
    """Map a raw metric label to WLJ's canonical circumference/composition name, or None
    for anything unknown or DERIVED (e.g. waist-hip ratio — WLJ derives WHR from waist/hips
    on read, never stores it). WLJ owns the canonical names ('arm_left', never 'bicep';
    'shoulders'/'hips' plural, even though screens show the singular)."""
    if not raw:
        return None
    key = str(raw).strip().lower().replace("-", "_").replace(" ", "_")
    while "__" in key:
        key = key.replace("__", "_")
    if key in BODY_METRICS:
        return key
    if key in _WHOLE_METRIC_ALIASES:            # singular→plural + synonyms (None for derived)
        return _WHOLE_METRIC_ALIASES[key]
    if "whr" in key or "ratio" in key:
        return None  # derived on read, never stored
    # Sided aliases: 'l_bicep' → 'arm_left', 'left_forearm' → 'forearm_left', 'r_calf' → 'calf_right'.
    side = part = None
    for tok in key.split("_"):
        if tok in _SIDE_ALIASES and side is None:
            side = _SIDE_ALIASES[tok]
        elif tok in _PART_ALIASES:
            part = _PART_ALIASES[tok]
    if part and side:
        cand = f"{part}_{side}"
        if cand in BODY_METRICS:
            return cand
    return None


def default_body_unit(metric):
    """The unit WLJ assumes when the source didn't state one."""
    if metric in _BODY_CIRCUMFERENCE_METRICS:
        return "in"
    if metric in _BODY_PCT_METRICS:
        return "pct"
    if metric in _BODY_MASS_METRICS:
        return "lb"
    return {"bmr": "kcal", "metabolic_age": "years", "visceral_fat": "index"}.get(metric, "")


def body_metric_label(metric):
    """Human label for a canonical metric (reuses the Body Intelligence label map)."""
    try:
        from apps.health.services.body_composition_snapshot import METRIC_LABELS
        if metric in METRIC_LABELS:
            return METRIC_LABELS[metric]
    except Exception:  # pragma: no cover - defensive
        pass
    return (metric or "").replace("_", " ").title()


def is_absent_measurement(value):
    """A source row that means 'not measured' — WLJ must treat '--' / blank / 0 as ABSENT,
    never as a real zero circumference (a Renpho screenshot shows unfilled parts as '--'/'0.00')."""
    if value is None:
        return True
    s = str(value).strip()
    if s in ("", "--", "—", "-", "0", "0.0", "0.00", "N/A", "n/a", "null", "None"):
        return True
    try:
        return float(value) == 0.0
    except (TypeError, ValueError):
        return True  # unparseable → skip, don't store garbage


def validate_body_measurement(metric, value, unit):
    """Plausibility gate for ONE measurement candidate (assumes not absent). Rejects a
    misread value so it never becomes truth. Ranges are deliberately wide — a gate, not
    a precision check."""
    if metric not in BODY_METRICS:
        return False
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False
    if v <= 0:
        return False
    u = (unit or "").lower()
    if metric in _BODY_CIRCUMFERENCE_METRICS:
        return 5.0 <= v <= 260.0 if u == "cm" else 2.0 <= v <= 100.0
    if metric in _BODY_PCT_METRICS:
        return 1.0 <= v <= 75.0
    if metric in _BODY_MASS_METRICS:
        return 0.2 <= v <= 300.0 if u == "kg" else 0.5 <= v <= 600.0
    if metric == "bmr":
        return 500.0 <= v <= 5000.0
    if metric == "metabolic_age":
        return 5.0 <= v <= 120.0
    if metric == "visceral_fat":
        return 1.0 <= v <= 60.0
    if metric == "bmi":
        return 8.0 <= v <= 90.0
    return True


def is_low_confidence(conf):
    """Whether a per-measurement perception confidence is below the floor (→ flag for the
    user to verify in the review card). Missing confidence is treated as confident."""
    if conf is None:
        return False
    try:
        return float(conf) < _CONFIDENCE_FLOOR
    except (TypeError, ValueError):
        return True


def map_measurement_source(source):
    """Map free-text source ('Renpho Screenshot', 'InBody', …) to a canonical source choice
    valid for BOTH BodyMeasurementSession and BodyCompositionEntry."""
    s = (source or "").strip().lower()
    if "renpho" in s:
        return "renpho"
    if "inbody" in s:
        return "inbody"
    if "apple" in s or "health" in s:
        return "apple_health"
    if "dexa" in s:
        return "dexa_scan"
    if "withings" in s or "scale" in s:
        return "smart_scale"
    return "other"


def derive_whr(measurements):
    """Derive waist-hip ratio from validated measurements (waist ÷ hips), for DISPLAY only.
    Returns a rounded float or None. WHR is never stored — always recomputed from the two
    canonical circumferences, so it can never drift."""
    vals = {m.get("metric"): m.get("value") for m in (measurements or [])}
    try:
        waist, hips = float(vals.get("waist")), float(vals.get("hips"))
        if waist > 0 and hips > 0:
            return round(waist / hips, 2)
    except (TypeError, ValueError):
        pass
    return None


def artifact_resolved_measurement_session(user, artifact_id):
    """Artifact-level IDEMPOTENCY for a measurement session. If this exact screenshot already
    produced a LIVE BodyMeasurementSession, return it — re-uploading the SAME image can never
    create a second session. Returns the session or None (nothing resolved, or since deleted)."""
    if not artifact_id:
        return None
    try:
        from apps.capture.models import MultimodalArtifact
        from apps.health.models import BodyMeasurementSession
        sid = MultimodalArtifact.objects.filter(
            id=artifact_id, user=user, status="resolved",
            resolved_intent="log_body_measurements",
            resolved_object_type="BodyMeasurementSession",
        ).values_list("resolved_object_id", flat=True).first()
        if not sid:
            return None
        return BodyMeasurementSession.objects.filter(
            id=sid, user=user, status="active",
        ).first()
    except Exception:  # pragma: no cover - defensive
        return None


# ── Confirmation POLICY (WLJ owns the decision; the model only proposes) ──────
# Intents that write clinical / financial / identity truth ALWAYS confirm from an image —
# perception can misread and these are trust-critical.
_ALWAYS_CONFIRM_INTENTS = frozenset({
    "log_glucose", "log_blood_pressure", "log_labs", "add_medication",
    "log_expense", "add_transaction", "add_contact", "add_insurance_card",
    "add_identity_document",
    # A full body check-in read from a screenshot/photo always gets a review card —
    # perception can misread a value and a session writes many measurements at once.
    "log_body_measurements",
    # Structured Import Orchestration: a document parsed into MANY records always previews
    # first — the user confirms the whole batch before anything is created.
    "import_journal_entries",
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


# Intents whose confirmation is gated on the CANDIDATE DATA via a `confirmed` kwarg inside the
# HANDLER (multimodal data imports), not by an external gate. BOTH confirmation-completion paths
# must forward confirmed=True for these or a confirmed import re-triggers its own gate and never
# persists: the CoS model re-call path (apps/ai/cos_services/action_execution.py) AND the
# deterministic bare-"yes" replay (apps/ai/intent_service.py :: handle_crud_confirmation).
# This is the single source of truth for that set.
DATA_CONFIRM_INTENTS = frozenset({"log_weight", "log_body_measurements",
                                  "import_journal_entries"})

# NOTE: the multimodal-import confirmation PRESENTATION (turning a handler's structured
# confirmation_detail into the RESULTS-not-intentions text the user sees) lives in the generic
# framework apps/ai/import_confirmation.py — NOT here and NOT in any domain handler. This module
# owns perception/normalization/validation TRUTH only.
