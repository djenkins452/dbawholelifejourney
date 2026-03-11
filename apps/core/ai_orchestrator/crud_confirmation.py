"""
CRUD Confirmation Gate — deterministic user approval before any write operation.

No write operation executes without explicit user confirmation.
Uses structured option parsing (A/B/C keys) with backward-compatible
command parsing (CONFIRM/CANCEL/EDIT).

Pipeline position:
    Activity Reconciliation → CRUD Confirmation Gate → Execution

Includes:
- Structured A/B/C option generation
- Deterministic response parsing (letter keys + legacy keywords)
- Idempotency protection via UUID action_id
- Confirmation expiry handling (300s TTL)
- Rich confirmation message building
"""

import logging
from typing import Dict, List, Optional, Tuple

from apps.core.ai_orchestrator.activity_reconciliation import (
    ReconciliationDecision,
    ReconciliationResult,
)

logger = logging.getLogger(__name__)


# ── Passthrough / Confirmation (delegated to action_policy) ───────────
# Import from action_policy for the canonical source of truth.
# Keep PASSTHROUGH_INTENTS for backward compat with any direct importers.

from apps.core.ai_orchestrator.action_policy import (  # noqa: E402
    PASSTHROUGH_INTENTS,
    requires_confirmation,
)

# Re-export so existing `from crud_confirmation import requires_confirmation`
# continues to work.
__all__ = [
    'PASSTHROUGH_INTENTS',
    'requires_confirmation',
    'parse_confirmation_response',
    'parse_option_response',
    'parse_disambiguation_response',
    'build_structured_confirmation',
    'build_crud_confirmation_message',
    'build_disambiguation_message',
    'INTENT_LABELS',
]


# ── Standard Option Templates ─────────────────────────────────────────

def _standard_options():
    """Default A/B/C confirmation options."""
    return [
        {'key': 'A', 'label': 'Confirm', 'action': 'confirm', 'style': 'primary'},
        {'key': 'B', 'label': 'Cancel', 'action': 'cancel', 'style': 'secondary'},
        {'key': 'C', 'label': 'Edit', 'action': 'edit', 'style': 'secondary'},
    ]


def _skip_options():
    """Options for a skip (already exists) scenario."""
    return [
        {'key': 'A', 'label': 'Keep as is', 'action': 'confirm', 'style': 'primary'},
        {'key': 'B', 'label': 'Cancel', 'action': 'cancel', 'style': 'secondary'},
    ]


# ── Deterministic Response Parsing ────────────────────────────────────

def parse_confirmation_response(
    response: str,
    options: Optional[List[Dict]] = None,
) -> Optional[str]:
    """
    Parse user response to a confirmation prompt.

    Supports:
    - Letter keys: A, B, C (mapped to options[index].action)
    - Legacy keywords: CONFIRM, YES, CANCEL, NO, EDIT (backward compatible)
    - Case-insensitive, whitespace-tolerant

    Args:
        response: User's raw response text.
        options: Structured options list (from build_structured_confirmation).
                 If None, letter-key parsing is skipped (backward compat).

    Returns:
        'confirm', 'cancel', 'edit', or the option's action string.
        None if unrecognized.
    """
    token = response.strip().upper()

    # ── Letter key parsing (A/B/C) ────────────────────────────
    # Only when structured options are available.
    if options and len(token) == 1 and token.isalpha():
        idx = ord(token) - ord('A')
        if 0 <= idx < len(options):
            action = options[idx].get('action', 'confirm')
            logger.info(
                "[CRUD_GATE] Option key %s → action %s",
                token, action,
            )
            return action

    # ── Legacy keyword parsing (backward compatible) ──────────
    if token.startswith('CONFIRM') or token in ('YES', 'Y'):
        return 'confirm'

    if token.startswith('CANCEL') or token in ('NO', 'N'):
        return 'cancel'

    if (token.startswith('EDIT')
            or token.startswith('MODIFY')
            or token.startswith('CHANGE')):
        return 'edit'

    return None


