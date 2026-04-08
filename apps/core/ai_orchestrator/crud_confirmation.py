"""
CRUD Confirmation Gate — deterministic user approval before any write operation.

No write operation executes without explicit user confirmation.
Uses structured option parsing (A/B/C keys) with backward-compatible
command parsing (CONFIRM/CANCEL/EDIT).

Pipeline position:
    Activity Reconciliation → CRUD Confirmation Gate → Execution

Phase 6.6 — Explicit Confirmation UX:
- Action / Details / Impact structured format (mandatory)
- Before → After field lines for updates
- Specific impact statements with magnitude
- Task-class awareness (critical / foundational / flexible)
- Hard block on incomplete confirmations (raises IncompleteConfirmationError)
- Always emits structured A/B/C pill options
"""

import logging
from typing import Dict, List, Optional, Tuple

from apps.core.ai_orchestrator.activity_reconciliation import (
    ReconciliationDecision,
    ReconciliationResult,
)

logger = logging.getLogger(__name__)


# ── Passthrough / Confirmation (delegated to action_policy) ───────────
from apps.core.ai_orchestrator.action_policy import (  # noqa: E402
    PASSTHROUGH_INTENTS,
    requires_confirmation,
)

__all__ = [
    'PASSTHROUGH_INTENTS',
    'requires_confirmation',
    'parse_confirmation_response',
    'parse_option_response',
    'parse_disambiguation_response',
    'build_structured_confirmation',
    'build_crud_confirmation_message',
    'build_disambiguation_message',
    'IncompleteConfirmationError',
    'INTENT_LABELS',
]


# ── Hard block: incomplete confirmations ─────────────────────────────

class IncompleteConfirmationError(Exception):
    """
    Raised when a confirmation cannot be rendered because required
    fields are missing. The orchestrator must fall back to clarification,
    never render a vague confirmation.
    """

    def __init__(self, intent_type: str, missing_fields: List[str]):
        self.intent_type = intent_type
        self.missing_fields = missing_fields
        super().__init__(
            f"Incomplete confirmation for {intent_type}: "
            f"missing {', '.join(missing_fields)}"
        )


# Per-intent required fields. If any are missing (empty/None), we refuse
# to render a confirmation and force a clarification round-trip instead.
REQUIRED_FIELDS: Dict[str, List[str]] = {
    # Tasks / calendar
    'create_task': ['title'],
    'create_routine_task': ['title'],
    'create_event': ['title'],
    'add_reminder': ['title'],
    'mutate_task': ['_target'],           # must resolve target entity
    'mutate_calendar_event': ['_target'],
    'complete_task': ['_target'],
    'skip_task': ['_target'],
    # Logs — must have a value
    'log_weight': ['_value'],
    'log_blood_pressure': ['_value'],
    'log_heart_rate': ['_value'],
    'log_glucose': ['_value'],
    'log_blood_oxygen': ['_value'],
    'log_body_measurement': ['_value'],
    'log_water': ['_value'],
    'log_steps': ['_value'],
    # Content
    'create_journal_entry': ['_content'],
    'add_gratitude': ['_content'],
    'log_prayer': ['_content'],
    'save_verse': ['_content'],
}


def _field_is_present(params: dict, field: str) -> bool:
    """
    Check whether a required field is present and non-empty.

    Special virtual fields:
        _target — target entity resolved (resolved_name/title/task_query)
        _value  — any numeric/text value present
        _content — journal/prayer/gratitude content
    """
    if field == '_target':
        return bool(
            params.get('resolved_name')
            or params.get('title')
            or params.get('name')
            or params.get('task_query')
            or params.get('task_keyword')
            or params.get('event_id')
            or params.get('task_id')
        )
    if field == '_value':
        for key in (
            'value', 'weight', 'bpm', 'systolic', 'diastolic',
            'glucose', 'spo2', 'oxygen', 'amount', 'ounces',
            'steps', 'measurement', 'reading',
        ):
            v = params.get(key)
            if v not in (None, '', 0):
                return True
        return False
    if field == '_content':
        for key in ('content', 'text', 'body', 'entry', 'note', 'prayer'):
            v = params.get(key)
            if v not in (None, ''):
                return True
        return False
    v = params.get(field)
    return v not in (None, '')


