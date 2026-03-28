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
URGENCY_ORDER = {"overdue": 0, "now": 1, "next": 2, "upcoming": 3}


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
        actions.append({
            "source": "medicine",
            "urgency": "next",
            "type": "medicine_group",
            "pk": None,
            "title": g["title"],
            "source_url": "",
            "can_complete": True,
            "is_foundational": g.get("is_foundational", False),
            "commitment_level": "",
            "goal_name": g.get("goal_name", ""),
            "time_of_day": g.get("time_of_day", ""),
            "time_display": "",
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

    # ── Sort: foundational first, then by urgency, then alphabetical ──
    actions.sort(key=lambda a: (
        not a["is_foundational"],
        URGENCY_ORDER.get(a["urgency"], 9),
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
        elif item['source_type'] == 'medication_dose':
            window = item.get('execution_group_id', 'unscheduled')
            if window not in medicine_groups_map:
                medicine_groups_map[window] = {
                    'title': item.get('parent_title', window),
                    'time_of_day': window,
                    'is_foundational': True,
                    'goal_name': '',
                    'all_taken': False,
                    'total': 0,
                    'taken': 0,
                }
            medicine_groups_map[window]['total'] += 1
            if item.get('completed_today'):
                medicine_groups_map[window]['taken'] += 1

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
    """Parse HH:MM string to datetime.time, or None."""
    if not time_str:
        return None
    try:
        from datetime import datetime as _dt
        return _dt.strptime(time_str, '%H:%M').time()
    except (ValueError, TypeError):
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

        # Classify urgency for positioning (even completed items get urgency
        # so they appear in the correct time group)
        if item['source_type'] == 'routine_item':
            if sched_time and not is_overdue:
                delta = time_diff_minutes(now_time, sched_time)
                if -45 <= delta <= 30:
                    urgency = "now"
                elif delta < -45:
                    urgency = "now"  # Past — show in NOW as completed/overdue
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

    # Step 3: Group items by execution group
    groups_map = {}  # (group_type, group_id) → group dict
    standalone_items = []

    for item in all_items:
        gt = item['group_type']
        gid = item['group_id']

        if gt == 'standalone' or gid is None:
            standalone_items.append(item)
        else:
            key = (gt, gid)
            if key not in groups_map:
                groups_map[key] = {
                    'group_type': gt,
                    'group_id': gid,
                    'title': item['parent_title'] or gt.replace('_', ' ').title(),
                    'items': [],
                    'total': 0,
                    'completed_count': 0,
                    'is_foundational': False,
                }
            group = groups_map[key]
            group['items'].append(item)
            group['total'] += 1
            if item['completed']:
                group['completed_count'] += 1
            if item['is_foundational']:
                group['is_foundational'] = True

    # Finalize groups
    result_groups = []
    for group in groups_map.values():
        group['all_complete'] = (
            group['completed_count'] >= group['total'] and group['total'] > 0
        )
        # Group urgency = most urgent pending item, or "now" if all complete
        pending_urgencies = [
            URGENCY_ORDER.get(i['urgency'], 9)
            for i in group['items'] if not i['completed']
        ]
        if pending_urgencies:
            min_urg = min(pending_urgencies)
            urg_map = {v: k for k, v in URGENCY_ORDER.items()}
            group['urgency'] = urg_map.get(min_urg, 'upcoming')
        else:
            # All complete — assign based on scheduled time of first item
            first_time = next(
                (i['scheduled_time'] for i in group['items'] if i['scheduled_time']),
                None,
            )
            if first_time:
                group['urgency'] = classify_urgency(first_time, False, now_time)
            else:
                group['urgency'] = 'now'

        # Sort items within group: pending first, then by scheduled time
        group['items'].sort(key=lambda i: (
            i['completed'],
            i['scheduled_time'] or datetime.time(23, 59),
        ))
        result_groups.append(group)

    # Wrap standalone items as single-item groups
    for item in standalone_items:
        result_groups.append({
            'group_type': 'standalone',
            'group_id': item.get('source_id'),
            'title': item['title'],
            'items': [item],
            'total': 1,
            'completed_count': 1 if item['completed'] else 0,
            'all_complete': item['completed'],
            'is_foundational': item['is_foundational'],
            'urgency': item['urgency'],
        })

    # Step 4: Sort groups — within each phase, pending first then completed
    result_groups.sort(key=lambda g: (
        URGENCY_ORDER.get(g['urgency'], 9),
        g['all_complete'],  # Completed groups after pending within same phase
        not g['is_foundational'],
        g['title'],
    ))

    # Step 5: Split into phase buckets — completed groups stay in their time phase
    phase_groups = {
        'now': [g for g in result_groups
                if g['urgency'] in ('overdue', 'now')],
        'upcoming': [g for g in result_groups
                     if g['urgency'] == 'next'],
        'later': [g for g in result_groups
                  if g['urgency'] == 'upcoming'],
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
