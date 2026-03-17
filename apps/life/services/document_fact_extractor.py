# ==============================================================================
# File: apps/life/services/document_fact_extractor.py
# Description: Phase 6A — Extract structured facts from document content
# Created: 2026-03-17
# ==============================================================================
"""
DocumentFactExtractor — Extract structured facts from document raw_text.

Pipeline:
  raw_text → LLM extraction → structured candidates → deterministic validation
  → ExtractedFact records → Fact→Signal mapping → targeted recompute

LLM is ONLY a structured candidate extractor. All trust decisions
(validation, normalization, domain mapping, confidence) are deterministic.
"""

import json
import logging
import re
from datetime import date as date_type
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

logger = logging.getLogger(__name__)

# Source weight for document-extracted facts (architecture review: 0.7)
DOCUMENT_SOURCE_WEIGHT = 0.7

# Minimum confidence from LLM to accept
LLM_CONFIDENCE_THRESHOLD = 0.6

# Minimum raw_text length for LLM extraction
MIN_TEXT_LENGTH = 50

# Valid fact types
VALID_FACT_TYPES = {
    'amount', 'appointment', 'person', 'medication',
    'obligation', 'subscription',
}

# Fact type → signal type mapping (deterministic)
FACT_SIGNAL_MAP = {
    'amount': ('financial_health', 'finance'),
    'obligation': ('financial_health', 'finance'),
    'subscription': ('financial_health', 'finance'),
    'appointment': ('health_activity', 'health'),
    'medication': ('medication_adherence', 'health'),
    'person': None,  # Only maps when domain_hint is set
}

# Person domain_hint → signal mapping
PERSON_SIGNAL_MAP = {
    'health': ('health_activity', 'health'),
    'relationships': ('relational_engagement', 'relationships'),
}

# LLM prompt for fact extraction
FACT_EXTRACTION_PROMPT = """Analyze this document text and extract structured facts — concrete, specific pieces of information explicitly stated in the text.

For each fact found, return a JSON object with key "facts" containing an array:
- fact_type: one of [amount, appointment, person, medication, obligation, subscription]
- confidence: 0.0-1.0 how confident you are this fact is explicitly stated
- extracted_text: the exact phrase (max 200 chars)
- structured_value: a JSON object with type-specific fields:
  * amount: {"value": number, "currency": "USD", "merchant": "...", "date": "YYYY-MM-DD"}
  * appointment: {"provider": "...", "datetime": "YYYY-MM-DD", "location": "..."}
  * person: {"name": "...", "role": "...", "context": "..."}
  * medication: {"name": "...", "dosage": "...", "frequency": "..."}
  * obligation: {"description": "...", "amount": number, "due_date": "YYYY-MM-DD", "recurring": false}
  * subscription: {"service": "...", "amount": number, "frequency": "monthly", "next_date": "YYYY-MM-DD"}
- effective_date: "YYYY-MM-DD" or null (when does this fact apply?)
- domain_hint: one of [health, finance, faith, relationships, life] or null

Rules:
1. Only extract facts EXPLICITLY stated in the text.
2. Do NOT infer facts not present.
3. Only include facts with confidence >= 0.6.
4. Dates must be in YYYY-MM-DD format.
5. Amounts must be numbers (no currency symbols in the value field).
6. Return ONLY valid JSON — no markdown, no explanation."""


class DocumentFactExtractor:
    """
    Extract structured facts from document content.

    Pipeline: raw_text → LLM → validation → ExtractedFact records
    """

    @staticmethod
    def extract_facts(document):
        """
        Extract facts from a Document's raw_text.

        Returns list of created ExtractedFact records.
        """
        from apps.core.ai_eae.models import ExtractedFact

        # Gate: must have raw_text
        raw_text = getattr(document, 'raw_text', '') or ''
        if not raw_text.strip() or len(raw_text.strip()) < MIN_TEXT_LENGTH:
            return []

        # Gate: idempotency — skip if facts already extracted for this source
        ct = ContentType.objects.get_for_model(document)
        if ExtractedFact.objects.filter(
            source_content_type=ct,
            source_object_id=document.pk,
        ).exists():
            logger.debug(
                "Document %s already has facts — skipping", document.pk,
            )
            return []

        # Build text for LLM (include metadata for context)
        text_for_llm = _build_llm_text(document, raw_text)

        # LLM extraction
        try:
            raw_candidates = _call_openai(text_for_llm)
        except Exception as e:
            logger.warning(
                "OpenAI fact extraction failed for document %s: %s",
                document.pk, e,
            )
            return []

        # Deterministic validation
        created = []
        for raw in raw_candidates:
            fact = _validate_and_create(document, raw)
            if fact:
                created.append(fact)

        if created:
            logger.info(
                "Extracted %d facts from document %s",
                len(created), document.pk,
            )

        return created


def _build_llm_text(document, raw_text):
    """Build text payload for LLM extraction."""
    parts = []
    if document.title:
        parts.append(f"Document Title: {document.title}")
    if document.category:
        parts.append(f"Category: {document.category}")
    if document.document_date:
        parts.append(f"Document Date: {document.document_date}")
    parts.append(f"\n--- Document Content ---\n{raw_text[:6000]}")
    return '\n'.join(parts)


