# =============================================================================
# File: apps/core/execution/_sentinel_cert.py
# Purpose: TEMPORARY operator infra (Blocker #14 Layer 2 certification). Seeds a
#   DETERMINISTIC throwaway sentinel account with a realistic YESTERDAY across every
#   execution-item kind, so the Execution Completion router can be certified on the
#   LIVE production worker WITHOUT touching Danny's real execution history. After the
#   run the sentinel is hard-deleted → net data change ZERO.
#
#   Blast radius is bounded BY CONSTRUCTION: every function operates on ONE fixed
#   sentinel email and can never resolve, mutate, or delete any other user. Read-only
#   for the rest of the platform.
#
#   Lifecycle: this module + its endpoint are removed in one commit once Layer 2 is
#   customer-certified (see docs/wlj_claude_changelog.md; temporary-infra rule).
# =============================================================================
import logging
from datetime import time, timedelta

logger = logging.getLogger(__name__)

# The ONLY account this module may ever touch. Not a real person; never reused.
SENTINEL_EMAIL = "exec-sentinel-l2@wlj-cert.local"


# ── identity ────────────────────────────────────────────────────────────────
def _ensure_user():
    """Create (or fetch) the sentinel user, writes-enabled on the model-interface
    runtime, onboarded + terms-accepted so the real CoS pipeline runs fully."""
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from apps.users.models import TermsAcceptance, UserPreferences

    User = get_user_model()
    user, _created = User.objects.get_or_create(
        email=SENTINEL_EMAIL,
        defaults={"first_name": "Sentinel", "last_name": "Exec"})
    user.set_unusable_password()
    user.save(update_fields=["password"])

    prefs, _ = UserPreferences.objects.get_or_create(user=user)
    prefs.use_model_interface = True
    prefs.use_model_interface_writes = True
    prefs.has_completed_onboarding = True
    prefs.save()

    tv = (getattr(settings, "WLJ_SETTINGS", {}) or {}).get("TERMS_VERSION", "1.0")
    TermsAcceptance.objects.get_or_create(user=user, terms_version=tv)
    return user


def _get_user():
    from django.contrib.auth import get_user_model
    return get_user_model().objects.filter(email__iexact=SENTINEL_EMAIL).first()


# ── seed ────────────────────────────────────────────────────────────────────
def seed(day=None):
    """Purge, then seed a realistic YESTERDAY across all nine execution kinds:
    tasks, prayer, bible, medication, supplements, journal, morning/evening/nightly
    routines. All INCOMPLETE, so the certification conversation performs the writes.
    Returns the seed manifest + the resulting execution review (discovery proof)."""
    from apps.core.utils import get_user_today

    teardown()  # deterministic: always start from a clean sentinel
    user = _ensure_user()
    day = day or (get_user_today(user) - timedelta(days=1))
    manifest = {"tasks": [], "routines": [], "intakes": [], "journal_expectation": None}

    _seed_tasks(user, day, manifest)
    _seed_faith_routines(user, manifest)          # Prayer Time + Bible Reading
    _seed_daily_routines(user, manifest)          # Morning + Evening + Nightly (+Journal item)
    _seed_medications(user, day, manifest)        # medication + supplement doses

    from apps.core.execution.execution_review import build_execution_review
    return {"sentinel": SENTINEL_EMAIL, "day": day.isoformat(),
            "manifest": manifest, "review": build_execution_review(user, day)}


def _seed_tasks(user, day, manifest):
    from apps.life.models import Task
    for title in ("Call the pharmacy", "Submit the expense report"):
        Task.objects.create(user=user, title=title, due_date=day,
                            is_routine=False, completion_status="pending")
        manifest["tasks"].append(title)


def _routine(user, name):
    from apps.life.models import Routine
    return Routine.objects.create(user=user, name=name, is_active=True)


def _item(routine, name, hhmm):
    from apps.life.models import RoutineSchedule
    return RoutineSchedule.objects.create(
        routine=routine, name=name, scheduled_time=time(*hhmm),
        days_of_week="0,1,2,3,4,5,6", is_active=True)


