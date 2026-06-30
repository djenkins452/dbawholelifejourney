"""
Deterministic Conversation Memory.

The conversation itself becomes truth. After Beth answers, we durably record a
STRUCTURED memory of the turn — what she said, the supporting fact, and the
deterministic basis — on the conversation row. A follow-up ("Why do you say that?")
is then answered DETERMINISTICALLY from that record, not reconstructed by an LLM from
chat history. Beth knows what she just said and why, every time.

Storage is `AssistantConversation.metadata["last_answer"]` (apps/ai/models.py:549) —
the same JSONField + save(update_fields=["metadata"]) pattern already used for
pending_clarification / conversation_state. No migration.
"""
import logging

logger = logging.getLogger(__name__)

_KEY = "last_answer"


def record_last_answer(conversation, lane, result):
    """Persist the structured memory of the turn Beth just produced."""
    if conversation is None or not isinstance(result, dict):
        return
    if lane == "why_explainer":
        # Don't overwrite the basis we're explaining — but DO let an explicit goal hint
        # (a comparison / what-changed follow-up) advance the standing conversation goal.
        goal = result.get("goal")
        if goal:
            try:
                md = dict(getattr(conversation, "metadata", None) or {})
                if md.get(_KEY):
                    md[_KEY]["goal"] = goal
                    conversation.metadata = md
                    conversation.save(update_fields=["metadata"])
            except Exception:
                logger.warning("record_last_answer goal-update failed", exc_info=True)
        return
    answer = (result.get("answer") or "").strip()
    if not answer:
        return
    try:
        md = dict(getattr(conversation, "metadata", None) or {})
        # Conversational frame: topic (timeframe-independent) + timeframe, so a bare
        # reference ("what about yesterday?") re-points the topic without restating it.
        from apps.ai.chatgpt_cos.conversation_object import topic_of, evolve_goal
        frame = topic_of(result.get("fact_key")) or (None, None)
        # Conversation GOAL: what the user is trying to accomplish. Evolves from the
        # previous frame (review → compare → trend), so the objective persists across
        # turns — not just the subject. An explicit hint from the resolver wins.
        prev = md.get(_KEY)
        goal = evolve_goal(prev, frame[0], frame[1], explicit=result.get("goal"))
        # ACTIVE SUBJECT — which object currently owns the conversation, the anchor that
        # follow-ups ("compared to my average", "is that good?") resolve against. It moves
        # ONLY on a primary question or an explicit refocus; a comparison NEVER silently
        # moves it (the resolver passes an explicit active_subject only when it should).
        if "active_subject" in result:
            active_subject = result.get("active_subject")
        elif lane == "foundational_facts" and result.get("fact_key"):
            active_subject = {"fact_key": result.get("fact_key"),
                              "fact": result.get("fact") or {}}
        else:
            active_subject = (prev or {}).get("active_subject")
        md[_KEY] = {
            "answer": answer,
            "lane": lane,
            "intent": result.get("fact_key"),     # the question's resolved intent
            "fact_key": result.get("fact_key"),
            "topic": frame[0],                    # e.g. "meals" — survives timeframe changes
            "timeframe": frame[1],                # e.g. "today"
            "goal": goal,                         # e.g. "compare" — why we're discussing it
            "active_subject": active_subject,     # the anchor — moves only on explicit refocus
            "fact": result.get("fact") or {},
            "basis": (result.get("basis") or "").strip(),
            # Supporting facts for natural follow-ups (read from here, no new retrieval).
            "supporting": result.get("supporting") or {},
        }
        conversation.metadata = md
        conversation.save(update_fields=["metadata"])
    except Exception:
        logger.warning("conversation_memory: record failed", exc_info=True)


def get_last_answer(conversation):
    md = getattr(conversation, "metadata", None) or {}
    return md.get(_KEY)


def _topic_label(last):
    return (last.get("fact_key") or "").replace("_", " ").replace("last ", "") \
        .replace(" reading", "").strip() or "that"


# The ONE warning string — shared so the value answer and every time follow-up are
# byte-identical when a timestamp is in the future (Truth Consistency).
_FUTURE_WARNING = ("That timestamp appears to be in the future, which shouldn't be "
                   "possible. There may be a synchronization or timezone issue, so the "
                   "reading's time is unconfirmed.")


def _time_or_warning(raw, user):
    """Render a stored timestamp, OR the future-warning if it is impossible. TEMPORAL
    SANITY AT READ TIME guarantees a follow-up can never render a future time as real —
    so it can never contradict the value answer that flagged it unconfirmed."""
    from django.utils import timezone
    from apps.core.truth.temporal import is_future
    if is_future(raw, timezone.now()):
        return None, _FUTURE_WARNING
    from apps.core.truth.render import render_datetime
    return (render_datetime(user, raw) if user else str(raw)), None


