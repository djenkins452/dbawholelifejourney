"""
Health → Calendar activity descriptors.

The Calendar projects ACTIVITIES, not implementation details. Health owns the
canonical activity name for its projected items; the Calendar only groups and
renders them.

Nothing here is fabricated — every activity is derived from existing source
truth (IntakeSchedule.time_of_day + Intake.intake_type, WorkoutSchedule). The
Calendar never decides these names.

An "activity descriptor" is a plain dict:
    {key, label, icon, unit, url}
  - key   : grouping key. Events sharing a key on the same day collapse into one
            Calendar chip. Meds/supplements are keyed by (window, type) so the
            morning batch becomes ONE "Morning Medications"; workouts share a
            single "workout" key so multiple active plans collapse to one.
  - label : the user-facing activity name shown on the Calendar.
  - icon  : a single emoji.
  - unit  : singular noun for the count parenthetical ("medication"); empty when
            the activity should not show a count (workout).
  - url   : where clicking the activity opens (the owning module's experience).
"""

# Landing pages inside Health (the owning module — "how I do it" lives here).
_INTAKE_URL = "/health/physical/intake/"
_WORKOUT_URL = "/health/physical/fitness/workouts/"

# One workout activity regardless of how many active plans/schedules contribute.
WORKOUT_ACTIVITY = {
    "key": "workout",
    "label": "Workout",
    "icon": "🏋️",
    "unit": "",  # never show a count — it's one activity
    "url": _WORKOUT_URL,
}

# Fallback window ordering for display when time_of_day is blank.
_WINDOW_FALLBACK = [
    (11, "morning", "Morning"),
    (14, "lunch", "Lunch"),
    (17, "afternoon", "Afternoon"),
    (21, "evening", "Evening"),
    (24, "nightly", "Nightly"),
]


def _window(schedule):
    """(key_fragment, display) for a schedule's time-of-day window.

    Prefers the source-owned IntakeSchedule.time_of_day; falls back to the
    scheduled hour only when that field is blank.
    """
    from apps.health.models import IntakeSchedule

    tod = getattr(schedule, "time_of_day", "") or ""
    if tod:
        disp = dict(IntakeSchedule.TIME_OF_DAY_CHOICES).get(tod, tod.replace("_", " ").title())
        return tod, disp
    hour = schedule.scheduled_time.hour if schedule.scheduled_time else 9
    for cutoff, key, disp in _WINDOW_FALLBACK:
        if hour < cutoff:
            return key, disp
    return "daily", "Daily"


def medicine_activities(schedule_ids):
    """Map IntakeSchedule pks → activity descriptor.

    One bulk query (request-path safe, F5). Medication vs supplement comes from
    Intake.intake_type; the window comes from IntakeSchedule.time_of_day — both
    existing source truth. Keys collapse a window's doses into one activity:
    "Morning Medications" / "Morning Supplements".
    """
    from apps.health.models import Intake, IntakeSchedule

    out = {}
    ids = [i for i in schedule_ids if i]
    if not ids:
        return out
    rows = IntakeSchedule.objects.filter(pk__in=ids).select_related("intake")
    for s in rows:
        is_supp = getattr(s.intake, "intake_type", Intake.INTAKE_TYPE_MEDICATION) == \
            Intake.INTAKE_TYPE_SUPPLEMENT
        win_key, win_disp = _window(s)
        noun = "Supplements" if is_supp else "Medications"
        out[str(s.pk)] = {
            "key": "%s_%s" % (win_key, "supplements" if is_supp else "medications"),
            "label": "%s %s" % (win_disp, noun),
            "icon": "💊",
            "unit": "supplement" if is_supp else "medication",
            "url": _INTAKE_URL,
        }
    return out
