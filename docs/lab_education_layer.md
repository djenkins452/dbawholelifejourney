# Lab Education Layer

## Overview

The Lab Education Layer provides structured, general medical education for every lab test in WLJ. It is designed to help users understand what their lab results measure — **without providing medical advice, diagnosis, treatment plans, or personal recommendations**.

## Content Rules

### Required Tone
- Educational, neutral, non-personalized, plain language
- Written for a general audience (no medical jargon without explanation)

### Approved Phrasing
- "Low levels are commonly associated with..."
- "High levels may be seen in..."
- "Factors that can influence this test include..."

### Prohibited Phrasing (Enforced by Automated Tests)
The following phrases **must never** appear in education content:

| Phrase | Reason |
|--------|--------|
| "you should" | Personal advice |
| "you need to" | Directive language |
| "you must" | Prescriptive |
| "talk to your doctor" | Escalation/advice |
| "see your doctor" | Escalation/advice |
| "consult your doctor" | Escalation/advice |
| "in your case" | Personalized interpretation |
| "because you have" | Personalized interpretation |
| "you should consider" | Personal advice |
| "we recommend" | Recommendation |
| "it is recommended that you" | Recommendation |
| "stop taking" | Treatment advice |
| "start taking" | Treatment advice |
| "take this medication" | Treatment advice |
| "prescribe" | Treatment advice |

These are scanned automatically in the test suite (`LabEducationProhibitedPhraseTests`).

## Data Model

### LabEducationContent

| Field | Type | Description |
|-------|------|-------------|
| `lab_test` | OneToOneField → LabTestCatalog | The canonical lab test |
| `summary_plain_name` | CharField(200) | Plain-language name |
| `what_it_measures` | TextField | What the test measures |
| `what_it_reflects` | TextField | What it reflects about body function |
| `low_general_associations` | TextField | General causes of low values |
| `high_general_associations` | TextField | General causes of high values |
| `common_influencing_factors` | TextField | Non-prescriptive factors |
| `typical_panel` | CharField(100) | Panel grouping (CBC, CMP, etc.) |
| `reviewed_at` | DateTimeField | When content was last reviewed |
| `is_system_generated` | BooleanField | True if created by migration |

### Relationship
- One-to-one with `LabTestCatalog`
- Accessed via `lab_test.education` reverse relation
- If no education exists: UI shows "Educational information for this test is not yet available."

## Disclaimer Policy

Every education display (modal, inline panel) includes this disclaimer at the bottom:

> This information is provided for general educational purposes only and is not medical advice. It is not intended to diagnose, treat, cure, or prevent any condition.

The disclaimer is:
- Not alarming
- Not escalating urgency
- Required on every display

## UI Behavior

### Labs Summary Page (Modal)
- Each lab result row has an ℹ️ "About this test" button
- Clicking opens a modal with AJAX-loaded education content
- Content is cached client-side per test+flag combination
- Modal closes on backdrop click, X button, or Escape key

### Result Detail Page (Inline)
- Expandable `<details>` element labeled "About This Test"
- Sits between the result detail grid and the history section

### Abnormal Prioritization
When a result has an abnormal flag:
- **Low (L, LL)**: "Low values" section is shown first and emphasized
- **High (H, HH)**: "High values" section is shown first and emphasized
- **Normal**: Sections shown in standard order (low, then high)

Emphasized sections have a subtle accent-colored left border and background.

## Generation Workflow

### System-Seeded Tests (Migration)
- `0004_seed_lab_education.py` creates education for all 57 seeded catalog tests
- Content is generated with `is_system_generated=True`
- Covers: CBC, CMP, Lipids, Thyroid, A1c, Urinalysis, Inflammation

### Dynamically Added Tests
When a new test is auto-created during PDF import:
1. `LabTestCatalog` entry is created with `needs_review=True`
2. No `LabEducationContent` exists yet
3. UI shows "Educational information for this test is not yet available."
4. Admin can find tests without education via the "Needs Education" filter on LabTestCatalogAdmin
5. Admin creates education content manually via LabEducationContentAdmin

### Admin Features
- **LabEducationContentAdmin**: Full CRUD with fieldsets, search, filters
- **NeedsEducationFilter** on LabTestCatalogAdmin: Shows tests missing education
- **"Mark as reviewed"** bulk action: Sets `reviewed_at` to current timestamp

## Testing

Tests are in `apps/medical/tests/test_medical.py`:

| Test Class | Tests | Purpose |
|------------|-------|---------|
| `LabEducationCoverageTests` | 3 | Every seeded test has education, counts match, fields populated |
| `LabEducationProhibitedPhraseTests` | 1 | Scans all text fields for prohibited phrases |
| `LabEducationModelTests` | 2 | OneToOne constraint, string representation |
| `LabEducationViewTests` | 7 | Detail page includes education, AJAX endpoint, flag ordering, missing education handling, auth required |

Total: **13 education-specific tests** added to the existing 41.
