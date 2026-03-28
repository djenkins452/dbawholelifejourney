"""
Beth Check-in Renderer — Chief of Staff Briefing Layer

Renders morning/midday/evening briefings using ONLY deterministic data.
The LLM is NOT involved in generating any state description.

Beth's briefing model (every interaction):
1. Greeting (natural, simple)
2. Day narrative (1 sentence, flow-oriented, no domain labels)
3. Situational awareness (behind / on track / ahead)
4. Time-aware triage (DO NOW vs MOVE LATER, with feasibility)
5. Adjustment suggestion (if items can't fit)
6. Decision prompt (if change needed — no auto-execution)

DATA SOURCES (exclusively):
- Today Engine (get_today_context) — unified day dataset
- Current time (user_now) — for triage windows
- User first name — for greeting

RULES:
- NO domain labels (Faith, Health, Tasks)
- NO counts or status language ("8 routines pending")
- NO coaching or commentary
- NO LLM inference
- Describe FLOW, not inventory
- Mention meds ONLY if due soon or overdue
- Suppress distant future items in morning
"""

import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)


def render_morning_checkin(user) -> str:
    """Render a deterministic morning briefing from execution truth."""
    try:
        return _render_checkin_from_truth(user)
    except Exception:
        logger.error(
            "[CHECKIN RENDERER] Failed for user=%s, returning safe fallback",
            user.id, exc_info=True,
        )
        return _SAFE_FALLBACK


def render_checkin_for_time(user) -> str:
    """Render a briefing appropriate for the current time of day."""
    try:
        from apps.core.utils import get_user_now
        hour = get_user_now(user).hour
        if hour < 12:
            return _render_checkin_from_truth(user, phase="morning")
        elif hour < 17:
            return _render_checkin_from_truth(user, phase="midday")
        else:
            return _render_checkin_from_truth(user, phase="evening")
    except Exception:
        logger.error(
            "[CHECKIN RENDERER] Failed for user=%s, returning safe fallback",
            user.id, exc_info=True,
        )
        return _SAFE_FALLBACK


def build_cos_structured_output(user) -> dict:
    """Canonical CoS structured output from Today Engine.

    Single unified entry point that ALL CoS paths should use.
    Returns structured data + rendered text from the same computation.

    Returns dict with:
        greeting: str
        day_narrative: str
        state: 'behind' | 'on_track' | 'ahead'
        state_text: str (human-readable situation description)
        next_commitment: str | None
        do_now: list of {'name': str, 'duration_est': int}
        sequence: list of str (explicit ordering)
        move_later: list of {'name': str, 'reason': str}
        adjustment_reason: str | None
        decision_required: bool
        completed: list of str (completed item names)
        phase: 'morning' | 'midday' | 'evening'
        rendered_text: str (full deterministic briefing text)
    """
    try:
        return _build_structured_from_truth(user)
    except Exception:
        logger.error(
            "[COS STRUCTURED] Failed for user=%s, returning safe fallback",
            user.id, exc_info=True,
        )
        return {
            'greeting': 'Good morning.',
            'day_narrative': '',
            'state': 'on_track',
            'state_text': '',
            'next_commitment': None,
            'do_now': [],
            'sequence': [],
            'move_later': [],
            'adjustment_reason': None,
            'decision_required': False,
            'completed': [],
            'phase': 'morning',
            'rendered_text': _SAFE_FALLBACK,
        }


