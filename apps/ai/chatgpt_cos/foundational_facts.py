# ==============================================================================
# File: apps/ai/chatgpt_cos/foundational_facts.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Deterministic foundational-fact fast path (no tools, no agentic loop)
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-06-24
# ==============================================================================
"""
Foundation fact fast path.

For the five foundational fact prompts we do NOT use the agentic tool loop.
Instead:

    classify intent  ->  get_foundational_health_facts(keys)  ->  plain _call_api
    to phrase the already-retrieved truth  ->  answer.

This mirrors the proven OpenAI mechanism (plain ``ai_service._call_api`` — no
``tools``, no ``tool_choice``, no agentic loop). If ``_call_api`` fails for any
reason, we return a deterministic factual sentence built directly from the
retrieved payload, so the user NEVER sees an empty/failure response.

No legacy Beth, no Beth renderers, no Beth validators are involved.
"""

import json
import logging
import re

from apps.ai.cos_services.execution_facts import EXECUTION_FACT_KEYS

logger = logging.getLogger(__name__)

# Deterministic intent -> fact key map (narrow, foundational facts only).
# First keyword that matches wins; the five categories do not overlap.
_FACT_KEYWORDS = [
    ("current_weight",       ("weight", "weigh", "how much do i weigh")),
    ("last_glucose_reading", ("glucose", "blood sugar", "blood-sugar", "bloodsugar")),
    ("current_medications",  ("medication", "medicine", "meds", "what meds",
                              "drugs i", "pills i")),
    ("calories_today",       ("calorie", "calories")),
    ("protein_today",        ("protein",)),
    ("sleep_last_night",     ("sleep", "slept", "rest last night")),
    # "steps" (plural) only — never bare "step" (avoids matching "next step").
    ("steps_recent",         ("steps", "step count", "how many steps")),
    ("last_blood_pressure_reading", ("blood pressure", "blood-pressure", "bp")),
    ("latest_meal_logged",   ("meal", "meals", "did i eat", "last food")),
    # ----- GOALS domain facts (deterministic, canonical build_goal_state) -----
    # Goal-specific keywords only — never the reasoning cues ("biggest goal risk",
    # "goals at risk"), which fall through to the Goals reasoning quartet.
    ("active_goal_count",    ("how many goals", "how many active goals",
                              "how many goal", "number of goals", "count of goals")),
    ("goals_overdue",        ("overdue goals", "goals overdue", "goals past due",
                              "goals are overdue", "any goals overdue")),
    ("next_goal_deadline",   ("next goal deadline", "goal deadline", "next goal due",
                              "when is my next goal", "when's my next goal")),
    ("top_goal",             ("top goal", "main goal", "primary goal",
                              "what is my goal", "what's my goal", "whats my goal")),
]

FOUNDATIONAL_KEYS = [k for k, _ in _FACT_KEYWORDS]

# Keys resolved from the Goals canonical state instead of the health-facts source.
GOAL_FACT_KEYS = {"top_goal", "active_goal_count", "goals_overdue",
                  "next_goal_deadline"}

_UNKNOWN_SENTENCE = {
    "current_weight": "I don't have a current weight recorded for you yet.",
    "last_glucose_reading": "I don't have a recent glucose reading recorded for you.",
    "current_medications": "I don't have any current medications recorded for you.",
    "calories_today": "I don't have any calories logged for you today.",
    "protein_today": "I don't have any protein logged for you today.",
    "sleep_last_night": "I don't have last night's sleep recorded yet — it may not have synced.",
    "steps_recent": "I don't have recent step data recorded for you — it may not have synced yet.",
    "next_appointment": "You have nothing else on your calendar today.",
    "steps_today": "I don't have today's steps yet — they may not have synced.",
    "steps_yesterday": "I don't have yesterday's steps recorded.",
    "calories_yesterday": "I don't have any calories logged for you yesterday.",
    "average_sleep_7d": "I don't have enough sleep data to show an average yet.",
    "sleep_trend": "I don't have a sleep trend for you yet.",
    "last_blood_pressure_reading": "I don't have a blood pressure reading recorded for you.",
    "latest_meal_logged": "I don't have any logged meals recorded for you yet.",
    "top_goal": "I don't have an active goal recorded for you yet.",
    "active_goal_count": "I don't have any active goals recorded for you yet.",
    "goals_overdue": "I don't have any goals recorded for you yet.",
    "next_goal_deadline": "I don't have any upcoming goal deadlines recorded for you.",
}


