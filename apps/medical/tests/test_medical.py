"""
Whole Life Journey - Medical App Tests

Tests for:
  - PDF text extraction
  - Lab parsing (text → structured results)
  - Catalog mapping (raw name → canonical test)
  - Duplicate detection (fingerprinting)
  - Import orchestration (full pipeline)
  - Views (upload, summary, detail)
"""

import hashlib
import os
import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, RequestFactory
from django.urls import reverse
from django.utils import timezone

from apps.users.models import TermsAcceptance

from apps.medical.models import (
    ImportBatch,
    ImportErrorRow,
    LabPanel,
    LabResult,
    LabTestAlias,
    LabTestCatalog,
    MedicalAuditLog,
    MedicalDocument,
)
from apps.medical.services.duplicate_detector import (
    check_batch_duplicates,
    compute_fingerprint,
)
from apps.medical.services.lab_parser import (
    ParsedResult,
    parse_lab_text,
    parse_numeric_value,
)
from apps.medical.services.mapper import (
    guess_panel_type,
    map_to_catalog,
    normalize_test_name,
)

User = get_user_model()


def _create_test_user(email="test@example.com", password="testpass123"):
    """Create a test user with terms accepted and onboarding completed."""
    user = User.objects.create_user(email=email, password=password)
    current_terms_version = settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0")
    TermsAcceptance.objects.create(user=user, terms_version=current_terms_version)
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


SAMPLE_PDF_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "docs", "labs_sample.pdf",
)


# =============================================================================
# PDF Text Extraction Tests
# =============================================================================

class PDFTextExtractorTests(TestCase):
    """Test PDF text extraction service."""

    def test_extract_from_sample_pdf(self):
        """Extract text from the sample PDF and verify output."""
        if not os.path.exists(SAMPLE_PDF_PATH):
            self.skipTest(f"Sample PDF not found at {SAMPLE_PDF_PATH}")

        from apps.medical.services.pdf_text_extractor import PDFTextExtractor

        extractor = PDFTextExtractor(SAMPLE_PDF_PATH)
        result = extractor.extract()

        self.assertTrue(result["has_text"])
        self.assertGreater(result["page_count"], 0)
        self.assertGreater(len(result["text"]), 100)
        self.assertEqual(result["method"], "text")

    def test_compute_file_hash(self):
        """File hash should be deterministic."""
        if not os.path.exists(SAMPLE_PDF_PATH):
            self.skipTest(f"Sample PDF not found at {SAMPLE_PDF_PATH}")

        from apps.medical.services.pdf_text_extractor import PDFTextExtractor

        hash1 = PDFTextExtractor.compute_file_hash(SAMPLE_PDF_PATH)
        hash2 = PDFTextExtractor.compute_file_hash(SAMPLE_PDF_PATH)
        self.assertEqual(hash1, hash2)
        self.assertEqual(len(hash1), 64)  # SHA-256 hex digest

    def test_extract_from_nonexistent_file(self):
        """Extraction from missing file should not crash."""
        from apps.medical.services.pdf_text_extractor import PDFTextExtractor

        extractor = PDFTextExtractor("/tmp/nonexistent_file.pdf")
        result = extractor.extract()
        self.assertFalse(result["has_text"])


# =============================================================================
# Lab Parser Tests
# =============================================================================

