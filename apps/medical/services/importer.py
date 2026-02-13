"""
Import orchestrator.

Coordinates the full ingestion pipeline:
  1. Extract text from PDF
  2. Parse text into structured results
  3. Map to catalog
  4. Detect duplicates
  5. Import into database
  6. Record errors
  7. Create audit log
"""

import hashlib
import logging
import tempfile
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from apps.life.models import Document
from apps.medical.models import (
    ImportBatch,
    LabPanel,
    LabResult,
    MedicalAuditLog,
    MedicalDocument,
)
from .duplicate_detector import check_batch_duplicates, compute_fingerprint
from .error_reporter import record_error
from .lab_parser import ParsedResult, parse_lab_text, parse_numeric_value
from .mapper import guess_panel_type, map_to_catalog
from .ocr_extractor import extract_with_fallback
from .pdf_text_extractor import PDFTextExtractor

logger = logging.getLogger(__name__)

# Maximum file size: 20MB
MAX_FILE_SIZE = 20 * 1024 * 1024


class IngestionResult:
    """Result of an ingestion run."""

    def __init__(self):
        self.import_batch = None
        self.medical_document = None
        self.total_found = 0
        self.imported = 0
        self.skipped_duplicates = 0
        self.failed = 0
        self.new_catalog_entries = 0
        self.errors = []
        self.success = False
        self.error_message = ""


def ingest_lab_pdf(user, uploaded_file, ip_address=None) -> IngestionResult:
    """
    Full ingestion pipeline for a lab PDF.

    Args:
        user: User instance
        uploaded_file: Django UploadedFile or file-like object
        ip_address: Client IP for audit log

    Returns:
        IngestionResult with summary
    """
    result = IngestionResult()

    # 1. Validate file
    file_size = uploaded_file.size if hasattr(uploaded_file, 'size') else 0
    if file_size > MAX_FILE_SIZE:
        result.error_message = f"File too large ({file_size // 1024 // 1024}MB). Maximum is {MAX_FILE_SIZE // 1024 // 1024}MB."
        return result

    filename = getattr(uploaded_file, 'name', 'unknown.pdf')
    if not filename.lower().endswith('.pdf'):
        result.error_message = "Only PDF files are supported."
        return result

    # 2. Compute file hash
    file_hash = PDFTextExtractor.compute_file_hash(uploaded_file)

    # Check if this exact file was already uploaded by this user (active records only)
    existing_doc = MedicalDocument.objects.filter(
        user=user, file_hash=file_hash
    ).first()
    if existing_doc:
        # Check if it has any active results — if not, it's orphaned and we can clean it up
        active_results = LabResult.objects.filter(
            user=user, medical_document=existing_doc
        ).exists()
        if active_results:
            result.error_message = (
                f"This file was already uploaded on {existing_doc.created_at.strftime('%Y-%m-%d')}. "
                "If you want to re-import, delete the previous import first."
            )
            return result
        else:
            # Orphaned document with no active results — clean it up
            logger.info("Cleaning up orphaned MedicalDocument %s (no active results)", existing_doc.pk)
            existing_doc.soft_delete()

    # Also clean up any soft-deleted docs with this hash (hard delete to free the hash)
    MedicalDocument.all_objects.filter(
        user=user, file_hash=file_hash, status="deleted"
    ).delete()

    # 3. Save to temp file for processing
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
        uploaded_file.seek(0)
        for chunk in uploaded_file.chunks() if hasattr(uploaded_file, 'chunks') else [uploaded_file.read()]:
            tmp.write(chunk)
        tmp_path = tmp.name
    uploaded_file.seek(0)

    # 4. Extract text
    extraction = extract_with_fallback(tmp_path)
    if not extraction["has_text"]:
        result.error_message = (
            "Could not extract text from this PDF. "
            "The file may be encrypted, corrupted, or in an unsupported format."
        )
        # Clean up temp file
        import os
        os.unlink(tmp_path)
        return result

    # 5. Create Organize Document (category=medical)
    organize_doc = Document.objects.create(
        user=user,
        title=f"Lab Results - {filename}",
        category="medical",
        file=uploaded_file,
        file_type="pdf",
        file_size=file_size,
        document_date=timezone.now().date(),
        created_via="import",
    )

    # 6. Create MedicalDocument
    med_doc = MedicalDocument.objects.create(
        user=user,
        organize_document=organize_doc,
        original_filename=filename,
        file_hash=file_hash,
        page_count=extraction["page_count"],
        extracted_text=extraction["text"],
        extraction_method=extraction["method"],
        created_via="import",
    )
    result.medical_document = med_doc

    # 7. Parse text into structured results
    parsed_results = parse_lab_text(extraction["text"])
    result.total_found = len(parsed_results)

    if not parsed_results:
        result.error_message = (
            "Text was extracted but no lab results were found. "
            "The format may not be supported yet."
        )
        # Still create the import batch to record the attempt
        batch = ImportBatch.objects.create(
            user=user,
            medical_document=med_doc,
            status="completed",
            total_rows_found=0,
            started_at=timezone.now(),
            completed_at=timezone.now(),
        )
        result.import_batch = batch
        result.success = True  # Document was stored even if no results parsed
        return result

    # 8. Create ImportBatch
    batch = ImportBatch.objects.create(
        user=user,
        medical_document=med_doc,
        status="processing",
        total_rows_found=len(parsed_results),
        started_at=timezone.now(),
    )
    result.import_batch = batch

    # 9. Map, dedupe, and import
    try:
        _process_parsed_results(user, batch, med_doc, parsed_results, result)
    except Exception as e:
        logger.error("Import processing failed: %s", str(e), exc_info=True)
        batch.status = "failed"
        batch.error_summary = str(e)
        batch.completed_at = timezone.now()
        batch.save()
        result.error_message = f"Import processing failed: {str(e)}"
        return result

    # 10. Finalize batch
    batch.rows_imported = result.imported
    batch.rows_skipped_duplicate = result.skipped_duplicates
    batch.rows_failed = result.failed
    batch.completed_at = timezone.now()
    batch.status = "completed" if result.failed == 0 else "partial"
    batch.save()

    # 11. Audit log (no PHI)
    MedicalAuditLog.objects.create(
        user=user,
        action="import",
        detail=f"Imported {result.imported} results, {result.skipped_duplicates} duplicates skipped, {result.failed} failed",
        ip_address=ip_address,
    )

    result.success = True

    # Clean up temp file
    import os
    try:
        os.unlink(tmp_path)
    except OSError:
        pass

    return result


