# ==============================================================================
# File: apps/ai/chatgpt_cos/workout_history.py
# Capability: WORKOUT RETRIEVAL / ENTITY COMPLETENESS (Workout treated like Sleep &
# Weight). The truth already exists (WorkoutQueries.completed_on + WorkoutSession.
# total_volume, which is load-aware); the gap was retrieval — "Did you see my
# workout?", "Over 40,000 lbs total", "did I work out on 7/2?" were search failures.
# This resolves the point in time (defaulting to TODAY when none is given, since a
# bare "did you see my workout?" means today) and reads the canonical completed-workout
# truth for that day: existence, total volume, duration. Deterministic; honest when a
# day has no completed workout.
# ==============================================================================
import logging

logger = logging.getLogger(__name__)

_WORKOUT_CUES = ("workout", "work out", "worked out", "working out", "lift", "lifted",
                 "lifting", "trained", "training", "gym", "exercise")
# Volume phrasings that imply a workout even without a workout word ("Over 40,000 lbs
# total", "total volume").
_VOLUME_PHRASES = ("lbs total", "pounds total", "total volume", "total lifted",
                   "how much did i lift", "how much have i lifted", "tonnage",
                   "lbs lifted", "pounds lifted")
_DURATION_CUES = ("how long", "duration", "how many minutes", "minutes did")


def _aggregate(sessions):
    sessions = list(sessions)
    if not sessions:
        return None
    volume = 0.0
    for s in sessions:
        try:
            volume += float(s.total_volume or 0)
        except Exception:
            pass
    duration = sum(int(getattr(s, "duration_minutes", 0) or 0) for s in sessions)
    names = [s.name for s in sessions if getattr(s, "name", "")]
    return {"count": len(sessions), "total_volume_lb": round(volume),
            "total_duration_min": duration, "names": names}


def answer(user, message, conversation=None):
    n = (message or "").lower()
    if not (any(c in n for c in _WORKOUT_CUES) or any(p in n for p in _VOLUME_PHRASES)):
        return None
    from apps.ai.chatgpt_cos.date_reference import (
        resolve_reference_date, fmt_date, user_today)
    target = resolve_reference_date(user, message, include_today=True)
    try:
        today = user_today(user)
    except Exception:
        return None
    if target is None:
        target = today                       # "did you see my workout?" → today

    try:
        from apps.health.services.workout_queries import WorkoutQueries
        agg = _aggregate(WorkoutQueries.completed_on(user, target))
    except Exception:
        logger.warning("workout_history: retrieval failed", exc_info=True)
        return None

    when = "today" if target == today else f"on {fmt_date(target)}"
    when_cap = "Today" if target == today else f"On {fmt_date(target)}"

    if agg is None:
        ans = f"I don't see a completed workout {when}."
    else:
        vol, dur, cnt = agg["total_volume_lb"], agg["total_duration_min"], agg["count"]
        sess = "session" if cnt == 1 else "sessions"
        want_volume = (any(p in n for p in _VOLUME_PHRASES) or "volume" in n
                       or ("lbs" in n and "total" in n) or ("pounds" in n and "total" in n))
        want_duration = any(c in n for c in _DURATION_CUES)
        if want_volume and vol:
            ans = f"{when_cap} you lifted {vol:,} lb of total volume across {cnt} {sess}."
        elif want_duration and dur:
            ans = f"{when_cap} you trained {dur} minutes across {cnt} {sess}."
        else:
            bits = []
            if agg["names"]:
                bits.append(", ".join(agg["names"]))
            if vol:
                bits.append(f"{vol:,} lb total volume")
            if dur:
                bits.append(f"{dur} min")
            detail = " — " + "; ".join(bits) if bits else ""
            ans = f"Yes, I see your workout {when}: {cnt} {sess}{detail}."

    return {"answer": ans, "tools_called": [], "tools_advertised": [],
            "lane": "workout_history", "workout_date": target.isoformat()}
