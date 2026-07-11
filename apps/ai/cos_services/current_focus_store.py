# ==============================================================================
# File: apps/ai/cos_services/current_focus_store.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Current Context SAFETY NET — the last authoritatively-resolved focus
#              reference for a conversation. Priority-2 fallback ONLY.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-10
# ==============================================================================
"""
Conversation-scoped last-known focus — a SAFETY NET, never the source of truth.

The CURRENT REQUEST is always authoritative for Current Context ("what is the user
looking at right now?"). This store exists ONLY so that when a single turn arrives
without a `focus_ref` (an intermittent client omission — the input kept focus, an
HTMX swap staled the <head>, etc.), WLJ can fall back to the last object the user was
authoritatively seen looking at IN THIS CONVERSATION, clearly marked as a stale-able
fallback. The moment a fresh `focus_ref` arrives, it wins and overwrites this.

We store the REFERENCE ONLY (never resolved content): the object identity may go
stale, but content is always re-resolved fresh from canonical truth on recall, so a
fallback never serves stale content or a deleted/unowned object. Cache-backed with a
short TTL — a net for a brief client hiccup, not conversation history.
"""

import logging

logger = logging.getLogger(__name__)

# Safety-net window. Long enough to survive a client hiccup across a few turns; short
# enough that this is a net, not a memory. Not history — Current Context owns "now".
_TTL_SECONDS = 3600

_KEY = "wlj:cc:last_focus:{cid}"


def _key(conversation):
    cid = getattr(conversation, "id", None)
    return _KEY.format(cid=cid) if cid else None


def remember_focus(conversation, ref, *, now_iso=None, url=None):
    """Record the AUTHORITATIVELY-resolved focus reference for this conversation as the
    priority-2 fallback for a later turn that arrives without one. Stores the reference,
    the timestamp it was authoritatively seen, and the PAGE URL it was seen on (never
    content). The url is the navigation discriminator: the fallback is a SAME-PAGE
    transient-omission net, so recall only honors it when the later turn is on that same
    url (see current_context._resolve_fallback). Never raises."""
    key = _key(conversation)
    if not key or not ref:
        return
    try:
        from django.core.cache import cache
        cache.set(key, {"ref": str(ref), "at": now_iso,
                        "url": (str(url).strip() if url else None)}, _TTL_SECONDS)
    except Exception:  # pragma: no cover - defensive
        logger.debug("current_focus_store: remember skipped", exc_info=True)


def recall_focus(conversation):
    """The last authoritatively-seen focus {ref, at} for this conversation, or None.
    Never raises."""
    key = _key(conversation)
    if not key:
        return None
    try:
        from django.core.cache import cache
        val = cache.get(key)
        return val if isinstance(val, dict) and val.get("ref") else None
    except Exception:  # pragma: no cover - defensive
        logger.debug("current_focus_store: recall skipped", exc_info=True)
        return None


def forget_focus(conversation):
    """Explicitly drop the remembered focus (e.g. a clear subject change). Never raises."""
    key = _key(conversation)
    if not key:
        return
    try:
        from django.core.cache import cache
        cache.delete(key)
    except Exception:  # pragma: no cover - defensive
        logger.debug("current_focus_store: forget skipped", exc_info=True)
