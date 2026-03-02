"""
Pantry Photo Detection Service

Processes pantry/fridge/freezer photos through Vision AI to detect
food items, matches them to Ingredient records, and creates
PantryPhotoDetection entries for user confirmation.

No PantryItems are created until the user confirms detections.
"""

import base64
import json
import logging
from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


# Pantry-specific vision prompt — optimized for ingredient detection
PANTRY_VISION_PROMPT = """You are analyzing a photo of the inside of a {location_type}.
Your goal is to identify all visible FOOD ITEMS and INGREDIENTS.

IMPORTANT RULES:
1. Focus ONLY on food items — ignore non-food objects.
2. Be specific: "whole milk" not just "milk", "green bell pepper" not just "pepper".
3. Estimate quantity when possible (e.g., "2 cartons", "1 bag", "3 apples").
4. Assign a confidence score (0.0-1.0) for each item based on visibility.
5. Do NOT identify people or non-food items.

RESPONSE FORMAT (strict JSON):
{{
  "items": [
    {{
      "label": "specific food item name",
      "quantity": 1,
      "unit": "piece",
      "confidence": 0.85,
      "storage_hint": "refrigerator"
    }}
  ]
}}

Unit options: piece, bag, carton, bottle, can, jar, box, bunch, lb, oz, gallon, container, pack
Respond ONLY with valid JSON. No markdown, no explanation."""


