# ==============================================================================
# File: apps/core/ai_memory/life_fact_extractor.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Extracts and persists biographical life facts from conversations
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-08
# ==============================================================================
"""
Life Fact Extraction Service

Analyzes user messages for meaningful personal life facts (family relationships,
deaths, milestones, health conditions, etc.) and persists them as PersonalFact
records for permanent CoS memory.

Design principles:
- Runs asynchronously in a background thread — never blocks chat response
- Only analyzes the SINGLE most recent user message (not full conversation)
- Uses lightweight regex pre-screening to avoid unnecessary API calls
- AI extraction only fires when regex signals potential life facts
- Deduplicates against existing PersonalFact records before saving
- User consent gates: ai_enabled + ai_data_consent required
- Respects opt-out phrases from personal_context.py
"""

import logging
import re

logger = logging.getLogger(__name__)

# Regex pre-screening patterns — if ANY match, send to AI for extraction.
# These are intentionally broad to catch candidates, not to extract facts.
# The AI call does the actual extraction with precision.
LIFE_FACT_SIGNAL_PATTERNS = [
    # Family / relationship mentions
    r"\b(?:my|our)\s+(?:wife|husband|spouse|partner|mom|mother|dad|father|"
    r"son|daughter|brother|sister|grandmother|grandfather|grandma|grandpa|"
    r"nana|papa|aunt|uncle|cousin|niece|nephew|in-law|step-?\w+|"
    r"wife'?s?\s+(?:mother|father|sister|brother|family)|"
    r"husband'?s?\s+(?:mother|father|sister|brother|family))\b",
    # Death / loss
    r"\b(?:passed\s+away|died|lost\s+(?:my|our|her|his)|funeral|"
    r"memorial|grief|grieving|mourning|in\s+memory\s+of|"
    r"no\s+longer\s+(?:with\s+us|alive|here))\b",
    # Health conditions (lasting, not temporary)
    r"\b(?:diagnosed\s+with|has\s+(?:cancer|diabetes|alzheimer|dementia|"
    r"parkinson|autism|adhd|anxiety|depression|ptsd)|chronic|disability|"
    r"in\s+remission|surgery\s+(?:for|on)|wheelchair|terminal)\b",
    # Life milestones
    r"\b(?:got\s+married|wedding|divorced|separated|"
    r"expecting\s+(?:a\s+)?(?:baby|child)|pregnant|"
    r"born\s+(?:in|on)|adopted|retired|graduated)\b",
    # Significant personal history
    r"\b(?:grew\s+up\s+in|raised\s+(?:in|by)|from\s+(?:originally|"
    r"a\s+small\s+town)|military|served\s+in|veteran)\b",
]

# Compiled pattern for efficiency
LIFE_FACT_SIGNAL_RE = re.compile(
    "|".join(LIFE_FACT_SIGNAL_PATTERNS),
    re.IGNORECASE,
)


def _message_has_life_fact_signals(message: str) -> bool:
    """Quick regex check — does this message potentially contain life facts?"""
    return bool(LIFE_FACT_SIGNAL_RE.search(message))


def extract_life_facts_from_message(user, user_message: str, assistant_response: str = "") -> int:
    """
    Analyze a single user message for personal life facts and persist them.

    This is the main entry point called from post-response intelligence.

    Args:
        user: The User instance
        user_message: The user's message text
        assistant_response: The assistant's response (for context, not analyzed)

    Returns:
        Number of new facts persisted (0 if none found or gated)
    """
    if not user_message or len(user_message) < 15:
        return 0

    # Gate: check user consent
    try:
        prefs = user.preferences
        if not prefs.ai_enabled or not prefs.ai_data_consent:
            return 0
    except Exception:
        return 0

    # Gate: check for opt-out phrases
    from apps.ai.personal_context import contains_opt_out_phrase
    if contains_opt_out_phrase(user_message):
        logger.info("Life fact extraction skipped — opt-out phrase detected")
        return 0

    # Gate: regex pre-screening — avoid API call if no signals
    if not _message_has_life_fact_signals(user_message):
        return 0

    logger.info("Life fact signals detected in message, running AI extraction")

    try:
        return _extract_and_persist(user, user_message, assistant_response)
    except Exception as e:
        logger.error("Life fact extraction failed: %s", e, exc_info=True)
        return 0


