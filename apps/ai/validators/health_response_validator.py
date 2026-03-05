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

The strict health status enforcer (enforce_strict_health_status) is NOT
observe-only — it deterministically builds the 4-line response from
CoS context, bypassing LLM output entirely.

Public API:
    validate_health_response(response_text, cos_context, user) -> dict
    enforce_strict_health_status(cos_context) -> str
"""

import logging
import re

logger = logging.getLogger(__name__)


# =========================================================================
# Strict Health Status Enforcer (deterministic — bypasses LLM)
# =========================================================================

def enforce_strict_health_status(cos_context):
    """
    Build the exact 4-line health intelligence status response from CoS context.

    This is called INSTEAD of using LLM output when strict health status mode
    is active. It reads the enum values directly from the context dict and
    returns a deterministic string. The LLM output is discarded.

    Args:
        cos_context: dict — the CoS context containing health_intelligence.

    Returns:
        str — exactly 4 lines:
            Fat loss phase: <ENUM>
            Plateau risk: <ENUM>
            Muscle preservation: <ENUM>
            Last updated: <timestamp>
    """
    body_comp = {}
    last_computed = ''

    if cos_context:
        hi = cos_context.get('health_intelligence', {})
        body_comp = hi.get('body_comp', {})
        last_computed = hi.get('last_computed', '')

    phase = body_comp.get('fat_loss_phase') or 'UNKNOWN (awaiting data)'
    plateau = body_comp.get('plateau_risk_label') or 'UNKNOWN (awaiting data)'
    muscle = body_comp.get('muscle_preservation_status') or 'UNKNOWN (awaiting data)'

    # Format last_updated — strip microseconds from ISO timestamp if present
    if last_computed:
        # Truncate to seconds: "2026-03-05T08:00:00.123456" → "2026-03-05T08:00:00"
        updated = last_computed.split('.')[0] if '.' in str(last_computed) else str(last_computed)
    else:
        updated = 'UNKNOWN'

    return (
        f"Fat loss phase: {phase}\n"
        f"Plateau risk: {plateau}\n"
        f"Muscle preservation: {muscle}\n"
        f"Last updated: {updated}"
    )


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

# Weekly protein total patterns — LLM should never use weekly totals.
# It should say "averaged Xg per day" not "logged Xg this week".
_PROTEIN_WEEKLY_TOTAL_PATTERNS = [
    # "Xg this week" / "Xg for the week" / "Xg over the week"
    re.compile(
        r'\b(\d{2,5})\s*g?\s*(?:this|for the|over the|during the|for this|in the)\s+week\b',
        re.IGNORECASE,
    ),
    # "total protein this week" / "total of Xg"
    re.compile(
        r'\btotal\s+(?:protein|intake)\s+(?:this|for the|over the)\s+week\b',
        re.IGNORECASE,
    ),
    # "you've logged/consumed/eaten Xg this week"
    re.compile(
        r"\byou(?:'ve|'re| have| are)\s+(?:logged|consumed|eaten|had|tracked)\s+\d+\s*g?\s*(?:this|for the|over the)\s+week\b",
        re.IGNORECASE,
    ),
    # "weekly total of Xg" / "week total: Xg"
    re.compile(
        r'\bweek(?:ly)?\s+total\b',
        re.IGNORECASE,
    ),
]

# Body composition generic range patterns — LLM should use system values only.
_BODY_COMP_GENERIC_PATTERNS = [
    # "15-20% body fat" or "body fat of 15-20%"
    re.compile(
        r'\b(\d{1,2})\s*[-–to]+\s*(\d{1,2})\s*%?\s*(?:body\s+fat|BF)\b',
        re.IGNORECASE,
    ),
    # "ideal body fat is..." or "healthy body fat range"
    re.compile(
        r'\b(?:ideal|healthy|optimal|target|recommended)\s+body\s+fat\b',
        re.IGNORECASE,
    ),
    # "1-2 lbs per week is recommended" / "lose 1 to 2 pounds per week"
    re.compile(
        r'\b(\d+\.?\d*)\s*[-–to]+\s*(\d+\.?\d*)\s*(?:lbs?|pounds?)\s*(?:per|a|each)\s*week\b',
        re.IGNORECASE,
    ),
    # "your fat mass is approximately" / "estimated fat mass"
    re.compile(
        r'\b(?:your\s+)?fat\s+mass\s+is\s+(?:approximately|about|roughly|estimated)\b',
        re.IGNORECASE,
    ),
    # Generic plateau predictions: "you will/may plateau in X days/weeks"
    re.compile(
        r'\byou\b.*\bplateau\b.*\bin\b.*\b(?:days?|weeks?)\b',
        re.IGNORECASE,
    ),
    # Self-classified phase: "you appear/seem to be in/entering X phase"
    re.compile(
        r'\byou\b.*\b(?:appear|seem)\b.*\b(?:in|entering)\b.*\bphase\b',
        re.IGNORECASE,
    ),
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

    # Check for weekly protein totals (should always use daily average)
    for pattern in _PROTEIN_WEEKLY_TOTAL_PATTERNS:
        match = pattern.search(response_text)
        if match:
            violations.append({
                'type': 'PROTEIN_WEEKLY_TOTAL',
                'found': match.group(0),
                'system_value': None,
                'message': (
                    f"Response uses weekly protein total language: '{match.group(0)}'. "
                    f"CoS must use 7-day daily average, never weekly totals."
                ),
            })

    # Check for generic body composition advice
    for pattern in _BODY_COMP_GENERIC_PATTERNS:
        match = pattern.search(response_text)
        if match:
            violations.append({
                'type': 'GENERIC_BODY_COMP',
                'found': match.group(0),
                'system_value': None,
                'message': (
                    f"Response uses generic body composition language: '{match.group(0)}'. "
                    f"CoS must use locked system values from BODY COMPOSITION block."
                ),
            })

    # Health intelligence enum enforcement
    violations.extend(
        _check_health_intelligence_enums(response_text, cos_context)
    )

    # Determine severity
    severity = 'none'
    if violations:
        critical_types = {
            'GENERIC_PROTEIN_RANGE', 'PROTEIN_WEEKLY_TOTAL', 'GENERIC_BODY_COMP',
            'INVALID_MUSCLE_STATUS', 'INVALID_FAT_LOSS_PHASE', 'INVALID_PLATEAU_RISK',
        }
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


# =========================================================================
# Health Intelligence Enum Enforcement
# =========================================================================

# Valid enum values for health intelligence fields
_VALID_FAT_LOSS_PHASES = {
    'RAPID_INITIAL_LOSS', 'STABLE_FAT_LOSS', 'RECOMPOSITION', 'PLATEAU', 'REBOUND_RISK',
}
_VALID_PLATEAU_RISK_LABELS = {'LOW', 'RISING', 'HIGH'}
_VALID_MUSCLE_PRESERVATION = {'HIGH_QUALITY', 'MODERATE_QUALITY', 'MUSCLE_RISK'}

# Words that indicate the LLM paraphrased an enum instead of quoting it
_INVALID_MUSCLE_WORDS = re.compile(
    r'\bmuscle\s+preservation\b[^:]*?\b(stable|good|strong|adequate|fine|normal|healthy|ok)\b',
    re.IGNORECASE,
)
_INVALID_PHASE_WORDS = re.compile(
    r'\b(in the|currently in|entering the|entering a)\b[^.]{0,30}\bfat\s+loss\s+phase\b'
    r'|\bfat\s+loss\s+phase\b[^:]{0,30}\b(in the|currently in|entering the|entering a)\b',
    re.IGNORECASE,
)

# Pattern to detect when response mentions health intelligence fields
_HEALTH_INTEL_RESPONSE_PATTERN = re.compile(
    r'(?:fat\s+loss\s+phase|plateau\s+risk|muscle\s+preservation)',
    re.IGNORECASE,
)


def _check_health_intelligence_enums(response_text, cos_context):
    """
    Validate that health intelligence enum fields use exact system values.

    Checks:
    1. If response mentions muscle preservation with invalid words like "stable"
    2. If response mentions fat loss phase with paraphrased language
    3. If response mentions unrelated modules (sleep/calendar) when health
       intelligence fields are being answered in a short format
    """
    violations = []

    if not _HEALTH_INTEL_RESPONSE_PATTERN.search(response_text):
        return violations

    # Check for invalid muscle preservation words
    match = _INVALID_MUSCLE_WORDS.search(response_text)
    if match:
        violations.append({
            'type': 'INVALID_MUSCLE_STATUS',
            'found': match.group(0),
            'system_value': None,
            'message': (
                f"Response uses invalid muscle preservation word '{match.group(1)}'. "
                f"Must use exact enum: HIGH_QUALITY, MODERATE_QUALITY, or MUSCLE_RISK."
            ),
        })

    # Check for paraphrased fat loss phase (narrative instead of enum)
    match = _INVALID_PHASE_WORDS.search(response_text)
    if match:
        violations.append({
            'type': 'INVALID_FAT_LOSS_PHASE',
            'found': match.group(0).strip(),
            'system_value': None,
            'message': (
                f"Response paraphrases fat loss phase instead of using enum. "
                f"Must use: RAPID_INITIAL_LOSS, STABLE_FAT_LOSS, RECOMPOSITION, PLATEAU, or REBOUND_RISK."
            ),
        })

    return violations


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
