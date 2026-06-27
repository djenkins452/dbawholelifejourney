"""
Guided Capture Session service (Medication Acquisition V1 completion).

Accumulates the images of ONE guided capture session, merges them into a single
COMBINED extraction (richer than any single image), and feeds the EXISTING
acquisition pipeline. The session is the only new idea here; the pipeline is
unchanged:

    Session (multiple images) → combined extraction → MedicationScanDraft
    → Confidence Review → Duplicate Detection → Confirmation → MedicationEvent → Intake

`process_capture_session` runs OFF the request path (a Celery worker), updating the
session's progress as it goes and staging exactly ONE draft. Images are analyzed
then discarded — only extracted fields are kept (no raw-image retention).
"""

import logging

from apps.health.medication_acquisition import (
    create_draft_from_scan,
    vision_details_to_extracted,
    vision_item_field,
)
from apps.health.medication_confidence import (
    compute_field_confidences,
    compute_overall_confidence,
)

logger = logging.getLogger(__name__)

# Field-merge priority: the FIRST image that supplies a non-empty value wins (front
# photo names the product; the pharmacy/facts photo fills dose/Rx/ingredients). A
# later image never overwrites an already-read field — capture order is meaningful.
QUALITY_LABELS = [
    (0.85, "Excellent"),
    (0.70, "Good"),
    (0.45, "Fair"),
    (0.0, "Needs another photo"),
]


def _vision():
    from apps.scan.services import vision_service
    return vision_service


def _clean_b64(image_data):
    return image_data.split(",", 1)[1] if "," in (image_data or "") else image_data


# `vision_item_field` (shared normalizer) is imported from medication_acquisition —
# the single author of Vision-item access; no duplicate logic here.


def _merge_details(per_image_details):
    """Combine per-image Vision `details` dicts into one. First non-empty value per
    field wins (capture order is meaningful); absence stays absence."""
    merged = {}
    for details in per_image_details:
        for key, value in (details or {}).items():
            if value in (None, "", []):
                continue
            if merged.get(key) in (None, "", []):
                merged[key] = value
    return merged


def _quality_label(confidence):
    if confidence is None:
        return "Needs another photo"
    for threshold, label in QUALITY_LABELS:
        if confidence >= threshold:
            return label
    return "Needs another photo"


# ── Background processing (production orchestration) ──────────────────────────
# `process_capture_session` runs OFF the request path (a Celery worker). It walks
# the session's images, updating progress as it goes, merges them into one combined
# extraction, computes confidence, and stages exactly ONE MedicationScanDraft via
# the unchanged pipeline. Raises on a retryable Vision error (the task retries);
# marks the session FAILED (keeping images for retry) when nothing readable came back.

def process_capture_session(session):
    """Analyze all images of a MedicationCaptureSession in the background, updating
    its progress, and stage one draft. Returns the draft, or None if unreadable."""
    from apps.health.capture_profiles import get_profile

    session.mark_analyzing()
    images = session.images or []
    steps = (get_profile(session.profile) or {}).get("steps", [])
    vision = _vision()

    per_image_details = []
    categories = []
    vision_errors = []
    for idx, image_data in enumerate(images):
        label = steps[idx]["label"] if idx < len(steps) else "additional photo"
        session.current_step = f"Analyzing {label}…"
        session.save(update_fields=["current_step", "updated_at"])
        # A Vision exception is RETRYABLE — let it propagate so the task retries
        # without losing the session or its images.
        # try_fatsecret=False: this is a MEDICATION/supplement capture (the user
        # picked a profile) — never route it through the FatSecret FOOD AI, which
        # would return food fields (no medication name) and skip the medicine prompt.
        result = vision.analyze_image(
            image_base64=_clean_b64(image_data),
            request_id=f"capture-{session.pk}",
            image_format="jpeg",
            try_fatsecret=False,
        )
        err = getattr(result, "error", None)
        items = (getattr(result, "items", None) or []) if not err else []
        details = {}
        if items:
            details = dict(vision_item_field(items[0], "details") or {})
            label_text = vision_item_field(items[0], "label") or ""
            if not details.get("name") and label_text:
                details.setdefault("name", label_text)
        # Instrumentation — trace the ACTUAL extraction per image (no PHI image data).
        logger.info(
            "capture %s img %s/%s: category=%s confidence=%s items=%s name=%r error=%r",
            session.pk, idx + 1, len(images),
            getattr(result, "top_category", None), getattr(result, "confidence", None),
            len(items), details.get("name"), err,
        )
        if err:
            vision_errors.append(err)
        else:
            if result.top_category:
                categories.append(result.top_category)
            if details:
                per_image_details.append(details)
        session.images_analyzed = idx + 1
        session.save(update_fields=["images_analyzed", "updated_at"])

    session.current_step = "Combining information…"
    session.save(update_fields=["current_step", "updated_at"])
    merged = _merge_details(per_image_details)
    name = (merged.get("name") or "").strip()
    logger.info(
        "capture %s merged: name=%r categories=%s fields=%s vision_errors=%s",
        session.pk, name, categories, sorted(merged.keys()), vision_errors,
    )
    if not name:
        # Distinguish a Vision failure (retryable) from a genuine no-medication read.
        if vision_errors and not per_image_details:
            session.mark_failed(
                "We had trouble reading your photos. Please retry, or try clearer shots.")
        else:
            session.mark_failed(
                "We couldn't read a medication from those photos. "
                "Try clearer shots, replace a photo, or enter it manually.")
        return None

    session.current_step = "Calculating confidence…"
    session.save(update_fields=["current_step", "updated_at"])
    extracted = vision_details_to_extracted(merged, name=name)
    overall = compute_overall_confidence(
        compute_field_confidences(extracted, "bottle_image"))
    category = (
        "supplement" if "supplement" in categories
        else "medicine" if "medicine" in categories
        else ("supplement" if session.intake_type == "supplement" else "medicine")
    )

    draft = create_draft_from_scan(
        session.user, category,
        [{"label": name, "details": merged}],
        scan_confidence=overall,
        evidence=[{
            "source_type": "capture_session",
            "summary": f"Guided capture — {len(images)} photo(s) combined (background)",
            "confidence": overall,
        }],
    )
    if draft is None:
        session.mark_failed("We couldn't stage a draft from those photos.")
        return None

    session.mark_ready(draft, merged=merged, confidence=overall,
                       quality=_quality_label(overall))
    return draft
