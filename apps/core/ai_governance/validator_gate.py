"""
Phase 8 — Pre-Release Validator Gate.

Deterministic validator that inspects every LLM-generated response BEFORE
it is persisted or returned to the user. Enforces three policies:

    Structural-Critical: Banned internal terms in response text.
        → BLOCK: replace response with safe template, log SelfError Level 2.

    Unverifiable-Action-Claim: LLM claims an action was performed (scheduled,
        removed, confirmed, etc.) when no backend tool actually executed.
        → BLOCK: replace with truthful template, log SelfError Level 2.

    Numeric-Dependent: Internal numeric thresholds/scores exposed.
        → OBSERVE-ONLY: log SelfError Level 1, return original response.

If the validator itself crashes:
    → Log SelfError Level 3 (VALIDATOR_CRASH) + OpsAnomaly.
    → Return safe constrained response (never the original, never silent bypass).

Public API:
    validate_response(response, user, conversation=None, action_executed=None) -> dict
"""

import hashlib
import logging
import re
import uuid

from django.utils import timezone

logger = logging.getLogger(__name__)


# =========================================================================
# Safe Fallback Templates (deterministic, plain language, no jargon)
# =========================================================================

STRUCTURAL_BLOCK_RESPONSE = (
    "I need to rephrase that. Let me give you a clearer answer.\n\n"
    "Based on what you've shared, here's what I'd focus on right now: "
    "keep doing what's working, and let's check in on anything that "
    "feels off track. What would be most helpful to talk through?"
)

VALIDATOR_CRASH_RESPONSE = (
    "I want to make sure I'm giving you the best guidance. "
    "Let me take a step back.\n\n"
    "What's the most important thing on your mind right now? "
    "I'll focus there."
)

UNVERIFIABLE_ACTION_CLAIM_RESPONSE = (
    "I can't confirm that change was made because no calendar update was "
    "executed. I can create new events, but updates or removals aren't "
    "available through chat yet. If you want, I can create a new event "
    "for the correct date and time."
)


# =========================================================================
# Structural Detection — Banned Terms (from language_rules.py)
# =========================================================================

def _get_banned_terms():
    """Import and return BANNED_TERMS from language_rules."""
    from apps.core.ai_governance.language_rules import BANNED_TERMS
    return BANNED_TERMS


def _check_structural_violations(response_text):
    """
    Check response for banned internal terms (case-insensitive).

    Returns:
        list[str] — banned terms found (empty if clean).
    """
    lower_text = response_text.lower()
    found = []
    for term in _get_banned_terms():
        if term.lower() in lower_text:
            found.append(term)
    return found


# =========================================================================
# Numeric Detection — Internal Scores/Thresholds
# =========================================================================

# Patterns that indicate internal numeric leakage.
# These match phrases like "capacity at 85%", "miss rate is 0.7",
# "pressure index 72", "density score: 0.45", "CPI 0-100", etc.
_NUMERIC_PATTERNS = [
    # "capacity at/is/= XX%"
    re.compile(
        r'\b(?:capacity|density|compression|breach|erosion|collision|pressure)'
        r'\s+(?:at|is|=|:)\s*\d+(?:\.\d+)?%?',
        re.IGNORECASE,
    ),
    # "miss rate is/= 0.X"
    re.compile(
        r'\b(?:miss rate|honor rate|acceptance rate|action rate|success rate)'
        r'\s+(?:is|=|:)\s*\d+(?:\.\d+)?',
        re.IGNORECASE,
    ),
    # "score: 0.XX" or "score = 72" (bare numeric scores)
    re.compile(
        r'\b(?:drift score|pressure index|importance weight|responsiveness score'
        r'|confidence level|escalation modifier|capacity factor)'
        r'\s*(?:is|=|:|\s)\s*\d+(?:\.\d+)?',
        re.IGNORECASE,
    ),
    # "CPI" or "SRI" followed by a number
    re.compile(
        r'\b(?:CPI|SRI)\s*(?:is|=|:|\s)\s*\d+(?:\.\d+)?',
        re.IGNORECASE,
    ),
    # "Level 1/2/3" used as escalation terminology
    re.compile(
        r'\bescalation\s+level\s+\d',
        re.IGNORECASE,
    ),
]

# Patterns that look numeric but are acceptable in user-facing context.
# e.g., "3 out of 5 tasks", "completed 2 goals", "7 days", "24 hours"
_NUMERIC_SAFE_PATTERNS = [
    re.compile(r'\d+\s+(?:out of|of)\s+\d+', re.IGNORECASE),
    re.compile(r'\d+\s+(?:tasks?|goals?|items?|days?|hours?|minutes?|commitments?)', re.IGNORECASE),
    re.compile(r'(?:completed|finished|done|missed|made|honored)\s+\d+', re.IGNORECASE),
]


