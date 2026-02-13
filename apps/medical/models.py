"""
Whole Life Journey - Medical Models

Project: Whole Life Journey
Path: apps/medical/models.py
Purpose: Domain models for medical lab ingestion, catalog, panels, results, and imports

Models:
    - LabTestCatalog: Canonical lab test definitions (system-seeded + user-discovered)
    - LabTestAlias: Many-to-one alias mapping to canonical tests
    - LabEducationContent: Structured educational content for lab tests
    - LabPanel: Named panel groupings (CBC, CMP, Lipids, etc.)
    - MedicalDocument: Links an Organize Document to a medical import
    - ImportBatch: Tracks a single import run
    - ImportErrorRow: Normalized error capture per failed row
    - LabResult: Individual test result rows

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import hashlib
import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from apps.core.models import TimeStampedModel, UserOwnedModel


# =============================================================================
# Lab Test Catalog
# =============================================================================

class LabTestCatalog(TimeStampedModel):
    """
    Canonical lab test definition.

    System-seeded tests are loaded via migration (CBC, CMP, Lipids, etc.).
    New tests discovered during import are auto-created with needs_review=True.
    """

    CATEGORY_CHOICES = [
        ("hematology", "Hematology"),
        ("chemistry", "Chemistry"),
        ("lipids", "Lipids"),
        ("thyroid", "Thyroid"),
        ("diabetes", "Diabetes / Glycemic"),
        ("liver", "Liver Function"),
        ("kidney", "Kidney Function"),
        ("electrolytes", "Electrolytes"),
        ("inflammation", "Inflammation"),
        ("urinalysis", "Urinalysis"),
        ("cardiac", "Cardiac Markers"),
        ("vitamins", "Vitamins & Minerals"),
        ("hormones", "Hormones"),
        ("coagulation", "Coagulation"),
        ("immunology", "Immunology"),
        ("uncategorized", "Uncategorized"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(
        max_length=200,
        unique=True,
        help_text="Canonical display name (e.g., 'White Blood Cell Count')"
    )
    short_name = models.CharField(
        max_length=50,
        blank=True,
        help_text="Common abbreviation (e.g., 'WBC')"
    )
    category = models.CharField(
        max_length=30,
        choices=CATEGORY_CHOICES,
        default="uncategorized",
        db_index=True,
    )
    default_unit = models.CharField(
        max_length=50,
        blank=True,
        help_text="Standard unit (e.g., 'mg/dL', 'x10^3/uL')"
    )
    default_range_low = models.CharField(
        max_length=50,
        blank=True,
        help_text="Default reference range lower bound"
    )
    default_range_high = models.CharField(
        max_length=50,
        blank=True,
        help_text="Default reference range upper bound"
    )
    loinc_code = models.CharField(
        max_length=20,
        blank=True,
        help_text="LOINC code if known"
    )
    is_system_seeded = models.BooleanField(
        default=False,
        help_text="True if loaded via migration seed data"
    )
    needs_review = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True if auto-created during import and not yet reviewed"
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what this test measures"
    )
    sort_order = models.IntegerField(
        default=0,
        help_text="Display ordering within category"
    )

    class Meta:
        ordering = ["category", "sort_order", "name"]
        verbose_name = "Lab Test"
        verbose_name_plural = "Lab Test Catalog"

    def __str__(self):
        if self.short_name:
            return f"{self.name} ({self.short_name})"
        return self.name


class LabTestAlias(TimeStampedModel):
    """
    Maps many raw test name variations to a single canonical LabTestCatalog entry.

    During import, raw test names are normalized and looked up here.
    If no match, a new catalog entry + self-alias is created.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    alias = models.CharField(
        max_length=200,
        unique=True,
        help_text="Normalized alias (casefolded, trimmed, collapsed whitespace)"
    )
    canonical_test = models.ForeignKey(
        LabTestCatalog,
        on_delete=models.CASCADE,
        related_name="aliases",
        help_text="The canonical test this alias maps to"
    )

    class Meta:
        ordering = ["alias"]
        verbose_name = "Lab Test Alias"
        verbose_name_plural = "Lab Test Aliases"

    def __str__(self):
        return f"{self.alias} → {self.canonical_test.name}"


# =============================================================================
# Lab Education Content
# =============================================================================

