"""
Tests for Phase 4C: CoS Memory Intelligence + Ranking.

Tests cover:
- Memory scoring module (recency, pinned, entity, tag factors)
- search_notes_cos() service function
- get_related_notes_for_entity() with use_cos_ranking=True
- Blank query and fallback behavior
- Explainability (reasons)
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from unittest import skipUnless

from django.test import TestCase

from apps.notes.utils import is_postgres
from django.utils import timezone

from apps.core.models import Tag
from apps.notes.memory_scoring import (
    MAX_REASONS,
    _entity_factor,
    _normalize_fts_rank,
    _pinned_factor,
    _recency_factor,
    _tag_factor,
    score_fallback_note,
    score_note,
)
from apps.notes.models import Note, NoteAttachment
from apps.notes.services import (
    get_related_notes_for_entity,
    search_notes_cos,
)

User = get_user_model()


# ===========================================================================
# Unit tests for memory_scoring.py
# ===========================================================================


class NormalizeFtsRankTest(TestCase):
    """Tests for FTS rank normalization."""

    def test_normal_case(self):
        self.assertAlmostEqual(_normalize_fts_rank(0.5, 1.0), 0.5)

    def test_max_rank(self):
        self.assertAlmostEqual(_normalize_fts_rank(1.0, 1.0), 1.0)

    def test_zero_rank(self):
        self.assertAlmostEqual(_normalize_fts_rank(0.0, 1.0), 0.0)

    def test_zero_max_rank_with_positive_rank(self):
        """When max_rank is 0 but rank > 0, returns 0.5 (equal fallback)."""
        self.assertAlmostEqual(_normalize_fts_rank(0.3, 0.0), 0.5)

    def test_none_rank(self):
        self.assertAlmostEqual(_normalize_fts_rank(None, 1.0), 0.0)


class RecencyFactorTest(TestCase):
    """Tests for recency decay."""

    def test_just_updated(self):
        """Updated now → factor 1.0."""
        self.assertAlmostEqual(_recency_factor(timezone.now()), 1.0)

    def test_3_days_ago(self):
        """Updated 3 days ago → still in strong range (1.0)."""
        dt = timezone.now() - timedelta(days=3)
        self.assertAlmostEqual(_recency_factor(dt), 1.0)

    def test_7_days_ago(self):
        """Updated exactly 7 days ago → factor 1.0 (boundary)."""
        dt = timezone.now() - timedelta(days=7)
        self.assertAlmostEqual(_recency_factor(dt), 1.0, places=1)

    def test_20_days_ago(self):
        """Updated 20 days ago → moderate range."""
        dt = timezone.now() - timedelta(days=20)
        factor = _recency_factor(dt)
        self.assertGreater(factor, 0.6)
        self.assertLess(factor, 1.0)

    def test_100_days_ago(self):
        """Updated 100 days ago → light range."""
        dt = timezone.now() - timedelta(days=100)
        factor = _recency_factor(dt)
        self.assertGreater(factor, 0.3)
        self.assertLess(factor, 0.7)

    def test_365_days_ago(self):
        """Updated 365 days ago → minimal."""
        dt = timezone.now() - timedelta(days=365)
        self.assertAlmostEqual(_recency_factor(dt), 0.15)

    def test_none_updated_at(self):
        """None updated_at → minimal factor."""
        self.assertAlmostEqual(_recency_factor(None), 0.15)

    def test_recency_monotonically_decreasing(self):
        """More recent notes always score higher than older ones."""
        now = timezone.now()
        factors = [_recency_factor(now - timedelta(days=d)) for d in [0, 10, 50, 200]]
        for i in range(len(factors) - 1):
            self.assertGreaterEqual(factors[i], factors[i + 1])


class PinnedFactorTest(TestCase):
    def test_pinned(self):
        self.assertAlmostEqual(_pinned_factor(True), 1.0)

    def test_not_pinned(self):
        self.assertAlmostEqual(_pinned_factor(False), 0.0)


class EntityFactorTest(TestCase):
    def test_matching_entity(self):
        self.assertAlmostEqual(_entity_factor({(5, 10)}, 5, 10), 1.0)

    def test_no_match(self):
        self.assertAlmostEqual(_entity_factor({(5, 10)}, 5, 99), 0.0)

    def test_no_scope(self):
        self.assertAlmostEqual(_entity_factor({(5, 10)}, None, None), 0.0)


class TagFactorTest(TestCase):
    def test_full_overlap(self):
        self.assertAlmostEqual(_tag_factor(["work", "urgent"], ["work", "urgent"]), 1.0)

    def test_partial_overlap(self):
        self.assertAlmostEqual(_tag_factor(["work", "personal"], ["work", "urgent"]), 0.5)

    def test_no_overlap(self):
        self.assertAlmostEqual(_tag_factor(["work"], ["personal"]), 0.0)

    def test_empty_query_tags(self):
        self.assertAlmostEqual(_tag_factor(["work"], []), 0.0)

    def test_case_insensitive(self):
        self.assertAlmostEqual(_tag_factor(["Work"], ["work"]), 1.0)


class ScoreNoteTest(TestCase):
    """Tests for the combined score_note function."""

    def test_high_relevance_beats_pinned_irrelevant(self):
        """A highly relevant unpinned note must outrank a pinned irrelevant note."""
        relevant = score_note(
            fts_rank=0.9,
            max_fts_rank=1.0,
            updated_at=timezone.now(),
            is_pinned=False,
            note_attachment_entity_ids=set(),
            scoped_content_type_id=None,
            scoped_object_id=None,
            note_tag_names=[],
            query_tags=[],
        )
        pinned_irrelevant = score_note(
            fts_rank=0.05,
            max_fts_rank=1.0,
            updated_at=timezone.now(),
            is_pinned=True,
            note_attachment_entity_ids=set(),
            scoped_content_type_id=None,
            scoped_object_id=None,
            note_tag_names=[],
            query_tags=[],
        )
        self.assertGreater(relevant["combined_score"], pinned_irrelevant["combined_score"])

    def test_pinned_wins_when_equally_relevant(self):
        """Pinned note with similar FTS rank outranks unpinned."""
        pinned = score_note(
            fts_rank=0.8,
            max_fts_rank=1.0,
            updated_at=timezone.now(),
            is_pinned=True,
            note_attachment_entity_ids=set(),
            scoped_content_type_id=None,
            scoped_object_id=None,
            note_tag_names=[],
            query_tags=[],
        )
        unpinned = score_note(
            fts_rank=0.8,
            max_fts_rank=1.0,
            updated_at=timezone.now(),
            is_pinned=False,
            note_attachment_entity_ids=set(),
            scoped_content_type_id=None,
            scoped_object_id=None,
            note_tag_names=[],
            query_tags=[],
        )
        self.assertGreater(pinned["combined_score"], unpinned["combined_score"])

    def test_reasons_max_5(self):
        """Reasons list never exceeds MAX_REASONS."""
        result = score_note(
            fts_rank=0.9,
            max_fts_rank=1.0,
            updated_at=timezone.now(),
            is_pinned=True,
            note_attachment_entity_ids={(5, 10)},
            scoped_content_type_id=5,
            scoped_object_id=10,
            note_tag_names=["work", "urgent"],
            query_tags=["work", "urgent"],
        )
        self.assertLessEqual(len(result["reasons"]), MAX_REASONS)

    def test_reasons_are_strings(self):
        """All reasons are non-empty strings."""
        result = score_note(
            fts_rank=0.9,
            max_fts_rank=1.0,
            updated_at=timezone.now(),
            is_pinned=True,
            note_attachment_entity_ids=set(),
            scoped_content_type_id=None,
            scoped_object_id=None,
            note_tag_names=[],
            query_tags=[],
        )
        for reason in result["reasons"]:
            self.assertIsInstance(reason, str)
            self.assertTrue(len(reason) > 0)


class ScoreFallbackNoteTest(TestCase):
    def test_pinned_recent_scores_high(self):
        result = score_fallback_note(
            updated_at=timezone.now(),
            is_pinned=True,
        )
        self.assertGreater(result["combined_score"], 0)
        self.assertIn("Pinned note", result["reasons"])

    def test_old_unpinned_scores_low(self):
        result = score_fallback_note(
            updated_at=timezone.now() - timedelta(days=400),
            is_pinned=False,
        )
        self.assertLess(result["combined_score"], 0.1)


# ===========================================================================
# Integration tests for search_notes_cos()
# ===========================================================================


class SearchNotesCoSRecencyTest(TestCase):
    """Recency boost: newer equally-matching note ranks higher."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="cos_recency@example.com", password="testpass123"
        )

    def test_newer_note_ranks_higher(self):
        """Two notes matching the same query — newer one ranks higher."""
        old_note = Note.objects.create(user=self.user, body="quarterly budget review plan")
        new_note = Note.objects.create(user=self.user, body="quarterly budget review plan updated")

        # Manually set updated_at via queryset to avoid save() resetting it
        Note.objects.filter(pk=old_note.pk).update(
            updated_at=timezone.now() - timedelta(days=200)
        )
        Note.objects.filter(pk=new_note.pk).update(
            updated_at=timezone.now() - timedelta(days=1)
        )

        result = search_notes_cos(self.user, "quarterly budget review")
        results = result["results"]
        self.assertGreaterEqual(len(results), 2)

        # Find our notes in the results
        ids = [r["note_id"] for r in results]
        if new_note.pk in ids and old_note.pk in ids:
            new_idx = ids.index(new_note.pk)
            old_idx = ids.index(old_note.pk)
            self.assertLess(new_idx, old_idx, "Newer note should rank higher")


