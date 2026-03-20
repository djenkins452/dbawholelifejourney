# ==============================================================================
# File: apps/life/services/email_classifier.py
# Description: Phase 6B — Email classification (rules-first, LLM fallback)
# Created: 2026-03-17
# ==============================================================================
"""
EmailClassifier — Classify emails as KEEP / SKIP / UNCERTAIN.

Pipeline:
  Email → Rule-based classifier → KEEP / SKIP / UNCERTAIN
                                              ↓
                                   LLM classifier → KEEP / SKIP

Rules first. LLM only for UNCERTAIN emails. Minimizes API calls.
"""

import json
import logging
import re

from django.conf import settings

logger = logging.getLogger(__name__)

# Source weight constants for confidence scoring
WLJ_FLAGGED_CONFIDENCE = 1.0
RULE_KEEP_BASE_CONFIDENCE = 0.85
RULE_SKIP_BASE_CONFIDENCE = 0.90
LLM_CLASSIFICATION_THRESHOLD = 0.6

# --- Auto-SKIP sender patterns ---
SKIP_SENDER_PATTERNS = [
    r'noreply@',
    r'no-reply@',
    r'donotreply@',
    r'marketing@',
    r'newsletter@',
    r'notifications?@',
    r'updates?@',
    r'promo(tions)?@',
    r'info@.*\.substack\.com',
    r'digest@',
    r'mailer-daemon@',
    r'postmaster@',
]
_SKIP_SENDER_RE = re.compile(
    '|'.join(SKIP_SENDER_PATTERNS), re.IGNORECASE,
)

# --- Auto-SKIP subject patterns ---
SKIP_SUBJECT_PATTERNS = [
    r'unsubscribe',
    r'weekly digest',
    r'daily summary',
    r'newsletter',
    r'your weekly update',
    r'social media',
    r'new follower',
    r'liked your',
    r'commented on your',
    r'shared a post',
    r'invitation to connect',
]
_SKIP_SUBJECT_RE = re.compile(
    '|'.join(SKIP_SUBJECT_PATTERNS), re.IGNORECASE,
)

# --- Auto-KEEP patterns (financial) ---
FINANCIAL_PATTERNS = [
    r'\$\d+\.?\d{0,2}',           # Dollar amounts
    r'payment\s+(of|due|received)',
    r'invoice\s+#?\d',
    r'receipt\s+(for|from)',
    r'bill\s+(of|due|from)',
    r'statement\s+(for|from)',
    r'transaction\s+(alert|notification)',
    r'refund\s+(of|for|issued)',
]
_FINANCIAL_RE = re.compile(
    '|'.join(FINANCIAL_PATTERNS), re.IGNORECASE,
)

# --- Auto-KEEP patterns (health) ---
HEALTH_PATTERNS = [
    r'appointment\s+(on|for|scheduled|confirmed|reminder)',
    r'prescription\s+(ready|refill|is)',
    r'lab\s+results?',
    r'test\s+results?',
    r'your\s+visit\s+(on|with|to)',
    r'medication\s+(reminder|refill|ready)',
    r'doctor\s+appointment',
    r'medical\s+(record|bill|statement)',
]
_HEALTH_RE = re.compile(
    '|'.join(HEALTH_PATTERNS), re.IGNORECASE,
)

# --- Auto-KEEP patterns (subscription/obligation) ---
SUBSCRIPTION_PATTERNS = [
    r'subscription\s+(renewal|renew|charged|billing)',
    r'recurring\s+(payment|charge|billing)',
    r'auto-?(pay|payment|renew)',
    r'next\s+billing\s+date',
    r'membership\s+(renewal|expired|expiring)',
    r'due\s+date\s*:?\s*\d',
    r'payment\s+due',
]
_SUBSCRIPTION_RE = re.compile(
    '|'.join(SUBSCRIPTION_PATTERNS), re.IGNORECASE,
)

# WLJ flag detection
_WLJ_FLAG_RE = re.compile(r'\[WLJ\]', re.IGNORECASE)

# LLM classification prompt (cheap, ~200 tokens output)
CLASSIFICATION_PROMPT = """Classify this email for a personal life management system.

KEEP — contains personal financial, health, appointment, medication, subscription,
       bill/obligation, or life-planning information worth tracking.
SKIP — newsletter, marketing, social notification, automated system email,
       promotional, FYI-only with no trackable facts.

Return ONLY valid JSON:
{"classification": "KEEP" or "SKIP", "reason": "brief reason", "confidence": 0.0-1.0}"""


