"""Structured Import Orchestration — engine + Journal adapter unit tests.

docs/WLJ_STRUCTURED_IMPORT_ARCHITECTURE.md. Proves the reusable spine: per-record
validation, the preview/confirmation gate (nothing written until confirmed), atomic
creation, faithful body preservation, entry_time as first-class truth, dedup, artifact
idempotency, provenance (StructuredImportRun + link_artifact), and honest counts.
"""
import datetime as dt

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.import_adapters.journal_import import JournalImportAdapter, _plain_to_html
from apps.ai.models import StructuredImportRun
from apps.ai.structured_import import ImportOutcome, get_import_adapter, run_structured_import
from apps.capture.models import MultimodalArtifact
from apps.journal.models import JournalEntry

User = get_user_model()


class AdapterRegistryTests(TestCase):
    def test_journal_adapter_registered(self):
        self.assertIsInstance(get_import_adapter("import_journal_entries"),
                              JournalImportAdapter)


class JournalValidateTests(TestCase):
    def setUp(self):
        self.adapter = JournalImportAdapter()

    def test_valid_entry_normalized(self):
        valid, skipped = self.adapter.validate([
            {"entry_date": "2022-09-10", "entry_time": "10:00 AM", "body": "Busy day."},
        ])
        self.assertEqual(len(valid), 1)
        self.assertEqual(skipped, [])
        r = valid[0]
        self.assertEqual(r["entry_date"], dt.date(2022, 9, 10))
        self.assertEqual(r["entry_time"], dt.time(10, 0))
        self.assertTrue(r["has_time"])
        self.assertEqual(r["title"], "Saturday, September 10, 2022 – 10:00 AM")
        self.assertIn("<p>Busy day.</p>", r["body_html"])

    def test_no_time_entry(self):
        valid, _ = self.adapter.validate([
            {"entry_date": "2022-08-30", "body": "Great day."}])
        self.assertEqual(valid[0]["entry_time"], None)
        self.assertFalse(valid[0]["has_time"])
        self.assertEqual(valid[0]["title"], "Tuesday, August 30, 2022")

    def test_marked_skipped_surfaced_not_created(self):
        valid, skipped = self.adapter.validate([
            {"entry_date": "2022-09-05", "skipped": True}])
        self.assertEqual(valid, [])
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0]["reason"], "marked_skipped")
        self.assertEqual(skipped[0]["date_iso"], "2022-09-05")

    def test_invalid_date_skipped_never_dropped(self):
        valid, skipped = self.adapter.validate([{"entry_date": "not a date", "body": "x"}])
        self.assertEqual(valid, [])
        self.assertEqual(skipped[0]["reason"], "invalid_date")

    def test_empty_body_skipped(self):
        valid, skipped = self.adapter.validate([
            {"entry_date": "2022-09-01", "body": "   "}])
        self.assertEqual(valid, [])
        self.assertEqual(skipped[0]["reason"], "no_content")

    def test_human_date_and_2digit_year_fallback(self):
        valid, _ = self.adapter.validate([{"entry_date": "Aug 30, 22", "body": "x"}])
        self.assertEqual(valid[0]["entry_date"], dt.date(2022, 8, 30))

    def test_body_preserves_paragraphs_and_escapes(self):
        html = _plain_to_html("Line one.\n\nLine two <b>raw</b>.")
        self.assertIn("<p>Line one.</p>", html)
        self.assertIn("&lt;b&gt;", html)          # escaped, never rewritten
        self.assertEqual(html.count("<p>"), 2)


class EngineFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="imp@ex.com", password="x")
        self.adapter = JournalImportAdapter()
        self.records = [
            {"entry_date": "2022-09-10", "entry_time": "10:00 AM", "body": "A."},
            {"entry_date": "2022-09-08", "entry_time": "7:00 AM", "body": "B."},
            {"entry_date": "2022-09-05", "skipped": True},
        ]

    def test_preview_writes_nothing(self):
        out = run_structured_import(self.user, self.adapter, self.records,
                                    source="journal document", confirmed=False)
        self.assertIsInstance(out, ImportOutcome)
        self.assertEqual(out.status, "confirmation_required")
        self.assertEqual(JournalEntry.objects.filter(user=self.user).count(), 0)
        self.assertEqual(out.confirmation_detail["renderer"], "journal_import")
        self.assertEqual(len(out.confirmation_detail["records"]), 2)
        self.assertEqual(len(out.confirmation_detail["skipped"]), 1)

    def test_confirmed_creates_and_skips(self):
        out = run_structured_import(self.user, self.adapter, self.records,
                                    source="journal document", confirmed=True)
        self.assertEqual(out.status, "success")
        self.assertEqual(out.counts, {"created": 2, "skipped": 1,
                                      "duplicate": 0, "failed": 0})
        entries = JournalEntry.objects.filter(user=self.user).order_by("entry_date")
        self.assertEqual(entries.count(), 2)
        self.assertEqual(entries[0].entry_date, dt.date(2022, 9, 8))
        self.assertEqual(entries[0].entry_time, dt.time(7, 0))
        self.assertEqual(entries[0].created_via, "import")
        # Sep 5 (skipped) was never created.
        self.assertFalse(entries.filter(entry_date=dt.date(2022, 9, 5)).exists())

    def test_run_recorded_with_manifest(self):
        run_structured_import(self.user, self.adapter, self.records,
                              source="journal document", confirmed=True)
        run = StructuredImportRun.objects.get(user=self.user)
        self.assertEqual(run.target_domain, "journal")
        self.assertEqual(run.created_count, 2)
        self.assertEqual(run.skipped_count, 1)
        outcomes = {m["outcome"] for m in run.manifest}
        self.assertEqual(outcomes, {"created", "skipped"})

    def test_dedup_on_rerun_without_artifact(self):
        run_structured_import(self.user, self.adapter, self.records, confirmed=True)
        # Re-run the SAME records (no artifact id) → per-record dedup catches them all.
        out = run_structured_import(self.user, self.adapter, self.records, confirmed=True)
        self.assertEqual(out.counts["created"], 0)
        self.assertEqual(out.counts["duplicate"], 2)
        self.assertEqual(JournalEntry.objects.filter(user=self.user).count(), 2)

    def test_artifact_idempotency(self):
        art = MultimodalArtifact.objects.create(
            user=self.user, sha256="j" * 64, content_type="application/pdf", kind="document")
        run_structured_import(self.user, self.adapter, self.records,
                              source_artifact_id=art.id, confirmed=True)
        art.refresh_from_db()
        self.assertEqual(art.status, "resolved")
        self.assertEqual(art.resolved_intent, "import_journal_entries")
        self.assertEqual(art.resolved_object_type, "StructuredImportRun")
        # Same artifact again → idempotent, no new entries.
        out = run_structured_import(self.user, self.adapter, self.records,
                                    source_artifact_id=art.id, confirmed=True)
        self.assertEqual(out.status, "success")
        self.assertIn("already imported", out.message)
        self.assertEqual(JournalEntry.objects.filter(user=self.user).count(), 2)
        self.assertEqual(StructuredImportRun.objects.filter(user=self.user).count(), 1)

    def test_owner_scoped_dedup(self):
        other = User.objects.create_user(email="other@ex.com", password="x")
        run_structured_import(self.user, self.adapter, self.records, confirmed=True)
        # Another user importing identical records is NOT a duplicate for them.
        out = run_structured_import(other, self.adapter, self.records, confirmed=True)
        self.assertEqual(out.counts["created"], 2)

    def test_empty_document(self):
        out = run_structured_import(self.user, self.adapter, [], confirmed=True)
        self.assertEqual(out.status, "validation_failed")
        self.assertEqual(JournalEntry.objects.filter(user=self.user).count(), 0)
