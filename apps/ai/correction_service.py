# ==============================================================================
# File: correction_service.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Correction persistence for CoS. Detects when users correct
#              the assistant, stores structured corrections, and retrieves
#              them with high priority to prevent recurring mistakes.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-28
# ==============================================================================
"""
CoS Correction Persistence Service

When a user says "that's not right", "no I meant X", or "you misunderstood",
this service:
  1. Detects the correction intent
  2. Stores a structured CorrectionRecord with embedding
  3. Marks the corresponding ConversationMemory as corrected
  4. On future queries, retrieves relevant corrections with higher priority

Public API:
  - detect_correction(user_message) -> bool
  - store_correction(user, user_message, original_response, conversation)
  - retrieve_relevant_corrections(user, query, top_k=3) -> list[dict]
  - get_correction_context_block(user, query) -> str
"""

import logging
import re
from typing import List, Dict, Optional, Any

from django.utils import timezone

logger = logging.getLogger(__name__)

# Patterns that indicate the user is correcting the assistant
CORRECTION_PATTERNS = [
    # Direct negation
    r"(?:^|\b)(?:no|nope)[,.]?\s+(?:i\s+(?:meant|mean|said|was\s+saying|wanted))",
    r"(?:^|\b)(?:that'?s?\s+(?:not\s+(?:right|correct|what\s+i|accurate|true)))",
    r"(?:^|\b)(?:you(?:'re|\s+are)\s+(?:wrong|incorrect|mistaken|off|confused))",
    r"(?:^|\b)(?:you\s+(?:misunderstood|misread|got\s+(?:it|that)\s+wrong))",
    r"(?:^|\b)(?:i\s+didn'?t\s+(?:say|mean|ask)\s+(?:that|this))",
    r"(?:^|\b)(?:actually)[,.]?\s+(?:i|it|what|the)",
    r"(?:^|\b)(?:let\s+me\s+(?:correct|clarify|rephrase))",
    r"(?:^|\b)(?:i\s+(?:need\s+to\s+)?correct\s+(?:you|that|something))",
    r"(?:^|\b)(?:that\s+(?:was|is)n'?t?\s+what\s+(?:i|happened))",
    r"(?:^|\b)(?:not\s+(?:quite|exactly|really))[,.]",
    r"(?:^|\b)(?:wrong)[,.]?\s+(?:i|it|the|what)",
]

# Compiled patterns for efficiency
_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in CORRECTION_PATTERNS]


def detect_correction(user_message: str) -> bool:
    """
    Detect whether a user message is correcting the assistant.

    Uses pattern matching — no AI call needed.

    Args:
        user_message: The user's message text.

    Returns:
        True if the message appears to be a correction.
    """
    if not user_message or len(user_message) < 5:
        return False

    msg = user_message.strip()
    for pattern in _COMPILED_PATTERNS:
        if pattern.search(msg):
            return True

    return False


def store_correction(
    user,
    user_message: str,
    original_response: str,
    conversation=None,
    original_message_id: Optional[int] = None,
) -> Optional[Any]:
    """
    Store a structured correction record.

    Called when detect_correction() returns True.

    Args:
        user: Django User instance.
        user_message: The user's correction message.
        original_response: The assistant response being corrected.
        conversation: Optional AssistantConversation.
        original_message_id: Optional ID of the AssistantMessage being corrected.

    Returns:
        CorrectionRecord instance or None on failure.
    """
    try:
        from .models import CorrectionRecord, AssistantMessage, ConversationMemory

        # Build corrected truth from the user's correction
        corrected_truth = _extract_corrected_truth(user_message)

        # Detect topics
        from .memory_service import _detect_topics, _generate_embedding
        combined = f"{user_message} {original_response[:200]}"
        topic_tags = _detect_topics(combined)

        # Generate embedding for the correction
        embed_text = f"Correction: {user_message}\nOriginal: {original_response[:200]}"
        embedding = _generate_embedding(embed_text) or []

        # Get the original message if we have an ID
        original_msg = None
        if original_message_id:
            try:
                original_msg = AssistantMessage.objects.get(id=original_message_id)
            except AssistantMessage.DoesNotExist:
                pass

        # Create the correction record
        correction = CorrectionRecord.objects.create(
            user=user,
            original_message=original_msg,
            original_response=original_response[:1000],
            user_correction=user_message[:1000],
            corrected_truth=corrected_truth,
            topic_tags=topic_tags,
            embedding=embedding,
            confidence=0.8,
        )

        # Mark the corresponding ConversationMemory as corrected
        _mark_memory_corrected(user, original_response)

        logger.info(
            "Stored correction %d for user %s (topics: %s)",
            correction.pk, user.email, topic_tags
        )
        return correction

    except Exception as e:
        logger.warning("Failed to store correction: %s", e)
        return None


