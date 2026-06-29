"""
Referential Conversation Resolution.

Humans rarely restate the subject. Once a topic is established, a bare reference —
"what about yesterday?", "compared to today", "how about last week?", "and today?" —
should resolve against the active conversational FRAME (topic + timeframe): same topic,
new timeframe or a comparison. No restated subject, no topic drift, no generic coaching.

Generalized across every topic in the registry (apps/ai/chatgpt_cos/conversation_object.py)
— meals, weight, sleep, steps, glucose, calories, workouts, calendar, journal, and any
future deterministic fact. Deterministic: re-pointing answers by key; comparison composes
from values. Never falls through to an unrelated lane when a reference is clearly meant.
"""
import logging

logger = logging.getLogger(__name__)

# Bare timeframe references → re-point the active topic to that timeframe. PHRASE forms
# only — a complete fact question ("how many steps today?") is excluded by the
# classify guard in resolve_referential, never by a bare-word substring match.
_TF_CUES = {
    "yesterday": ("what about yesterday", "how about yesterday", "and yesterday",
                  "for yesterday", "what about last night"),
    "today": ("what about today", "how about today", "and today", "for today",
              "and now"),
    # Deeper timeline — recognized so a reference stays ON-TOPIC (answers honestly)
    # instead of drifting to another subject. Real N-day/N-month retrieval is the next
    # Trust Sprint (see docs/TRUST_FAILURE_INVENTORY.md).
    "day_before_yesterday": ("day before yesterday", "the day before yesterday",
                             "two days ago", "2 days ago", "what about the day before"),
    "last_week": ("what about last week", "how about last week", "for last week"),
    "last_month": ("what about last month", "how about last month", "for last month"),
}
_COMPARE_MARKERS = ("compared to", "compare to", "how does that compare",
                    "how does it compare", "how do they compare", " versus ", " vs ")
_AVG_MARKERS = ("average", "usual", "normal", "typical")

# Topics whose comparison is a meaningful NUMERIC delta (others re-point + present).
NUMERIC_TOPICS = {"steps", "calories", "protein", "weight", "glucose", "sleep"}


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _classify_reference(norm):
    """('timeframe', tf) | ('compare', tf|None) | None."""
    if any(m in norm for m in _COMPARE_MARKERS):
        for tf in ("day_before_yesterday", "last_month", "last_week", "yesterday", "today"):
            if tf.replace("_", " ") in norm:
                return ("compare", tf)
        if any(a in norm for a in _AVG_MARKERS):
            return ("compare", "average")
        return ("compare", None)
    for tf, cues in _TF_CUES.items():
        if norm == tf.replace("_", " ") or any(c in norm for c in cues):
            return ("timeframe", tf)
    return None


def resolve_referential(user, message, last):
    """Resolve a bare reference against the active frame. Returns a result dict
    (re-pointed answer or comparison), or None to let normal routing proceed."""
    topic = (last or {}).get("topic")
    if not topic:
        return None
    # A complete fact question ("how many steps today?") is a NEW subject, not a bare
    # reference — let the foundational lane answer it. Only un-classifiable references
    # ("what about yesterday?", "compared to today") resolve against the active frame.
    from apps.ai.chatgpt_cos.foundational_facts import classify_foundational_fact
    if classify_foundational_fact(message):
        return None
    norm = (message or "").strip().lower().rstrip("?.! ")
    ref = _classify_reference(norm)
    if not ref:
        return None
    kind, tf = ref
    if kind == "timeframe":
        return _repoint(user, topic, tf, last) or _on_topic_decline(topic, last, tf)
    return _compare(user, topic, tf, last)


def _result(answer, last, *, fact_key=None, fact=None):
    return {
        "answer": answer,
        "lane": "referential",
        "fast_path": "referential_resolution",
        "fact_key": fact_key if fact_key is not None else (last or {}).get("fact_key"),
        "fact": fact if fact is not None else (last or {}).get("fact") or {},
        "basis": answer,
    }


def _repoint(user, topic, tf, last):
    """Same topic, new timeframe → answer that fact by key (deterministic)."""
    from apps.ai.chatgpt_cos.conversation_object import fact_for_topic
    from apps.ai.chatgpt_cos.foundational_facts import answer_fact_by_key
    new_key = fact_for_topic(topic, tf)
    if not new_key:
        return None
    r = answer_fact_by_key(user, new_key)
    if r:
        r["lane"] = "referential"
        r["fast_path"] = "referential_resolution"
    return r


def _compare(user, topic, tf, last):
    from apps.ai.chatgpt_cos.conversation_object import fact_for_topic
    from apps.ai.chatgpt_cos.foundational_facts import answer_fact_by_key
    from apps.core.truth.present import humanize_number
    cur_fact = last.get("fact") or {}
    cur_val = _num(cur_fact.get("value"))
    unit = (cur_fact.get("unit") or "").strip()

    comp_fact, comp_label = None, None
    if tf in ("average", "last_week"):
        sup = (last.get("supporting") or {}).get("average")
        comp_fact = (sup or {}).get("fact")
        comp_label = "your recent average" if tf == "average" else "last week's average"
    elif tf:
        comp_key = fact_for_topic(topic, tf)
        if comp_key:
            r = answer_fact_by_key(user, comp_key)
            comp_fact = (r or {}).get("fact")
            comp_label = tf.replace("_", " ")

    if topic in NUMERIC_TOPICS and cur_val is not None and comp_fact:
        comp_val = _num(comp_fact.get("value"))
        if comp_val is not None:
            diff = cur_val - comp_val
            if abs(diff) < 1e-9:
                ans = f"About the same as {comp_label} — {humanize_number(cur_val)} {unit}".strip() + "."
            else:
                direction = "up" if diff > 0 else "down"
                ans = (f"That's {direction} {humanize_number(abs(diff))} {unit} from "
                       f"{comp_label} ({humanize_number(comp_val)} → {humanize_number(cur_val)})").strip() + "."
            return _result(ans, last)

    # Non-numeric topic (e.g. meals) or a cross-timeframe compare we can't delta →
    # re-point to that timeframe and present it on-topic. Never drift to coaching.
    if tf and tf != "average":
        repointed = _repoint(user, topic, tf, last)
        if repointed:
            return repointed
    return _on_topic_decline(topic, last, tf)


def _on_topic_decline(topic, last, tf):
    """Honest, on-topic answer when a reference can't be resolved — keeps the
    conversation on the established topic instead of falling through to an unrelated
    lane (which is how Beth used to drift into generic coaching)."""
    when = (tf or "that period").replace("_", " ")
    return _result(f"I don't have a separate {when} figure for your {topic} to compare yet.",
                   last)
