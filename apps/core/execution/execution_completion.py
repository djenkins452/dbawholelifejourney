# =============================================================================
# File: apps/core/execution/execution_completion.py
# Purpose: EXECUTION COMPLETION ROUTER (Blocker #14, Layer 2). Records that an
#   execution item was completed, ON THE DATE IT ACTUALLY HAPPENED — reconciling
#   reality after the fact, not "when Danny finally told WLJ." It ROUTES to the
#   EXISTING per-domain completion writes (one source of truth; no duplicate
#   recording path) and, where a write is today-anchored, records on the actual
#   date by reusing the SAME model the truth reads from.
#
#   Governing rule (Danny): WLJ records when something HAPPENED, not when entered.
#   "Yes, I took my meds yesterday" updates YESTERDAY's execution.
#
#   Honest by construction: returns `recorded` only when the underlying write
#   succeeded; `already_complete` when nothing to do; `needs_info` when the item
#   can't be a bare check (journal needs content); `unsupported` when no safe
#   write exists yet. NEVER reports success it did not perform. Never raises.
# =============================================================================
import logging
from datetime import datetime, time

logger = logging.getLogger(__name__)


def _result(status, kind, title, *, message="", detail=None):
    return {"status": status, "kind": kind, "title": title,
            "message": message, "detail": detail or {}}


def _anchor_dt(target_date):
    """A tz-aware datetime anchored to NOON of the target day, so a retroactive
    completion's timestamp lands on the day it happened (never 'now', a different day)."""
    from django.utils import timezone
    naive = datetime.combine(target_date, time(12, 0))
    tz = timezone.get_current_timezone()
    try:
        return timezone.make_aware(naive, tz)
    except Exception:
        return timezone.make_aware(naive)


def complete_execution_item(user, kind, title, target_date, *, content=None):
    """Record completion of ONE execution item (identified by kind + title) on
    `target_date`, reusing the existing per-domain write. `content` carries the actual
    text for kinds that are content, not a checkbox (journal). Returns a structured,
    honest result. Never raises."""
    kind = (kind or "").strip().lower()
    try:
        if kind in ("medication", "medications", "supplement", "supplements"):
            return _complete_medications(user, title, target_date)
        if kind == "task":
            return _complete_task(user, title, target_date)
        if kind in ("routine", "routine_item"):
            return _complete_routine(user, title, target_date)
        if kind == "workout":
            return _complete_workout(user, title, target_date)
        if kind == "journal":
            return _complete_journal(user, title, target_date, content)
        if kind in ("prayer", "bible_reading", "bible"):
            return _complete_faith_via_routine(user, kind, title, target_date)
        return _result("unsupported", kind, title,
                       message=f"No completion write is wired for '{kind}' yet.")
    except Exception:
        logger.warning("execution_completion: %s '%s' failed", kind, title, exc_info=True)
        return _result("error", kind, title,
                       message="That completion could not be recorded; nothing was changed.")


# --- Journal: reconcile by CREATING the entry dated to the day it happened -----------------
def _complete_journal(user, title, target_date, content):
    """Journal is CONTENT, not a checkbox. With no content yet, ask for it (needs_info).
    Given the content, CREATE the journal entry dated to `target_date` via the canonical
    journal write — which (single source of truth: has_entry_on) reconciles that day's
    journal execution automatically. No second completion mechanism."""
    from apps.journal.services.journal_queries import JournalQueries
    text = (content or "").strip()
    if not text:
        if JournalQueries.has_entry_on(user, target_date):
            return _result("already_complete", "journal", title or "Journal")
        return _result("needs_info", "journal", title or "Journal",
                       message="A journal entry is its actual content, not a checkbox. Ask the "
                               "user what they wrote/reflected on for that day, then call this "
                               "again with `content` set — WLJ will create the entry dated to "
                               "that day, which marks the day's journal complete.")
    from apps.journal.services.journal_writes import create_entry
    entry = create_entry(user, body=text, entry_date=target_date)
    return _result("recorded", "journal", title or "Journal",
                   message=f"Created the journal entry for {target_date.isoformat()}; that day's "
                           f"journal is now complete.",
                   detail={"entry_id": entry.id, "entry_date": entry.entry_date.isoformat()})


