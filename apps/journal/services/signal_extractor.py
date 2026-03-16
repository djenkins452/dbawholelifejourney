# ==============================================================================
# File: apps/journal/services/signal_extractor.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: NLP-based behavioral signal extraction from journal entries
# Created: 2026-03-14 (Architecture Evolution Phase 7)
# ==============================================================================
"""
JournalSignalExtractor — Extract behavioral signals from journal text.

Uses OpenAI to analyze journal entries and identify behavioral signals
that map to the WLJ Signal Taxonomy. Extracted signals are stored as
JournalSignal records and feed inferred_behavior data into the
signal persistence layer.

Safety rules:
- Only extracts signals explicitly described in text
- Does NOT infer behaviors not mentioned
- Minimum confidence threshold: 0.5
- Short entries (<20 words) are skipped to avoid false positives
"""

import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

# Minimum word count for meaningful extraction
MIN_WORDS_FOR_EXTRACTION = 20

# Valid signal types from the Signal Taxonomy
VALID_SIGNAL_TYPES = {
    'health_activity', 'health_biometrics', 'medication_adherence',
    'nutrition_compliance', 'faith_practice', 'mental_reflection',
    'cognitive_fitness', 'productivity_progress', 'financial_health',
    'relational_engagement',
}

SIGNAL_TYPE_DOMAIN = {
    'health_activity': 'health',
    'health_biometrics': 'health',
    'medication_adherence': 'health',
    'nutrition_compliance': 'health',
    'faith_practice': 'faith',
    'mental_reflection': 'mind',
    'cognitive_fitness': 'mind',
    'productivity_progress': 'life',
    'financial_health': 'finance',
    'relational_engagement': 'relationships',
}

EXTRACTION_PROMPT = """Analyze this journal entry and identify any behavioral signals — actions the user explicitly describes having done or experienced.

For each signal found, return a JSON array of objects with:
- signal_type: one of [health_activity, health_biometrics, medication_adherence, nutrition_compliance, faith_practice, mental_reflection, cognitive_fitness, productivity_progress, financial_health, relational_engagement]
- domain: the life domain (health, faith, mind, life, finance, relationships)
- confidence: 0.0-1.0 how confident you are this behavior actually occurred
- extracted_text: the exact phrase from the entry that indicates the behavior

Rules:
1. Only return signals for behaviors EXPLICITLY described. Do NOT infer.
2. Only include signals with confidence >= 0.5.
3. The extracted_text must be a direct quote from the entry.
4. If no behavioral signals are found, return an empty array: []

Return ONLY valid JSON — no markdown, no explanation."""


class JournalSignalExtractor:
    """
    Extract behavioral signals from journal entries using NLP.

    Usage:
        signals = JournalSignalExtractor.extract_signals(entry)
        # Returns list of created JournalSignal records
    """

    @staticmethod
    def extract_signals(entry):
        """
        Extract behavioral signals from a journal entry.

        Args:
            entry: JournalEntry instance

        Returns:
            List of created JournalSignal records, or empty list.
        """
        from apps.journal.models import JournalSignal

        # Gate: skip if entry already has signals (idempotency)
        if JournalSignal.objects.filter(entry=entry).exists():
            logger.debug(
                "Journal entry %s already has signals — skipping extraction",
                entry.pk,
            )
            return []

        # Gate: combine title + body for extraction
        text_parts = []
        if getattr(entry, 'title', None):
            text_parts.append(entry.title)
        if getattr(entry, 'body', None):
            text_parts.append(entry.body)

        text = ' '.join(text_parts).strip()
        if not text:
            return []

        # Gate: skip short entries
        word_count = len(text.split())
        if word_count < MIN_WORDS_FOR_EXTRACTION:
            logger.debug(
                "Journal entry %s has %d words (min %d) — skipping extraction",
                entry.pk, word_count, MIN_WORDS_FOR_EXTRACTION,
            )
            return []

        # Call OpenAI for extraction
        try:
            raw_signals = JournalSignalExtractor._call_openai(text)
        except Exception as e:
            logger.warning(
                "OpenAI signal extraction failed for entry %s: %s",
                entry.pk, e,
            )
            return []

        # Parse and store
        created = []
        for raw in raw_signals:
            signal = JournalSignalExtractor._validate_and_create(entry, raw)
            if signal:
                created.append(signal)

        if created:
            logger.info(
                "Extracted %d signals from journal entry %s",
                len(created), entry.pk,
            )

        return created

    @staticmethod
    def _call_openai(text):
        """
        Call OpenAI API to extract behavioral signals from text.

        Returns parsed list of signal dicts.
        """
        from apps.ai.services import get_openai_client

        client = get_openai_client()
        if not client:
            logger.warning(
                "OpenAI client not available (OPENAI_API_KEY missing?) — "
                "skipping journal signal extraction"
            )
            return []

        model = getattr(settings, 'OPENAI_JOURNAL_EXTRACTION_MODEL', 'gpt-4o-mini')

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": EXTRACTION_PROMPT},
                    {"role": "user", "content": text[:4000]},  # Truncate to avoid token limits
                ],
                temperature=0.1,  # Low temperature for consistent extraction
                max_tokens=1000,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            parsed = json.loads(content)

            # Handle both {"signals": [...]} and [...] formats
            if isinstance(parsed, dict):
                return parsed.get('signals', [])
            elif isinstance(parsed, list):
                return parsed
            else:
                logger.warning("Unexpected response format from OpenAI: %s", type(parsed))
                return []

        except json.JSONDecodeError as e:
            logger.warning("Failed to parse OpenAI response as JSON: %s", e)
            return []

    @staticmethod
    def _validate_and_create(entry, raw_signal):
        """
        Validate a raw signal dict and create a JournalSignal record.

        Returns JournalSignal or None if validation fails.
        """
        from apps.journal.models import JournalSignal

        signal_type = raw_signal.get('signal_type', '')
        confidence = raw_signal.get('confidence', 0.0)
        extracted_text = raw_signal.get('extracted_text', '')

        # Validate signal_type
        if signal_type not in VALID_SIGNAL_TYPES:
            logger.debug(
                "Invalid signal_type '%s' from OpenAI — skipping", signal_type,
            )
            return None

        # Validate confidence threshold
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            return None

        if confidence < 0.5:
            return None

        # Validate extracted_text exists
        if not extracted_text or not extracted_text.strip():
            return None

        # Determine domain
        domain = SIGNAL_TYPE_DOMAIN.get(signal_type, raw_signal.get('domain', ''))
        if not domain:
            return None

        # Create record
        return JournalSignal.objects.create(
            entry=entry,
            signal_type=signal_type,
            domain=domain,
            confidence=min(1.0, max(0.0, confidence)),
            extracted_text=extracted_text[:500],  # Cap at 500 chars
        )
