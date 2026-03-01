"""
Tests for Semantic Memory Layer.

Tests cover:
- Embedding text generation (deterministic)
- Cosine similarity correctness
- Signal-triggered embedding updates (mocked OpenAI)
- Hybrid scoring integration (semantic_score in score_note)
- semantic_similarity_map service function
- Backfill command
- Embedding integrity detection and repair
- Failure safety (embedding errors never crash Note save/search)
"""

import math
from io import StringIO
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.notes.embeddings import (
    build_note_embedding_text,
    cosine_similarity,
    generate_embedding,
    update_note_embedding,
)
from apps.notes.memory_scoring import score_note
from apps.notes.models import Note, NoteAttachment
from apps.notes.services import (
    find_notes_missing_embeddings,
    repair_missing_embeddings,
    search_notes_cos,
    semantic_similarity_map,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Helper: generate a fake embedding vector
# ---------------------------------------------------------------------------
def _fake_embedding(dim=1536, seed=1.0):
    """Generate a deterministic fake embedding vector."""
    vec = [math.sin(i * seed) for i in range(dim)]
    # Normalize
    mag = math.sqrt(sum(x * x for x in vec))
    return [x / mag for x in vec] if mag > 0 else vec


def _mock_openai_response(embedding_vector):
    """Create a mock OpenAI embedding response."""
    mock_data = MagicMock()
    mock_data.embedding = embedding_vector
    mock_response = MagicMock()
    mock_response.data = [mock_data]
    return mock_response


# ===========================================================================
# Unit tests for embeddings.py
# ===========================================================================


class BuildNoteEmbeddingTextTest(TestCase):
    """Tests for build_note_embedding_text determinism."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="embed_text@example.com", password="testpass123"
        )

    def test_basic_text_format(self):
        """Output includes Title, Body, Tags, Attachments sections."""
        note = Note.objects.create(
            user=self.user, title="Test Title", body="Test body content"
        )
        text = build_note_embedding_text(note)
        self.assertIn("Title: Test Title", text)
        self.assertIn("Body:\nTest body content", text)
        self.assertIn("Tags:", text)
        self.assertIn("Attachments:", text)

    def test_deterministic_output(self):
        """Same note state produces identical text."""
        note = Note.objects.create(
            user=self.user, title="Deterministic", body="Same output"
        )
        text1 = build_note_embedding_text(note)
        text2 = build_note_embedding_text(note)
        self.assertEqual(text1, text2)

    def test_empty_fields(self):
        """Handles blank title and empty tags/attachments gracefully."""
        note = Note.objects.create(user=self.user, body="Just body")
        text = build_note_embedding_text(note)
        self.assertIn("Title: \n", text)
        self.assertIn("Body:\nJust body", text)

    def test_includes_tags_text(self):
        """Tags text is included in embedding text."""
        note = Note.objects.create(user=self.user, body="Tagged note")
        Note.objects.filter(pk=note.pk).update(tags_text="work urgent")
        note.refresh_from_db()
        text = build_note_embedding_text(note)
        self.assertIn("Tags:\nwork urgent", text)


class CosineSimiIarityTest(TestCase):
    """Tests for cosine_similarity correctness."""

    def test_identical_vectors(self):
        """Identical vectors return 1.0."""
        vec = [1.0, 2.0, 3.0]
        self.assertAlmostEqual(cosine_similarity(vec, vec), 1.0, places=5)

    def test_orthogonal_vectors(self):
        """Orthogonal vectors return 0.0."""
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [0.0, 1.0, 0.0]
        self.assertAlmostEqual(cosine_similarity(vec1, vec2), 0.0)

    def test_similar_vectors(self):
        """Similar vectors return high score."""
        vec1 = [1.0, 2.0, 3.0]
        vec2 = [1.1, 2.1, 3.1]
        score = cosine_similarity(vec1, vec2)
        self.assertGreater(score, 0.99)

    def test_none_input(self):
        """None input returns 0.0."""
        self.assertAlmostEqual(cosine_similarity(None, [1.0]), 0.0)
        self.assertAlmostEqual(cosine_similarity([1.0], None), 0.0)

    def test_empty_vectors(self):
        """Empty vectors return 0.0."""
        self.assertAlmostEqual(cosine_similarity([], []), 0.0)

    def test_mismatched_lengths(self):
        """Mismatched vector lengths return 0.0."""
        self.assertAlmostEqual(cosine_similarity([1.0, 2.0], [1.0]), 0.0)

    def test_zero_vector(self):
        """Zero vector returns 0.0."""
        self.assertAlmostEqual(cosine_similarity([0.0, 0.0], [1.0, 2.0]), 0.0)

    def test_negative_clamped_to_zero(self):
        """Opposing vectors return 0.0 (clamped from negative)."""
        vec1 = [1.0, 0.0]
        vec2 = [-1.0, 0.0]
        self.assertAlmostEqual(cosine_similarity(vec1, vec2), 0.0)


class GenerateEmbeddingTest(TestCase):
    """Tests for generate_embedding function."""

    def test_empty_text_returns_none(self):
        """Empty/whitespace text returns None without calling API."""
        self.assertIsNone(generate_embedding(""))
        self.assertIsNone(generate_embedding("   "))

    @patch("apps.notes.embeddings.settings")
    def test_no_api_key_returns_none(self, mock_settings):
        """Missing API key returns None."""
        mock_settings.OPENAI_API_KEY = None
        self.assertIsNone(generate_embedding("test text"))

    @patch("openai.OpenAI")
    @patch("apps.notes.embeddings.settings")
    def test_successful_generation(self, mock_settings, mock_openai_class):
        """Successful API call returns embedding vector."""
        mock_settings.OPENAI_API_KEY = "test-key"
        fake_vec = _fake_embedding()
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = _mock_openai_response(fake_vec)
        mock_openai_class.return_value = mock_client

        result = generate_embedding("test text")
        self.assertEqual(result, fake_vec)
        mock_client.embeddings.create.assert_called_once()

    @patch("openai.OpenAI")
    @patch("apps.notes.embeddings.settings")
    def test_api_error_returns_none(self, mock_settings, mock_openai_class):
        """API error returns None without crashing."""
        mock_settings.OPENAI_API_KEY = "test-key"
        mock_client = MagicMock()
        mock_client.embeddings.create.side_effect = Exception("API timeout")
        mock_openai_class.return_value = mock_client

        result = generate_embedding("test text")
        self.assertIsNone(result)


class UpdateNoteEmbeddingTest(TestCase):
    """Tests for update_note_embedding function."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="update_embed@example.com", password="testpass123"
        )

    @patch("apps.notes.embeddings.generate_embedding")
    def test_updates_embedding_and_timestamp(self, mock_gen):
        """Successful embedding update saves vector and timestamp."""
        fake_vec = _fake_embedding()
        mock_gen.return_value = fake_vec

        note = Note.objects.create(user=self.user, body="Embed me")
        result = update_note_embedding(note)

        self.assertTrue(result)
        note.refresh_from_db()
        self.assertEqual(note.embedding, fake_vec)
        self.assertIsNotNone(note.embedding_updated_at)

    @patch("apps.notes.embeddings.generate_embedding")
    def test_failure_returns_false(self, mock_gen):
        """Failed embedding generation returns False."""
        mock_gen.return_value = None

        note = Note.objects.create(user=self.user, body="Fail embed")
        result = update_note_embedding(note)

        self.assertFalse(result)
        note.refresh_from_db()
        self.assertIsNone(note.embedding)

    def test_no_pk_returns_false(self):
        """Note without pk returns False."""
        note = Note(user=self.user, body="No pk")
        result = update_note_embedding(note)
        self.assertFalse(result)