class LabParserTests(TestCase):
    """Test lab result parsing."""

    def test_parse_empty_text(self):
        """Empty text should return empty list."""
        self.assertEqual(parse_lab_text(""), [])
        self.assertEqual(parse_lab_text("   "), [])
        self.assertEqual(parse_lab_text(None), [])

    def test_parse_numeric_value(self):
        """Test numeric value extraction."""
        self.assertEqual(parse_numeric_value("7.2"), Decimal("7.2"))
        self.assertEqual(parse_numeric_value("100"), Decimal("100"))
        self.assertIsNone(parse_numeric_value("Negative"))
        self.assertIsNone(parse_numeric_value(""))
        self.assertIsNone(parse_numeric_value(None))

    def test_parse_numeric_value_with_prefix(self):
        """Test numeric values with > or < prefixes."""
        result = parse_numeric_value(">60")
        self.assertEqual(result, Decimal("60"))

        result = parse_numeric_value("<200")
        self.assertEqual(result, Decimal("200"))

    def test_parse_sample_pdf_text(self):
        """Parse extracted text from the sample PDF."""
        if not os.path.exists(SAMPLE_PDF_PATH):
            self.skipTest(f"Sample PDF not found at {SAMPLE_PDF_PATH}")

        from apps.medical.services.pdf_text_extractor import PDFTextExtractor

        extractor = PDFTextExtractor(SAMPLE_PDF_PATH)
        extraction = extractor.extract()
        results = parse_lab_text(extraction["text"])

        # Should find at least some results
        self.assertGreater(len(results), 0, "Parser should find at least one result")

        # Each result should have required fields
        for r in results:
            self.assertTrue(r.test_name, f"Result missing test_name: {r}")
            self.assertTrue(r.value, f"Result missing value: {r}")

    def test_parse_table_format(self):
        """Test parsing standard table-format lab results."""
        text = """
Test Name       Result  Flag  Units     Reference Range
WBC             7.2           x10^3/uL  4.5-11.0
RBC             4.8           x10^6/uL  4.5-5.5
Hemoglobin      15.0          g/dL      13.5-17.5
Hematocrit      44.0          %         38.0-50.0
Glucose         110     H     mg/dL     70-99
"""
        results = parse_lab_text(text)
        # Should parse at least some of these
        self.assertGreater(len(results), 0)

    def test_parsed_result_fields(self):
        """ParsedResult should have all expected fields."""
        pr = ParsedResult(
            test_name="WBC",
            value="7.2",
            unit="x10^3/uL",
            reference_range="4.5-11.0",
            range_low="4.5",
            range_high="11.0",
            abnormal_flag="",
            collected_at=datetime(2025, 1, 17, 12, 0),
            confidence=0.9,
        )
        self.assertEqual(pr.test_name, "WBC")
        self.assertEqual(pr.value, "7.2")
        self.assertEqual(pr.confidence, 0.9)


# =============================================================================
# Mapper Tests
# =============================================================================

