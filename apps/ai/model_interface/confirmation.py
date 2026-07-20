# ==============================================================================
# File: apps/ai/model_interface/confirmation.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Bound confirmation transactions (Blocker 1 — no confused deputy)
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-09
# ==============================================================================
"""
Bound confirmation transactions for the model-interface action path.

HARDENING (Slice 7.2 — Blocker 1). Each confirmation is its own bound transaction with an
identity, so `resolve` executes a SPECIFIC confirmation by id — never "whatever is stored."

RICH CONFIRMATION (docs/WLJ_RICH_CONFIRMATION_ARCHITECTURE.md). The bound record now also
carries the presentation-independent `view` (title/summary/preview/actions) and is
CONVERSATION-BOUND, so the SAME record drives the on-screen card, the deterministic button
endpoint, and the typed pre-parser. Resolving leaves a short-lived tombstone (status
resolved/cancelled) so a replay is reported as *already resolved* rather than *expired*.

    { id, action, params, summary, view, conversation_id, source_artifact_id, status, choice }

Storage is a dedicated per-user cache dict, isolated from the legacy `pending_intent_*` key.
"""

import logging
import uuid

from django.core.cache import cache

logger = logging.getLogger(__name__)

_TTL = 300          # seconds an open confirmation stays resolvable
_MAX_OPEN = 8       # cap concurrent records per user (open + recent tombstones)


def _key(user_id):
    return f"wlj:mi:confirm:{user_id}"


def _load(user_id):
    try:
        return cache.get(_key(user_id)) or {}
    except Exception:  # pragma: no cover - defensive
        return {}


def _save(user_id, store):
    try:
        if store:
            cache.set(_key(user_id), store, _TTL)
        else:
            cache.delete(_key(user_id))
    except Exception:  # pragma: no cover - defensive
        logger.warning("mi.confirmation: save failed user=%s", user_id, exc_info=True)


def create(user, action, params, summary, *, view=None, conversation_id=None,
           source_artifact_id=None):
    """Create a bound confirmation; return {confirmation_id, summary, expires_in, view} or None."""
    uid = getattr(user, "id", None)
    store = _load(uid)
    # Bound the number of stored records (drop the oldest if over cap).
    if len(store) >= _MAX_OPEN:
        for k in list(store)[: len(store) - _MAX_OPEN + 1]:
            store.pop(k, None)
    cid = uuid.uuid4().hex
    store[cid] = {
        "id": cid, "action": action, "params": dict(params or {}),
        "summary": summary, "view": view or None,
        "conversation_id": (int(conversation_id) if conversation_id else None),
        "source_artifact_id": source_artifact_id or None,
        "status": "pending", "choice": None,
    }
    _save(uid, store)
    return {"confirmation_id": cid, "summary": summary, "expires_in": _TTL,
            "view": view or None}


def get(user, cid):
    """Return the PENDING confirmation record for this user+id, or None."""
    if not cid:
        return None
    rec = _load(getattr(user, "id", None)).get(cid)
    if not rec or rec.get("status") != "pending":
        return None
    return rec


def peek(user, cid):
    """Return the record for this user+id regardless of status (pending/resolved/cancelled),
    or None if it never existed / has expired out of the cache. Lets the caller distinguish
    'already resolved' from 'expired'."""
    if not cid:
        return None
    return _load(getattr(user, "id", None)).get(cid)


def consume(user, cid, *, status="resolved", choice=None):
    """Single-use: mark the confirmation resolved/cancelled (a short-lived tombstone within
    the same TTL) so it can never be resolved twice and a replay reads as already-resolved."""
    uid = getattr(user, "id", None)
    store = _load(uid)
    rec = store.get(cid)
    if rec is not None:
        rec["status"] = status
        if choice:
            rec["choice"] = choice
        store[cid] = rec
        _save(uid, store)


def list_open(user):
    """Open confirmations as [{confirmation_id, summary}] — surfaced in the standing
    context so the model can resolve a SPECIFIC one on the user's 'yes'."""
    store = _load(getattr(user, "id", None))
    return [{"confirmation_id": cid, "summary": r.get("summary", "")}
            for cid, r in store.items() if r.get("status") == "pending"]


def bind_conversation(user, conversation_id):
    """Bind this turn's freshly-minted confirmations (conversation_id still None) to the
    conversation, and return the client payload for the NEWEST one (or None). Called by the
    runtime after a turn so the card is conversation-scoped without threading the id through
    the model tool loop."""
    cid_int = int(conversation_id) if conversation_id else None
    uid = getattr(user, "id", None)
    store = _load(uid)
    newest = None
    changed = False
    for rec in store.values():
        if rec.get("status") == "pending" and rec.get("conversation_id") is None:
            rec["conversation_id"] = cid_int
            changed = True
            newest = rec
    if changed:
        _save(uid, store)
    return client_view(newest) if newest else None


def open_for_conversation(user, conversation_id):
    """Pending records bound to THIS conversation (newest-ish first by store order reversed).
    Used by the deterministic typed pre-parser to resolve a confirm/cancel in context."""
    cid_int = int(conversation_id) if conversation_id else None
    store = _load(getattr(user, "id", None))
    recs = [r for r in store.values()
            if r.get("status") == "pending"
            and (cid_int is None or r.get("conversation_id") == cid_int)]
    return list(reversed(recs))


def client_view(rec, *, status=None):
    """Shape a stored record into the client confirmation payload (id + view + status)."""
    if not rec:
        return None
    view = rec.get("view") or {}
    return {
        "confirmation_id": rec.get("id"),
        "status": status or rec.get("status", "pending"),
        "expires_in": _TTL,
        "title": view.get("title", ""),
        "summary": view.get("summary", ""),
        "preview": view.get("preview", []),
        "actions": view.get("actions", {}),
    }


def summarize(action, params):
    """A short, deterministic human summary of what will happen (for the user + audit)."""
    params = params or {}
    if params:
        bits = ", ".join(f"{k}={v}" for k, v in list(params.items())[:6])
        return f"{action} ({bits})"
    return action
