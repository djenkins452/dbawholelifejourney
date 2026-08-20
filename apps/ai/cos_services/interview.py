# ==============================================================================
# File: apps/ai/cos_services/interview.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: M4 — deterministic Getting to Know You orchestration
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-08-19
# ==============================================================================
"""Getting to Know You — the deterministic half of the hybrid interview.

WLJ owns what is KNOWN and what the user RULED OUT. The model owns what is worth
asking. This module never chooses a question, never orders topics, never scores
coverage and never marks an interview finished — it reports an unordered inventory and
enforces the boundaries the user set.

Deliberate teaching: a user who opened this experience is here to teach, so validated
facts persist through the canonical Personal Knowledge service (Contract 7.1) with
`provenance=interview`. About Me is the review surface; nothing is confirmed per-fact,
because turning a conversation into a confirmation queue would destroy it.
"""

import logging

from django.utils import timezone

from apps.core.personal_knowledge import service as pk
from apps.core.personal_knowledge.models import Provenance, ReviewState, Sensitivity

logger = logging.getLogger(__name__)

# Areas AVAILABLE to explore. An inventory, never an agenda and never a checklist —
# a user is not expected to have anything in any of them.
AVAILABLE_AREAS = (
    "background", "family", "work", "home", "routines", "interests",
    "goals", "values", "faith", "history", "communication", "help_preferences",
)

_VALID_TOPIC_STATES = {
    "discussed": "discussed",
    "satisfied": "satisfied",
    "parked": "parked",
    "declined": "declined",
}

MAX_FACTS_PER_TURN = 8          # a bound, not a target


def _session_model():
    from apps.ai.models import InterviewSession
    return InterviewSession


def start_or_resume(user, conversation=None):
    """Return the user's live session, resuming a paused one rather than starting over."""
    InterviewSession = _session_model()
    session = (InterviewSession.objects
               .filter(user=user)
               .order_by("-last_active_at")
               .first())
    if session is None:
        session = InterviewSession.objects.create(user=user, conversation=conversation)
        logger.info("interview: started user=%s", getattr(user, "id", None))
        return session
    changed = []
    if session.status != InterviewSession.STATUS_ACTIVE:
        session.status = InterviewSession.STATUS_ACTIVE
        changed.append("status")
    if conversation is not None and session.conversation_id != conversation.id:
        session.conversation = conversation
        changed.append("conversation")
    if changed:
        session.save(update_fields=changed + ["last_active_at"])
    return session


def active_session(user, conversation=None):
    """The session in play for this conversation, or None. Read-only."""
    InterviewSession = _session_model()
    qs = InterviewSession.objects.filter(user=user,
                                         status=InterviewSession.STATUS_ACTIVE)
    if conversation is not None:
        bound = qs.filter(conversation=conversation).first()
        if bound:
            return bound
    return qs.order_by("-last_active_at").first()


def pause(user, conversation=None):
    """Stop for now. Everything already taught stays; the session resumes later."""
    session = active_session(user, conversation)
    if session is None:
        return None
    session.status = _session_model().STATUS_PAUSED
    session.save(update_fields=["status", "last_active_at"])
    logger.info("interview: paused user=%s turns=%s", getattr(user, "id", None),
                session.turn_count)
    return session


def set_topic_state(session, topic, state):
    """Record an outcome the USER established for one area.

    `declined` is absolute: a declined area is never offered again unless the user
    reopens it. Emergent labels are accepted as-is — a life does not need a deploy.
    """
    normalized = _VALID_TOPIC_STATES.get((state or "").strip().lower())
    topic = (topic or "").strip().lower()
    if not topic or normalized is None:
        return False
    states = dict(session.topic_states or {})
    states[topic] = {"state": normalized, "at": timezone.now().isoformat()}
    session.topic_states = states
    session.save(update_fields=["topic_states", "last_active_at"])
    return True


