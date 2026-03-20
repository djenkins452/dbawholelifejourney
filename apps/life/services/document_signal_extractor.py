# ==============================================================================
# File: apps/life/services/document_signal_extractor.py
# Description: Phase 5.5 — Document signal extraction (hybrid rule + LLM)
# Created: 2026-03-16
# ==============================================================================
"""
DocumentSignalExtractor — Extract signals from document metadata.

Two-tier strategy:
  Tier 1 (always): Category-based mapping + keyword detection
  Tier 2 (conditional): LLM extraction when description/notes >= 100 chars

Document signals are the LOWEST confidence tier — verified > journal >
capture > document_llm > document_rule.
"""

import json
import logging
import re

from django.conf import settings

logger = logging.getLogger(__name__)

# Minimum text length for Tier 2 LLM extraction
MIN_TEXT_LENGTH_FOR_LLM = 100

# LLM confidence threshold (same as capture)
LLM_CONFIDENCE_THRESHOLD = 0.6

# Rule-based confidence for category mapping
CATEGORY_RULE_CONFIDENCE = 0.65

# Rule-based confidence for keyword detection
KEYWORD_RULE_CONFIDENCE = 0.55

# Category → signal type mapping (Tier 1)
CATEGORY_SIGNAL_MAP = {
    'medical': ('health_activity', 'health'),
    'insurance': ('health_activity', 'health'),
    'education': ('cognitive_fitness', 'brain_training'),
    'financial': ('financial_health', 'finance'),
    'tax': ('financial_health', 'finance'),
}

# Keyword patterns → (signal_type, domain, extractor_type)
KEYWORD_PATTERNS = [
    # Health keywords
    (re.compile(r'\b(prescription|medication|medicine|rx|dosage|refill)\b', re.I),
     'medication_adherence', 'health', 'keyword_rule'),
    (re.compile(r'\b(diagnosis|lab\s*result|blood\s*work|test\s*result|mri|ct\s*scan|x-?ray)\b', re.I),
     'health_biometrics', 'health', 'keyword_rule'),
    (re.compile(r'\b(appointment|doctor|physician|specialist|checkup|physical)\b', re.I),
     'health_activity', 'health', 'keyword_rule'),
    # Education keywords
    (re.compile(r'\b(certificate|diploma|transcript|degree|course|training|certification)\b', re.I),
     'cognitive_fitness', 'brain_training', 'keyword_rule'),
    # Faith keywords
    (re.compile(r'\b(church|baptism|bible|scripture|sermon|ministry|prayer)\b', re.I),
     'faith_practice', 'faith', 'keyword_rule'),
]

# Valid signal types (same as capture extractor)
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
    'mental_reflection': 'journal',
    'cognitive_fitness': 'brain_training',
    'productivity_progress': 'life',
    'financial_health': 'finance',
    'relational_engagement': 'relationships',
}

# LLM prompt for Tier 2 (same structure as capture, but for short metadata)
DOCUMENT_EXTRACTION_PROMPT = """Analyze this document metadata and identify any behavioral signals — actions or states the user explicitly describes in their notes.

For each signal found, return a JSON object with key "signals" containing an array:
- signal_type: one of [health_activity, health_biometrics, medication_adherence, nutrition_compliance, faith_practice, mental_reflection, cognitive_fitness, productivity_progress, financial_health, relational_engagement]
- extractor_type: "llm"
- confidence: 0.0-1.0
- extracted_text: the exact phrase (max 200 chars)
- direction: "positive" or "negative"

Rules:
1. Only return signals for behaviors EXPLICITLY described.
2. Include both positive and negative behaviors.
3. Do NOT infer from category alone — only from description/notes text content.
4. Only include signals with confidence >= 0.6.
5. Return ONLY valid JSON — no markdown, no explanation."""


