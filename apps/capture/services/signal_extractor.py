# ==============================================================================
# File: apps/capture/services/signal_extractor.py
# Description: Phase 5.5 — Capture signal extraction (LLM + validation)
# Created: 2026-03-16
# ==============================================================================
"""
CaptureSignalExtractor — Extract behavioral signals from capture transcripts.

Architecture:
  1. LLM extracts structured CANDIDATES from transcript text
  2. Deterministic validation layer filters, normalizes, and maps candidates
  3. Valid candidates are stored as CaptureSignal records
  4. CaptureSignal records are later blended into SignalSnapshots

The LLM is ONLY a "structured candidate extractor" — it NEVER assigns
signals, scores, or writes to the signal pipeline. All decisions about
validity, thresholds, signal mapping, and scoring are deterministic.

Supports both positive and negative behavior detection:
  "I went for a run" → health_activity, direction=positive
  "I skipped my workout" → health_activity, direction=negative
"""

import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

# Minimum word count for LLM extraction (transcripts are usually long)
MIN_WORDS_FOR_EXTRACTION = 15

# Confidence threshold — candidates below this are discarded
CONFIDENCE_THRESHOLD = 0.6

# Valid signal types from the Signal Taxonomy (base types only, no patterns)
VALID_SIGNAL_TYPES = {
    'health_activity', 'health_biometrics', 'medication_adherence',
    'nutrition_compliance', 'faith_practice', 'mental_reflection',
    'cognitive_fitness', 'productivity_progress', 'financial_health',
    'relational_engagement',
}

# Canonical domain mapping (deterministic, not LLM-assigned)
SIGNAL_TYPE_DOMAIN = {
    'health_activity': 'health',
    'health_biometrics': 'health',
    'medication_adherence': 'health',
    'nutrition_compliance': 'health',
    'faith_practice': 'faith',
    'mental_reflection': 'journal',
    'cognitive_fitness': 'brain_training',
    'productivity_progress': 'life',
    'financial_health': 'finance',
    'relational_engagement': 'relationships',
}

# Valid extractor types (one per design extractor)
VALID_EXTRACTOR_TYPES = {
    'emotional_tone',
    'relationship',
    'health_behavior',
    'intent_commitment',
    'spiritual_faith',
    'cognitive_learning',
}

# LLM extraction prompt — returns structured candidates ONLY
EXTRACTION_PROMPT = """Analyze this transcript and identify behavioral signals — actions or states the speaker explicitly describes.

For each signal found, return a JSON object with key "signals" containing an array of objects with:
- signal_type: one of [health_activity, health_biometrics, medication_adherence, nutrition_compliance, faith_practice, mental_reflection, cognitive_fitness, productivity_progress, financial_health, relational_engagement]
- extractor_type: one of [emotional_tone, relationship, health_behavior, intent_commitment, spiritual_faith, cognitive_learning]
- confidence: 0.0-1.0 how confident you are this behavior is explicitly described
- extracted_text: the exact phrase from the transcript (max 200 chars)
- direction: "positive" if the behavior occurred/was practiced, "negative" if explicitly skipped/missed/avoided

Rules:
1. Only return signals for behaviors EXPLICITLY described in the text.
2. Include BOTH positive behaviors ("I went running") AND negative behaviors ("I skipped my workout").
3. For negative behaviors, direction MUST be "negative".
4. Only include signals with confidence >= 0.6.
5. The extracted_text must be a direct quote or close paraphrase from the transcript.
6. Do NOT infer behaviors not mentioned.
7. Do NOT assign final scores — only identify what behaviors are described.

Return ONLY valid JSON with a "signals" key — no markdown, no explanation."""


