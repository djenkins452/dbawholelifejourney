"""
Phase 5A — Executive Commitment Contract (ECC) — DB-Backed Layer.

Project: Whole Life Journey
Path: apps/core/ai_orchestrator/commitment_contract.py
Purpose: Deterministic commitment detection, enforcement, and closure.

Description:
    DB-backed behavioral protocol that:
    1. Detects commitment intent via lexical matching
    2. Enforces explicit time boundaries (always required)
    3. Requires done-definition only for vague actions
    4. Manages tier-aware renegotiation gating with history
    5. Enforces binary closure (single or multi-commitment)
    6. Adds minimal, non-motivational positive lock-in
    7. Persists all commitments to DB with concurrency-safe locking
    8. Supports multi-commitment stacking (max 5 per user)
    9. Provides cross-session commitment continuity
    10. Includes false-positive mitigation for casual language

    Commitments are user-global and persist across conversations.
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
    - normalize_commitment(draft) -> CommitmentData
    - apply_renegotiation_rules(commitment_data, user_text, tier) -> CommitmentData | RenegotiationBlocked | MissingField
    - close_commitment(commitment_data, user_response, tier) -> CommitmentData | str
    - render_commitment_confirmation(commitment_data) -> str
    - render_positive_lock_in(commitment_data) -> str | None
    - process_ecc_closure(user_input, pending_commitments) -> dict | None
    - process_ecc_detection(user_input, tier, user, active_commitments) -> dict | None
    - format_ecc_injection(pending_commitments) -> str
    - create_db_commitment(user, commitment_data, conversation, tier) -> Commitment
    - close_db_commitment(commitment, status, closure_type) -> None
    - get_pending_commitments(user) -> list[Commitment]

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional

from django.utils import timezone

logger = logging.getLogger(__name__)


# =========================================================================
# DATACLASSES (runtime objects — lightweight, no DB dependency)
# =========================================================================


@dataclass
class CommitmentData:
    """Runtime commitment data object. Used for pipeline processing."""
    normalized_text: str
    commitment_type: Literal['DO', 'DECIDE', 'SCHEDULE', 'STOP']
    time_boundary: datetime
    done_definition: str
    status: Literal['pending', 'closed_success', 'closed_missed'] = 'pending'
    time_boundary_display: Optional[str] = None
    db_id: Optional[int] = None  # PK of Commitment model if persisted

    def to_dict(self):
        """Serialize to JSON-safe dict for conversation.metadata pointer."""
        return {
            'normalized_text': self.normalized_text,
            'commitment_type': self.commitment_type,
            'time_boundary': self.time_boundary.isoformat(),
            'done_definition': self.done_definition,
            'status': self.status,
            'time_boundary_display': self.time_boundary_display,
            'db_id': self.db_id,
        }

    @classmethod
    def from_dict(cls, data):
        """Deserialize from dict stored in conversation.metadata."""
        if not data or not isinstance(data, dict):
            return None
        try:
            return cls(
                normalized_text=data['normalized_text'],
                commitment_type=data['commitment_type'],
                time_boundary=datetime.fromisoformat(data['time_boundary']),
                done_definition=data.get('done_definition', ''),
                status=data.get('status', 'pending'),
                time_boundary_display=data.get('time_boundary_display'),
                db_id=data.get('db_id'),
            )
        except (KeyError, ValueError, TypeError):
            return None

    @classmethod
    def from_db(cls, commitment):
        """Create CommitmentData from a DB Commitment instance."""
        if not commitment:
            return None
        return cls(
            normalized_text=commitment.normalized_text,
            commitment_type=commitment.commitment_type,
            time_boundary=commitment.time_boundary,
            done_definition=commitment.done_definition or '',
            status=commitment.status,
            time_boundary_display=commitment.time_boundary_display,
            db_id=commitment.pk,
        )


# Legacy alias for backward compatibility with existing tests
Commitment = CommitmentData


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


@dataclass
class RenegotiationBlocked:
    """Returned when renegotiation is blocked (non-CLEAN tier or missing time)."""
    choices: list


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
# FALSE-POSITIVE EXCLUSION PATTERNS
# =========================================================================

# Words/phrases that follow a trigger but indicate casual speech, not a
# commitment. Checked AFTER trigger match, BEFORE field extraction.
_FALSE_POSITIVE_EXCLUSIONS = (
    # Food/dining
    'have pizza', 'have lunch', 'have dinner', 'have breakfast',
    'have a snack', 'have some', 'have the', 'have a beer',
    'have a drink', 'have coffee', 'have tea', 'have water',
    'have a sandwich', 'have a salad', 'have a burger',
    'have ice cream', 'have a cookie', 'have cake',
    'eat', 'grab',
    # Casual/conversational
    'think about it', 'see', 'try', 'check',
    'let you know', 'get back to you', 'be fine',
    'be okay', 'be alright', 'be there', 'be right',
    'miss you', 'love',
)


# =========================================================================
# VAGUE VERB LIST (done-definition required only for these)
# =========================================================================

_VAGUE_VERBS = (
    'work on', 'review', 'start', 'progress',
    'handle', 'deal with', 'improve', 'figure out',
    'look into', 'think about', 'explore', 'research',
    'address', 'tackle', 'process',
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


def _find_trigger_word_boundary(normalized, trigger):
    """
    Find trigger in normalized text with word-boundary awareness.

    The 'ill' trigger (from "I'll") must not match inside words like
    "will", "fill", "pill", "still", etc. Only match when the trigger
    starts at a word boundary (start of string or preceded by space).

    Returns:
        int — index of match, or -1 if not found.
    """
    start = 0
    while True:
        idx = normalized.find(trigger, start)
        if idx == -1:
            return -1
        # Check word boundary: must be at start of string or preceded by space
        if idx == 0 or normalized[idx - 1] == ' ':
            return idx
        # Not at word boundary, keep searching
        start = idx + 1


def _extract_action_text(normalized, trigger):
    """
    Extract the action portion after the commitment trigger.

    Args:
        normalized: normalized input text.
        trigger: the matched trigger phrase.

    Returns:
        str — the action text, or empty string.
    """
    idx = _find_trigger_word_boundary(normalized, trigger)
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


def _is_false_positive(normalized_after_trigger):
    """
    Check if the text after a commitment trigger is a false positive.

    E.g., "I'll have pizza" → false positive.
         "I'll have the report done" → NOT false positive.

    Args:
        normalized_after_trigger: str — normalized text after trigger.

    Returns:
        bool — True if this is a false positive (not a real commitment).
    """
    if not normalized_after_trigger:
        return True
    for exclusion in _FALSE_POSITIVE_EXCLUSIONS:
        if normalized_after_trigger.startswith(exclusion):
            return True
    return False


def _action_requires_done_definition(action_text):
    """
    Check if an action requires a done-definition based on vague verb detection.

    Simple atomic verbs (call, send, submit, pay, schedule, log) do NOT
    require done-definition. Vague verbs (work on, review, start, etc.) DO.

    Args:
        action_text: str — the action text.

    Returns:
        bool — True if done-definition is required.
    """
    if not action_text:
        return True
    action_lower = action_text.lower()
    return any(verb in action_lower for verb in _VAGUE_VERBS)


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

    Includes false-positive filtering: casual phrases like "I'll have pizza"
    are excluded.

    No LLM detection. Deterministic only.

    Args:
        text: str — user input.

    Returns:
        bool — True if commitment language detected.
    """
    if not text:
        return False
    normalized = _normalize_for_matching(text)

    # Find the matched trigger and text after it
    for trigger in _COMMITMENT_TRIGGERS:
        idx = _find_trigger_word_boundary(normalized, trigger)
        if idx != -1:
            after = normalized[idx + len(trigger):].strip()
            if _is_false_positive(after):
                continue  # Try next trigger or return False
            return True
    return False


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
    - time_boundary ALWAYS checked first (always required)
    - done_definition checked second ONLY if action contains vague verbs

    Args:
        text: str — user input.

    Returns:
        CommitmentDraft if all required fields present, or MissingField for the
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
        if _find_trigger_word_boundary(normalized, trigger) != -1:
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

    # Request ONE missing field at a time
    # Time boundary is ALWAYS required
    if not time_raw:
        return MissingField('time_boundary')

    # Done-definition required ONLY for vague actions
    if not done_def and _action_requires_done_definition(action):
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


