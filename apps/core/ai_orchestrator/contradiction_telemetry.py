"""
Rollup-vs-Canonical Contradiction Telemetry.

Detects cases where a rollup_summary section claims completion while
canonical child items remain incomplete. Emits structured warnings for
operator visibility.

Examples detected:

    PRAYER_ROLLUP_VS_ITEMS  — domains.prayer == True but a routine item
        whose name is in FAITH_PRAYER_NAMES is still actionable.

    BIBLE_ROLLUP_VS_ITEMS   — same pattern for bible reading.

    MEDICATION_WINDOW_VS_DOSE — window all_taken == True but a dose
        in that window has status != 'taken' in the fresh schedule.

    WORKOUT_ROLLUP_VS_ITEMS / JOURNAL_ROLLUP_VS_ITEMS — same shape.

PURE module: no DB, no LLM. Operates only on pre-fetched state dicts.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)

# Matches the lowercased name set used by the bridge in
# apps/core/execution/execution_truth_engine.py.
_FAITH_PRAYER_NAMES = {"prayer", "prayer time", "morning prayer", "pray"}
_FAITH_BIBLE_NAMES = {
    "bible reading", "bible study", "scripture", "scripture reading",
    "read bible", "read scripture",
}
_WORKOUT_KEYWORDS = {"workout", "exercise", "training session"}
_JOURNAL_KEYWORDS = {"journal", "journal entry", "morning journal"}


@dataclass
class Contradiction:
    code: str
    rollup_section: str
    rollup_claim: str
    conflicting_items: List[dict] = field(default_factory=list)
    user_id: Optional[int] = None
    request_id: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "rollup_section": self.rollup_section,
            "rollup_claim": self.rollup_claim,
            "conflicting_items": self.conflicting_items,
            "user_id": self.user_id,
            "request_id": self.request_id,
        }


def _open_routine_items(items, name_set):
    """Return open (not completed, actionable) routine items whose
    lowercased title falls in `name_set`."""
    out = []
    for it in items or []:
        if it.get("source_type") != "routine_item":
            continue
        if it.get("completed_today"):
            continue
        if not it.get("is_actionable"):
            continue
        title = (it.get("title") or "").lower().strip()
        if title in name_set:
            out.append(it)
    return out


def _open_routine_items_by_keyword(items, keywords):
    """Return open routine items whose title contains any of the
    given keywords (substring match — used for workout/journal where
    titles vary)."""
    out = []
    for it in items or []:
        if it.get("source_type") != "routine_item":
            continue
        if it.get("completed_today"):
            continue
        if not it.get("is_actionable"):
            continue
        title = (it.get("title") or "").lower()
        if any(kw in title for kw in keywords):
            out.append(it)
    return out


def detect_contradictions(
    *,
    exec_state: dict,
    fresh_med_schedule: Optional[list] = None,
    user_id: Optional[int] = None,
    request_id: Optional[str] = None,
) -> List[Contradiction]:
    """Detect rollup-vs-canonical contradictions in a single execution
    state snapshot.

    Args:
        exec_state: dict from build_execution_state(user). Must contain
            'items' and 'summaries' (with 'domains' and 'medications').
        fresh_med_schedule: optional list of dose dicts from
            _fresh_module_state(user, 'medicine')['schedule_status_today'].
            When provided, enables MEDICATION_WINDOW_VS_DOSE detection.
        user_id, request_id: forwarded into emitted Contradiction
            records and telemetry log lines.

    Returns:
        list[Contradiction] — empty when nothing contradicts.
    """
    items = exec_state.get("items") or []
    summaries = exec_state.get("summaries") or {}
    domains = summaries.get("domains") or {}
    medications = summaries.get("medications") or {}

    found: List[Contradiction] = []

    # ── Faith rollup vs items ──────────────────────────────────────
    if domains.get("prayer"):
        offenders = _open_routine_items(items, _FAITH_PRAYER_NAMES)
        if offenders:
            found.append(Contradiction(
                code="PRAYER_ROLLUP_VS_ITEMS",
                rollup_section="DAILY EXECUTION STATUS",
                rollup_claim="prayer: DONE",
                conflicting_items=[{
                    "source_id": o.get("source_id"),
                    "title": o.get("title"),
                    "completion_status": o.get("completion_status"),
                } for o in offenders],
                user_id=user_id,
                request_id=request_id,
            ))

    if domains.get("bible_reading"):
        offenders = _open_routine_items(items, _FAITH_BIBLE_NAMES)
        if offenders:
            found.append(Contradiction(
                code="BIBLE_ROLLUP_VS_ITEMS",
                rollup_section="DAILY EXECUTION STATUS",
                rollup_claim="bible_reading: DONE",
                conflicting_items=[{
                    "source_id": o.get("source_id"),
                    "title": o.get("title"),
                    "completion_status": o.get("completion_status"),
                } for o in offenders],
                user_id=user_id,
                request_id=request_id,
            ))

    if domains.get("workout"):
        offenders = _open_routine_items_by_keyword(items, _WORKOUT_KEYWORDS)
        if offenders:
            found.append(Contradiction(
                code="WORKOUT_ROLLUP_VS_ITEMS",
                rollup_section="DAILY EXECUTION STATUS",
                rollup_claim="workout: DONE",
                conflicting_items=[{
                    "source_id": o.get("source_id"),
                    "title": o.get("title"),
                } for o in offenders],
                user_id=user_id,
                request_id=request_id,
            ))

    if domains.get("journal"):
        offenders = _open_routine_items_by_keyword(items, _JOURNAL_KEYWORDS)
        if offenders:
            found.append(Contradiction(
                code="JOURNAL_ROLLUP_VS_ITEMS",
                rollup_section="DAILY EXECUTION STATUS",
                rollup_claim="journal: DONE",
                conflicting_items=[{
                    "source_id": o.get("source_id"),
                    "title": o.get("title"),
                } for o in offenders],
                user_id=user_id,
                request_id=request_id,
            ))

    # ── Medication window rollup vs fresh schedule ─────────────────
    if fresh_med_schedule and medications:
        # Group fresh doses by window for comparison.
        fresh_by_window = {}
        for d in fresh_med_schedule:
            w = d.get("window_label") or "unscheduled"
            fresh_by_window.setdefault(w, []).append(d)

        for window_key, ws in medications.items():
            if not ws.get("all_taken"):
                continue
            # Window key in summaries is f"{group_type}_{window_label}".
            # Strip the group_type prefix to get the canonical window.
            label = window_key
            for prefix in ("medication_window_", "supplement_window_"):
                if label.startswith(prefix):
                    label = label[len(prefix):]
                    break
            doses = fresh_by_window.get(label) or []
            offenders = [
                d for d in doses
                if (d.get("status") or "").lower() not in ("taken", "skipped")
            ]
            if offenders:
                found.append(Contradiction(
                    code="MEDICATION_WINDOW_VS_DOSE",
                    rollup_section="MEDICATION PROGRESS",
                    rollup_claim=f"{ws.get('label', label)}: ALL TAKEN",
                    conflicting_items=[{
                        "medicine_name": d.get("medicine_name"),
                        "scheduled_time": d.get("scheduled_time"),
                        "status": d.get("status"),
                    } for d in offenders],
                    user_id=user_id,
                    request_id=request_id,
                ))

    if found:
        for c in found:
            logger.warning(
                "ROLLUP_CONTRADICTION_WARNING user=%s request=%s "
                "code=%s rollup='%s' conflicting=%d",
                user_id, request_id, c.code,
                c.rollup_claim, len(c.conflicting_items),
            )

    return found