class CaptureSignalExtractor:
    """
    Extract behavioral signal candidates from capture transcripts.

    Two-phase pipeline:
    1. LLM extraction → raw candidates (untrusted)
    2. Deterministic validation → CaptureSignal records (trusted)
    """

    @staticmethod
    def extract_signals(entry):
        """
        Extract and validate behavioral signals from a CaptureEntry.

        Args:
            entry: CaptureEntry instance (must have status='ready')

        Returns:
            List of created CaptureSignal records, or empty list.
        """
        from apps.capture.models import CaptureSignal

        # Gate: skip if already extracted (idempotency)
        if CaptureSignal.objects.filter(entry=entry).exists():
            logger.debug(
                "Capture entry %s already has signals — skipping extraction",
                entry.pk,
            )
            return []

        # Gate: must have transcript
        transcript = getattr(entry, 'transcript', None)
        if not transcript or not transcript.strip():
            return []

        # Combine transcript + summary for richer extraction
        text_parts = [transcript]
        summary = getattr(entry, 'summary', None)
        if summary and summary.strip():
            text_parts.append(summary)
        text = '\n\n'.join(text_parts).strip()

        # Gate: minimum length
        word_count = len(text.split())
        if word_count < MIN_WORDS_FOR_EXTRACTION:
            logger.debug(
                "Capture entry %s has %d words (min %d) — skipping",
                entry.pk, word_count, MIN_WORDS_FOR_EXTRACTION,
            )
            return []

        # Phase 1: LLM extraction (untrusted candidates)
        try:
            raw_candidates = CaptureSignalExtractor._call_openai(text)
        except Exception as e:
            logger.warning(
                "OpenAI extraction failed for capture %s: %s",
                entry.pk, e,
            )
            return []

        # Phase 2: Deterministic validation
        created = []
        for raw in raw_candidates:
            signal = CaptureSignalExtractor._validate_and_create(entry, raw)
            if signal:
                created.append(signal)

        if created:
            logger.info(
                "Extracted %d signals from capture entry %s "
                "(positive=%d, negative=%d)",
                len(created), entry.pk,
                sum(1 for s in created if s.direction == 'positive'),
                sum(1 for s in created if s.direction == 'negative'),
            )

        return created

    @staticmethod
    def _call_openai(text):
        """
        Call OpenAI to extract structured candidates from text.

        Returns list of raw candidate dicts (untrusted — must be validated).
        """
        from apps.ai.services import get_openai_client

        client = get_openai_client()
        if not client:
            logger.warning(
                "OpenAI client not available — skipping capture extraction"
            )
            return []

        model = getattr(settings, 'OPENAI_CAPTURE_EXTRACTION_MODEL', 'gpt-4o-mini')

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": EXTRACTION_PROMPT},
                    {"role": "user", "content": text[:8000]},
                ],
                temperature=0.1,
                max_tokens=1500,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            parsed = json.loads(content)

            if isinstance(parsed, dict):
                return parsed.get('signals', [])
            elif isinstance(parsed, list):
                return parsed
            else:
                logger.warning(
                    "Unexpected response format from OpenAI: %s", type(parsed)
                )
                return []

        except json.JSONDecodeError as e:
            logger.warning("Failed to parse OpenAI response as JSON: %s", e)
            return []

    @staticmethod
    def _validate_and_create(entry, raw_candidate):
        """
        Deterministic validation layer.

        Validates and normalizes a raw LLM candidate, then creates a
        CaptureSignal record. Returns None if validation fails.

        This is where ALL trust decisions are made — the LLM output
        is never trusted directly.
        """
        from apps.capture.models import CaptureSignal

        # --- Extract fields ---
        signal_type = raw_candidate.get('signal_type', '')
        extractor_type = raw_candidate.get('extractor_type', '')
        extracted_text = raw_candidate.get('extracted_text', '')
        direction = raw_candidate.get('direction', 'positive')
        confidence = raw_candidate.get('confidence', 0.0)

        # --- Validate signal_type ---
        if signal_type not in VALID_SIGNAL_TYPES:
            logger.debug("Invalid signal_type '%s' — discarding", signal_type)
            return None

        # --- Validate confidence threshold ---
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            return None

        if confidence < CONFIDENCE_THRESHOLD:
            return None

        # --- Validate extracted_text ---
        if not extracted_text or not extracted_text.strip():
            return None

        # --- Normalize direction ---
        if direction not in ('positive', 'negative'):
            direction = 'positive'

        # --- Normalize extractor_type ---
        if extractor_type not in VALID_EXTRACTOR_TYPES:
            extractor_type = 'health_behavior'  # fallback

        # --- Deterministic domain mapping (NEVER use LLM's domain) ---
        domain = SIGNAL_TYPE_DOMAIN.get(signal_type)
        if not domain:
            return None

        # --- Create validated record ---
        return CaptureSignal.objects.create(
            entry=entry,
            signal_type=signal_type,
            domain=domain,
            confidence=min(1.0, max(0.0, confidence)),
            extracted_text=extracted_text[:500],
            direction=direction,
            extractor_type=extractor_type,
        )
