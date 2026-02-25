# ==============================================================================
# File: memory_service.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: RAG-based long-term memory for CoS. Stores conversation turns
#              with vector embeddings and retrieves semantically similar past
#              exchanges to inject into the system prompt.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-25
# ==============================================================================
"""
CoS Long-Term Memory Service (Phase 3a)

Provides vector-based semantic memory so CoS can reference past conversations:
  - "Last Tuesday you mentioned struggling with consistency in your Quiet Time..."
  - "Remember when you said you wanted to focus more on prayer this month?"

Architecture:
  1. After each assistant response, embed the user message + summary via
     OpenAI text-embedding-3-small (1536 dims, $0.02/1M tokens — very cheap).
  2. Store embedding + metadata in ConversationMemory.
  3. Before each new response, embed the incoming query, retrieve top-K
     similar past exchanges via cosine similarity.
  4. Inject retrieved memories into the system prompt as
     "RELEVANT PAST CONVERSATIONS".

Performance:
  - Embedding call: ~100ms, $0.00002 per exchange
  - Retrieval: cosine similarity over user's last 500 memories in Python
    (~2ms for 500 vectors of 1536 dims). Migrate to pgvector if needed.
  - Only stores exchanges > 20 chars (filters out "yes", "ok", etc.)

Public API:
  - store_memory(user, message, response, conversation, page_context)
  - retrieve_relevant_memories(user, query, top_k=5) -> list[dict]
  - get_memory_context_block(user, query) -> str
"""

import logging
import math
from typing import List, Dict, Optional, Any

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

# Embedding model — cheapest, fast, good enough for semantic similarity
EMBEDDING_MODEL = 'text-embedding-3-small'
EMBEDDING_DIMENSIONS = 1536

# Memory limits
MAX_MEMORIES_PER_USER = 500  # Keep last 500 exchanges
MIN_MESSAGE_LENGTH = 20      # Don't store trivial messages
MAX_RETRIEVE = 5             # Top-K memories to retrieve
SIMILARITY_THRESHOLD = 0.35  # Minimum cosine similarity to include

# Topic detection keywords
TOPIC_KEYWORDS = {
    'faith': ['bible', 'scripture', 'pray', 'prayer', 'god', 'jesus', 'church',
              'faith', 'worship', 'devotion', 'reading plan', 'sabbath', 'sermon',
              'holy', 'spirit', 'psalm', 'verse'],
    'health': ['weight', 'blood pressure', 'heart rate', 'workout', 'exercise',
               'sleep', 'fasting', 'medication', 'medicine', 'calories', 'steps',
               'glucose', 'oxygen', 'bmi', 'diet', 'nutrition', 'pain'],
    'goals': ['goal', 'milestone', 'target', 'deadline', 'progress', 'achieve',
              'accomplish', 'complete'],
    'tasks': ['task', 'todo', 'due', 'overdue', 'pending', 'priority', 'schedule',
              'routine', 'habit'],
    'journal': ['journal', 'entry', 'reflect', 'reflection', 'mood', 'feeling',
                'grateful', 'gratitude', 'write', 'wrote'],
    'relationships': ['wife', 'husband', 'spouse', 'kids', 'children', 'family',
                      'friend', 'mother', 'father', 'sister', 'brother', 'son',
                      'daughter', 'relationship'],
    'finance': ['budget', 'money', 'spend', 'save', 'income', 'expense',
                'financial', 'debt', 'investment'],
}


def _get_openai_client():
    """Get or create OpenAI client."""
    api_key = getattr(settings, 'OPENAI_API_KEY', None)
    if not api_key:
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=api_key, timeout=30)
    except Exception as e:
        logger.warning("Failed to create OpenAI client for embeddings: %s", e)
        return None


def _generate_embedding(text: str) -> Optional[List[float]]:
    """Generate embedding vector for text using OpenAI API.

    Returns list of floats (1536 dimensions) or None on failure.
    """
    client = _get_openai_client()
    if not client:
        return None

    try:
        # Truncate to avoid token limits (8191 tokens max for this model)
        truncated = text[:6000]

        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=truncated,
        )

        # Telemetry (best-effort)
        try:
            usage = getattr(response, 'usage', None)
            if usage:
                from apps.owner_finance.services.telemetry import log_llm_usage
                log_llm_usage(
                    user=None,
                    feature='MEMORY_EMBED',
                    model_name=EMBEDDING_MODEL,
                    input_tokens=getattr(usage, 'total_tokens', 0),
                    output_tokens=0,
                )
        except Exception:
            pass

        return response.data[0].embedding
    except Exception as e:
        logger.warning("Embedding generation failed: %s", e)
        return None


def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0

    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    magnitude_a = math.sqrt(sum(a * a for a in vec_a))
    magnitude_b = math.sqrt(sum(b * b for b in vec_b))

    if magnitude_a == 0 or magnitude_b == 0:
        return 0.0

    return dot_product / (magnitude_a * magnitude_b)


def _detect_topics(text: str) -> List[str]:
    """Detect topic tags from text using keyword matching."""
    text_lower = text.lower()
    topics = []
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            topics.append(topic)
    return topics