def _build_structured_from_truth(user) -> dict:
    """Build structured CoS output from Today Engine data."""
    from apps.core.today.today_engine import get_today_context
    from apps.core.utils import get_user_now

    ctx = get_today_context(user)
    user_now = get_user_now(user)
    hour = user_now.hour
    first_name = getattr(user, 'first_name', '') or ''

    # Determine phase
    if hour < 12:
        phase = 'morning'
    elif hour < 17:
        phase = 'midday'
    else:
        phase = 'evening'

    # 1. Greeting
    if phase == 'morning':
        if hour < 5:
            greeting = f"Early start{', ' + first_name if first_name else ''}."
        elif hour < 9:
            greeting = f"Good morning{', ' + first_name if first_name else ''}."
        else:
            greeting = f"Morning{', ' + first_name if first_name else ''}."
    elif phase == 'midday':
        greeting = f"Midday check{', ' + first_name if first_name else ''}."
    else:
        greeting = f"End of day{', ' + first_name if first_name else ''}."

    # 2. Day narrative
    day_narrative = _build_day_narrative(ctx, user_now)

    # 3. Situational awareness
    overdue = ctx.get('overdue', [])
    coming_up = ctx.get('coming_up', [])
    completed = ctx.get('completed', [])
    later = ctx.get('later', [])

    state, state_text = _assess_situation_structured(
        overdue, completed, coming_up, user_now,
    )

    # 4. Triage
    triage = _build_triage_structured(
        ctx, user_now, overdue, coming_up, later,
    )

    # 5. Completed names
    completed_names = [e['label'] for e in completed]

    # 6. Render text (reuse existing renderers)
    if phase == 'morning':
        rendered_text = _render_morning(ctx, user, user_now)
    elif phase == 'midday':
        rendered_text = _render_midday(ctx, user, user_now)
    else:
        rendered_text = _render_evening(ctx, user, user_now)

    _validate_output(rendered_text)

    return {
        'greeting': greeting,
        'day_narrative': day_narrative,
        'state': state,
        'state_text': state_text,
        'next_commitment': triage['next_commitment'],
        'do_now': triage['do_now'],
        'sequence': triage['sequence'],
        'move_later': triage['move_later'],
        'adjustment_reason': triage['adjustment_reason'],
        'decision_required': triage['decision_required'],
        'completed': completed_names,
        'phase': phase,
        'rendered_text': rendered_text,
    }


# ---------------------------------------------------------------------------
# Internal renderer
# ---------------------------------------------------------------------------

_SAFE_FALLBACK = (
    "Good morning.\n\n"
    "I wasn't able to load your day right now. "
    "Try asking me what's on your plate."
)

# Re-export for backward compat with tests
from apps.core.today.today_engine import COMING_UP_WINDOW_MINUTES as UPCOMING_WINDOW_MINUTES  # noqa: F401, E402

# Banned words — if any appear in output, validation fails
_BANNED_WORDS = frozenset({"items", "tasks", "routines", "domains"})

# Default activity durations (minutes) for feasibility triage.
# Used when no scheduled duration is available from the item data.
_DEFAULT_DURATIONS = {
    'bible reading': 15,
    'prayer': 15,
    'prayer time': 15,
    'quiet time': 15,
    'devotion': 15,
    'workout': 45,
    'exercise': 45,
    'shower': 15,
    'journal': 10,
    'journaling': 10,
    'meditation': 10,
}
_DEFAULT_DURATION_FALLBACK = 15  # minutes


def _estimate_duration(item_name: str) -> int:
    """Estimate activity duration in minutes from item name."""
    name_lower = (item_name or '').lower().strip()
    for key, minutes in _DEFAULT_DURATIONS.items():
        if key in name_lower:
            return minutes
    return _DEFAULT_DURATION_FALLBACK


def _render_checkin_from_truth(user, phase: str = "morning") -> str:
    """Core renderer — builds Chief of Staff briefing from Today Engine."""
    from apps.core.today.today_engine import get_today_context
    from apps.core.utils import get_user_now

    ctx = get_today_context(user)
    user_now = get_user_now(user)

    if phase == "morning":
        output = _render_morning(ctx, user, user_now)
    elif phase == "midday":
        output = _render_midday(ctx, user, user_now)
    elif phase == "evening":
        output = _render_evening(ctx, user, user_now)
    else:
        output = _render_morning(ctx, user, user_now)

    _validate_output(output)
    return output


# ---------------------------------------------------------------------------
# MORNING BRIEFING
# ---------------------------------------------------------------------------

