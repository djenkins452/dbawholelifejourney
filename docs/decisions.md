# Architecture Decisions Log

*Key decisions made during development, with rationale.*

---

## Medical Module Decisions (2026-02-12)

### 1. Catalog Mode: Hybrid (Mode C)

**Decision:** Seed common tests via migration + auto-create on miss with `needs_review=True`.

**Rationale:** Pure seeded catalogs break on unknown tests. Pure auto-create has no curation. Hybrid gives us a curated core (45 tests, 150+ aliases) with graceful handling of new tests. Unknown tests get `category="uncategorized"` and can be merged via admin.

### 2. File Storage: Use Existing Organize Document System

**Decision:** Store medical PDFs as `Document(category='medical')` in the existing Organize module, not duplicate storage.

**Rationale:** Avoids storing the same file twice. Cloudinary encryption-at-rest applies automatically. Users see medical documents in both the Medical module and Organize.

### 3. Deletion Strategy: Retain Results on Document Delete

**Decision:** When a medical document is deleted, lab results are retained with a "Source document removed" note. Results are NOT cascade-deleted.

**Rationale:** Lab results have independent clinical value. Losing historical test data because a source PDF was removed would be harmful. Users can still delete individual results if desired.

### 4. Duplicate Detection: SHA-256 Fingerprint

**Decision:** Application-level fingerprint check, not database unique constraint.

**Rationale:** Database-level unique constraints on fingerprint would break when soft-deleted records exist (user might want to re-import after deleting). Application-level check queries `all_objects` (including soft-deleted) for thorough dedup, while allowing clear reporting of skipped duplicates.

### 5. Medical Nav Placement: Under Health

**Decision:** Medical Labs & Vitals appears as a column in the Health mega menu, not as a separate top-level nav item.

**Rationale:** Medical lab results are health data. Adding another top-level nav item would crowd the navigation. Users expect to find lab results under Health.

### 6. No Medical Advice

**Decision:** Display facts only — value, unit, reference range, status label (High/Low/Within range). No interpretation, no recommendations.

**Rationale:** Legal and ethical requirement. The app is not a medical device. Status labels are factual observations (value > range = "High") without clinical interpretation.

### 7. Security: HIPAA-Level Practices

**Decision:** Implement audit logging, user-scoped queries, encryption-at-rest, and PHI-free logging.

**Rationale:** Medical data requires stronger privacy protections. Audit logs record actions without logging actual values. All queries filter by user. Standard Django app logs never contain lab values.

### 8. OCR: Optional Fallback

**Decision:** OCR via pytesseract is a graceful fallback, not a hard requirement.

**Rationale:** Most lab PDFs are text-based (patient portals generate digital PDFs). OCR is needed for scanned paper reports but shouldn't be a deployment blocker. If pytesseract isn't available, the system gracefully reports "Could not extract text."
