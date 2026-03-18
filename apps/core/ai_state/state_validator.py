"""
SAE State Contract Validator.

Validates that domain state builders produce correctly shaped output
with the Rich State Contract overlay (_contract + _meta).

Purpose:
    - Catch drift between flat keys and _contract structure
    - Ensure new domains include _contract from day one
    - Provide visibility into state health without breaking production

Usage:
    from apps.core.ai_state.state_validator import validate_state_contract

    # In tests or observability checks:
    state = build_task_state(user)
    issues = validate_state_contract('tasks', state)
    # issues = [] means valid

Architecture note:
    Flat keys are the current operational interface (consumed by 50+ files).
    _contract is the canonical target structure for future migration.
    This validator ensures _contract stays in sync with flat keys.
    Flat key removal is a FUTURE phase — not enforced here.
"""

import logging

logger = logging.getLogger(__name__)

# ── Contract shape definitions per domain ──────────────────────────
# Each domain declares which _contract sections it must have and
# which keys within each section are required.

_CONTRACT_SCHEMAS = {
    'tasks': {
        'summary': ['total_pending', 'completed_today', 'momentum_signal'],
        'today': ['items', 'next_up'],
        'upcoming': ['tomorrow', 'future'],
        'alerts': ['overdue', 'overdue_count'],
    },
    'calendar': {
        'summary': ['today_count', 'schedule_density'],
        'today': ['items', 'current_event', 'next_event'],
        'upcoming': ['events'],
        'alerts': ['overdue'],
    },
    'medicine': {
        'summary': ['active_count', 'adherence_7d', 'expected_today'],
        'today': ['schedule_status', 'taken', 'missed', 'pending'],
        'upcoming': [],
        'alerts': ['needs_refill'],
    },
    'routine': {
        'summary': ['total_routines', 'today_count'],
        'today': ['items_by_window', 'current_window', 'next_up'],
        'upcoming': [],
        'alerts': ['missed'],
    },
}

_CONTRACT_SECTIONS = frozenset({'summary', 'today', 'upcoming', 'alerts'})

_META_REQUIRED_KEYS = frozenset({'last_updated', 'source', 'completeness', 'confidence'})
_META_COMPLETENESS_VALUES = frozenset({'full', 'partial', 'limited'})
_META_CONFIDENCE_VALUES = frozenset({'high', 'medium', 'low'})


def validate_state_contract(domain: str, state: dict) -> list:
    """Validate that a domain's state dict includes a correct _contract overlay.

    Args:
        domain: Domain name (e.g., 'tasks', 'calendar').
        state: The dict returned by the domain's build_*_state() function.

    Returns:
        List of issue strings. Empty list = valid.
    """
    issues = []

    if domain not in _CONTRACT_SCHEMAS:
        # Domain not yet in contract system — not an error, just skip
        return issues

    # ── Validate _contract exists ──
    contract = state.get('_contract')
    if contract is None:
        issues.append(f"{domain}: missing '_contract' key")
        return issues  # can't validate further

    if not isinstance(contract, dict):
        issues.append(f"{domain}: '_contract' is not a dict")
        return issues

    # ── Validate required sections exist ──
    schema = _CONTRACT_SCHEMAS[domain]
    for section in _CONTRACT_SECTIONS:
        if section not in contract:
            issues.append(f"{domain}: _contract missing section '{section}'")
            continue

        # Validate required keys within each section
        required_keys = schema.get(section, [])
        section_data = contract[section]
        if not isinstance(section_data, dict):
            issues.append(
                f"{domain}: _contract.{section} is {type(section_data).__name__}, "
                f"expected dict"
            )
            continue

        for key in required_keys:
            if key not in section_data:
                issues.append(
                    f"{domain}: _contract.{section} missing required key '{key}'"
                )

    # ── Validate _meta exists and is correct ──
    meta = state.get('_meta')
    if meta is None:
        issues.append(f"{domain}: missing '_meta' key")
    elif not isinstance(meta, dict):
        issues.append(f"{domain}: '_meta' is not a dict")
    else:
        for key in _META_REQUIRED_KEYS:
            if key not in meta:
                issues.append(f"{domain}: _meta missing required key '{key}'")

        completeness = meta.get('completeness')
        if completeness and completeness not in _META_COMPLETENESS_VALUES:
            issues.append(
                f"{domain}: _meta.completeness '{completeness}' not in "
                f"{_META_COMPLETENESS_VALUES}"
            )

        confidence = meta.get('confidence')
        if confidence and confidence not in _META_CONFIDENCE_VALUES:
            issues.append(
                f"{domain}: _meta.confidence '{confidence}' not in "
                f"{_META_CONFIDENCE_VALUES}"
            )

        if meta.get('source') != 'SAE':
            issues.append(
                f"{domain}: _meta.source should be 'SAE', "
                f"got '{meta.get('source')}'"
            )

    return issues


def validate_all_user_state(user_state: dict) -> dict:
    """Validate _contract for all domains that have schemas defined.

    Args:
        user_state: Full UserState.state_data dict (keyed by domain name).

    Returns:
        Dict of {domain: [issues]}. Only domains with issues are included.
    """
    all_issues = {}
    for domain in _CONTRACT_SCHEMAS:
        domain_state = user_state.get(domain, {})
        if not domain_state:
            continue
        issues = validate_state_contract(domain, domain_state)
        if issues:
            all_issues[domain] = issues
    return all_issues


def log_validation_results(user_state: dict, user_id=None):
    """Run validation and log results. Safe to call in background tasks.

    Returns True if all domains pass, False if any issues found.
    """
    issues = validate_all_user_state(user_state)
    if not issues:
        return True

    for domain, domain_issues in issues.items():
        for issue in domain_issues:
            logger.warning(
                "STATE_CONTRACT_DRIFT user=%s %s",
                user_id or '?',
                issue,
            )
    return False
