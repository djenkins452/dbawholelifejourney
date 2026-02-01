# ==============================================================================
# File: apps/ai/personal_context.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Service for extracting and managing AI personal context from conversations
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-20
# ==============================================================================
"""
Personal Context Extraction Service

This module handles:
1. Extracting personal facts from AI conversations
2. Detecting opt-out phrases when user doesn't want something saved
3. Merging new facts with existing context
4. Providing context for AI system prompts

The personal context helps the AI assistant respond more empathetically
by understanding the user's personal circumstances (family situation,
background, challenges, etc.) without the user having to repeat themselves.

Key Principles:
- User is always in control - they can view, edit, delete their context
- Never lie or change truth - context is for sensitivity, not sugar-coating
- When user says "give it to me straight" - AI gives unfiltered truth
- Context is used to avoid insensitivity, not to withhold information

Privacy:
- Context is encrypted at rest
- User can see exactly what's stored
- User can delete any or all facts
- Opt-out phrases are honored immediately
"""

import logging
import re


logger = logging.getLogger(__name__)

# Phrases that indicate user doesn't want something saved
OPT_OUT_PHRASES = [
    r"don'?t save that",
    r"don'?t remember (that|this)",
    r"forget (what I said|that|this)",
    r"keep (that|this) private",
    r"don'?t store (that|this)",
    r"don'?t record (that|this)",
    r"please don'?t save",
    r"actually,? don'?t save",
    r"actually,? forget",
    r"off the record",
    r"between us",
    r"just between you and me",
]

# Compiled regex for efficiency
OPT_OUT_PATTERN = re.compile(
    '|'.join(OPT_OUT_PHRASES),
    re.IGNORECASE
)


def contains_opt_out_phrase(text: str) -> bool:
    """
    Check if text contains phrases indicating user doesn't want info saved.

    Args:
        text: The message text to check

    Returns:
        True if opt-out phrase detected
    """
    return bool(OPT_OUT_PATTERN.search(text))


def extract_personal_context_from_conversation(
    messages: list[dict],
    existing_context: str = ''
) -> tuple[str, list[str]]:
    """
    Extract personal facts from a conversation using AI.

    This analyzes the conversation and extracts meaningful personal facts
    that would help the AI respond more empathetically in the future.

    Args:
        messages: List of message dicts with 'role' and 'content' keys
        existing_context: Current personal context (to avoid duplicates)

    Returns:
        Tuple of (new_context_to_add, list_of_extracted_facts)
        Returns empty strings/lists if nothing to extract
    """
    from .services import AIService

    if not messages:
        return '', []

    # Build conversation text, filtering out opt-out content
    conversation_parts = []
    skip_until_next_message = False

    for msg in messages:
        role = msg.get('role', 'user')
        content = msg.get('content', '')

        if role == 'user':
            # Check for opt-out phrases
            if contains_opt_out_phrase(content):
                skip_until_next_message = True
                logger.info("Opt-out phrase detected, skipping content for extraction")
                continue

            skip_until_next_message = False
            conversation_parts.append(f"User: {content}")
        elif role == 'assistant' and not skip_until_next_message:
            conversation_parts.append(f"Assistant: {content}")

    if not conversation_parts:
        return '', []

    conversation_text = "\n".join(conversation_parts)

    # Build the extraction prompt
    extraction_prompt = f"""Analyze this conversation and extract any personal facts about the user that would help an AI assistant understand them better and respond more empathetically in the future.

Focus on:
- Family situation (married, single, children, parents, siblings)
- Life circumstances (job, health conditions, challenges)
- Important experiences (loss, achievements, struggles)
- Preferences and values
- Background information they shared

DO NOT extract:
- Temporary states (feeling tired today)
- Opinions about the AI
- Task-related details
- Anything that seems like a one-time mention

IMPORTANT: Write facts in a warm, human-readable format as if describing a friend.
- Good: "Your parents divorced when you were young"
- Bad: "family_status: divorced"

If the user mentioned something sensitive, include it but note it's sensitive.
If there are no meaningful personal facts to extract, respond with: NO_FACTS_FOUND

Current known context (avoid duplicates):
{existing_context if existing_context else "(No existing context)"}

Conversation to analyze:
{conversation_text}

Extract personal facts (one per line, human-readable):"""

    try:
        # Use AIService for extraction
        service = AIService()
        system_prompt = "You are an AI assistant that extracts personal facts from conversations. Be concise and focus only on meaningful, lasting personal details."
        response = service._call_api(
            system_prompt=system_prompt,
            user_prompt=extraction_prompt,
            max_tokens=500
        )

        if not response:
            return '', []

        # Parse the response
        response_text = response.strip()

        if 'NO_FACTS_FOUND' in response_text:
            return '', []

        # Split into individual facts
        facts = [
            line.strip().lstrip('- ').lstrip('* ')
            for line in response_text.split('\n')
            if line.strip() and not line.strip().startswith('#')
        ]

        # Filter out empty and duplicate facts
        facts = [f for f in facts if f and len(f) > 10]  # Minimum length to avoid junk

        if not facts:
            return '', []

        # Join facts with newlines
        new_context = '\n'.join(facts)

        logger.info(f"Extracted {len(facts)} personal facts from conversation")
        return new_context, facts

    except Exception as e:
        logger.error(f"Personal context extraction failed: {e}", exc_info=True)
        return '', []


