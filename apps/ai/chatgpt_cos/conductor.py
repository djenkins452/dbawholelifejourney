# ==============================================================================
# File: apps/ai/chatgpt_cos/conductor.py
# THE CONDUCTOR — orchestration only. Governing contract: it owns WHO answers a turn and
# HOW conversation state advances; it never owns WHAT is thought. "WLJ owns truth · Beth's
# capabilities own wisdom · The Conductor owns the conversation."
#
# STEP 1 (this file, foundation only): the COMMIT LIFECYCLE — a single, always-runs point
# where every turn advances one unified conversation state. Today's routing, lanes, answers,
# and existing state stores are UNCHANGED; this adds the one place future steps consolidate
# state progression into, plus per-turn observability. No classifier, no dispatch, no
# reordering — those are later steps, gated on production observation of this one.
#
# Contract guardrails honored here:
#   G1 no domain knowledge · G2 no content generation · G5 bounded & finite ·
#   G6 no invented fallback reasoning. This module reads/writes state metadata and logs.
#   It imports NO intelligence/domain/truth module and composes NO user-facing text.
# Enforced by apps/ai/tests/test_conductor_contract.py.
# ==============================================================================
import logging

logger = logging.getLogger(__name__)

STATE_KEY = "conductor_state"
_HISTORY_CAP = 8


def read_turn_state(conversation):
    """The single unified turn state for this conversation (or {} when absent). A
    read-only view; the Conductor is the only writer (via commit_turn)."""
    try:
        md = getattr(conversation, "metadata", None) or {}
        st = md.get(STATE_KEY)
        return st if isinstance(st, dict) else {}
    except Exception:
        return {}


def _subject_key(result):
    """Best-effort extraction of the turn's active-subject KEY from a handler result —
    metadata only (e.g. 'sleep_last_night'), never an interpretation of its meaning."""
    if not isinstance(result, dict):
        return None
    key = result.get("fact_key")
    if not key:
        subj = result.get("active_subject")
        if isinstance(subj, dict):
            key = subj.get("fact_key")
    return key or None


def commit_turn(conversation, *, winner, result=None, user=None):
    """Advance the ONE conversation state after a turn has been owned — ALWAYS, regardless
    of which handler answered. This is the commit lifecycle the Conductor owns: every turn
    stamps the universal fields (turn count, last act, active subject, last seen) so state
    can never silently fail to advance.

    STEP 1 scope: record only. It does not clear, reorder, or reinterpret anything, and it
    never raises — a state-progression failure must never break a delivered answer."""
    if conversation is None:
        return
    try:
        md = dict(getattr(conversation, "metadata", None) or {})
        st = dict(md.get(STATE_KEY) or {})
        turn = int(st.get("turn", 0)) + 1

        st["turn"] = turn
        st["last_act"] = winner
        subject = _subject_key(result)
        if subject:                       # carry the prior subject forward when this turn
            st["active_subject_key"] = subject   # names none (Step 1: record, don't clear)

        try:
            if user is not None:
                from apps.core.utils import get_user_now
                st["last_seen"] = get_user_now(user).isoformat()
        except Exception:
            pass

        history = list(st.get("history") or [])
        history.append({"turn": turn, "act": winner,
                        "subject": st.get("active_subject_key")})
        st["history"] = history[-_HISTORY_CAP:]

        md[STATE_KEY] = st
        conversation.metadata = md
        conversation.save(update_fields=["metadata"])

        logger.info("COS_TURN_COMMIT user=%s turn=%s act=%s subject=%s",
                    getattr(user, "id", None), turn, winner,
                    st.get("active_subject_key"))
    except Exception:
        logger.warning("conductor.commit_turn failed", exc_info=True)