def normalize_commitment(draft, reference_time=None, user=None):
    """
    Normalize a CommitmentDraft into a full CommitmentData.

    - Normalizes text
    - Normalizes time boundary to concrete datetime
    - Classifies type: DECIDE / SCHEDULE / STOP / DO
    - Sets status = pending

    Phase 2: Uses get_current_local_datetime(user) when user is available.
    Falls back to timezone.now() if user not provided. Never uses naive datetime.

    Args:
        draft: CommitmentDraft with all fields present.
        reference_time: Optional datetime to use as reference for relative
                       time calculations. Defaults to user-local now.
        user: Optional User instance for timezone-aware time.

    Returns:
        CommitmentData instance, or MissingField if time boundary is ambiguous.
    """
    if reference_time is None:
        reference_time = _get_reference_time(user)

    # Use action text as-is (already case-corrected by extract_commitment_fields)
    normalized_text = draft.action

    # Parse time boundary to concrete datetime
    time_boundary = _parse_time_boundary(draft.time_boundary_raw, reference_time)

    # Phase 2: _parse_time_boundary may return MissingField — propagate it
    if isinstance(time_boundary, MissingField):
        return time_boundary

    # Classify commitment type (lowercase internally)
    commitment_type = _classify_commitment_type(normalized_text)

    return CommitmentData(
        normalized_text=normalized_text,
        commitment_type=commitment_type,
        time_boundary=time_boundary,
        done_definition=draft.done_definition or '',
        status='pending',
        time_boundary_display=draft.time_boundary_display,
    )