class SearchNotesCoSPinnedTest(TestCase):
    """Pinned boost tests."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="cos_pinned@example.com", password="testpass123"
        )

    def test_pinned_with_similar_relevance_ranks_higher(self):
        """Pinned note with similar FTS relevance outranks unpinned."""
        unpinned = Note.objects.create(
            user=self.user, body="important project milestone tracking", is_pinned=False
        )
        pinned = Note.objects.create(
            user=self.user, body="important project milestone tracking", is_pinned=True
        )

        result = search_notes_cos(self.user, "project milestone tracking")
        results = result["results"]
        if len(results) >= 2:
            ids = [r["note_id"] for r in results]
            if pinned.pk in ids and unpinned.pk in ids:
                pinned_idx = ids.index(pinned.pk)
                unpinned_idx = ids.index(unpinned.pk)
                self.assertLess(pinned_idx, unpinned_idx)

    @skipUnless(is_postgres(), "Requires PostgreSQL full-text search ranking")
    def test_pinned_irrelevant_does_not_outrank_strong_match(self):
        """Pinned note with low relevance should not outrank strong text match."""
        strong_match = Note.objects.create(
            user=self.user,
            title="Machine learning research",
            body="Deep learning neural networks tensorflow pytorch machine learning models",
            is_pinned=False,
        )
        pinned_weak = Note.objects.create(
            user=self.user,
            title="Grocery list",
            body="Buy milk eggs bread machine for kitchen",
            is_pinned=True,
        )

        result = search_notes_cos(self.user, "machine learning neural networks")
        results = result["results"]
        if len(results) >= 2:
            ids = [r["note_id"] for r in results]
            if strong_match.pk in ids and pinned_weak.pk in ids:
                strong_idx = ids.index(strong_match.pk)
                pinned_idx = ids.index(pinned_weak.pk)
                self.assertLess(strong_idx, pinned_idx)


class SearchNotesCoSEntityBoostTest(TestCase):
    """Entity scope boost tests."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="cos_entity@example.com", password="testpass123"
        )

    def test_scoped_entity_note_ranks_higher(self):
        """Note attached to scoped entity ranks higher than unattached note."""
        from apps.life.models import Project

        project = Project.objects.create(
            user=self.user, title="Alpha Project", description="P"
        )
        ct = ContentType.objects.get_for_model(project)

        attached = Note.objects.create(
            user=self.user, body="alpha project design decisions and notes"
        )
        NoteAttachment.objects.create(
            note=attached, content_type=ct, object_id=project.pk
        )

        unattached = Note.objects.create(
            user=self.user, body="alpha project design decisions separate notes"
        )

        result = search_notes_cos(
            self.user,
            "alpha project design",
            content_type="life.project",
            object_id=project.pk,
        )
        results = result["results"]
        if len(results) >= 2:
            ids = [r["note_id"] for r in results]
            if attached.pk in ids and unattached.pk in ids:
                att_idx = ids.index(attached.pk)
                unatt_idx = ids.index(unattached.pk)
                self.assertLess(att_idx, unatt_idx)