def _render_morning(ctx, user, user_now) -> str:
    """Morning briefing — CoS contract: greeting, situation, plan, day view.

    Structure:
    A. Opening — greeting + situation awareness
    B. Immediate plan — 1-2 next actions + constraint anchor
    C. Full-day view — key items later today (medications, priorities)
    D. Closing — directional statement
    """
    lines = []
    first_name = getattr(user, 'first_name', '') or ''
    hour = user_now.hour

    # ── A. Opening: Greeting + Situation ──
    if hour < 5:
        lines.append(f"Early start{', ' + first_name if first_name else ''}.")
    elif hour < 9:
        lines.append(
            f"Good morning{', ' + first_name if first_name else ''}."
        )
    else:
        lines.append(f"Morning{', ' + first_name if first_name else ''}.")

    overdue = ctx.get("overdue", [])
    coming_up = ctx.get("coming_up", [])
    completed = ctx.get("completed", [])
    later = ctx.get("later", [])

    _state, situation = _assess_situation_structured(
        overdue, completed, coming_up, user_now,
    )
    lines.append("")
    lines.append(situation)

    # ── B. Immediate Plan: next actions + anchor ──
    triage = _build_morning_triage(
        ctx, user_now, overdue, coming_up, later,
        situation_state=_state,
    )
    if triage:
        lines.append("")
        lines.append(triage)

    # Completed acknowledgment (brief, only if some done)
    if completed:
        names = [e['label'] for e in completed[:3]]
        if len(completed) <= 3:
            lines.append("")
            lines.append(f"Already done: {', '.join(names)}.")
        else:
            lines.append("")
            lines.append(
                f"Already done: {', '.join(names)}, "
                f"+{len(completed) - 3} more."
            )

    # ── C. Full-Day View: key afternoon/evening items ──
    day_view = _build_full_day_view(ctx, user_now)
    if day_view:
        lines.append("")
        lines.append(day_view)

    # ── D. Closing: directional ──
    closing = _morning_closing(_state, completed, overdue, later, user_now)
    if closing:
        lines.append("")
        lines.append(closing)

    return "\n".join(lines)


def _build_full_day_view(ctx, user_now) -> str:
    """Build a brief view of key items later today.

    Priority order (max 4 items):
    1. Medications (highest — health-critical)
    2. Hard scheduled commitments (time-bound)
    3. Work priorities (payroll, 1-3-1, etc.)
    4. One supporting item if space allows
    """
    later = ctx.get("later", [])
    if not later:
        return ""

    # Categorize notable items with priority tiers
    medications = []
    commitments = []
    work_priorities = []

    for entry in later:
        item = entry.get('item', {})
        name = (item.get('name') or '').strip()
        source = item.get('source', '')
        priority = item.get('priority', '')
        time_str = item.get('time_str', '')
        name_lower = name.lower()
        label = f"{name} ({time_str})" if time_str else name

        is_medication = source == 'medication' or any(
            k in name_lower for k in ('mounjaro', 'medication', 'medicine')
        )
        is_commitment = any(
            k in name_lower
            for k in ('meeting', 'appointment', 'call', 'class')
        )
        is_work = any(
            k in name_lower for k in ('payroll', '1-3-1', 'standup')
        )
        is_high_priority = priority in ('foundational', 'high', 'important')

        if is_medication:
            medications.append(label)
        elif is_commitment:
            commitments.append(label)
        elif is_work or is_high_priority:
            work_priorities.append(label)

    # Assemble in priority order, max 4 items total
    notable = []
    for bucket in (medications, commitments, work_priorities):
        for item in bucket:
            if len(notable) >= 4:
                break
            notable.append(item)

    if not notable:
        return ""

    return "Later today: " + ", ".join(notable) + "."


def _morning_closing(state, completed, overdue, later, user_now=None) -> str:
    """Short directional closing line, rotating by day."""
    # Use a fixed fallback if user_now not provided (tests)
    from django.utils import timezone as _tz
    now = user_now or _tz.now()

    if state == 'ahead':
        return _rotating_phrase(_CLOSING_PHRASES_AHEAD, now)
    if state == 'behind':
        return _rotating_phrase(_CLOSING_PHRASES_BEHIND, now)
    if completed and len(completed) >= 2:
        return _rotating_phrase(_CLOSING_PHRASES_GOOD_START, now)
    if later:
        return _rotating_phrase(_CLOSING_PHRASES_DEFAULT, now)
    return ""