def _check_learned_sender(user, sender):
    """
    Check if this sender has a learned classification override.

    Args:
        user: User instance (or None for anonymous/dry-run)
        sender: email sender string

    Returns:
        dict with classification result, or None if no override
    """
    if not user or not sender:
        return None

    try:
        from apps.life.models import EmailClassificationFeedback

        normalized = sender.lower().strip()
        # Extract email address from "Name <email>" format
        if '<' in normalized and '>' in normalized:
            normalized = normalized.split('<')[1].split('>')[0]

        feedback = EmailClassificationFeedback.objects.filter(
            user=user,
            sender=normalized,
        ).first()

        if feedback:
            return {
                'classification': feedback.corrected_classification,
                'confidence': 0.95,
                'reason': f'learned:{feedback.corrected_classification}_sender',
                'method': 'learned',
                'wlj_flagged': False,
            }
    except Exception as e:
        logger.debug("Learning override check failed: %s", e)

    return None


def classify_email(email, user=None):
    """
    Classify a single email as KEEP, SKIP, or UNCERTAIN.

    Args:
        email: dict with keys: id, subject, sender, body, snippet, date
        user: optional User instance for learning overrides

    Returns:
        dict with: classification, confidence, reason, method
    """
    subject = email.get('subject', '') or ''
    sender = email.get('sender', '') or ''
    body = email.get('body', '') or ''
    text = f"{subject} {body[:1000]}"

    # 0. Learning overrides — check before rules
    learned = _check_learned_sender(user, sender)
    if learned:
        return learned

    # 1. WLJ flag — highest priority, always KEEP
    if _WLJ_FLAG_RE.search(subject):
        return {
            'classification': 'keep',
            'confidence': WLJ_FLAGGED_CONFIDENCE,
            'reason': 'rule:wlj_flagged',
            'method': 'rule',
            'wlj_flagged': True,
        }

    # 2. Auto-SKIP: sender patterns
    if _SKIP_SENDER_RE.search(sender):
        return {
            'classification': 'skip',
            'confidence': RULE_SKIP_BASE_CONFIDENCE,
            'reason': 'rule:skip_sender',
            'method': 'rule',
            'wlj_flagged': False,
        }

    # 3. Auto-SKIP: subject patterns
    if _SKIP_SUBJECT_RE.search(subject):
        return {
            'classification': 'skip',
            'confidence': RULE_SKIP_BASE_CONFIDENCE,
            'reason': 'rule:skip_subject',
            'method': 'rule',
            'wlj_flagged': False,
        }

    # 4. Auto-SKIP: empty/trivial body
    body_text = body.strip()
    if len(body_text) < 20:
        return {
            'classification': 'skip',
            'confidence': RULE_SKIP_BASE_CONFIDENCE,
            'reason': 'rule:empty_body',
            'method': 'rule',
            'wlj_flagged': False,
        }

    # 5. Auto-KEEP: financial patterns
    if _FINANCIAL_RE.search(text):
        return {
            'classification': 'keep',
            'confidence': RULE_KEEP_BASE_CONFIDENCE,
            'reason': 'rule:financial_pattern',
            'method': 'rule',
            'wlj_flagged': False,
        }

    # 6. Auto-KEEP: health patterns
    if _HEALTH_RE.search(text):
        return {
            'classification': 'keep',
            'confidence': RULE_KEEP_BASE_CONFIDENCE,
            'reason': 'rule:health_pattern',
            'method': 'rule',
            'wlj_flagged': False,
        }

    # 7. Auto-KEEP: subscription/obligation patterns
    if _SUBSCRIPTION_RE.search(text):
        return {
            'classification': 'keep',
            'confidence': 0.80,
            'reason': 'rule:subscription_pattern',
            'method': 'rule',
            'wlj_flagged': False,
        }

    # 8. UNCERTAIN — needs LLM classification
    return {
        'classification': 'uncertain',
        'confidence': 0.0,
        'reason': 'no_rule_match',
        'method': 'pending_llm',
        'wlj_flagged': False,
    }