def _call_openai(text):
    """Call OpenAI for structured fact extraction."""
    from apps.ai.services import get_openai_client

    client = get_openai_client()
    if not client:
        return []

    model = getattr(settings, 'OPENAI_FACT_EXTRACTION_MODEL', 'gpt-4o-mini')

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": FACT_EXTRACTION_PROMPT},
                {"role": "user", "content": text[:8000]},
            ],
            temperature=0.1,
            max_tokens=2000,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        parsed = json.loads(content)

        if isinstance(parsed, dict):
            return parsed.get('facts', [])
        elif isinstance(parsed, list):
            return parsed
        return []

    except json.JSONDecodeError as e:
        logger.warning("Failed to parse fact extraction JSON: %s", e)
        return []


def _validate_and_create(document, raw_candidate):
    """
    Deterministic validation + creation of an ExtractedFact.

    Validates types, normalizes values, applies confidence weighting.
    Returns None if validation fails.
    """
    from apps.core.ai_eae.models import ExtractedFact
    from django.contrib.contenttypes.models import ContentType

    fact_type = raw_candidate.get('fact_type', '')
    extracted_text = raw_candidate.get('extracted_text', '')
    structured_value = raw_candidate.get('structured_value', {})
    effective_date = raw_candidate.get('effective_date')
    domain_hint = raw_candidate.get('domain_hint', '')
    confidence = raw_candidate.get('confidence', 0.0)

    # Validate fact_type
    if fact_type not in VALID_FACT_TYPES:
        logger.debug("Invalid fact_type '%s' — discarding", fact_type)
        return None

    # Validate confidence
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        return None
    if confidence < LLM_CONFIDENCE_THRESHOLD:
        return None

    # Validate extracted_text
    if not extracted_text or not extracted_text.strip():
        return None

    # Validate structured_value
    if not isinstance(structured_value, dict):
        return None

    # Type-specific validation
    validated_value = _validate_structured_value(fact_type, structured_value)
    if validated_value is None:
        return None

    # Parse effective_date
    parsed_date = _parse_date(effective_date)

    # Normalize domain_hint
    valid_domains = {'health', 'finance', 'faith', 'relationships', 'life'}
    if domain_hint not in valid_domains:
        domain_hint = _infer_domain_hint(fact_type)

    # Apply source weight
    final_confidence = min(1.0, max(0.0, confidence * DOCUMENT_SOURCE_WEIGHT))

    ct = ContentType.objects.get_for_model(document)

    return ExtractedFact.objects.create(
        user=document.user,
        source_content_type=ct,
        source_object_id=document.pk,
        source_type='document',
        fact_type=fact_type,
        structured_value=validated_value,
        confidence=round(final_confidence, 3),
        extracted_text=extracted_text[:500],
        effective_date=parsed_date,
        domain_hint=domain_hint,
    )


def _validate_structured_value(fact_type, value):
    """Type-specific validation for structured_value. Returns normalized dict or None."""
    if fact_type == 'amount':
        raw_val = value.get('value')
        if raw_val is None:
            return None
        try:
            amount = float(raw_val)
        except (TypeError, ValueError):
            return None
        return {
            'value': round(amount, 2),
            'currency': value.get('currency', 'USD'),
            'merchant': str(value.get('merchant', ''))[:200],
            'date': str(value.get('date', ''))[:10],
        }

    elif fact_type == 'appointment':
        return {
            'provider': str(value.get('provider', ''))[:200],
            'datetime': str(value.get('datetime', ''))[:20],
            'location': str(value.get('location', ''))[:200],
        }

    elif fact_type == 'person':
        name = value.get('name', '')
        if not name:
            return None
        return {
            'name': str(name)[:200],
            'role': str(value.get('role', ''))[:100],
            'context': str(value.get('context', ''))[:200],
        }

    elif fact_type == 'medication':
        name = value.get('name', '')
        if not name:
            return None
        return {
            'name': str(name)[:200],
            'dosage': str(value.get('dosage', ''))[:100],
            'frequency': str(value.get('frequency', ''))[:100],
        }

    elif fact_type == 'obligation':
        return {
            'description': str(value.get('description', ''))[:300],
            'amount': _safe_float(value.get('amount')),
            'due_date': str(value.get('due_date', ''))[:10],
            'recurring': bool(value.get('recurring', False)),
        }

    elif fact_type == 'subscription':
        return {
            'service': str(value.get('service', ''))[:200],
            'amount': _safe_float(value.get('amount')),
            'frequency': str(value.get('frequency', 'monthly'))[:20],
            'next_date': str(value.get('next_date', ''))[:10],
        }

    return None


def _safe_float(val):
    """Safely convert to float, return None if impossible."""
    if val is None:
        return None
    try:
        return round(float(val), 2)
    except (TypeError, ValueError):
        return None


def _parse_date(date_str):
    """Parse YYYY-MM-DD date string, return None if invalid."""
    if not date_str:
        return None
    try:
        parts = str(date_str)[:10].split('-')
        if len(parts) == 3:
            return date_type(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, TypeError):
        pass
    return None


def _infer_domain_hint(fact_type):
    """Infer domain_hint from fact_type."""
    mapping = {
        'amount': 'finance',
        'obligation': 'finance',
        'subscription': 'finance',
        'appointment': 'health',
        'medication': 'health',
        'person': '',
    }
    return mapping.get(fact_type, '')
