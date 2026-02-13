# Medical Lab Ingestion - User & Developer Guide

*Last updated: 2026-02-12*

---

## Overview

The Medical module ingests lab result PDFs, extracts structured test results, deduplicates them, and stores them linked to the user's profile. Uploaded PDFs are also stored in Organize > Documents as "Medical Records".

---

## Supported Formats

The parser handles three major lab PDF formats:

1. **Patient Portal Format** (UT Medical / MyChart)
   - Test headers with "Learn more about this" links
   - Value + Date entries
   - Reference range on separate line

2. **Table Format** (Standard Lab Reports)
   - Column-based: Test Name | Result | Flag | Units | Reference Range
   - Multi-page support

3. **Generic Text Format** (Fallback)
   - Line-by-line regex parsing
   - Lower confidence scores

**OCR Support:** If pdfplumber cannot extract text (scanned PDFs), the system falls back to pytesseract OCR (requires Tesseract installed).

---

## Duplicate Prevention

**Fingerprint formula:**
```
sha256(user_id | canonical_test_id | collected_at_iso | value | unit | provider)
```

- Application-level check before insert (clear reporting)
- Skipped duplicates are counted in import summary
- Re-uploading the same PDF file (by SHA-256 hash) is blocked entirely

---

## Error Handling

Failed rows are stored as `ImportErrorRow` records:
- Row number, raw test name, raw value, raw unit, raw range
- Error type and message
- Downloadable as CSV from the Import Results page

---

## How to Run Tests

```bash
# Run all medical tests (41 tests)
python manage.py test apps.medical.tests.test_medical -v 1

# Run specific test class
python manage.py test apps.medical.tests.test_medical.IngestionIntegrationTest -v 1

# Run with failfast
python manage.py test apps.medical.tests.test_medical -v 1 --failfast
```

**Sample PDF:** Tests use `/docs/labs_sample.pdf`. If missing, integration tests will be skipped.

---

## Ingestion Pipeline

1. **Validate** — File size (20MB max), format (.pdf only)
2. **Hash** — SHA-256 of file content, check for duplicate uploads
3. **Extract** — pdfplumber text extraction, OCR fallback
4. **Parse** — Detect format, extract structured results
5. **Map** — Match raw test names to canonical catalog via alias table
6. **Dedupe** — Fingerprint-based duplicate detection
7. **Import** — Atomic transaction for results + panels
8. **Audit** — Non-PHI audit log entry

---

## Service Modules

| Module | Purpose |
|--------|---------|
| `pdf_text_extractor.py` | Text extraction from normal PDFs |
| `ocr_extractor.py` | OCR fallback for scanned PDFs |
| `lab_parser.py` | Multi-format text → structured results |
| `mapper.py` | Raw test name → LabTestCatalog mapping |
| `duplicate_detector.py` | Fingerprint computation + batch dedup |
| `error_reporter.py` | ImportErrorRow creation + CSV export |
| `importer.py` | Full pipeline orchestration |

---

## Lab Test Catalog

- 45 system-seeded tests across 16 categories
- 150+ aliases for common name variations
- Auto-creates new entries for unknown tests (`needs_review=True`)
- Admin tools for merging and reviewing unknown tests

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Could not extract text" | PDF may be encrypted or image-only without Tesseract installed |
| "This file was already uploaded" | Same file hash — delete previous import to re-upload |
| No results parsed | Format may not be supported — check parser logs |
| "pdfplumber not installed" | `pip install pdfplumber` |
| OCR not working | Install Tesseract: `brew install tesseract` (macOS) |

---

## Security

- Users can only view their own medical data (enforced at queryset level)
- Audit logs record all access without PHI
- PDFs stored via Cloudinary (server-side encryption in production)
- File uploads limited to 20MB
- Soft deletes preserve data with 30-day retention