# =========================================================================
# Action-Claim Detection — Unverifiable Action Confirmations
# =========================================================================

# Patterns that indicate the LLM is claiming it performed a backend action.
# These ONLY trigger when action_executed=False (no tool actually ran).
_ACTION_CLAIM_PATTERNS = [
    # Checkmark confirmations: "✓ Scheduled", "✓ Removed", "✓ Confirmed"
    re.compile(r'[✓✔☑]\s*(?:scheduled|removed|confirmed|deleted|updated|rescheduled|added|created|cancelled|canceled)', re.IGNORECASE),
    # "I've <past-tense action>"
    re.compile(r"\bI'?ve\s+(?:scheduled|removed|deleted|added|rescheduled|updated|confirmed|created|cancelled|canceled|set\s+that|taken\s+care)", re.IGNORECASE),
    # "I <past-tense action> it/that/the/your"
    re.compile(r'\bI\s+(?:scheduled|removed|deleted|added|rescheduled|updated|confirmed|created|cancelled|canceled)\s+(?:it|that|the|your|those|both|all|them)\b', re.IGNORECASE),
    # "It's set" / "It's been scheduled/removed"
    re.compile(r"\bit'?s\s+(?:set|been\s+(?:scheduled|removed|deleted|updated|rescheduled|added|confirmed|created))\b", re.IGNORECASE),
    # "I took care of that" / "I took care of it"
    re.compile(r'\bI\s+took\s+care\s+of\s+(?:that|it|those)\b', re.IGNORECASE),
    # Standalone "Done" as action completion (must be near start of sentence or alone)
    re.compile(r'(?:^|[.!]\s*)Done[.!]?\s*(?:$|[A-Z])', re.MULTILINE),
]


def _check_action_claims(response_text):
    """
    Check response for action-confirmation language.

    Returns:
        list[str] — matched claim phrases (empty if clean).
    """
    found = []
    for pattern in _ACTION_CLAIM_PATTERNS:
        matches = pattern.findall(response_text)
        for match in matches:
            found.append(match.strip())
    return found


def _check_numeric_deviations(response_text):
    """
    Check response for internal numeric/threshold leakage.

    Uses policy-based tolerance: only flags patterns that look like
    internal system metrics, not contextual numbers.

    Returns:
        list[str] — matched patterns (empty if clean).
    """
    found = []
    for pattern in _NUMERIC_PATTERNS:
        matches = pattern.findall(response_text)
        for match in matches:
            # Check if this match overlaps with a safe pattern
            is_safe = False
            for safe_pat in _NUMERIC_SAFE_PATTERNS:
                # Check if the safe pattern covers this region
                if safe_pat.search(response_text):
                    # More precise: check if the match text itself is part
                    # of a safe pattern match
                    for safe_match in safe_pat.finditer(response_text):
                        if match in safe_match.group():
                            is_safe = True
                            break
                if is_safe:
                    break
            if not is_safe:
                found.append(match)
    return found


# =========================================================================
# Core Validator
# =========================================================================

def _response_hash(response_text):
    """SHA-256 of response text for correlation (not storage)."""
    return hashlib.sha256(response_text.encode('utf-8')).hexdigest()


def validate_response(response, user=None, conversation=None, action_executed=None):
    """
    Pre-release validation gate for LLM-generated responses.

    Checks:
        1. Structural violations (banned terms) → BLOCK + replace
        2. Unverifiable action claims (when no action executed) → BLOCK + replace
        3. Numeric deviations (internal scores) → OBSERVE-ONLY

    On validator crash:
        → Level 3 SelfError + OpsAnomaly + safe constrained response.

    Args:
        response: str — the LLM response text to validate.
        user: User instance (nullable).
        conversation: AssistantConversation (nullable, for context).
        action_executed: bool or None — whether a backend action was
            executed in this request. When False, action-confirmation
            language in the response triggers a BLOCK.

    Returns:
        dict:
            'response': str — original or replacement response.
            'blocked': bool — True if response was replaced.
            'violations': list — detected violations (for logging).
    """
    try:
        return _validate_response_inner(response, user, conversation, action_executed)
    except Exception as exc:
        # ── VALIDATOR CRASH — never silent bypass ──
        logger.error("Phase 8: Validator gate CRASHED: %s", exc)
        try:
            _handle_validator_crash(response, user, exc)
        except Exception as crash_exc:
            # Even crash handler failed — still return safe response
            logger.error(
                "Phase 8: CRITICAL — crash handler itself failed: %s",
                crash_exc,
            )
        return {
            'response': VALIDATOR_CRASH_RESPONSE,
            'blocked': True,
            'violations': [f'VALIDATOR_CRASH: {exc}'],
        }