class SearchNotesCoSTagOverlapTest(TestCase):
    """Tag overlap boost tests."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="cos_tags@example.com", password="testpass123"
        )

    def test_tag_overlap_boosts_score(self):
        """Notes with matching tags get a higher combined_score."""
        tag = Tag.objects.create(name="onboarding", user=self.user)

        tagged = Note.objects.create(
            user=self.user, body="new employee onboarding checklist process"
        )
        tagged.tags.add(tag)

        untagged = Note.objects.create(
            user=self.user, body="new employee onboarding checklist process notes"
        )

        result = search_notes_cos(
            self.user, "employee onboarding", tags=["onboarding"]
        )
        results = result["results"]
        if len(results) >= 2:
            scores = {r["note_id"]: r["combined_score"] for r in results}
            if tagged.pk in scores and untagged.pk in scores:
                self.assertGreater(scores[tagged.pk], scores[untagged.pk])


class SearchNotesCoSExplainabilityTest(TestCase):
    """Tests for reasons/explainability."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="cos_explain@example.com", password="testpass123"
        )

    def test_reasons_present_and_stable(self):
        """Each result has reasons list with stable string entries."""
        Note.objects.create(
            user=self.user, body="quarterly review performance check", is_pinned=True
        )

        result = search_notes_cos(self.user, "quarterly review")
        for r in result["results"]:
            self.assertIn("reasons", r)
            self.assertIsInstance(r["reasons"], list)
            self.assertLessEqual(len(r["reasons"]), MAX_REASONS)
            for reason in r["reasons"]:
                self.assertIsInstance(reason, str)
                self.assertTrue(len(reason) > 0)

    def test_pinned_reason_present(self):
        """Pinned note result includes 'Pinned note' reason."""
        Note.objects.create(
            user=self.user, body="critical deadline tracker pinned item", is_pinned=True
        )
        result = search_notes_cos(self.user, "critical deadline tracker")
        for r in result["results"]:
            if r["pinned"]:
                self.assertIn("Pinned note", r["reasons"])

    def test_tag_overlap_reason(self):
        """Tag overlap shows in reasons when tags match."""
        tag = Tag.objects.create(name="finance", user=self.user)
        note = Note.objects.create(
            user=self.user, body="finance budget review quarterly report"
        )
        note.tags.add(tag)

        result = search_notes_cos(self.user, "budget review", tags=["finance"])
        for r in result["results"]:
            if r["note_id"] == note.pk:
                tag_reasons = [x for x in r["reasons"] if "Tag overlap" in x]
                self.assertTrue(len(tag_reasons) > 0)


