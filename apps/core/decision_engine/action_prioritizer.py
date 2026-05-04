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

Recovery contract additions (consumed by build_execution_state):
    - prioritize_execution_items now FILTERS out non-recoverable items
      and items suppressed by block collapse. Selectors must stay dumb.
    - compute_block_collapses() returns the structured BlockCollapse list
      with strategy ∈ {recover_partially, skip, defer}.
    - compute_at_risk() applies the strict risk horizon and suppresses
      non-dependency future risk when overdue exists.
    - apply_recovery_bucket_selection() re-orders the action list per
      RecoveryState.mode without blending buckets.
"""

import datetime
import logging

from apps.core.execution.constants import (
    AT_RISK_HORIZON_MINUTES,
    COLLAPSE_MIN_GROUP_SIZE,
    DEPENDENCY_RISK_HORIZON_MINUTES,
)
from apps.core.execution.recoverability import is_recoverable
from apps.core.execution.recovery_state import (
    NORMAL,
    RECOVERY,
    SHUTDOWN,
    STABILIZE,
)
from apps.core.execution.task_classifier import FLEXIBLE

logger = logging.getLogger(__name__)

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


def prioritize_execution_items(
    execution_items, current_time, summaries=None,
    suppressed_source_keys=None,
):
    """
    Adapter: convert ExecutionItem dicts from the authoritative execution contract
    into the format build_action_priorities() expects, then prioritize.

    This is the PREFERRED entry point for consumers of the execution contract.

    Args:
        execution_items: list of ExecutionItem dicts from build_today_execution()
            (each annotated with task_class / recovery_grace_minutes / is_reset_action)
        current_time: datetime.time — user's local time
        summaries: optional dict — execution summaries for binary domain actions
        suppressed_source_keys: optional set of (source_type, source_id) tuples
            whose items must NOT enter the action pool — supplied by the
            block-collapse layer in build_execution_state. Items in this
            set are filtered before any ranking happens.

    Returns:
        Sorted list of action dicts. Each action carries the upstream
        recovery metadata (task_class, is_reset_action, is_recoverable,
        domain) so selectors can filter without re-deriving.
    """
    suppressed = suppressed_source_keys or set()

    # Map execution items → action prioritizer's schedule_items + pending_routines
    schedule_items = []
    pending_routines = []
    medicine_groups_map = {}  # window → {total, taken, ...}

    # Source metadata index: action.pk + action.source → enrichment dict.
    # Used after build_action_priorities() to attach task_class /
    # is_reset_action / is_recoverable / domain to each action.
    meta_index = {}
    medicine_group_meta = {}  # group_key → {is_recoverable, task_class, ...}

    for item in execution_items:
        if not item.get('is_actionable', False):
            continue
        # Belt-and-suspenders: never surface completed items even if
        # is_actionable was set incorrectly upstream.
        if item.get('completed_today'):
            continue

        # Recovery filter: drop non-recoverable items (HARD_EXPIRED past
        # scheduled, WINDOWED past cutoff). They surface in expired_items
        # / collapsed_blocks / risk-mode foundational tracking instead.
        if not is_recoverable(item, current_time):
            continue

        # Block-collapse suppression — gate set by the upstream layer.
        src_key = (item.get('source_type'), item.get('source_id'))
        if src_key in suppressed:
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
            meta_index[('schedule', item['source_id'])] = {
                'task_class': item.get('task_class'),
                'is_reset_action': item.get('is_reset_action', False),
                'is_recoverable': True,  # filtered above
                'domain': item.get('domain'),
                'source_type': 'task',
                'source_id': item['source_id'],
            }
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
            meta_index[('routine', item['source_id'])] = {
                'task_class': item.get('task_class'),
                'is_reset_action': item.get('is_reset_action', False),
                'is_recoverable': True,
                'domain': item.get('domain'),
                'source_type': 'routine_item',
                'source_id': item['source_id'],
            }
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
            # Recovery metadata at the group level — most-foundational
            # classification wins; reset flag is OR-aggregated.
            mg_meta = medicine_group_meta.setdefault(group_key, {
                'task_class': item.get('task_class'),
                'is_reset_action': item.get('is_reset_action', False),
                'is_foundational': item.get('is_foundational', False),
                'domain': item.get('domain'),
                'source_type': item['source_type'],
                'source_id': group_key,
            })
            mg_meta['is_reset_action'] = (
                mg_meta['is_reset_action'] or item.get('is_reset_action', False)
            )
            if item.get('is_foundational'):
                mg_meta['is_foundational'] = True

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

    actions = build_action_priorities(
        schedule_items=schedule_items,
        pending_routines=pending_routines,
        medicine_groups=medicine_groups,
        binary_actions=binary_actions,
        current_time=current_time,
    )

    # Enrich each action with upstream recovery metadata so selectors and
    # downstream layers can read it without re-deriving. For medicine
    # groups (which have no pk) we look up by (source, group_key) where
    # group_key is the time_of_day field on the group dict.
    for a in actions:
        src = a.get('source')
        pk = a.get('pk')
        meta = None
        if src in ('schedule', 'routine') and pk is not None:
            meta = meta_index.get((src, pk))
        elif src == 'intake':
            window = a.get('time_of_day')
            # try medication_window then supplement_window
            for gt in ('medication_window', 'supplement_window'):
                meta = medicine_group_meta.get(f"{gt}_{window}")
                if meta:
                    break
        if meta:
            a['task_class'] = meta.get('task_class')
            a['is_reset_action'] = meta.get('is_reset_action', False)
            a['is_recoverable'] = meta.get('is_recoverable', True)
            a['domain'] = meta.get('domain')
            a['source_type'] = meta.get('source_type')
        else:
            # Binary actions and unmapped items: safe defaults.
            a.setdefault('task_class', None)
            a.setdefault('is_reset_action', False)
            a.setdefault('is_recoverable', True)
            a.setdefault('domain', a.get('source'))
            a.setdefault('source_type', None)

    return actions


# ── Block collapse ──────────────────────────────────────────────────

def compute_block_collapses(execution_items, current_time, active_block=None):
    """Group missed items in the same execution_group into BlockCollapse
    summaries with a deterministic strategy.

    A block collapses when:
      - It is NOT the currently active block, AND
      - It contains >= COLLAPSE_MIN_GROUP_SIZE open items where each
        item is either overdue or non-recoverable.

    Strategy assignment:
      recover_partially  block has >=1 recoverable foundational item.
                          Only those items remain in the action pool.
      skip               every item in the block is non-recoverable.
                          All items suppressed from the action pool.
      defer              recoverable but no foundational lever — the
                          block is parked. All items suppressed from
                          the action pool, but visible in summaries.

    Returns:
        dict:
            'collapses': list of {
                'group_type': str,
                'group_id': str,
                'parent_title': str,
                'item_count': int,
                'recoverable_count': int,
                'expired_count': int,
                'has_foundational_recoverable': bool,
                'strategy': 'recover_partially' | 'skip' | 'defer',
                'item_source_ids': list[(source_type, source_id)],
            }
            'suppressed_source_keys': set of (source_type, source_id) tuples
                that prioritize_execution_items must filter out.
    """
    active_name = (active_block or {}).get('name')
    groups = {}
    for it in (execution_items or []):
        if it.get('completed_today'):
            continue
        if not it.get('is_actionable', False):
            continue
        gtype = it.get('execution_group_type')
        gid = it.get('execution_group_id')
        if not gtype or not gid or gtype == 'standalone':
            continue
        # Only consider items that are overdue or non-recoverable; an
        # all-pending future block is not a candidate for collapse.
        is_late = it.get('time_status') == 'overdue'
        is_dead = not is_recoverable(it, current_time)
        if not (is_late or is_dead):
            continue
        # Skip the active block — its items are still being executed.
        if active_name and gid == active_name:
            continue
        groups.setdefault((gtype, gid), []).append(it)

    collapses = []
    suppressed = set()

    for (gtype, gid), items in groups.items():
        if len(items) < COLLAPSE_MIN_GROUP_SIZE:
            continue
        recoverable_items = [i for i in items if is_recoverable(i, current_time)]
        expired_items = [i for i in items if not is_recoverable(i, current_time)]
        foundational_recoverable = [
            i for i in recoverable_items if i.get('is_foundational')
        ]
        reset_recoverable = [
            i for i in recoverable_items if i.get('is_reset_action')
        ]
        # A "lever" is anything worth keeping in the action pool: a
        # foundational item OR a reset action. Both let the user
        # actually do something useful from the missed block.
        levers = list({
            (i.get('source_type'), i.get('source_id')): i
            for i in foundational_recoverable + reset_recoverable
        }.values())

        if not recoverable_items:
            strategy = 'skip'
            keep_keys = set()
        elif levers:
            strategy = 'recover_partially'
            keep_keys = {
                (i.get('source_type'), i.get('source_id')) for i in levers
            }
        else:
            strategy = 'defer'
            keep_keys = set()

        for i in items:
            key = (i.get('source_type'), i.get('source_id'))
            if key not in keep_keys:
                suppressed.add(key)

        parent_title = (
            items[0].get('parent_title')
            or f"{gtype.replace('_', ' ').title()}"
        )
        collapses.append({
            'group_type': gtype,
            'group_id': gid,
            'parent_title': parent_title,
            'item_count': len(items),
            'recoverable_count': len(recoverable_items),
            'expired_count': len(expired_items),
            'has_foundational_recoverable': bool(foundational_recoverable),
            'strategy': strategy,
            'item_source_ids': [
                (i.get('source_type'), i.get('source_id')) for i in items
            ],
        })

    return {
        'collapses': collapses,
        'suppressed_source_keys': suppressed,
    }


# ── Risk computation ────────────────────────────────────────────────

def compute_at_risk(actions, blocked_dependents, current_time):
    """Apply strict risk-horizon rules to the prioritized action list.

    Returns the subset that legitimately qualifies as "at risk":
      A. Any overdue item is at_risk by definition.
      B. Future items inside AT_RISK_HORIZON_MINUTES.
      C. Future items inside DEPENDENCY_RISK_HORIZON_MINUTES that
         participate in a dependency chain (their pk appears as a key
         in blocked_dependents — i.e., other tasks are gated on them).

    Suppression rule:
      If overdue items exist AND no dependency chain exists for a
      given future item, that future item is suppressed (returns
      empty future-list, overdue-only).
    """
    if not actions:
        return []

    overdue = [a for a in actions if a.get('urgency') == 'overdue']
    # When nothing is overdue, foundational now-tier items become the
    # at-risk fallback (they are about to slip).
    now_foundational = [
        a for a in actions
        if a.get('urgency') == 'now' and a.get('is_foundational')
    ]
    blocked_keys = set((blocked_dependents or {}).keys())

    def _delta_minutes(a):
        td = _parse_time(a.get('time_display'))
        if td is None:
            return None
        now_min = current_time.hour * 60 + current_time.minute
        sched_min = td.hour * 60 + td.minute
        return sched_min - now_min

    def _has_dependency(a):
        pk = a.get('pk')
        if pk is None:
            return False
        return f"task:{pk}" in blocked_keys or f"routine:{pk}" in blocked_keys

    future_at_risk = []
    for a in actions:
        if a.get('urgency') in ('overdue', 'now'):
            continue
        delta = _delta_minutes(a)
        if delta is None or delta < 0:
            continue
        if delta <= AT_RISK_HORIZON_MINUTES:
            future_at_risk.append(a)
        elif (
            delta <= DEPENDENCY_RISK_HORIZON_MINUTES
            and _has_dependency(a)
        ):
            future_at_risk.append(a)

    # Suppression: when overdue items exist, drop future items that do
    # NOT participate in a dependency chain. Overdue items remain.
    if overdue:
        future_at_risk = [a for a in future_at_risk if _has_dependency(a)]
        return overdue + future_at_risk

    # No overdue: now-tier foundational items become the leading risk
    # signal, with the same future-horizon set.
    return now_foundational + future_at_risk


# ── Recovery-mode bucket selection ──────────────────────────────────

def apply_recovery_bucket_selection(actions, recovery_state):
    """Re-order the action list per RecoveryState.mode without blending.

    NORMAL    pass-through.
    STABILIZE reset action(s) first; rest follows original order.
    RECOVERY  bucket order: reset → recoverable foundational overdue
              → quick-win recoverable overdue → next anchor.
    SHUTDOWN  essential-anchor only: foundational items remaining +
              flexible/upcoming-anchor; non-foundational overdue
              non-anchor items dropped from primary order.

    The function ONLY reorders / filters the list. It does not
    fabricate new actions.
    """
    if not actions or not recovery_state:
        return list(actions or [])

    mode = recovery_state.get('mode', NORMAL)

    if mode == NORMAL:
        return list(actions)

    def _is_reset(a):
        return bool(a.get('is_reset_action'))

    def _is_foundational(a):
        return bool(a.get('is_foundational'))

    def _is_overdue(a):
        return a.get('urgency') == 'overdue'

    if mode == STABILIZE:
        resets = [a for a in actions if _is_reset(a)]
        rest = [a for a in actions if not _is_reset(a)]
        return resets + rest

    if mode == RECOVERY:
        resets = [a for a in actions if _is_reset(a)]
        foundational_overdue = [
            a for a in actions
            if _is_foundational(a) and _is_overdue(a) and not _is_reset(a)
        ]
        quick_overdue = [
            a for a in actions
            if _is_overdue(a)
            and not _is_foundational(a)
            and not _is_reset(a)
        ]
        rest = [
            a for a in actions
            if a not in resets
            and a not in foundational_overdue
            and a not in quick_overdue
        ]
        return resets + foundational_overdue + quick_overdue + rest

    if mode == SHUTDOWN:
        # Keep foundational items (anchors) + items in the upcoming
        # "nightly" window; drop non-foundational overdue chatter.
        kept = []
        for a in actions:
            if _is_foundational(a):
                kept.append(a)
                continue
            # Allow forward-only non-overdue items; drop non-foundational
            # overdue items so we don't tell the user to "catch up" at 9PM.
            if not _is_overdue(a):
                kept.append(a)
        return kept

    return list(actions)


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