def retrieve_relevant_corrections(
    user,
    query: str,
    top_k: int = 3,
) -> List[Dict[str, Any]]:
    """
    Retrieve the most relevant corrections for a query.

    Uses cosine similarity against correction embeddings.

    Args:
        user: Django User instance.
        query: Current user message.
        top_k: Number of corrections to return.

    Returns:
        List of correction dicts sorted by relevance.
    """
    from .models import CorrectionRecord
    from .memory_service import _generate_embedding, _cosine_similarity

    query_embedding = _generate_embedding(query)
    if not query_embedding:
        return []

    corrections = CorrectionRecord.objects.filter(user=user).order_by('-created_at')[:100]

    scored = []
    for corr in corrections:
        if not corr.embedding:
            continue
        sim = _cosine_similarity(query_embedding, corr.embedding)
        if sim >= 0.30:  # Lower threshold than memories — corrections are important
            scored.append({
                'original_response': corr.original_response,
                'user_correction': corr.user_correction,
                'corrected_truth': corr.corrected_truth,
                'topic_tags': corr.topic_tags,
                'created_at': corr.created_at,
                'confidence': corr.confidence,
                'similarity': round(sim, 3),
            })

    scored.sort(key=lambda x: x['similarity'], reverse=True)
    return scored[:top_k]


def get_correction_context_block(user, query: str) -> str:
    """
    Build the system prompt injection block for relevant corrections.

    Returns empty string if no relevant corrections found.
    """
    corrections = retrieve_relevant_corrections(user, query)
    if not corrections:
        return ""

    lines = []
    for corr in corrections:
        dt = corr['created_at']
        now = timezone.now()
        delta = now - dt

        if delta.days == 0:
            time_label = "Earlier today"
        elif delta.days == 1:
            time_label = "Yesterday"
        elif delta.days < 7:
            time_label = dt.strftime("%A")
        elif delta.days < 30:
            weeks = delta.days // 7
            time_label = f"{weeks} week{'s' if weeks > 1 else ''} ago"
        else:
            time_label = dt.strftime("%B %d")

        truth = corr['corrected_truth'] or corr['user_correction'][:200]
        lines.append(
            f"  [{time_label}] You previously said something incorrect. "
            f"The user corrected you:\n"
            f"  User said: \"{corr['user_correction'][:200]}\"\n"
            f"  Correct information: {truth}"
        )

    block = "\n\n".join(lines)
    return f"""
IMPORTANT CORRECTIONS (the user has corrected you before on these topics — do NOT repeat the same mistakes):
{block}

Always incorporate these corrections into your responses. If the topic comes up again, use the corrected information.
"""


def _extract_corrected_truth(user_message: str) -> str:
    """
    Extract the corrected fact from the user's correction message.

    Simple heuristic: look for the part after correction indicators.
    """
    msg = user_message.strip()

    # Try to find the corrected info after common correction phrases
    after_patterns = [
        r"(?:actually|no)[,.]?\s+(.*)",
        r"(?:i\s+(?:meant|mean|said))\s+(.*)",
        r"(?:it'?s?\s+(?:actually|really))\s+(.*)",
        r"(?:the\s+(?:correct|right)\s+(?:answer|thing)\s+is)\s+(.*)",
        r"(?:what\s+i\s+(?:meant|mean)\s+(?:was|is))\s+(.*)",
    ]

    for pattern in after_patterns:
        match = re.search(pattern, msg, re.IGNORECASE)
        if match:
            truth = match.group(1).strip().rstrip('.!?')
            if len(truth) > 5:
                return truth[:500]

    # Fallback: use the whole message as the correction
    return msg[:500]


def _mark_memory_corrected(user, original_response: str):
    """
    Find and mark the ConversationMemory that matches the corrected response.
    """
    from .models import ConversationMemory

    try:
        # Find the most recent memory whose summary matches
        summary_prefix = original_response[:100]
        recent_memories = ConversationMemory.objects.filter(
            user=user,
        ).order_by('-created_at')[:10]

        for mem in recent_memories:
            if mem.assistant_summary and summary_prefix[:50] in mem.assistant_summary:
                mem.was_corrected = True
                mem.helpfulness_score = max(mem.helpfulness_score - 0.5, -1.0)
                mem.save(update_fields=['was_corrected', 'helpfulness_score'])
                logger.debug("Marked memory %d as corrected", mem.pk)
                return

    except Exception as e:
        logger.debug("Failed to mark memory as corrected: %s", e)
