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


def compose_why(last):
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