def parse_option_response(
    response: str,
    options: List[Dict],
) -> Optional[str]:
    """
    Parse a response against a specific set of options.

    Unlike parse_confirmation_response, this ONLY handles structured options
    (no legacy keyword fallback). Use for custom A/B/C flows like
    "this instance vs entire series".

    Returns:
        The matching option's 'action' value, or None.
    """
    token = response.strip().upper()

    # Single letter key
    if len(token) == 1 and token.isalpha():
        idx = ord(token) - ord('A')
        if 0 <= idx < len(options):
            return options[idx].get('action', options[idx].get('value'))

    # Match by label (case-insensitive, for accessibility)
    for opt in options:
        if token == opt.get('label', '').upper():
            return opt.get('action', opt.get('value'))

    return None


# ── Disambiguation Response Parsing ──────────────────────────────────

def parse_disambiguation_response(response: str, num_candidates: int) -> Optional[dict]:
    """
    Parse user response to a disambiguation prompt.

    Returns:
        {'action': 'select', 'index': int}   — user picked a number (0-based)
        {'action': 'cancel'}                  — user wants to cancel
        {'action': 'create_new'}              — user wants to create a new one instead
        None                                  — unrecognized response
    """
    token = response.strip().upper()

    # Cancel
    if token.startswith('CANCEL') or token in ('NO', 'N'):
        return {'action': 'cancel'}

    # "None of these" / create new
    if token in ('NONE', 'NEW', 'CREATE NEW', 'NONE OF THESE', 'CREATE'):
        return {'action': 'create_new'}

    # Numeric selection (strip leading # if present)
    cleaned = response.strip().lstrip('#').strip()
    if cleaned.isdigit():
        num = int(cleaned)
        if 1 <= num <= num_candidates:
            return {'action': 'select', 'index': num - 1}
        return None  # Out of range

    # Ordinal selection
    ordinals = {
        'FIRST': 1, 'SECOND': 2, 'THIRD': 3, 'FOURTH': 4, 'FIFTH': 5,
        'THE FIRST ONE': 1, 'THE SECOND ONE': 2, 'THE THIRD ONE': 3,
        'THE FOURTH ONE': 4, 'THE FIFTH ONE': 5,
        'THE FIRST': 1, 'THE SECOND': 2, 'THE THIRD': 3,
    }
    ordinal = ordinals.get(token)
    if ordinal and 1 <= ordinal <= num_candidates:
        return {'action': 'select', 'index': ordinal - 1}

    return None


# ── Disambiguation Message Builder ───────────────────────────────────

def build_disambiguation_message(recon: ReconciliationResult) -> str:
    """Build a numbered disambiguation prompt with title + time for each candidate."""
    parts = []
    if recon.confirm_message:
        parts.append(recon.confirm_message)
    else:
        parts.append('I found multiple matches. Which one did you mean?')

    parts.append('')
    for i, c in enumerate(recon.candidates[:5]):
        line = f"  {i + 1}. {c.get('title', '?')}"
        time_val = c.get('time')
        if time_val:
            line += f" ({time_val})"
        due = c.get('due_date')
        if due and due != 'None':
            line += f" [due {due}]"
        parts.append(line)

    parts.append('')
    parts.append('Reply with a number, NONE to create new, or CANCEL')
    return '\n'.join(parts)


# ── Confirmation Message Builder ─────────────────────────────────────