def _extract_and_persist(user, user_message: str, assistant_response: str) -> int:
    """Run AI extraction and persist new facts."""
    from apps.ai.services import AIService
    from .models import PersonalFact

    # Load existing facts for deduplication context
    existing_facts = list(
        PersonalFact.objects.filter(user=user, is_active=True)
        .values_list("fact_text", flat=True)
    )
    existing_context = "\n".join(f"- {f}" for f in existing_facts) if existing_facts else "(none)"

    extraction_prompt = f"""Analyze this user message for meaningful personal LIFE FACTS — biographical details that should be permanently remembered.

EXTRACT ONLY facts in these categories:
- family_relationship: family members and their relationships (e.g., "Linda (Nana) is user's wife's mother")
- death: deaths or losses of people important to the user
- health_condition: lasting health conditions (user's or family members')
- life_milestone: marriages, births, graduations, retirements, moves
- life_circumstance: career, living situation, significant background
- personal_value: deeply held values or beliefs stated with conviction
- preference: strong lasting preferences relevant to life context

DO NOT EXTRACT:
- Temporary states (tired today, busy this week)
- Task-related details (I need to do X)
- Opinions about the app or AI
- Anything already known (see existing facts below)
- Vague or uncertain statements

For each fact, output EXACTLY this JSON format (one per line):
{{"fact_type": "category", "subject_name": "person name or empty", "relationship": "relationship to user or empty", "fact_text": "human-readable fact", "confidence": 0.9}}

If NO meaningful life facts are found, output exactly: NO_FACTS

EXISTING FACTS (do not duplicate):
{existing_context}

USER MESSAGE:
{user_message}

ASSISTANT RESPONSE (for context only):
{assistant_response[:500] if assistant_response else "(none)"}

Extract life facts (JSON, one per line):"""

    service = AIService()
    response = service._call_api(
        system_prompt=(
            "You extract personal biographical facts from user messages. "
            "Be precise — only extract facts the user clearly stated. "
            "Never infer, guess, or hallucinate facts. "
            "If unsure, do NOT extract. Accuracy is more important than coverage."
        ),
        user_prompt=extraction_prompt,
        max_tokens=500,
    )

    if not response or "NO_FACTS" in response:
        return 0

    return _parse_and_save_facts(user, response, existing_facts)


def _parse_and_save_facts(user, response: str, existing_facts: list[str]) -> int:
    """Parse AI response and save new PersonalFact records."""
    import json
    from .models import PersonalFact

    saved_count = 0
    existing_lower = {f.lower().strip() for f in existing_facts}

    for line in response.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or "NO_FACTS" in line:
            continue

        try:
            fact_data = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue

        fact_text = fact_data.get("fact_text", "").strip()
        if not fact_text or len(fact_text) < 10:
            continue

        # Deduplication: skip if substantially similar to existing fact
        if fact_text.lower().strip() in existing_lower:
            continue
        if _is_duplicate_fact(fact_text, existing_facts):
            continue

        fact_type = fact_data.get("fact_type", "other")
        valid_types = {c[0] for c in PersonalFact.FACT_TYPE_CHOICES}
        if fact_type not in valid_types:
            fact_type = "other"

        confidence = fact_data.get("confidence", 0.8)
        if not isinstance(confidence, (int, float)):
            confidence = 0.8
        confidence = max(0.0, min(1.0, float(confidence)))

        PersonalFact.objects.create(
            user=user,
            fact_type=fact_type,
            subject_name=fact_data.get("subject_name", "")[:200],
            relationship=fact_data.get("relationship", "")[:100],
            fact_text=fact_text,
            confidence=confidence,
            source="conversation",
        )
        saved_count += 1
        logger.info("Saved personal fact [%s]: %s", fact_type, fact_text[:80])

    return saved_count


def _is_duplicate_fact(new_fact: str, existing_facts: list[str]) -> bool:
    """
    Check if a new fact is substantially similar to any existing fact.
    Uses simple word overlap to catch rephrased duplicates.
    """
    new_words = set(new_fact.lower().split())
    # Remove very common words for comparison
    stop_words = {"the", "a", "an", "is", "was", "are", "were", "has", "have",
                  "had", "to", "of", "and", "in", "for", "on", "with", "my",
                  "your", "their", "his", "her", "our"}
    new_significant = new_words - stop_words

    if len(new_significant) < 2:
        return False

    for existing in existing_facts:
        existing_words = set(existing.lower().split()) - stop_words
        if len(existing_words) < 2:
            continue
        overlap = new_significant & existing_words
        # If 70%+ of significant words overlap, treat as duplicate
        overlap_ratio = len(overlap) / min(len(new_significant), len(existing_words))
        if overlap_ratio >= 0.7:
            return True

    return False


def build_personal_facts_prompt(user) -> str:
    """
    Build the system prompt section for structured personal facts.

    This is injected alongside the existing personal_context prompt
    to give CoS deterministic access to biographical facts.

    Args:
        user: The User instance

    Returns:
        Formatted prompt section, or empty string if no facts
    """
    from .models import PersonalFact

    facts = PersonalFact.objects.filter(user=user, is_active=True)
    if not facts.exists():
        return ""

    # Group facts by type for readable prompt
    grouped = {}
    for fact in facts:
        label = dict(PersonalFact.FACT_TYPE_CHOICES).get(fact.fact_type, fact.fact_type)
        grouped.setdefault(label, []).append(fact.fact_text)

    lines = []
    for category, fact_texts in grouped.items():
        lines.append(f"**{category}:**")
        for text in fact_texts:
            lines.append(f"  - {text}")

    facts_block = "\n".join(lines)

    return f"""
## PERSONAL LIFE FACTS

The following biographical facts have been learned from conversations.
These are permanent, verified facts — not temporary context.

{facts_block}

IMPORTANT: These facts are things the user explicitly shared. Reference them
naturally when relevant. Never question or second-guess these facts.
If a fact involves loss or grief, be appropriately sensitive.
"""