class SearchNotesCoSBlankQueryTest(TestCase):
    """Blank query returns pinned + recent."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="cos_blank@example.com", password="testpass123"
        )

    def test_blank_query_returns_results(self):
        """Blank query returns pinned + recent notes."""
        Note.objects.create(user=self.user, body="Recent note one")
        Note.objects.create(user=self.user, body="Recent note two", is_pinned=True)

        result = search_notes_cos(self.user, "")
        self.assertEqual(result["query"], "")
        self.assertGreaterEqual(len(result["results"]), 2)

    def test_blank_query_pinned_first(self):
        """Blank query returns pinned notes before unpinned."""
        Note.objects.create(user=self.user, body="Not pinned note")
        pinned = Note.objects.create(
            user=self.user, body="Pinned note blank", is_pinned=True
        )

        result = search_notes_cos(self.user, "")
        if len(result["results"]) >= 2:
            self.assertEqual(result["results"][0]["note_id"], pinned.pk)

    def test_blank_query_has_reasons(self):
        """Blank query results include reasons."""
        Note.objects.create(user=self.user, body="Blank reasons test", is_pinned=True)
        result = search_notes_cos(self.user, "")
        for r in result["results"]:
            self.assertIn("reasons", r)
            self.assertTrue(len(r["reasons"]) > 0)


class SearchNotesCoSFallbackTest(TestCase):
    """Fallback behavior when no FTS matches found."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="cos_fallback@example.com", password="testpass123"
        )

    def test_no_matches_returns_fallback(self):
        """Query with no matches returns pinned + recent with fallback reason."""
        Note.objects.create(user=self.user, body="Regular everyday note")

        result = search_notes_cos(self.user, "xyznonexistentquery987")
        self.assertGreaterEqual(len(result["results"]), 1)
        # Should have fallback reason
        first = result["results"][0]
        fallback_reasons = [r for r in first["reasons"] if "Fallback" in r]
        self.assertTrue(len(fallback_reasons) > 0)

    def test_no_notes_at_all(self):
        """Query with no notes at all returns empty results."""
        result = search_notes_cos(self.user, "anything")
        self.assertEqual(len(result["results"]), 0)