# --- Medication / supplement: record the day's doses as taken (reuse the enumerator) -----
def _complete_medications(user, title, target_date):
    from apps.health.medicine_utils import get_expected_dose_entries
    from apps.health.models import Intake, IntakeLog
    entries = get_expected_dose_entries(user, target_date, target_date)  # (med_id, sched_id, day)
    if not entries:
        return _result("unsupported", "medications", title,
                       message="No medication doses were expected that day.")
    recorded, already = 0, 0
    for med_id, sched_id, day in entries:
        existing = IntakeLog.objects.filter(
            user=user, intake_id=med_id, schedule_id=sched_id, scheduled_date=day).first()
        if existing and existing.log_status in (IntakeLog.STATUS_TAKEN, IntakeLog.STATUS_LATE):
            already += 1
            continue
        log, _created = IntakeLog.objects.get_or_create(
            user=user, intake_id=med_id, schedule_id=sched_id, scheduled_date=day,
            defaults={"source": IntakeLog.SOURCE_LLM_ACTION})
        # mark_taken anchored to the ACTUAL day (retroactive), reusing the model's own write.
        log.mark_taken(taken_at=_anchor_dt(day), source=IntakeLog.SOURCE_LLM_ACTION)
        recorded += 1
    if recorded == 0 and already:
        return _result("already_complete", "medications", title,
                       detail={"already_taken": already})
    return _result("recorded", "medications", title,
                   message=f"Recorded {recorded} dose(s) taken for {target_date.isoformat()}.",
                   detail={"recorded": recorded, "already_taken": already})


# --- Task: occurrence-scoped completion (mark_complete keeps due_date = that day) ---------
def _complete_task(user, title, target_date):
    from apps.life.services.task_queries import TaskQueries
    match = None
    for t in TaskQueries.due_today(user, as_of=target_date):
        if (title or "").strip().lower() in (getattr(t, "title", "") or "").lower():
            match = t
            break
    if match is None:
        # Already complete for that day? (occurrence-scoped)
        for t in TaskQueries.completed_due_on(user, target_date):
            if (title or "").strip().lower() in (getattr(t, "title", "") or "").lower():
                return _result("already_complete", "task", title)
        return _result("unsupported", "task", title,
                       message="No pending task with that title was due that day.")
    match.mark_complete()  # occurrence-scoped by due_date; reconciles that day's occurrence
    return _result("recorded", "task", title,
                   message=f"Marked the task '{match.title}' complete.")


# --- Routine item: reuse toggle_routine_completion (first-class retroactive correction) ---
def _complete_routine(user, title, target_date, *, name_words=None):
    from apps.life.models import RoutineSchedule
    from apps.life.services.routine_helpers import toggle_routine_completion
    from apps.core.execution.completion_service import is_routine_item_complete
    dow = target_date.weekday()
    want = (title or "").strip().lower()
    schedules = [s for s in RoutineSchedule.objects.filter(
        routine__user=user, is_active=True).select_related("routine")]
    matched = []
    for s in schedules:
        nm = (getattr(s, "item_name", "") or getattr(getattr(s, "routine", None), "name", "")
              or "").lower()
        hit = (want and want in nm) if not name_words else any(w in nm for w in name_words)
        if hit and _schedule_applies(s, dow):
            matched.append(s)
    if not matched:
        return _result("unsupported", "routine", title,
                       message="No matching routine item was scheduled that day.")
    recorded, already = 0, 0
    for s in matched:
        try:
            if is_routine_item_complete(user, s, target_date):
                already += 1
                continue
        except Exception:
            pass
        toggle_routine_completion(user, s, target_date, completion_mode="scheduled")
        recorded += 1
    if recorded == 0 and already:
        return _result("already_complete", "routine", title, detail={"already": already})
    return _result("recorded", "routine", title,
                   message=f"Recorded {recorded} routine step(s) complete for "
                           f"{target_date.isoformat()}.", detail={"recorded": recorded})


def _schedule_applies(schedule, dow):
    try:
        return schedule.applies_to_day(dow)
    except Exception:
        return True  # fall back to permissive; the day match is best-effort


# --- Workout: reuse the model with the actual date -----------------------------------------
def _complete_workout(user, title, target_date):
    from apps.health.models import WorkoutSession
    exists = WorkoutSession.objects.filter(user=user, date=target_date).first()
    if exists:
        return _result("already_complete", "workout", title)
    WorkoutSession.objects.create(user=user, date=target_date,
                                  name=(title or "Workout"))
    return _result("recorded", "workout", title,
                   message=f"Recorded a workout for {target_date.isoformat()}.")


# --- Prayer / Bible: reconcile via the "Prayer Time" / "Bible Reading" routine item --------
def _complete_faith_via_routine(user, kind, title, target_date):
    words = (("pray",) if kind == "prayer" else ("bible", "scripture", "devotion"))
    res = _complete_routine(user, title, target_date, name_words=words)
    if res["status"] in ("recorded", "already_complete"):
        res["kind"] = kind
        return res
    return _result("unsupported", kind, title,
                   message=(f"{title} isn't tracked as a routine that day, and there is no "
                            f"other retroactive completion write for it yet."))