def record_facts(session, facts):
    """Persist deliberately-taught facts through the CANONICAL Personal Knowledge service.

    WLJ owns schema, provenance, topic, review state, sensitivity, ownership and the
    domain boundary; the model only proposes statements. Nothing here writes a PK row
    directly. Returns (recorded, rejected) — rejections are reported honestly so the
    conversation never claims something was remembered when it was not.
    """
    recorded, rejected = [], []
    for item in (facts or [])[:MAX_FACTS_PER_TURN]:
        if not isinstance(item, dict):
            continue
        statement = (item.get("statement") or "").strip()
        if not statement:
            continue
        topic = (item.get("topic") or "other").strip().lower()
        subject = (item.get("subject") or "").strip()
        # Sensitivity is a POLICY decision WLJ owns; the model may only flag, never clear.
        sensitivity = (Sensitivity.SENSITIVE if item.get("sensitive")
                       else Sensitivity.NORMAL)
        try:
            fact = pk.add_fact(
                session.user, statement,
                topic=topic, subject_label=subject,
                provenance=Provenance.INTERVIEW,
                # Deliberate teaching is user-authored truth — not an unverified guess.
                review_state=ReviewState.USER_AUTHORED,
                sensitivity=sensitivity,
                source_conversation=session.conversation,
                # TEMPORAL ANCHOR (M5). WLJ knows exactly when it was told something —
                # that is WLJ's own truth, not an inference about the user. Anchoring the
                # fact means a point-in-time detail ("Tom is 14") stays honest as it ages
                # instead of silently becoming false, and the model never has to DERIVE a
                # birth year, which would be arithmetic on an unstated birthday.
                as_of=timezone.localdate(),
            )
            recorded.append(fact)
        except Exception as exc:
            # A domain-boundary rejection or malformed statement must not break the
            # conversation, and must never be reported as remembered.
            logger.info("interview: fact rejected user=%s reason=%s",
                        getattr(session.user, "id", None), exc)
            rejected.append({"statement": statement, "reason": str(exc)})
    if recorded:
        session.facts_recorded = (session.facts_recorded or 0) + len(recorded)
        session.save(update_fields=["facts_recorded", "last_active_at"])
    return recorded, rejected


def note_turn(session):
    session.turn_count = (session.turn_count or 0) + 1
    session.save(update_fields=["turn_count", "last_active_at"])


def read(user, conversation=None):
    """The deterministic interview block for the Executive Context Envelope.

    An INVENTORY, deliberately unordered and unscored: what is known, what the user
    ruled out, and where we are. No next-topic, no percentage, no completion.
    """
    session = active_session(user, conversation)
    if session is None:
        return None
    try:
        counts = pk.topic_counts(user)
    except Exception:  # pragma: no cover - envelope must never hard-fail
        logger.warning("interview: topic counts unavailable", exc_info=True)
        counts = {}

    states = session.topic_states or {}
    areas = []
    for area in AVAILABLE_AREAS:
        entry = states.get(area) or {}
        areas.append({
            "area": area,
            "things_known": counts.get(area, 0),
            "user_state": entry.get("state"),      # None = never addressed
        })
    # Emergent areas the user actually talked about, outside the predefined inventory.
    for key in sorted(set(list(counts) + list(states))):
        if key not in AVAILABLE_AREAS:
            areas.append({
                "area": key, "things_known": counts.get(key, 0),
                "user_state": (states.get(key) or {}).get("state"), "emergent": True,
            })
    return {
        "status": session.status,
        "turns_so_far": session.turn_count,
        "things_learned_this_session": session.facts_recorded,
        "areas": areas,
        "declined_areas": session.declined_topics(),
        "note": ("An unordered INVENTORY of what is known and what the user ruled out — "
                 "not an agenda, not a checklist, and never a measure of the person. "
                 "You decide what is worth asking; never work through these in order, "
                 "and never treat an empty area as a gap to fill."),
    }
