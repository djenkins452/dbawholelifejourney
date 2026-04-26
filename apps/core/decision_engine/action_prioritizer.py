"""
Shared Action Prioritizer — single source of truth for action ordering.

This module is PURE: no side effects, no DB writes, no LLM calls.
It takes normalized inputs and returns a prioritized list of action items.

Used by:
    - Dashboard V2 (display)
    - CoS context builder (explain/recommend)

Priority ordering (strict):
    1. foundational + overdue
    2. foundational + due now
    3. non-foundational + overdue
    4. non-foundational + due now
    5. foundational + next/upcoming
    6. non-foundational + next/upcoming

Foundational precedence per item:
    linked goal/habit/domain is_foundational > item-level is_foundational > False
"""

import datetime

# Canonical urgency ordering — lower = higher priority
URGENCY_ORDER = {"overdue": 0, "now": 1, "next": 2, "upcoming": 3, "done": 4}


def time_block_key_for(scheduled_time):
    """Round a time to the nearest 15-min block. Returns 'HH:MM' string or None.

    Public — exported so block-level completion endpoints can match
    Action Center grouping without re-implementing the rounding rule.
    """
    if scheduled_time is None:
        return None
    total_minutes = scheduled_time.hour * 60 + scheduled_time.minute
    rounded = (total_minutes // 15) * 15
    h, m = divmod(rounded, 60)
    return f"{h:02d}:{m:02d}"


def time_diff_minutes(now_time, target_time):
    """
    Calculate minutes from now_time to target_time (positive = future).
    Both are datetime.time objects.
    """
    now_mins = now_time.hour * 60 + now_time.minute
    target_mins = target_time.hour * 60 + target_time.minute
    return target_mins - now_mins


def classify_urgency(item_time, is_overdue, now_time):
    """
    Classify an item's urgency based on its time and overdue status.

    Args:
        item_time: datetime.time or None
        is_overdue: bool
        now_time: datetime.time (user's local time)

    Returns:
        str: "overdue" | "now" | "next" | "upcoming"
    """
    if is_overdue:
        return "overdue"
    if item_time is None:
        return "upcoming"
    delta = time_diff_minutes(now_time, item_time)
    if -5 <= delta <= 30:
        return "now"
    elif delta <= 120:
        return "next"
    return "upcoming"


def build_action_priorities(
    *,
    schedule_items=None,
    pending_routines=None,
    medicine_groups=None,
    binary_actions=None,
    current_time=None,
):
    """
    Build a prioritized list of ALL pending actionable items.

    All inputs are normalized dicts — the caller is responsible for
    converting ORM objects into this format.

    Args:
        schedule_items: list of dicts, each with:
            title, pk, time (datetime.time|None), is_overdue (bool),
            is_completed (bool), is_foundational (bool),
            source_url, can_complete, commitment_level, goal_name,
            type ("task"|"event"), time_display
        pending_routines: list of dicts, each with:
            title, pk, is_foundational (bool),
            source_url, commitment_level, goal_name
        medicine_groups: list of dicts, each with:
            title (label), time_of_day, is_foundational (bool),
            goal_name, all_taken (bool)
        binary_actions: list of dicts, each with:
            source ("journal"|"faith"|"workout"), title,
            source_url, is_foundational (bool), goal_name,
            is_done (bool)
        current_time: datetime.time — user's local time for urgency calc

    Returns:
        list of action item dicts, sorted by foundational + urgency.
        Each item has: source, urgency, type, pk, title, source_url,
        can_complete, is_foundational, commitment_level, goal_name,
        time_of_day, time_display
    """
    actions = []
    now_time = current_time or datetime.time(12, 0)

    # ── Schedule items (overdue + time-aware) ──
    for item in (schedule_items or []):
        if item.get("is_completed"):
            continue

        urgency = classify_urgency(
            item.get("time"), item.get("is_overdue", False), now_time
        )

        actions.append({
            "source": "schedule",
            "urgency": urgency,
            "type": item.get("type", "task"),
            "pk": item.get("pk"),
            "title": item["title"],
            "source_url": item.get("source_url", ""),
            "can_complete": item.get("can_complete", False),
            "is_foundational": item.get("is_foundational", False),
            "commitment_level": item.get("commitment_level", ""),
            "goal_name": item.get("goal_name", ""),
            "time_of_day": None,
            "time_display": item.get("time_display", ""),
        })

    # ── Pending routines ──
    for item in (pending_routines or []):
        # Classify urgency from scheduled time (if available) instead
        # of always defaulting to "next". Routine items use a wider
        # "now" window (45 min past scheduled time) because routines
        # represent activity blocks, not point-in-time deadlines.
        _r_time = item.get("time")
        _r_overdue = item.get("is_overdue", False)
        if _r_time and not _r_overdue:
            _r_delta = time_diff_minutes(now_time, _r_time)
            if -45 <= _r_delta <= 30:
                _r_urgency = "now"
            elif _r_delta < -45:
                _r_urgency = "next"  # Past window but not flagged overdue
            elif _r_delta <= 120:
                _r_urgency = "next"
            else:
                _r_urgency = "upcoming"
        else:
            _r_urgency = classify_urgency(_r_time, _r_overdue, now_time)
        action = {
            "source": "routine",
            "urgency": _r_urgency,
            "type": "task",
            "pk": item["pk"],
            "title": item["title"],
            "source_url": item.get("source_url", ""),
            "can_complete": True,
            "is_foundational": item.get("is_foundational", False),
            "commitment_level": item.get("commitment_level", ""),
            "goal_name": item.get("goal_name", ""),
            "time_of_day": None,
            "time_display": item.get("time_display", ""),
        }
        if item.get("toggle_url"):
            action["toggle_url"] = item["toggle_url"]
        actions.append(action)

    # ── Untaken medicine groups ──
    for g in (medicine_groups or []):
        if g.get("all_taken"):
            continue
        # Use time-aware urgency: overdue meds are urgent, not "next"
        if g.get("has_overdue"):
            med_urgency = "overdue"
        else:
            _med_time = _parse_time(g.get("scheduled_time"))
            med_urgency = classify_urgency(_med_time, False, now_time)
        actions.append({
            "source": "intake",
            "urgency": med_urgency,
            "type": "medicine_group",
            "pk": None,
            "title": g["title"],
            "source_url": "",
            "can_complete": True,
            "is_foundational": g.get("is_foundational", False),
            "commitment_level": "",
            "goal_name": g.get("goal_name", ""),
            "time_of_day": g.get("time_of_day", ""),
            # Surface the group's scheduled_time so intra-tier sort
            # respects time order (was empty string, which collapsed
            # all medicine groups to end-of-day in the time sort).
            "time_display": g.get("scheduled_time", "") or "",
        })

    # ── Binary daily actions (journal, faith, workout) ──
    for item in (binary_actions or []):
        if item.get("is_done"):
            continue
        actions.append({
            "source": item["source"],
            "urgency": "next",
            "type": "link",
            "pk": None,
            "title": item["title"],
            "source_url": item.get("source_url", ""),
            "can_complete": False,
            "is_foundational": item.get("is_foundational", False),
            "commitment_level": "",
            "goal_name": item.get("goal_name", ""),
            "time_of_day": None,
            "time_display": "",
        })

    # ── Sort: urgency first, then by time, then foundational, then title ──
    # Time-first ordering ensures "what to do next" is clear regardless of type.
    actions.sort(key=lambda a: (
        URGENCY_ORDER.get(a["urgency"], 9),
        _parse_time(a.get("time_display")) or datetime.time(23, 59),
        not a["is_foundational"],
        a["title"],
    ))

    return actions


def prioritize_execution_items(execution_items, current_time, summaries=None):
    """
    Adapter: convert ExecutionItem dicts from the authoritative execution contract
    into the format build_action_priorities() expects, then prioritize.

    This is the PREFERRED entry point for consumers of the execution contract.

    Args:
        execution_items: list of ExecutionItem dicts from build_today_execution()
        current_time: datetime.time — user's local time
        summaries: optional dict — execution summaries for binary domain actions

    Returns:
        Sorted list of action dicts (same format as build_action_priorities output).
    """
    # Map execution items → action prioritizer's schedule_items + pending_routines
    schedule_items = []
    pending_routines = []
    medicine_groups_map = {}  # window → {total, taken, ...}

    for item in execution_items:
        if not item.get('is_actionable', False):
            continue
        # Belt-and-suspenders: never surface completed items even if
        # is_actionable was set incorrectly upstream.
        if item.get('completed_today'):
            continue

        if item['source_type'] == 'task':
            schedule_items.append({
                'title': item['title'],
                'pk': item['source_id'],
                'time': _parse_time(item.get('scheduled_time')),
                'time_display': item.get('scheduled_time', ''),
                'is_overdue': item['time_status'] == 'overdue',
                'is_completed': False,
                'is_foundational': item.get('is_foundational', False),
                'source_url': item.get('detail_url', ''),
                'can_complete': True,
                'commitment_level': item.get('importance', 'important'),
                'goal_name': '',
                'type': 'task',
                'is_all_day': False,
            })
        elif item['source_type'] == 'routine_item':
            # Pass scheduled_time so routines get proper urgency
            # classification (now/next/upcoming) instead of always "next"
            _routine_time = _parse_time(item.get('scheduled_time'))
            _routine_overdue = item.get('time_status') == 'overdue'
            pending_routines.append({
                'pk': item['source_id'],
                'title': item['title'],
                'source_url': item.get('detail_url', ''),
                'is_foundational': item.get('is_foundational', False),
                'commitment_level': item.get('importance', 'flexible'),
                'goal_name': item.get('parent_title', ''),
                'toggle_url': item.get('toggle_url', ''),
                'time': _routine_time,
                'time_display': item.get('scheduled_time', ''),
                'is_overdue': _routine_overdue,
            })
        elif item['source_type'] in ('medication_dose', 'supplement_dose'):
            # Use group_type + window as key to keep medications and supplements separate
            group_type = item.get('execution_group_type', 'medication_window')
            window = item.get('execution_group_id', 'unscheduled')
            group_key = f"{group_type}_{window}"
            is_foundational = item.get('is_foundational', item['source_type'] == 'medication_dose')
            if group_key not in medicine_groups_map:
                medicine_groups_map[group_key] = {
                    'title': item.get('parent_title', window),
                    'time_of_day': window,
                    'is_foundational': is_foundational,
                    'goal_name': '',
                    'all_taken': False,
                    'total': 0,
                    'taken': 0,
                    'has_overdue': False,
                    'scheduled_time': item.get('scheduled_time'),
                    'group_type': group_type,
                }
            medicine_groups_map[group_key]['total'] += 1
            if item.get('completed_today'):
                medicine_groups_map[group_key]['taken'] += 1
            # Track if any dose in this window is overdue
            if item.get('time_status') == 'overdue':
                medicine_groups_map[group_key]['has_overdue'] = True

    # Finalize medicine groups
    medicine_groups = []
    for ws in medicine_groups_map.values():
        ws['all_taken'] = ws['taken'] >= ws['total'] and ws['total'] > 0
        medicine_groups.append(ws)

    # Binary actions from summaries — ONLY include expected domains
    binary_actions = []
    if summaries and summaries.get('domains'):
        domains = summaries['domains']
        expected = summaries.get('expected', {})
        _binary_map = [
            ('journal', 'Write in journal', '/journal/', 'journal'),
            ('faith_engaged', 'Bible reading', '/faith/reading-plans/', 'faith'),
            ('workout', 'Log a workout', '/health/fitness/', 'workout'),
        ]
        for key, title, url, expected_key in _binary_map:
            # Skip domains not expected today (e.g., no workout on Sunday)
            if not expected.get(expected_key, False):
                continue
            binary_actions.append({
                'source': key,
                'title': title,
                'source_url': url,
                'is_done': domains.get(key, False),
                'is_foundational': False,
                'goal_name': '',
            })

    return build_action_priorities(
        schedule_items=schedule_items,
        pending_routines=pending_routines,
        medicine_groups=medicine_groups,
        binary_actions=binary_actions,
        current_time=current_time,
    )


def _parse_time(time_str):
    """Parse time string to datetime.time, or None.

    Accepts:
    - 'HH:MM' (24-hour, canonical)
    - 'h:MM AM/PM' or 'HH:MM AM/PM' (12-hour, from state_builder)
    - datetime.time objects (passthrough)
    """
    if not time_str:
        return None
    if isinstance(time_str, datetime.time):
        return time_str
    try:
        from datetime import datetime as _dt
        # Try 24-hour first (canonical format from execution contract)
        return _dt.strptime(time_str.strip(), '%H:%M').time()
    except (ValueError, TypeError, AttributeError):
        pass
    try:
        from datetime import datetime as _dt
        # Fallback: 12-hour format (defense-in-depth for any unNormalized path)
        return _dt.strptime(time_str.strip(), '%I:%M %p').time()
    except (ValueError, TypeError, AttributeError):
        return None


def group_actions(actions):
    """
    Group action items into NOW / NEXT / LATER categories.

    Args:
        actions: list of action item dicts (from build_action_priorities)

    Returns:
        dict with keys: "now", "next", "later" — each a list of items.
    """
    return {
        "now": [a for a in actions if a["urgency"] in ("overdue", "now")],
        "next": [a for a in actions if a["urgency"] == "next"],
        "later": [a for a in actions if a["urgency"] == "upcoming"],
    }


def find_next_upcoming(actions, future_medicine_groups=None, schedule_later=None):
    """
    Find the next upcoming item for "All Clear" closure state.
    Deterministic — no LLM, no CoS.

    Returns:
        dict with title + time_display, or None.
    """
    # Check future medicine groups first
    for g in (future_medicine_groups or []):
        if not g.get("all_taken"):
            return {"title": g.get("title", g.get("label", "")), "time_display": ""}

    # Check later schedule items
    for item in (schedule_later or []):
        return {"title": item["title"], "time_display": item.get("time_display", "")}

    return None


# ── Grouped Action Center ────────────────────────────────────────────
#
# The unified Action Center replaces separate routine/medicine/schedule
# cards. It includes ALL items (completed and pending), grouped by their
# execution group (routine, medication window, standalone task).
#
# This function does NOT replace build_action_priorities or
# prioritize_execution_items — those remain for CoS context and
# backward compatibility. This is a NEW presentation-layer builder.


def build_grouped_action_center(execution_items, current_time, summaries=None):
    """
    Build grouped action center data from the execution contract.

    Unlike prioritize_execution_items, this:
    - Includes ALL items (completed + pending)
    - Groups items by execution_group (routine, medication window, standalone)
    - Returns structured data for the unified Action Center template

    Args:
        execution_items: list of ExecutionItem dicts from build_today_execution()
        current_time: datetime.time — user's local time
        summaries: optional dict — execution summaries for binary domain actions

    Returns:
        dict with:
            groups: list of group dicts, sorted by urgency then foundational
            total_items: int
            completed_items: int
            all_done: bool
            phase_groups: {"now": [...], "upcoming": [...], "later": [...]}
    """
    now_time = current_time or datetime.time(12, 0)

    # Step 1: Build item dicts with urgency classification for ALL items
    all_items = []
    for item in execution_items:
        sched_time = _parse_time(item.get('scheduled_time'))
        is_overdue = item.get('time_status') == 'overdue'
        completed = item.get('completed_today', False)

        # Classify urgency for positioning.
        # Completed items in the past get "done" so they sort into a
        # chronological "Earlier" section — NOT into NOW or UPCOMING.
        # Incomplete items in the past are genuinely overdue.
        if sched_time:
            delta = time_diff_minutes(now_time, sched_time)
            if completed and delta < -5:
                # Completed and scheduled time is in the past → "done"
                urgency = "done"
            elif not completed and delta < -30:
                # Incomplete and well past scheduled time → overdue
                urgency = "overdue"
            elif item['source_type'] == 'routine_item':
                # Routine items: wider "now" window (45 min past)
                if -45 <= delta <= 30:
                    urgency = "now"
                elif delta <= 120:
                    urgency = "next"
                else:
                    urgency = "upcoming"
            else:
                urgency = classify_urgency(sched_time, is_overdue, now_time)
        else:
            urgency = classify_urgency(sched_time, is_overdue, now_time)

        # Format time for display (AM/PM)
        time_display = ''
        if sched_time:
            hour = sched_time.hour
            minute = sched_time.minute
            ampm = 'AM' if hour < 12 else 'PM'
            display_hour = hour % 12 or 12
            time_display = f"{display_hour}:{minute:02d} {ampm}"

        all_items.append({
            'source_type': item['source_type'],
            'source_id': item.get('source_id'),
            'title': item['title'],
            'domain': item.get('domain', 'life'),
            'importance': item.get('importance', 'flexible'),
            'urgency': urgency,
            'scheduled_time': sched_time,
            'time_display': time_display,
            'completed': completed,
            'completion_status': item.get('completion_status', 'pending'),
            'is_actionable': item.get('is_actionable', False),
            'is_foundational': item.get('is_foundational', False),
            'toggle_url': item.get('toggle_url', ''),
            'detail_url': item.get('detail_url', ''),
            'group_type': item.get('execution_group_type', 'standalone'),
            'group_id': item.get('execution_group_id'),
            'parent_title': item.get('parent_title', ''),
        })

    # Step 2: Add binary domain actions (journal, workout, faith)
    # BUT skip any that are already covered by a routine item (e.g., "Journal"
    # in Nightly Routine means we don't also need "Write in journal" standalone)
    if summaries and summaries.get('domains'):
        domains = summaries['domains']
        expected = summaries.get('expected', {})

        # Build set of activity_types already present in routine items
        _covered_activities = set()
        for item in all_items:
            if item['source_type'] == 'routine_item':
                # Check title-based matching for common activities
                title_lower = item['title'].lower()
                if 'journal' in title_lower:
                    _covered_activities.add('journal')
                if 'bible' in title_lower or 'reading' in title_lower:
                    _covered_activities.add('faith')
                if 'workout' in title_lower or 'exercise' in title_lower:
                    _covered_activities.add('workout')

        _binary_map = [
            ('journal', 'Write in journal', '/journal/', 'journal'),
            ('faith_engaged', 'Bible reading', '/faith/reading-plans/', 'faith'),
            ('workout', 'Log a workout', '/health/fitness/', 'workout'),
        ]
        for key, title, url, expected_key in _binary_map:
            if not expected.get(expected_key, False):
                continue
            # Skip if already covered by a routine item
            if expected_key in _covered_activities:
                continue
            is_done = domains.get(key, False)
            all_items.append({
                'source_type': 'binary',
                'source_id': None,
                'title': title,
                'domain': expected_key,
                'importance': 'flexible',
                'urgency': 'next',
                'scheduled_time': None,
                'time_display': '',
                'completed': is_done,
                'completion_status': 'completed' if is_done else 'pending',
                'is_actionable': not is_done,
                'is_foundational': False,
                'toggle_url': '',
                'detail_url': url,
                'group_type': 'standalone',
                'group_id': None,
                'parent_title': '',
                'source': key,
            })

    # Step 3: Sort ALL items globally by execution order (item-level, not group-level)
    #
    # IMPORTANCE_ORDER: critical=0 > foundational=1 > important=2 > standard=3 > flexible=4
    _IMPORTANCE_ORDER = {
        'foundational': 0, 'critical': 0,
        'important': 1, 'standard': 2,
        'flexible': 3, 'optimization': 3,
    }

    all_items.sort(key=lambda i: (
        URGENCY_ORDER.get(i['urgency'], 9),           # 1. urgency phase
        i['scheduled_time'] or datetime.time(23, 59),  # 2. actual scheduled time
        i['completed'],                                 # 3. incomplete before complete
        _IMPORTANCE_ORDER.get(i['importance'], 5),      # 4. priority/importance
        i['title'],                                     # 5. stable tie-breaker
    ))

    # Step 4: Group into TIME BLOCKS — items at the same time go together
    #
    # A time block is defined by (scheduled_time rounded to nearest 15 min).
    # Items within the same time block stay together regardless of type.
    # Unscheduled items (no scheduled_time) go into a separate "flexible" section.

    def _time_block_key(scheduled_time):
        """Round to nearest 15-min block for grouping. Returns HH:MM string or None."""
        return time_block_key_for(scheduled_time)

    def _time_block_display(block_key):
        """Convert HH:MM block key to display format (e.g., '6:00 PM')."""
        if not block_key:
            return 'Flexible'
        h, m = int(block_key[:2]), int(block_key[3:])
        ampm = 'AM' if h < 12 else 'PM'
        display_h = h % 12 or 12
        return f"{display_h}:{m:02d} {ampm}"

    # Build time blocks
    time_blocks = {}  # block_key → list of items
    flexible_items = []

    for item in all_items:
        bk = _time_block_key(item['scheduled_time'])
        if bk is None:
            flexible_items.append(item)
        else:
            if bk not in time_blocks:
                time_blocks[bk] = []
            time_blocks[bk].append(item)

    # Step 5: Convert time blocks into group dicts for the template
    #
    # Each time block becomes a group. The template renders groups with
    # their items. Group-level toggle (bulk complete) is preserved for
    # homogeneous groups (all items from same original execution group).

    result_groups = []

    for block_key in sorted(time_blocks.keys()):
        block_items = time_blocks[block_key]
        total_in_block = len(block_items)
        completed_in_block = sum(1 for i in block_items if i['completed'])

        # Determine the most urgent item in the block
        block_urgencies = [URGENCY_ORDER.get(i['urgency'], 9) for i in block_items]
        min_urg_val = min(block_urgencies) if block_urgencies else 9
        urg_map = {v: k for k, v in URGENCY_ORDER.items()}
        block_urgency = urg_map.get(min_urg_val, 'upcoming')

        # Time block as primary execution unit (Option C):
        # Every time block renders one parent control. Original group
        # type is no longer surfaced as the rendering branch — instead
        # we expose `intake_window` (when the block is purely intake
        # from one window) so the block-level completion endpoint can
        # preserve the canonical intake_group_log optimization without
        # the template needing branch logic.
        intake_windows = set()
        intake_only = bool(block_items)
        for item in block_items:
            gt = item.get('group_type', 'standalone')
            if gt in ('medication_window', 'supplement_window'):
                intake_windows.add((gt, item.get('group_id')))
            else:
                intake_only = False
        intake_window_key = (
            list(intake_windows)[0][1]
            if intake_only and len(intake_windows) == 1
            else None
        )

        result_groups.append({
            'group_type': 'time_block',
            'group_id': block_key,
            'title': _time_block_display(block_key),
            'time_block_key': block_key,
            'items': block_items,
            'total': total_in_block,
            'completed_count': completed_in_block,
            'all_complete': completed_in_block >= total_in_block and total_in_block > 0,
            'is_foundational': any(i['is_foundational'] for i in block_items),
            'urgency': block_urgency,
            'is_time_block': True,
            # Optimization hint for the block-level completion endpoint:
            # when set, this block is purely one intake window and may
            # be completed via the canonical intake_group_log pathway
            # (single window-level rollup) instead of per-dose dispatch.
            'intake_window_key': intake_window_key,
        })

    # ── HARD GUARD: no scheduled item may appear in flexible ──
    # If an item has a scheduled_time string but _parse_time returned None
    # (format mismatch), it would land here incorrectly. Catch and log.
    scheduled_ids = {i['source_id'] for bk_items in time_blocks.values() for i in bk_items}
    guarded_flexible = []
    for item in flexible_items:
        if item['source_id'] in scheduled_ids:
            continue  # Already in a time block — skip duplicate
        # If the raw item had a scheduled_time from an upstream source but it
        # wasn't parsed, that's a bug. Log it so we can fix the format upstream.
        raw_time = item.get('time_display') or ''
        if raw_time and item['scheduled_time'] is None:
            import logging as _log
            _log.getLogger(__name__).error(
                "HARD GUARD: item '%s' (source_type=%s, source_id=%s) has "
                "time_display='%s' but scheduled_time=None — time format not parsed. "
                "Fix the upstream time normalization.",
                item.get('title'), item.get('source_type'),
                item.get('source_id'), raw_time,
            )
        guarded_flexible.append(item)
    flexible_items = guarded_flexible

    # Add flexible/unscheduled section (distinct from scheduled timeline)
    if flexible_items:
        flex_completed = sum(1 for i in flexible_items if i['completed'])
        result_groups.append({
            'group_type': 'flexible',
            'group_id': 'flexible',
            'title': 'Flexible',
            'time_block_key': None,
            'items': flexible_items,
            'total': len(flexible_items),
            'completed_count': flex_completed,
            'all_complete': flex_completed >= len(flexible_items) and len(flexible_items) > 0,
            'is_foundational': any(i['is_foundational'] for i in flexible_items),
            'urgency': 'flexible',
            'is_time_block': False,
        })

    # Step 6: Split into phase buckets
    phase_groups = {
        'now': [g for g in result_groups
                if g['urgency'] in ('overdue', 'now')],
        'upcoming': [g for g in result_groups
                     if g['urgency'] == 'next'],
        'later': [g for g in result_groups
                  if g['urgency'] == 'upcoming'],
        'done': [g for g in result_groups
                 if g['urgency'] == 'done'],
        'flexible': [g for g in result_groups
                     if g['urgency'] == 'flexible'],
    }

    total = sum(g['total'] for g in result_groups)
    completed = sum(g['completed_count'] for g in result_groups)

    return {
        'groups': result_groups,
        'phase_groups': phase_groups,
        'total_items': total,
        'completed_items': completed,
        'all_done': completed >= total and total > 0,
        'has_items': total > 0,
    }
