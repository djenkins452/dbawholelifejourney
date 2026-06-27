"""
Guided Capture Session service (Medication Acquisition V1 completion).

Accumulates the images of ONE guided capture session, merges them into a single
COMBINED extraction (richer than any single image), and feeds the EXISTING
acquisition pipeline. The session is the only new idea here; the pipeline is
unchanged:

    Session (multiple images) → combined extraction → MedicationScanDraft
    → Confidence Review → Duplicate Detection → Confirmation → MedicationEvent → Intake

`analyze_capture` previews the merged confidence mid-session (no draft, nothing
canonical). `finalize_capture` creates the one draft and hands off to review.
Images are analyzed then discarded — only extracted fields are kept (no raw-image
retention), consistent with the rest of acquisition.
"""

import logging

from apps.health.capture_profiles import suggested_next_photo
from apps.health.medication_acquisition import (
    create_draft_from_scan,
    vision_details_to_extracted,
)
from apps.health.medication_confidence import (
    compute_field_confidences,
    compute_overall_confidence,
    confidence_band,
    missing_fields,
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


def _extract_from_images(images, image_format="jpeg"):
    """Run Vision over each image and merge → (category, merged_details, name).
    Returns (None, {}, "") if nothing usable was read."""
    vision = _vision()
    per_image_details = []
    categories = []
    for image_data in images or []:
        try:
            result = vision.analyze_image(
                image_base64=_clean_b64(image_data),
                request_id="capture",
                image_format=image_format,
            )
        except Exception:
            logger.warning("capture: vision analyze failed for an image", exc_info=True)
            continue
        if getattr(result, "error", None):
            continue
        if result.top_category:
            categories.append(result.top_category)
        items = result.items or []
        if items:
            item = items[0] or {}
            per_image_details.append(item.get("details", {}) or {})
            # Carry the label as a name fallback when structured name is absent.
            if not (item.get("details") or {}).get("name") and item.get("label"):
                per_image_details[-1].setdefault("name", item.get("label"))

    merged = _merge_details(per_image_details)
    # Prefer a med/supplement category; default to medicine.
    category = "supplement" if "supplement" in categories else (
        "medicine" if "medicine" in categories else (categories[0] if categories else None)
    )
    name = (merged.get("name") or "").strip()
    return category, merged, name


def analyze_capture(user, images, *, intake_type="medication", image_format="jpeg"):
    """Mid-session confidence preview — NO draft, nothing canonical. Returns the
    combined confidence, quality label, what's still missing, and a deterministic
    'why' prompt for the next photo."""
    category, merged, name = _extract_from_images(images, image_format=image_format)
    if not name:
        return {
            "ok": False,
            "name": "",
            "confidence": None,
            "confidence_pct": None,
            "quality": "Needs another photo",
            "missing": [],
            "suggestion": "a clear photo of the front label",
            "prompt": "I couldn't identify the product yet — try a clear photo of the front label.",
        }

    extracted = vision_details_to_extracted(merged, name=name)
    fc = compute_field_confidences(extracted, "bottle_image")
    overall = compute_overall_confidence(fc)
    missing = missing_fields(extracted, intake_type=intake_type)
    suggestion = suggested_next_photo(missing)

    if suggestion and (overall is None or confidence_band(overall) != "high"):
        prompt = (f"I've identified {name}. To improve confidence, "
                  f"I'd like {suggestion}.")
        enough = False
    else:
        prompt = f"I have enough to review {name}. You can finish, or add another photo."
        enough = True

    return {
        "ok": True,
        "name": name,
        "category": category,
        "confidence": overall,
        "confidence_pct": int(round(overall * 100)) if overall is not None else None,
        "quality": _quality_label(overall),
        "missing": missing,
        "suggestion": suggestion,
        "prompt": prompt,
        "enough": enough,
    }


def finalize_capture(user, images, *, intake_type="medication", image_format="jpeg"):
    """End the session: combine all images into ONE MedicationScanDraft via the
    existing pipeline. Returns the draft (or None if nothing usable). Nothing is
    canonical yet — review + confirm still follow."""
    category, merged, name = _extract_from_images(images, image_format=image_format)
    if not name:
        return None

    # Confidence over the combined extraction (one overall scan confidence).
    extracted = vision_details_to_extracted(merged, name=name)
    overall = compute_overall_confidence(
        compute_field_confidences(extracted, "bottle_image"))

    # Respect the user-selected product type for the category when Vision is unsure.
    if not category:
        category = "supplement" if intake_type == "supplement" else "medicine"

    return create_draft_from_scan(
        user, category,
        [{"label": name, "details": merged}],
        scan_confidence=overall,
        evidence=[{
            "source_type": "capture_session",
            "summary": f"Guided capture — {len(images or [])} photo(s) combined",
            "confidence": overall,
        }],
    )
