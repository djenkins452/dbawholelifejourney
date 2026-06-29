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
        r = _repoint(user, topic, tf, last)
        if r:
            # A move to another day of the same topic IS a comparison intent emerging.
            r["goal"] = "compare"
            return r
        return _on_topic_decline(topic, last, tf)
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
    from apps.ai.chatgpt_cos.conversation_object import fact_for_topic, comparison_semantics
    from apps.ai.chatgpt_cos.foundational_facts import answer_fact_by_key
    from apps.core.truth.present import humanize_number
    cur_fact = last.get("fact") or {}
    cur_val = _num(cur_fact.get("value"))
    unit = (cur_fact.get("unit") or "").strip()

    # COMPARISON SEMANTICS: ask the domain how this metric should be compared. The engine
    # never guesses — it executes the declared contract.
    sem = comparison_semantics(topic)
    explanation = ""

    comp_fact, comp_label = None, None
    if sem.get("strategy") == "average":
        # Point readings are noisy (e.g. glucose) → compare against the average baseline,
        # not point-vs-point, and explain why. (No new retrieval — uses the supporting avg.)
        sup = (last.get("supporting") or {}).get("average")
        comp_fact = (sup or {}).get("fact")
        comp_label = "your recent average"
        explanation = sem.get("explanation", "")
    elif tf in ("average", "last_week"):
        sup = (last.get("supporting") or {}).get("average")
        comp_fact = (sup or {}).get("fact")
        comp_label = "your recent average" if tf == "average" else "last week's average"
    elif tf:
        comp_key = fact_for_topic(topic, tf)
        if comp_key:
            r = answer_fact_by_key(user, comp_key)
            comp_fact = (r or {}).get("fact")
            comp_label = tf.replace("_", " ")

    goal = "trend" if tf in ("average", "last_week", "last_month") else "compare"

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
            if explanation:
                ans += f" I compared against your recent average because {explanation}."
            r = _result(ans, last)
            r["goal"] = goal
            r["comparison_confidence"] = sem.get("confidence", "medium")
            return r

    # Non-numeric topic (e.g. meals): a comparison means SIDE-BY-SIDE — the active
    # timeframe AND the comparison timeframe together, not just one of them. This is the
    # objective the customer actually had ("compare my meals across days").
    if tf and tf != "average":
        side = _side_by_side(user, topic, last, tf)
        if side:
            r = _result(side, last)
            r["goal"] = goal
            return r
    return _on_topic_decline(topic, last, tf)


_TF_LABELS = {"today": "Today", "yesterday": "Yesterday",
              "day_before_yesterday": "The day before", "last_week": "Last week",
              "last_month": "Last month"}


def _tf_label(tf):
    return _TF_LABELS.get(tf, (tf or "Then").replace("_", " ").capitalize())


def _side_by_side(user, topic, last, comp_tf):
    """Present the active timeframe and the comparison timeframe together (the real
    'compare' objective for a non-numeric topic like meals). Deterministic."""
    comp = _repoint(user, topic, comp_tf, last)
    if not comp:
        return None
    from apps.core.truth.present import present_groups
    a_lbl, b_lbl = _tf_label(last.get("timeframe")), _tf_label(comp_tf)
    a_meals = (last.get("fact") or {}).get("meals")
    b_meals = (comp.get("fact") or {}).get("meals")
    if a_meals is not None and b_meals is not None:
        # INTENT FULFILLMENT: the comparison itself is the answer, not two lists.
        from apps.ai.chatgpt_cos.fulfillment import fulfill_meal_comparison
        insight = fulfill_meal_comparison(a_lbl, a_meals, b_lbl, b_meals)
        if insight:
            return insight
        # Nothing to compare (e.g. one day empty) → fall back to showing the data.
        a = present_groups(a_meals.items(), lead=f"{a_lbl}:") or f"{a_lbl}: nothing logged."
        b = present_groups(b_meals.items(), lead=f"{b_lbl}:") or f"{b_lbl}: nothing logged."
        return a + "\n\n" + b
    # Generic fallback: two rendered answers under timeframe headers.
    a = (last.get("answer") or "").strip()
    b = (comp.get("answer") or "").strip()
    if not b:
        return None
    return f"{a_lbl}: {a}\n\n{b_lbl}: {b}"


def _on_topic_decline(topic, last, tf):
    """Honest, on-topic answer when a reference can't be resolved — keeps the
    conversation on the established topic instead of falling through to an unrelated
    lane (which is how Beth used to drift into generic coaching)."""
    when = (tf or "that period").replace("_", " ")
    return _result(f"I don't have a separate {when} figure for your {topic} to compare yet.",
                   last)