def classify_with_llm(email):
    """
    LLM classification for UNCERTAIN emails.

    Args:
        email: dict with keys: id, subject, sender, body

    Returns:
        dict with: classification (keep/skip), confidence, reason, method
    """
    subject = email.get('subject', '') or ''
    sender = email.get('sender', '') or ''
    body = (email.get('body', '') or '')[:500]

    user_prompt = (
        f"Subject: {subject}\n"
        f"From: {sender}\n"
        f"Content: {body}"
    )

    try:
        from apps.ai.services import get_openai_client

        client = get_openai_client()
        if not client:
            return {
                'classification': 'skip',
                'confidence': 0.5,
                'reason': 'llm:unavailable_default_skip',
                'method': 'llm_fallback',
                'wlj_flagged': False,
            }

        response = client.chat.completions.create(
            model=settings.OPENAI_MINI_MODEL,
            messages=[
                {"role": "system", "content": CLASSIFICATION_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=150,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        parsed = json.loads(content)

        classification = parsed.get('classification', 'SKIP').lower()
        if classification not in ('keep', 'skip'):
            classification = 'skip'

        confidence = min(1.0, max(0.0, float(parsed.get('confidence', 0.5))))
        reason = f"llm:{parsed.get('reason', 'unspecified')}"

        return {
            'classification': classification,
            'confidence': confidence,
            'reason': reason[:200],
            'method': 'llm',
            'wlj_flagged': False,
        }

    except json.JSONDecodeError as e:
        logger.warning("LLM classification JSON parse failed: %s", e)
        return {
            'classification': 'skip',
            'confidence': 0.5,
            'reason': 'llm:parse_error',
            'method': 'llm_fallback',
            'wlj_flagged': False,
        }
    except Exception as e:
        logger.warning("LLM classification failed: %s", e)
        return {
            'classification': 'skip',
            'confidence': 0.5,
            'reason': f'llm:error_{type(e).__name__}',
            'method': 'llm_fallback',
            'wlj_flagged': False,
        }


def classify_emails_dry_run(user):
    """
    Dry run: classify all fetchable emails without any DB writes.

    Args:
        user: Django User instance with Gmail connected

    Returns:
        dict with: total_scanned, keep, skip, uncertain, stats
    """
    from apps.life.models import GmailCredential
    from apps.life.services.gmail import GmailService

    try:
        credential = user.gmail_credential
    except GmailCredential.DoesNotExist:
        return {'error': 'not_connected', 'total_scanned': 0}

    if not credential.scan_enabled:
        return {'error': 'disabled', 'total_scanned': 0}

    try:
        gmail_service = GmailService()
    except (ImportError, ValueError) as e:
        return {'error': f'service_unavailable: {e}', 'total_scanned': 0}

    # Refresh token if needed
    if credential.is_token_expired:
        new_creds = gmail_service.refresh_credentials(
            credential.get_credentials_dict()
        )
        if new_creds:
            credential.update_from_credentials(new_creds)
        else:
            return {'error': 'token_expired', 'total_scanned': 0}

    # Fetch emails
    try:
        emails = gmail_service.get_primary_inbox_emails(
            credential.get_credentials_dict(),
            max_results=credential.max_emails_per_scan,
            days_back=credential.days_to_look_back,
        )
    except Exception as e:
        return {'error': f'fetch_failed: {e}', 'total_scanned': 0}

    if not emails:
        return {'total_scanned': 0, 'keep': [], 'skip': {}, 'uncertain': []}

    keep_list = []
    skip_groups = {}
    uncertain_list = []
    llm_calls = 0
    rule_only = 0

    for email in emails:
        result = classify_email(email, user=user)

        if result['classification'] == 'keep':
            rule_only += 1
            keep_list.append({
                'gmail_id': email.get('id', ''),
                'subject': email.get('subject', '')[:100],
                'sender': email.get('sender', ''),
                'date': str(email.get('date', '')),
                'classification': 'KEEP',
                'confidence': result['confidence'],
                'reason': result['reason'],
            })

        elif result['classification'] == 'skip':
            rule_only += 1
            reason = result['reason']
            skip_groups[reason] = skip_groups.get(reason, 0) + 1

        elif result['classification'] == 'uncertain':
            # Run LLM classification
            llm_result = classify_with_llm(email)
            llm_calls += 1

            if llm_result['classification'] == 'keep':
                keep_list.append({
                    'gmail_id': email.get('id', ''),
                    'subject': email.get('subject', '')[:100],
                    'sender': email.get('sender', ''),
                    'date': str(email.get('date', '')),
                    'classification': 'KEEP',
                    'confidence': llm_result['confidence'],
                    'reason': llm_result['reason'],
                })
            elif llm_result['confidence'] < LLM_CLASSIFICATION_THRESHOLD:
                uncertain_list.append({
                    'gmail_id': email.get('id', ''),
                    'subject': email.get('subject', '')[:100],
                    'sender': email.get('sender', ''),
                    'confidence': llm_result['confidence'],
                    'reason': llm_result['reason'],
                })
            else:
                reason = llm_result['reason']
                skip_groups[reason] = skip_groups.get(reason, 0) + 1

    total = len(emails)
    return {
        'total_scanned': total,
        'keep': keep_list,
        'skip': skip_groups,
        'uncertain': uncertain_list,
        'stats': {
            'keep_rate': len(keep_list) / total if total else 0,
            'skip_rate': sum(skip_groups.values()) / total if total else 0,
            'uncertain_rate': len(uncertain_list) / total if total else 0,
            'llm_calls': llm_calls,
            'rule_only': rule_only,
        },
    }
