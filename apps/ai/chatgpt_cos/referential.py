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
        # HISTORICAL TRUTH NAVIGATION: a bare reference the fixed timeframes don't cover
        # ("day before yesterday?", "July 1st?", "when did I first drop below 290?",
        # "average last month?") — navigate the topic's canonical deterministic history
        # rather than declining. The active topic is known; the navigator needs no keyword.
        nav = _historical_nav(user, topic, message)
        if nav:
            return _result(nav, last)
        return None
    kind, tf = ref
    if kind == "timeframe":
        r = _repoint(user, topic, tf, last)
        if r:
            # A move to another day of the same topic IS a comparison intent emerging.
            r["goal"] = "compare"
            return r
        # The fixed timeframe has no fact_key (e.g. day_before_yesterday) — navigate the
        # canonical history instead of the old "I don't have a separate … figure" decline.
        nav = _historical_nav(user, topic, message)
        if nav:
            return _result(nav, last)
        return _on_topic_decline(topic, last, tf)
    return _compare(user, topic, tf, last)


# Topics whose deterministic history supports natural navigation (point-in-time,
# threshold, extremum, aggregate). Each module exposes `navigate(user, message) -> str|None`.
_TOPIC_HISTORY_NAV = {"weight": "apps.ai.chatgpt_cos.weight_history"}


def _historical_nav(user, topic, message):
    """Delegate an elliptical historical follow-up to the active topic's canonical
    navigator (the SAME engine the explicit lane uses), so 'day before yesterday?' and
    'July 1st?' resolve deterministically instead of drifting or declining."""
    mod_path = _TOPIC_HISTORY_NAV.get(topic)
    if not mod_path:
        return None
    try:
        import importlib
        return importlib.import_module(mod_path).navigate(user, message)
    except Exception:
        logger.warning("referential: historical nav failed for topic=%s", topic, exc_info=True)
        return None


def _result(answer, last, *, fact_key=None, fact=None):
    return {
        "answer": answer,
        "lane": "referential",
        "fast_path": "referential_resolution",
        "fact_key": fact_key if fact_key is not None else (last or {}).get("fact_key"),
        "fact": fact if fact is not None else (last or {}).get("fact") or {},
        "basis": answer,
        # A comparison stays on the same topic — carry its supporting facts forward so a
        # later "compared to my average" still finds them (don't strip them on each turn).
        "supporting": (last or {}).get("supporting") or {},
    }


def _repoint(user, topic, tf, last):
    """Same topic, new timeframe → answer that fact by key (deterministic). An explicit
    refocus ('what about yesterday?') — so it MOVES the Active Subject."""
    from apps.ai.chatgpt_cos.conversation_object import fact_for_topic
    from apps.ai.chatgpt_cos.foundational_facts import answer_fact_by_key
    new_key = fact_for_topic(topic, tf)
    if not new_key:
        return None
    r = answer_fact_by_key(user, new_key)
    if r:
        r["lane"] = "referential"
        r["fast_path"] = "referential_resolution"
        r["active_subject"] = {"fact_key": new_key, "fact": r.get("fact") or {}}
    return r


def _delta_sentence(cur_val, comp_val, comp_label, unit):
    diff = cur_val - comp_val
    if abs(diff) < 1e-9:
        return f"About the same as {comp_label} — {_h(cur_val)} {unit}".strip() + "."
    direction = "up" if diff > 0 else "down"
    return (f"That's {direction} {_h(abs(diff))} {unit} from {comp_label} "
            f"({_h(comp_val)} → {_h(cur_val)})").strip() + "."


def _h(v):
    from apps.core.truth.present import humanize_number
    return humanize_number(v)


