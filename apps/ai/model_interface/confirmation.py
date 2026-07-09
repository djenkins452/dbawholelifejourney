# ==============================================================================
# File: apps/ai/model_interface/confirmation.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Bound confirmation transactions (Blocker 1 — no confused deputy)
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-09
# ==============================================================================
"""
Bound confirmation transactions for the model-interface action path.

HARDENING (Slice 7.2 — Blocker 1). The old flow stored ONE mutable pending action per
user and executed "whatever was stored" on "yes" — a confused-deputy risk. Now each
confirmation is its own bound transaction with an identity:

    { id, action, params, summary, status }

`resolve` executes a SPECIFIC confirmation by id — never "whatever is stored." Each id is
single-use (consumed on resolve). Open confirmations are LISTABLE (`list_open`) so the
runtime can surface them in the standing context each turn — otherwise the model, which
only sees prior *text* across turns, would never have the id to resolve (the id is in a
tool result, not the transcript). Storage is a dedicated per-user cache dict, isolated
from the legacy `pending_intent_*` key so the two paths can never collide.
"""

import logging
import uuid

from django.core.cache import cache

logger = logging.getLogger(__name__)

_TTL = 300          # seconds an open confirmation stays resolvable
_MAX_OPEN = 5       # cap concurrent open confirmations per user


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


def create(user, action, params, summary):
    """Create a bound confirmation; return {confirmation_id, summary, expires_in} or None."""
    uid = getattr(user, "id", None)
    store = _load(uid)
    # Bound the number of open confirmations (drop the oldest if over cap).
    if len(store) >= _MAX_OPEN:
        for k in list(store)[: len(store) - _MAX_OPEN + 1]:
            store.pop(k, None)
    cid = uuid.uuid4().hex
    store[cid] = {"id": cid, "action": action, "params": dict(params or {}),
                  "summary": summary, "status": "pending"}
    _save(uid, store)
    return {"confirmation_id": cid, "summary": summary, "expires_in": _TTL}


def get(user, cid):
    """Return the confirmation record for this user+id, or None."""
    if not cid:
        return None
    rec = _load(getattr(user, "id", None)).get(cid)
    if not rec or rec.get("status") != "pending":
        return None
    return rec


def consume(user, cid):
    """Single-use: remove the confirmation so it can never be resolved twice."""
    uid = getattr(user, "id", None)
    store = _load(uid)
    if cid in store:
        store.pop(cid, None)
        _save(uid, store)


def list_open(user):
    """Open confirmations as [{confirmation_id, summary}] — surfaced in the standing
    context so the model can resolve a SPECIFIC one on the user's 'yes'."""
    store = _load(getattr(user, "id", None))
    return [{"confirmation_id": cid, "summary": r.get("summary", "")}
            for cid, r in store.items() if r.get("status") == "pending"]


def summarize(action, params):
    """A short, deterministic human summary of what will happen (for the user + audit)."""
    params = params or {}
    if params:
        bits = ", ".join(f"{k}={v}" for k, v in list(params.items())[:6])
        return f"{action} ({bits})"
    return action
