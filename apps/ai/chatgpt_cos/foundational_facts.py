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
]

FOUNDATIONAL_KEYS = [k for k, _ in _FACT_KEYWORDS]

_UNKNOWN_SENTENCE = {
    "current_weight": "I don't have a current weight recorded for you yet.",
    "last_glucose_reading": "I don't have a recent glucose reading recorded for you.",
    "current_medications": "I don't have any current medications recorded for you.",
    "calories_today": "I don't have any calories logged for you today.",
    "protein_today": "I don't have any protein logged for you today.",
    "sleep_last_night": "I don't have recent sleep data recorded for you.",
    "average_sleep_7d": "I don't have enough sleep data to show an average yet.",
    "sleep_trend": "I don't have a sleep trend for you yet.",
}

_PHRASE_SYSTEM = (
    "You are the user's Chief of Staff. In ONE short, natural, warm sentence, "
    "state the fact provided. Use ONLY the data given — never add, infer, round, "
    "or invent any number. If the value is unknown, say it isn't recorded yet."
)


def classify_foundational_fact(message):
    """Return the fact key for a foundational-fact prompt, or None.

    Deterministic keyword match — no LLM, no Beth, no broad NLU."""
    if not message:
        return None
    text = str(message).lower()
    for key, keywords in _FACT_KEYWORDS:
        for kw in keywords:
            if kw in text:
                return key
    return None


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
    if key in ("sleep_last_night", "average_sleep_7d"):
        s = f"You've been averaging {value} {unit or 'hours'} of sleep"
        if fact.get("trend"):
            s += f", and your sleep trend is {fact['trend']}"
        return s + "."
    if key == "sleep_trend":
        return f"Your sleep trend is {value}."
    return f"{key}: {value} {unit}".strip()


def answer_foundational_fact(user, message):
    """Deterministic foundational-fact fast path.

    Returns the same result shape as ChatGPTCoSService.generate, or None if the
    message is not a foundational fact prompt (caller proceeds normally).
    """
    key = classify_foundational_fact(message)
    if key is None:
        return None

    from apps.ai.cos_services.health_facts import get_foundational_health_facts
    from apps.ai.services import ai_service

    facts = get_foundational_health_facts(user, [key])
    fact = facts.get(key, {}) if isinstance(facts, dict) else {}

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
        "tools_called": ["get_foundational_health_facts"],
        "fast_path": "foundational_fact",
        "fact_key": key,
    }
