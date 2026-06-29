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
    if lane == "why_explainer":           # don't overwrite the basis we're explaining
        return
    answer = (result.get("answer") or "").strip()
    if not answer:
        return
    try:
        md = dict(getattr(conversation, "metadata", None) or {})
        md[_KEY] = {
            "answer": answer,
            "lane": lane,
            "fact_key": result.get("fact_key"),
            "fact": result.get("fact") or {},
            "basis": (result.get("basis") or "").strip(),
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


def compose_when(last, user=None):
    """'At what time?' — the timestamp from the SAME stored fact, rendered in the
    user's timezone + 12-hour format. No LLM."""
    if not last:
        return None
    fact = last.get("fact") or {}
    if fact.get("temporal_warning"):
        return fact["temporal_warning"]            # impossible time → the warning
    raw = fact.get("recorded_at") or fact.get("as_of") or fact.get("for_date")
    if not raw:
        return "I don't have a confirmed time recorded for that reading."
    from apps.core.truth.render import render_datetime
    when = render_datetime(user, raw) if user else str(raw)
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
