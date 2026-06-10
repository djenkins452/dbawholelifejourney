"""Page-awareness continuity — bounded, cache-based, conversation-scoped.

When a turn lands on a page WITH content (e.g. a Faith reading/journey with
scripture), we drop a short-lived marker keyed by conversation. Its only job is
to let follow-ups ("tell me more", "go deeper", "explain that") stay grounded in
the CURRENT page instead of being hijacked by an earlier HEALTH thread's
continuity. No new memory system; a 15-min TTL marker, same pattern as the
health thread context. Never raises.

Design rule: this NEVER asserts page content by itself — it only signals "the
user is actively on a content page", so the page-aware prompt path (which fetches
the real, current scripture each turn) wins over the health deepen path. It can
therefore never introduce stale/hallucinated content.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_TTL_SECONDS = 900  # 15 minutes — "current thread" lifetime


def page_continuity_enabled() -> bool:
    try:
        from django.conf import settings
        return bool(getattr(settings, "WLJ_BETH_PAGE_CONTINUITY", True))
    except Exception:
        return True


def _key(conversation):
    cid = getattr(conversation, "id", None)
    return f"beth:pgctx:{cid}" if cid else None


def remember_active_page(conversation):
    """Mark that the user is actively on a content page (call when the page-aware
    prompt is injected WITH content). Refreshes the TTL each turn."""
    if not page_continuity_enabled():
        return
    try:
        from django.core.cache import cache
        key = _key(conversation)
        if key:
            cache.set(key, True, _TTL_SECONDS)
    except Exception:
        logger.debug("remember_active_page failed", exc_info=True)


def active_page_present(conversation) -> bool:
    """True if the user was recently on a content page in this conversation."""
    if not page_continuity_enabled():
        return False
    try:
        from django.core.cache import cache
        key = _key(conversation)
        return bool(cache.get(key)) if key else False
    except Exception:
        return False