# ===========================================================================
# Signal-driven embedding lifecycle tests
# ===========================================================================


class EmbeddingSignalTest(TestCase):
    """Tests for signal-triggered embedding updates."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="embed_signal@example.com", password="testpass123"
        )

    @patch("apps.notes.embeddings.generate_embedding")
    def test_note_create_triggers_embedding(self, mock_gen):
        """Creating a new note triggers embedding generation."""
        fake_vec = _fake_embedding()
        mock_gen.return_value = fake_vec

        note = Note.objects.create(user=self.user, body="Signal create test")

        mock_gen.assert_called()
        note.refresh_from_db()
        self.assertEqual(note.embedding, fake_vec)

    @patch("apps.notes.embeddings.generate_embedding")
    def test_note_body_change_triggers_embedding(self, mock_gen):
        """Changing note body triggers new embedding generation."""
        fake_vec = _fake_embedding(seed=2.0)
        mock_gen.return_value = fake_vec

        note = Note.objects.create(user=self.user, body="Original body")
        mock_gen.reset_mock()

        note.body = "Updated body content"
        note.save()

        mock_gen.assert_called()

    @patch("apps.notes.embeddings.generate_embedding")
    def test_embedding_failure_does_not_crash_save(self, mock_gen):
        """Embedding API failure does not prevent note save."""
        mock_gen.side_effect = Exception("API down")

        # Should not raise
        note = Note.objects.create(user=self.user, body="Save must work")
        self.assertIsNotNone(note.pk)
        note.refresh_from_db()
        self.assertEqual(note.body, "Save must work")


# ===========================================================================
# Hybrid scoring tests
# ===========================================================================


class HybridScoringTest(TestCase):
    """Tests for semantic_score integration in score_note."""

    def test_semantic_score_increases_combined(self):
        """Adding semantic_score increases combined_score."""
        base_args = dict(
            fts_rank=0.5,
            max_fts_rank=1.0,
            updated_at=timezone.now(),
            is_pinned=False,
            note_attachment_entity_ids=set(),
            scoped_content_type_id=None,
            scoped_object_id=None,
            note_tag_names=[],
            query_tags=[],
        )

        without_semantic = score_note(**base_args, semantic_score=0.0)
        with_semantic = score_note(**base_args, semantic_score=0.8)

        self.assertGreater(
            with_semantic["combined_score"],
            without_semantic["combined_score"],
        )

    def test_semantic_match_reason(self):
        """High semantic score adds 'Semantic match' reason."""
        result = score_note(
            fts_rank=0.5,
            max_fts_rank=1.0,
            updated_at=timezone.now(),
            is_pinned=False,
            note_attachment_entity_ids=set(),
            scoped_content_type_id=None,
            scoped_object_id=None,
            note_tag_names=[],
            query_tags=[],
            semantic_score=0.8,
        )
        self.assertIn("Semantic match", result["reasons"])

    def test_no_semantic_no_reason(self):
        """Zero semantic score does not add semantic reason."""
        result = score_note(
            fts_rank=0.5,
            max_fts_rank=1.0,
            updated_at=timezone.now(),
            is_pinned=False,
            note_attachment_entity_ids=set(),
            scoped_content_type_id=None,
            scoped_object_id=None,
            note_tag_names=[],
            query_tags=[],
            semantic_score=0.0,
        )
        self.assertNotIn("Semantic match", result["reasons"])

    def test_high_fts_still_beats_pinned_irrelevant(self):
        """The scoring invariant holds with new weights: relevant > pinned irrelevant."""
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
            semantic_score=0.8,
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
            semantic_score=0.0,
        )
        self.assertGreater(
            relevant["combined_score"],
            pinned_irrelevant["combined_score"],
        )


# ===========================================================================
# semantic_similarity_map tests
# ===========================================================================


class SemanticSimilarityMapTest(TestCase):
    """Tests for semantic_similarity_map service function."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="sim_map@example.com", password="testpass123"
        )

    def test_returns_scores_for_notes_with_embeddings(self):
        """Notes with embeddings get similarity scores."""
        vec1 = _fake_embedding(seed=1.0)
        vec2 = _fake_embedding(seed=1.1)
        query_vec = _fake_embedding(seed=1.0)

        note1 = Note.objects.create(user=self.user, body="Note one")
        note2 = Note.objects.create(user=self.user, body="Note two")
        Note.objects.filter(pk=note1.pk).update(embedding=vec1)
        Note.objects.filter(pk=note2.pk).update(embedding=vec2)
        note1.refresh_from_db()
        note2.refresh_from_db()

        scores = semantic_similarity_map(query_vec, [note1, note2])
        self.assertIn(note1.pk, scores)
        self.assertIn(note2.pk, scores)
        # note1 should be more similar (same seed)
        self.assertGreater(scores[note1.pk], scores[note2.pk])

    def test_skips_notes_without_embeddings(self):
        """Notes without embeddings are omitted from results."""
        query_vec = _fake_embedding(seed=1.0)

        note = Note.objects.create(user=self.user, body="No embedding")
        scores = semantic_similarity_map(query_vec, [note])
        self.assertEqual(scores, {})

    def test_none_query_embedding_returns_empty(self):
        """None query embedding returns empty dict."""
        note = Note.objects.create(user=self.user, body="Some note")
        scores = semantic_similarity_map(None, [note])
        self.assertEqual(scores, {})