def get_foundational_goal_facts(user, keys):
    """Deterministic Goal facts from canonical build_goal_state (no LLM, P24).

    Reads the warm SAE goals module — never recomputes goal truth. Returns the
    same {key: {status, value, ...}} shape the health-facts source uses.
    """
    try:
        from apps.core.ai_state.state_engine import get_module_state
        gs = get_module_state(user, "goals", allow_rebuild=False) or {}
    except Exception:
        logger.warning("COS_FOUNDATION_GOAL_STATE_FAILED user=%s",
                       getattr(user, "id", None), exc_info=True)
        gs = {}
    out = {}
    for key in keys:
        if key == "active_goal_count":
            n = gs.get("active_goal_count")
            out[key] = ({"status": "ok", "value": int(n)} if n is not None
                        else {"status": "unknown"})
        elif key == "top_goal":
            mission = gs.get("mission") if isinstance(gs.get("mission"), dict) else None
            title = None
            if mission:
                title = (mission.get("title") or mission.get("goal_title")
                         or mission.get("name"))
            if not title:
                titles = gs.get("active_titles") or []
                title = titles[0].get("title") if titles else None
            out[key] = ({"status": "ok", "value": title} if title
                        else {"status": "unknown"})
        elif key == "goals_overdue":
            n = gs.get("overdue_goal_count")
            names = [t.get("title") for t in (gs.get("overdue_titles") or [])
                     if t.get("title")]
            out[key] = {"status": "ok", "value": int(n or 0), "titles": names}
        elif key == "next_goal_deadline":
            d = gs.get("days_to_next_deadline")
            upcoming = gs.get("upcoming_titles") or []
            title = upcoming[0].get("title") if upcoming else None
            out[key] = ({"status": "ok", "value": int(d), "title": title}
                        if d is not None else {"status": "unknown"})
    return out

_PHRASE_SYSTEM = (
    "You are the user's Chief of Staff. In ONE short, natural, warm sentence, "
    "state the fact provided. Use ONLY the data given — never add, infer, round, "
    "or invent any number. If the value is unknown, say it isn't recorded yet."
)


# Personal/external BOUNDARY (P26 DC#3). A definitional/general question that
# happens to contain a domain word ("what is a healthy WEIGHT generally?") must NOT
# trigger personal retrieval. EXTERNAL framing + NO personal grounding => general.
_EXTERNAL_SIGNALS = (
    "generally", "in general", "typically", "typical", "usually", "on average", "average",
    "healthy range", "normal range", "healthy level", "normal level", "ideal range",
    "what is a healthy", "what's a healthy", "what is a normal", "what's a normal",
    "what is normal", "what's normal", "what is the normal", "what is an ideal",
    "what counts as", "considered healthy", "considered normal", "supposed to be",
    "recommended range", "what range", "definition of", "what does it mean",
)

# EDUCATIONAL OVERLAY — phrases that ask for GENERAL education layered ON a personal
# fact ("which of my medications are commonly USED FOR diabetes", "list each med and
# what it is COMMONLY USED FOR"). These are HYBRID: WLJ owns the personal list, but
# the educational part is general knowledge. The deterministic fact-stater can't
# combine them, so it must DECLINE and let the tool loop (WLJ tools + general
# knowledge) handle it. Distinct from _EXTERNAL_SIGNALS, which mark a PURELY general
# question (no personal data needed).
_EDUCATIONAL_OVERLAY = (
    "used for", "use for", "used to treat", "what do they treat", "what does it treat",
    "what are they for", "what is it for", "what's it for", "what they're for",
    "what it's for", "what are these for", "commonly used", "purpose of",
    "what's the purpose", "what is the purpose", "why do i take", "why am i taking",
    "what do they do", "what does it do", "what are they used", "what is it used",
)


