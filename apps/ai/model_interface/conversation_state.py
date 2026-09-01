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
Reasoning (model): whether a follow-up ("for a leak?", "is that dangerous?", "it/that")
  refers to the active subject, and whether a short "yes" answers a pending confirmation.

DETERMINISTIC LIFECYCLE — EVENT-DRIVEN PRIMARY, turn/time only as a last-resort fallback:
  * ACTIVATE  — an upload arrives, or the model retrieves an entity/artifact (get_entity).
  * UPDATE    — the SAME subject is re-surfaced (re-retrieved) → its source_turn resets
                (deterministic reinforcement; a text-only "is it about the subject?" is the
                model's semantic call, not a WLJ event).
  * SUPERSEDE — a NEW upload, or a retrieval of a DIFFERENT subject, replaces the subject.
                This is the PRIMARY way a subject changes.
  * CLEAR (event) — an explicit reset (`clear()`; `AssistantConversation.clear_messages`).
                Pending confirmations clear on their own event path (single-use consume in
                `confirmation.py`) when resolved/declined/cancelled.
  * PRESERVE  — an ambiguous follow-up with no new subject signal → keep the subject.
  * CLEAR (fallback, ONLY when no event above fired) — the whole state expires after
                TTL_SECONDS of INACTIVITY, and an unreinforced subject ages out after a
                GENEROUS turn backstop. These are safety nets for state the model
                SEMANTICALLY abandoned ("never mind" / a new task) — which WLJ cannot detect
                deterministically (that is language = the model's job, Article I.2) — NOT the
                primary clear mechanism.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_KEY = "conversation_state"
# FALLBACKS ONLY (not the primary lifecycle — supersession/clear events are). They bound
# state the model silently moved on from, which WLJ cannot observe deterministically.
TTL_SECONDS = 1800          # whole-state INACTIVITY fallback (30 min)
MAX_SUBJECT_TURNS = 12      # generous turn BACKSTOP for an unreinforced, never-superseded subject
_MAX_ARTIFACTS = 6          # bounded active-artifact list
_MAX_COMPLETED = 8          # bounded recent-completion list
# A completed write stays authoritative for long enough to stop a re-proposal, then ages
# out with everything else. It is EVIDENCE for the model, never a substitute for canonical
# truth: the record itself remains the authority.
MAX_COMPLETED_TURNS = 12
SCHEMA_VERSION = 1
# Deterministic pointer fields a retrieved subject may carry beyond {kind, ref, label}.
# Strictly an allow-list: references the next turn can RE-RETRIEVE with, never content.
_SUBJECT_REF_FIELDS = ("domain", "metric")


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
    # FALLBACK backstop (not the primary clear — supersession events are): an unreinforced,
    # never-superseded subject ages out only after a generous turn window.
    if isinstance(subj, dict) and subj.get("ref") is not None:
        cur_turn = state.get("turn") or 0
        src_turn = subj.get("source_turn") or 0
        subj = dict(subj)
        subj["turns_ago"] = max(0, cur_turn - src_turn)
        # (domain/metric pointers ride along untouched — see _SUBJECT_REF_FIELDS.)
        if subj["turns_ago"] <= MAX_SUBJECT_TURNS:
            out["active_subject"] = subj
    # GUIDED REVIEW session (Blocker #15): the active one-at-a-time execution review —
    # the current item awaiting the user's answer + which items were already presented.
    # A conversation-scoped CURSOR (references only, not truth); the item queue itself is
    # re-derived from the Execution Review projection each turn. Ages out with the state TTL.
    gr = state.get("guided_review")
    if isinstance(gr, dict) and gr.get("current"):
        out["guided_review"] = gr
    # ALREADY DONE — verified completions, so a later turn cannot re-propose a write that
    # has already happened. Facts only (what, when, which target); the canonical record
    # remains the authority.
    cur_turn = state.get("turn") or 0
    done = [d for d in (state.get("completed_actions") or []) if isinstance(d, dict)]
    done = [dict(d, turns_ago=max(0, cur_turn - (d.get("turn") or 0)))
            for d in done
            if (cur_turn - (d.get("turn") or 0)) <= MAX_COMPLETED_TURNS]
    if done:
        out["completed_actions"] = done[:_MAX_COMPLETED]
    # AWAITING AN ANSWER — the unresolved action a short reply should refine.
    pc = state.get("pending_clarification")
    if isinstance(pc, dict) and pc.get("tool"):
        out["pending_clarification"] = pc
    return out if (out.get("active_subject") or out.get("active_artifacts")
                   or out.get("guided_review") or out.get("completed_actions")
                   or out.get("pending_clarification")) else None


def set_guided_review(conversation, guided_review) -> None:
    """Persist the active guided-review cursor (current item awaiting an answer + the
    keys already presented) onto the conversation state, atomically. Never raises."""
    if conversation is None:
        return
    try:
        now = _now()
        state = _load(conversation)
        state["guided_review"] = guided_review
        state["updated_ts"] = _iso(now)          # keep the session alive under the TTL
        state.setdefault("schema_version", SCHEMA_VERSION)
        _save(conversation, state)
    except Exception:
        logger.warning("conversation_state: set_guided_review failed conv=%s",
                       getattr(conversation, "id", "?"), exc_info=True)


def clear_guided_review(conversation) -> None:
    """End the guided-review session (reconciled / stopped). Never raises."""
    if conversation is None:
        return
    try:
        state = _load(conversation)
        if state.pop("guided_review", None) is not None:
            _save(conversation, state)
    except Exception:
        logger.warning("conversation_state: clear_guided_review failed conv=%s",
                       getattr(conversation, "id", "?"), exc_info=True)


def record_completed_action(conversation, *, tool_name, summary, target=None,
                            domain=None, now=None) -> None:
    """Record that a confirmed action ACTUALLY SUCCEEDED — the missing continuity event.

    Confirmations resolve on a DIFFERENT turn from the one that proposed them (the confirm
    endpoint), and that turn never called `record_turn`. So a successful write left no trace
    in working state at all: the next prompt carried the proposal in history with nothing
    saying it had been carried out, and the model re-proposed it. Recording the completion
    here is what makes "already done" a deterministic fact instead of something the model
    has to infer from prose.

    It also SUPERSEDES an active subject that the completed action consumed — an uploaded
    label stops being the live subject once the thing it depicted has been logged. Without
    that, an image stays dominant for its whole turn window and keeps re-suggesting itself,
    even after the conversation has moved to another domain entirely.
    """
    if conversation is None:
        return
    try:
        now = _now(now)
        state = _load(conversation)
        turn = state.get("turn") or 0
        done = [d for d in (state.get("completed_actions") or []) if isinstance(d, dict)]
        entry = {"tool": tool_name or "", "summary": (summary or "")[:200],
                 "turn": turn, "ts": _iso(now)}
        if target:
            entry["target"] = str(target)[:120]
        if domain:
            entry["domain"] = str(domain)[:40]
        done.insert(0, entry)
        state["completed_actions"] = done[:_MAX_COMPLETED]

        # SUPERSEDE a consumed artifact subject. An attachment is the live subject while it
        # is being acted on; once a write derived from it succeeds, keeping it active is
        # what let an old label hijack unrelated turns.
        subj = state.get("active_subject")
        if isinstance(subj, dict) and subj.get("artifact"):
            state["active_subject"] = None
        state["updated_ts"] = _iso(now)
        state.setdefault("schema_version", SCHEMA_VERSION)
        _save(conversation, state)
    except Exception:
        logger.warning("conversation_state: record_completed_action failed conv=%s",
                       getattr(conversation, "id", "?"), exc_info=True)


# ── unresolved clarification ─────────────────────────────────────────────────
def set_pending_clarification(conversation, *, tool_name, question, args=None,
                              target=None, domain=None, now=None) -> None:
    """Persist an action that is WAITING ON AN ANSWER, not one that failed.

    A handler that needs to know "this occurrence or the whole series?" is asking a
    question, and the user's next message is the answer to it. Without this the reply
    arrives with no intent to attach to, and the model resolves it against whatever else
    is lying around — which is how "Just today" reopened an unrelated domain.
    """
    if conversation is None:
        return
    try:
        now = _now(now)
        state = _load(conversation)
        state["pending_clarification"] = {
            "tool": tool_name or "",
            "question": (question or "")[:400],
            "args": {k: v for k, v in (args or {}).items()
                     if isinstance(k, str)},
            "target": str(target)[:120] if target else None,
            "domain": str(domain)[:40] if domain else None,
            "turn": state.get("turn") or 0,
            "ts": _iso(now),
        }
        state["updated_ts"] = _iso(now)
        state.setdefault("schema_version", SCHEMA_VERSION)
        _save(conversation, state)
    except Exception:
        logger.warning("conversation_state: set_pending_clarification failed conv=%s",
                       getattr(conversation, "id", "?"), exc_info=True)


def clear_pending_clarification(conversation) -> None:
    """The question has been answered (or abandoned). Never raises."""
    if conversation is None:
        return
    try:
        state = _load(conversation)
        if state.pop("pending_clarification", None) is not None:
            _save(conversation, state)
    except Exception:
        logger.warning("conversation_state: clear_pending_clarification failed conv=%s",
                       getattr(conversation, "id", "?"), exc_info=True)


def active_artifact_ids(conversation, *, now=None) -> list:
    """The artifact id(s) of the CURRENT active-artifact subject — so a follow-up turn can
    RE-PERCEIVE an active image/video/document and keep it SEEABLE, not merely referenced.
    Returns [] when no (non-expired) active artifact. Read-path safe (reuses read()'s expiry;
    this is a READ, never a write)."""
    st = read(conversation, now=now) or {}
    subj = st.get("active_subject") or {}
    if subj.get("artifact") and subj.get("ref") is not None:
        return [subj["ref"]]
    return []


def record_turn(conversation, *, attachments=None, retrieved_subject=None,
                now=None) -> None:
    """Deterministically advance the working-state after a turn — the EVENT-DRIVEN write
    path (ACTIVATE / SUPERSEDE / PRESERVE). Never raises.

    Events (concrete signals, not language):
      * attachments — an upload THIS turn → ACTIVATE/SUPERSEDE: the primary upload becomes the
        active subject and joins active_artifacts (the leak-video case).
      * retrieved_subject — an entity/artifact the model just retrieved via get_entity
        ({kind, ref, label}) → ACTIVATE/SUPERSEDE (or UPDATE, when it re-surfaces the SAME
        subject: source_turn resets → reinforced).
    Otherwise PRESERVE: the prior subject persists unchanged (cleared only by a later
    supersession/clear event, or — as a last resort — the turn/time FALLBACKS in read())."""
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
            # Compact deterministic POINTERS only (domain/metric), so a follow-up that
            # merely shifts the DATE ("Yesterday's?") can be re-retrieved from the same
            # authority. Never prose, never a summary, never inferred intent.
            for field in _SUBJECT_REF_FIELDS:
                val = retrieved_subject.get(field)
                if val:
                    subject[field] = val
        # else: keep the prior subject unchanged (it ages via source_turn).

        new_state = {
            "schema_version": SCHEMA_VERSION,
            "turn": turn,
            "updated_ts": _iso(now),
            "active_subject": subject,
            "active_artifacts": artifacts[:_MAX_ARTIFACTS],
            "last_answer_turn": turn,
        }
        # PRESERVE the active guided-review session across the end-of-turn rebuild — the
        # tool set it mid-turn; it must survive to the next turn until the workflow itself
        # advances or clears it (else the pending question is wiped the moment it's asked —
        # the exact Blocker #15 loss). Ages out with the state TTL like everything else.
        gr = state.get("guided_review")
        if isinstance(gr, dict) and gr.get("current"):
            new_state["guided_review"] = gr
        # PRESERVE completions and any unresolved question across the rebuild — both are
        # cross-turn continuity, and record_turn() rebuilds the whole dict.
        if state.get("completed_actions"):
            new_state["completed_actions"] = state["completed_actions"][:_MAX_COMPLETED]
        if isinstance(state.get("pending_clarification"), dict):
            new_state["pending_clarification"] = state["pending_clarification"]
        _save(conversation, new_state)
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