def _validate_required_fields(intent_type: str, params: dict) -> None:
    """Raise IncompleteConfirmationError if required fields are missing."""
    required = REQUIRED_FIELDS.get(intent_type, [])
    missing = [f for f in required if not _field_is_present(params, f)]
    if missing:
        raise IncompleteConfirmationError(intent_type, missing)


# ── Standard Option Templates ─────────────────────────────────────────
# All CRUD confirmations use A·Confirm / B·Edit / C·Cancel with explicit
# styles so the frontend can render pill-primary/secondary/danger buttons.

def _standard_options():
    """Default A/B/C confirmation options (spec: Confirm, Edit, Cancel)."""
    return [
        {
            'key': 'A', 'label': 'Confirm',
            'action': 'confirm', 'style': 'primary',
        },
        {
            'key': 'B', 'label': 'Edit',
            'action': 'edit', 'style': 'secondary',
        },
        {
            'key': 'C', 'label': 'Cancel',
            'action': 'cancel', 'style': 'danger',
        },
    ]


def _skip_options():
    """Options for a skip (already exists) scenario."""
    return [
        {
            'key': 'A', 'label': 'Keep it',
            'action': 'confirm', 'style': 'primary',
        },
        {
            'key': 'B', 'label': 'Cancel',
            'action': 'cancel', 'style': 'danger',
        },
    ]


# ── Deterministic Response Parsing ────────────────────────────────────

# Natural-language vocabulary → canonical action.
# Phase 6.6: users may click a pill, type "A"/"B"/"C", or type natural
# language like "yes", "edit", "cancel".
_CONFIRM_WORDS = frozenset({
    'CONFIRM', 'YES', 'Y', 'YEP', 'YEAH', 'OK', 'OKAY', 'SURE',
    'GO', 'DO IT', 'SOUNDS GOOD',
})
_CANCEL_WORDS = frozenset({
    'CANCEL', 'NO', 'N', 'NOPE', 'STOP', 'NEVER MIND', 'NEVERMIND',
    'FORGET IT', 'ABORT',
})
_EDIT_WORDS = frozenset({
    'EDIT', 'MODIFY', 'CHANGE', 'UPDATE', 'FIX', 'ADJUST',
})


