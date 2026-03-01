"""
Semantic embedding service for Notes.

Generates, stores, and compares embeddings for Notes using OpenAI's
text-embedding-3-small model. All functions are failure-safe — embedding
errors never crash Note save or search operations.

Used by:
- signals.py (automatic lifecycle updates on Note content changes)
- backfill_note_embeddings command (batch backfill)
- services.py (semantic similarity scoring in search_notes_cos)
"""

import logging
import math

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"


def build_note_embedding_text(note):
    """
    Create deterministic text representation of a Note for embedding.

    Uses all indexed fields to produce a consistent text block.
    Always returns the same output for the same Note state.

    Returns:
        str: Formatted text for embedding generation.
    """
    title = note.title or ""
    body = note.body or ""
    tags_text = note.tags_text or ""
    attachments_text = note.attachments_text or ""

    return (
        f"Title: {title}\n"
        f"Body:\n{body}\n"
        f"Tags:\n{tags_text}\n"
        f"Attachments:\n{attachments_text}"
    )


def generate_embedding(text):
    """
    Generate an embedding vector using OpenAI's text-embedding-3-small.

    Args:
        text: The text to embed.

    Returns:
        list[float] on success, None on any failure.
        Never raises — all errors are logged and return None.
    """
    if not text or not text.strip():
        return None

    api_key = getattr(settings, "OPENAI_API_KEY", None)
    if not api_key:
        logger.warning("OPENAI_API_KEY not configured — skipping embedding generation")
        return None

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, timeout=30)
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text[:8000],  # Truncate to stay within token limits
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error("Failed to generate embedding: %s", e)
        return None


def update_note_embedding(note):
    """
    Generate and save embedding for a Note.

    Workflow:
    1. Build embedding text from note fields
    2. Call OpenAI to generate embedding
    3. Save embedding + timestamp via queryset update (no recursion)

    Args:
        note: Note instance (must be saved / have a pk).

    Returns:
        bool: True if embedding was updated, False on failure.
    """
    if not note.pk:
        return False

    try:
        text = build_note_embedding_text(note)
        embedding = generate_embedding(text)
        if embedding is None:
            return False

        # Use queryset update to avoid triggering save() signals
        from .models import Note

        Note.objects.filter(pk=note.pk).update(
            embedding=embedding,
            embedding_updated_at=timezone.now(),
        )
        return True
    except Exception as e:
        logger.error("Failed to update embedding for Note %s: %s", note.pk, e)
        return False


def cosine_similarity(vec1, vec2):
    """
    Compute cosine similarity between two vectors.

    Returns a normalized score between 0 and 1.
    Handles safely: None values, mismatched sizes, empty vectors.

    Args:
        vec1: First embedding vector (list of floats or None).
        vec2: Second embedding vector (list of floats or None).

    Returns:
        float: Similarity score in [0, 1]. Returns 0 if invalid.
    """
    if not vec1 or not vec2:
        return 0.0

    if len(vec1) != len(vec2):
        return 0.0

    try:
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude_a = math.sqrt(sum(a * a for a in vec1))
        magnitude_b = math.sqrt(sum(b * b for b in vec2))

        if magnitude_a == 0 or magnitude_b == 0:
            return 0.0

        similarity = dot_product / (magnitude_a * magnitude_b)
        # Clamp to [0, 1] — cosine similarity can be negative for opposing vectors
        return max(0.0, min(1.0, similarity))
    except (TypeError, ValueError):
        return 0.0
