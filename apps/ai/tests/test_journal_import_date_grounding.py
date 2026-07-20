"""Structured Import — DETERMINISTIC DATE GROUNDING certification.

Permanent fixture for the 2026-07-20 production defect: a journal document containing
Aug 29 – Sep 8 2022 headers was reported as "6 entries from October 10 to October 15, 2023"
— fabricated dates that appear NOWHERE in the source. Root cause: WLJ trusted the model's
normalized ISO date. Fix: dates come ONLY from the document's explicit headers, parsed
deterministically by WLJ; the model's dates are never used when a source document is present.

These tests assert the parser:
  • recognizes ONLY explicit date headers actually in the source (real export quirks: list
    numbers, "Sept", 2-digit years, times smushed onto the year),
  • correctly identifies the skipped day,
  • preserves timestamps,
  • NEVER produces a date absent from the source — even when the model fabricates one,
  • reports UNCERTAINTY rather than inventing a boundary/date when it cannot parse.
"""
import datetime as dt

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.action_handlers import ActionHandler
from apps.ai.import_adapters.journal_import import (
    JournalImportAdapter,
    parse_journal_document,
)
from apps.capture.models import MultimodalArtifact
from apps.journal.models import JournalEntry

User = get_user_model()

# The uploaded journal document's extracted text — Aug 29 – Sep 8, 2022. Faithful to the real
# export's quirks: leading list numbers, weekday names, "Sept"/"Aug" abbreviations, a 2-digit
# year, times SMUSHED onto the year ("20226:30am"), and an explicit "(skipped)" day.
DOCUMENT_TEXT = """Danny's Journal.docx

1. Monday, August 29, 20226:30am
Started the week with an early quiet time. Feeling focused about the compensation project.

2. Tuesday, Aug 30, 22
Overall, today was a great day. Other than the interaction with Melanie around my comp
training, my day at work was fantastic.

3. Saturday, Sept 3, 2022
A moment that I really appreciated today was when Heather did the dishes this morning.

4. Sunday, September 4, 20221:40pm
Today has been a great day. Heather and I made the decision to take control of our lives.

5. Monday, September 5, 2022 (skipped)

6. Tuesday, September 6, 20229:38pm
Today has been a good day. Very busy at work. Today was Haley's debut as the Head Coach.

7. Wednesday, September 7, 20227:00am
This morning started out rough. I really didn't want to get up and do the things I committed to.

8. Thursday, September 8, 20227:00am
Today I am thankful for my health and for my energy to get up and continue this journey.
"""

# The SET of dates that actually appear in the document — nothing outside this may ever be created.
SOURCE_DATES = {
    dt.date(2022, 8, 29), dt.date(2022, 8, 30), dt.date(2022, 9, 3), dt.date(2022, 9, 4),
    dt.date(2022, 9, 5), dt.date(2022, 9, 6), dt.date(2022, 9, 7), dt.date(2022, 9, 8),
}

# What the model FABRICATED in production (dates absent from the source) — the regression input.
FABRICATED_MODEL_ENTRIES = [
    {"entry_date": "2023-10-10", "entry_time": "09:00", "body": "invented"},
    {"entry_date": "2023-10-11", "body": "invented"},
    {"entry_date": "2023-10-12", "body": "invented"},
    {"entry_date": "2023-10-13", "body": "invented"},
    {"entry_date": "2023-10-14", "body": "invented"},
    {"entry_date": "2023-10-15", "body": "invented"},
]


