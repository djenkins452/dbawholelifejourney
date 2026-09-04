# ==============================================================================
# File: apps/ai/checkin_author.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: OpenAI authors the entire proactive Check-in from deterministic truth.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-10
# ==============================================================================
"""
Check-in authoring — WLJ assembles deterministic truth; OpenAI writes the words.

This retires the WLJ-authored check-in renderer. The proactive Check-in message is now
authored end-to-end by the conversational model from the Executive Context Envelope
(Current Context · Current Action · Execution State + Timing · Mission Link · AI
Relationship). WLJ contributes NO motivational or coaching prose and NO judgment — it
supplies facts and calculations; the model recognizes the moment, judges the situation,
connects to the mission, and speaks.

Triggering logic and execution policy are unchanged and live elsewhere (proactive_checkins,
the routers) — this module only replaces the AUTHORING of the message.

Degrades to the canonical next-action DIRECTIVE (a deterministic fact line, not the retired
prose) when the model is unavailable, so a check-in is never a fabricated status report.
"""

import json
import logging

logger = logging.getLogger(__name__)

# The check-in prompt carries the Constitution plus a full truth envelope. The tool loop
# was given a real budget when the 12k default was found to be truncating it; this is the
# same correction for the same reason, on the sibling call path.
CHECKIN_GOVERN_BUDGET = 100_000

_PHASE_HINT = {
    "morning": "It is morning — the user is starting their day.",
    "midday": "It is midday — the day is in progress.",
    "evening": "It is evening — the day is winding down.",
    "end_of_day": "It is the end of the day.",
}


def _derive_phase(user):
    try:
        from apps.core.utils import get_user_now
        h = get_user_now(user).hour
    except Exception:
        return None
    if h < 10:
        return "morning"
    if h < 15:
        return "midday"
    if h < 21:
        return "evening"
    return "end_of_day"


def _system_prompt() -> str:
    """The constant behavioural contract, and nothing else.

    The task and the truth used to be appended HERE, after the Constitution — and the
    token governor truncates a system prompt FROM THE END. Measured 2026-09-04: this
    prompt was 122,518 chars, the governor's default budget kept 29,817 of them (24%),
    and what it cut was the authoring instruction and the entire truth envelope. The
    model received two-thirds of a constitution, a truncation marker and an EMPTY user
    turn — so it said "Hello! How can I assist you today?" twice. It was not a fallback;
    it was a real provider call with nothing left to do.
    """
    from apps.ai.model_interface.constitution import CONSTITUTION
    return CONSTITUTION


SILENCE_TOKEN = "NO_MESSAGE"


def _user_prompt(envelope, phase, signals=None) -> str:
    """The task and the truth, in the USER turn — which the governor never trims.

    Position is the fix. A check-in has no user message of its own, so this slot was
    empty while the actual work sat at the far end of a 122k-char system prompt behind
    a truncation boundary. Putting the work where it cannot be evicted removes the
    class rather than detecting it.

    The task is stated as a DECISION, not an assignment. WLJ has established that
    something is live; whether any of it is worth interrupting a person's day for is a
    judgment, and judgments belong to the model. `SILENCE_TOKEN` is simply how it says
    "not worth it" — without an affordance for silence, a model asked to author a message
    will always author one, which is how a goal-pace calculation became a notification.
    """
    detected = ""
    if signals:
        detected = ("\n=== DETECTED SIGNALS (deterministic; WLJ noticed these, WLJ has "
                    "NOT decided any of them matters) ===\n"
                    + json.dumps(signals, ensure_ascii=False, default=str) + "\n")
    return (
        "=== PROACTIVE CHECK-IN ===\n"
        + (_PHASE_HINT.get(phase or "", "") + "\n")
        + "You may send this person an unprompted message right now. First decide whether "
          "you should. There is no obligation to say anything, and a message that does not "
          "help them is worse than silence — they did not ask for this one.\n"
          "If there IS something worth their attention, write it in your own natural voice "
          "from the deterministic truth below. If a high-priority action is due or late "
          "(see `current_action` / `execution_state`), lead with it. When the truth carries "
          "a `mission_link`, connect that action to the mission using the mission's "
          "`why_it_matters` from `missions`. Give ONE clear next action, then stop. Judge "
          "the situation yourself (behind / on time / at risk) from the timing FACTS — WLJ "
          "does not label it. Use ONLY the truth provided; never invent a time, task, "
          "mission, or number. Be brief and human — a trusted Chief of Staff, not a status "
          "report; no lists of everything, no filler.\n"
          f"If nothing here is genuinely worth interrupting them for, reply with exactly "
          f"{SILENCE_TOKEN} and nothing else. That is a normal, correct outcome.\n"
        + detected
        + "\n=== DETERMINISTIC TRUTH ===\n"
        + json.dumps(envelope, ensure_ascii=False, default=str)
    )