class PantryPhotoDetectionService:
    """
    Orchestrates the pantry photo → detection → confirmation pipeline.

    Steps:
    1. Send image to Vision AI with pantry-specific prompt
    2. Extract food object labels
    3. Normalize label text
    4. Fuzzy match to Ingredient model
    5. Assign confidence score
    6. Default suggested quantity = 1 unit
    7. Create PantryPhotoDetection entries

    Does NOT create PantryItem — that happens in confirmation.
    """

    def __init__(self):
        self._client = None

    @property
    def client(self):
        """Lazy-initialize OpenAI client."""
        if self._client is None:
            try:
                import openai
                self._client = openai.OpenAI(
                    api_key=getattr(settings, "OPENAI_API_KEY", ""),
                    timeout=30,
                )
            except ImportError:
                logger.error("openai package not installed")
            except Exception as e:
                logger.error("Failed to initialize OpenAI client: %s", e, exc_info=True)
        return self._client

    # Smaller image size for pantry photos (1024px instead of 2048px)
    PANTRY_MAX_DIMENSION = 1024

    def process_upload(self, upload):
        """
        Process a single PantryPhotoUpload through Vision AI.

        Args:
            upload: PantryPhotoUpload instance with image field

        Returns:
            list of PantryPhotoDetection instances created
        """
        from apps.scan.services.image_utils import image_field_to_base64, resize_for_vision

        if upload.processed:
            logger.info("Upload %d already processed, skipping", upload.pk)
            return list(upload.detections.all())

        # Convert image to base64
        base64_data, mime_type = image_field_to_base64(upload.image)
        if not base64_data:
            logger.error("Could not read image for upload %d", upload.pk)
            upload.processed = True
            upload.raw_detection_json = {"error": "Could not read image"}
            upload.save(update_fields=["processed", "raw_detection_json"])
            return []

        # Resize for cost optimization — pantry uses smaller images
        base64_data = resize_for_vision(base64_data, mime_type, max_dim=self.PANTRY_MAX_DIMENSION)

        return self._process_base64(upload, base64_data, mime_type)

    def process_from_memory(self, upload, raw_bytes, content_type="image/jpeg"):
        """
        Process a photo from in-memory bytes (skips Cloudinary round-trip).

        Args:
            upload: PantryPhotoUpload instance (already saved, image field may be empty)
            raw_bytes: Raw image bytes from request.FILES
            content_type: MIME type of the image

        Returns:
            list of PantryPhotoDetection instances created
        """
        from apps.scan.services.image_utils import resize_for_vision

        if upload.processed:
            logger.info("Upload %d already processed, skipping", upload.pk)
            return list(upload.detections.all())

        # Convert raw bytes to base64
        base64_data = base64.b64encode(raw_bytes).decode("utf-8")

        # Resize for cost optimization — pantry uses smaller images
        base64_data = resize_for_vision(base64_data, content_type, max_dim=self.PANTRY_MAX_DIMENSION)

        return self._process_base64(upload, base64_data, content_type)

    def _process_base64(self, upload, base64_data, mime_type):
        """
        Shared processing logic for both upload-based and in-memory processing.
        """
        from apps.scan.services.image_utils import compute_image_hash

        # Check cache (10-minute window)
        image_hash = compute_image_hash(base64_data)
        cache_key = f"pantry_detect:{image_hash}"
        cached_result = cache.get(cache_key)

        if cached_result:
            logger.info("Using cached detection for upload %d", upload.pk)
            raw_result = cached_result
        else:
            # Call Vision AI
            raw_result = self._call_vision_api(
                base64_data, mime_type, upload.session.location_type
            )
            if raw_result and "error" not in raw_result:
                cache.set(cache_key, raw_result, 600)  # 10 min cache

        # Store raw result
        upload.raw_detection_json = raw_result or {}
        upload.processed = True
        upload.save(update_fields=["processed", "raw_detection_json"])

        if not raw_result or "error" in raw_result:
            return []

        # Create detection entries
        detections = self._create_detections(upload, raw_result)

        # Update session detection count
        session = upload.session
        session.items_detected = session.detections.count()
        session.save(update_fields=["items_detected"])

        return detections

    def _call_vision_api(self, base64_data, mime_type, location_type):
        """Call OpenAI Vision API with pantry-specific prompt."""
        if not self.client:
            return {"error": "Vision API client not available"}

        prompt = PANTRY_VISION_PROMPT.format(location_type=location_type)
        model = getattr(settings, "OPENAI_VISION_MODEL", "gpt-4o")

        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{base64_data}",
                                    "detail": "high",
                                },
                            },
                        ],
                    }
                ],
                max_tokens=2000,
                temperature=0.1,
            )

            content = response.choices[0].message.content.strip()
            # Strip markdown fences if present
            if content.startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()

            return json.loads(content)

        except json.JSONDecodeError as e:
            logger.error("Vision API returned invalid JSON: %s", e)
            return {"error": f"Invalid JSON response: {e}"}
        except Exception as e:
            logger.error("Vision API call failed: %s", e, exc_info=True)
            return {"error": str(e)}

    def _create_detections(self, upload, raw_result):
        """Create PantryPhotoDetection entries from Vision AI result."""
        from apps.meals.models import PantryPhotoDetection
        from apps.meals.services.ingredient_matching import match_ingredient_name

        items = raw_result.get("items", [])
        detections = []

        # Track ingredient IDs already detected in this session (across all uploads)
        existing_ingredient_ids = set(
            upload.session.detections.exclude(
                upload=upload,
            ).values_list("matched_ingredient_id", flat=True)
        )

        for item in items:
            label = item.get("label", "").strip()
            if not label:
                continue

            # Match to ingredient
            match = match_ingredient_name(label)

            # Skip if this ingredient was already detected in another upload for this session
            if match.ingredient_id and match.ingredient_id in existing_ingredient_ids:
                continue

            confidence = Decimal(str(min(max(item.get("confidence", 0.5), 0), 1)))
            quantity = item.get("quantity")
            unit = item.get("unit", "piece")

            if quantity is not None:
                try:
                    quantity = Decimal(str(quantity))
                except (ValueError, TypeError):
                    quantity = Decimal("1")
            else:
                quantity = Decimal("1")

            detection = PantryPhotoDetection(
                session=upload.session,
                upload=upload,
                detected_label=label[:200],
                matched_ingredient_id=match.ingredient_id if match.ingredient_id else None,
                confidence_score=confidence,
                suggested_quantity=quantity,
                unit=unit[:20] if unit else "piece",
            )
            detections.append(detection)

            # Track this ingredient to prevent duplicates within this batch too
            if match.ingredient_id:
                existing_ingredient_ids.add(match.ingredient_id)

        # Bulk create for efficiency
        if detections:
            PantryPhotoDetection.objects.bulk_create(detections)
            # Re-fetch to get PKs
            detections = list(upload.detections.all())

        return detections

    def confirm_session(self, session, confirmed_ids, quantities=None, ingredient_overrides=None):
        """
        Confirm selected detections and create/update PantryItems.

        Args:
            session: PantryScanSession instance
            confirmed_ids: list of PantryPhotoDetection PKs to confirm
            quantities: dict of {detection_id: new_quantity} for quantity overrides
            ingredient_overrides: dict of {detection_id: ingredient_id} for ingredient changes

        Returns:
            tuple of (items_created, items_updated)
        """
        from apps.meals.models import (
            InventoryTransaction,
            PantryItem,
            PantryPhotoDetection,
            Ingredient,
        )

        quantities = quantities or {}
        ingredient_overrides = ingredient_overrides or {}
        items_created = 0
        items_updated = 0
        confirmed_confidences = []

        with transaction.atomic():
            detections = session.detections.filter(pk__in=confirmed_ids)

            # Track seen ingredients to prevent duplicates within session
            seen_ingredients = set()

            for detection in detections:
                # Apply ingredient override if provided
                if detection.pk in ingredient_overrides:
                    override_id = ingredient_overrides[detection.pk]
                    try:
                        detection.matched_ingredient = Ingredient.objects.get(pk=override_id)
                    except Ingredient.DoesNotExist:
                        logger.warning(
                            "Ingredient override %d not found for detection %d",
                            override_id, detection.pk,
                        )

                if not detection.matched_ingredient:
                    # Auto-create ingredient from detected label — user explicitly
                    # confirmed they want this item, so don't silently reject
                    from apps.meals.services.ingredient_matching import get_or_create_ingredient
                    try:
                        ingredient = get_or_create_ingredient(detection.detected_label)
                        detection.matched_ingredient = ingredient
                        detection.save(update_fields=["matched_ingredient"])
                        logger.info(
                            "Auto-created ingredient '%s' for detection %d",
                            ingredient.canonical_name, detection.pk,
                        )
                    except Exception as e:
                        logger.error(
                            "Failed to auto-create ingredient for detection %d: %s",
                            detection.pk, e, exc_info=True,
                        )
                        detection.rejected = True
                        detection.save(update_fields=["rejected"])
                        continue

                # Duplicate guard within same session
                ing_id = detection.matched_ingredient_id
                if ing_id in seen_ingredients:
                    detection.rejected = True
                    detection.save(update_fields=["rejected"])
                    continue
                seen_ingredients.add(ing_id)

                # Apply quantity override
                quantity = quantities.get(
                    detection.pk,
                    detection.suggested_quantity or Decimal("1"),
                )
                if not isinstance(quantity, Decimal):
                    quantity = Decimal(str(quantity))

                # Mark detection confirmed
                detection.confirmed = True
                detection.save(update_fields=["confirmed"])
                confirmed_confidences.append(detection.confidence_score)

                # Create or update PantryItem
                pantry_item, created = PantryItem.objects.get_or_create(
                    household=session.household,
                    ingredient=detection.matched_ingredient,
                    defaults={
                        "quantity": quantity,
                        "unit": detection.unit or "piece",
                        "confidence_score": detection.confidence_score,
                        "last_confirmed_at": timezone.now(),
                    },
                )

                if created:
                    items_created += 1
                    # Estimate expiration if shelf life is known
                    if detection.matched_ingredient.shelf_life_days:
                        from datetime import timedelta
                        pantry_item.expiration_date_estimated = (
                            timezone.now().date()
                            + timedelta(days=detection.matched_ingredient.shelf_life_days)
                        )
                        pantry_item.save(update_fields=["expiration_date_estimated"])
                else:
                    # Update existing item
                    pantry_item.quantity += quantity
                    pantry_item.confidence_score = detection.confidence_score
                    pantry_item.last_confirmed_at = timezone.now()
                    pantry_item.save(update_fields=[
                        "quantity", "confidence_score", "last_confirmed_at",
                    ])
                    items_updated += 1

                # Log transaction
                InventoryTransaction.objects.create(
                    pantry_item=pantry_item,
                    delta_quantity=quantity,
                    source="photo_scan",
                    notes=f"Photo scan: {detection.detected_label} ({session.get_location_type_display()})",
                )

            # Mark remaining unconfirmed detections as rejected
            session.detections.filter(
                confirmed=False, rejected=False
            ).exclude(pk__in=confirmed_ids).update(rejected=True)

            # Update session stats
            session.items_confirmed = len(confirmed_confidences)
            if confirmed_confidences:
                avg_conf = sum(confirmed_confidences) / len(confirmed_confidences)
                session.overall_confidence = Decimal(str(round(float(avg_conf), 2)))
            session.completed_at = timezone.now()
            session.save(update_fields=[
                "items_confirmed", "overall_confidence", "completed_at",
            ])

        return items_created, items_updated

    def cancel_session(self, session):
        """Cancel a scan session, marking all detections as rejected."""
        session.detections.filter(confirmed=False).update(rejected=True)
        session.completed_at = timezone.now()
        session.save(update_fields=["completed_at"])


