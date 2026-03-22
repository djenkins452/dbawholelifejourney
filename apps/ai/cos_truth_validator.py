"""
CoS Truth Validator — Post-response guardrail against fabricated completions.

The LLM does not decide truth. The system declares truth. The LLM must obey.

Checks the LLM's response against live execution data. If the response
claims something is complete/done when it's NOT DONE in the execution
contract, the response is REJECTED (non-streaming) or corrected (streaming).

This is a hard guardrail: Beth must NEVER tell the user something is done
when it isn't. Trust > tone.
"""
import logging
import re

logger = logging.getLogger(__name__)

# ─── COMPLETION CLAIM PATTERNS ───────────────────────────────────────────
# These detect when Beth says a domain is done/completed/finished.

_DOMAIN_CLAIM_PATTERNS = {
    'prayer': [
        re.compile(r'prayer\b.{0,40}\b(?:done|complet|finish|wrapped|logged)', re.I),
        re.compile(r'(?:done|complet|finish|wrapped|logged)\b.{0,40}\bprayer\b', re.I),
        re.compile(r'prayer\s+(?:is|has been|was)\s+(?:done|completed|finished)', re.I),
        re.compile(r"you(?:'ve| have)\s+(?:already\s+)?(?:done|completed|finished)\s+(?:your\s+)?prayer", re.I),
    ],
    'bible_reading': [
        re.compile(r'(?:bible|scripture|reading)\b.{0,40}\b(?:done|complet|finish|wrapped|logged)', re.I),
        re.compile(r'(?:done|complet|finish|wrapped|logged)\b.{0,40}\b(?:bible|scripture|reading)\b', re.I),
        re.compile(r'(?:bible|scripture)\s+(?:reading\s+)?(?:is|has been|was)\s+(?:done|completed|finished)', re.I),
        re.compile(r"you(?:'ve| have)\s+(?:already\s+)?(?:done|completed|finished)\s+(?:your\s+)?(?:bible|scripture|reading)", re.I),
    ],
    'workout': [
        re.compile(r'workout\b.{0,40}\b(?:done|complet|finish|wrapped|logged)', re.I),
        re.compile(r'(?:done|complet|finish|wrapped|logged)\b.{0,40}\bworkout\b', re.I),
        re.compile(r'workout\s+(?:is|has been|was)\s+(?:done|completed|finished)', re.I),
    ],
    'journal': [
        re.compile(r'journal\b.{0,40}\b(?:done|complet|finish|wrapped|logged)', re.I),
        re.compile(r'(?:done|complet|finish|wrapped|logged)\b.{0,40}\bjournal\b', re.I),
        re.compile(r'journal(?:ing)?\s+(?:is|has been|was)\s+(?:done|completed|finished)', re.I),
    ],
}

# Combined pattern for "prayer and bible reading" style claims
_COMBINED_CLAIM_PATTERNS = [
    re.compile(
        r'(?:prayer|bible|scripture|reading)\s+(?:and|&)\s+(?:prayer|bible|scripture|reading)'
        r'\b.{0,40}\b(?:done|complet|finish|wrapped)',
        re.I,
    ),
    re.compile(
        r'(?:done|complet|finish|wrapped)\b.{0,40}'
        r'(?:prayer|bible|scripture|reading)\s+(?:and|&)\s+(?:prayer|bible|scripture|reading)',
        re.I,
    ),
]

# ─── FALSE PRAISE PATTERNS ──────────────────────────────────────────────
# These detect when Beth praises when nothing is done.
# Only flagged when completion rate is LOW (< 40%).
_FALSE_PRAISE_PATTERNS = [
    re.compile(r'great\s+start', re.I),
    re.compile(r'off\s+to\s+a\s+(?:great|good|strong|solid)\s+start', re.I),
    re.compile(r'productive\s+(?:day|morning|start)', re.I),
    re.compile(r"you(?:'ve| have)\s+(?:already\s+)?knocked\s+(?:out|off)", re.I),
    re.compile(r'solid\s+(?:day|morning|effort|progress)', re.I),
    re.compile(r'wrapped\s+up\s+(?:your|the)\s+(?:morning|routine)', re.I),
    re.compile(r'strong\s+(?:morning|start|day)', re.I),
    re.compile(r"you(?:'re| are)\s+(?:off to|having)\s+a\s+(?:great|good|solid)", re.I),
    re.compile(r'nice\s+(?:work|job|progress)\s+(?:this|so\s+far)', re.I),
    re.compile(r'well\s+on\s+(?:your|the)\s+way', re.I),
]