class DeterministicParserTests(TestCase):
    def test_extracts_exactly_the_source_headers(self):
        entries, had = parse_journal_document(DOCUMENT_TEXT)
        self.assertTrue(had)
        self.assertEqual([e["entry_date"] for e in entries], sorted(SOURCE_DATES))

    def test_no_date_outside_the_source_ever(self):
        entries, _ = parse_journal_document(DOCUMENT_TEXT)
        for e in entries:
            self.assertIn(e["entry_date"], SOURCE_DATES)
            self.assertEqual(e["entry_date"].year, 2022)  # never 2023

    def test_skipped_day(self):
        entries, _ = parse_journal_document(DOCUMENT_TEXT)
        sep5 = [e for e in entries if e["entry_date"] == dt.date(2022, 9, 5)][0]
        self.assertTrue(sep5["skipped"])

    def test_timestamps_preserved(self):
        entries, _ = parse_journal_document(DOCUMENT_TEXT)
        by_date = {e["entry_date"]: e for e in entries}
        self.assertEqual(by_date[dt.date(2022, 8, 29)]["entry_time"], dt.time(6, 30))
        self.assertEqual(by_date[dt.date(2022, 9, 4)]["entry_time"], dt.time(13, 40))
        self.assertEqual(by_date[dt.date(2022, 9, 6)]["entry_time"], dt.time(21, 38))
        self.assertIsNone(by_date[dt.date(2022, 8, 30)]["entry_time"])  # no time shown
        self.assertIsNone(by_date[dt.date(2022, 9, 3)]["entry_time"])

    def test_body_bound_to_correct_header(self):
        entries, _ = parse_journal_document(DOCUMENT_TEXT)
        by_date = {e["entry_date"]: e for e in entries}
        self.assertIn("Melanie", by_date[dt.date(2022, 8, 30)]["body"])
        self.assertIn("Haley's debut", by_date[dt.date(2022, 9, 6)]["body"])
        # A date MENTIONED inside prose is not a boundary.
        self.assertNotIn(dt.date(1960, 1, 1), SOURCE_DATES)

    def test_prose_starting_with_a_date_is_not_a_header(self):
        text = ("1. Friday, January 6, 2023\n"
                "April 7, 2022 was the day everything changed, and I wrote a long reflection "
                "about it that continues for several sentences here.\n")
        entries, had = parse_journal_document(text)
        self.assertTrue(had)
        self.assertEqual([e["entry_date"] for e in entries], [dt.date(2023, 1, 6)])

    def test_no_headers_reports_uncertainty(self):
        entries, had = parse_journal_document(
            "Just some free-form notes I typed with no dates or headers at all.")
        self.assertFalse(had)
        self.assertEqual(entries, [])

    def test_invalid_calendar_date_dropped_not_guessed(self):
        entries, _ = parse_journal_document("1. February 30, 2022\nbody\n")
        self.assertEqual(entries, [])  # Feb 30 is not a real date → never invented


class AdapterGroundingTests(TestCase):
    def setUp(self):
        self.adapter = JournalImportAdapter()

    def test_source_text_overrides_fabricated_model_dates(self):
        # The model handed WLJ six October-2023 dates; the source says Aug 29 – Sep 8 2022.
        # The document wins — every created date is from the source, none from the model.
        valid, skipped = self.adapter.validate(FABRICATED_MODEL_ENTRIES, source_text=DOCUMENT_TEXT)
        dates = {r["entry_date"] for r in valid}
        self.assertEqual(dates, SOURCE_DATES - {dt.date(2022, 9, 5)})  # Sep 5 skipped
        self.assertFalse(any(r["entry_date"].year == 2023 for r in valid))
        self.assertTrue(any(s["reason"] == "marked_skipped" for s in skipped))

    def test_uncertainty_when_document_unparseable(self):
        valid, skipped = self.adapter.validate(
            FABRICATED_MODEL_ENTRIES, source_text="notes with no headers whatsoever")
        self.assertEqual(valid, [])
        self.assertEqual(skipped[0]["reason"], "uncertain_boundaries")


