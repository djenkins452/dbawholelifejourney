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
        {'key': 'A', 'label': 'Sounds good', 'action': 'confirm', 'style': 'primary'},
        {'key': 'B', 'label': 'Never mind', 'action': 'cancel', 'style': 'secondary'},
        {'key': 'C', 'label': 'Change something', 'action': 'edit', 'style': 'secondary'},
    ]


def _skip_options():
    """Options for a skip (already exists) scenario."""
    return [
        {'key': 'A', 'label': 'Keep it', 'action': 'confirm', 'style': 'primary'},
        {'key': 'B', 'label': 'Never mind', 'action': 'cancel', 'style': 'secondary'},
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
        parts.append('I found a few matches. Which one did you mean?')

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
    parts.append('Pick a number, or say "none of these" to create a new one.')
    return '\n'.join(parts)


# ── Confirmation Message Builder ─────────────────────────────────────

# Human-readable names for intent types.
# Also available via get_policy(intent).label from action_policy,
# but kept here for backward compatibility with direct importers.
INTENT_LABELS = {
    # Creates
    'create_task': 'Adding a task',
    'create_routine_task': 'Adding a daily routine',
    'create_event': 'Adding to your calendar',
    'create_goal': 'Creating a goal',
    'set_intention': 'Setting your intention',
    'add_reminder': 'Setting a reminder',
    'create_journal_entry': 'Saving a journal entry',
    'add_gratitude': 'Noting gratitude',
    'add_faith_milestone': 'Recording a faith milestone',
    'save_verse': 'Saving a verse',
    # Mutations
    'mutate_task': 'Updating your task',
    'mutate_calendar_event': 'Updating your calendar event',
    'complete_task': 'Marking task complete',
    'skip_task': 'Skipping a task',
    'mark_prayer_answered': 'Marking prayer as answered',
    'update_goal_progress': 'Updating goal progress',
    'complete_shopping_item': 'Marking item as purchased',
    'set_cos_name': 'Changing assistant name',
    # Logs
    'log_weight': 'Logging your weight',
    'log_blood_pressure': 'Logging blood pressure',
    'log_heart_rate': 'Logging heart rate',
    'log_glucose': 'Logging blood sugar',
    'log_blood_oxygen': 'Logging blood oxygen',
    'log_body_measurement': 'Logging a measurement',
    'log_food': 'Logging food',
    'log_sleep': 'Logging sleep',
    'log_water': 'Logging water intake',
    'log_steps': 'Logging steps',
    'take_medication': 'Marking medication as taken',
    'take_intake_by_time': 'Marking intakes as taken',
    'start_fast': 'Starting a fast',
    'end_fast': 'Ending your fast',
    'log_prayer': 'Adding a prayer',
    'log_habit': 'Logging a habit',
    'log_workout': 'Logging a workout',
    'log_exercise_set': 'Logging an exercise set',
    'log_cardio': 'Logging cardio',
    'log_transaction': 'Logging a transaction',
    'log_transformation_protocol': 'Logging transformation',
    'log_shopping_item': 'Adding to shopping list',
    # System
    'undo_last_action': 'Undoing last action',
    'edit_last_entry': 'Editing last entry',
    'email_intake_list': 'Emailing intake list',
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

    from_str = _format_time_str(existing_time) if existing_time and existing_time != 'None' else 'unscheduled'

    if new_time:
        parts = [f'Moving {existing_title} from {from_str} to {_format_time_str(new_time)}']
    else:
        parts = [f'Updating {existing_title}']

    parts.append('')
    parts.append('Reply with: CONFIRM, CANCEL, or EDIT')
    return '\n'.join(parts)


def _build_skip_message(recon: ReconciliationResult) -> str:
    """Build message for a proposed skip (existing + same time)."""
    if recon.skip_message:
        return f"{recon.skip_message}\n\nReply with: CONFIRM to keep, or CANCEL"
    matched = recon.matched_object or {}
    title = matched.get('title', 'activity')
    return f'{title} is already scheduled \u2014 no changes needed.\n\nReply with: CONFIRM to keep, or CANCEL'


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
    # Extract key details based on intent type.
    # resolved_name is set by EntityResolver when it matches a database entity.
    title = (
        params.get('resolved_name')
        or params.get('title')
        or params.get('name')
        or params.get('task_query')
        or params.get('task_keyword')
        or ''
    )
    value = params.get('value') or params.get('weight') or params.get('bpm', '')
    time_str = params.get('scheduled_time') or params.get('start_time', '')
    date_str = params.get('due_date') or params.get('start_date') or params.get('date', '')

    # Override label for mutate intents based on actual action (delete vs update)
    action = params.get('action', '')
    if action == 'delete' and intent in ('mutate_task', 'mutate_calendar_event'):
        entity = 'calendar event' if 'calendar' in intent else 'task'
        if params.get('delete_series'):
            label = f'Removing recurring {entity} series'
        else:
            label = f'Removing {entity}'

    # Build conversational summary (no "Proposed Action" heading)
    parts = []
    summary = label
    if title:
        summary += f': "{title}"'
    elif value:
        summary += f': {value}'
    parts.append(summary)

    # Add date/time naturally
    if date_str and time_str:
        parts.append(f'{date_str} at {_format_time_str(time_str)}')
    elif time_str:
        parts.append(f'at {_format_time_str(time_str)}')
    elif date_str:
        parts.append(f'{date_str}')

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
