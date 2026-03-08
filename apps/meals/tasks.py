"""
Celery tasks for Meal Intelligence async processing.

Handles:
- Pantry photo scan processing through Vision AI
- Receipt image processing through Vision AI (async receipt ingestion)
"""

import logging
import time
from decimal import Decimal

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.db import transaction

logger = logging.getLogger(__name__)


def _update_receipt_progress(receipt, stage, progress):
    """Update receipt processing progress atomically."""
    receipt.processing_stage = stage
    receipt.processing_progress = progress
    receipt.save(update_fields=["processing_stage", "processing_progress", "updated_at"])


@shared_task(
    bind=True,
    name="apps.meals.tasks.process_pantry_scan_task",
    max_retries=1,
    default_retry_delay=10,
    soft_time_limit=180,  # 3 minutes — generous for 5 photos
    acks_late=True,
    reject_on_worker_lost=True,
)
def process_pantry_scan_task(self, session_id):
    """
    Process all unprocessed uploads in a pantry scan session through Vision AI.

    Called async from PantryScanStartView after images are saved.
    The confirm page polls for completion.

    Args:
        session_id: PK of PantryScanSession to process
    """
    from apps.meals.models import PantryScanSession
    from apps.meals.services.pantry_photo_detection import pantry_photo_detection_service

    task_id = self.request.id or "local"
    start = time.monotonic()

    logger.info(
        "Pantry scan task starting (session=%d, task_id=%s)",
        session_id, task_id,
    )

    try:
        session = PantryScanSession.objects.get(pk=session_id)
    except PantryScanSession.DoesNotExist:
        logger.error("Pantry scan session %d not found", session_id)
        return {"status": "error", "reason": "session_not_found"}

    unprocessed = list(session.uploads.filter(processed=False))
    processed_count = 0
    error_count = 0

    try:
        for upload in unprocessed:
            try:
                pantry_photo_detection_service.process_upload(upload)
                processed_count += 1
            except Exception as e:
                logger.error(
                    "Failed to process upload %d in session %d: %s",
                    upload.pk, session_id, e, exc_info=True,
                )
                # Mark as processed with error so we don't retry forever
                upload.processed = True
                upload.raw_detection_json = {"error": str(e)}
                upload.save(update_fields=["processed", "raw_detection_json"])
                error_count += 1

    except SoftTimeLimitExceeded:
        logger.warning(
            "Pantry scan task timed out (session=%d, processed=%d/%d)",
            session_id, processed_count, len(unprocessed),
        )
        # Mark remaining uploads as processed with timeout error
        for upload in session.uploads.filter(processed=False):
            upload.processed = True
            upload.raw_detection_json = {"error": "Processing timed out"}
            upload.save(update_fields=["processed", "raw_detection_json"])
        return {
            "status": "timeout",
            "session_id": session_id,
            "processed": processed_count,
            "total": len(unprocessed),
        }

    duration = time.monotonic() - start
    logger.info(
        "Pantry scan task complete (session=%d, processed=%d, errors=%d, %.1fs)",
        session_id, processed_count, error_count, duration,
    )

    return {
        "status": "ok",
        "session_id": session_id,
        "processed": processed_count,
        "errors": error_count,
        "duration_seconds": round(duration, 2),
    }


