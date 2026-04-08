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
    # Phase 2 domains
    'finance': {
        'summary': ['account_count', 'cash_pressure_level'],
        'today': [],
        'upcoming': [],
        'alerts': [],
    },
    'relationships': {
        'summary': ['active_count', 'neglected_count'],
        'today': ['birthdays'],
        'upcoming': [],
        'alerts': ['neglected'],
    },
    'brain_training': {
        'summary': ['sessions_this_week', 'streak_length'],
        'today': ['completed'],
        'upcoming': [],
        'alerts': [],
    },
    'medical': {
        'summary': ['total_lab_results'],
        'today': [],
        'upcoming': [],
        'alerts': ['abnormal_results'],
    },
    'capture': {
        'summary': ['unprocessed_count', 'backlog_level'],
        'today': ['captures_today'],
        'upcoming': [],
        'alerts': [],
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


# ─────────────────────────────────────────────────────────────────────
# Phase 6+ Signal Contract Enforcement Layer
# ─────────────────────────────────────────────────────────────────────
#
# Validates per-key conventions across all domain state dicts:
#   - `_pct`, `_percent`, `_percentage` suffixes → value must be 0–100
#   - `_ratio` suffix                           → value must be 0–1
#   - `_score` suffix                            → value must be 0–100
#     (unless documented otherwise; see SIGNAL_CONVENTIONS.md)
#   - `_trend` suffix                            → value must be one of
#                                                   "increasing", "decreasing",
#                                                   "stable", "insufficient_data"
#
# The validator LOGS violations (never raises) so it is safe to run
# on the critical path. Intended for background observability runs
# or pre-deploy gate tests.

_PERCENT_SUFFIXES = ("_pct", "_percent", "_percentage")
_SCORE_SUFFIXES = ("_score",)
_RATIO_SUFFIXES = ("_ratio",)
_TREND_SUFFIXES = ("_trend",)

_VALID_TREND_VALUES = frozenset(
    {"increasing", "decreasing", "stable", "insufficient_data",
     # Legacy vocabularies still in use by some builders:
     "improving", "declining", "up", "down", "flat"}
)

# Keys that are explicitly allowed to exceed the normal 0-100 bound.
# Add here (not in logic) so drift shows up in code review.
_SCORE_BOUND_EXEMPT = frozenset({
    "workout_consistency_score",  # capped at 150 (ratio * 100 of 7d/30d)
    "strength_trend_score",       # non-numeric: "increasing"/"decreasing"
    "today_training_load",        # arbitrary training load units
    "weekly_training_load",       # arbitrary training load units
    "avg_daily_load_7d",          # arbitrary training load units
})


def validate_signal_conventions(domain: str, domain_state: dict) -> list:
    """Check per-key unit conventions for a single domain state dict.

    Returns a list of issue strings; empty list means the dict is clean.
    Safe to call on any state dict — unknown keys are ignored.

    This is Phase 6+ enforcement: it runs alongside the existing
    Rich State Contract validator but focuses on VALUE bounds rather
    than STRUCTURE.
    """
    if not isinstance(domain_state, dict):
        return [f"[{domain}] not a dict: got {type(domain_state).__name__}"]

    issues = []
    for key, value in domain_state.items():
        if not isinstance(key, str) or key.startswith("_"):
            continue
        if value is None:
            # None is a valid "not measured" sentinel — skip bound check.
            continue

        # Percent-suffixed keys must be 0-100 numeric.
        if any(key.endswith(sfx) for sfx in _PERCENT_SUFFIXES):
            if not isinstance(value, (int, float)):
                issues.append(
                    f"[{domain}.{key}] percent key has non-numeric "
                    f"value: {value!r}"
                )
                continue
            if value < 0 or value > 100:
                issues.append(
                    f"[{domain}.{key}] percent out of bounds (expected "
                    f"0-100): {value}"
                )
            continue

        # Ratio-suffixed keys must be 0-1 numeric.
        if any(key.endswith(sfx) for sfx in _RATIO_SUFFIXES):
            if not isinstance(value, (int, float)):
                issues.append(
                    f"[{domain}.{key}] ratio key has non-numeric "
                    f"value: {value!r}"
                )
                continue
            if value < 0 or value > 1.5:  # small slack for cap-at-1 rounding
                issues.append(
                    f"[{domain}.{key}] ratio out of bounds (expected "
                    f"0-1): {value}"
                )
            continue

        # Score-suffixed keys: numeric if present, must be 0-100
        # unless explicitly exempt.
        if any(key.endswith(sfx) for sfx in _SCORE_SUFFIXES):
            if key in _SCORE_BOUND_EXEMPT:
                continue
            if not isinstance(value, (int, float)):
                # Some _score fields are intentionally text-valued
                # (e.g. strength_trend_score = "increasing"). If not
                # in the exempt set, that's still a convention bug.
                issues.append(
                    f"[{domain}.{key}] score key has non-numeric "
                    f"value: {value!r}"
                )
                continue
            if value < 0 or value > 100:
                issues.append(
                    f"[{domain}.{key}] score out of bounds (expected "
                    f"0-100): {value}"
                )
            continue

        # Trend-suffixed keys must be in the approved vocabulary.
        if any(key.endswith(sfx) for sfx in _TREND_SUFFIXES):
            if not isinstance(value, str):
                issues.append(
                    f"[{domain}.{key}] trend key has non-string "
                    f"value: {value!r}"
                )
                continue
            if value not in _VALID_TREND_VALUES:
                issues.append(
                    f"[{domain}.{key}] trend value not in approved "
                    f"vocabulary: {value!r}"
                )
            continue

    return issues


def validate_all_signal_conventions(user_state: dict) -> dict:
    """Apply validate_signal_conventions across every domain dict.

    Returns {domain: [issue, ...]} for domains with any violations.
    Empty dict means everything is clean.
    """
    all_issues = {}
    for domain, domain_state in (user_state or {}).items():
        if not isinstance(domain_state, dict):
            continue
        if domain.startswith("_"):
            continue
        issues = validate_signal_conventions(domain, domain_state)
        if issues:
            all_issues[domain] = issues
    return all_issues


def log_signal_convention_violations(user_state: dict, user_id=None) -> bool:
    """Run signal-convention validation and log any violations.

    Returns True if clean, False if any issues found. Does not raise.
    Safe for use in background observability / nightly audits.
    """
    issues = validate_all_signal_conventions(user_state)
    if not issues:
        return True
    for domain, domain_issues in issues.items():
        for issue in domain_issues:
            logger.warning(
                "SIGNAL_CONVENTION_VIOLATION user=%s %s",
                user_id or "?", issue,
            )
    return False
