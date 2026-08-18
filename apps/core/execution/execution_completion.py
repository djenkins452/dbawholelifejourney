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


# ══════════════════════════════════════════════════════════════════════════════
# IDENTITY-FIRST COMPLETION (2026-08-18 production incident)
# ══════════════════════════════════════════════════════════════════════════════
# Execution truth already carries canonical identity for every executable object it
# surfaces (`source_type` + `source_id`, plus the same `toggle_url` the Dashboard button
# posts to). Before this, the ONLY way in here was `kind` + display TITLE, so the model
# had to translate a known object back into text and ask WLJ to rediscover it — which is
# how "Mark Shower complete" became a Task lookup that missed and then a claim that
# Shower might not be scheduled.
#
# ONE mapping, here, from the execution-truth vocabulary to this router's kind
# vocabulary. Unsupported source types FAIL CLOSED.
SOURCE_TYPE_TO_KIND = {
    "task": "task",
    "routine_item": "routine",
    "medication_dose": "medications",
    "supplement_dose": "medications",
}


def kind_for_source_type(source_type):
    """Deterministic vocabulary bridge. Returns None for an unsupported source type."""
    return SOURCE_TYPE_TO_KIND.get((source_type or "").strip().lower())


def _titles_agree(requested, resolved):
    """Deterministic target binding: does the resolved object match what was requested?

    Conservative and case/space-insensitive: either side containing the other counts as
    agreement ("Workout" vs "Workout (5 min)"), anything else does not. A SAFETY
    check, not a matcher — it never SELECTS an object, it only refuses one.
    """
    a = " ".join((requested or "").lower().split())
    b = " ".join((resolved or "").lower().split())
    if not a or not b:
        return True          # nothing to compare against — binding not asserted
    return a in b or b in a


def complete_by_identity(user, source_type, source_id, target_date,
                         requested_target=None):
    """Complete the EXACT occurrence identified by execution truth.

    Identity establishes the occurrence, so this never re-resolves from a display title
    and never inherits a default day. Delegates to the SAME domain-owned authority the
    corresponding UI control uses. Never raises.
    """
    st = (source_type or "").strip().lower()
    kind = kind_for_source_type(st)
    if kind is None:
        return _result("unsupported", st or "unknown", "",
                       message=f"'{source_type}' is not a completable execution type.",
                       detail={"resolution": "unsupported_source_type",
                               "establishes_absence": False})
    try:
        # TARGET INTEGRITY (2026-08-18). Resolve the object FIRST, verify it is the one
        # the user asked for, and only then mutate. requested -> resolved -> mutated must
        # be the same canonical object; a mismatch FAILS CLOSED and changes nothing.
        resolved = _peek_identity(user, st, source_id)
        if resolved is None:
            return _result("not_found", kind, requested_target or "",
                           message="That item no longer exists.",
                           detail={"resolution": "identity_not_found",
                                   "establishes_absence": True,
                                   "requested_target": requested_target,
                                   "source_id": source_id})
        if not _titles_agree(requested_target, resolved):
            logger.warning(
                "execution_completion: TARGET MISMATCH user=%s requested=%r "
                "resolved=%r source=%s/%s — refusing to mutate",
                getattr(user, "id", None), requested_target, resolved, st, source_id)
            return _result("target_mismatch", kind, resolved,
                           message=(f"That id belongs to '{resolved}', not "
                                    f"'{requested_target}'. I did not change anything."),
                           detail={"resolution": "target_mismatch",
                                   "establishes_absence": False,
                                   "requested_target": requested_target,
                                   "resolved_target": resolved,
                                   "source_id": source_id, "mutated": False})
        if st == "task":
            return _complete_task_by_id(user, source_id, target_date)
        if st == "routine_item":
            return _complete_routine_by_id(user, source_id, target_date)
        return _complete_dose_by_id(user, source_id, target_date, source_type=st)
    except Exception:
        logger.warning("execution_completion: identity completion failed %s/%s",
                       st, source_id, exc_info=True)
        return _result("error", kind, "",
                       message="That completion could not be recorded; nothing was changed.",
                       detail={"resolution": "error", "establishes_absence": False})


