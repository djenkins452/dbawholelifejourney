"""Structured Import Orchestration — CERTIFICATION against the first real production case.

The attached historical journal document (Danny's journal, Aug 30 – Sep 10 2022). This drives
the batch the model would produce THROUGH the real handler + engine and certifies the customer
experience end to end: a faithful preview (nothing written), then confirmed creation of the
real entries, Sep 5 surfaced as skipped, original bodies preserved verbatim, times preserved,
and re-import idempotent. A regression here means the customer-facing import behavior broke.

Recognition (splitting the document, excluding the repeated "Danny's Journal.docx" header noise,
normalizing dates/times) is the MODEL's job in production; this test supplies the clean batch the
model produces and certifies WLJ's deterministic half.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.action_handlers import ActionHandler
from apps.ai.import_confirmation import render_import_confirmation
from apps.ai.intent_service import IntentResult, IntentService
from apps.capture.models import MultimodalArtifact
from apps.journal.models import JournalEntry

User = get_user_model()

# The 8 dated items the model recognizes in the document (7 real entries + Sep 5 skipped).
# Bodies are representative excerpts of the originals (verbatim — never rewritten).
DOCUMENT_ENTRIES = [
    {"entry_date": "2022-09-10", "entry_time": "10:00",
     "body": "Yesterday was extremely busy. All because I started the day off wrong."},
    {"entry_date": "2022-09-08", "entry_time": "07:00",
     "body": "Today I am thankful for my health and for my energy to get up and continue "
             "this journey."},
    {"entry_date": "2022-09-07", "entry_time": "07:00",
     "body": "Wishing my brother a happy birthday. Born in 1960 would make him 62 today."},
    {"entry_date": "2022-09-06", "entry_time": "21:38",
     "body": "Today has been a good day. Very busy at work.\n\nToday was Haley's debut as "
             "the Head Coach."},
    {"entry_date": "2022-09-05", "skipped": True},
    {"entry_date": "2022-09-04", "entry_time": "13:40",
     "body": "Today has been a great day. Heather and I made the decision to take control "
             "of our lives."},
    {"entry_date": "2022-09-03",
     "body": "A moment that I really appreciated today was when Heather did the dishes this "
             "morning."},
    {"entry_date": "2022-08-30",
     "body": "Overall, today was a great day. Other than the way the day ended with my "
             "interaction with Melanie around my comp training."},
]


class JournalImportCertification(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="cert@ex.com", password="x")
        self.handler = ActionHandler(self.user)

    # ── 1. Preview: faithful, and writes nothing ────────────────────────────
    def test_preview_reports_findings_and_writes_nothing(self):
        result = self.handler.handle_import_journal_entries(
            entries=DOCUMENT_ENTRIES, source="journal document")
        self.assertFalse(result.success)
        self.assertEqual(result.error, "confirmation_required")
        self.assertEqual(JournalEntry.objects.filter(user=self.user).count(), 0)

        text = render_import_confirmation(result.confirmation_detail)
        self.assertIn("Found 8 entries", text)
        self.assertIn("August 30, 2022 through September 10, 2022", text)
        self.assertIn("7 will be imported", text)
        self.assertIn("5 have a recorded time", text)
        self.assertIn("2 have no recorded time", text)
        # Sep 5 is surfaced as skipped, with the reason — never silently dropped.
        self.assertIn("Monday, September 5, 2022", text)
        self.assertIn("marked this day as skipped", text)

    # ── 2. Confirmed: creates the real entries, skips Sep 5 ──────────────────
    def test_confirmed_creates_seven_entries(self):
        result = self.handler.handle_import_journal_entries(
            entries=DOCUMENT_ENTRIES, source="journal document", confirmed=True)
        self.assertTrue(result.success)
        self.assertEqual(result.created_object["created"], 7)
        self.assertEqual(result.created_object["skipped"], 1)

        entries = JournalEntry.objects.filter(user=self.user)
        self.assertEqual(entries.count(), 7)
        self.assertFalse(entries.filter(entry_date="2022-09-05").exists())

    # ── 3. Faithful preservation of date, time, title, and body ─────────────
    def test_entry_fidelity(self):
        self.handler.handle_import_journal_entries(
            entries=DOCUMENT_ENTRIES, source="journal document", confirmed=True)
        e = JournalEntry.objects.get(user=self.user, entry_date="2022-09-10")
        self.assertEqual(str(e.entry_time), "10:00:00")
        self.assertEqual(e.title, "Saturday, September 10, 2022 – 10:00 AM")
        self.assertEqual(e.created_via, "import")
        # Body preserved verbatim (the plain shadow carries the original words).
        self.assertIn("started the day off wrong", e.body_plain)

        # A pm time is preserved correctly (9:38pm → 21:38).
        pm = JournalEntry.objects.get(user=self.user, entry_date="2022-09-06")
        self.assertEqual(str(pm.entry_time), "21:38:00")
        self.assertIn("9:38 PM", pm.title)

        # A timeless entry keeps entry_time null and a date-only title.
        timeless = JournalEntry.objects.get(user=self.user, entry_date="2022-08-30")
        self.assertIsNone(timeless.entry_time)
        self.assertEqual(timeless.title, "Tuesday, August 30, 2022")

    # ── 4. Idempotent re-import from the same artifact ──────────────────────
    def test_reimport_same_artifact_is_idempotent(self):
        # An IMAGE journal — the model reads the photo and provides entries (no document text
        # to ground against), so the model-provided records are the source here.
        art = MultimodalArtifact.objects.create(
            user=self.user, sha256="c" * 64, content_type="image/jpeg", kind="image")
        first = self.handler.handle_import_journal_entries(
            entries=DOCUMENT_ENTRIES, source="journal document",
            source_artifact_id=art.id, confirmed=True)
        self.assertTrue(first.success)
        self.assertEqual(JournalEntry.objects.filter(user=self.user).count(), 7)

        again = self.handler.handle_import_journal_entries(
            entries=DOCUMENT_ENTRIES, source="journal document",
            source_artifact_id=art.id, confirmed=True)
        self.assertTrue(again.success)
        self.assertIn("already imported", again.message)
        self.assertEqual(JournalEntry.objects.filter(user=self.user).count(), 7)

    # ── 5. Full dispatch path (execute_intent → handler) ────────────────────
    def test_dispatch_through_execute_intent(self):
        intent = IntentResult(intent_type="import_journal_entries",
                              parameters={"entries": DOCUMENT_ENTRIES,
                                          "source": "journal document", "confirmed": True},
                              confidence=1.0)
        result = IntentService().execute_intent(intent, self.user)
        self.assertTrue(result.success)
        self.assertEqual(JournalEntry.objects.filter(user=self.user).count(), 7)
