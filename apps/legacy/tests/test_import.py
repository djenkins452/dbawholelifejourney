"""Legacy Import Engine tests (Discovery / OpenAI always mocked)."""

from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.legacy.models import ImportBatch, ImportChunk, Memory, MemoryDiscovery
from apps.legacy.services import discovery as D
from apps.legacy.services import import_engine
from apps.legacy.services.import_adapters import (
    ImportNotAvailable, chunk, get_adapter,
)

User = get_user_model()

# Two segments each longer than the chunk target → two chunks.
_SEG = "This is a sentence about my grandfather Walter and the lake at Soddy Daisy. " * 55
SAMPLE = (
    "# My story\n\n"
    "## [1] 🤖 Assistant\n\n" + _SEG + "\n\n"
    "## [2] 🧑 Danny\n\n" + _SEG + "\n"
)


def _make_user(email="keeper@example.com"):
    from apps.users.models import TermsAcceptance
    u = User.objects.create_user(email=email, password="pw12345!")
    TermsAcceptance.objects.create(user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


class AdapterTests(TestCase):
    def test_chat_adapter_parses_messages(self):
        segs = get_adapter("chatgpt")(SAMPLE)
        self.assertEqual(len(segs), 2)
        self.assertEqual(segs[0].ref, "message 1")
        self.assertEqual(segs[1].ref, "message 2")

    def test_plain_text_adapter(self):
        segs = get_adapter("plain_text")("Para one.\n\nPara two.\n\nPara three.")
        self.assertEqual(len(segs), 3)
        self.assertEqual(segs[0].ref, "paragraph 1")

    def test_word_pdf_unavailable(self):
        with self.assertRaises(ImportNotAvailable):
            get_adapter("word")("anything")

    def test_chunker_splits_and_titles(self):
        segs = get_adapter("chatgpt")(SAMPLE)
        chunks = chunk(segs)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0]["index"], 1)
        self.assertTrue(chunks[0]["title"])
        self.assertEqual(chunks[0]["source_ref"], "message 1")


class EngineTests(TestCase):
    def setUp(self):
        self.user = _make_user()

    def test_create_batch_parses_pending_chunks(self):
        batch = import_engine.create_batch(self.user, "My story", "chatgpt", SAMPLE)
        self.assertEqual(batch.total_chunks, 2)
        self.assertEqual(batch.chunks.count(), 2)
        self.assertTrue(all(c.status == "pending" for c in batch.chunks.all()))
        self.assertEqual(batch.imported_count, 0)

    def test_import_first_two_creates_drafts_with_provenance(self):
        batch = import_engine.create_batch(self.user, "My story", "chatgpt", SAMPLE)
        with patch.object(D, "is_available", return_value=False):   # skip OpenAI
            memories = import_engine.import_chunks(batch, limit=2)
        self.assertEqual(len(memories), 2)
        m = memories[0]
        self.assertEqual(m.entry_state, Memory.EntryState.DRAFT)
        self.assertEqual(m.created_via, Memory.CREATED_VIA_IMPORT)
        self.assertEqual(m.import_batch, batch)
        self.assertEqual(m.import_chunk, 1)
        self.assertIn("Imported from My story", m.provenance_note)
        batch.refresh_from_db()
        self.assertEqual(batch.imported_count, 2)
        self.assertEqual(batch.import_status, ImportBatch.Status.COMPLETE)
        self.assertEqual(batch.chunks.filter(status="imported").count(), 2)

    def test_partial_import_then_rest(self):
        batch = import_engine.create_batch(self.user, "My story", "chatgpt", SAMPLE)
        with patch.object(D, "is_available", return_value=False):
            first = import_engine.import_chunks(batch, limit=1)
            self.assertEqual(len(first), 1)
            self.assertEqual(batch.chunks.filter(status="pending").count(), 1)
            rest = import_engine.import_chunks(batch, indices=None)  # all remaining
        self.assertEqual(len(rest), 1)
        self.assertEqual(batch.chunks.filter(status="pending").count(), 0)

    def test_import_runs_discovery(self):
        from apps.legacy.tests.test_discovery import FAKE
        batch = import_engine.create_batch(self.user, "My story", "chatgpt", SAMPLE)
        with patch.object(D, "is_available", return_value=True), \
             patch.object(D, "_extract", return_value=FAKE):
            memories = import_engine.import_chunks(batch, limit=1)
        # Same Discovery Engine ran and produced proposals — nothing canonical yet.
        self.assertTrue(MemoryDiscovery.objects.filter(memory=memories[0]).exists())
        self.assertTrue(MemoryDiscovery.objects.filter(memory=memories[0], status="proposed").exists())

    def test_batch_stats(self):
        from apps.legacy.tests.test_discovery import FAKE
        batch = import_engine.create_batch(self.user, "My story", "chatgpt", SAMPLE)
        with patch.object(D, "is_available", return_value=True), \
             patch.object(D, "_extract", return_value=FAKE):
            import_engine.import_chunks(batch, limit=2)
        stats = import_engine.batch_stats(batch)
        self.assertEqual(stats["stories_imported"], 2)
        self.assertEqual(stats["stories_total"], 2)
        self.assertGreaterEqual(stats["people"], 1)
        self.assertGreaterEqual(stats["quotes"], 1)
        self.assertGreaterEqual(stats["relationships"], 1)


class ImportViewTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.other = _make_user("other@example.com")
        self.client.force_login(self.user)

    def test_new_import_via_paste_creates_batch(self):
        r = self.client.post(reverse("legacy:import_new"), {
            "source_name": "My story", "source_type": "chatgpt", "paste": SAMPLE,
        })
        self.assertEqual(r.status_code, 302)
        batch = ImportBatch.objects.get(user=self.user, source_name="My story")
        self.assertEqual(batch.total_chunks, 2)

    def test_new_import_requires_content(self):
        r = self.client.post(reverse("legacy:import_new"), {
            "source_name": "x", "source_type": "chatgpt", "paste": ""})
        self.assertEqual(r.status_code, 200)   # re-renders form with error
        self.assertContains(r, "Upload a text file or paste")

    def test_detail_and_run(self):
        batch = import_engine.create_batch(self.user, "My story", "chatgpt", SAMPLE)
        self.assertEqual(self.client.get(reverse("legacy:import_detail", args=[batch.pk])).status_code, 200)
        with patch.object(D, "is_available", return_value=False):
            r = self.client.post(reverse("legacy:import_run", args=[batch.pk]),
                                 {"mode": "next", "count": "2"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Memory.objects.filter(user=self.user, import_batch=batch).count(), 2)

    def test_cannot_access_others_batch(self):
        batch = import_engine.create_batch(self.other, "Theirs", "chatgpt", SAMPLE)
        self.assertEqual(self.client.get(reverse("legacy:import_detail", args=[batch.pk])).status_code, 404)

    def test_login_required(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("legacy:imports")).status_code, 302)