def apply_renegotiation_rules(commitment_data, user_text, tier):
    """
    Apply tier-aware renegotiation rules.

    CLEAN tier:
        Allow renegotiation ONLY if:
        - New explicit time boundary present
        - If scope changed → require new done-definition (if vague verb)

    EARLY_EROSION or STRUCTURAL_DRIFT tier:
        Do NOT allow renegotiation deferral.
        Return two deterministic choices:
        A) Keep original commitment with smaller timebox (15–30 min)
        B) Formally cancel and accept consequence

    No motivational framing.

    Args:
        commitment_data: CommitmentData instance.
        user_text: str — user's renegotiation message.
        tier: str — CLEAN / EARLY_EROSION / STRUCTURAL_DRIFT.

    Returns:
        Updated CommitmentData (if CLEAN renegotiation allowed), or
        RenegotiationBlocked (if renegotiation blocked), or
        MissingField (if scope changed and new done-def needed).
    """
    if tier == 'CLEAN':
        return _handle_clean_renegotiation(commitment_data, user_text)

    # EARLY_EROSION or STRUCTURAL_DRIFT — block renegotiation deferral
    return RenegotiationBlocked(choices=[
        "A) Keep original commitment with a 15\u201330 minute minimum version now",
        "B) Formally cancel and accept consequence",
    ])