def _has_educational_overlay(text):
    """True when a message asks for general education on top of a personal fact."""
    return any(sig in text for sig in _EDUCATIONAL_OVERLAY)


def external_general_signal(message):
    """True when a message is clearly an EXTERNAL/definitional question (not about
    the user's own data): strong external framing AND no personal grounding. Shared
    by the foundational classifier (suppress personal retrieval) and the general
    lane (claim it). Pure, deterministic (P26 DC#3)."""
    if not message:
        return False
    t = str(message).lower()
    tokens = set(re.findall(r"[a-z']+", t))
    personal = bool(tokens & {"my", "i", "me", "mine", "myself", "our", "we"}) or \
        any(p in t for p in ("am i", "do i", "should i", "i'm", "i've"))
    if personal:
        return False
    return any(sig in t for sig in _EXTERNAL_SIGNALS)


def classify_foundational_fact(message):
    """Return the fact key for a foundational-fact prompt, or None.

    Deterministic keyword match — no LLM, no Beth, no broad NLU. EXTERNAL/
    definitional questions ("what is a healthy weight generally?") are suppressed so
    they never retrieve the user's personal data (P26 DC#3)."""
    if not message:
        return None
    if external_general_signal(message):
        return None
    text = str(message).lower()
    # HYBRID (personal fact + general education) — e.g. "which of my medications are
    # commonly used for diabetes". The deterministic fact-stater would answer with
    # the bare list and the educational layer would never run. Decline so it falls
    # through to the tool loop, which combines WLJ truth with general knowledge.
    if _has_educational_overlay(text):
        return None
    # PROGRESSION questions ("what's after Goal Weight 284.9?") are milestone-
    # sequence questions owned by Goals, NOT current-fact lookups — even though the
    # milestone NAME contains a fact keyword like "weight" (P29 DC#1).
    if any(c in text for c in ("what's after", "whats after", "what is after",
                               "what comes after", "next after", "after goal weight",
                               "comes next in", "next milestone", "next phase")):
        return None
    # EXECUTION status facts (journaled/worked out/appointments today, next appt) —
    # deterministic providers that previously fell to the LLM (Batch 2).
    exec_key = _classify_execution_fact(text)
    if exec_key:
        return exec_key
    matched = None
    for key, keywords in _FACT_KEYWORDS:
        if any(kw in text for kw in keywords):
            matched = key
            break
    if matched is None:
        return None
    return _refine_to_day(matched, text)


def _classify_execution_fact(text):
    """Deterministic 'did I X today / what's on my calendar' detection. Gated on a
    status phrasing ('did i'/'have i'/'do i have') so coaching questions ('what
    workout should I do today') never match. 'yesterday' is out of Batch-2 scope."""
    if "yesterday" in text:
        return None
    status_q = any(p in text for p in ("did i", "have i", "do i have", "am i"))
    today_q = any(p in text for p in ("today", "yet", "so far"))
    if ("journal" in text or "journaled" in text) and status_q and today_q:
        return "journal_today"
    if (any(w in text for w in ("work out", "workout", "worked out",
                                "exercise", "exercised", "gym"))
            and status_q and today_q):
        return "workout_today"
    if ("appointment" in text or "on my calendar" in text
            or "on my schedule" in text):
        if "next" in text or "upcoming" in text:
            return "next_appointment"
        return "appointments_today"
    return None