def compose_supporting(last, user=None, label="meals"):
    """Answer a follow-up from a SUPPORTING fact already on the active topic — no new
    retrieval, no LLM. e.g. "what did I eat?" after a calorie answer reads the stored
    meals. Returns None (so the lane declines to normal routing) when there is no such
    supporting fact on the active topic."""
    if not last:
        return None
    sup = (last.get("supporting") or {}).get(label)
    if not sup or not sup.get("fact"):
        return None
    from apps.ai.chatgpt_cos.foundational_facts import format_fact_sentence
    return format_fact_sentence(sup.get("key", ""), sup["fact"])


def _fmt_num(n):
    return int(n) if float(n).is_integer() else round(n, 1)


def compose_comparison(last, user=None, kind="prior"):
    """'Compared to yesterday / my average?' — answered from the primary value and a
    SUPPORTING comparison fact ('prior' = yesterday, 'average' = recent average) already
    on the active topic. No new retrieval, no LLM. Generic across every numeric fact."""
    if not last:
        return None
    fact = last.get("fact") or {}
    cur = fact.get("value")
    sup = (last.get("supporting") or {}).get(kind)
    comp = (sup or {}).get("fact", {}).get("value") if sup else None
    if cur is None or comp is None:
        return None
    try:
        cur_n, comp_n = float(cur), float(comp)
    except (TypeError, ValueError):
        return None
    unit = fact.get("unit", "")
    when = "yesterday" if kind == "prior" else "your recent average"
    diff = cur_n - comp_n
    if abs(diff) < 1e-9:
        return f"About the same as {when} — {_fmt_num(cur_n)} {unit}".strip() + "."
    direction = "up" if diff > 0 else "down"
    return (f"That's {direction} {_fmt_num(abs(diff))} {unit} from {when} "
            f"({_fmt_num(comp_n)} → {_fmt_num(cur_n)})").strip() + "."


# Facts whose VALUE is an aggregate/average, not a single point-in-time reading.
_AVERAGE_FACT_KEYS = {"average_sleep_7d", "average_glucose_yesterday", "steps_recent"}


def compose_is_average(last, user=None):
    """TF4 — 'Is that an average? / a single reading?' answered from the active fact's
    nature, never a clarifying question. Offers the recent average alongside a single
    reading (already on the object — no new retrieval), anticipating the next question."""
    fk = (last or {}).get("fact_key")
    if not fk:
        return None
    from apps.core.truth.present import humanize_number
    fact = last.get("fact") or {}
    val = fact.get("value")
    unit = (fact.get("unit") or "").strip()
    if fk in _AVERAGE_FACT_KEYS:
        shown = f" ({humanize_number(val)} {unit})".rstrip() if val is not None else ""
        return f"Yes — that{shown} is an average, not a single reading."
    # A single/point reading — offer the average too if it's already on hand.
    avg = ((last.get("supporting") or {}).get("average") or {}).get("fact") or {}
    base = "No — that's a single reading"
    if val is not None:
        base += f" ({humanize_number(val)} {unit})".rstrip()
    if avg.get("value") is not None:
        return base + f". Your recent average is {humanize_number(avg['value'])} {unit}".rstrip() + "."
    return base + ", not an average."


def compose_what_changed(last, user=None):
    """TF5 — 'what changed? / what caused that?' → the deterministic comparison already
    available on the object (vs yesterday, else vs the recent average)."""
    for kind in ("prior", "average"):
        ans = compose_comparison(last, user, kind=kind)
        if ans:
            return ans
    return None


def compose_more(last, user=None):
    """TF5 — 'anything else? / go deeper' → the remaining supporting facts on the active
    object, each rendered through the presentation layer. No new retrieval, no LLM."""
    sup = (last or {}).get("supporting") or {}
    if not sup:
        return None
    from apps.ai.chatgpt_cos.foundational_facts import format_fact_sentence
    parts = []
    for label, entry in sup.items():
        if label == "prior":                 # comparison-only, not a standalone detail
            continue
        fact = (entry or {}).get("fact")
        key = (entry or {}).get("key")
        if fact and key:
            txt = (format_fact_sentence(key, fact) or "").strip()
            if txt:
                parts.append(txt)
    if not parts:
        return None
    return "\n".join(parts)