# ===========================================================================
# search_notes_cos hybrid integration tests
# ===========================================================================


class SearchNotesCoSSemanticTest(TestCase):
    """Tests for semantic scoring in search_notes_cos."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="cos_semantic@example.com", password="testpass123"
        )

    @patch("apps.notes.embeddings.generate_embedding")
    def test_search_with_embeddings(self, mock_gen):
        """Search integrates semantic scoring when embeddings available."""
        fake_vec = _fake_embedding(seed=1.0)
        mock_gen.return_value = fake_vec

        Note.objects.create(
            user=self.user, body="semantic search integration test content"
        )

        result = search_notes_cos(self.user, "semantic search integration")
        self.assertIn("results", result)

    @patch("apps.notes.embeddings.generate_embedding")
    def test_search_works_without_embeddings(self, mock_gen):
        """Search works correctly even when embedding generation fails."""
        mock_gen.return_value = None

        Note.objects.create(
            user=self.user, body="no embedding search test content"
        )

        result = search_notes_cos(self.user, "no embedding search")
        self.assertIn("results", result)

    @patch("apps.notes.embeddings.generate_embedding")
    def test_query_embedding_generated_once(self, mock_gen):
        """Query embedding is generated exactly once per search."""
        mock_gen.return_value = _fake_embedding()

        Note.objects.create(user=self.user, body="once test query content")
        Note.objects.create(user=self.user, body="once test query second note")

        # Reset call count after note creation (signals call it)
        initial_calls = mock_gen.call_count
        search_notes_cos(self.user, "once test query")
        # Only ONE additional call for the query embedding
        search_calls = mock_gen.call_count - initial_calls
        self.assertEqual(search_calls, 1)


# ===========================================================================
# Backfill command tests
# ===========================================================================


class BackfillEmbeddingsCommandTest(TestCase):
    """Tests for backfill_note_embeddings management command."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="backfill_cmd@example.com", password="testpass123"
        )

    @patch("apps.notes.embeddings.generate_embedding")
    def test_backfill_all(self, mock_gen):
        """Backfill processes all notes."""
        mock_gen.return_value = _fake_embedding()

        Note.objects.create(user=self.user, body="Backfill one")
        Note.objects.create(user=self.user, body="Backfill two")

        out = StringIO()
        call_command("backfill_note_embeddings", stdout=out)
        output = out.getvalue()
        self.assertIn("Backfill complete", output)
        self.assertIn("Succeeded: 2", output)

    @patch("apps.notes.embeddings.generate_embedding")
    def test_backfill_missing_only(self, mock_gen):
        """--missing-only only processes notes without embeddings."""
        mock_gen.return_value = _fake_embedding()

        note1 = Note.objects.create(user=self.user, body="Has embedding")
        # note1 got embedding via signal+mock; verify it's set
        note1.refresh_from_db()
        self.assertIsNotNone(note1.embedding)

        note2 = Note.objects.create(user=self.user, body="Missing embedding")
        # Manually clear note2's embedding to simulate missing state
        Note.objects.filter(pk=note2.pk).update(embedding=None, embedding_updated_at=None)

        out = StringIO()
        call_command("backfill_note_embeddings", missing_only=True, stdout=out)
        output = out.getvalue()
        self.assertIn("Succeeded: 1", output)

    @patch("apps.notes.embeddings.generate_embedding")
    def test_backfill_with_limit(self, mock_gen):
        """--limit restricts number of notes processed."""
        mock_gen.return_value = _fake_embedding()

        for i in range(5):
            Note.objects.create(user=self.user, body=f"Limit note {i}")

        out = StringIO()
        call_command("backfill_note_embeddings", limit=2, stdout=out)
        output = out.getvalue()
        self.assertIn("Processed: 2", output)

    @patch("apps.notes.embeddings.generate_embedding")
    def test_backfill_handles_failures(self, mock_gen):
        """Backfill handles embedding failures gracefully."""
        mock_gen.return_value = None  # All fail

        Note.objects.create(user=self.user, body="Fail backfill")

        out = StringIO()
        call_command("backfill_note_embeddings", stdout=out)
        output = out.getvalue()
        self.assertIn("Failed: 1", output)

    def test_backfill_no_notes(self):
        """Backfill with no notes shows success message."""
        out = StringIO()
        call_command("backfill_note_embeddings", stdout=out)
        self.assertIn("No notes to process", out.getvalue())