def _build_day_narrative(ctx, user_now) -> str:
    """Build a 1-sentence flow description of the day.

    Describes the shape of the day — not a list, not counts.
    Focuses on: morning structure → key commitment → general layout.
    """
    all_items = ctx.get("all_items", [])
    pending = [
        i for i in all_items
        if not i.get("completed") and i.get("scheduled_time")
    ]
    if not pending:
        return ""

    # Sort by time
    pending.sort(key=lambda i: i["scheduled_time"])

    # Find the key structural items
    morning_items = [
        i for i in pending
        if i["scheduled_time"].hour < 12
    ]
    afternoon_items = [
        i for i in pending
        if 12 <= i["scheduled_time"].hour < 17
    ]

    # Build narrative from morning flow
    if not morning_items:
        if afternoon_items:
            first = afternoon_items[0]
            return (
                f"Your first commitment is "
                f"{first['name']} at {first.get('time_str', '')}."
            )
        return ""

    # Describe the morning structure
    first = morning_items[0]
    last_morning = morning_items[-1]

    if len(morning_items) == 1:
        return (
            f"Your morning starts with {first['name']} "
            f"at {first.get('time_str', '')}."
        )

    # Find a "hard" commitment (shower, meeting, appointment)
    hard_commits = [
        i for i in morning_items
        if any(k in (i['name'] or '').lower() for k in (
            'shower', 'meeting', 'appointment', 'call', 'class',
        ))
    ]

    if hard_commits:
        anchor = hard_commits[0]
        before_anchor = [
            i for i in morning_items
            if i["scheduled_time"] < anchor["scheduled_time"]
        ]
        if before_anchor:
            return (
                f"Your morning leads into "
                f"{anchor['name']} at {anchor.get('time_str', '')}, "
                f"with {len(before_anchor)} "
                f"{'items' if len(before_anchor) != 1 else 'item'} "
                f"before that."
            )
        return (
            f"Your morning starts with {anchor['name']} "
            f"at {anchor.get('time_str', '')}."
        )

    # Generic: describe span
    return (
        f"Your morning runs from "
        f"{first.get('time_str', '')} through "
        f"{last_morning.get('time_str', '')}."
    )


def _assess_situation(overdue, completed, coming_up, user_now) -> str:
    """Determine situational state: behind / on track / ahead.

    Returns text description only. Use _assess_situation_structured()
    for both state enum and text.
    """
    _state, text = _assess_situation_structured(
        overdue, completed, coming_up, user_now,
    )
    return text


def _rotating_phrase(phrases, user_now):
    """Select a phrase deterministically based on day-of-year.

    Rotates through the phrase list so the same user sees different
    phrasing each day, without randomness or state.
    """
    idx = user_now.timetuple().tm_yday % len(phrases)
    return phrases[idx]


# ── Phrase banks for rotating variety ──
_ORIENTATION_PHRASES = (
    "Let's get your morning started.",
    "Fresh start — here's the plan.",
    "Morning's open. Let's set the pace.",
    "Time to get moving.",
)

_NUDGE_PHRASES = (
    "Running a bit late — let's get focused.",
    "Slightly behind — let's close the gap.",
    "A little late, but recoverable. Let's go.",
    "Not quite on schedule — let's tighten up.",
)

_BEHIND_PHRASES = (
    "You're behind this morning — let's prioritize.",
    "Several things are overdue. Focus on what matters most.",
    "Behind schedule — one step at a time.",
    "Late start. Let's cut to what counts.",
)

_AHEAD_PHRASES = (
    "You're ahead — solid position.",
    "Ahead of schedule. Nice work.",
    "Strong start — you've got margin.",
)

_CLOSING_PHRASES_DEFAULT = (
    "Keep this morning tight.",
    "Handle the next step, then move.",
    "Stay focused on what's in front of you.",
    "Keep the momentum going.",
    "One thing at a time — you've got this.",
)

_CLOSING_PHRASES_AHEAD = (
    "Keep that momentum.",
    "Strong position — stay sharp.",
    "Nice pace. Keep it going.",
)

_CLOSING_PHRASES_BEHIND = (
    "One thing at a time.",
    "Just the next step.",
    "Focus beats speed.",
    "Don't rush — be deliberate.",
)

_CLOSING_PHRASES_GOOD_START = (
    "Good start — keep it going.",
    "Solid progress already.",
    "Off to a good start.",
)