def _refine_to_day(key, text):
    """Batch 1 — when a metric is asked for a SPECIFIC day, route to the per-day
    deterministic fact (DailyHealthQueries) instead of the 7-day average. 'Retrieve,
    never derive': "steps yesterday" -> steps_yesterday, "sleep last night" -> the
    actual last night. Bare "steps" defaults to today."""
    is_yesterday = "yesterday" in text
    if key == "steps_recent":
        return "steps_yesterday" if is_yesterday else "steps_today"
    if key == "calories_today" and is_yesterday:
        return "calories_yesterday"
    if key == "sleep_last_night" and any(
            w in text for w in ("average", "this week", "past week", "7 day", "7-day",
                                "weekly", "lately", "typically")):
        # "average/this-week sleep" stays on the 7-day-average SAE fact; only a
        # specific-night question ("last night") gets the per-day deterministic fact.
        return "average_sleep_7d"
    return key


def format_fact_sentence(key, fact):
    """Build a deterministic factual sentence straight from the payload.

    This is the guaranteed answer used when phrasing via _call_api is
    unavailable — it is never empty and never invents data."""
    if not isinstance(fact, dict) or fact.get("status") in (
        "unknown", "unsupported_fact",
    ):
        return _UNKNOWN_SENTENCE.get(key, "That isn't recorded for you yet.")

    value = fact.get("value")
    unit = (fact.get("unit") or "").strip()

    if key == "current_weight":
        s = f"Your current weight is {value} {unit}".strip()
        if fact.get("trend"):
            s += f", and the trend is {fact['trend']}"
        return s + "."
    if key == "last_glucose_reading":
        return f"Your last glucose reading was {value} {unit}".strip() + "."
    if key == "current_medications":
        meds = value if isinstance(value, list) else [value]
        count = fact.get("count", len(meds))
        return (f"You're currently taking {count} medication(s): "
                f"{', '.join(str(m) for m in meds)}.")
    if key == "calories_today":
        s = f"You've consumed {value} calories today"
        if fact.get("target"):
            s += f" (target {fact['target']})"
        return s + "."
    if key == "protein_today":
        s = f"You've consumed {value} g of protein today"
        if fact.get("target"):
            s += f" (target {fact['target']} g)"
        return s + "."
    if key == "sleep_last_night":
        # Batch 1/3 — the ACTUAL most-recent night, with read freshness (Law 1).
        if fact.get("freshness") == "stale":
            fd = fact.get("for_date")
            return (f"I don't have last night's sleep yet — your most recent is "
                    f"{value} {unit or 'hours'}, from {fd}.")
        return f"You slept {value} {unit or 'hours'} last night."
    if key == "average_sleep_7d":
        s = f"You've been averaging {value} {unit or 'hours'} of sleep"
        if fact.get("trend"):
            s += f", and your sleep trend is {fact['trend']}"
        return s + "."
    if key == "journal_today":
        return ("Yes — you've journaled today." if value
                else "Not yet — you haven't journaled today.")
    if key == "workout_today":
        return ("Yes — you've logged a workout today." if value
                else "Not yet — you haven't logged a workout today.")
    if key == "appointments_today":
        if not value:
            return "You have nothing on your calendar today."
        items = fact.get("items") or []
        listed = ("; ".join(items)) if items else ""
        n = value
        head = f"You have {n} appointment{'s' if n != 1 else ''} today"
        return f"{head}: {listed}." if listed else f"{head}."
    if key == "next_appointment":
        return f"Your next appointment is {value}."
    if key in ("steps_today", "steps_yesterday"):
        if key == "steps_today" and fact.get("freshness") == "partial":
            return f"You've logged {value} steps so far today."
        when = "yesterday" if key == "steps_yesterday" else "today"
        return f"You logged {value} steps {when}."
    if key == "calories_yesterday":
        return f"You ate {value} calories yesterday."
    if key == "steps_recent":
        # Legacy 7-day-average fallback (the classifier now routes to the per-day
        # fact above); kept honest as an average, never a specific day.
        return f"You've been averaging about {value} steps a day over the past week."
    if key == "sleep_trend":
        return f"Your sleep trend is {value}."
    if key == "last_blood_pressure_reading":
        dia = fact.get("diastolic")
        bp = f"{value}/{dia}" if dia is not None else f"{value}"
        return f"Your last blood pressure reading was {bp} mmHg."
    if key == "latest_meal_logged":
        return f"Your most recently logged meal entry was on {value}."
    if key == "active_goal_count":
        return f"You have {value} active goal(s) right now."
    if key == "top_goal":
        return f"Your top goal right now is \"{value}\"."
    if key == "goals_overdue":
        if not value:
            return "You don't have any overdue goals right now."
        names = fact.get("titles") or []
        if names:
            return f"You have {value} overdue goal(s): {', '.join(names)}."
        return f"You have {value} overdue goal(s)."
    if key == "next_goal_deadline":
        title = fact.get("title")
        if title:
            return f"Your next goal deadline is in {value} day(s) — \"{title}\"."
        return f"Your next goal deadline is in {value} day(s)."
    return f"{key}: {value} {unit}".strip()