@shared_task(
    bind=True,
    name="apps.meals.tasks.process_receipt_image_task",
    max_retries=1,
    default_retry_delay=10,
    soft_time_limit=60,  # 1 minute — single receipt image
    time_limit=90,  # Hard kill at 90s
    acks_late=True,
    reject_on_worker_lost=True,
)
def process_receipt_image_task(self, receipt_id):
    """
    Process a receipt image through Vision AI asynchronously.

    Called from ReceiptUploadView after the image is saved to storage.
    The receipt is created with confirmation_status=CONFIRM_PROCESSING.
    On success, updates to CONFIRM_PENDING and creates ReceiptItems.
    On failure, updates to CONFIRM_FAILED with error message.

    Progress stages:
        upload (10%) → image_processing (25%) → vision_extraction (60%)
        → item_parsing (80%) → classification (90%) → complete (100%)

    Args:
        receipt_id: PK of Receipt to process
    """
    from apps.meals.models import Ingredient, Receipt, ReceiptItem

    task_id = self.request.id or "local"
    start = time.monotonic()

    logger.info(
        "Receipt processing task starting (receipt=%d, task_id=%s)",
        receipt_id,
        task_id,
    )

    try:
        receipt = Receipt.objects.get(pk=receipt_id)
    except Receipt.DoesNotExist:
        logger.error("Receipt %d not found", receipt_id)
        return {"status": "error", "reason": "receipt_not_found"}

    try:
        # Acquire lock to prevent concurrent processing (sync fallback race)
        with transaction.atomic():
            locked_receipt = (
                Receipt.objects.select_for_update(skip_locked=True)
                .filter(pk=receipt_id, confirmation_status=Receipt.CONFIRM_PROCESSING)
                .first()
            )
            if not locked_receipt:
                logger.info(
                    "Receipt %d already processed or locked, skipping", receipt_id
                )
                return {"status": "skipped", "reason": "already_processed_or_locked"}

            # Stage 1: Upload complete
            _update_receipt_progress(locked_receipt, Receipt.STAGE_UPLOAD, 10)

        # Read image bytes from storage (outside transaction — I/O)
        if not receipt.image:
            raise ValueError("No image attached to receipt")

        receipt.image.open("rb")
        raw_bytes = receipt.image.read()
        receipt.image.close()

        # Determine content type from filename
        import mimetypes

        mime_type, _ = mimetypes.guess_type(receipt.image.name)
        content_type = mime_type or "image/jpeg"

        # Stage 2: Image processing (compression)
        _update_receipt_progress(receipt, Receipt.STAGE_IMAGE_PROCESSING, 25)

        # Process through Vision service
        from apps.meals.services.receipt_vision import ReceiptVisionService

        service = ReceiptVisionService()

        # Stage 3: Vision extraction
        _update_receipt_progress(receipt, Receipt.STAGE_VISION_EXTRACTION, 60)

        if content_type == "application/pdf":
            vision_result = service.process_pdf(raw_bytes)
        else:
            vision_result = service.process_image(raw_bytes, content_type)

        if vision_result.error:
            receipt.confirmation_status = Receipt.CONFIRM_FAILED
            receipt.processing_error = vision_result.error
            receipt.processing_progress = 0
            receipt.processing_stage = ""
            receipt.save(
                update_fields=[
                    "confirmation_status", "processing_error",
                    "processing_progress", "processing_stage", "updated_at",
                ]
            )
            logger.error(
                "Receipt %d vision processing failed: %s",
                receipt_id,
                vision_result.error,
            )
            return {"status": "error", "reason": vision_result.error}

        # Stage 4: Item parsing
        _update_receipt_progress(receipt, Receipt.STAGE_ITEM_PARSING, 80)

        # If PDF text extraction returned raw text, parse it with text parser
        if vision_result.source == "pdf_text":
            from apps.meals.services.receipt_parser import (
                match_receipt_items,
                parse_receipt_text,
            )

            parsed = parse_receipt_text(vision_result.raw_text)
            receipt.raw_text = vision_result.raw_text
            receipt.store = parsed.store or ""
            receipt.total = parsed.total or Decimal("0")
            receipt.receipt_type = Receipt.RECEIPT_TYPE_GROCERY
            receipt.parsed_json = {
                "store": parsed.store,
                "date": parsed.date,
                "items": [
                    {
                        "name": i.raw_name,
                        "price": float(i.price) if i.price else None,
                        "qty": float(i.quantity) if i.quantity else None,
                    }
                    for i in parsed.items
                ],
            }

            # Parse date
            if parsed.date:
                from datetime import datetime as dt

                for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%m/%d/%y"):
                    try:
                        receipt.receipt_date = dt.strptime(parsed.date, fmt).date()
                        break
                    except ValueError:
                        continue

            # Create receipt items
            matched = match_receipt_items(parsed)
            for item, match in matched:
                ReceiptItem.objects.create(
                    receipt=receipt,
                    ingredient=Ingredient.objects.filter(
                        pk=match.ingredient_id
                    ).first()
                    if match.ingredient_id
                    else None,
                    raw_name=item.raw_name,
                    raw_price=item.price,
                    quantity=item.quantity or Decimal("1"),
                    unit=item.unit or "each",
                    match_confidence=match.confidence if match else Decimal("0"),
                )

        else:
            # Vision API result — update receipt fields
            receipt.raw_text = vision_result.raw_text
            receipt.store = vision_result.store or ""
            receipt.total = vision_result.total or Decimal("0")
            receipt.subtotal = vision_result.subtotal
            receipt.tax_amount = vision_result.tax
            receipt.payment_method = vision_result.payment_method or ""
            receipt.receipt_type = vision_result.receipt_type
            receipt.parsed_json = {
                "store": vision_result.store,
                "date": vision_result.date,
                "items": vision_result.items,
                "source": vision_result.source,
            }

            # Parse date
            if vision_result.date:
                from datetime import datetime as dt

                for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y"):
                    try:
                        receipt.receipt_date = dt.strptime(
                            vision_result.date, fmt
                        ).date()
                        break
                    except ValueError:
                        continue

            # Create ReceiptItem entries from Vision items
            from apps.meals.services.ingredient_matching import match_ingredient_name

            for item_data in vision_result.items:
                name = item_data.get("name", "")
                if not name:
                    continue

                match = match_ingredient_name(name)
                price = item_data.get("price")

                ReceiptItem.objects.create(
                    receipt=receipt,
                    ingredient=Ingredient.objects.filter(
                        pk=match.ingredient_id
                    ).first()
                    if match.ingredient_id
                    else None,
                    raw_name=name,
                    raw_price=Decimal(str(price)) if price else None,
                    quantity=Decimal(str(item_data.get("quantity", 1))),
                    unit="each",
                    match_confidence=match.confidence,
                    category=item_data.get("category", ""),
                )

        # Stage 5: Classification complete
        _update_receipt_progress(receipt, Receipt.STAGE_COMPLETE, 100)

        # Mark as ready for confirmation
        receipt.confirmation_status = Receipt.CONFIRM_PENDING
        receipt.processing_error = ""
        receipt.save()

        duration = time.monotonic() - start
        item_count = receipt.items.count()
        logger.info(
            "Receipt %d processed successfully: %s, %d items (%.1fs)",
            receipt_id,
            receipt.store,
            item_count,
            duration,
        )

        return {
            "status": "ok",
            "receipt_id": receipt_id,
            "store": receipt.store,
            "items_count": item_count,
            "duration_seconds": round(duration, 2),
        }

    except SoftTimeLimitExceeded:
        logger.warning("Receipt %d processing timed out", receipt_id)
        receipt.confirmation_status = Receipt.CONFIRM_FAILED
        receipt.processing_error = "Processing timed out. Please try again."
        receipt.processing_progress = 0
        receipt.processing_stage = ""
        receipt.save(
            update_fields=[
                "confirmation_status", "processing_error",
                "processing_progress", "processing_stage", "updated_at",
            ]
        )
        return {"status": "timeout", "receipt_id": receipt_id}

    except Exception as exc:
        logger.error(
            "Receipt %d processing failed: %s",
            receipt_id,
            exc,
            exc_info=True,
        )
        receipt.confirmation_status = Receipt.CONFIRM_FAILED
        receipt.processing_error = str(exc)[:500]
        receipt.processing_progress = 0
        receipt.processing_stage = ""
        receipt.save(
            update_fields=[
                "confirmation_status", "processing_error",
                "processing_progress", "processing_stage", "updated_at",
            ]
        )
        return {"status": "error", "receipt_id": receipt_id, "reason": str(exc)}