# ===========================================================================
# Embedding integrity tests
# ===========================================================================


class EmbeddingIntegrityTest(TestCase):
    """Tests for find_notes_missing_embeddings and repair_missing_embeddings."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="embed_integrity@example.com", password="testpass123"
        )

    def test_find_missing_embeddings(self):
        """Detects notes without embeddings."""
        note = Note.objects.create(user=self.user, body="No embedding here")
        # Clear embedding
        Note.objects.filter(pk=note.pk).update(embedding=None)

        missing = find_notes_missing_embeddings()
        self.assertEqual(missing.count(), 1)
        self.assertEqual(missing.first().pk, note.pk)

    def test_notes_with_embeddings_not_flagged(self):
        """Notes with embeddings are not flagged as missing."""
        note = Note.objects.create(user=self.user, body="Has embedding")
        Note.objects.filter(pk=note.pk).update(embedding=_fake_embedding())

        missing = find_notes_missing_embeddings()
        self.assertEqual(missing.count(), 0)

    @patch("apps.notes.embeddings.generate_embedding")
    def test_repair_missing_embeddings(self, mock_gen):
        """repair_missing_embeddings generates embeddings for notes missing them."""
        mock_gen.return_value = _fake_embedding()

        note = Note.objects.create(user=self.user, body="Repair embed note")
        # Clear embedding set by signal
        Note.objects.filter(pk=note.pk).update(embedding=None)

        result = repair_missing_embeddings()
        self.assertEqual(result["notes_processed"], 1)
        self.assertEqual(result["notes_succeeded"], 1)

        note.refresh_from_db()
        self.assertIsNotNone(note.embedding)

    @patch("apps.notes.embeddings.generate_embedding")
    def test_repair_idempotent(self, mock_gen):
        """Repair on clean data returns zero processed."""
        mock_gen.return_value = _fake_embedding()

        Note.objects.create(user=self.user, body="Already has embedding")
        # Signal already set embedding (mocked)

        result = repair_missing_embeddings()
        self.assertEqual(result["notes_processed"], 0)


# ===========================================================================
# Failure safety tests
# ===========================================================================


class FailureSafetyTest(TestCase):
    """Tests that embedding failures never break core functionality."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="fail_safe@example.com", password="testpass123"
        )

    @patch("apps.notes.embeddings.generate_embedding", side_effect=Exception("API crash"))
    def test_note_creation_survives_embedding_crash(self, mock_gen):
        """Note creation succeeds even if embedding crashes."""
        note = Note.objects.create(user=self.user, body="Must survive")
        self.assertIsNotNone(note.pk)

    @patch("apps.notes.embeddings.generate_embedding", side_effect=Exception("API crash"))
    def test_note_edit_survives_embedding_crash(self, mock_gen):
        """Note editing succeeds even if embedding crashes."""
        # Reset mock for create
        mock_gen.side_effect = None
        mock_gen.return_value = None
        note = Note.objects.create(user=self.user, body="Edit me")

        mock_gen.side_effect = Exception("API crash")
        note.body = "Edited body"
        note.save()  # Must not crash

        note.refresh_from_db()
        self.assertEqual(note.body, "Edited body")

    @patch("apps.notes.embeddings.generate_embedding", return_value=None)
    def test_search_survives_embedding_failure(self, mock_gen):
        """search_notes_cos works when embedding generation fails."""
        Note.objects.create(
            user=self.user, body="search failure safety test content"
        )
        result = search_notes_cos(self.user, "search failure safety")
        self.assertIn("results", result)