def _resolve_target(user, topic, tf, sem, last):
    """The user's explicit Comparison TARGET → (fact, label, is_average). HONORED always,
    independent of the metric's preferred strategy. Only when the user gives no explicit
    target (tf is None) does the metric's semantics choose the baseline."""
    from apps.ai.chatgpt_cos.conversation_object import fact_for_topic
    from apps.ai.chatgpt_cos.foundational_facts import answer_fact_by_key
    avg = ((last.get("supporting") or {}).get("average") or {}).get("fact")
    if tf is None:                                   # no explicit target — metric chooses
        if sem.get("strategy") == "average" and avg:
            return avg, "your recent average", True
        prior = ((last.get("supporting") or {}).get("prior") or {}).get("fact")
        return prior, "yesterday", False
    if tf == "average":
        return avg, "your recent average", True
    if tf in ("last_week", "last_month", "day_before_yesterday"):
        # We don't have this period's real data (deep-timeline gap). Do NOT substitute
        # the recent average and pretend it was the requested target — return unavailable
        # so the caller declines honestly (and may offer the average explicitly).
        return None, tf.replace("_", " "), False
    comp_key = fact_for_topic(topic, tf)             # a specific day the user named
    if comp_key:
        r = answer_fact_by_key(user, comp_key)
        return (r or {}).get("fact"), tf.replace("_", " "), False
    return None, None, False


def _compare(user, topic, tf, last):
    from apps.ai.chatgpt_cos.conversation_object import comparison_semantics
    # ANCHOR on the ACTIVE SUBJECT, not whatever was last answered — a comparison must
    # not let the anchor drift (the production bug: "compared to my average" anchored on
    # yesterday instead of the current reading under discussion).
    active = last.get("active_subject") or {}
    cur_fact = active.get("fact") or last.get("fact") or {}
    cur_val = _num(cur_fact.get("value"))
    unit = (cur_fact.get("unit") or "").strip()
    sem = comparison_semantics(topic)
    goal = "trend" if tf in ("average", "last_week", "last_month") else "compare"

    # 1) HONOR THE USER'S TARGET FIRST — never silently replaced.
    comp_fact, comp_label, target_is_average = _resolve_target(user, topic, tf, sem, last)

    # Comparing "to today" re-centers the Active Subject on the current reading (the user
    # explicitly named today); any other target leaves the anchor untouched.
    recenter = None
    if tf == "today" and comp_fact is not None:
        from apps.ai.chatgpt_cos.conversation_object import fact_for_topic
        recenter = {"fact_key": fact_for_topic(topic, "today"), "fact": comp_fact}

    if topic in NUMERIC_TOPICS and cur_val is not None:
        comp_val = _num((comp_fact or {}).get("value"))
        avg_fact = ((last.get("supporting") or {}).get("average") or {}).get("fact")
        avg_val = _num((avg_fact or {}).get("value"))
        # The metric prefers an average and the user asked for something else → ADD a
        # recommendation afterward. Additive, never substitutive.
        # Don't append the average add-on when re-centering on "today" — the anchor is
        # mid-shift, so the "today is …" phrasing would mislabel the value.
        recommend_avg = (sem.get("strategy") == "average" and not target_is_average
                         and avg_val is not None and avg_fact is not comp_fact
                         and tf != "today")

        if comp_val is not None:
            ans = _delta_sentence(cur_val, comp_val, comp_label, unit)        # the answer
            if recommend_avg:
                rd = cur_val - avg_val
                side = "above" if rd > 0 else ("below" if rd < 0 else "in line with")
                ans += (f" {sem.get('explanation', '').strip().capitalize()}. A more "
                        f"meaningful comparison is your recent average: today is "
                        f"{_h(abs(rd))} {unit} {side} it ({_h(avg_val)} → {_h(cur_val)}).")
            r = _result(ans, last)
            r["goal"] = goal
            # Layer 2 Reasoning Confidence: the conclusion is only as trustworthy as its
            # weakest input — combine the metric's semantics confidence with the Layer 1
            # fact's own confidence (read-only).
            from apps.ai.chatgpt_cos.reasoning.engines import reasoning_confidence
            r["comparison_confidence"] = reasoning_confidence(
                sem.get("confidence"), cur_fact.get("confidence"))
            r["comparison_target"] = comp_label
            if recenter:
                r["active_subject"] = recenter      # user named "today" → re-anchor there
            return r

        # Target requested but unavailable. Don't silently substitute — say so, then offer
        # the average if the metric prefers it.
        if tf and tf not in ("average",) and recommend_avg:
            rd = cur_val - avg_val
            side = "above" if rd > 0 else ("below" if rd < 0 else "in line with")
            ans = (f"I don't have a {comp_label} figure for your {topic} to compare "
                   f"directly. As a more meaningful comparison, today is {_h(abs(rd))} "
                   f"{unit} {side} your recent average ({_h(avg_val)} → {_h(cur_val)}).")
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