def compose_when(last, user=None):
    """'At what time?' — the timestamp from the SAME stored fact, rendered in the
    user's timezone + 12-hour format, with read-time temporal sanity. No LLM."""
    if not last:
        return None
    fact = last.get("fact") or {}
    if fact.get("temporal_warning"):
        return fact["temporal_warning"]            # impossible time → the warning
    raw = fact.get("recorded_at") or fact.get("as_of") or fact.get("for_date")
    if not raw:
        return "I don't have a confirmed time recorded for that reading."
    when, warning = _time_or_warning(raw, user)
    if warning:
        return warning                             # never render a future time
    return f"That was recorded on {when}." if when else \
        "I don't have a confirmed time recorded for that reading."


def compose_concern(last, user=None, positive_frame=False):
    """'Should I be concerned?' (negative frame) / 'Is that good?' (positive frame) —
    answered from the fact's clinical interpretation, with correct polarity. NEVER
    reassures over a flagged value (a danger is "not good" AND "yes, be concerned")."""
    if not last:
        return None
    interp = (last.get("fact") or {}).get("interpretation") or {}
    safety = interp.get("safety")
    label = _topic_label(last)
    advice = interp.get("advice") or "this reading needs attention."
    if safety == "danger":
        return (f"No — that's not good. {advice}" if positive_frame
                else f"Yes — {advice}")
    if safety == "caution":
        return (f"It's not quite ideal — your {label} is "
                f"{interp.get('display', 'outside the typical range')}. "
                f"{interp.get('advice', '')}").strip()
    if safety == "ok":
        disp = interp.get("display", "in range")
        return (f"Yes — your {label} is {disp}, right where you want it."
                if positive_frame
                else f"No — your {label} is {disp}, nothing to worry about there.")
    return ("I don't have a specific concern flag on that one — it looks within your "
            "usual range, but check with your care team if you're unsure.")


def compose_meaning(last, user=None):
    """'Why is that important? / What does that mean?' — the health meaning from the
    fact's interpretation (not 'because your data says so')."""
    if not last:
        return None
    interp = (last.get("fact") or {}).get("interpretation") or {}
    if interp.get("meaning"):
        lead = f"Your {_topic_label(last)} is {interp.get('display', '')}".strip()
        return f"{lead}. {interp['meaning']}"
    return compose_why(last)               # fall back to the basis explanation


def compose_is_current(last, user=None):
    """'Is that current? / When was it recorded?' — freshness + rendered recency."""
    if not last:
        return None
    fact = last.get("fact") or {}
    if fact.get("temporal_warning"):
        return fact["temporal_warning"]
    raw = fact.get("recorded_at") or fact.get("as_of") or fact.get("for_date")
    fresh = fact.get("freshness")
    if not raw:
        return "I can't confirm exactly when that was recorded."
    # Read-time temporal sanity: a future stored time is never reported as real.
    from django.utils import timezone
    from apps.core.truth.temporal import is_future
    if is_future(raw, timezone.now()):
        return _FUTURE_WARNING
    rel = ""
    if user:
        from apps.core.truth.render import render_relative_time
        rel = render_relative_time(user, raw)
    if fresh == "stale":
        return f"It's a little old — recorded {rel or 'a while ago'}, so it may not be current."
    return f"Yes — that's your most recent reading, recorded {rel or 'recently'}."


def compose_why(last, user=None):
    """Deterministic explanation of the PRIOR answer from its supporting fact —
    no LLM. Returns the explanation string, or None if there's nothing to explain."""
    if not last:
        return None
    fact = last.get("fact") or {}
    basis = (last.get("basis") or "").strip()
    parts = []
    if basis:
        parts.append(f"Because that's what your data shows — {basis.rstrip('.')}")
    else:
        prior = (last.get("answer") or "").strip()
        if not prior:
            return None
        parts.append(f"I said that from your tracked data — {prior.rstrip('.')}")
    low_basis = (basis or last.get("answer") or "").lower()
    interp = fact.get("interpretation") or {}
    # Add the interpretation pieces the basis didn't already carry (no repetition,
    # but never drop the safety advice for a flagged value).
    seg_bits = []
    if interp.get("display") and interp["display"].lower() not in low_basis:
        seg_bits.append(f"that reading is {interp['display']}")
    adv = (interp.get("advice") or "").rstrip(".")
    if interp.get("concern") and adv and adv.lower() not in low_basis:
        seg_bits.append(adv)
    if seg_bits:
        parts.append(", and ".join(seg_bits))
    fresh = fact.get("freshness")
    if fresh in ("stale", "pending", "missing") and not interp \
            and "current" not in low_basis and "synced" not in low_basis:
        parts.append("and I flagged that the data isn't fully current")
    return ". ".join(parts).strip().rstrip(".") + "."