# Buckets that mean something is actually outstanding right now. `later` and `completed`
# describe a day that needs no interruption.
_LIVE_BUCKETS = ("overdue", "due_now", "coming_up")


def has_reason_to_interrupt(envelope, signals=None) -> bool:
    """Is there a concrete, current thing to say — before any words are generated?

    WLJ's half of "prefer silence over low-value output". This is a FACT question, so it
    is WLJ's to answer: does the day's canonical execution truth contain anything live,
    or is there a decided current action? Whether that thing is worth saying, and how, is
    still entirely the model's judgment.

    Domain-agnostic by construction — it reads the execution buckets and the single
    decision authority, and knows nothing about weight, tasks, medication or any metric.
    """
    if signals:
        return True
    envelope = envelope or {}
    execution = envelope.get("execution_state") or {}
    if any(execution.get(bucket) for bucket in _LIVE_BUCKETS):
        return True
    current = envelope.get("current_action") or {}
    return bool(current.get("primary_action"))


def _is_silence(text) -> bool:
    """Did the model decline? Tolerant of punctuation and case, nothing more."""
    stripped = (text or "").strip().strip(".!\"' ").upper()
    return stripped == SILENCE_TOKEN


def author_checkin(user, *, phase=None, signals=None) -> str:
    """OpenAI decides whether to send a proactive check-in, and authors it if so.

    WLJ assembles the truth and any deterministically DETECTED signals; the model decides
    whether any of it warrants interrupting the person, and writes the words. Returns the
    authored text, "" for silence, or — if the model is unavailable — the canonical
    next-action directive (a deterministic fact, never the retired prose). Never raises.

    ATTRIBUTION LIVES HERE, not with the caller. A check-in is autonomous by nature: no
    human asked for it, whichever entry point reached this function. It was previously
    left to each caller to declare, and the ones that forgot made real provider calls
    classified `unattributed` — invisible to the very gate that exists to stop unattended
    spend. Marking the WORK means a new caller cannot reintroduce that hole.
    """
    from apps.ai.llm_accounting import (SOURCE_PROACTIVE_CHECKIN, TRAFFIC_PROACTIVE,
                                        llm_traffic_context)
    from apps.ai.llm_admission import autonomous_workload

    phase = phase or _derive_phase(user)

    try:
        from apps.ai.model_interface.service import ModelInterfaceService
        envelope = ModelInterfaceService(user).build_standing_context()
    except Exception:  # pragma: no cover - defensive
        logger.warning("checkin_author: envelope assembly failed", exc_info=True)
        envelope = {}

    # NOTHING LIVE COSTS NOTHING. No live execution truth, no decided action and no
    # detected signal means there is not even a candidate to weigh, so the day ends
    # without a provider call at all. This is WLJ's half — a FACT question. Whether a
    # candidate is worth saying is the model's, below.
    if not has_reason_to_interrupt(envelope, signals):
        logger.info("checkin_author: nothing live for user=%s — silent, no provider call",
                    getattr(user, "id", "?"))
        return ""

    text = None
    with autonomous_workload("proactive_checkin"), llm_traffic_context(
            traffic_class=TRAFFIC_PROACTIVE, source=SOURCE_PROACTIVE_CHECKIN):
        try:
            from apps.ai.services import ai_service
            text = ai_service._call_api(
                _system_prompt(), _user_prompt(envelope, phase, signals),
                max_tokens=400, endpoint="proactive_checkin", user=user,
                # Sized to the model, not to the legacy 12k default that truncated this
                # prompt's task and truth away entirely.
                govern_budget=CHECKIN_GOVERN_BUDGET,
            )
        except Exception:
            logger.warning("checkin_author: model authoring failed", exc_info=True)

    # THE MODEL MAY DECLINE. Something was live, and it judged none of it worth a person's
    # attention right now. That is the intended outcome, not a failure, and it must not
    # fall through to the degraded directive — which would turn every "not worth it" into
    # a message anyway.
    if _is_silence(text):
        logger.info("checkin_author: model judged nothing worth interrupting user=%s",
                    getattr(user, "id", "?"))
        return ""

    if text and str(text).strip():
        return str(text).strip()

    # Degraded (model unavailable): the canonical next-action directive — a FACT, not
    # prose — but ONLY when there is genuinely an action to state. Without that guard the
    # directive degrades to "Nothing pending right now.", which is precisely the
    # low-value interruption this whole path exists to stop; a signal-driven check-in
    # would announce nothing at all rather than staying quiet.
    try:
        from apps.core.execution.decision_authority import (current_action,
                                                            current_action_directive)
        if not (current_action(user) or {}).get("primary_action"):
            return ""
        return current_action_directive(user)
    except Exception:  # pragma: no cover - defensive
        return ""