class EndToEndCertification(TestCase):
    """The full production path: model fabricates dates, but WLJ grounds to the artifact text."""

    def setUp(self):
        self.user = User.objects.create_user(email="grd@ex.com", password="x")
        self.handler = ActionHandler(self.user)
        self.artifact = MultimodalArtifact.objects.create(
            user=self.user, sha256="g" * 64, content_type="application/pdf", kind="document",
            perception_status=MultimodalArtifact.PERCEPTION_DONE,
            extracted_text=DOCUMENT_TEXT)

    def test_confirmed_import_uses_source_dates_never_fabricated(self):
        result = self.handler.handle_import_journal_entries(
            entries=FABRICATED_MODEL_ENTRIES, source="journal document",
            source_artifact_id=self.artifact.id, confirmed=True)
        self.assertTrue(result.success)
        entries = JournalEntry.objects.filter(user=self.user)
        self.assertEqual(entries.count(), 7)  # 8 headers, Sep 5 skipped
        created_dates = set(entries.values_list("entry_date", flat=True))
        self.assertEqual(created_dates, SOURCE_DATES - {dt.date(2022, 9, 5)})
        # THE defect assertion: not one October-2023 date exists.
        self.assertEqual(entries.filter(entry_date__year=2023).count(), 0)
        self.assertEqual(entries.filter(entry_date__month=10).count(), 0)

    def test_document_only_no_model_entries(self):
        # The model does NOT transcribe — passes only source_artifact_id. WLJ reads the document.
        result = self.handler.handle_import_journal_entries(
            entries=None, source="journal document",
            source_artifact_id=self.artifact.id, confirmed=True)
        self.assertTrue(result.success)
        entries = JournalEntry.objects.filter(user=self.user)
        self.assertEqual(entries.count(), 7)
        self.assertEqual(set(entries.values_list("entry_date", flat=True)),
                         SOURCE_DATES - {dt.date(2022, 9, 5)})

    def test_preview_reports_source_dates(self):
        result = self.handler.handle_import_journal_entries(
            entries=FABRICATED_MODEL_ENTRIES, source="journal document",
            source_artifact_id=self.artifact.id)
        self.assertEqual(result.error, "confirmation_required")
        from apps.ai.import_confirmation import render_import_confirmation
        text = render_import_confirmation(result.confirmation_detail)
        self.assertIn("August 29, 2022", text)
        self.assertIn("September 8, 2022", text)
        self.assertNotIn("2023", text)
        self.assertNotIn("October", text)


class PerceptionTimingTests(TestCase):
    """A document import must NEVER fall back to model dates while perception is still running
    (the async window right after upload) — it reports honestly and creates nothing."""

    def setUp(self):
        self.user = User.objects.create_user(email="tim@ex.com", password="x")
        self.handler = ActionHandler(self.user)

    def test_pending_perception_reports_processing_not_model_dates(self):
        art = MultimodalArtifact.objects.create(
            user=self.user, sha256="p" * 64, content_type="application/pdf", kind="document",
            perception_status=MultimodalArtifact.PERCEPTION_PENDING)  # no extracted_text yet
        result = self.handler.handle_import_journal_entries(
            entries=FABRICATED_MODEL_ENTRIES, source="journal document",
            source_artifact_id=art.id, confirmed=True)
        self.assertFalse(result.success)
        self.assertIn("still reading", (result.message or "").lower())
        self.assertEqual(JournalEntry.objects.filter(user=self.user).count(), 0)

    def test_failed_perception_reports_unreadable(self):
        art = MultimodalArtifact.objects.create(
            user=self.user, sha256="f" * 64, content_type="application/pdf", kind="document",
            perception_status=MultimodalArtifact.PERCEPTION_FAILED)
        result = self.handler.handle_import_journal_entries(
            entries=FABRICATED_MODEL_ENTRIES, source_artifact_id=art.id, confirmed=True)
        self.assertFalse(result.success)
        self.assertIn("re-upload", (result.message or "").lower())
        self.assertEqual(JournalEntry.objects.filter(user=self.user).count(), 0)


class AttachmentSurfacingTests(TestCase):
    """The delivery payload must carry the FILENAME and an honest perception marker so the
    model can never treat a real attachment as absent."""

    def setUp(self):
        self.user = User.objects.create_user(email="surf@ex.com", password="x")

    def test_filename_and_processing_marker_surfaced_for_pending_doc(self):
        from apps.ai.multimodal import attachments_from_ids
        art = MultimodalArtifact.objects.create(
            user=self.user, sha256="s" * 64, content_type="application/pdf", kind="document",
            original_filename="Danny's Journal.docx",
            perception_status=MultimodalArtifact.PERCEPTION_PENDING)
        out = attachments_from_ids(self.user, [art.id])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["filename"], "Danny's Journal.docx")
        self.assertEqual(out[0]["perception"], "processing")

    def test_failed_perception_still_surfaces_marker(self):
        from apps.ai.multimodal import attachments_from_ids
        art = MultimodalArtifact.objects.create(
            user=self.user, sha256="t" * 64, content_type="application/pdf", kind="document",
            original_filename="notes.docx",
            perception_status=MultimodalArtifact.PERCEPTION_FAILED)
        out = attachments_from_ids(self.user, [art.id])
        self.assertEqual(out[0]["filename"], "notes.docx")
        self.assertEqual(out[0]["perception"], "unreadable")