def merge_personal_context(existing: str, new: str) -> str:
    """
    Merge new personal context with existing context.

    Avoids duplicates and keeps the context clean and readable.

    Args:
        existing: Current personal context
        new: New facts to add

    Returns:
        Merged context string
    """
    if not new:
        return existing

    if not existing:
        return new

    # Parse existing facts
    existing_facts = set(
        line.strip().lower()
        for line in existing.split('\n')
        if line.strip()
    )

    # Add new facts that aren't duplicates (case-insensitive check)
    new_facts = []
    for line in new.split('\n'):
        line = line.strip()
        if line and line.lower() not in existing_facts:
            new_facts.append(line)

    if not new_facts:
        return existing

    # Combine
    return existing + '\n' + '\n'.join(new_facts)


def remove_fact_from_context(context: str, fact_to_remove: str) -> str:
    """
    Remove a specific fact from the personal context.

    Used when user explicitly asks to remove something.

    Args:
        context: Current personal context
        fact_to_remove: The fact text to remove

    Returns:
        Updated context with fact removed
    """
    if not context or not fact_to_remove:
        return context

    # Filter out the matching fact (case-insensitive)
    fact_lower = fact_to_remove.lower().strip()
    remaining_facts = [
        line for line in context.split('\n')
        if line.strip() and line.strip().lower() != fact_lower
    ]

    return '\n'.join(remaining_facts)


def update_user_personal_context(user, conversation_messages: list[dict]) -> bool:
    """
    Extract personal context from a conversation and update the user's profile.

    This is the main entry point called before conversation clear/delete.

    Args:
        user: The User instance
        conversation_messages: List of message dicts from the conversation

    Returns:
        True if context was updated, False otherwise
    """
    try:
        prefs = user.preferences

        # Check if AI is enabled and user has consented
        if not prefs.ai_enabled or not prefs.ai_data_consent:
            logger.debug("AI not enabled or no consent, skipping context extraction")
            return False

        # Get existing context
        existing_context = prefs.ai_personal_context or ''

        # Extract new facts
        new_context, facts = extract_personal_context_from_conversation(
            conversation_messages,
            existing_context
        )

        if not new_context:
            return False

        # Merge and save
        merged_context = merge_personal_context(existing_context, new_context)
        prefs.ai_personal_context = merged_context
        prefs.save(update_fields=['_ai_personal_context', 'updated_at'])

        logger.info(f"Updated personal context for user {user.id} with {len(facts)} new facts")
        return True

    except Exception as e:
        logger.error(f"Failed to update personal context for user {user.id}: {e}", exc_info=True)
        return False


def build_personal_context_prompt(context: str) -> str:
    """
    Build the system prompt section for personal context.

    This is injected into the AI system prompt to make responses more empathetic.

    Args:
        context: The user's personal context string

    Returns:
        Formatted prompt section
    """
    if not context:
        return ''

    return f"""
## WHAT YOU KNOW ABOUT THIS USER

The following personal facts have been learned from previous conversations.
Use this context to respond more empathetically and avoid insensitivity.
NEVER bring these up unprompted - only use them to inform your responses.
If the user asks for hard truths or honesty, give it to them straight regardless.

{context}

Remember: This context is for sensitivity, not sugar-coating. Be helpful and honest.
"""
