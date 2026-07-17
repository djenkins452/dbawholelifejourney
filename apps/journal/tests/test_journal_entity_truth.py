# ==============================================================================
# File: apps/journal/tests/test_journal_entity_truth.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The Journal ENTITY truth surface — record-level journal retrieval for
#   the Model Interface. Root cause fix (2026-07-17): "what was my journal about
#   yesterday?" / "what was my mood yesterday?" could not resolve to journal content
#   (journal exposed no entity surface), so the model fell through to a cross-domain
#   search that surfaced unrelated health metrics (walking speed, audio exposure).
#   mood/emotions are FIELDS on JournalEntry — journal content, not a separate domain.
#   Additive: extends the canonical JournalQueries + JournalDomainTruth; nothing else
#   changes. Verifies the fix AND that existing entity surfaces are unregressed.
# ==============================================================================
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.cos_services.domain_entity import (
    entity_capability_index, get_domain_entity,
)
from apps.journal.models import Emotion, JournalEntry
from apps.journal.services.journal_queries import JournalQueries

User = get_user_model()


class JournalEntitySurfaceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="jent@test.com", password="x")
        self.today = date.today()
        e = JournalEntry.objects.create(
            user=self.user, entry_date=self.today - timedelta(days=1),
            title="Rough day", body="<p>Felt tired but pushed through my workout.</p>",
            mood="tired")
        e.emotions.add(Emotion.objects.get_or_create(name="fatigue")[0])
        JournalEntry.objects.create(
            user=self.user, entry_date=self.today - timedelta(days=3),
            title="Good news", body="<p>Got the promotion!</p>", mood="happy")

    def test_journal_is_now_entity_capable(self):
        self.assertEqual(entity_capability_index().get("journal"), ("entry",))

    def test_list_entries_returns_content_mood_and_emotions(self):
        r = get_domain_entity(self.user, "journal", entity_type="entry")
        self.assertEqual(r["status"], "ready")
        self.assertEqual(r["count"], 2)
        top = r["entities"][0]                      # newest first
        self.assertIn("Rough day", top["identity"])
        self.assertEqual(top["definition"]["mood"], "tired")
        self.assertEqual(top["definition"]["emotions"], ["fatigue"])
        # the narrative body is the plain-text shadow — never raw HTML
        self.assertEqual(top["extensions"]["content"],
                         "Felt tired but pushed through my workout.")
        self.assertNotIn("<p>", top["extensions"]["content"])

    def test_mood_is_answerable_from_journal_truth(self):
        # "what was my mood yesterday?" — mood is a field, resolvable by date lookup.
        r = get_domain_entity(self.user, "journal",
                              name=str(self.today - timedelta(days=1)))
        self.assertEqual(r["status"], "ready")
        self.assertEqual(r["entity"]["definition"]["mood"], "tired")

    def test_lookup_by_title(self):
        r = get_domain_entity(self.user, "journal", name="promotion")
        # title contains "Good news", not "promotion"; body has it — title match returns None,
        # but the date form is the primary path. Confirm a real title substring resolves:
        r2 = get_domain_entity(self.user, "journal", name="Good news")
        self.assertEqual(r2["status"], "ready")
        self.assertEqual(r2["entity"]["definition"]["mood"], "happy")

    def test_empty_when_no_entries(self):
        other = User.objects.create_user(email="empty@test.com", password="x")
        r = get_domain_entity(other, "journal", entity_type="entry")
        self.assertEqual(r["status"], "empty")

    def test_queries_layer_returns_complete_entities(self):
        ents = JournalQueries.describe(self.user)
        self.assertEqual(len(ents), 2)
        self.assertEqual(ents[0].kind, "journal_entry")
        self.assertEqual(ents[0].definition["mood"], "tired")


class ExistingEntitySurfacesUnregressedTests(TestCase):
    """The change is purely additive — the other entity-capable domains are intact."""

    def test_entity_capability_index_still_has_health_and_medicine(self):
        idx = entity_capability_index()
        self.assertIn("workout", idx.get("health", ()))
        self.assertIn("medication", idx.get("medicine", ()))
        self.assertIn("person", idx.get("legacy", ()))
        # journal is added, not swapped in
        self.assertIn("entry", idx.get("journal", ()))

    def test_health_and_medicine_entities_still_resolve(self):
        u = User.objects.create_user(email="reg@test.com", password="x")
        # honest "empty" (no seeded data) — a valid state, not an error/regression
        self.assertEqual(get_domain_entity(u, "health", entity_type="workout")["status"],
                         "empty")
        self.assertEqual(
            get_domain_entity(u, "medicine", entity_type="medication")["status"], "empty")