def _assess_situation_structured(overdue, completed, coming_up, user_now):
    """Determine situational state with graduated tone.

    Three tiers for overdue items based on severity:
    - orientation: items past schedule but user likely just starting day
      (no completions, items < 90 min overdue)
    - nudge: moderate lateness or some activity already
    - behind: clearly late (items 2+ hours overdue or many overdue)

    Phrases rotate by day-of-year for natural variety.

    Returns:
        (state, text) where state is 'behind' | 'on_track' | 'ahead'
    """
    has_overdue = len(overdue) > 0
    has_completed = len(completed) > 0
    hour = user_now.hour

    if has_overdue:
        # Calculate how far the most overdue item has slipped
        max_overdue_min = 0
        for entry in overdue:
            item = entry.get('item', {})
            sched = item.get('scheduled_time')
            if sched:
                delta = (user_now - sched).total_seconds() / 60
                if delta > max_overdue_min:
                    max_overdue_min = delta

        # Tier 1: Orientation — user just opening the app, items are
        # only slightly past schedule, nothing completed yet.
        if not has_completed and max_overdue_min < 90:
            return ('on_track', _rotating_phrase(_ORIENTATION_PHRASES, user_now))

        # Tier 2: Gentle nudge — moderate lateness or user has been
        # active but falling behind
        if max_overdue_min < 120 or len(overdue) <= 2:
            return ('behind', _rotating_phrase(_NUDGE_PHRASES, user_now))

        # Tier 3: Clearly behind — significant overdue items
        return ('behind', _rotating_phrase(_BEHIND_PHRASES, user_now))

    if has_completed and not coming_up:
        return ('ahead', _rotating_phrase(_AHEAD_PHRASES, user_now))

    if hour < 6 and not has_completed:
        return ('on_track', "Early start — you've got time to set the tone.")

    return ('on_track', "You're on track.")


def _build_morning_triage(
    ctx, user_now, overdue, coming_up, later,
    situation_state='on_track',
) -> str:
    """Time-aware feasibility triage (text-only wrapper).

    Returns: guidance text with DO NOW + MOVE LATER sections.
    """
    result = _build_triage_structured(
        ctx, user_now, overdue, coming_up, later,
        situation_state=situation_state,
    )
    return result['text']