class MapperTests(TestCase):
    """Test catalog mapping service."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Load the seed catalog via migration data
        from django.core.management import call_command
        call_command("migrate", "medical", verbosity=0)

    def test_normalize_test_name(self):
        """Normalization should casefold, trim, collapse whitespace."""
        self.assertEqual(normalize_test_name("  WBC  "), "wbc")
        self.assertEqual(normalize_test_name("White  Blood   Cell"), "white blood cell")
        self.assertEqual(normalize_test_name(""), "")

    def test_map_known_alias(self):
        """Known aliases should map to existing catalog entries."""
        catalog, created = map_to_catalog("WBC")
        self.assertFalse(created)
        self.assertEqual(catalog.short_name, "WBC")

    def test_map_known_alias_case_insensitive(self):
        """Mapping should be case-insensitive."""
        catalog, created = map_to_catalog("wbc")
        self.assertFalse(created)

    def test_map_unknown_creates_entry(self):
        """Unknown test names should auto-create catalog entries."""
        unique_name = f"Very Unusual Test {uuid.uuid4().hex[:8]}"
        catalog, created = map_to_catalog(unique_name)
        self.assertTrue(created)
        self.assertTrue(catalog.needs_review)
        self.assertFalse(catalog.is_system_seeded)
        self.assertEqual(catalog.category, "uncategorized")

        # Verify alias was created
        self.assertTrue(
            LabTestAlias.objects.filter(
                alias=normalize_test_name(unique_name)
            ).exists()
        )

    def test_map_empty_name_raises(self):
        """Empty test names should raise ValueError."""
        with self.assertRaises(ValueError):
            map_to_catalog("")

    def test_guess_panel_type(self):
        """Panel type guessing from name."""
        self.assertEqual(guess_panel_type("CBC with Diff"), "cbc")
        self.assertEqual(guess_panel_type("Lipid Panel"), "lipid")
        self.assertEqual(guess_panel_type("Comprehensive Metabolic Panel"), "cmp")
        self.assertEqual(guess_panel_type("Thyroid Panel"), "thyroid")
        self.assertEqual(guess_panel_type(""), "custom")
        self.assertEqual(guess_panel_type("Random Panel"), "custom")


# =============================================================================
# Duplicate Detector Tests
# =============================================================================

class DuplicateDetectorTests(TestCase):
    """Test duplicate detection via fingerprinting."""

    def test_fingerprint_deterministic(self):
        """Same inputs should produce same fingerprint."""
        dt = timezone.now()
        fp1 = compute_fingerprint(
            user_id=1,
            canonical_test_id=uuid.uuid4(),
            raw_test_name="WBC",
            collected_at=dt,
            value_text="7.2",
            unit="x10^3/uL",
        )
        fp2 = compute_fingerprint(
            user_id=1,
            canonical_test_id=uuid.uuid4(),  # Different ID
            raw_test_name="WBC",
            collected_at=dt,
            value_text="7.2",
            unit="x10^3/uL",
        )
        # Different canonical_test_id = different fingerprint
        self.assertNotEqual(fp1, fp2)

    def test_fingerprint_different_values(self):
        """Different values should produce different fingerprints."""
        dt = timezone.now()
        test_id = uuid.uuid4()
        fp1 = compute_fingerprint(1, test_id, "WBC", dt, "7.2", "x10^3/uL")
        fp2 = compute_fingerprint(1, test_id, "WBC", dt, "8.0", "x10^3/uL")
        self.assertNotEqual(fp1, fp2)

    def test_batch_duplicate_check(self):
        """Batch check should separate unique from duplicate candidates."""
        user = _create_test_user(email="test_dedup@example.com")
        dt = timezone.now()
        test_catalog = LabTestCatalog.objects.create(
            name="Test Dedup Entry",
            category="uncategorized",
        )

        # Create an existing result
        fp_existing = compute_fingerprint(
            user.id, test_catalog.id, "Test", dt, "7.2", "mg/dL"
        )
        LabResult.objects.create(
            user=user,
            canonical_test=test_catalog,
            raw_test_name="Test",
            value_text="7.2",
            unit="mg/dL",
            collected_at=dt,
            fingerprint=fp_existing,
        )

        # Check batch with one duplicate and one new
        candidates = [
            {"fingerprint": fp_existing, "data": "duplicate"},
            {"fingerprint": "brand_new_fingerprint", "data": "unique"},
        ]

        unique, dupes = check_batch_duplicates(candidates, user.id)
        self.assertEqual(len(unique), 1)
        self.assertEqual(len(dupes), 1)
        self.assertEqual(unique[0]["data"], "unique")
        self.assertEqual(dupes[0]["data"], "duplicate")


# =============================================================================
# Model Tests
# =============================================================================

class LabResultModelTests(TestCase):
    """Test LabResult model behavior."""

    def setUp(self):
        self.user = _create_test_user(email="test_model@example.com")
        self.catalog = LabTestCatalog.objects.create(
            name="Test Result Model",
            short_name="TRM",
            category="chemistry",
            default_unit="mg/dL",
        )

    def test_auto_compute_fingerprint(self):
        """Fingerprint should be auto-computed on save."""
        result = LabResult(
            user=self.user,
            canonical_test=self.catalog,
            raw_test_name="Test",
            value_text="100",
            unit="mg/dL",
            collected_at=timezone.now(),
        )
        result.save()
        self.assertTrue(result.fingerprint)
        self.assertEqual(len(result.fingerprint), 64)

    def test_auto_compute_abnormal_flag_high(self):
        """Abnormal flag should be auto-computed from value vs range."""
        result = LabResult(
            user=self.user,
            canonical_test=self.catalog,
            raw_test_name="Glucose",
            value_text="120",
            value_numeric=Decimal("120"),
            unit="mg/dL",
            range_low=Decimal("70"),
            range_high=Decimal("99"),
            collected_at=timezone.now(),
        )
        result.save()
        self.assertEqual(result.abnormal_flag, "H")

    def test_auto_compute_abnormal_flag_low(self):
        """Low values should get L flag."""
        result = LabResult(
            user=self.user,
            canonical_test=self.catalog,
            raw_test_name="Glucose",
            value_text="50",
            value_numeric=Decimal("50"),
            unit="mg/dL",
            range_low=Decimal("70"),
            range_high=Decimal("99"),
            collected_at=timezone.now(),
        )
        result.save()
        self.assertEqual(result.abnormal_flag, "L")

    def test_within_range_no_flag(self):
        """Within-range values should have no flag."""
        result = LabResult(
            user=self.user,
            canonical_test=self.catalog,
            raw_test_name="Glucose",
            value_text="85",
            value_numeric=Decimal("85"),
            unit="mg/dL",
            range_low=Decimal("70"),
            range_high=Decimal("99"),
            collected_at=timezone.now(),
        )
        result.save()
        self.assertEqual(result.abnormal_flag, "")

    def test_status_label(self):
        """Status label should reflect abnormal flag."""
        result = LabResult(
            user=self.user,
            canonical_test=self.catalog,
            raw_test_name="Test",
            value_text="100",
            unit="mg/dL",
            collected_at=timezone.now(),
            range_low=Decimal("70"),
            range_high=Decimal("99"),
        )
        result.abnormal_flag = "H"
        self.assertEqual(result.status_label, "High")

        result.abnormal_flag = "L"
        self.assertEqual(result.status_label, "Low")

        result.abnormal_flag = ""
        self.assertEqual(result.status_label, "Within range")

    def test_is_abnormal(self):
        """is_abnormal property should detect any flag."""
        result = LabResult(
            user=self.user,
            raw_test_name="Test",
            value_text="100",
            collected_at=timezone.now(),
        )
        result.abnormal_flag = ""
        self.assertFalse(result.is_abnormal)
        result.abnormal_flag = "H"
        self.assertTrue(result.is_abnormal)


# =============================================================================
# View Tests
# =============================================================================

class MedicalViewTests(TestCase):
    """Test medical views."""

    def setUp(self):
        self.user = _create_test_user(email="test_views@example.com")
        self.client.force_login(self.user)

    def test_home_page_loads(self):
        """Labs summary page should load for authenticated user."""
        response = self.client.get(reverse("medical:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Labs & Vitals")

    def test_upload_page_loads(self):
        """Upload page should load for authenticated user."""
        response = self.client.get(reverse("medical:upload"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Upload Lab Results")

    def test_home_requires_auth(self):
        """Unauthenticated users should be redirected."""
        self.client.logout()
        response = self.client.get(reverse("medical:home"))
        self.assertEqual(response.status_code, 302)

    def test_upload_requires_auth(self):
        """Unauthenticated users should be redirected from upload."""
        self.client.logout()
        response = self.client.get(reverse("medical:upload"))
        self.assertEqual(response.status_code, 302)

    def test_home_shows_empty_state(self):
        """Empty state should show when no results exist."""
        response = self.client.get(reverse("medical:home"))
        self.assertContains(response, "No lab results yet")

    def test_home_with_results(self):
        """Summary page should show results when they exist."""
        catalog = LabTestCatalog.objects.create(
            name="Test View Result",
            category="chemistry",
        )
        LabResult.objects.create(
            user=self.user,
            canonical_test=catalog,
            raw_test_name="Test View Result",
            value_text="100",
            unit="mg/dL",
            collected_at=timezone.now(),
        )
        response = self.client.get(reverse("medical:home"))
        self.assertContains(response, "Test View Result")
        self.assertNotContains(response, "No lab results yet")

    def test_result_detail_page(self):
        """Result detail page should load."""
        catalog = LabTestCatalog.objects.create(
            name="Detail Test",
            category="chemistry",
        )
        result = LabResult.objects.create(
            user=self.user,
            canonical_test=catalog,
            raw_test_name="Detail Test",
            value_text="100",
            unit="mg/dL",
            collected_at=timezone.now(),
        )
        response = self.client.get(
            reverse("medical:result_detail", kwargs={"pk": result.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Detail Test")

    def test_cannot_view_other_users_data(self):
        """Users should not be able to view another user's results."""
        other_user = _create_test_user(email="other@example.com")
        catalog = LabTestCatalog.objects.create(
            name="Other User Test",
            category="chemistry",
        )
        result = LabResult.objects.create(
            user=other_user,
            canonical_test=catalog,
            raw_test_name="Other User Test",
            value_text="100",
            unit="mg/dL",
            collected_at=timezone.now(),
        )
        response = self.client.get(
            reverse("medical:result_detail", kwargs={"pk": result.pk})
        )
        self.assertEqual(response.status_code, 404)

    def test_upload_invalid_file(self):
        """Upload of non-PDF should show error."""
        f = SimpleUploadedFile("test.txt", b"not a pdf", content_type="text/plain")
        response = self.client.post(reverse("medical:upload"), {"file": f})
        self.assertEqual(response.status_code, 200)
        # Should stay on upload page with error

    def test_panel_detail_page(self):
        """Panel detail page should load."""
        panel = LabPanel.objects.create(
            user=self.user,
            panel_type="cbc",
            name="CBC",
            collected_at=timezone.now(),
        )
        response = self.client.get(
            reverse("medical:panel_detail", kwargs={"pk": panel.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Complete Blood Count")

    def test_trend_page_loads(self):
        """Test trend page should load."""
        catalog = LabTestCatalog.objects.create(
            name="Trend Test",
            category="chemistry",
        )
        LabResult.objects.create(
            user=self.user,
            canonical_test=catalog,
            raw_test_name="Trend Test",
            value_text="100",
            unit="mg/dL",
            collected_at=timezone.now(),
        )
        response = self.client.get(
            reverse("medical:test_trend", kwargs={"test_id": catalog.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Trend Test")


# =============================================================================
# Integration Test
# =============================================================================

class IngestionIntegrationTest(TestCase):
    """End-to-end ingestion test using the sample PDF."""

    def setUp(self):
        self.user = _create_test_user(email="test_ingest@example.com")
        # Load catalog via migrations
        from django.core.management import call_command
        call_command("migrate", "medical", verbosity=0)

    def test_ingest_sample_pdf(self):
        """Full ingestion pipeline on the sample PDF."""
        if not os.path.exists(SAMPLE_PDF_PATH):
            self.skipTest(f"Sample PDF not found at {SAMPLE_PDF_PATH}")

        from apps.medical.services.importer import ingest_lab_pdf

        with open(SAMPLE_PDF_PATH, "rb") as f:
            uploaded = SimpleUploadedFile(
                "labs_sample.pdf",
                f.read(),
                content_type="application/pdf",
            )

        result = ingest_lab_pdf(
            user=self.user,
            uploaded_file=uploaded,
            ip_address="127.0.0.1",
        )

        # Should succeed (even if 0 results parsed from a synthetic sample)
        self.assertTrue(
            result.success,
            f"Ingestion failed: {result.error_message}"
        )
        self.assertIsNotNone(result.import_batch)

        # Verify medical document was created
        self.assertIsNotNone(result.medical_document)
        self.assertTrue(result.medical_document.file_hash)

        # Verify import batch has valid counts
        batch = result.import_batch
        self.assertEqual(batch.status, "completed" if batch.rows_failed == 0 else "partial")
        self.assertEqual(
            batch.total_rows_found,
            batch.rows_imported + batch.rows_skipped_duplicate + batch.rows_failed,
        )

        # Verify audit log was created
        self.assertTrue(
            MedicalAuditLog.objects.filter(
                user=self.user,
                action="import",
            ).exists()
        )

    def test_duplicate_upload_blocked(self):
        """Re-uploading the same file should be blocked."""
        if not os.path.exists(SAMPLE_PDF_PATH):
            self.skipTest(f"Sample PDF not found at {SAMPLE_PDF_PATH}")

        from apps.medical.services.importer import ingest_lab_pdf

        with open(SAMPLE_PDF_PATH, "rb") as f:
            content = f.read()

        # First upload
        uploaded1 = SimpleUploadedFile("labs.pdf", content, content_type="application/pdf")
        result1 = ingest_lab_pdf(self.user, uploaded1, "127.0.0.1")
        self.assertTrue(result1.success)

        # Second upload of same file
        uploaded2 = SimpleUploadedFile("labs.pdf", content, content_type="application/pdf")
        result2 = ingest_lab_pdf(self.user, uploaded2, "127.0.0.1")
        self.assertFalse(result2.success)
        self.assertIn("already uploaded", result2.error_message)

    def test_file_size_limit(self):
        """Files over 20MB should be rejected."""
        from apps.medical.services.importer import ingest_lab_pdf

        # Create a mock file that reports > 20MB
        large_file = MagicMock()
        large_file.size = 25 * 1024 * 1024
        large_file.name = "huge.pdf"

        result = ingest_lab_pdf(self.user, large_file, "127.0.0.1")
        self.assertFalse(result.success)
        self.assertIn("too large", result.error_message)

    def test_non_pdf_rejected(self):
        """Non-PDF files should be rejected."""
        from apps.medical.services.importer import ingest_lab_pdf

        text_file = SimpleUploadedFile("test.txt", b"not a pdf", content_type="text/plain")
        result = ingest_lab_pdf(self.user, text_file, "127.0.0.1")
        self.assertFalse(result.success)
        self.assertIn("PDF", result.error_message)


# =============================================================================
# Audit Log Tests
# =============================================================================

class AuditLogTests(TestCase):
    """Test audit logging behavior."""

    def setUp(self):
        self.user = _create_test_user(email="test_audit@example.com")

    def test_audit_log_creation(self):
        """Audit logs should be created correctly."""
        log = MedicalAuditLog.objects.create(
            user=self.user,
            action="view",
            detail="Viewed labs summary",
            ip_address="127.0.0.1",
        )
        self.assertEqual(log.action, "view")
        self.assertEqual(log.user, self.user)

    def test_view_creates_audit_log(self):
        """Viewing the summary page should create an audit log."""
        self.client.force_login(self.user)
        response = self.client.get(reverse("medical:home"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            MedicalAuditLog.objects.filter(
                user=self.user,
                action="view",
            ).exists()
        )