class LabEducationContent(TimeStampedModel):
    """
    Structured educational content for a lab test.

    Provides general medical education only — NOT medical advice, diagnosis,
    treatment plans, or personal recommendations.

    Content rules:
    - Educational, neutral, non-personalized, plain language
    - Uses phrasing like "Low levels are commonly associated with..."
    - NEVER uses "you should", "you need to", "talk to your doctor",
      "in your case", "because you have", "you should consider"
    - NEVER recommends treatment, medications, or lifestyle plans
    - NEVER diagnoses or interprets results in context of other labs
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lab_test = models.OneToOneField(
        LabTestCatalog,
        on_delete=models.CASCADE,
        related_name="education",
        help_text="The canonical lab test this education content describes"
    )
    summary_plain_name = models.CharField(
        max_length=200,
        help_text="Plain-language name (e.g., 'White Blood Cell Count')"
    )
    what_it_measures = models.TextField(
        help_text="What this test measures, in plain language"
    )
    what_it_reflects = models.TextField(
        help_text="What this test reflects about body function"
    )
    low_general_associations = models.TextField(
        blank=True,
        help_text="What low values are commonly associated with (general causes)"
    )
    high_general_associations = models.TextField(
        blank=True,
        help_text="What high values are commonly associated with (general causes)"
    )
    common_influencing_factors = models.TextField(
        help_text="Common non-prescriptive factors that can influence results"
    )
    typical_panel = models.CharField(
        max_length=100,
        blank=True,
        help_text="Typical panel grouping (e.g., 'CBC', 'CMP', 'Lipid Panel')"
    )
    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this content was last reviewed for accuracy"
    )
    is_system_generated = models.BooleanField(
        default=False,
        help_text="True if generated via seed migration"
    )

    class Meta:
        ordering = ["lab_test__category", "lab_test__sort_order"]
        verbose_name = "Lab Education Content"
        verbose_name_plural = "Lab Education Content"

    def __str__(self):
        return f"Education: {self.lab_test.name}"


# =============================================================================
# Lab Panels
# =============================================================================

class LabPanel(UserOwnedModel):
    """
    A panel grouping (e.g., CBC, CMP, Lipid Panel) tied to a user and collection date.

    Panels group related LabResult rows together for display and organization.
    """

    PANEL_TYPE_CHOICES = [
        ("cbc", "Complete Blood Count (CBC)"),
        ("cmp", "Comprehensive Metabolic Panel (CMP)"),
        ("bmp", "Basic Metabolic Panel (BMP)"),
        ("lipid", "Lipid Panel"),
        ("thyroid", "Thyroid Panel"),
        ("a1c", "Hemoglobin A1c"),
        ("urinalysis", "Urinalysis"),
        ("liver", "Liver Function Panel"),
        ("kidney", "Renal Function Panel"),
        ("iron", "Iron Studies"),
        ("inflammation", "Inflammation Markers"),
        ("coagulation", "Coagulation Panel"),
        ("vitamin", "Vitamin Panel"),
        ("hormone", "Hormone Panel"),
        ("cardiac", "Cardiac Panel"),
        ("custom", "Custom / Other"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    panel_type = models.CharField(
        max_length=30,
        choices=PANEL_TYPE_CHOICES,
        default="custom",
    )
    name = models.CharField(
        max_length=200,
        help_text="Panel name as it appeared on the report"
    )
    collected_at = models.DateTimeField(
        help_text="When the specimen was collected"
    )
    provider = models.CharField(
        max_length=200,
        blank=True,
        help_text="Lab provider / ordering physician"
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-collected_at"]
        verbose_name = "Lab Panel"
        verbose_name_plural = "Lab Panels"

    def __str__(self):
        return f"{self.get_panel_type_display()} - {self.collected_at.strftime('%Y-%m-%d')}"

    def get_absolute_url(self):
        return reverse("medical:panel_detail", kwargs={"pk": self.pk})

    @property
    def result_count(self):
        return self.results.count()

    @property
    def abnormal_count(self):
        return self.results.exclude(abnormal_flag="").count()


# =============================================================================
# Medical Document (links to Organize Document)
# =============================================================================

class MedicalDocument(UserOwnedModel):
    """
    Links a medical PDF to the Organize Document system.

    The raw PDF is stored exactly once as an apps.life.Document with category='medical'.
    This model references that document and ties it to the import pipeline.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organize_document = models.OneToOneField(
        "life.Document",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="medical_document",
        help_text="Link to the Organize Document (category='medical')"
    )
    original_filename = models.CharField(
        max_length=500,
        help_text="Original uploaded filename"
    )
    file_hash = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text="SHA-256 hash of the uploaded file for dedup"
    )
    page_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of pages in the PDF"
    )
    extracted_text = models.TextField(
        blank=True,
        help_text="Raw extracted text (for debugging, NOT logged in app logs)"
    )
    extraction_method = models.CharField(
        max_length=20,
        blank=True,
        choices=[
            ("text", "Text extraction (pdfplumber)"),
            ("ocr", "OCR (pytesseract)"),
            ("mixed", "Mixed (text + OCR fallback)"),
        ],
        help_text="How text was extracted from the PDF"
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Medical Document"
        verbose_name_plural = "Medical Documents"

    def __str__(self):
        return self.original_filename

    def get_absolute_url(self):
        return reverse("medical:document_detail", kwargs={"pk": self.pk})


# =============================================================================
# Import Batch
# =============================================================================

class ImportBatch(TimeStampedModel):
    """
    Tracks a single import run: counts, timestamps, status.
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("partial", "Partially Completed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="import_batches",
    )
    medical_document = models.ForeignKey(
        MedicalDocument,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="import_batches",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )
    # Counts
    total_rows_found = models.PositiveIntegerField(default=0)
    rows_imported = models.PositiveIntegerField(default=0)
    rows_skipped_duplicate = models.PositiveIntegerField(default=0)
    rows_failed = models.PositiveIntegerField(default=0)
    # Timing
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    # Error summary
    error_summary = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Import Batch"
        verbose_name_plural = "Import Batches"

    def __str__(self):
        return f"Import {self.id} - {self.status} ({self.rows_imported} imported)"

    def get_absolute_url(self):
        return reverse("medical:import_detail", kwargs={"pk": self.pk})

    @property
    def duration_seconds(self):
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


# =============================================================================
# Import Error Row
# =============================================================================

class ImportErrorRow(TimeStampedModel):
    """
    Normalized error capture for a single failed row during import.

    Enough info to debug and optionally re-import.
    Exportable as CSV.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    import_batch = models.ForeignKey(
        ImportBatch,
        on_delete=models.CASCADE,
        related_name="error_rows",
    )
    row_number = models.PositiveIntegerField(
        help_text="Line/row number in the source document"
    )
    raw_test_name = models.CharField(
        max_length=500,
        blank=True,
        help_text="Raw test name as extracted"
    )
    raw_value = models.CharField(
        max_length=200,
        blank=True,
        help_text="Raw value as extracted"
    )
    raw_unit = models.CharField(
        max_length=100,
        blank=True,
        help_text="Raw unit as extracted"
    )
    raw_range = models.CharField(
        max_length=200,
        blank=True,
        help_text="Raw reference range as extracted"
    )
    raw_line = models.TextField(
        blank=True,
        help_text="The complete raw line/text that failed"
    )
    error_type = models.CharField(
        max_length=50,
        help_text="Error category (parse_error, validation_error, mapping_error, etc.)"
    )
    error_message = models.TextField(
        help_text="Human-readable error description"
    )

    class Meta:
        ordering = ["import_batch", "row_number"]
        verbose_name = "Import Error"
        verbose_name_plural = "Import Errors"

    def __str__(self):
        return f"Row {self.row_number}: {self.error_type}"


# =============================================================================
# Lab Result
# =============================================================================

class LabResult(UserOwnedModel):
    """
    Individual lab test result row.

    Core entity: one measured value for one test at one point in time.
    Linked to user, optionally to a panel and source document.
    """

    ABNORMAL_CHOICES = [
        ("", "Normal / Within Range"),
        ("L", "Low"),
        ("H", "High"),
        ("LL", "Critical Low"),
        ("HH", "Critical High"),
        ("A", "Abnormal (unspecified)"),
    ]

    STATUS_CHOICES = [
        ("final", "Final"),
        ("preliminary", "Preliminary"),
        ("pending_review", "Pending Review"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Test identification
    canonical_test = models.ForeignKey(
        LabTestCatalog,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="results",
        help_text="Mapped canonical test (null if unmapped)"
    )
    raw_test_name = models.CharField(
        max_length=500,
        help_text="Original test name as extracted from the report"
    )

    # Result value
    value_text = models.CharField(
        max_length=200,
        help_text="Result value as text (e.g., '7.2', '>60', 'Negative')"
    )
    value_numeric = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Parsed numeric value (null for non-numeric results like 'Negative')"
    )
    unit = models.CharField(
        max_length=100,
        blank=True,
        help_text="Unit of measurement"
    )

    # Reference range
    range_low = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Reference range lower bound (numeric)"
    )
    range_high = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Reference range upper bound (numeric)"
    )
    range_text = models.CharField(
        max_length=200,
        blank=True,
        help_text="Reference range as text (e.g., '<200', '70-99', 'Negative')"
    )

    # Abnormality
    abnormal_flag = models.CharField(
        max_length=5,
        choices=ABNORMAL_CHOICES,
        default="",
        blank=True,
        db_index=True,
        help_text="Abnormal flag from the report"
    )

    # Timing
    collected_at = models.DateTimeField(
        db_index=True,
        help_text="When the specimen was collected"
    )
    reported_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the result was reported"
    )
    date_estimated = models.BooleanField(
        default=False,
        help_text="True if collected_at was estimated (not extracted from document)"
    )

    # Relationships
    panel = models.ForeignKey(
        LabPanel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="results",
        help_text="Panel this result belongs to (if any)"
    )
    medical_document = models.ForeignKey(
        MedicalDocument,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="results",
        help_text="Source medical document"
    )
    import_batch = models.ForeignKey(
        ImportBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="results",
        help_text="Import batch that created this result"
    )

    # Provider
    provider = models.CharField(
        max_length=200,
        blank=True,
        help_text="Lab provider or ordering physician"
    )

    # Result status
    result_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="final",
    )

    # Dedup fingerprint
    fingerprint = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text="SHA-256 fingerprint for duplicate detection"
    )

    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-collected_at", "raw_test_name"]
        verbose_name = "Lab Result"
        verbose_name_plural = "Lab Results"
        indexes = [
            models.Index(fields=["user", "collected_at"]),
            models.Index(fields=["user", "canonical_test", "collected_at"]),
            models.Index(fields=["user", "abnormal_flag", "collected_at"]),
        ]

    def __str__(self):
        name = self.canonical_test.short_name if self.canonical_test and self.canonical_test.short_name else self.raw_test_name
        return f"{name}: {self.value_text} {self.unit}"

    def get_absolute_url(self):
        return reverse("medical:result_detail", kwargs={"pk": self.pk})

    def compute_fingerprint(self):
        """
        Compute a deterministic fingerprint for duplicate detection.

        fingerprint = sha256(user_id + canonical_test_id_or_raw_name +
                            collected_at_iso + value_normalized + unit_normalized + provider)
        """
        parts = [
            str(self.user_id),
            str(self.canonical_test_id) if self.canonical_test_id else self.raw_test_name.strip().lower(),
            self.collected_at.isoformat() if self.collected_at else "",
            self.value_text.strip().lower(),
            self.unit.strip().lower(),
            self.provider.strip().lower(),
        ]
        raw = "|".join(parts)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def save(self, *args, **kwargs):
        # Auto-compute fingerprint
        if not self.fingerprint:
            self.fingerprint = self.compute_fingerprint()
        # Auto-compute abnormal flag from value and range if not already set
        if not self.abnormal_flag and self.value_numeric is not None:
            self.abnormal_flag = self._compute_abnormal_flag()
        super().save(*args, **kwargs)

    def _compute_abnormal_flag(self):
        """Compute abnormal flag based on value vs reference range."""
        if self.value_numeric is None:
            return ""
        if self.range_low is not None and self.value_numeric < self.range_low:
            return "L"
        if self.range_high is not None and self.value_numeric > self.range_high:
            return "H"
        return ""

    @property
    def status_label(self):
        """
        Returns a factual status label based on value vs reference range.
        No medical advice — just factual classification.
        """
        if not self.abnormal_flag:
            if self.range_low is not None or self.range_high is not None:
                return "Within range"
            return "No range available"

        labels = {
            "L": "Low",
            "H": "High",
            "LL": "Critical low",
            "HH": "Critical high",
            "A": "Abnormal",
        }
        return labels.get(self.abnormal_flag, "Unknown")

    @property
    def is_abnormal(self):
        return self.abnormal_flag != ""


# =============================================================================
# Audit Log (HIPAA-level)
# =============================================================================

class MedicalAuditLog(TimeStampedModel):
    """
    Audit log for medical data access and modifications.

    Records who did what, when, without logging PHI.
    """

    ACTION_CHOICES = [
        ("upload", "Document Uploaded"),
        ("import", "Lab Results Imported"),
        ("view", "Results Viewed"),
        ("delete_doc", "Document Deleted"),
        ("delete_results", "Results Deleted"),
        ("export", "Data Exported"),
        ("merge_test", "Catalog Test Merged"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="medical_audit_logs",
    )
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    detail = models.TextField(
        blank=True,
        help_text="Non-PHI details (e.g., 'Imported 42 results from batch xyz')"
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Medical Audit Log"
        verbose_name_plural = "Medical Audit Logs"

    def __str__(self):
        return f"{self.user} - {self.action} - {self.created_at}"
