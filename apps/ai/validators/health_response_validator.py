"""
Health Response Validator — detects when CoS generates generic health advice
instead of using WLJ system-calculated values.

This validator runs AFTER the LLM generates a response but BEFORE it's
returned to the user. It catches cases where the LLM ignores the
HEALTH INTELLIGENCE block and substitutes generic textbook ranges.

Detection approach:
    1. Extract any health metric ranges from the response (e.g., "110-138g")
    2. Compare against the system-calculated values in CoS context
    3. If the response contains a generic range that doesn't match system
       values, log a SelfError and flag the response

This is an OBSERVE-ONLY validator (does not block responses), but logs
violations so we can track CoS compliance with system values.

Public API:
    validate_health_response(response_text, cos_context, user) -> dict
"""

import logging
import re

logger = logging.getLogger(__name__)


# =========================================================================
# Generic Range Detection Patterns
# =========================================================================

# Protein ranges like "0.7-1.0g per pound" or "110-138g" or "1.0 to 1.2 grams"
_PROTEIN_RANGE_PATTERNS = [
    # "X-Yg" or "X to Yg" (numeric ranges with g/grams suffix)
    re.compile(
        r'(\d{2,3})\s*[-–to]+\s*(\d{2,3})\s*(?:g|grams)\b',
        re.IGNORECASE,
    ),
    # "0.X-0.Yg per pound/lb" (per-pound multiplier ranges)
    re.compile(
        r'(\d+\.?\d*)\s*[-–to]+\s*(\d+\.?\d*)\s*(?:g|grams?)\s*(?:per|/)\s*(?:pound|lb|lbs?)\b',
        re.IGNORECASE,
    ),
    # "between Xg and Yg"
    re.compile(
        r'between\s+(\d{2,3})\s*(?:g|grams?)\s+and\s+(\d{2,3})\s*(?:g|grams?)\b',
        re.IGNORECASE,
    ),
]

# Sleep ranges like "7-9 hours"
_SLEEP_RANGE_PATTERNS = [
    re.compile(
        r'(\d+\.?\d*)\s*[-–to]+\s*(\d+\.?\d*)\s*hours?\s*(?:of\s+)?sleep',
        re.IGNORECASE,
    ),
]

# Generic health advice phrases (not tied to system data)
_GENERIC_HEALTH_PHRASES = [
    re.compile(r'\bgenerally\s+recommended\b', re.IGNORECASE),
    re.compile(r'\btypical(?:ly)?\s+(?:for|range|target)\b', re.IGNORECASE),
    re.compile(r'\bmost\s+(?:people|adults|experts)\s+recommend\b', re.IGNORECASE),
    re.compile(r'\bstandard\s+(?:recommendation|guideline)\b', re.IGNORECASE),
    re.compile(r'\bgeneral\s+(?:guideline|recommendation|rule)\b', re.IGNORECASE),
    re.compile(r'\ba\s+good\s+(?:target|goal|range)\s+(?:for|is|would)\b', re.IGNORECASE),
]


def validate_health_response(response_text, cos_context=None, user=None):
    """
    Validate that a CoS response uses system health values, not generic ranges.

    This is OBSERVE-ONLY — it never blocks the response.

    Args:
        response_text: str — the LLM response to validate.
        cos_context: dict — the CoS context that was injected (contains
            health_intelligence with system values).
        user: User instance (for logging).

    Returns:
        dict:
            'violations': list of detected violations
            'has_violations': bool
            'severity': 'none' | 'warning' | 'critical'
    """
    if not response_text:
        return {'violations': [], 'has_violations': False, 'severity': 'none'}

    violations = []

    # Get system values for comparison
    system_protein_target = None
    system_protein_method = None
    if cos_context:
        health_intel = cos_context.get('health_intelligence', {})
        protein = health_intel.get('protein', {})
        if protein:
            system_protein_target = protein.get('target_g')
            system_protein_method = protein.get('method')

    # Check for generic protein ranges
    for pattern in _PROTEIN_RANGE_PATTERNS:
        matches = pattern.finditer(response_text)
        for match in matches:
            low = float(match.group(1))
            high = float(match.group(2))

            # If system has a protein target, check if this range contradicts it
            if system_protein_target is not None:
                target = float(system_protein_target)
                # A range that doesn't contain the system target = violation
                if not (low <= target <= high) or (high - low > 30):
                    violations.append({
                        'type': 'GENERIC_PROTEIN_RANGE',
                        'found': match.group(0),
                        'system_value': f"{target:.0f}g",
                        'message': (
                            f"Response contains protein range '{match.group(0)}' "
                            f"but system target is {target:.0f}g"
                        ),
                    })
            else:
                # No system value, but a range suggests generic advice
                violations.append({
                    'type': 'GENERIC_PROTEIN_RANGE_NO_SYSTEM',
                    'found': match.group(0),
                    'system_value': None,
                    'message': (
                        f"Response contains generic protein range '{match.group(0)}' "
                        f"without referencing system-calculated values"
                    ),
                })

    # Check for generic health advice phrases
    for pattern in _GENERIC_HEALTH_PHRASES:
        match = pattern.search(response_text)
        if match:
            violations.append({
                'type': 'GENERIC_HEALTH_PHRASE',
                'found': match.group(0),
                'system_value': None,
                'message': (
                    f"Response uses generic health language: '{match.group(0)}'. "
                    f"CoS should reference system-calculated values."
                ),
            })

    # Determine severity
    severity = 'none'
    if violations:
        critical_types = {'GENERIC_PROTEIN_RANGE'}
        if any(v['type'] in critical_types for v in violations):
            severity = 'critical'
        else:
            severity = 'warning'

    # Log violations
    if violations:
        _log_health_response_violations(violations, user, response_text)

    return {
        'violations': violations,
        'has_violations': bool(violations),
        'severity': severity,
    }


def _log_health_response_violations(violations, user, response_text):
    """Log health response violations for monitoring."""
    violation_summary = '; '.join(v['message'] for v in violations[:3])
    logger.warning(
        "Health response validator: %d violation(s) detected — %s",
        len(violations),
        violation_summary,
    )

    # Log SelfError for tracking
    try:
        from apps.core.ai_governance.self_governance import record_self_error
        record_self_error(
            user=user,
            level=1,
            category='HEALTH_INTEL',
            trigger_code='GENERIC_HEALTH_RESPONSE',
            trigger_detail=violation_summary[:500],
            was_blocked=False,
        )
    except Exception as e:
        logger.warning("Failed to log health response violation: %s", e)

    # OpsAnomaly for visibility
    try:
        from apps.core.ai_observability.models import OpsAnomaly
        OpsAnomaly.objects.create(
            severity='P3',
            engine_name='HIE',
            anomaly_type='GENERIC_HEALTH_RESPONSE',
            summary=f"CoS generated generic health advice instead of system values: {violation_summary[:200]}",
            evidence={
                'violations': [
                    {'type': v['type'], 'found': v['found'], 'system_value': v['system_value']}
                    for v in violations[:5]
                ],
            },
            suggested_actions=[
                "Check that HEALTH INTELLIGENCE block is present in CoS injection.",
                "Verify protein_service.calculate_target() returns correct values.",
                "Review system prompt SECTION 9 (Health Intelligence Enforcement).",
            ],
        )
    except Exception as e:
        logger.warning("Failed to log health response ops anomaly: %s", e)