def parse_confirmation_response(
    response: str,
    options: Optional[List[Dict]] = None,
) -> Optional[str]:
    """
    Parse user response to a confirmation prompt.

    Supports:
    - Letter keys: A, B, C (mapped to options[index].action)
    - Legacy keywords: CONFIRM, YES, CANCEL, NO, EDIT
    - Natural language: yes, no, edit, change, cancel, stop, ...
    - Case-insensitive, whitespace-tolerant

    Returns:
        'confirm', 'cancel', 'edit', or None if unrecognized.
    """
    token = response.strip().upper()
    if not token:
        return None

    # ── Letter key parsing (A/B/C) ────────────────────────────
    if options and len(token) == 1 and token.isalpha():
        idx = ord(token) - ord('A')
        if 0 <= idx < len(options):
            action = options[idx].get('action', 'confirm')
            logger.info(
                "[CRUD_GATE] Option key %s → action %s",
                token, action,
            )
            return action

    # ── Exact-word natural language ───────────────────────────
    if token in _CONFIRM_WORDS:
        return 'confirm'
    if token in _CANCEL_WORDS:
        return 'cancel'
    if token in _EDIT_WORDS:
        return 'edit'

    # ── Legacy keyword prefix parsing (backward compatible) ──
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
    """
    token = response.strip().upper()

    if len(token) == 1 and token.isalpha():
        idx = ord(token) - ord('A')
        if 0 <= idx < len(options):
            return options[idx].get('action', options[idx].get('value'))

    for opt in options:
        if token == opt.get('label', '').upper():
            return opt.get('action', opt.get('value'))

    return None


# ── Disambiguation Response Parsing ──────────────────────────────────

def parse_disambiguation_response(response: str, num_candidates: int) -> Optional[dict]:
    """Parse user response to a disambiguation prompt."""
    token = response.strip().upper()

    if token.startswith('CANCEL') or token in ('NO', 'N'):
        return {'action': 'cancel'}

    if token in ('NONE', 'NEW', 'CREATE NEW', 'NONE OF THESE', 'CREATE'):
        return {'action': 'create_new'}

    cleaned = response.strip().lstrip('#').strip()
    if cleaned.isdigit():
        num = int(cleaned)
        if 1 <= num <= num_candidates:
            return {'action': 'select', 'index': num - 1}
        return None

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
    """Build a numbered disambiguation prompt."""
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


# ── Intent Labels ────────────────────────────────────────────────────

INTENT_LABELS = {
    # Creates
    'create_task': 'Create task',
    'create_routine_task': 'Create daily routine',
    'create_event': 'Create calendar event',
    'create_goal': 'Create goal',
    'set_intention': 'Set intention',
    'add_reminder': 'Set reminder',
    'create_journal_entry': 'Save journal entry',
    'add_gratitude': 'Note gratitude',
    'add_faith_milestone': 'Record faith milestone',
    'save_verse': 'Save verse',
    # Mutations
    'mutate_task': 'Update task',
    'mutate_calendar_event': 'Update calendar event',
    'complete_task': 'Mark task complete',
    'skip_task': 'Skip task',
    'mark_prayer_answered': 'Mark prayer answered',
    'update_goal_progress': 'Update goal progress',
    'complete_shopping_item': 'Mark item purchased',
    'set_cos_name': 'Change assistant name',
    # Logs
    'log_weight': 'Log weight',
    'log_blood_pressure': 'Log blood pressure',
    'log_heart_rate': 'Log heart rate',
    'log_glucose': 'Log blood sugar',
    'log_blood_oxygen': 'Log blood oxygen',
    'log_body_measurement': 'Log measurement',
    'log_food': 'Log food',
    'log_sleep': 'Log sleep',
    'log_water': 'Log water',
    'log_steps': 'Log steps',
    'take_medication': 'Mark medication taken',
    'take_intake_by_time': 'Mark intakes taken',
    'start_fast': 'Start fast',
    'end_fast': 'End fast',
    'log_prayer': 'Add prayer',
    'log_habit': 'Log habit',
    'log_workout': 'Log workout',
    'log_exercise_set': 'Log exercise set',
    'log_cardio': 'Log cardio',
    'log_transaction': 'Log transaction',
    'log_transformation_protocol': 'Log transformation',
    'log_shopping_item': 'Add to shopping list',
    # System
    'undo_last_action': 'Undo last action',
    'edit_last_entry': 'Edit last entry',
    'email_intake_list': 'Email intake list',
}


# ── Task-class awareness helpers ─────────────────────────────────────

def _extract_task_class(params: dict, recon: Optional[ReconciliationResult]) -> Optional[str]:
    """
    Extract the task class from intent params or reconciled entity.

    Returns one of: 'critical', 'foundational', 'flexible', or None.
    Maps commitment levels → task class:
        non_negotiable / critical → critical
        foundational               → foundational
        important / flexible       → flexible (default standard)
    """
    candidates = [
        params.get('task_class'),
        params.get('commitment_level'),
        params.get('importance'),
        params.get('priority'),
    ]
    if recon and recon.matched_object:
        candidates.append(recon.matched_object.get('commitment_level'))
        candidates.append(recon.matched_object.get('importance'))

    for raw in candidates:
        if not raw:
            continue
        val = str(raw).strip().lower()
        if val in ('critical', 'non_negotiable', 'non-negotiable'):
            return 'critical'
        if val == 'foundational':
            return 'foundational'
        if val in ('flexible', 'important', 'optional'):
            return 'flexible'
    return None


def _task_class_warning(task_class: Optional[str]) -> Optional[str]:
    """Return a warning line to append to the impact section."""
    if task_class == 'critical':
        return "⚠ Time-sensitive — this is a CRITICAL item."
    if task_class == 'foundational':
        return "Must complete today — this is a FOUNDATIONAL commitment."
    return None


# ── Structured Confirmation Builder ──────────────────────────────────

def build_structured_confirmation(
    enriched_action,
    recon_result: Optional[ReconciliationResult] = None,
    decision_suggestion: Optional[Dict] = None,
) -> Tuple[str, List[Dict]]:
    """
    Build the explicit confirmation message and A/B/C options.

    Returns:
        (message_text, options_list)

    Raises:
        IncompleteConfirmationError — if required fields are missing.
        The orchestrator must catch this and fall back to clarification.
    """
    # Hard block: refuse to render a vague confirmation.
    _validate_required_fields(enriched_action.intent_type, enriched_action.parameters)

    text = build_crud_confirmation_message(enriched_action, recon_result)

    # Determine options based on reconciliation type
    if recon_result and recon_result.decision == ReconciliationDecision.SKIP:
        options = _skip_options()
    else:
        options = _standard_options()

    # Apply decision suggestion: mark suggested option
    if decision_suggestion and decision_suggestion.get('suggested_action'):
        suggested = decision_suggestion['suggested_action']
        for opt in options:
            if opt['action'] == suggested:
                opt['is_suggested'] = True
                break

    return text, options


def build_crud_confirmation_message(
    enriched_action,
    recon_result: Optional[ReconciliationResult] = None,
) -> str:
    """
    Build the explicit confirmation message (Action / Details / Impact).

    Never includes legacy "Reply with: CONFIRM, CANCEL, or EDIT" instructions
    — the frontend renders A/B/C pills and the option labels appear in the
    AssistantMessage.quick_replies JSON.
    """
    intent = enriched_action.intent_type
    params = enriched_action.parameters
    label = INTENT_LABELS.get(intent, intent.replace('_', ' ').title())
    task_class = _extract_task_class(params, recon_result)

    # Reconciliation-informed messages
    if recon_result and recon_result.decision == ReconciliationDecision.RESCHEDULE:
        return _build_reschedule_message(recon_result, params, task_class)

    if recon_result and recon_result.decision == ReconciliationDecision.SKIP:
        return _build_skip_message(recon_result)

    if recon_result and recon_result.decision == ReconciliationDecision.CONFIRM:
        return _build_confirm_ambiguous_message(recon_result, label, params)

    if recon_result and recon_result.decision == ReconciliationDecision.DISAMBIGUATE:
        return build_disambiguation_message(recon_result)

    # Standard create/log/mutate confirmation
    is_delete = params.get('action') == 'delete' and intent in (
        'mutate_task', 'mutate_calendar_event',
    )
    is_update = intent in (
        'mutate_task', 'mutate_calendar_event', 'update_goal_progress',
    ) and not is_delete

    if is_delete:
        return _build_delete_message(intent, params, task_class)
    if is_update:
        return _build_update_message(intent, label, params, recon_result, task_class)
    return _build_create_message(intent, label, params, task_class)


# ── Field formatting ─────────────────────────────────────────────────

def _bullet(lines: List[str]) -> List[str]:
    return [f"• {line}" for line in lines]


def _get_title(params: dict) -> str:
    return (
        params.get('resolved_name')
        or params.get('title')
        or params.get('name')
        or params.get('task_query')
        or params.get('task_keyword')
        or ''
    )


def _format_time_str(time_val) -> str:
    """Format a time value (HH:MM or string) for display."""
    if not time_val or str(time_val) == 'None':
        return 'unscheduled'
    time_str = str(time_val)
    if ':' in time_str and len(time_str) <= 8:
        try:
            from datetime import datetime as dt
            t = dt.strptime(time_str[:5], '%H:%M').time()
            return t.strftime('%I:%M %p').lstrip('0')
        except (ValueError, TypeError):
            pass
    return time_str


def _format_date_str(date_val) -> str:
    if not date_val or str(date_val) == 'None':
        return ''
    return str(date_val)


def _format_value(key: str, value) -> str:
    """Format a numeric/text value with appropriate units."""
    if value in (None, ''):
        return ''
    units = {
        'weight': 'lbs',
        'bpm': 'bpm',
        'heart_rate': 'bpm',
        'glucose': 'mg/dL',
        'spo2': '%',
        'oxygen': '%',
        'water': 'oz',
        'ounces': 'oz',
        'steps': 'steps',
        'systolic': '',
        'diastolic': '',
    }
    unit = units.get(key, '')
    return f"{value} {unit}".strip()


def _create_field_lines(intent: str, params: dict) -> List[str]:
    """Extract field → value lines for a create/log action."""
    lines = []
    title = _get_title(params)
    if title:
        lines.append(f"Title → {title}")

    date_str = _format_date_str(
        params.get('due_date') or params.get('start_date') or params.get('date'),
    )
    if date_str:
        lines.append(f"Day → {date_str}")

    time_str = params.get('scheduled_time') or params.get('start_time')
    if time_str:
        lines.append(f"Time → {_format_time_str(time_str)}")

    end_time = params.get('end_time') or params.get('scheduled_end_time')
    if end_time:
        lines.append(f"End → {_format_time_str(end_time)}")

    if params.get('is_recurring') or params.get('recurrence'):
        rec = params.get('recurrence') or 'weekly'
        lines.append(f"Repeats → {rec}")

    # Log values
    for key, field_label in [
        ('weight', 'Weight'),
        ('bpm', 'Heart rate'),
        ('heart_rate', 'Heart rate'),
        ('glucose', 'Glucose'),
        ('spo2', 'SpO₂'),
        ('water', 'Water'),
        ('steps', 'Steps'),
    ]:
        if params.get(key) not in (None, ''):
            lines.append(f"{field_label} → {_format_value(key, params[key])}")

    systolic = params.get('systolic')
    diastolic = params.get('diastolic')
    if systolic and diastolic:
        lines.append(f"Blood pressure → {systolic}/{diastolic}")

    for key, field_label in [
        ('category', 'Category'),
        ('priority', 'Priority'),
        ('domain', 'Domain'),
        ('notes', 'Notes'),
    ]:
        v = params.get(key)
        if v:
            lines.append(f"{field_label} → {v}")

    return lines


def _update_field_lines(
    intent: str, params: dict, recon: Optional[ReconciliationResult],
) -> Tuple[List[str], List[str]]:
    """
    Build Before/After field lines for an update action.

    Returns:
        (before_lines, after_lines) — each a list of "Field → value" strings.
    """
    matched = (recon.matched_object if recon else None) or {}

    field_map = [
        # (param key, old key from matched_object, display label, formatter)
        ('title', 'title', 'Title', str),
        ('scheduled_time', 'time', 'Time', _format_time_str),
        ('start_time', 'time', 'Time', _format_time_str),
        ('new_scheduled_time', 'time', 'Time', _format_time_str),
        ('end_time', 'end_time', 'End', _format_time_str),
        ('due_date', 'due_date', 'Day', _format_date_str),
        ('start_date', 'start_date', 'Day', _format_date_str),
        ('date', 'date', 'Day', _format_date_str),
        ('priority', 'priority', 'Priority', str),
        ('category', 'category', 'Category', str),
        ('notes', 'notes', 'Notes', str),
        ('progress', 'progress', 'Progress', str),
    ]

    seen_labels = set()
    before = []
    after = []
    for new_key, old_key, display, formatter in field_map:
        new_val = params.get(new_key)
        if new_val in (None, ''):
            continue
        if display in seen_labels:
            continue
        old_val = matched.get(old_key)
        new_fmt = formatter(new_val)
        old_fmt = formatter(old_val) if old_val not in (None, '') else '—'
        if new_fmt == old_fmt:
            continue
        before.append(f"{display} → {old_fmt}")
        after.append(f"{display} → {new_fmt}")
        seen_labels.add(display)

    return before, after


# ── Impact helpers ───────────────────────────────────────────────────

def _create_impact(intent: str, params: dict) -> str:
    """Specific impact line for create actions."""
    if params.get('is_recurring') or params.get('recurrence'):
        rec = params.get('recurrence') or 'recurring'
        return f"Adds a new {rec} entry to your calendar."
    if intent == 'create_event':
        return "Adds a new event to your calendar."
    if intent in ('create_task', 'create_routine_task', 'add_reminder'):
        return "Adds a new task to your list."
    if intent.startswith('log_') or intent == 'take_medication':
        return "Adds a new log entry to your history."
    if intent == 'create_goal':
        return "Creates a new goal you'll track going forward."
    if intent == 'create_journal_entry':
        return "Saves a new journal entry."
    return "Creates a new entry."


def _update_impact(
    intent: str, params: dict, recon: Optional[ReconciliationResult],
) -> str:
    """Specific impact line for update actions, including magnitude."""
    matched = (recon.matched_object if recon else None) or {}
    old_time = matched.get('time')
    new_time = (
        params.get('scheduled_time')
        or params.get('start_time')
        or params.get('new_scheduled_time')
    )
    if old_time and new_time and old_time != new_time:
        delta = _time_delta_str(old_time, new_time)
        if delta:
            return f"Moves this {_entity_word(intent)} {delta}."

    if params.get('recurrence') or params.get('is_recurring'):
        return f"Updates the recurring {_entity_word(intent)} series."

    changed = [k for k in ('title', 'priority', 'category', 'notes') if params.get(k)]
    if changed:
        return (
            f"Updates {', '.join(changed)} on this {_entity_word(intent)}."
        )
    return f"Updates this {_entity_word(intent)}."


def _entity_word(intent: str) -> str:
    if 'calendar' in intent or intent == 'create_event':
        return 'event'
    if 'goal' in intent:
        return 'goal'
    return 'task'


def _time_delta_str(old_time, new_time) -> Optional[str]:
    """Return a human delta like '+1 hour later' or '30 minutes earlier'."""
    try:
        from datetime import datetime as dt
        o = dt.strptime(str(old_time)[:5], '%H:%M')
        n = dt.strptime(str(new_time)[:5], '%H:%M')
        delta_min = int((n - o).total_seconds() / 60)
        if delta_min == 0:
            return None
        direction = 'later' if delta_min > 0 else 'earlier'
        minutes = abs(delta_min)
        if minutes % 60 == 0:
            hours = minutes // 60
            unit = 'hour' if hours == 1 else 'hours'
            return f"{hours} {unit} {direction}"
        return f"{minutes} minutes {direction}"
    except (ValueError, TypeError):
        return None


def _delete_impact(intent: str, params: dict) -> str:
    entity = _entity_word(intent)
    if params.get('delete_series'):
        return f"Removes the entire recurring {entity} series — this cannot be undone."
    return f"Permanently removes this {entity}."


# ── Message builders (Action / Details / Impact) ─────────────────────

def _compose(action_line: str, detail_lines: List[str], impact_line: str) -> str:
    """Compose the explicit Action / Details / Impact block."""
    parts = [f"Action: {action_line}", ""]
    if detail_lines:
        parts.append("Details:")
        parts.extend(_bullet(detail_lines))
        parts.append("")
    parts.append(f"Impact: {impact_line}")
    return '\n'.join(parts)


def _compose_update(
    action_line: str,
    before: List[str],
    after: List[str],
    impact_line: str,
) -> str:
    parts = [f"Action: {action_line}", ""]
    if before or after:
        parts.append("Before:")
        parts.extend(_bullet(before or ['—']))
        parts.append("")
        parts.append("After:")
        parts.extend(_bullet(after or ['—']))
        parts.append("")
    parts.append(f"Impact: {impact_line}")
    return '\n'.join(parts)


def _append_task_class(msg: str, task_class: Optional[str]) -> str:
    warning = _task_class_warning(task_class)
    if warning:
        return f"{msg}\n{warning}"
    return msg


def _build_create_message(
    intent: str, label: str, params: dict, task_class: Optional[str],
) -> str:
    title = _get_title(params)
    action_line = f"{label}" + (f': "{title}"' if title else '')
    detail_lines = _create_field_lines(intent, params)
    impact = _create_impact(intent, params)
    msg = _compose(action_line, detail_lines, impact)
    return _append_task_class(msg, task_class)


def _build_update_message(
    intent: str,
    label: str,
    params: dict,
    recon: Optional[ReconciliationResult],
    task_class: Optional[str],
) -> str:
    title = _get_title(params) or (
        (recon.matched_object or {}).get('title', '') if recon else ''
    )
    action_line = f"{label}" + (f': "{title}"' if title else '')
    before, after = _update_field_lines(intent, params, recon)
    impact = _update_impact(intent, params, recon)
    msg = _compose_update(action_line, before, after, impact)
    return _append_task_class(msg, task_class)


def _build_delete_message(
    intent: str, params: dict, task_class: Optional[str],
) -> str:
    entity = _entity_word(intent)
    title = _get_title(params)
    action_line = f"Delete {entity}" + (f': "{title}"' if title else '')
    detail_lines = []
    if title:
        detail_lines.append(f"Target → {title}")
    if params.get('delete_series'):
        detail_lines.append("Scope → entire recurring series")
    impact = _delete_impact(intent, params)
    msg = _compose(action_line, detail_lines, impact)
    return _append_task_class(msg, task_class)


def _build_reschedule_message(
    recon: ReconciliationResult, params: dict, task_class: Optional[str],
) -> str:
    matched = recon.matched_object or {}
    existing_title = matched.get('title', 'activity')
    existing_time = matched.get('time')
    new_time = (
        params.get('scheduled_time')
        or params.get('start_time')
        or params.get('new_scheduled_time')
    )

    action_line = f'Reschedule: "{existing_title}"'
    before = [f"Time → {_format_time_str(existing_time)}"] if existing_time else ["Time → —"]
    after = [f"Time → {_format_time_str(new_time)}"] if new_time else ["Time → —"]

    delta = _time_delta_str(existing_time, new_time) if (existing_time and new_time) else None
    impact = (
        f"Moves this {_entity_word(recon.original_intent)} {delta}."
        if delta
        else f"Updates the time on this {_entity_word(recon.original_intent)}."
    )

    msg = _compose_update(action_line, before, after, impact)
    return _append_task_class(msg, task_class)


def _build_skip_message(recon: ReconciliationResult) -> str:
    """Build message for a proposed skip (existing + same time)."""
    matched = recon.matched_object or {}
    title = matched.get('title', 'activity')
    base = recon.skip_message or (
        f'"{title}" is already scheduled — no changes needed.'
    )
    return (
        f"Action: Keep existing entry\n\n"
        f"Details:\n• {base}\n\n"
        f"Impact: Nothing changes — your existing entry stays as-is."
    )


def _build_confirm_ambiguous_message(
    recon: ReconciliationResult, label: str, params: dict,
) -> str:
    """Build message for an ambiguous match requiring disambiguation."""
    if recon.confirm_message:
        base = recon.confirm_message
    else:
        matched = recon.matched_object or {}
        title = matched.get('title', 'activity')
        base = f'I found a possible match: "{title}". Is this what you meant?'

    parts = [f"Action: {label} (confirm match)", "", "Details:", f"• {base}"]
    if recon.candidates:
        for i, c in enumerate(recon.candidates[:5]):
            parts.append(f"  {i + 1}. {c.get('title', '?')}")
    parts.append("")
    parts.append("Impact: Confirms which existing item you meant before making changes.")
    return '\n'.join(parts)