def _process_parsed_results(user, batch, med_doc, parsed_results, result):
    """Process parsed results: map, dedupe, import."""

    # Group by panel for panel creation
    panel_groups = {}
    candidates = []

    for parsed in parsed_results:
        # Map to catalog
        try:
            catalog_entry, was_created = map_to_catalog(parsed.test_name)
            if was_created:
                result.new_catalog_entries += 1
        except Exception as e:
            record_error(
                batch, parsed.row_number,
                raw_test_name=parsed.test_name,
                raw_value=parsed.value,
                raw_unit=parsed.unit,
                raw_range=parsed.reference_range,
                raw_line=parsed.raw_line,
                error_type="mapping_error",
                error_message=str(e),
            )
            result.failed += 1
            continue

        # Parse numeric value
        value_numeric = parse_numeric_value(parsed.value)

        # Parse range values
        range_low = _safe_decimal(parsed.range_low)
        range_high = _safe_decimal(parsed.range_high)

        # Compute fingerprint
        fp = compute_fingerprint(
            user_id=user.id,
            canonical_test_id=catalog_entry.id,
            raw_test_name=parsed.test_name,
            collected_at=parsed.collected_at,
            value_text=parsed.value,
            unit=parsed.unit,
        )

        candidates.append({
            "parsed": parsed,
            "catalog_entry": catalog_entry,
            "value_numeric": value_numeric,
            "range_low": range_low,
            "range_high": range_high,
            "fingerprint": fp,
        })

    # Batch dedupe check
    unique, duplicates = check_batch_duplicates(candidates, user.id)
    result.skipped_duplicates = len(duplicates)

    # Import unique results
    with transaction.atomic():
        # Create panels for grouped results
        panels_cache = {}

        for candidate in unique:
            parsed = candidate["parsed"]

            # Determine panel
            panel = None
            if parsed.panel_name and parsed.collected_at:
                panel_key = f"{parsed.panel_name}|{parsed.collected_at.isoformat()}"
                if panel_key not in panels_cache:
                    panel_type = guess_panel_type(parsed.panel_name)
                    panel = LabPanel.objects.create(
                        user=user,
                        panel_type=panel_type,
                        name=parsed.panel_name,
                        collected_at=parsed.collected_at,
                        created_via="import",
                    )
                    panels_cache[panel_key] = panel
                else:
                    panel = panels_cache[panel_key]

            try:
                # Determine result status
                status = "final"
                if parsed.confidence < 0.7:
                    status = "pending_review"

                lab_result = LabResult(
                    user=user,
                    canonical_test=candidate["catalog_entry"],
                    raw_test_name=parsed.test_name,
                    value_text=parsed.value,
                    value_numeric=candidate["value_numeric"],
                    unit=parsed.unit,
                    range_low=candidate["range_low"],
                    range_high=candidate["range_high"],
                    range_text=parsed.reference_range,
                    abnormal_flag=parsed.abnormal_flag,
                    collected_at=parsed.collected_at or timezone.now(),
                    reported_at=parsed.reported_at,
                    panel=panel,
                    medical_document=med_doc,
                    import_batch=batch,
                    result_status=status,
                    fingerprint=candidate["fingerprint"],
                    created_via="import",
                )
                lab_result.save()
                result.imported += 1

            except Exception as e:
                record_error(
                    batch, parsed.row_number,
                    raw_test_name=parsed.test_name,
                    raw_value=parsed.value,
                    raw_unit=parsed.unit,
                    raw_range=parsed.reference_range,
                    raw_line=parsed.raw_line,
                    error_type="save_error",
                    error_message=str(e),
                )
                result.failed += 1


def _safe_decimal(value_str):
    """Safely convert string to Decimal, return None on failure."""
    if not value_str:
        return None
    try:
        return Decimal(value_str.replace(',', ''))
    except (InvalidOperation, ValueError):
        return None