# Human-readable names for intent types.
# Also available via get_policy(intent).label from action_policy,
# but kept here for backward compatibility with direct importers.
INTENT_LABELS = {
    # Creates
    'create_task': 'Create task',
    'create_routine_task': 'Create routine task',
    'create_event': 'Create calendar event',
    'create_goal': 'Create goal',
    'set_intention': 'Set intention',
    'add_reminder': 'Add reminder',
    'create_journal_entry': 'Create journal entry',
    'add_gratitude': 'Log gratitude',
    'add_faith_milestone': 'Add faith milestone',
    'save_verse': 'Save verse',
    # Mutations
    'mutate_task': 'Update task',
    'mutate_calendar_event': 'Update calendar event',
    'complete_task': 'Complete task',
    'skip_task': 'Skip task',
    'mark_prayer_answered': 'Mark prayer answered',
    'update_goal_progress': 'Update goal progress',
    'complete_shopping_item': 'Mark shopping item purchased',
    'set_cos_name': 'Change assistant name',
    # Logs
    'log_weight': 'Log weight',
    'log_blood_pressure': 'Log blood pressure',
    'log_heart_rate': 'Log heart rate',
    'log_glucose': 'Log blood sugar',
    'log_blood_oxygen': 'Log blood oxygen',
    'log_body_measurement': 'Log body measurement',
    'log_food': 'Log food',
    'log_sleep': 'Log sleep',
    'log_water': 'Log water intake',
    'log_steps': 'Log steps',
    'take_medicine': 'Mark medicine taken',
    'take_medicines_by_time': 'Mark medicines taken',
    'start_fast': 'Start fast',
    'end_fast': 'End fast',
    'log_prayer': 'Log prayer',
    'log_habit': 'Log habit',
    'log_workout': 'Log workout',
    'log_exercise_set': 'Log exercise set',
    'log_cardio': 'Log cardio session',
    'log_transaction': 'Log transaction',
    'log_transformation_protocol': 'Log transformation',
    'log_shopping_item': 'Add shopping item',
    # System
    'undo_last_action': 'Undo last action',
    'edit_last_entry': 'Edit last entry',
    'email_medicine_list': 'Email medicine list',
}


# ── Structured Confirmation Builder ──────────────────────────────────

def build_structured_confirmation(
    enriched_action,
    recon_result: Optional[ReconciliationResult] = None,
    decision_suggestion: Optional[Dict] = None,
) -> Tuple[str, List[Dict]]:
    """
    Build both text message and structured A/B/C options.

    Returns:
        (message_text, options_list)

    The options_list contains dicts with:
        key: 'A', 'B', 'C', etc.
        label: Human-readable label
        action: Backend action string ('confirm', 'cancel', 'edit', etc.)
        style: 'primary' or 'secondary'
        is_suggested: True if decision memory suggests this option
    """
    text = build_crud_confirmation_message(enriched_action, recon_result)

    # Determine options based on reconciliation type
    if recon_result and recon_result.decision == ReconciliationDecision.SKIP:
        options = _skip_options()
    else:
        options = _standard_options()

    # Apply decision suggestion: reorder so suggested option is first
    if decision_suggestion and decision_suggestion.get('suggested_action'):
        suggested = decision_suggestion['suggested_action']
        for opt in options:
            if opt['action'] == suggested:
                opt['is_suggested'] = True
                break

    # Replace the "Reply with: CONFIRM, CANCEL, or EDIT" line with A/B/C format
    option_labels = ' / '.join(
        f"{opt['key']}) {opt['label']}" for opt in options
    )
    # Replace last line of text
    lines = text.split('\n')
    # Find and replace the "Reply with:" line
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].startswith('Reply with:'):
            lines[i] = option_labels
            break
    else:
        # No "Reply with:" found — append options
        lines.append('')
        lines.append(option_labels)

    text = '\n'.join(lines)
    return text, options


def build_crud_confirmation_message(
    enriched_action,
    recon_result: Optional[ReconciliationResult] = None,
) -> str:
    """
    Build a rich confirmation message for the user.

    The message varies based on whether reconciliation detected
    an existing match (reschedule/skip) or not (new create/log).

    Args:
        enriched_action: EnrichedAction to describe
        recon_result: ReconciliationResult from Layer 1 (optional)

    Returns:
        Formatted confirmation message string
    """
    intent = enriched_action.intent_type
    params = enriched_action.parameters
    label = INTENT_LABELS.get(intent, intent.replace('_', ' ').title())

    # Handle reconciliation-informed messages
    if recon_result and recon_result.decision == ReconciliationDecision.RESCHEDULE:
        return _build_reschedule_message(recon_result, params)

    if recon_result and recon_result.decision == ReconciliationDecision.SKIP:
        return _build_skip_message(recon_result)

    if recon_result and recon_result.decision == ReconciliationDecision.CONFIRM:
        return _build_confirm_ambiguous_message(recon_result, label, params)

    if recon_result and recon_result.decision == ReconciliationDecision.DISAMBIGUATE:
        return build_disambiguation_message(recon_result)

    # Standard create/log/mutate confirmation
    return _build_standard_message(intent, label, params)


