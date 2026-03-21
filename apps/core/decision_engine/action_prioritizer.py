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
        action = {
            "source": "routine",
            "urgency": "next",
            "type": "task",
            "pk": item["pk"],
            "title": item["title"],
            "source_url": item.get("source_url", ""),
            "can_complete": True,
            "is_foundational": item.get("is_foundational", False),
            "commitment_level": item.get("commitment_level", ""),
            "goal_name": item.get("goal_name", ""),
            "time_of_day": None,
            "time_display": "",
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
            pending_routines.append({
                'pk': item['source_id'],
                'title': item['title'],
                'source_url': item.get('detail_url', ''),
                'is_foundational': item.get('is_foundational', False),
                'commitment_level': item.get('importance', 'flexible'),
                'goal_name': item.get('parent_title', ''),
                'toggle_url': item.get('toggle_url', ''),
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

    # Binary actions from summaries
    binary_actions = []
    if summaries and summaries.get('domains'):
        domains = summaries['domains']
        _binary_map = [
            ('journal', 'Write in journal', '/journal/'),
            ('faith_engaged', 'Bible reading', '/faith/reading-plans/'),
            ('workout', 'Log a workout', '/health/fitness/'),
        ]
        for key, title, url in _binary_map:
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