def validate_response_truth(response_text, user, allow_regenerate=True):
    """
    Validate that the LLM response doesn't claim completions that aren't real.

    Args:
        response_text: The LLM's generated response
        user: Django User instance
        allow_regenerate: If True (non-streaming), return should_reject=True
            so caller can regenerate. If False (streaming), append correction.

    Returns:
        tuple: (validated_response, violations_found)
        - validated_response: corrected response (or original if no violations)
        - violations_found: list of violation dicts with 'should_reject' flag
    """
    if not response_text:
        return response_text, []

    try:
        from apps.core.execution.today_execution import build_today_execution
        exec_contract = build_today_execution(user)
        exec_summaries = exec_contract.get('summaries', {})
        exec_domains = exec_summaries.get('domains', {})
    except Exception as e:
        logger.warning("CoS truth validator: couldn't get execution data: %s", e)
        return response_text, []

    violations = []

    # Check each domain for false completion claims
    for domain, patterns in _DOMAIN_CLAIM_PATTERNS.items():
        domain_done = exec_domains.get(domain, False)
        if domain_done:
            continue  # Domain IS done, claims are valid

        # Domain is NOT done — check if response claims it is
        for pattern in patterns:
            if pattern.search(response_text):
                violations.append({
                    'domain': domain,
                    'type': 'false_completion',
                    'pattern': pattern.pattern,
                    'actual_status': 'NOT DONE',
                    'claimed_status': 'DONE',
                    'should_reject': allow_regenerate,
                })
                break  # One violation per domain is enough

    # Check combined claims ("prayer and Bible reading have been completed")
    for pattern in _COMBINED_CLAIM_PATTERNS:
        if pattern.search(response_text):
            for domain in ['prayer', 'bible_reading']:
                if not exec_domains.get(domain, False):
                    if not any(v['domain'] == domain for v in violations):
                        violations.append({
                            'domain': domain,
                            'type': 'false_completion_combined',
                            'pattern': 'combined_claim',
                            'actual_status': 'NOT DONE',
                            'claimed_status': 'DONE',
                            'should_reject': allow_regenerate,
                        })

    # Check false praise when completion rate is LOW
    _completion_rate = _compute_completion_rate(exec_summaries, exec_domains)
    if _completion_rate < 40:
        for pattern in _FALSE_PRAISE_PATTERNS:
            if pattern.search(response_text):
                violations.append({
                    'domain': 'tone',
                    'type': 'false_praise',
                    'pattern': pattern.pattern,
                    'actual_status': f'completion_rate={_completion_rate}%',
                    'claimed_status': 'positive_praise',
                    'should_reject': allow_regenerate,
                })
                break  # One praise violation is enough

    if not violations:
        logger.info(
            "[CoS VALIDATOR RUN] user=%s result=PASS — no truth violations",
            user.id,
        )
        return response_text, []

    # Log violations for monitoring
    domain_names = [v['domain'] for v in violations]
    logger.error(
        "[CoS VALIDATOR RUN] user=%s result=FAIL domains=%s types=%s — "
        "Beth fabricated completion or gave false praise. "
        "Execution data contradicts response claims.",
        user.id,
        domain_names,
        [v['type'] for v in violations],
    )

    # For non-streaming path with should_reject: caller will regenerate
    # For streaming path: append correction
    if any(v.get('should_reject') for v in violations):
        # Return violations with should_reject flag — caller handles regeneration
        return response_text, violations

    # Streaming fallback: append correction
    not_done_items = []
    domain_labels = {
        'prayer': 'prayer',
        'bible_reading': 'Bible reading',
        'workout': 'workout',
        'journal': 'journaling',
        'tone': None,  # Don't list tone in correction
    }
    for v in violations:
        label = domain_labels.get(v['domain'])
        if label and label not in not_done_items:
            not_done_items.append(label)

    if not_done_items:
        correction = (
            "\n\n*(Correction: "
            + ", ".join(not_done_items)
            + " "
            + ("is" if len(not_done_items) == 1 else "are")
            + " not yet completed today.)*"
        )
        return response_text + correction, violations

    return response_text, violations