def _build_triage_structured(
    ctx, user_now, overdue, coming_up, later,
    situation_state='on_track',
) -> dict:
    """Time-aware feasibility triage returning structured data + text.

    Returns dict with:
        do_now: list of {'name': str, 'duration_est': int}
        move_later: list of {'name': str, 'reason': str}
        next_commitment: str | None (the hard deadline name)
        adjustment_reason: str | None
        decision_required: bool
        sequence: list of str (explicit ordering)
        text: str (rendered guidance text)
    """
    result = {
        'do_now': [],
        'move_later': [],
        'next_commitment': None,
        'adjustment_reason': None,
        'decision_required': False,
        'sequence': [],
        'text': '',
    }

    # Collect actionable items: overdue + coming_up (not completed)
    actionable = []
    for item in overdue:
        raw = item.get('item', {})
        if not raw.get('completed'):
            actionable.append(raw)
    for item in coming_up:
        raw = item.get('item', {})
        if not raw.get('completed'):
            actionable.append(raw)

    if not actionable:
        # Nothing actionable — check for later items
        next_action = ctx.get('next', '')
        if next_action and next_action != "Start with your next planned item.":
            result['text'] = f"Start with {next_action}."
            result['sequence'] = [next_action]
        return result

    # Find next hard commitment (fixed-time item that acts as deadline)
    hard_deadline = None
    hard_deadline_name = None
    for bucket in [coming_up, later]:
        for entry in bucket:
            raw = entry.get('item', {})
            if raw.get('completed'):
                continue
            sched = raw.get('scheduled_time')
            name = raw.get('name', '')
            is_hard = any(
                k in (name or '').lower()
                for k in ('shower', 'meeting', 'appointment', 'call',
                          'class', 'mounjaro', 'medication')
            )
            if is_hard and sched and sched > user_now:
                hard_deadline = sched
                hard_deadline_name = name
                break
        if hard_deadline:
            break

    result['next_commitment'] = hard_deadline_name

    if not hard_deadline:
        # No hard deadline found — just guide to start
        next_name = actionable[0].get('name', '')
        if len(actionable) == 1:
            result['text'] = f"Start with {next_name}."
            result['do_now'] = [{'name': next_name, 'duration_est': _estimate_duration(next_name)}]
            result['sequence'] = [next_name]
        else:
            names = [i.get('name', '') for i in actionable[:3]]
            result['text'] = f"Start with {names[0]}, then {', then '.join(names[1:])}."
            result['do_now'] = [
                {'name': n, 'duration_est': _estimate_duration(n)}
                for n in names
            ]
            result['sequence'] = names
        return result

    # Feasibility split: what fits before the deadline?
    available_minutes = max(
        0,
        int((hard_deadline - user_now).total_seconds() / 60),
    )

    do_now = []
    move_later = []
    time_used = 0

    def _sort_key(item):
        sched = item.get('scheduled_time')
        priority = 0 if item.get('priority') == 'foundational' else 1
        return (priority, sched or user_now)

    actionable.sort(key=_sort_key)

    for item in actionable:
        name = item.get('name', '')
        if name.lower() == (hard_deadline_name or '').lower():
            continue
        duration = _estimate_duration(name)
        if time_used + duration <= available_minutes:
            do_now.append(name)
            time_used += duration
        else:
            move_later.append(name)

    # Populate structured data
    result['do_now'] = [
        {'name': n, 'duration_est': _estimate_duration(n)} for n in do_now
    ]
    result['move_later'] = [
        {'name': n, 'reason': f"won't fit before {hard_deadline_name}"}
        for n in move_later
    ]
    result['sequence'] = do_now + [hard_deadline_name] + move_later
    if move_later:
        result['adjustment_reason'] = (
            f"Not enough time before {hard_deadline_name} at "
            f"{hard_deadline.strftime('%I:%M %p').lstrip('0')}"
        )
        result['decision_required'] = True

    # Build text output
    parts = []
    deadline_time_str = hard_deadline.strftime('%I:%M %p').lstrip('0')

    if do_now:
        # Lead with the first action, not a feasibility report
        parts.append(f"Start with {do_now[0]}.")
        if len(do_now) > 1:
            rest = do_now[1:]
            rest_str = ', then '.join(rest)
            parts.append(
                f"Then {rest_str} — all before "
                f"{hard_deadline_name} at {deadline_time_str}."
            )
        else:
            parts.append(
                f"{hard_deadline_name} is at {deadline_time_str}."
            )
    elif not move_later:
        next_action = ctx.get('next', '')
        if next_action:
            parts.append(f"Start with {next_action}.")

    # Only suggest rescheduling when user is behind — in orientation
    # or on-track states, premature reschedule suggestions feel
    # like pressure before the user has started.
    if move_later and situation_state == 'behind':
        if len(move_later) == 1:
            parts.append(
                f"{move_later[0]} can move to later today."
            )
        else:
            items_str = ' and '.join(
                [', '.join(move_later[:-1]), move_later[-1]]
                if len(move_later) > 2
                else move_later
            )
            parts.append(
                f"{items_str} can move to later today."
            )

    result['text'] = "\n".join(parts)
    return result


# ---------------------------------------------------------------------------
# MIDDAY ALIGNMENT
# ---------------------------------------------------------------------------