def store_memory(
    user,
    user_message: str,
    assistant_response: str,
    conversation=None,
    page_context: Optional[Dict[str, Any]] = None,
) -> Optional[Any]:
    """Store a conversation exchange with its embedding for future retrieval.

    Called after each assistant response. Skips trivial messages.

    Args:
        user: Django User instance
        user_message: The user's message
        assistant_response: The assistant's full response
        conversation: Optional AssistantConversation instance
        page_context: Optional page context dict

    Returns:
        ConversationMemory instance or None if skipped
    """
    # Skip trivial messages
    if not user_message or len(user_message.strip()) < MIN_MESSAGE_LENGTH:
        return None

    # Skip if it looks like a simple confirmation
    trivial = {'yes', 'no', 'ok', 'sure', 'thanks', 'thank you', 'got it',
               'cool', 'yep', 'nope', 'done', 'good', 'great', 'nice'}
    if user_message.strip().lower().rstrip('.!?') in trivial:
        return None

    try:
        from .models import ConversationMemory

        # Build the text to embed: user question + condensed answer
        assistant_summary = assistant_response[:300] if assistant_response else ""
        embed_text = f"User: {user_message}\nAssistant: {assistant_summary}"

        # Generate embedding
        embedding = _generate_embedding(embed_text)
        if not embedding:
            # Still store without embedding for text-based fallback
            embedding = []

        # Detect topics
        combined_text = f"{user_message} {assistant_summary}"
        topic_tags = _detect_topics(combined_text)

        # Extract page context type
        page_context_type = ''
        if page_context:
            pc = page_context.get('page_content')
            if pc:
                page_context_type = pc.get('type', '')

        # Create memory record
        memory = ConversationMemory.objects.create(
            user=user,
            conversation=conversation,
            user_message=user_message[:1000],
            assistant_summary=assistant_summary,
            topic_tags=topic_tags,
            page_context_type=page_context_type,
            embedding=embedding,
        )

        # Prune old memories beyond limit
        _prune_old_memories(user)

        logger.debug(
            "Stored memory %d for user %s (topics: %s, has_embedding: %s)",
            memory.pk, user.email, topic_tags, bool(embedding)
        )
        return memory

    except Exception as e:
        logger.warning("Failed to store conversation memory: %s", e)
        return None


def _prune_old_memories(user):
    """Remove oldest memories beyond MAX_MEMORIES_PER_USER."""
    from .models import ConversationMemory

    count = ConversationMemory.objects.filter(user=user).count()
    if count > MAX_MEMORIES_PER_USER:
        excess = count - MAX_MEMORIES_PER_USER
        oldest_ids = list(
            ConversationMemory.objects.filter(user=user)
            .order_by('created_at')
            .values_list('id', flat=True)[:excess]
        )
        ConversationMemory.objects.filter(id__in=oldest_ids).delete()
        logger.debug("Pruned %d old memories for user %s", excess, user.email)


def retrieve_relevant_memories(
    user,
    query: str,
    top_k: int = MAX_RETRIEVE,
    exclude_minutes: int = 30,
) -> List[Dict[str, Any]]:
    """Retrieve the most semantically similar past conversations.

    Args:
        user: Django User instance
        query: The current user message to find similar memories for
        top_k: Number of memories to return
        exclude_minutes: Exclude memories from the last N minutes (avoid
                        echoing what was just said)

    Returns:
        List of dicts with keys: user_message, assistant_summary, topic_tags,
        created_at, similarity
    """
    from .models import ConversationMemory

    # Generate query embedding
    query_embedding = _generate_embedding(query)
    if not query_embedding:
        return []

    # Get user's memories (exclude very recent to avoid echo)
    cutoff = timezone.now() - timezone.timedelta(minutes=exclude_minutes)
    memories = ConversationMemory.objects.filter(
        user=user,
        created_at__lt=cutoff,
    ).exclude(
        embedding=[],
    ).order_by('-created_at')[:MAX_MEMORIES_PER_USER]

    # Compute similarities
    scored = []
    for mem in memories:
        if not mem.embedding:
            continue
        sim = _cosine_similarity(query_embedding, mem.embedding)
        if sim >= SIMILARITY_THRESHOLD:
            scored.append({
                'user_message': mem.user_message,
                'assistant_summary': mem.assistant_summary,
                'topic_tags': mem.topic_tags,
                'page_context_type': mem.page_context_type,
                'created_at': mem.created_at,
                'similarity': round(sim, 3),
            })

    # Sort by similarity descending, take top_k
    scored.sort(key=lambda x: x['similarity'], reverse=True)
    return scored[:top_k]


def get_memory_context_block(user, query: str) -> str:
    """Build the system prompt injection block for relevant past conversations.

    Returns empty string if no relevant memories found.

    Args:
        user: Django User instance
        query: Current user message

    Returns:
        Formatted string for system prompt injection
    """
    memories = retrieve_relevant_memories(user, query)
    if not memories:
        return ""

    lines = []
    for mem in memories:
        # Format the date naturally
        dt = mem['created_at']
        now = timezone.now()
        delta = now - dt

        if delta.days == 0:
            time_label = "Earlier today"
        elif delta.days == 1:
            time_label = "Yesterday"
        elif delta.days < 7:
            time_label = dt.strftime("%A")  # "Tuesday"
        elif delta.days < 30:
            weeks = delta.days // 7
            time_label = f"{weeks} week{'s' if weeks > 1 else ''} ago"
        else:
            time_label = dt.strftime("%B %d")  # "February 15"

        topics = ', '.join(mem['topic_tags']) if mem['topic_tags'] else 'general'
        lines.append(
            f"  [{time_label} | {topics}]\n"
            f"  User: {mem['user_message'][:200]}\n"
            f"  You said: {mem['assistant_summary'][:200]}"
        )

    block = "\n\n".join(lines)
    return f"""
RELEVANT PAST CONVERSATIONS (retrieved from memory — reference naturally when relevant):
{block}

Use these memories to provide continuity. Say things like "You mentioned last week..." or "When we talked about this before..." — but only when genuinely relevant. Do NOT force references to old conversations.
"""