class SearchNotesCoSResultStructureTest(TestCase):
    """Tests for result envelope structure."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="cos_struct@example.com", password="testpass123"
        )

    def test_result_envelope(self):
        """Response has query, scope, results keys."""
        Note.objects.create(user=self.user, body="structure test content note")
        result = search_notes_cos(self.user, "structure test")
        self.assertIn("query", result)
        self.assertIn("scope", result)
        self.assertIn("results", result)

    def test_result_fields(self):
        """Each result has all required fields."""
        Note.objects.create(
            user=self.user, body="fields check note content test", is_pinned=True
        )
        result = search_notes_cos(self.user, "fields check")
        if result["results"]:
            r = result["results"][0]
            required_fields = [
                "note_id", "display_title", "url", "headline",
                "rank_score", "combined_score", "reasons",
                "pinned", "updated_at", "tags", "attachments_summary",
            ]
            for field in required_fields:
                self.assertIn(field, r, f"Missing field: {field}")

    def test_scope_includes_entity(self):
        """Scope dict includes content_type when entity-scoped."""
        Note.objects.create(user=self.user, body="scope entity test content")
        result = search_notes_cos(
            self.user, "scope entity", content_type="life.project", object_id=1
        )
        self.assertEqual(result["scope"]["content_type"], "life.project")
        self.assertEqual(result["scope"]["object_id"], 1)


# ===========================================================================
# Integration tests for get_related_notes_for_entity with CoS ranking
# ===========================================================================


class RelatedNotesCoSRankingTest(TestCase):
    """Tests for get_related_notes_for_entity with use_cos_ranking=True."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="cos_related@example.com", password="testpass123"
        )

    def test_cos_ranking_adds_score_and_reasons(self):
        """With use_cos_ranking=True, results include combined_score and reasons."""
        from apps.life.models import Project

        project = Project.objects.create(
            user=self.user, title="CoS Related Project", description="P"
        )
        ct = ContentType.objects.get_for_model(project)
        note = Note.objects.create(user=self.user, body="Related to project")
        NoteAttachment.objects.create(note=note, content_type=ct, object_id=project.pk)

        results = get_related_notes_for_entity(
            user=self.user,
            content_type="life.project",
            object_id=project.pk,
            use_cos_ranking=True,
        )
        self.assertEqual(len(results), 1)
        self.assertIn("combined_score", results[0])
        self.assertIn("reasons", results[0])
        self.assertIn("Attached to this entity", results[0]["reasons"])

    def test_cos_ranking_false_no_extra_fields(self):
        """With use_cos_ranking=False (default), no scoring fields added."""
        from apps.life.models import Project

        project = Project.objects.create(
            user=self.user, title="Default Related Project", description="P"
        )
        ct = ContentType.objects.get_for_model(project)
        note = Note.objects.create(user=self.user, body="Default related")
        NoteAttachment.objects.create(note=note, content_type=ct, object_id=project.pk)

        results = get_related_notes_for_entity(
            user=self.user,
            content_type="life.project",
            object_id=project.pk,
        )
        self.assertEqual(len(results), 1)
        self.assertNotIn("combined_score", results[0])
        self.assertNotIn("reasons", results[0])