def close_commitment(commitment_data, user_response, tier=None):
    """
    Enforce binary closure on a commitment.

    If user confirms completion: status = closed_success
    If user denies: status = closed_missed
    If ambiguous: return clarification question.

    Args:
        commitment_data: CommitmentData instance.
        user_response: str — user's closure response.
        tier: str — optional tier (unused in closure, reserved).

    Returns:
        CommitmentData with updated status, or str (clarification question).
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
        commitment_data.status = 'closed_success'
        return commitment_data

    if is_negative and not is_affirmative:
        commitment_data.status = 'closed_missed'
        return commitment_data

    # Ambiguous — ask binary
    return "Is it done — yes or no?"


def render_commitment_confirmation(commitment_data):
    """
    Render the commitment confirmation message.

    Output exactly:
    "Commitment set: [action] [time]. Done means: [definition]."
    Or without done-definition for atomic actions:
    "Commitment set: [action] [time]."

    Uses time_boundary_display (human-readable phrase) when available,
    falls back to formatted datetime.

    Args:
        commitment_data: CommitmentData instance.

    Returns:
        str — confirmation message.
    """
    # Use human-readable time phrase if available
    if commitment_data.time_boundary_display:
        time_part = commitment_data.time_boundary_display
    else:
        time_part = (
            f"by {commitment_data.time_boundary.strftime('%Y-%m-%d %I:%M %p').lstrip('0')}"
        )

    # Ensure time clause has a preposition
    if not time_part.lower().startswith(('by ', 'at ', 'before ', 'on ', 'in ')):
        time_part = f"by {time_part}"

    if commitment_data.done_definition:
        # Strip trailing period from done-definition to avoid double period
        done_def = commitment_data.done_definition.rstrip('.')
        return (
            f"Commitment set: {commitment_data.normalized_text} {time_part}. "
            f"Done means: {done_def}."
        )

    return f"Commitment set: {commitment_data.normalized_text} {time_part}."


def render_positive_lock_in(commitment_data):
    """
    Render minimal positive lock-in message.

    Triggers ONLY if:
    - status == closed_success
    - Caller must enforce once-per-day max externally

    Output exactly:
    "Time boundary honored. Repeat this structure."

    No praise. No emotional tone.

    Args:
        commitment_data: CommitmentData instance.

    Returns:
        str if conditions met, None otherwise.
    """
    if commitment_data.status != 'closed_success':
        return None

    return "Time boundary honored. Repeat this structure."


# =========================================================================
# CLOSURE TRIGGERS
# =========================================================================

# Lexical triggers indicating commitment closure intent.
# Checked BEFORE renegotiation and new commitment detection.
# Matched against normalized input (lowercase, apostrophes stripped).
_CLOSURE_TRIGGERS = (
    'its done',
    'done',
    'finished',
    'completed',
    'i finished it',
    'yes',
    'yeah',
    'yep',
    'yea',
)


def _detect_closure_intent(text):
    """
    Detect closure intent via lexical matching.

    Deterministic only. No LLM.

    Args:
        text: str — user input.

    Returns:
        bool — True if closure language detected.
    """
    if not text:
        return False
    normalized = _normalize_for_matching(text)
    return any(trigger in normalized for trigger in _CLOSURE_TRIGGERS)


def _extract_numeric_selection(text):
    """
    Extract a numeric commitment selection from user text.

    When multiple commitments are pending, user must select by number.

    Args:
        text: str — user input.

    Returns:
        int or None — 1-based index of selected commitment.
    """
    if not text:
        return None
    # Match standalone numbers like "1", "2", "#1", "#2"
    match = re.search(r'#?(\d+)', text.strip())
    if match:
        return int(match.group(1))
    return None


def process_ecc_closure(user_input, pending_commitments):
    """
    Attempt to close a pending commitment based on user input.

    Precedence: closure runs BEFORE renegotiation and new commitment detection.

    Multi-commitment rules:
    - If exactly 1 pending → "Done." closes it automatically.
    - If >1 pending → requires numeric selection. If none provided,
      list all commitments and ask for number.

    Args:
        user_input: str — user's message.
        pending_commitments: list — pending CommitmentData objects or DB Commitment objects.

    Returns:
        dict with:
            'closed': bool — whether closure was processed.
            'commitment': CommitmentData | None — updated commitment if closed.
            'response': str — closure response or clarification question.
            'db_id': int | None — PK of closed commitment (for DB update).
            'needs_selection': bool — True if user must select from list.
        Or None if no closure intent detected.
    """
    if not pending_commitments:
        return None

    pending = [c for c in pending_commitments
               if (getattr(c, 'status', None) == 'pending'
                   or getattr(c, 'status', None) == 'pending')]
    if not pending:
        return None

    if not _detect_closure_intent(user_input):
        return None

    # Single commitment → auto-close
    if len(pending) == 1:
        target = pending[0]
        commitment_data = CommitmentData.from_db(target) if hasattr(target, 'pk') else target
        result = close_commitment(commitment_data, user_input)

        if isinstance(result, CommitmentData):
            response = ''
            if result.status == 'closed_success':
                lock_in = render_positive_lock_in(result)
                response = lock_in or ''
            elif result.status == 'closed_missed':
                response = "Commitment missed. What blocked completion?"
            return {
                'closed': True,
                'commitment': result,
                'response': response,
                'db_id': getattr(target, 'pk', None) or getattr(target, 'db_id', None),
                'needs_selection': False,
            }

        # Ambiguous
        return {
            'closed': False,
            'commitment': None,
            'response': result,  # "Is it done — yes or no?"
            'db_id': None,
            'needs_selection': False,
        }

    # Multiple commitments → require numeric selection
    selection = _extract_numeric_selection(user_input)
    if selection and 1 <= selection <= len(pending):
        target = pending[selection - 1]
        commitment_data = CommitmentData.from_db(target) if hasattr(target, 'pk') else target
        result = close_commitment(commitment_data, user_input)

        if isinstance(result, CommitmentData):
            response = ''
            if result.status == 'closed_success':
                lock_in = render_positive_lock_in(result)
                response = lock_in or ''
            elif result.status == 'closed_missed':
                response = "Commitment missed. What blocked completion?"
            return {
                'closed': True,
                'commitment': result,
                'response': response,
                'db_id': getattr(target, 'pk', None) or getattr(target, 'db_id', None),
                'needs_selection': False,
            }

        return {
            'closed': False,
            'commitment': None,
            'response': result,
            'db_id': None,
            'needs_selection': False,
        }

    # No valid selection — list commitments and ask
    lines = ["Which commitment is done? Reply with the number:"]
    for i, c in enumerate(pending, 1):
        text = getattr(c, 'normalized_text', '')
        lines.append(f"{i}) {text}")
    return {
        'closed': False,
        'commitment': None,
        'response': '\n'.join(lines),
        'db_id': None,
        'needs_selection': True,
    }


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
# IDEMPOTENCY PROTECTION
# =========================================================================

# In-memory idempotency cache (3-second window)
_idempotency_cache = {}


def _check_idempotency(user_id, message):
    """
    Check if this message is a duplicate within the 3-second idempotency window.

    Uses SHA256 hash of (user_id + normalized_message + timestamp_rounded_to_second).

    Args:
        user_id: int — user primary key.
        message: str — raw user message.

    Returns:
        str or None — cached response if duplicate, None if new.
    """
    import time

    now = int(time.time())
    normalized = _normalize_for_matching(message)
    # Check current second and previous 2 seconds (3-second window)
    for ts in range(now - 2, now + 1):
        key = hashlib.sha256(
            f"{user_id}:{normalized}:{ts}".encode()
        ).hexdigest()
        if key in _idempotency_cache:
            return _idempotency_cache[key]
    return None


def _store_idempotency(user_id, message, response):
    """
    Store a response in the idempotency cache.

    Args:
        user_id: int — user primary key.
        message: str — raw user message.
        response: str — the response to cache.
    """
    import time

    now = int(time.time())
    normalized = _normalize_for_matching(message)
    key = hashlib.sha256(
        f"{user_id}:{normalized}:{now}".encode()
    ).hexdigest()
    _idempotency_cache[key] = response

    # Cleanup old entries (older than 10 seconds)
    stale_keys = []
    for k, v in _idempotency_cache.items():
        # We can't decode the timestamp from the hash, so just limit cache size
        pass
    # Simple size cap: if cache > 100 entries, clear it
    if len(_idempotency_cache) > 100:
        _idempotency_cache.clear()


# =========================================================================
# PIPELINE INTEGRATION
# =========================================================================


def process_ecc_detection(user_input, tier, active_commitments=None, user=None):
    """
    Main ECC pipeline entry point.

    Called between tier evaluation and R5 escalation.
    Processes user input for commitment intent and returns
    appropriate ECC response or None if no commitment detected.

    Precedence order:
    1. Renegotiation of active commitment (checked FIRST)
    2. New commitment detection (with hard limit check)

    Args:
        user_input: str — user's message.
        tier: str — CLEAN / EARLY_EROSION / STRUCTURAL_DRIFT.
        active_commitments: list — pending commitments (CommitmentData or DB objects).
        user: User instance — for DB operations and hard limit check.

    Returns:
        dict with:
            'detected': bool — whether commitment intent was found.
            'response': str | None — tightening question, confirmation,
                        or formatted blocking choices.
            'commitment': CommitmentData | None — if fully formed.
            'renegotiation': RenegotiationBlocked | None — if blocked.
            'limit_reached': bool — if hard limit blocked creation.
        Or None if no commitment intent detected.
    """
    if active_commitments is None:
        active_commitments = []

    # --- RENEGOTIATION PRECEDENCE ---
    if active_commitments and _detect_renegotiation_intent(user_input):
        pending = [c for c in active_commitments
                   if getattr(c, 'status', None) == 'pending']
        if pending:
            latest = pending[-1]
            commitment_data = CommitmentData.from_db(latest) if hasattr(latest, 'pk') else latest
            reneg_result = apply_renegotiation_rules(commitment_data, user_input, tier)
            # Strict type dispatch — order matters
            if isinstance(reneg_result, RenegotiationBlocked):
                return {
                    'detected': True,
                    'response': '\n'.join(reneg_result.choices),
                    'commitment': None,
                    'renegotiation': reneg_result,
                    'limit_reached': False,
                }
            elif isinstance(reneg_result, MissingField):
                question = generate_tightening_question(reneg_result)
                return {
                    'detected': True,
                    'response': question,
                    'commitment': None,
                    'renegotiation': None,
                    'limit_reached': False,
                }
            elif isinstance(reneg_result, CommitmentData):
                return {
                    'detected': True,
                    'response': render_commitment_confirmation(reneg_result),
                    'commitment': reneg_result,
                    'renegotiation': None,
                    'limit_reached': False,
                }

    # --- NEW COMMITMENT DETECTION ---
    if not detect_commitment_intent(user_input):
        return None

    # Hard limit check (max 5 pending per user)
    if user:
        try:
            from apps.core.blueprint.models import Commitment as CommitmentModel
            if not CommitmentModel.can_create(user):
                return {
                    'detected': True,
                    'response': (
                        "You have 5 active commitments. "
                        "Close or cancel one before creating another."
                    ),
                    'commitment': None,
                    'renegotiation': None,
                    'limit_reached': True,
                }
        except Exception:
            pass  # If DB check fails, allow creation (graceful degradation)

    # New commitment — extract fields
    result = extract_commitment_fields(user_input)

    if isinstance(result, MissingField):
        question = generate_tightening_question(result)
        return {
            'detected': True,
            'response': question,
            'commitment': None,
            'renegotiation': None,
            'limit_reached': False,
        }

    # All fields present — normalize and confirm
    commitment_data = normalize_commitment(result, user=user)

    # Phase 2: normalize_commitment may return MissingField if time is ambiguous
    if isinstance(commitment_data, MissingField):
        question = generate_tightening_question(commitment_data)
        return {
            'detected': True,
            'response': question,
            'commitment': None,
            'renegotiation': None,
            'limit_reached': False,
        }

    confirmation = render_commitment_confirmation(commitment_data)

    return {
        'detected': True,
        'response': confirmation,
        'commitment': commitment_data,
        'renegotiation': None,
        'limit_reached': False,
    }


def format_ecc_injection(active_commitments):
    """
    Format ECC state for injection into the CoS system prompt.

    Appended after tier evaluation, before R5 escalation logic.
    Only includes active (pending) commitments.
    Supports multiple commitments with numbered listing.

    Args:
        active_commitments: list — CommitmentData or DB Commitment instances.

    Returns:
        str — formatted injection block, or empty string if no commitments.
    """
    pending = [c for c in (active_commitments or [])
               if getattr(c, 'status', None) == 'pending']
    if not pending:
        return ''

    lines = ['--- ACTIVE COMMITMENTS (ECC) ---']
    for i, c in enumerate(pending, 1):
        text = getattr(c, 'normalized_text', '')
        ctype = getattr(c, 'commitment_type', 'DO')
        tb_display = getattr(c, 'time_boundary_display', '')
        tb = getattr(c, 'time_boundary', None)
        done_def = getattr(c, 'done_definition', '') or ''

        # Use human-readable time phrase if available
        if tb_display:
            time_part = tb_display
            if not time_part.lower().startswith(
                ('by ', 'at ', 'before ', 'on ', 'in ')
            ):
                time_part = f"by {time_part}"
        elif tb:
            time_part = f"by {tb.strftime('%Y-%m-%d %I:%M %p')}"
        else:
            time_part = ''

        if done_def:
            done_def_clean = done_def.rstrip('.')
            lines.append(
                f"{i}. COMMITMENT [{ctype}]: {text} "
                f"{time_part}. Done means: {done_def_clean}."
            )
        else:
            lines.append(
                f"{i}. COMMITMENT [{ctype}]: {text} {time_part}."
            )

    lines.append(
        "ENFORCEMENT: Commitments require explicit closure (done or missed). "
        "Do not allow ambiguous completion claims."
    )
    if len(pending) > 1:
        lines.append(
            "MULTI-COMMITMENT: When user says 'done', ask which commitment "
            "by number. Do not assume."
        )
    lines.append('--- END ACTIVE COMMITMENTS ---')

    return '\n'.join(lines)


# =========================================================================
# DB OPERATIONS (concurrency-safe)
# =========================================================================


def create_db_commitment(user, commitment_data, conversation=None, tier=''):
    """
    Persist a CommitmentData to the database with concurrency-safe locking.

    Args:
        user: User instance.
        commitment_data: CommitmentData instance.
        conversation: AssistantConversation instance (optional traceability).
        tier: str — activation state at creation time.

    Returns:
        Commitment DB instance, or None if creation failed.
    """
    try:
        from django.db import transaction
        from apps.core.blueprint.models import Commitment as CommitmentModel

        with transaction.atomic():
            # Re-check hard limit inside transaction
            if not CommitmentModel.can_create(user):
                logger.warning(
                    "Commitment creation blocked: user %s at limit", user.pk
                )
                return None

            # Phase 2: Store timezone at creation for local-intent preservation
            tz_at_creation = ''
            if user:
                try:
                    tz_at_creation = user.preferences.timezone_iana
                except Exception:
                    pass

            db_commitment = CommitmentModel.objects.create(
                user=user,
                conversation=conversation,
                normalized_text=commitment_data.normalized_text,
                commitment_type=commitment_data.commitment_type,
                time_boundary=commitment_data.time_boundary,
                time_boundary_display=commitment_data.time_boundary_display or '',
                done_definition=commitment_data.done_definition or '',
                status=CommitmentModel.STATUS_PENDING,
                tier_at_creation=tier,
                timezone_at_creation=tz_at_creation,
            )
            commitment_data.db_id = db_commitment.pk
            return db_commitment
    except Exception as e:
        logger.error("Failed to create DB commitment: %s", e)
        return None


def close_db_commitment(db_commitment, status, closure_type):
    """
    Close a DB commitment with concurrency-safe locking.

    Args:
        db_commitment: Commitment DB instance (or PK).
        status: str — new status.
        closure_type: str — closure type.
    """
    try:
        from django.db import transaction
        from apps.core.blueprint.models import Commitment as CommitmentModel

        pk = db_commitment if isinstance(db_commitment, int) else db_commitment.pk

        with transaction.atomic():
            locked = CommitmentModel.objects.select_for_update(
                nowait=False
            ).get(pk=pk)
            locked.close(status, closure_type)
    except Exception as e:
        logger.error("Failed to close DB commitment %s: %s", db_commitment, e)


def record_renegotiation(db_commitment, original_time, requested_time, tier, was_blocked, choice=''):
    """
    Record a renegotiation attempt in the database.

    Args:
        db_commitment: Commitment DB instance.
        original_time: datetime — original time boundary.
        requested_time: datetime or None — requested new time.
        tier: str — activation state at renegotiation time.
        was_blocked: bool — whether renegotiation was blocked.
        choice: str — 'A' or 'B' if blocked.
    """
    try:
        from apps.core.blueprint.models import CommitmentRenegotiation
        CommitmentRenegotiation.objects.create(
            commitment=db_commitment,
            original_time_boundary=original_time,
            requested_time_boundary=requested_time,
            tier_at_time=tier,
            was_blocked=was_blocked,
            blocked_choice_selected=choice,
        )
    except Exception as e:
        logger.error("Failed to record renegotiation: %s", e)


def get_pending_commitments(user):
    """
    Get all pending commitments for a user from the database.

    Args:
        user: User instance.

    Returns:
        QuerySet of Commitment instances.
    """
    try:
        from apps.core.blueprint.models import Commitment as CommitmentModel
        return list(CommitmentModel.pending_for_user(user).order_by('created_at'))
    except Exception as e:
        logger.error("Failed to get pending commitments: %s", e)
        return []


# =========================================================================
# INTERNAL — TIME AUTHORITY (Phase 2)
# =========================================================================


def _get_reference_time(user=None):
    """
    Get the authoritative reference time for time boundary parsing.

    Phase 2: Single time authority. Uses get_current_local_datetime(user)
    when user is available, falls back to timezone.now(). Never uses
    naive datetime.now().

    Args:
        user: Optional User instance with preferences.timezone_iana.

    Returns:
        datetime — timezone-aware reference time.
    """
    if user:
        try:
            from apps.core.utils import get_current_local_datetime
            return get_current_local_datetime(user)
        except Exception:
            pass
    return timezone.now()


# =========================================================================
# INTERNAL — TIME BOUNDARY PARSING
# =========================================================================


def _parse_time_boundary(raw, reference_time):
    """
    Parse a raw time boundary string to a concrete datetime.

    Deterministic parsing only — no LLM inference.

    Phase 2: ALLOW_END_OF_DAY_DEFAULT = False. Silent 23:59 defaults removed.
    Expressions without explicit time return MissingField('time_boundary')
    so the tightening question fires. Only expressions with concrete time
    (specific hours, "in X minutes/hours", "this morning", "tomorrow evening")
    resolve to a datetime.

    Args:
        raw: str — raw time expression (e.g., "today", "by 5pm", "tomorrow").
        reference_time: datetime — reference for relative calculations.

    Returns:
        datetime — concrete time boundary, or MissingField if time is ambiguous.
    """
    from datetime import timedelta

    if not raw:
        return MissingField('time_boundary')

    raw_lower = raw.lower().strip()

    # Phase 2: "today" / "tonight" / "this afternoon" / "this evening" without
    # explicit time → require tightening question. No silent 23:59 default.
    # But "today by 5pm" / "today at 3pm" resolve to concrete time.
    if raw_lower.startswith('today') or raw_lower in (
        'tonight', 'this evening', 'this afternoon',
    ):
        today_time = re.search(
            r'(?:by|at|before)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)',
            raw_lower,
        )
        if today_time:
            hour = int(today_time.group(1))
            minute = int(today_time.group(2) or 0)
            ampm = today_time.group(3)
            if ampm == 'pm' and hour != 12:
                hour += 12
            elif ampm == 'am' and hour == 12:
                hour = 0
            return reference_time.replace(
                hour=hour, minute=minute, second=0, microsecond=0,
            )
        return MissingField('time_boundary')

    # "this morning" → noon (concrete enough — morning has a known end)
    if raw_lower == 'this morning':
        return reference_time.replace(hour=12, minute=0, second=0, microsecond=0)

    # "tomorrow" variants — only resolve if time-of-day specified
    if raw_lower.startswith('tomorrow'):
        tomorrow = reference_time + timedelta(days=1)
        if 'morning' in raw_lower:
            return tomorrow.replace(hour=12, minute=0, second=0, microsecond=0)
        if 'evening' in raw_lower or 'night' in raw_lower:
            return tomorrow.replace(hour=21, minute=0, second=0, microsecond=0)
        # "tomorrow by/at Xam/pm" — explicit time on tomorrow
        tomorrow_time = re.search(
            r'(?:by|at|before)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)',
            raw_lower,
        )
        if tomorrow_time:
            hour = int(tomorrow_time.group(1))
            minute = int(tomorrow_time.group(2) or 0)
            ampm = tomorrow_time.group(3)
            if ampm == 'pm' and hour != 12:
                hour += 12
            elif ampm == 'am' and hour == 12:
                hour = 0
            return tomorrow.replace(
                hour=hour, minute=minute, second=0, microsecond=0,
            )
        # Bare "tomorrow" without time → tightening question
        return MissingField('time_boundary')

    # "end of today" / "end of the day" → ambiguous, require specific time
    if 'end of' in raw_lower and ('today' in raw_lower or 'the day' in raw_lower):
        return MissingField('time_boundary')

    # "end of the week" / "end of this week" → ambiguous, require specific time
    if 'end of' in raw_lower and 'week' in raw_lower:
        return MissingField('time_boundary')

    # "end of the month" / "end of this month" → ambiguous, require specific time
    if 'end of' in raw_lower and 'month' in raw_lower:
        return MissingField('time_boundary')

    # "in X minutes/hours" — concrete delta from now
    in_match = re.match(r'in (\d+) (minutes?|hours?|days?|weeks?)', raw_lower)
    if in_match:
        amount = int(in_match.group(1))
        unit = in_match.group(2)
        if 'minute' in unit:
            return reference_time + timedelta(minutes=amount)
        if 'hour' in unit:
            return reference_time + timedelta(hours=amount)
        # "in X days/weeks" — date without time → tightening question
        if 'day' in unit or 'week' in unit:
            return MissingField('time_boundary')

    # Day-of-week — date without time → tightening question
    days_map = {
        'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
        'friday': 4, 'saturday': 5, 'sunday': 6,
    }
    for day_name, day_num in days_map.items():
        if day_name in raw_lower:
            return MissingField('time_boundary')

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

    # Fallback: no recognizable concrete time → tightening question
    # Phase 2: ALLOW_END_OF_DAY_DEFAULT = False — no silent 23:59
    return MissingField('time_boundary')


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


def _handle_clean_renegotiation(commitment_data, user_text):
    """
    Handle renegotiation for CLEAN tier.

    Allow ONLY if:
    - New explicit time boundary present
    - If scope changed → require new done-definition (if vague verb)

    Args:
        commitment_data: CommitmentData instance.
        user_text: str — renegotiation message.

    Returns:
        Updated CommitmentData, or MissingField if new done-definition needed,
        or RenegotiationBlocked if no new time boundary.
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
        return RenegotiationBlocked(choices=[
            "A) Keep original commitment with a 15\u201330 minute minimum version now",
            "B) Formally cancel and accept consequence",
        ])

    # Check if scope changed (action text differs significantly)
    new_normalized = _normalize_for_matching(user_text)
    scope_changed = _detect_scope_change(commitment_data.normalized_text, new_normalized)

    if scope_changed:
        # Only require done-definition if new scope has vague verbs
        if _action_requires_done_definition(user_text):
            # Check for new done-definition
            new_done = None
            for pattern in _DONE_PATTERNS:
                match = pattern.search(user_text)
                if match:
                    new_done = match.group(1).strip()
                    break

            if not new_done:
                return MissingField('done_definition')

            commitment_data.done_definition = new_done

    # Phase 2: Use timezone-aware reference time (single time authority)
    new_time = _parse_time_boundary(new_time_raw, _get_reference_time())

    # Phase 2: _parse_time_boundary may return MissingField — for renegotiation,
    # return RenegotiationBlocked asking for a specific time (not a MissingField,
    # which would be treated as a new commitment tightening question).
    if isinstance(new_time, MissingField):
        return RenegotiationBlocked(choices=[
            "A) Specify an exact time (e.g. 'by 3pm next Wednesday')",
            "B) Keep original commitment with a 15\u201330 minute minimum version now",
        ])

    commitment_data.time_boundary = new_time

    return commitment_data


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
