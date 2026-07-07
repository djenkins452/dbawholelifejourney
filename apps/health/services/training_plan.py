# ==============================================================================
# File: apps/health/services/training_plan.py
# Capability: DETERMINISTIC TRAINING-PLAN READER.
#
# A Chief of Staff coaches WITHIN the user's intentional program — it does not react to
# an isolated workout count as if every session were random. This reads the user's
# structured weekly plan (the active WorkoutPlan + its WorkoutSchedule rotation) so
# recovery reasoning can tell the difference between "an intentional 6-day split with a
# built-in rest day" and "genuine overtraining". Read-only; never raises.
#
# Fields on the plan (apps/health/models.py): WorkoutPlan(is_active, days_per_week),
# WorkoutSchedule(day_of_week 0=Mon..6=Sun, template, is_rest_day). There is no
# strength/cardio TYPE field on the template, so type-alternation is a best-effort
# heuristic on template names — the deterministic core is has_plan + has_recovery_day.
# ==============================================================================
import logging

logger = logging.getLogger(__name__)

_STRENGTH_HINTS = ("strength", "lift", "weights", "resistance", "push", "pull", "legs",
                   "upper", "lower", "chest", "back", "squat", "deadlift")
_CARDIO_HINTS = ("cardio", "bike", "ride", "run", "pickleball", "swim", "row", "walk",
                 "conditioning", "hiit", "zone 2", "zone2")


def _kind(name):
    n = (name or "").lower()
    if any(h in n for h in _STRENGTH_HINTS):
        return "strength"
    if any(h in n for h in _CARDIO_HINTS):
        return "cardio"
    return "other"


def read_training_plan(user, today=None):
    """The user's intentional weekly training program, or a `has_plan=False` shell when
    there is none. Deterministic, read-only.

    Returns {
      "has_plan": bool,             # a structured active WorkoutPlan exists
      "has_recovery_day": bool,     # a rest day is built into the weekly rotation
      "days_per_week": int,         # training days in the plan
      "alternates": bool,           # workout TYPES alternate day-to-day (heuristic)
      "today_is_rest": bool,        # today is a planned rest day
      "today_type": str|None,       # today's planned template name
      "tomorrow_type": str|None,    # tomorrow's planned template name
    }
    """
    blank = {"has_plan": False, "has_recovery_day": False, "days_per_week": 0,
             "alternates": False, "today_is_rest": False, "today_type": None,
             "tomorrow_type": None}
    try:
        from apps.health.models import WorkoutPlan
        plan = (WorkoutPlan.objects.filter(user=user, is_active=True)
                .order_by("-id").first())
        if plan is None:
            return blank
        entries = list(plan.schedule_entries.select_related("template")
                       .order_by("day_of_week"))
        if not entries:
            return blank
        if today is None:
            from apps.core.utils import get_user_today
            today = get_user_today(user)
        wd = today.weekday()               # 0=Mon..6=Sun — matches day_of_week
        by_day = {e.day_of_week: e for e in entries}
        has_recovery_day = any(e.is_rest_day for e in entries)
        training_days = [e for e in entries if not e.is_rest_day]
        # Type alternation: do consecutive TRAINING days switch kind (strength↔cardio)?
        kinds = [_kind(getattr(e.template, "name", "")) for e in training_days]
        known = [k for k in kinds if k != "other"]
        alternates = (len(known) >= 3 and len(set(known)) >= 2
                      and all(known[i] != known[i + 1] for i in range(len(known) - 1)))

        def _slot(day):
            e = by_day.get(day)
            if e is None:
                return True, None                    # no entry → treat as open/rest
            if e.is_rest_day:
                return True, None
            return False, getattr(e.template, "name", None)
        today_is_rest, today_type = _slot(wd)
        _, tomorrow_type = _slot((wd + 1) % 7)
        return {
            "has_plan": True,
            "has_recovery_day": has_recovery_day,
            "days_per_week": (plan.days_per_week or len(training_days)),
            "alternates": alternates,
            "today_is_rest": today_is_rest,
            "today_type": today_type,
            "tomorrow_type": tomorrow_type,
        }
    except Exception:
        logger.warning("read_training_plan failed", exc_info=True)
        return blank