def _seed_faith_routines(user, manifest):
    # Prayer + Bible each under their OWN routine whose NAME carries the faith word,
    # because the completion router matches routine items by ROUTINE name. That makes
    # each independently completable, and the review surfaces them as Prayer/Bible
    # (faith-word routine names are skipped from the routine list).
    pr = _routine(user, "Prayer Time")
    _item(pr, "Prayer Time", (6, 30))
    bi = _routine(user, "Bible Reading")
    _item(bi, "Bible Reading", (6, 45))
    manifest["routines"] += ["Prayer Time", "Bible Reading"]


def _seed_daily_routines(user, manifest):
    morning = _routine(user, "Morning Routine")
    _item(morning, "Make Bed", (7, 0))
    _item(morning, "Drink Water", (7, 15))
    evening = _routine(user, "Evening Routine")
    _item(evening, "Tidy Kitchen", (19, 0))
    _item(evening, "Prep Coffee", (19, 30))
    nightly = _routine(user, "Nightly Routine")
    _item(nightly, "Wind Down", (21, 30))
    _item(nightly, "Set Alarm", (21, 45))
    _item(nightly, "Journal", (22, 0))            # name ∈ JOURNAL_NAMES → journal expected
    manifest["routines"] += ["Morning Routine", "Evening Routine", "Nightly Routine"]
    manifest["journal_expectation"] = "Nightly Routine → 'Journal' item"


def _seed_medications(user, day, manifest):
    from apps.health.models import Intake, IntakeSchedule
    for name, itype, hhmm in (("Metformin (sentinel)", "medication", (8, 0)),
                              ("Atorvastatin (sentinel)", "medication", (20, 0)),
                              ("Vitamin D (sentinel)", "supplement", (8, 0))):
        med = Intake.objects.create(user=user, name=name, purpose="certification",
                                    intake_type=itype, start_date=day)
        IntakeSchedule.objects.create(intake=med, scheduled_time=time(*hhmm))
        manifest["intakes"].append(f"{name} [{itype}]")


# ── read-back (verification) ──────────────────────────────────────────────────
def read(day=None):
    """Return the execution review for the seeded day AND for today (to prove no
    completion bled to today), plus the raw execution truth and the underlying row
    counts that make idempotency / no-duplication auditable."""
    from apps.core.utils import get_user_today
    from apps.core.execution.execution_review import build_execution_review
    from apps.core.execution.execution_truth_engine import get_execution_truth

    user = _get_user()
    if not user:
        return {"error": "sentinel not seeded"}
    today = get_user_today(user)
    day = day or (today - timedelta(days=1))
    return {
        "sentinel": SENTINEL_EMAIL, "day": day.isoformat(), "today": today.isoformat(),
        "review_day": build_execution_review(user, day),
        "review_today": build_execution_review(user, today),
        "truth_day": get_execution_truth(user, day),
        "counts": _counts(user, day),
    }


def _counts(user, day):
    from apps.life.models import Task, RoutineLog
    from apps.health.models import IntakeLog, WorkoutSession
    from apps.journal.models import JournalEntry
    return {
        "tasks_completed_due_day": Task.objects.filter(
            user=user, completion_status="completed", due_date=day).count(),
        "routine_logs_day": list(RoutineLog.objects.filter(
            user=user, scheduled_date=day).values_list("log_status", flat=True)),
        "intake_logs_day": list(IntakeLog.objects.filter(
            user=user, scheduled_date=day).values_list("log_status", flat=True)),
        "intake_logs_today_leak": IntakeLog.objects.filter(
            user=user, scheduled_date=day + timedelta(days=1)).count(),
        "workout_sessions_day": WorkoutSession.objects.filter(user=user, date=day).count(),
        "journal_entries_day": JournalEntry.objects.filter(
            user=user, entry_date=day).count(),
    }


# ── teardown (net-zero) ────────────────────────────────────────────────────────
def teardown():
    """Hard-delete the sentinel user and everything it cascades to. Scoped to the one
    fixed sentinel email — can never touch a real account. Returns deletion counts."""
    user = _get_user()
    if not user:
        return {"sentinel": SENTINEL_EMAIL, "deleted": False, "reason": "did not exist"}
    uid = user.id
    deleted_total, per_model = user.delete()  # hard cascade (throwaway account)
    still = _get_user() is not None
    return {"sentinel": SENTINEL_EMAIL, "deleted": True, "user_id": uid,
            "rows_deleted": deleted_total, "per_model": per_model,
            "exists_after": still}