def build_strict_regeneration_prompt(violations, exec_domains):
    """
    Build a strict system prompt suffix for regeneration after a truth violation.

    Used when the non-streaming path rejects a fabricated response and needs
    to regenerate with stronger enforcement.

    Returns:
        str: Additional system prompt instruction
    """
    domain_labels = {
        'prayer': 'prayer',
        'bible_reading': 'Bible reading',
        'workout': 'workout',
        'journal': 'journaling',
    }

    not_done = []
    for domain, done in exec_domains.items():
        if not done and domain in domain_labels:
            not_done.append(domain_labels[domain])

    return (
        "\n\n"
        "CRITICAL CORRECTION — YOUR PREVIOUS RESPONSE WAS REJECTED.\n"
        "You claimed something was completed when it was NOT.\n"
        f"The following are NOT DONE today: {', '.join(not_done)}.\n"
        "DO NOT state or imply these are complete.\n"
        "DO NOT use positive praise language (great start, solid progress, etc).\n"
        "State facts only. What is NOT done must be described as NOT done.\n"
        "Respond again with accurate information."
    )


def _compute_completion_rate(exec_summaries, exec_domains):
    """Compute completion rate from execution data."""
    total = 0
    completed = 0

    # Domain completions
    for domain, done in exec_domains.items():
        if domain in ('journal', 'workout', 'bible_reading', 'prayer'):
            total += 1
            if done:
                completed += 1

    # Routine items
    routines = exec_summaries.get('routines', {})
    for rid, rdata in routines.items():
        total += rdata.get('total_count', 0)
        completed += rdata.get('completed_count', 0)

    # Medication items
    meds = exec_summaries.get('medications', {})
    for wk, ms in meds.items():
        total += ms.get('total', 0)
        completed += ms.get('taken', 0)

    if total == 0:
        return 0
    return round(completed / total * 100)


def log_cos_debug_state(user):
    """
    Log the current execution state for debugging CoS truth issues.
    Called on each response to provide traceability.

    Returns:
        dict with current state for logging
    """
    try:
        from apps.core.execution.today_execution import build_today_execution
        from apps.faith.engagement import get_faith_engagement_details
        from apps.core.utils import get_user_today

        today = get_user_today(user)
        exec_contract = build_today_execution(user)
        exec_domains = exec_contract.get('summaries', {}).get('domains', {})
        faith_details = get_faith_engagement_details(user, today)

        state = {
            'date': str(today),
            'prayer_today': exec_domains.get('prayer', False),
            'bible_today': exec_domains.get('bible_reading', False),
            'journal_today': exec_domains.get('journal', False),
            'workout_today': exec_domains.get('workout', False),
            'faith_engaged_today': faith_details.get('faith_engaged_today', False),
            'reading_completed_today': faith_details.get('reading_completed_today', False),
            'faith_task_completed_today': faith_details.get('faith_task_completed_today', False),
        }

        # Routine completion
        routines = exec_contract.get('summaries', {}).get('routines', {})
        total_routine_items = 0
        completed_routine_items = 0
        for rid, rdata in routines.items():
            total_routine_items += rdata.get('total_count', 0)
            completed_routine_items += rdata.get('completed_count', 0)
        state['routine_items_completed'] = f"{completed_routine_items}/{total_routine_items}"

        # Tasks
        state['tasks_completed_today'] = exec_contract.get(
            'summaries', {},
        ).get('tasks_completed_today', 0)

        logger.info(
            "[CoS DEBUG] user=%s date=%s prayer_today=%s bible_today=%s "
            "journal_today=%s workout_today=%s "
            "routine_items=%s tasks_completed=%s",
            user.id,
            state['date'],
            state['prayer_today'],
            state['bible_today'],
            state['journal_today'],
            state['workout_today'],
            state['routine_items_completed'],
            state['tasks_completed_today'],
        )

        return state

    except Exception as e:
        logger.warning("[CoS DEBUG] Failed to build debug state: %s", e)
        return {}