class PantryScanSessionService:
    """
    Session-level intelligence: confidence drift, household stats.
    """

    @staticmethod
    def calculate_confidence_drift(household):
        """
        Calculate overall pantry confidence drift for a household.

        Logic:
        - If last scan > 14 days: reduce overall pantry confidence
        - If no recent confirmation activity: flag as low confidence
        - Returns dict with drift metrics
        """
        from apps.meals.models import PantryItem, PantryScanSession

        now = timezone.now()

        # Find last scan session
        last_session = (
            PantryScanSession.objects.filter(
                household=household,
                completed_at__isnull=False,
            )
            .order_by("-completed_at")
            .first()
        )

        # Calculate days since last scan
        days_since_scan = None
        if last_session and last_session.completed_at:
            days_since_scan = (now - last_session.completed_at).days

        # Overall pantry confidence from active items
        active_items = PantryItem.objects.filter(
            household=household, quantity__gt=0
        )
        item_count = active_items.count()

        if item_count == 0:
            return {
                "overall_confidence": 0,
                "days_since_last_scan": days_since_scan,
                "items_tracked": 0,
                "low_confidence_items": 0,
                "confidence_status": "empty",
            }

        # Decay confidence on all items
        total_confidence = Decimal("0")
        low_count = 0
        for item in active_items:
            item.decay_confidence()
            total_confidence += item.confidence_score
            if item.confidence_score < Decimal("0.5"):
                low_count += 1

        avg_confidence = float(total_confidence / item_count)

        # Additional drift for stale scans
        if days_since_scan is not None and days_since_scan > 14:
            staleness_penalty = min((days_since_scan - 14) * 0.02, 0.30)
            avg_confidence = max(0.10, avg_confidence - staleness_penalty)

        # Determine status
        if avg_confidence >= 0.75:
            status = "high"
        elif avg_confidence >= 0.50:
            status = "moderate"
        elif avg_confidence >= 0.25:
            status = "low"
        else:
            status = "critical"

        return {
            "overall_confidence": round(avg_confidence, 2),
            "days_since_last_scan": days_since_scan,
            "items_tracked": item_count,
            "low_confidence_items": low_count,
            "confidence_status": status,
        }

    @staticmethod
    def get_recent_sessions(household, limit=5):
        """Get recent scan sessions for display."""
        from apps.meals.models import PantryScanSession

        return (
            PantryScanSession.objects.filter(
                household=household,
                completed_at__isnull=False,
            )
            .order_by("-completed_at")[:limit]
        )


# Module-level singleton
pantry_photo_detection_service = PantryPhotoDetectionService()
pantry_scan_session_service = PantryScanSessionService()