class DocumentSignalExtractor:
    """
    Hybrid extraction: Tier 1 (rules) + Tier 2 (conditional LLM).
    """

    @staticmethod
    def extract_signals(document):
        """
        Extract signals from a Document instance.

        Returns list of created DocumentSignal records.
        """
        from apps.life.models import DocumentSignal

        # Gate: idempotency
        if DocumentSignal.objects.filter(document=document).exists():
            logger.debug(
                "Document %s already has signals — skipping", document.pk,
            )
            return []

        created = []

        # Tier 1: Category-based mapping
        tier1 = DocumentSignalExtractor._extract_category_signals(document)
        created.extend(tier1)

        # Tier 1: Keyword detection in title + description + notes
        tier1_kw = DocumentSignalExtractor._extract_keyword_signals(document)
        created.extend(tier1_kw)

        # Tier 2: Conditional LLM extraction
        text = DocumentSignalExtractor._get_text_for_llm(document)
        if text and len(text) >= MIN_TEXT_LENGTH_FOR_LLM:
            tier2 = DocumentSignalExtractor._extract_llm_signals(document, text)
            created.extend(tier2)

        if created:
            logger.info(
                "Extracted %d signals from document %s", len(created), document.pk,
            )

        return created

    @staticmethod
    def _extract_category_signals(document):
        """Tier 1: Map document category to signal type."""
        from apps.life.models import DocumentSignal

        category = getattr(document, 'category', '')
        if not category or category not in CATEGORY_SIGNAL_MAP:
            return []

        signal_type, domain = CATEGORY_SIGNAL_MAP[category]

        signal = DocumentSignal.objects.create(
            document=document,
            signal_type=signal_type,
            domain=domain,
            confidence=CATEGORY_RULE_CONFIDENCE,
            extracted_text=f"Document category: {category}",
            direction='positive',
            extractor_type='category_rule',
        )
        return [signal]

    @staticmethod
    def _extract_keyword_signals(document):
        """Tier 1: Keyword pattern matching on text fields."""
        from apps.life.models import DocumentSignal

        text_parts = []
        for field in ('title', 'description', 'notes'):
            val = getattr(document, field, None)
            if val and val.strip():
                text_parts.append(val)
        text = ' '.join(text_parts)
        if not text.strip():
            return []

        created = []
        seen_types = set()

        for pattern, signal_type, domain, extractor_type in KEYWORD_PATTERNS:
            if signal_type in seen_types:
                continue
            match = pattern.search(text)
            if match:
                seen_types.add(signal_type)
                signal = DocumentSignal.objects.create(
                    document=document,
                    signal_type=signal_type,
                    domain=domain,
                    confidence=KEYWORD_RULE_CONFIDENCE,
                    extracted_text=match.group(0)[:500],
                    direction='positive',
                    extractor_type=extractor_type,
                )
                created.append(signal)

        return created

    @staticmethod
    def _get_text_for_llm(document):
        """Build text payload for Tier 2 LLM extraction."""
        parts = []
        if getattr(document, 'title', ''):
            parts.append(f"Title: {document.title}")
        if getattr(document, 'description', '') and document.description.strip():
            parts.append(f"Description: {document.description}")
        if getattr(document, 'notes', '') and document.notes.strip():
            parts.append(f"Notes: {document.notes}")
        if getattr(document, 'category', ''):
            parts.append(f"Category: {document.category}")
        return '\n'.join(parts)

    @staticmethod
    def _extract_llm_signals(document, text):
        """Tier 2: LLM extraction for documents with enough text."""
        from apps.life.models import DocumentSignal

        try:
            raw_candidates = DocumentSignalExtractor._call_openai(text)
        except Exception as e:
            logger.warning(
                "OpenAI extraction failed for document %s: %s", document.pk, e,
            )
            return []

        created = []
        for raw in raw_candidates:
            signal = DocumentSignalExtractor._validate_and_create(document, raw)
            if signal:
                created.append(signal)
        return created

    @staticmethod
    def _call_openai(text):
        """Call OpenAI for Tier 2 extraction."""
        from apps.ai.services import get_openai_client

        client = get_openai_client()
        if not client:
            return []

        model = getattr(settings, 'OPENAI_DOCUMENT_EXTRACTION_MODEL', settings.OPENAI_MINI_MODEL)

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": DOCUMENT_EXTRACTION_PROMPT},
                    {"role": "user", "content": text[:2000]},
                ],
                temperature=0.1,
                max_tokens=500,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            parsed = json.loads(content)

            if isinstance(parsed, dict):
                return parsed.get('signals', [])
            elif isinstance(parsed, list):
                return parsed
            return []

        except json.JSONDecodeError as e:
            logger.warning("Failed to parse document extraction JSON: %s", e)
            return []

    @staticmethod
    def _validate_and_create(document, raw_candidate):
        """Deterministic validation for LLM candidates."""
        from apps.life.models import DocumentSignal

        signal_type = raw_candidate.get('signal_type', '')
        extracted_text = raw_candidate.get('extracted_text', '')
        direction = raw_candidate.get('direction', 'positive')
        confidence = raw_candidate.get('confidence', 0.0)

        if signal_type not in VALID_SIGNAL_TYPES:
            return None

        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            return None

        if confidence < LLM_CONFIDENCE_THRESHOLD:
            return None

        if not extracted_text or not extracted_text.strip():
            return None

        if direction not in ('positive', 'negative'):
            direction = 'positive'

        domain = SIGNAL_TYPE_DOMAIN.get(signal_type)
        if not domain:
            return None

        return DocumentSignal.objects.create(
            document=document,
            signal_type=signal_type,
            domain=domain,
            confidence=min(1.0, max(0.0, confidence)),
            extracted_text=extracted_text[:500],
            direction=direction,
            extractor_type='llm',
        )