def _peek_identity(user, source_type, source_id):
    """Return the canonical TITLE of the owned object, or None. READ-ONLY — never writes.

    Ownership is enforced here: a foreign object resolves to None, so a mismatched or
    foreign id can never reach a mutation path.
    """
    try:
        if source_type == "task":
            from apps.life.models import Task
            row = Task.objects.filter(pk=source_id, user=user, status="active").first()
            return getattr(row, "title", None) if row else None
        if source_type == "routine_item":
            from apps.life.models import RoutineSchedule
            row = (RoutineSchedule.objects
                   .filter(pk=source_id, routine__user=user, is_active=True)
                   .select_related("routine").first())
            if not row:
                return None
            return (getattr(row, "item_name", "") or getattr(row, "name", "")
                    or getattr(getattr(row, "routine", None), "name", "") or "")
        from apps.health.models import IntakeSchedule
        row = (IntakeSchedule.objects.filter(pk=source_id, intake__user=user)
               .select_related("intake").first())
        return getattr(getattr(row, "intake", None), "name", None) if row else None
    except Exception:  # pragma: no cover - defensive; binding must fail closed
        logger.warning("execution_completion: identity peek failed %s/%s",
                       source_type, source_id, exc_info=True)
        return None


def _complete_task_by_id(user, source_id, target_date):
    """Delegate to the EXISTING canonical task authority (`Task.mark_complete`)."""
    from apps.life.models import Task
    task = Task.objects.filter(pk=source_id, user=user, status="active").first()
    if task is None:
        return _result("not_found", "task", "",
                       message="That task no longer exists.",
                       detail={"resolution": "identity_not_found",
                               "establishes_absence": True, "source_id": source_id})
    if getattr(task, "completion_status", "") == "completed":
        return _result("already_complete", "task", task.title,
                       detail={"source_id": source_id})
    task.mark_complete()
    return _result("recorded", "task", task.title,
                   message=f"Marked '{task.title}' complete.",
                   detail={"source_id": source_id})


def _complete_routine_by_id(user, source_id, target_date):
    """Delegate to `toggle_routine_completion` — the EXACT authority the Dashboard
    routine control posts to (`dashboard_v2:routine_schedule_toggle`)."""
    from apps.core.execution.completion_service import is_routine_item_complete
    from apps.life.models import RoutineSchedule
    from apps.life.services.routine_helpers import toggle_routine_completion

    schedule = (RoutineSchedule.objects
                .filter(pk=source_id, routine__user=user, is_active=True)
                .select_related("routine").first())
    if schedule is None:
        return _result("not_found", "routine", "",
                       message="That routine item no longer exists.",
                       detail={"resolution": "identity_not_found",
                               "establishes_absence": True, "source_id": source_id})
    title = (getattr(schedule, "item_name", "") or getattr(schedule, "name", "")
             or getattr(getattr(schedule, "routine", None), "name", "") or "")
    try:
        if is_routine_item_complete(user, schedule, target_date):
            return _result("already_complete", "routine", title,
                           detail={"source_id": source_id})
    except Exception:
        pass
    toggle_routine_completion(user, schedule, target_date, completion_mode="scheduled")
    return _result("recorded", "routine", title,
                   message=f"Marked '{title}' complete.",
                   detail={"source_id": source_id,
                           "occurrence_date": target_date.isoformat()})


def _complete_dose_by_id(user, source_id, target_date, *, source_type):
    """Delegate to the shared dose authority the Dashboard control also uses."""
    from apps.health.models import IntakeSchedule
    from apps.health.services.dose_completion import complete_dose

    schedule = (IntakeSchedule.objects
                .filter(pk=source_id, intake__user=user)
                .select_related("intake").first())
    if schedule is None:
        return _result("not_found", "medications", "",
                       message="That scheduled dose no longer exists.",
                       detail={"resolution": "identity_not_found",
                               "establishes_absence": True, "source_id": source_id})
    out = complete_dose(user, schedule, target_date)
    title = out.get("title", "")
    if out["status"] == "already_complete":
        return _result("already_complete", "medications", title,
                       detail={"source_id": source_id})
    if out["status"] == "not_applicable":
        return _result("unsupported", "medications", title,
                       message="That dose is not scheduled for that day.",
                       detail={"resolution": "not_scheduled_that_day",
                               "establishes_absence": False, "source_id": source_id})
    return _result("recorded", "medications", title,
                   message=f"Recorded '{title}' as taken.",
                   detail={"source_id": source_id,
                           "occurrence_date": target_date.isoformat()})


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
