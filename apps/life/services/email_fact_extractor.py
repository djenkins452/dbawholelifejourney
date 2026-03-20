# ==============================================================================
# File: apps/life/services/email_fact_extractor.py
# Description: Phase 6B — Extract structured facts from email content
# Created: 2026-03-17
# ==============================================================================
"""
EmailFactExtractor — Extract structured facts from email content.

Pipeline:
  email → rule extraction → LLM extraction (if rules found nothing)
  → deterministic validation → ExtractedFact records

Reuses Phase 6A validation logic from DocumentFactExtractor.
"""

import json
import logging
import re
from datetime import date as date_type

from django.conf import settings
from django.contrib.contenttypes.models import ContentType

logger = logging.getLogger(__name__)

# Source weight for email-extracted facts
EMAIL_SOURCE_WEIGHT = 0.7
EMAIL_WLJ_SOURCE_WEIGHT = 0.9

# Minimum confidence from LLM to accept
LLM_CONFIDENCE_THRESHOLD = 0.6

# Valid fact types (same as Phase 6A)
VALID_FACT_TYPES = {
    'amount', 'appointment', 'person', 'medication',
    'obligation', 'subscription',
}

# Reuse the same LLM prompt from Phase 6A DocumentFactExtractor
FACT_EXTRACTION_PROMPT = """Analyze this email and extract structured facts — concrete, specific pieces of information explicitly stated in the text.

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

# --- Rule-based extraction patterns ---

# Amount: $XX.XX with optional merchant context
_AMOUNT_RE = re.compile(
    r'(?:(?P<merchant>[\w\s&\'-]{2,30})\s+)?'
    r'\$(?P<amount>\d{1,8}(?:\.\d{1,2})?)',
    re.IGNORECASE,
)

# Appointment: date-like patterns near appointment keywords
_APPOINTMENT_RE = re.compile(
    r'(?:appointment|visit|scheduled)\s+(?:on|for|at)\s+'
    r'(?P<date_text>[A-Z][a-z]+\s+\d{1,2}(?:,?\s+\d{4})?'
    r'|\d{1,2}/\d{1,2}/\d{2,4}'
    r'|\d{4}-\d{2}-\d{2})',
    re.IGNORECASE,
)

# Medication: prescription/refill patterns
_MEDICATION_RE = re.compile(
    r'(?:prescription|medication|refill)\s+'
    r'(?:for\s+|ready\s*:?\s*)?'
    r'(?P<name>[A-Z][a-zA-Z\s]{2,40})',
    re.IGNORECASE,
)

# Obligation: bill/payment due patterns
_OBLIGATION_RE = re.compile(
    r'(?:bill|payment|balance)\s+(?:of\s+)?\$(?P<amount>\d{1,8}(?:\.\d{1,2})?)'
    r'(?:\s+(?:due|by)\s+(?P<date_text>[A-Z][a-z]+\s+\d{1,2}(?:,?\s+\d{4})?'
    r'|\d{1,2}/\d{1,2}/\d{2,4}))?',
    re.IGNORECASE,
)

# Subscription: recurring charge patterns
_SUBSCRIPTION_RE = re.compile(
    r'(?P<service>[\w\s&\'-]{2,30})\s+'
    r'(?:subscription|membership|renewal)\s+'
    r'(?:.*?\$(?P<amount>\d{1,8}(?:\.\d{1,2})?))?',
    re.IGNORECASE,
)


class EmailFactExtractor:
    """
    Extract structured facts from email content.

    Uses rules first, LLM for complex emails. Reuses Phase 6A validation.
    """

    @staticmethod
    def extract_facts(user, email_dict, processed_email, wlj_flagged=False):
        """
        Extract facts from an email.

        Args:
            user: User instance
            email_dict: dict from GmailService (subject, sender, body, etc.)
            processed_email: ProcessedEmail record (for GenericFK source)
            wlj_flagged: if True, use higher source weight

        Returns:
            list of created ExtractedFact records
        """
        from apps.core.ai_eae.models import ExtractedFact

        # Idempotency: skip if already extracted for this source
        ct = ContentType.objects.get_for_model(processed_email)
        if ExtractedFact.objects.filter(
            source_content_type=ct,
            source_object_id=processed_email.pk,
        ).exists():
            logger.debug(
                "Email %s already has facts — skipping",
                processed_email.gmail_message_id,
            )
            return []

        body = email_dict.get('body', '') or ''
        subject = email_dict.get('subject', '') or ''
        text = f"{subject}\n{body}"

        if len(text.strip()) < 20:
            return []

        source_weight = (
            EMAIL_WLJ_SOURCE_WEIGHT if wlj_flagged else EMAIL_SOURCE_WEIGHT
        )

        # Step 1: Try rule-based extraction
        rule_candidates = _extract_rules(email_dict)

        if rule_candidates:
            created = []
            for candidate in rule_candidates:
                fact = _validate_and_create(
                    user, processed_email, candidate, source_weight,
                )
                if fact:
                    created.append(fact)
            if created:
                logger.info(
                    "Rule-extracted %d facts from email %s",
                    len(created), processed_email.gmail_message_id,
                )
                return created

        # Step 2: LLM extraction (rules found nothing)
        try:
            llm_candidates = _call_openai(email_dict)
        except Exception as e:
            logger.warning(
                "OpenAI fact extraction failed for email %s: %s",
                processed_email.gmail_message_id, e,
            )
            return []

        created = []
        for candidate in llm_candidates:
            fact = _validate_and_create(
                user, processed_email, candidate, source_weight,
            )
            if fact:
                created.append(fact)

        if created:
            logger.info(
                "LLM-extracted %d facts from email %s",
                len(created), processed_email.gmail_message_id,
            )

        return created


def _extract_rules(email_dict):
    """
    Rule-based fact extraction from email content.

    Returns list of candidate dicts (same format as LLM output).
    """
    subject = email_dict.get('subject', '') or ''
    body = email_dict.get('body', '') or ''
    sender = email_dict.get('sender', '') or ''
    text = f"{subject}\n{body[:2000]}"

    candidates = []

    # Amount extraction
    for match in _AMOUNT_RE.finditer(text):
        amount_str = match.group('amount')
        merchant = (match.group('merchant') or '').strip()
        try:
            amount = float(amount_str)
        except (TypeError, ValueError):
            continue
        if amount < 0.01 or amount > 100000:
            continue
        candidates.append({
            'fact_type': 'amount',
            'confidence': 0.85,
            'extracted_text': match.group(0)[:200],
            'structured_value': {
                'value': round(amount, 2),
                'currency': 'USD',
                'merchant': merchant[:200] or sender.split('@')[0],
            },
            'effective_date': None,
            'domain_hint': 'finance',
        })

    # Appointment extraction
    for match in _APPOINTMENT_RE.finditer(text):
        date_text = match.group('date_text')
        candidates.append({
            'fact_type': 'appointment',
            'confidence': 0.80,
            'extracted_text': match.group(0)[:200],
            'structured_value': {
                'provider': '',
                'datetime': date_text[:20],
                'location': '',
            },
            'effective_date': None,
            'domain_hint': 'health',
        })

    # Medication extraction
    for match in _MEDICATION_RE.finditer(text):
        name = match.group('name').strip()
        if len(name) < 3:
            continue
        candidates.append({
            'fact_type': 'medication',
            'confidence': 0.80,
            'extracted_text': match.group(0)[:200],
            'structured_value': {
                'name': name[:200],
                'dosage': '',
                'frequency': '',
            },
            'effective_date': None,
            'domain_hint': 'health',
        })

    # Obligation extraction
    for match in _OBLIGATION_RE.finditer(text):
        amount_str = match.group('amount')
        try:
            amount = float(amount_str)
        except (TypeError, ValueError):
            continue
        candidates.append({
            'fact_type': 'obligation',
            'confidence': 0.85,
            'extracted_text': match.group(0)[:200],
            'structured_value': {
                'description': subject[:300],
                'amount': round(amount, 2),
                'due_date': (match.group('date_text') or '')[:10],
                'recurring': False,
            },
            'effective_date': None,
            'domain_hint': 'finance',
        })

    # Subscription extraction
    for match in _SUBSCRIPTION_RE.finditer(text):
        service = match.group('service').strip()
        amount_str = match.group('amount') or ''
        amount = None
        if amount_str:
            try:
                amount = round(float(amount_str), 2)
            except (TypeError, ValueError):
                pass
        candidates.append({
            'fact_type': 'subscription',
            'confidence': 0.75,
            'extracted_text': match.group(0)[:200],
            'structured_value': {
                'service': service[:200],
                'amount': amount,
                'frequency': 'monthly',
                'next_date': '',
            },
            'effective_date': None,
            'domain_hint': 'finance',
        })

    return candidates


def _call_openai(email_dict):
    """Call OpenAI for structured fact extraction from email."""
    from apps.ai.services import get_openai_client

    client = get_openai_client()
    if not client:
        return []

    subject = email_dict.get('subject', '') or ''
    sender = email_dict.get('sender', '') or ''
    date = email_dict.get('date', '') or ''
    body = (email_dict.get('body', '') or '')[:4000]

    user_prompt = (
        f"Email Subject: {subject}\n"
        f"From: {sender}\n"
        f"Date: {date}\n"
        f"\n--- Email Content ---\n{body}"
    )

    model = getattr(settings, 'OPENAI_FACT_EXTRACTION_MODEL', settings.OPENAI_MINI_MODEL)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": FACT_EXTRACTION_PROMPT},
                {"role": "user", "content": user_prompt[:8000]},
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
        logger.warning("Failed to parse email fact extraction JSON: %s", e)
        return []


def _validate_and_create(user, processed_email, raw_candidate, source_weight):
    """
    Deterministic validation + creation of ExtractedFact from email.

    Reuses the same validation logic as Phase 6A DocumentFactExtractor.
    """
    from apps.core.ai_eae.models import ExtractedFact
    from apps.life.services.document_fact_extractor import (
        _parse_date,
        _validate_structured_value,
    )

    fact_type = raw_candidate.get('fact_type', '')
    extracted_text = raw_candidate.get('extracted_text', '')
    structured_value = raw_candidate.get('structured_value', {})
    effective_date = raw_candidate.get('effective_date')
    domain_hint = raw_candidate.get('domain_hint', '')
    confidence = raw_candidate.get('confidence', 0.0)

    # Validate fact_type
    if fact_type not in VALID_FACT_TYPES:
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

    # Type-specific validation (reuse Phase 6A)
    validated_value = _validate_structured_value(fact_type, structured_value)
    if validated_value is None:
        return None

    # Parse effective_date
    parsed_date = _parse_date(effective_date)

    # Normalize domain_hint
    valid_domains = {'health', 'finance', 'faith', 'relationships', 'life'}
    if domain_hint not in valid_domains:
        from apps.life.services.document_fact_extractor import _infer_domain_hint
        domain_hint = _infer_domain_hint(fact_type)

    # Apply source weight
    final_confidence = min(1.0, max(0.0, confidence * source_weight))

    ct = ContentType.objects.get_for_model(processed_email)

    return ExtractedFact.objects.create(
        user=user,
        source_content_type=ct,
        source_object_id=processed_email.pk,
        source_type='email',
        fact_type=fact_type,
        structured_value=validated_value,
        confidence=round(final_confidence, 3),
        extracted_text=extracted_text[:500],
        effective_date=parsed_date,
        domain_hint=domain_hint,
    )