def _validate_response_inner(response, user, conversation, action_executed=None):
    """Inner validation logic — may raise on unexpected errors."""
    if not response or not isinstance(response, str):
        return {'response': response or '', 'blocked': False, 'violations': []}

    trace_id = str(uuid.uuid4())
    resp_hash = _response_hash(response)
    violations = []

    # ── 1. Structural check (BLOCKING) ──
    structural = _check_structural_violations(response)
    if structural:
        violations.extend([f'STRUCTURAL:{t}' for t in structural])
        _log_structural_violation(
            user=user,
            terms_found=structural,
            resp_hash=resp_hash,
            trace_id=trace_id,
        )
        return {
            'response': STRUCTURAL_BLOCK_RESPONSE,
            'blocked': True,
            'violations': violations,
        }

    # ── 2. Unverifiable action-claim check (BLOCKING) ──
    # Only fires when we KNOW no backend action executed (action_executed=False).
    # When action_executed is None (legacy callers), this check is skipped.
    if action_executed is False:
        action_claims = _check_action_claims(response)
        if action_claims:
            violations.extend([f'ACTION_CLAIM:{c}' for c in action_claims])
            _log_unverifiable_action_claim(
                user=user,
                claims_found=action_claims,
                resp_hash=resp_hash,
                trace_id=trace_id,
            )
            return {
                'response': UNVERIFIABLE_ACTION_CLAIM_RESPONSE,
                'blocked': True,
                'violations': violations,
            }

    # ── 3. Numeric check (OBSERVE-ONLY) ──
    numeric = _check_numeric_deviations(response)
    if numeric:
        violations.extend([f'NUMERIC:{m}' for m in numeric])
        _log_numeric_deviation(
            user=user,
            matches=numeric,
            resp_hash=resp_hash,
            trace_id=trace_id,
        )
        return {
            'response': response,  # original — observe-only
            'blocked': False,
            'violations': violations,
        }

    # ── Clean ──
    return {'response': response, 'blocked': False, 'violations': []}


# =========================================================================
# Logging Helpers (fire-and-forget)
# =========================================================================

def _log_structural_violation(user, terms_found, resp_hash, trace_id):
    """Log SelfError + DecisionRecord + OpsAnomaly for structural violation."""
    try:
        from apps.core.ai_governance.self_governance import record_self_error
        record_self_error(
            user=user,
            level=2,
            category='STRUCTURAL',
            trigger_code='BANNED_TERM_LEAKED',
            trigger_detail=f"Banned terms detected: {', '.join(terms_found)}",
            original_response_hash=resp_hash,
            was_blocked=True,
            trace_id=trace_id,
        )
    except Exception as e:
        logger.warning("Phase 8: Failed to log structural violation: %s", e)

    # DecisionRecord
    try:
        from apps.core.ai_observability.models import DecisionRecord
        DecisionRecord.objects.create(
            trace_id=trace_id,
            decision_type='validation',
            engine_name='VGE',
            decision='BLOCK_STRUCTURAL',
            rationale=f"Banned terms found: {', '.join(terms_found)}",
            inputs_summary=f"response_hash={resp_hash[:16]}...",
            affected_items=terms_found,
            user_id=user.id if user else None,
            confidence=1.0,
        )
    except Exception as e:
        logger.warning("Phase 8: Failed to log decision record: %s", e)

    # OpsAnomaly
    try:
        from apps.core.ai_observability.models import OpsAnomaly
        OpsAnomaly.objects.create(
            severity='P2',
            engine_name='VGE',
            anomaly_type='STRUCTURAL_VIOLATION',
            summary=f"Banned term leaked in response: {', '.join(terms_found[:3])}",
            evidence={'terms': terms_found, 'response_hash': resp_hash},
            suggested_actions=[
                "Review LLM system prompt for term suppression.",
                "Check if new terms need adding to BANNED_TERMS.",
            ],
        )
    except Exception as e:
        logger.warning("Phase 8: Failed to log ops anomaly: %s", e)


