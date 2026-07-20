# ==============================================================================
# File: apps/ai/model_interface/conversation_state.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Conversation State — the ONE deterministic, conversation-scoped
#   working-state authority ("what are we talking about / doing / waiting on").
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-20
# ==============================================================================
"""
Conversation State (Chief-of-Staff working-state authority)
===========================================================

Current Context answers "what PAGE is the user on?". Conversation State answers
"what are we currently TALKING ABOUT, DOING, or WAITING ON?" — a different
deterministic truth. WLJ owns the deterministic working-state; the conversational
model reasons over it (Article I.1 / I.2). WLJ never interprets language and never
becomes a conductor.

ONE authority, conversation-scoped, durable in
``AssistantConversation.metadata["conversation_state"]`` (atomic with the turn write,
no migration, the correct grain). It GENERALIZES — it does not fork — existing state:
pending confirmations stay in the ``confirmation`` authority (read through in the
salient lead); artifacts stay in ``MultimodalArtifact``. This module adds only the
missing pointers: the ACTIVE SUBJECT and ACTIVE ARTIFACTS carried across turns.

Facts and references only — never a model-authored summary of the conversation.

Determinism (WLJ):
  * active_subject is DERIVED from concrete signals — this turn's uploaded attachment,
    or an entity the model just retrieved via get_entity — never from parsing language.
  * it persists for a bounded window and expires; a new subject supersedes the old.
Reasoning (model): whether a follow-up ("for a leak?", "is that dangerous?", "it/that")
  refers to the active subject, and whether a short "yes" answers a pending confirmation.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_KEY = "conversation_state"
TTL_SECONDS = 1800          # whole-state inactivity expiry (30 min)
MAX_SUBJECT_TURNS = 4       # turns an unreinforced active subject stays offered
_MAX_ARTIFACTS = 6          # bounded active-artifact list
SCHEMA_VERSION = 1


def _now(now=None):
    if now is not None:
        return now
    from django.utils import timezone
    return timezone.now()


def _iso(dt):
    try:
        return dt.isoformat()
    except Exception:
        return None


def _load(conversation) -> dict:
    try:
        md = getattr(conversation, "metadata", None) or {}
        st = md.get(_KEY)
        return dict(st) if isinstance(st, dict) else {}
    except Exception:
        return {}


def _save(conversation, state) -> None:
    """Persist atomically on the conversation row (update only the metadata column)."""
    try:
        md = getattr(conversation, "metadata", None)
        if not isinstance(md, dict):
            md = {}
        md[_KEY] = state
        conversation.metadata = md
        conversation.save(update_fields=["metadata", "updated_at"])
    except Exception:
        logger.warning("conversation_state: save failed conv=%s",
                       getattr(conversation, "id", "?"), exc_info=True)


def _age_seconds(state, now) -> float:
    from datetime import datetime
    ts = state.get("updated_ts")
    if not ts:
        return 1e12
    try:
        then = datetime.fromisoformat(ts)
        return max(0.0, (now - then).total_seconds())
    except Exception:
        return 1e12


def read(conversation, *, now=None) -> dict | None:
    """The CURRENT (non-expired) conversation working-state as facts, or None.

    Read-path safe (one dict read, no I/O). Applies time-based and turn-based expiry
    so stale state never contaminates a later conversation."""
    if conversation is None:
        return None
    state = _load(conversation)
    if not state:
        return None
    now = _now(now)
    if _age_seconds(state, now) > TTL_SECONDS:
        return None                       # whole state expired
    out = {
        "turn": state.get("turn"),
        "updated_ts": state.get("updated_ts"),
        "active_artifacts": list(state.get("active_artifacts") or [])[:_MAX_ARTIFACTS],
    }
    subj = state.get("active_subject")
    # Turn-based expiry of the active subject (kept as facts if still in window).
    if isinstance(subj, dict) and subj.get("ref") is not None:
        cur_turn = state.get("turn") or 0
        src_turn = subj.get("source_turn") or 0
        subj = dict(subj)
        subj["turns_ago"] = max(0, cur_turn - src_turn)
        if subj["turns_ago"] <= MAX_SUBJECT_TURNS:
            out["active_subject"] = subj
    return out if (out.get("active_subject") or out.get("active_artifacts")) else None


def record_turn(conversation, *, attachments=None, retrieved_subject=None,
                now=None) -> None:
    """Deterministically advance the working-state after a turn. Never raises.

    Signals (concrete, not language):
      * attachments — artifacts uploaded THIS turn → the primary one becomes the active
        subject and joins active_artifacts (the leak-video case).
      * retrieved_subject — an entity/artifact the model just retrieved via get_entity
        ({kind, ref, label}) → becomes the active subject when no upload this turn.
    Otherwise the prior subject persists (until its turn/time window expires)."""
    if conversation is None:
        return
    try:
        now = _now(now)
        state = _load(conversation)
        turn = (state.get("turn") or 0) + 1
        artifacts = list(state.get("active_artifacts") or [])
        subject = state.get("active_subject") if isinstance(
            state.get("active_subject"), dict) else None

        atts = [a for a in (attachments or []) if isinstance(a, dict)]
        if atts:
            # Newest uploads lead; merge into the bounded active-artifact list.
            for a in atts:
                aid = a.get("artifact_id")
                if aid is None:
                    continue
                artifacts = [x for x in artifacts if x.get("artifact_id") != aid]
                artifacts.insert(0, {"artifact_id": aid, "kind": a.get("kind") or "artifact",
                                     "filename": a.get("filename") or a.get("original_filename"),
                                     "ts": _iso(now)})
            primary = atts[0]
            subject = {"kind": (primary.get("kind") or "artifact"),  # video/image/document
                       "artifact": True,                              # → retrieve via artifacts
                       "ref": primary.get("artifact_id"),
                       "label": (primary.get("filename") or primary.get("original_filename")
                                 or f"{primary.get('kind') or 'file'} you uploaded"),
                       "source_turn": turn, "first_ts": _iso(now)}
        elif isinstance(retrieved_subject, dict) and retrieved_subject.get("ref") is not None:
            subject = {"kind": retrieved_subject.get("kind") or "entity",
                       "ref": retrieved_subject.get("ref"),
                       "label": retrieved_subject.get("label") or "the item you asked about",
                       "source_turn": turn, "first_ts": _iso(now)}
        # else: keep the prior subject unchanged (it ages via source_turn).

        state = {
            "schema_version": SCHEMA_VERSION,
            "turn": turn,
            "updated_ts": _iso(now),
            "active_subject": subject,
            "active_artifacts": artifacts[:_MAX_ARTIFACTS],
            "last_answer_turn": turn,
        }
        _save(conversation, state)
    except Exception:
        logger.warning("conversation_state: record_turn failed conv=%s",
                       getattr(conversation, "id", "?"), exc_info=True)


def clear(conversation) -> None:
    """Drop the working-state (e.g. explicit topic reset). Never raises."""
    try:
        md = getattr(conversation, "metadata", None) or {}
        if _KEY in md:
            md.pop(_KEY, None)
            conversation.metadata = md
            conversation.save(update_fields=["metadata", "updated_at"])
    except Exception:
        pass
