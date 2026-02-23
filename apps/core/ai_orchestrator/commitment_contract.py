"""
Phase 5A — Executive Commitment Contract (ECC) Runtime Layer.

Project: Whole Life Journey
Path: apps/core/ai_orchestrator/commitment_contract.py
Purpose: Deterministic commitment detection, enforcement, and closure.

Description:
    Runtime-only behavioral protocol that:
    1. Detects commitment intent via lexical matching
    2. Enforces explicit time boundaries
    3. Requires a one-sentence definition of done
    4. Manages tier-aware renegotiation gating
    5. Enforces binary closure
    6. Adds minimal, non-motivational positive lock-in

    No database persistence. Commitments are runtime-scoped only.
    No LLM calls. Deterministic behavior only.

Integration Order (within CoS pipeline):
    1. Lexical hardening (existing Phase 4 R3)
    2. Tier evaluation (existing Phase 3)
    3. ECC detection (this module — if commitment intent)
    4. ECC enforcement / tightening (this module)
    5. Existing R5 escalation logic (existing Phase 4 R5)

    ECC must not override R5. ECC precedes R5.

Public API:
    - detect_commitment_intent(text) -> bool
    - extract_commitment_fields(text) -> CommitmentDraft | MissingField
    - generate_tightening_question(missing_field) -> str
    - normalize_commitment(draft) -> Commitment
    - apply_renegotiation_rules(commitment, user_text, tier) -> Commitment | dict
    - close_commitment(commitment, user_response, tier) -> Commitment | str
    - render_commitment_confirmation(commitment) -> str
    - render_positive_lock_in(commitment) -> str | None

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional


# =========================================================================
# DATACLASSES
# =========================================================================


@dataclass
class Commitment:
    """Runtime commitment object. No persistence layer."""
    normalized_text: str
    commitment_type: Literal['DO', 'DECIDE', 'SCHEDULE', 'STOP']
    time_boundary: datetime
    done_definition: str
    status: Literal['pending', 'closed_success', 'closed_missed'] = 'pending'
    time_boundary_display: Optional[str] = None


@dataclass
class CommitmentDraft:
    """Intermediate object before normalization."""
    action: str
    time_boundary_raw: Optional[str] = None
    done_definition: Optional[str] = None
    time_boundary_display: Optional[str] = None


@dataclass
class MissingField:
    """Returned when a required field is missing from the commitment."""
    field_name: str


# =========================================================================
# COMMITMENT INTENT PATTERNS
# =========================================================================

# Normalized forms (apostrophes stripped by _normalize_for_matching).
# Order: longest first to avoid partial matches.
_COMMITMENT_TRIGGERS = (
    'i am going to',
    'im going to',
    'i plan to',
    'i will',
    'ill',
    'lets',
    'let us',
)


# =========================================================================
# TIME BOUNDARY PATTERNS
# =========================================================================

# Explicit time expressions — matched against normalized input.
_TIME_PATTERNS = (
    # Specific times
    re.compile(r'by (\d{1,2}(?::\d{2})?\s*(?:am|pm))'),
    re.compile(r'at (\d{1,2}(?::\d{2})?\s*(?:am|pm))'),
    re.compile(r'before (\d{1,2}(?::\d{2})?\s*(?:am|pm))'),
    # Relative day references
    re.compile(r'\b(today|tonight|this morning|this afternoon|this evening)\b'),
    re.compile(r'\b(tomorrow|tomorrow morning|tomorrow evening|tomorrow night)\b'),
    # Day-of-week
    re.compile(r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b'),
    # Date patterns
    re.compile(r'\b(\d{1,2}/\d{1,2}(?:/\d{2,4})?)\b'),
    # Relative expressions
    re.compile(r'\b(in \d+ (?:minutes?|hours?|days?|weeks?))\b'),
    re.compile(r'\b(next (?:week|month|monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b'),
    # End-of-period
    re.compile(r'\b(end of (?:today|the day|the week|this week|the month|this month))\b'),
)


# =========================================================================
# DONE-DEFINITION PATTERNS
# =========================================================================

# Phrases that signal a done-definition is being provided.
_DONE_PATTERNS = (
    re.compile(r"done (?:means|when|if|is when)\s+(.+)", re.IGNORECASE),
    re.compile(r"(?:it's|its|it is) done (?:when|if)\s+(.+)", re.IGNORECASE),
    re.compile(r"complete (?:means|when|if)\s+(.+)", re.IGNORECASE),
    re.compile(r"finished (?:means|when|if)\s+(.+)", re.IGNORECASE),
    re.compile(r"success (?:means|looks like)\s+(.+)", re.IGNORECASE),
)


# =========================================================================
# INTERNAL HELPERS
# =========================================================================


def _normalize_for_matching(text):
    """
    Normalize text for pattern matching.

    Same normalization approach as Phase 4 R3 _normalize_input:
    - Lowercase
    - Normalize curly apostrophes to straight
    - Strip apostrophes
    - Remove non-word/non-space punctuation
    - Collapse whitespace

    Returns:
        str — normalized text.
    """
    if not text:
        return ''
    result = text.lower()
    # Normalize curly apostrophes/quotes
    result = result.replace('\u2019', "'").replace('\u2018', "'")
    result = result.replace('\u201c', '"').replace('\u201d', '"')
    # Strip apostrophes (i'll → ill, it's → its)
    result = result.replace("'", '')
    # Strip remaining punctuation (keep letters, digits, spaces)
    result = re.sub(r'[^\w\s]', ' ', result)
    # Collapse repeated spaces
    result = re.sub(r'\s+', ' ', result).strip()
    return result


def _extract_action_text(normalized, trigger):
    """
    Extract the action portion after the commitment trigger.

    Args:
        normalized: normalized input text.
        trigger: the matched trigger phrase.

    Returns:
        str — the action text, or empty string.
    """
    idx = normalized.find(trigger)
    if idx == -1:
        return ''
    after = normalized[idx + len(trigger):].strip()
    # Remove trailing time expressions for cleaner action text
    for pattern in _TIME_PATTERNS:
        after = pattern.sub('', after).strip()
    # Clean up residual prepositions left by time removal
    after = re.sub(r'\s+(by|at|before|in|on|next)\s*$', '', after).strip()
    return after


# Regex patterns for finding triggers in ORIGINAL text (preserving case).
# Order must mirror _COMMITMENT_TRIGGERS for correct precedence.
_TRIGGER_ORIGINAL_PATTERNS = (
    re.compile(r"I\s+am\s+going\s+to\s+", re.IGNORECASE),
    re.compile(r"I['\u2019]m\s+going\s+to\s+", re.IGNORECASE),
    re.compile(r"I\s+plan\s+to\s+", re.IGNORECASE),
    re.compile(r"I\s+will\s+", re.IGNORECASE),
    re.compile(r"I['\u2019]ll\s+", re.IGNORECASE),
    re.compile(r"Let['\u2019]?s\s+", re.IGNORECASE),
    re.compile(r"Let\s+us\s+", re.IGNORECASE),
)


def _extract_after_trigger_original(text):
    """
    Find the commitment trigger in original text and return everything after it.

    Preserves original case.

    Args:
        text: str — original text (may include time but NOT done-definition).

    Returns:
        str or None — text after the trigger, preserving case.
    """
    for pattern in _TRIGGER_ORIGINAL_PATTERNS:
        match = pattern.search(text)
        if match:
            return text[match.end():]
    return None


def _split_action_and_time(text):
    """
    Split text (after trigger) into action and time display phrase.

    Finds the earliest time-related pattern match and looks backwards for
    an introducing preposition (by, at, before, on, in).

    Args:
        text: str — text after trigger, preserving original case.

    Returns:
        (action, time_display) — both preserving original case.
        time_display may be None if no time expression found.
    """
    if not text:
        return text, None

    text_lower = text.lower()

    # Find the earliest time pattern match position
    earliest_pos = len(text)
    for pattern in _TIME_PATTERNS:
        match = pattern.search(text_lower)
        if match:
            pos = match.start()
            if pos < earliest_pos:
                earliest_pos = pos

    if earliest_pos >= len(text):
        return text.strip(), None

    # Look backwards for a preposition that introduces the time phrase
    before = text[:earliest_pos]
    prep_match = re.search(r'\b(by|at|before|on|in)\s*$', before, re.IGNORECASE)
    if prep_match:
        earliest_pos = prep_match.start()

    action = text[:earliest_pos].strip()
    time_display = text[earliest_pos:].strip().rstrip('.')

    return action, time_display


# =========================================================================
# PUBLIC API
# =========================================================================


def detect_commitment_intent(text):
    """
    Detect commitment intent in user text via lexical matching.

    Triggers on:
    - "I will" / "I'll"
    - "I am going to" / "I'm going to"
    - "Let's"
    - "I plan to"

    No LLM detection. Deterministic only.

    Args:
        text: str — user input.

    Returns:
        bool — True if commitment language detected.
    """
    if not text:
        return False
    normalized = _normalize_for_matching(text)
    return any(trigger in normalized for trigger in _COMMITMENT_TRIGGERS)


def extract_commitment_fields(text):
    """
    Extract commitment fields from user text.

    Extraction order:
    1. Done-definition extracted from ORIGINAL text first
    2. Done-definition clause stripped from text
    3. Action extracted from ORIGINAL text (preserving case)
    4. Time display extracted from ORIGINAL text
    5. First letter of action and done-definition capitalized

    Returns MissingField for the FIRST missing required field (one at a time):
    - time_boundary checked first
    - done_definition checked second

    Args:
        text: str — user input.

    Returns:
        CommitmentDraft if all fields present, or MissingField for the
        first missing required field.
    """
    if not text:
        return MissingField('time_boundary')

    # Step 1: Extract done-definition from ORIGINAL text first
    done_def = None
    done_clause_start = len(text)
    for pattern in _DONE_PATTERNS:
        match = pattern.search(text)
        if match:
            done_def = match.group(1).strip()
            done_clause_start = match.start()
            break

    # Step 2: Get text before done-definition clause
    pre_done_text = text[:done_clause_start].strip().rstrip('.')

    # Step 3: Check for commitment trigger using normalized form
    normalized = _normalize_for_matching(pre_done_text)
    matched_trigger = None
    for trigger in _COMMITMENT_TRIGGERS:
        if trigger in normalized:
            matched_trigger = trigger
            break

    if not matched_trigger:
        return MissingField('time_boundary')

    # Step 4: Find trigger in ORIGINAL text and extract after it
    after_trigger = _extract_after_trigger_original(pre_done_text)
    if not after_trigger:
        after_trigger = pre_done_text  # Fallback

    # Step 5: Split action from time phrase (preserving case)
    action, time_display = _split_action_and_time(after_trigger)
    if not action:
        action = after_trigger

    # Capitalize first letter of action
    if action:
        action = action[0].upper() + action[1:]

    # Step 6: Extract time_raw for datetime parsing
    time_raw = None
    for pattern in _TIME_PATTERNS:
        match = pattern.search(text.lower())
        if match:
            time_raw = match.group(0).strip()
            break

    # Step 7: Clean done-definition
    if done_def:
        # Capitalize first letter
        done_def = done_def[0].upper() + done_def[1:]
        # Strip trailing period (render_commitment_confirmation adds one)
        done_def = done_def.rstrip('.')

    # Request ONE missing field at a time (time first, then done-def)
    if not time_raw:
        return MissingField('time_boundary')

    if not done_def:
        return MissingField('done_definition')

    return CommitmentDraft(
        action=action,
        time_boundary_raw=time_raw,
        done_definition=done_def,
        time_boundary_display=time_display,
    )


def generate_tightening_question(missing_field):
    """
    Generate the tightening question for a missing field.

    No variation. No extra language.

    Args:
        missing_field: MissingField instance.

    Returns:
        str — the tightening question.
    """
    if not isinstance(missing_field, MissingField):
        return ''

    if missing_field.field_name == 'time_boundary':
        return "When specifically will this be completed?"

    if missing_field.field_name == 'done_definition':
        return "What does 'done' mean in one sentence?"

    return ''


def normalize_commitment(draft, reference_time=None):
    """
    Normalize a CommitmentDraft into a full Commitment.

    - Normalizes text
    - Normalizes time boundary to concrete datetime
    - Classifies type: DECIDE / SCHEDULE / STOP / DO
    - Sets status = pending

    Args:
        draft: CommitmentDraft with all fields present.
        reference_time: Optional datetime to use as reference for relative
                       time calculations. Defaults to now.

    Returns:
        Commitment instance.
    """
    if reference_time is None:
        reference_time = datetime.now()

    # Use action text as-is (already case-corrected by extract_commitment_fields)
    normalized_text = draft.action

    # Parse time boundary to concrete datetime
    time_boundary = _parse_time_boundary(draft.time_boundary_raw, reference_time)

    # Classify commitment type (lowercase internally)
    commitment_type = _classify_commitment_type(normalized_text)

    return Commitment(
        normalized_text=normalized_text,
        commitment_type=commitment_type,
        time_boundary=time_boundary,
        done_definition=draft.done_definition or '',
        status='pending',
        time_boundary_display=draft.time_boundary_display,
    )


def apply_renegotiation_rules(commitment, user_text, tier):
    """
    Apply tier-aware renegotiation rules.

    CLEAN tier:
        Allow renegotiation ONLY if:
        - New explicit time boundary present
        - If scope changed → require new done-definition

    EARLY_EROSION or STRUCTURAL_DRIFT tier:
        Do NOT allow renegotiation deferral.
        Return two deterministic choices:
        A) Keep original commitment with smaller timebox (15–30 min)
        B) Formally cancel and accept consequence

    No motivational framing.

    Args:
        commitment: Commitment instance.
        user_text: str — user's renegotiation message.
        tier: str — CLEAN / EARLY_EROSION / STRUCTURAL_DRIFT.

    Returns:
        Updated Commitment (if CLEAN renegotiation allowed), or
        dict with 'choices' key (if renegotiation blocked).
    """
    if tier == 'CLEAN':
        return _handle_clean_renegotiation(commitment, user_text)

    # EARLY_EROSION or STRUCTURAL_DRIFT — block renegotiation deferral
    return {
        'blocked': True,
        'choices': [
            {
                'option': 'A',
                'description': (
                    f"Keep original commitment with 30-minute timebox: "
                    f"{commitment.normalized_text}"
                ),
            },
            {
                'option': 'B',
                'description': "Formally cancel this commitment.",
            },
        ],
    }


def close_commitment(commitment, user_response, tier=None):
    """
    Enforce binary closure on a commitment.

    If user confirms completion: status = closed_success
    If user denies: status = closed_missed
    If ambiguous: return clarification question.

    Args:
        commitment: Commitment instance.
        user_response: str — user's closure response.
        tier: str — optional tier (unused in closure, reserved).

    Returns:
        Commitment with updated status, or str (clarification question).
    """
    if not user_response:
        return "Is it done — yes or no?"

    normalized = _normalize_for_matching(user_response)

    # Affirmative signals
    affirmative = ('yes', 'done', 'completed', 'finished', 'yep', 'yeah', 'yea')
    # Negative signals
    negative = ('no', 'not done', 'didnt', 'did not', 'nope', 'not yet', 'missed')

    is_affirmative = any(word in normalized for word in affirmative)
    is_negative = any(word in normalized for word in negative)

    if is_affirmative and not is_negative:
        commitment.status = 'closed_success'
        return commitment

    if is_negative and not is_affirmative:
        commitment.status = 'closed_missed'
        return commitment

    # Ambiguous — ask binary
    return "Is it done — yes or no?"


def render_commitment_confirmation(commitment):
    """
    Render the commitment confirmation message.

    Output exactly:
    "Commitment set: [action] [time]. Done means: [definition]."

    Uses time_boundary_display (human-readable phrase) when available,
    falls back to formatted datetime.

    Args:
        commitment: Commitment instance.

    Returns:
        str — confirmation message.
    """
    # Use human-readable time phrase if available
    if commitment.time_boundary_display:
        time_part = commitment.time_boundary_display
    else:
        time_part = (
            f"by {commitment.time_boundary.strftime('%Y-%m-%d %I:%M %p').lstrip('0')}"
        )

    # Ensure time clause has a preposition
    if not time_part.lower().startswith(('by ', 'at ', 'before ', 'on ', 'in ')):
        time_part = f"by {time_part}"

    # Strip trailing period from done-definition to avoid double period
    done_def = commitment.done_definition.rstrip('.')

    return (
        f"Commitment set: {commitment.normalized_text} {time_part}. "
        f"Done means: {done_def}."
    )


def render_positive_lock_in(commitment):
    """
    Render minimal positive lock-in message.

    Triggers ONLY if:
    - status == closed_success
    - Caller must enforce once-per-day max externally

    Output exactly:
    "Time boundary honored. Repeat this structure."

    No praise. No emotional tone.

    Args:
        commitment: Commitment instance.

    Returns:
        str if conditions met, None otherwise.
    """
    if commitment.status != 'closed_success':
        return None

    return "Time boundary honored. Repeat this structure."


# =========================================================================
# RENEGOTIATION TRIGGERS
# =========================================================================

# Lexical triggers indicating renegotiation of an existing commitment.
# Checked BEFORE commitment intent detection to ensure precedence.
_RENEGOTIATION_TRIGGERS = (
    'move',
    'push',
    'delay',
    'reschedule',
    'next week',
    'later',
    'instead',
)


def _detect_renegotiation_intent(text):
    """
    Detect renegotiation intent via lexical matching.

    Deterministic only. No LLM.

    Args:
        text: str — user input.

    Returns:
        bool — True if renegotiation language detected.
    """
    if not text:
        return False
    normalized = _normalize_for_matching(text)
    return any(trigger in normalized for trigger in _RENEGOTIATION_TRIGGERS)


# =========================================================================
# PIPELINE INTEGRATION
# =========================================================================


def process_ecc_detection(user_input, tier, active_commitments=None):
    """
    Main ECC pipeline entry point.

    Called between tier evaluation and R5 escalation.
    Processes user input for commitment intent and returns
    appropriate ECC response or None if no commitment detected.

    Precedence order:
    1. Renegotiation of active commitment (checked FIRST)
    2. New commitment detection

    Args:
        user_input: str — user's message.
        tier: str — CLEAN / EARLY_EROSION / STRUCTURAL_DRIFT.
        active_commitments: list[Commitment] — runtime commitments in session.

    Returns:
        dict with:
            'detected': bool — whether commitment intent was found.
            'response': str | None — tightening question or confirmation.
            'commitment': Commitment | None — if fully formed.
            'renegotiation': dict | None — if renegotiation attempt on existing.
        Or None if no commitment intent detected.
    """
    if active_commitments is None:
        active_commitments = []

    # --- RENEGOTIATION PRECEDENCE ---
    # Check renegotiation BEFORE commitment intent detection.
    # Renegotiation triggers (move, push, delay, reschedule, instead, later,
    # next week) must route directly to apply_renegotiation_rules without
    # requiring a commitment trigger (I will, I'll, etc.).
    if active_commitments and _detect_renegotiation_intent(user_input):
        pending = [c for c in active_commitments if c.status == 'pending']
        if pending:
            latest = pending[-1]
            reneg_result = apply_renegotiation_rules(latest, user_input, tier)
            if isinstance(reneg_result, dict) and reneg_result.get('blocked'):
                return {
                    'detected': True,
                    'response': None,
                    'commitment': None,
                    'renegotiation': reneg_result,
                }
            elif isinstance(reneg_result, Commitment):
                return {
                    'detected': True,
                    'response': render_commitment_confirmation(reneg_result),
                    'commitment': reneg_result,
                    'renegotiation': None,
                }
            elif isinstance(reneg_result, MissingField):
                # Scope changed during renegotiation — need new done-def
                question = generate_tightening_question(reneg_result)
                return {
                    'detected': True,
                    'response': question,
                    'commitment': None,
                    'renegotiation': None,
                }

    # --- NEW COMMITMENT DETECTION ---
    if not detect_commitment_intent(user_input):
        return None

    # New commitment — extract fields
    result = extract_commitment_fields(user_input)

    if isinstance(result, MissingField):
        question = generate_tightening_question(result)
        return {
            'detected': True,
            'response': question,
            'commitment': None,
            'renegotiation': None,
        }

    # All fields present — normalize and confirm
    commitment = normalize_commitment(result)
    confirmation = render_commitment_confirmation(commitment)

    return {
        'detected': True,
        'response': confirmation,
        'commitment': commitment,
        'renegotiation': None,
    }


def format_ecc_injection(active_commitments):
    """
    Format ECC state for injection into the CoS system prompt.

    Appended after tier evaluation, before R5 escalation logic.
    Only includes active (pending) commitments.

    Args:
        active_commitments: list[Commitment] — runtime commitments.

    Returns:
        str — formatted injection block, or empty string if no commitments.
    """
    pending = [c for c in (active_commitments or []) if c.status == 'pending']
    if not pending:
        return ''

    lines = ['--- ACTIVE COMMITMENTS (ECC) ---']
    for c in pending:
        # Use human-readable time phrase if available
        if c.time_boundary_display:
            time_part = c.time_boundary_display
            if not time_part.lower().startswith(
                ('by ', 'at ', 'before ', 'on ', 'in ')
            ):
                time_part = f"by {time_part}"
        else:
            time_part = f"by {c.time_boundary.strftime('%Y-%m-%d %I:%M %p')}"
        done_def = c.done_definition.rstrip('.')
        lines.append(
            f"COMMITMENT [{c.commitment_type}]: {c.normalized_text} "
            f"{time_part}. Done means: {done_def}."
        )
    lines.append(
        "ENFORCEMENT: Commitments require explicit closure (done or missed). "
        "Do not allow ambiguous completion claims."
    )
    lines.append('--- END ACTIVE COMMITMENTS ---')

    return '\n'.join(lines)


# =========================================================================
# INTERNAL — TIME BOUNDARY PARSING
# =========================================================================


def _parse_time_boundary(raw, reference_time):
    """
    Parse a raw time boundary string to a concrete datetime.

    Deterministic parsing only — no LLM inference.

    Args:
        raw: str — raw time expression (e.g., "today", "by 5pm", "tomorrow").
        reference_time: datetime — reference for relative calculations.

    Returns:
        datetime — concrete time boundary.
    """
    from datetime import timedelta

    if not raw:
        return reference_time

    raw_lower = raw.lower().strip()

    # "today" / "tonight" / "this evening" → end of day
    if raw_lower in ('today', 'tonight', 'this evening', 'this afternoon'):
        return reference_time.replace(hour=23, minute=59, second=0, microsecond=0)

    # "this morning" → noon
    if raw_lower == 'this morning':
        return reference_time.replace(hour=12, minute=0, second=0, microsecond=0)

    # "tomorrow" variants
    if raw_lower.startswith('tomorrow'):
        tomorrow = reference_time + timedelta(days=1)
        if 'morning' in raw_lower:
            return tomorrow.replace(hour=12, minute=0, second=0, microsecond=0)
        if 'evening' in raw_lower or 'night' in raw_lower:
            return tomorrow.replace(hour=21, minute=0, second=0, microsecond=0)
        return tomorrow.replace(hour=23, minute=59, second=0, microsecond=0)

    # "end of today" / "end of the day"
    if 'end of' in raw_lower and ('today' in raw_lower or 'the day' in raw_lower):
        return reference_time.replace(hour=23, minute=59, second=0, microsecond=0)

    # "end of the week" / "end of this week"
    if 'end of' in raw_lower and 'week' in raw_lower:
        days_until_sunday = 6 - reference_time.weekday()
        if days_until_sunday <= 0:
            days_until_sunday = 7
        end_of_week = reference_time + timedelta(days=days_until_sunday)
        return end_of_week.replace(hour=23, minute=59, second=0, microsecond=0)

    # "end of the month" / "end of this month"
    if 'end of' in raw_lower and 'month' in raw_lower:
        if reference_time.month == 12:
            eom = reference_time.replace(year=reference_time.year + 1, month=1, day=1)
        else:
            eom = reference_time.replace(month=reference_time.month + 1, day=1)
        eom = eom - timedelta(days=1)
        return eom.replace(hour=23, minute=59, second=0, microsecond=0)

    # "in X minutes/hours/days/weeks"
    in_match = re.match(r'in (\d+) (minutes?|hours?|days?|weeks?)', raw_lower)
    if in_match:
        amount = int(in_match.group(1))
        unit = in_match.group(2)
        if 'minute' in unit:
            return reference_time + timedelta(minutes=amount)
        if 'hour' in unit:
            return reference_time + timedelta(hours=amount)
        if 'day' in unit:
            delta = timedelta(days=amount)
            target = reference_time + delta
            return target.replace(hour=23, minute=59, second=0, microsecond=0)
        if 'week' in unit:
            delta = timedelta(weeks=amount)
            target = reference_time + delta
            return target.replace(hour=23, minute=59, second=0, microsecond=0)

    # Day-of-week
    days_map = {
        'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
        'friday': 4, 'saturday': 5, 'sunday': 6,
    }
    # Check "next <day>" or bare day name
    for day_name, day_num in days_map.items():
        if day_name in raw_lower:
            current_day = reference_time.weekday()
            days_ahead = day_num - current_day
            if days_ahead <= 0:
                days_ahead += 7
            if 'next' in raw_lower:
                days_ahead += 7  # "next Monday" = the one after this coming
            target = reference_time + timedelta(days=days_ahead)
            return target.replace(hour=23, minute=59, second=0, microsecond=0)

    # Specific time: "by 5pm", "at 3:30 pm", "before 10am"
    time_match = re.match(
        r'(?:by|at|before)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)',
        raw_lower,
    )
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or 0)
        ampm = time_match.group(3)
        if ampm == 'pm' and hour != 12:
            hour += 12
        elif ampm == 'am' and hour == 12:
            hour = 0
        return reference_time.replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )

    # Fallback: end of current day
    return reference_time.replace(hour=23, minute=59, second=0, microsecond=0)


# =========================================================================
# INTERNAL — COMMITMENT TYPE CLASSIFICATION
# =========================================================================


def _classify_commitment_type(normalized_text):
    """
    Classify commitment type based on normalized text.

    Rules:
        contains "decide" → DECIDE
        contains "schedule" → SCHEDULE
        contains "stop" → STOP
        else → DO

    Lowercases internally so callers can pass case-preserved text.

    Args:
        normalized_text: str — commitment text.

    Returns:
        str — DO / DECIDE / SCHEDULE / STOP.
    """
    text = normalized_text.lower()
    if 'decide' in text:
        return 'DECIDE'
    if 'schedule' in text:
        return 'SCHEDULE'
    if 'stop' in text:
        return 'STOP'
    return 'DO'


# =========================================================================
# INTERNAL — CLEAN RENEGOTIATION
# =========================================================================


def _handle_clean_renegotiation(commitment, user_text):
    """
    Handle renegotiation for CLEAN tier.

    Allow ONLY if:
    - New explicit time boundary present
    - If scope changed → require new done-definition

    Args:
        commitment: Commitment instance.
        user_text: str — renegotiation message.

    Returns:
        Updated Commitment, or MissingField if new done-definition needed.
    """
    # Check for new time boundary
    new_time_raw = None
    for pattern in _TIME_PATTERNS:
        match = pattern.search(user_text.lower())
        if match:
            new_time_raw = match.group(0).strip()
            break

    if not new_time_raw:
        # No new time boundary — renegotiation not allowed
        return {
            'blocked': True,
            'reason': 'Renegotiation requires a new explicit time boundary.',
            'choices': [
                {
                    'option': 'A',
                    'description': (
                        f"Keep original commitment: {commitment.normalized_text}"
                    ),
                },
                {
                    'option': 'B',
                    'description': "Provide a new specific time boundary.",
                },
            ],
        }

    # Check if scope changed (action text differs significantly)
    new_normalized = _normalize_for_matching(user_text)
    scope_changed = _detect_scope_change(commitment.normalized_text, new_normalized)

    if scope_changed:
        # Check for new done-definition
        new_done = None
        for pattern in _DONE_PATTERNS:
            match = pattern.search(user_text)
            if match:
                new_done = match.group(1).strip()
                break

        if not new_done:
            return MissingField('done_definition')

        commitment.done_definition = new_done

    # Update time boundary
    new_time = _parse_time_boundary(new_time_raw, datetime.now())
    commitment.time_boundary = new_time

    return commitment


def _detect_scope_change(original_normalized, new_normalized):
    """
    Detect if the scope of a commitment has changed.

    Heuristic: if the new text contains pronouns referencing the
    original (it, this, that), scope has NOT changed. Otherwise,
    if less than 50% of the original words appear in the new text,
    scope has changed.

    Args:
        original_normalized: str — original commitment text.
        new_normalized: str — new user input.

    Returns:
        bool — True if scope changed.
    """
    # Pronoun references to the existing commitment = no scope change
    _REFERENCE_PRONOUNS = {'it', 'this', 'that', 'the same'}
    new_words = set(new_normalized.split())
    if new_words & _REFERENCE_PRONOUNS:
        return False

    original_words = set(original_normalized.split())
    if not original_words:
        return True

    overlap = original_words & new_words
    overlap_ratio = len(overlap) / len(original_words)

    return overlap_ratio < 0.5