def _render_midday(ctx, user, user_now) -> str:
    """Midday alignment — progress, slipping, recalibrated guidance."""
    lines = []
    first_name = getattr(user, 'first_name', '') or ''

    # Greeting
    lines.append(f"Midday check{', ' + first_name if first_name else ''}.")

    # Progress narrative
    all_items = ctx.get("all_items", [])
    completed = ctx.get("completed", [])
    overdue = ctx.get("overdue", [])
    total = len(all_items)
    done = len(completed)

    lines.append("")
    if total > 0:
        if done == 0:
            lines.append("Nothing completed yet today.")
        elif done == total:
            lines.append("Everything's done. Clean sweep.")
        elif done >= total * 0.7:
            lines.append(
                f"Strong progress — {done} of {total} done."
            )
        elif done >= total * 0.4:
            lines.append(
                f"Halfway there — {done} of {total} done."
            )
        else:
            lines.append(
                f"Slow start — {done} of {total} done so far."
            )

    # Slipping items
    if overdue:
        lines.append("")
        if len(overdue) == 1:
            lines.append(
                f"{overdue[0]['label']} has slipped. "
                f"Can you get to it this afternoon?"
            )
        else:
            names = [e['label'] for e in overdue[:3]]
            lines.append(
                f"Slipping: {', '.join(names)}."
            )

    # Remaining
    coming_up = ctx.get("coming_up", [])
    later = ctx.get("later", [])
    remaining = coming_up + later
    if remaining:
        lines.append("")
        names = [e['label'] for e in remaining[:4]]
        lines.append(f"Still ahead: {', '.join(names)}.")

    # Next action
    next_action = ctx.get('next', '')
    if next_action and next_action != "Start with your next planned item.":
        lines.append("")
        lines.append(f"Focus on {next_action} next.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# EVENING DEBRIEF
# ---------------------------------------------------------------------------

def _render_evening(ctx, user, user_now) -> str:
    """Evening debrief — results, explicit misses, tomorrow."""
    lines = []
    first_name = getattr(user, 'first_name', '') or ''

    lines.append(
        f"End of day{', ' + first_name if first_name else ''}."
    )

    # Results
    all_items = ctx.get("all_items", [])
    completed = ctx.get("completed", [])
    total = len(all_items)
    done = len(completed)

    lines.append("")
    if total == 0:
        lines.append("Nothing was scheduled today.")
    elif done == total:
        lines.append("You completed everything today. Well done.")
    elif done >= total * 0.7:
        lines.append(f"Solid day — {done} of {total} done.")
    elif done > 0:
        lines.append(f"{done} of {total} done today.")
    else:
        lines.append("Tough day — nothing got checked off.")

    # What got done (brief)
    if completed and len(completed) <= 5:
        names = [e['label'] for e in completed]
        lines.append("")
        lines.append(f"Done: {', '.join(names)}.")
    elif completed:
        names = [e['label'] for e in completed[:4]]
        lines.append("")
        lines.append(
            f"Done: {', '.join(names)}, +{len(completed) - 4} more."
        )

    # Explicit misses
    overdue = ctx.get("overdue", [])
    coming_up = ctx.get("coming_up", [])
    later = ctx.get("later", [])
    missed = overdue + coming_up + later
    if missed:
        names = [e['label'] for e in missed[:4]]
        lines.append("")
        lines.append(f"Missed: {', '.join(names)}.")

    # Tomorrow's load
    try:
        from apps.core.utils import get_user_today
        from apps.life.models import Task
        today = get_user_today(user)
        tomorrow = today + timedelta(days=1)
        tomorrow_count = Task.objects.filter(
            user=user, due_date=tomorrow, deleted_at__isnull=True,
        ).exclude(completion_status='skipped').count()
        if tomorrow_count:
            lines.append("")
            lines.append(
                f"Tomorrow has {tomorrow_count} "
                f"thing{'s' if tomorrow_count != 1 else ''} lined up."
            )
    except Exception:
        pass

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_output(output: str):
    """Validate that output contains no domain/aggregation language."""
    output_lower = output.lower()
    for word in _BANNED_WORDS:
        if word in output_lower:
            logger.warning(
                "[CHECKIN RENDERER] VALIDATION: banned word '%s' found",
                word,
            )


# ---------------------------------------------------------------------------
# State guard — blocks LLM-generated state descriptions
# ---------------------------------------------------------------------------

_STATE_PATTERNS = [
    "you completed",
    "you've completed",
    "you have completed",
    "you have done",
    "you did your",
    "you did the",
    "you've done your",
    "you've done the",
    "you still need to",
    "you still need",
    "what's left",
    "on your plate",
    "your tasks include",
    "your remaining",
    "you haven't done",
    "you haven't completed",
    "which sets a solid tone",
    "sets a great tone",
    "solid start",
    "great start to",
    "productive morning",
    "productive start",
    "keep the momentum",
    "keep up the momentum",
    "let's keep the momentum",
]


def contains_state_language(text: str) -> bool:
    """Check if text contains LLM-generated state language."""
    if not text:
        return False
    text_lower = text.lower()
    return any(pattern in text_lower for pattern in _STATE_PATTERNS)


def guard_llm_output(llm_output: str, user) -> str:
    """Guard against LLM-generated state in output.

    If the LLM output contains state language, replace with
    the deterministic check-in renderer output.
    """
    if not contains_state_language(llm_output):
        return llm_output

    logger.warning(
        "[STATE GUARD] Blocked LLM state language for user=%s",
        user.id,
    )

    try:
        return render_checkin_for_time(user)
    except Exception:
        logger.error(
            "[STATE GUARD] Fallback renderer failed for user=%s",
            user.id, exc_info=True,
        )
        return _SAFE_FALLBACK
