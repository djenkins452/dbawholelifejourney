"""
Execution Facts — deterministic "did I / what's on" Canonical Truth (Layer 1, Batch 2).

These status questions (journaled today? worked out today? appointments today?
next appointment?) previously had NO deterministic provider — they declined
through every lane and landed on the tool-loop LLM (Law 4 break), even though the
truth already exists. This provider reads the canonical Domain Truth Contracts /
pre-computed SAE state and returns a small fact dict — "retrieve, never derive".

Calendar facts read the pre-computed SAE `calendar` module state (never compute on
the request path — AI Engineering Rules / F-laws).
"""
import logging

logger = logging.getLogger(__name__)

EXECUTION_FACT_KEYS = {"journal_today", "workout_today", "workout_yesterday",
                       "appointments_today", "next_appointment", "meals_today",
                       "meals_yesterday", "meds_today", "last_journal"}


def get_foundational_execution_facts(user, keys):
    """Return {key: {value, source} | {status: unknown/unsupported_fact}}."""
    out = {}
    for key in keys:
        try:
            out[key] = _resolve(user, key)
        except Exception:
            logger.warning("execution_facts: resolve failed key=%s user=%s",
                           key, getattr(user, "id", None), exc_info=True)
            out[key] = {"status": "unknown", "reason": "retrieval failed"}
    return out


def _resolve(user, key):
    from apps.core.utils import get_user_today
    from apps.core.truth.freshness import CURRENT
    today = get_user_today(user)

    # These are "as of now / today" status facts — the platform Freshness verdict is
    # CURRENT (a second domain consuming apps.core.truth.freshness, no duplicate logic).
    if key == "journal_today":
        from apps.journal.services.journal_queries import JournalQueries
        return {"value": bool(JournalQueries.has_entry_on(user, today)),
                "source": "JournalQueries", "freshness": CURRENT}

    if key in ("workout_today", "workout_yesterday"):
        from datetime import timedelta
        from apps.health.services.workout_queries import WorkoutQueries
        day = today if key == "workout_today" else today - timedelta(days=1)
        # A completed-day boolean: False ("you didn't") is a definitive answer, not
        # missing data → always CURRENT.
        return {"value": bool(WorkoutQueries.is_completed_on(user, day)),
                "source": "WorkoutQueries", "freshness": CURRENT}

    if key in ("appointments_today", "next_appointment"):
        return _calendar_fact(user, key)

    if key == "meds_today":
        # Pre-computed SAE medicine state (never compute adherence on the request path).
        from apps.core.ai_state.state_engine import get_module_state
        try:
            st = get_module_state(user, "medicine", allow_rebuild=False) or {}
        except Exception:
            st = {}
        expected = st.get("expected_today") or 0
        return {"value": st.get("today_taken", 0), "expected": expected,
                "missed": st.get("today_missed", 0), "pending": st.get("today_pending", 0),
                "source": "SAE.medicine", "freshness": CURRENT}

    if key == "last_journal":
        from apps.core.ai_state.state_engine import get_module_state
        try:
            st = get_module_state(user, "journal", allow_rebuild=False) or {}
        except Exception:
            st = {}
        last = st.get("last_entry")
        if not last:
            return {"status": "unknown", "freshness": "missing",
                    "reason": "no journal entries recorded"}
        return {"value": last, "days_since": st.get("days_since_entry"),
                "source": "SAE.journal", "freshness": CURRENT}

    if key in ("meals_today", "meals_yesterday"):
        # Retrieve the ACTUAL meals (by type), never leak storage concepts like
        # "food entry". NutritionQueries is the canonical per-meal source.
        from collections import OrderedDict
        from datetime import timedelta
        from apps.health.services.nutrition_queries import NutritionQueries
        day = today if key == "meals_today" else today - timedelta(days=1)
        by_meal = OrderedDict((m, []) for m in ("breakfast", "lunch", "dinner", "snack"))
        for e in NutritionQueries.entries_on_date(user, day):
            name = (e.food_name or "").strip()
            if name:
                by_meal.setdefault(e.meal_type or "snack", []).append(name)
        meals = {m: items for m, items in by_meal.items() if items}
        total = sum(len(v) for v in meals.values())
        return {"value": total, "meals": meals, "source": "NutritionQueries",
                "freshness": CURRENT}

    return {"status": "unsupported_fact", "supported": sorted(EXECUTION_FACT_KEYS)}


def _label(entry):
    title = (entry or {}).get("title") or "an event"
    start = (entry or {}).get("start")
    return f"{title} at {start}" if start else title


def _calendar_fact(user, key):
    # Pre-computed SAE state only — NEVER live-compute the calendar on the request path.
    from apps.core.ai_state.state_engine import get_module_state
    try:
        st = get_module_state(user, "calendar", allow_rebuild=False) or {}
    except Exception:
        logger.warning("execution_facts: calendar state read failed user=%s",
                       getattr(user, "id", None), exc_info=True)
        st = {}

    from apps.core.truth.freshness import CURRENT, MISSING
    if key == "appointments_today":
        events = st.get("today_events") or []
        return {"value": len(events),
                "items": [_label(e) for e in events],
                "source": "calendar_state", "freshness": CURRENT}

    nxt = st.get("next_event")
    if not nxt:
        return {"status": "unknown", "freshness": MISSING,
                "reason": "no upcoming appointment today"}
    return {"value": _label(nxt), "source": "calendar_state", "freshness": CURRENT}