def answer_foundational_fact(user, message):
    """Deterministic foundational-fact fast path.

    Returns the same result shape as ChatGPTCoSService.generate, or None if the
    message is not a foundational fact prompt (caller proceeds normally).
    """
    key = classify_foundational_fact(message)
    if key is None:
        return None

    from apps.ai.services import ai_service

    # Deterministic Provider Registry routes the key to the owning domain provider
    # (goal / execution / health-default). New domains register, not branch here.
    fact, fact_source = _resolve_fact(user, key)

    # The guaranteed, deterministic answer built from the payload.
    deterministic = format_fact_sentence(key, fact)

    # Phrase the retrieved truth with the PLAIN _call_api (no tools, no loop).
    phrased = None
    try:
        phrased = ai_service._call_api(
            _PHRASE_SYSTEM,
            f"Fact to state ({key}): {json.dumps(fact, default=str)}",
            max_tokens=120,
            temperature=0.3,
            endpoint="cos_chat",
            user=user,
        )
    except Exception:
        logger.warning("COS_FOUNDATION_PHRASING_FAILED user=%s key=%s",
                       getattr(user, "id", None), key, exc_info=True)
        phrased = None

    answer = (phrased or "").strip() or deterministic
    logger.info(
        "COS_FOUNDATION_FASTPATH user=%s key=%s phrased=%s answer_len=%d",
        getattr(user, "id", None), key, bool((phrased or "").strip()), len(answer),
    )
    return {
        "answer": answer,
        "empty_reason": None,
        "tools_advertised": [],
        "tools_called": [fact_source],
        "fast_path": "foundational_fact",
        "fact_key": key,
    }


# ============================================================================
# Deterministic Provider Registry wiring (Layer 1 — last platform capability).
# New domains register a provider instead of adding an if/elif branch above.
# ============================================================================
from apps.ai.chatgpt_cos.fact_registry import (  # noqa: E402
    register_fact_provider, resolve as _registry_resolve,
)


def _exec_fact_provider(user, keys):
    from apps.ai.cos_services.execution_facts import get_foundational_execution_facts
    return get_foundational_execution_facts(user, keys)


def _health_fact_provider(user, keys):
    from apps.ai.cos_services.health_facts import get_foundational_health_facts
    return get_foundational_health_facts(user, keys)


def _register_builtin_fact_providers():
    register_fact_provider(lambda k: k in GOAL_FACT_KEYS,
                           get_foundational_goal_facts,
                           "get_foundational_goal_facts")
    register_fact_provider(lambda k: k in EXECUTION_FACT_KEYS,
                           _exec_fact_provider,
                           "get_foundational_execution_facts")
    # Default: health/nutrition/medicine facts (all remaining keys).
    register_fact_provider(lambda k: False, _health_fact_provider,
                           "get_foundational_health_facts", default=True)


_register_builtin_fact_providers()


def _resolve_fact(user, key):
    """Registry-driven dispatch for answer_foundational_fact (returns (fact, source))."""
    return _registry_resolve(user, key)