def _build_reschedule_message(recon: ReconciliationResult, params: dict) -> str:
    """Build message for a proposed reschedule."""
    matched = recon.matched_object or {}
    existing_title = matched.get('title', 'activity')
    existing_time = matched.get('time')

    new_time = params.get('scheduled_time') or params.get('start_time') or params.get('new_scheduled_time')

    parts = [f'I found an existing "{existing_title}"']
    if existing_time and existing_time != 'None':
        parts[0] += f' scheduled at {_format_time_str(existing_time)}'
    parts[0] += '.'

    if new_time:
        parts.append(f'You mentioned doing it at {_format_time_str(new_time)}.')
        parts.append('')
        parts.append('Proposed Action')
        parts.append(f'Move "{existing_title}"')
        parts.append(f'From: {_format_time_str(existing_time) if existing_time and existing_time != "None" else "unscheduled"}')
        parts.append(f'To: {_format_time_str(new_time)}')
    else:
        parts.append('')
        parts.append('Proposed Action')
        parts.append(f'Update "{existing_title}"')

    parts.append('')
    parts.append('Reply with: CONFIRM, CANCEL, or EDIT')
    return '\n'.join(parts)


def _build_skip_message(recon: ReconciliationResult) -> str:
    """Build message for a proposed skip (existing + same time)."""
    if recon.skip_message:
        return f"{recon.skip_message}\n\nReply with: CONFIRM to keep, or CANCEL"
    matched = recon.matched_object or {}
    title = matched.get('title', 'activity')
    return f'You already have "{title}" scheduled. No changes needed.\n\nReply with: CONFIRM to keep, or CANCEL'


def _build_confirm_ambiguous_message(
    recon: ReconciliationResult, label: str, params: dict,
) -> str:
    """Build message for an ambiguous match requiring disambiguation."""
    if recon.confirm_message:
        msg = recon.confirm_message
    else:
        matched = recon.matched_object or {}
        title = matched.get('title', 'activity')
        msg = f'I found a possible match: "{title}". Is this what you meant?'

    if recon.candidates:
        numbered = [f"  {i + 1}. {c.get('title', '?')}" for i, c in enumerate(recon.candidates[:5])]
        msg += '\n' + '\n'.join(numbered)

    msg += '\n\nReply with: CONFIRM, CANCEL, or EDIT'
    return msg


def _build_standard_message(intent: str, label: str, params: dict) -> str:
    """Build standard confirmation for new create/log/mutate actions."""
    parts = ['Proposed Action']

    # Extract key details based on intent type
    title = params.get('title') or params.get('name') or params.get('task_query', '')
    value = params.get('value') or params.get('weight') or params.get('bpm', '')
    time_str = params.get('scheduled_time') or params.get('start_time', '')
    date_str = params.get('due_date') or params.get('start_date') or params.get('date', '')

    # Override label for mutate intents based on actual action (delete vs update)
    action = params.get('action', '')
    if action == 'delete' and intent in ('mutate_task', 'mutate_calendar_event'):
        entity = 'calendar event' if 'calendar' in intent else 'task'
        if params.get('delete_series'):
            label = f'Delete recurring {entity} series'
        else:
            label = f'Delete {entity}'

    detail_parts = [label]
    if title:
        detail_parts[0] += f': "{title}"'
    elif value:
        detail_parts[0] += f': {value}'

    if date_str:
        detail_parts.append(f'Date: {date_str}')
    if time_str:
        detail_parts.append(f'Time: {_format_time_str(time_str)}')

    parts.extend(detail_parts)
    parts.append('')
    parts.append('Reply with: CONFIRM, CANCEL, or EDIT')
    return '\n'.join(parts)


def _format_time_str(time_val) -> str:
    """Format a time value for display."""
    if not time_val or str(time_val) == 'None':
        return 'unscheduled'

    time_str = str(time_val)

    # Handle HH:MM format
    if ':' in time_str and len(time_str) <= 8:
        try:
            from datetime import datetime as dt
            # Try HH:MM
            t = dt.strptime(time_str[:5], '%H:%M').time()
            return t.strftime('%I:%M %p').lstrip('0')
        except (ValueError, TypeError):
            pass

    return time_str
