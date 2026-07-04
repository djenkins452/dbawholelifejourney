"""Import orchestrator: classify each unit, route narratives vs facts, aliases."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.legacy.models import ImportBatch, ImportChunk, Person, RelationshipAlias
from apps.legacy.services import relationship_aliases as aliases
from apps.legacy.services.import_classifier import classify_chunks
from apps.legacy.services.import_engine import (
    create_batch, import_chunks, narrative_pending, review_queues,
)

User = get_user_model()


def _make_user(email="keeper@example.com"):
    from apps.users.models import TermsAcceptance
    u = User.objects.create_user(email=email, password="pw12345!")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


def _by_content(units):
    """Fake classifier: 'married'/'first dog' → fact, else story."""
    out = {}
    for u in units:
        b = u["body"].lower()
        out[u["index"]] = ("fact", "high") if ("married" in b or "first dog" in b) else ("story", "medium")
    return out


class ClassifierTests(TestCase):
    def test_fallback_to_story_on_failure(self):
        units = [{"index": 0, "title": "", "body": "a"}, {"index": 1, "title": "", "body": "b"}]
        out = classify_chunks(units, classifier=lambda u: None)   # simulate a failed call
        self.assertEqual(out[0], ("story", ""))
        self.assertEqual(out[1], ("story", ""))

    def test_applies_classifier_result(self):
        units = [
            {"index": 0, "title": "", "body": "I married Heather in 1997."},
            {"index": 1, "title": "", "body": "Dad took me fishing at dawn."},
        ]
        out = classify_chunks(units, classifier=_by_content)
        self.assertEqual(out[0], ("fact", "high"))
        self.assertEqual(out[1], ("story", "medium"))

    def test_invalid_kind_becomes_unknown(self):
        units = [{"index": 0, "title": "", "body": "x"}]
        out = classify_chunks(units, classifier=lambda u: {0: ("banana", "high")})
        self.assertEqual(out[0][0], "unknown")


class CreateBatchClassifyTests(TestCase):
    def setUp(self):
        self.user = _make_user()

    def test_classification_recorded_on_chunks(self):
        text = ("I married Heather on June 7, 1997.\n\n"
                "My dad took me fishing at the lake and we talked for hours "
                "about everything that mattered to us back then.")
        batch = create_batch(self.user, "Doc", "plain_text", text, classifier=_by_content)
        kinds = {ch.chunk_kind for ch in batch.chunks.all()}
        self.assertTrue(kinds)
        for ch in batch.chunks.all():
            if "married" in ch.body.lower():
                self.assertEqual(ch.chunk_kind, "fact")


class RoutingTests(TestCase):
    def setUp(self):
        self.user = _make_user()

    def _batch_with_kinds(self, kinds):
        """Deterministic batch — one chunk per kind, no reliance on the chunker."""
        batch = ImportBatch.objects.create(
            user=self.user, source_name="Doc", source_type="plain_text",
            total_chunks=len(kinds), import_status=ImportBatch.Status.PARSED,
            created_via=ImportBatch.CREATED_VIA_IMPORT)
        for i, k in enumerate(kinds):
            ImportChunk.objects.create(
                batch=batch, index=i, title="Unit %d" % i,
                body="Paragraph %d with enough words here to count as a unit." % i,
                chunk_kind=k)
        return batch

    def test_bulk_import_skips_non_narrative(self):
        batch = self._batch_with_kinds(["fact", "story", "story"])
        mems = import_chunks(batch, run_discovery=False)                    # bulk
        self.assertEqual(len(mems), 2)                                      # only the 2 stories
        fact = batch.chunks.get(index=0)
        self.assertEqual(fact.status, ImportChunk.Status.PENDING)           # fact NOT storied
        self.assertIsNone(fact.memory)

    def test_explicit_pick_overrides_classification(self):
        batch = self._batch_with_kinds(["fact"])
        ch = batch.chunks.first()
        mems = import_chunks(batch, indices=[ch.index], run_discovery=False)  # explicit override
        self.assertEqual(len(mems), 1)
        ch.refresh_from_db()
        self.assertEqual(ch.status, ImportChunk.Status.IMPORTED)

    def test_narrative_pending_counts_only_stories(self):
        batch = self._batch_with_kinds(["fact", "story", "story", "quote"])
        self.assertEqual(narrative_pending(batch), 2)

    def test_review_queues_group_by_kind(self):
        batch = self._batch_with_kinds(["story", "fact", "quote"])
        queues = {q["kind"]: q for q in review_queues(batch)}
        self.assertIn("fact", queues)
        self.assertIn("quote", queues)
        self.assertFalse(queues["fact"]["is_narrative"])
        self.assertTrue(queues["story"]["is_narrative"])


class AliasTests(TestCase):
    def setUp(self):
        self.user = _make_user()

    def test_is_alias_term(self):
        self.assertTrue(aliases.is_alias_term("Dad"))
        self.assertTrue(aliases.is_alias_term("Dad's"))
        self.assertTrue(aliases.is_alias_term("Coach"))
        self.assertFalse(aliases.is_alias_term("Heather"))

    def test_record_and_resolve(self):
        marvin = Person.objects.create(user=self.user, display_name="Marvin Jenkins")
        aliases.record(self.user, "Dad", marvin)
        self.assertEqual(aliases.resolve(self.user, "Dad"), marvin)
        self.assertEqual(aliases.resolve(self.user, "dad's"), marvin)   # normalized
        self.assertIsNone(aliases.resolve(self.user, "Mom"))            # unmapped

    def test_record_is_idempotent(self):
        p = Person.objects.create(user=self.user, display_name="M")
        aliases.record(self.user, "Dad", p)
        aliases.record(self.user, "Dad", p)
        self.assertEqual(RelationshipAlias.objects.filter(user=self.user, alias="dad").count(), 1)

    def test_alias_scoped_to_user(self):
        other = _make_user("other@example.com")
        p = Person.objects.create(user=self.user, display_name="Mine")
        aliases.record(self.user, "Dad", p)
        self.assertIsNone(aliases.resolve(other, "Dad"))


class ImportDetailQueueViewTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.client.force_login(self.user)

    def test_detail_renders_queues(self):
        batch = ImportBatch.objects.create(
            user=self.user, source_name="My Life", source_type="plain_text",
            total_chunks=2, import_status=ImportBatch.Status.PARSED,
            created_via=ImportBatch.CREATED_VIA_IMPORT)
        ImportChunk.objects.create(batch=batch, index=0, title="A fact",
                                   body="I married Heather in 1997.", chunk_kind="fact")
        ImportChunk.objects.create(batch=batch, index=1, title="A story",
                                   body="Dad took me fishing at the lake all afternoon.",
                                   chunk_kind="story")
        r = self.client.get(reverse("legacy:import_detail", args=[batch.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "review queues")
        self.assertContains(r, "Facts")     # the fact queue heading