def _log_numeric_deviation(user, matches, resp_hash, trace_id):
    """Log SelfError + DecisionRecord for numeric deviation (observe-only)."""
    try:
        from apps.core.ai_governance.self_governance import record_self_error
        record_self_error(
            user=user,
            level=1,
            category='NUMERIC',
            trigger_code='NUMERIC_DEVIATION',
            trigger_detail=f"Numeric patterns detected: {', '.join(matches[:5])}",
            original_response_hash=resp_hash,
            was_blocked=False,
            trace_id=trace_id,
        )
    except Exception as e:
        logger.warning("Phase 8: Failed to log numeric deviation: %s", e)

    # DecisionRecord
    try:
        from apps.core.ai_observability.models import DecisionRecord
        DecisionRecord.objects.create(
            trace_id=trace_id,
            decision_type='validation',
            engine_name='VGE',
            decision='OBSERVE_NUMERIC',
            rationale=f"Numeric patterns found (observe-only): {', '.join(matches[:5])}",
            inputs_summary=f"response_hash={resp_hash[:16]}...",
            affected_items=matches[:5],
            user_id=user.id if user else None,
            confidence=0.7,
        )
    except Exception as e:
        logger.warning("Phase 8: Failed to log decision record: %s", e)


def _log_unverifiable_action_claim(user, claims_found, resp_hash, trace_id):
    """Log SelfError + DecisionRecord + OpsAnomaly for unverifiable action claim."""
    claims_str = ', '.join(claims_found[:5])

    # SelfError Level 2
    try:
        from apps.core.ai_governance.self_governance import record_self_error
        record_self_error(
            user=user,
            level=2,
            category='STRUCTURAL',
            trigger_code='UNVERIFIABLE_ACTION_CLAIM',
            trigger_detail=f"Action-claim language with no backend execution: {claims_str}",
            original_response_hash=resp_hash,
            was_blocked=True,
            trace_id=trace_id,
        )
    except Exception as e:
        logger.warning("Phase 8: Failed to log unverifiable action claim: %s", e)

    # DecisionRecord
    try:
        from apps.core.ai_observability.models import DecisionRecord
        DecisionRecord.objects.create(
            trace_id=trace_id,
            decision_type='validation',
            engine_name='VGE',
            decision='BLOCK_UNVERIFIABLE_ACTION_CLAIM',
            rationale=f"LLM claimed action without backend execution: {claims_str}",
            inputs_summary=f"response_hash={resp_hash[:16]}...",
            affected_items=claims_found[:5],
            user_id=user.id if user else None,
            confidence=1.0,
        )
    except Exception as e:
        logger.warning("Phase 8: Failed to log action-claim decision record: %s", e)

    # OpsAnomaly
    try:
        from apps.core.ai_observability.models import OpsAnomaly
        OpsAnomaly.objects.create(
            severity='P2',
            engine_name='VGE',
            anomaly_type='STRUCTURAL_VIOLATION',
            summary=f"LLM fabricated action confirmation: {claims_str}",
            evidence={'claims': claims_found, 'response_hash': resp_hash},
            suggested_actions=[
                "Review LLM system prompt to discourage false confirmations.",
                "Implement delete/update event tools to handle these requests.",
            ],
        )
    except Exception as e:
        logger.warning("Phase 8: Failed to log action-claim ops anomaly: %s", e)


def _handle_validator_crash(original_response, user, exc):
    """Handle validator crash — Level 3 SelfError + OpsAnomaly."""
    resp_hash = _response_hash(original_response) if original_response else ''

    # SelfError Level 3
    try:
        from apps.core.ai_governance.self_governance import record_self_error
        record_self_error(
            user=user,
            level=3,
            category='GOVERNANCE',
            trigger_code='VALIDATOR_CRASH',
            trigger_detail=f"Validator exception: {exc}",
            original_response_hash=resp_hash,
            was_blocked=True,
            trace_id=str(uuid.uuid4()),
        )
    except Exception as e:
        logger.error("Phase 8: CRITICAL — failed to log validator crash: %s", e)

    # OpsAnomaly
    try:
        from apps.core.ai_observability.models import OpsAnomaly
        OpsAnomaly.objects.create(
            severity='P1',
            engine_name='VGE',
            anomaly_type='VALIDATOR_CRASH',
            summary=f"Validator gate crashed: {exc}",
            evidence={
                'exception': str(exc),
                'response_hash': resp_hash,
            },
            suggested_actions=[
                "Investigate validator_gate.py for the crash source.",
                "Check recent code changes to governance modules.",
            ],
        )
    except Exception as e:
        logger.error("Phase 8: CRITICAL — failed to log crash anomaly: %s", e)
