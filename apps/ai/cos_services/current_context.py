# ==============================================================================
# File: apps/ai/cos_services/current_context.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Current Context baseline (Pillar 4) — the FAST tier: "what's happening now"
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-09
# ==============================================================================
"""
Current Context — Pillar 4 of the WLJ ↔ model interface.

Current Context answers ONE question: "What is happening right now?" — the FAST-refresh
tier (seconds): the clock, the current WLJ page/screen the user is viewing, the active
task/selection, and a capability index. It changes constantly.

Current Context does NOT own deterministic understanding. Executive/clinical priority,
momentum, workload, patterns, material changes, etc. are DETERMINISTIC UNDERSTANDING —
the assessment tier of Truth (`apps/ai/model_interface/understanding.py`), a separate
owner with its own (medium) cadence. Refresh cadence is an ownership boundary
(Architecture Law) — we do not combine fast and medium concerns into one owner.

REQUEST-PATH-SAFE: everything here is cheap/deterministic (clock, static catalog,
client-supplied structured page context). No heavy compute, no warm needed.

`page_context` carries a REFERENCE, not scraped content: the page declares the canonical
object in focus via <meta name="wlj-context"> ('app_label.model:pk'), and WLJ resolves the
deterministic truth SERVER-SIDE, user-scoped, from the source-of-truth model
(apps.core.current_context.resolve_current_context). NOT a screenshot, NOT OCR, NOT DOM
scraping — client-scraped DOM is never treated as truth. The Current Context Contract is:
the page says WHERE it is + WHAT object it's showing; WLJ says what that object actually is.
"""

import logging

logger = logging.getLogger(__name__)

CURRENT_CONTEXT_SCHEMA_VERSION = "2.1"

# Max chars of resolved canonical content to hand the model (bounds tokens; the model
# can always call a truth tool for the full record).
_FOCUS_CONTENT_CAP = 3500


def _clock(user, now=None) -> dict:
    """User-local time + part of day. Cheap + deterministic; never raises."""
    try:
        from apps.core.truth import daypart
        if now is None:
            from apps.core.utils import get_user_now
            now = get_user_now(user)
        return {
            "local_time": now.strftime("%I:%M %p").lstrip("0"),
            "part_of_day": daypart.phase_of_day(user, now),
            "as_of": now.isoformat(),
        }
    except Exception:  # pragma: no cover - defensive
        logger.warning("CurrentContext: clock unavailable for user=%s",
                       getattr(user, "id", "?"))
        return {"status": "pending"}


def _capabilities() -> dict:
    """What truth WLJ can deterministically answer (static; no user data)."""
    try:
        from apps.core.truth import catalog
        cat = catalog.truth_catalog()
        domains = sorted(cat.keys()) if isinstance(cat, dict) else []
    except Exception:  # pragma: no cover - defensive
        domains = []
    return {
        "answerable_domains": domains,
        "note": "call a truth tool for anything not present in this baseline",
    }


def _location(page_context) -> dict:
    """The WHERE — navigation facts (url/module/page_title) the client reports. These are
    location, not content: safe to pass as 'where the user is'. Never scraped truth."""
    loc = {}
    for src, dst in (("url", "url"), ("module", "module"), ("page_title", "title")):
        v = (page_context.get(src) or "").strip() if isinstance(page_context, dict) else ""
        if v:
            loc[dst] = v
    return loc


def _resolve_focus(user, page_context):
    """The WHAT — the canonical object the page DECLARED via <meta name="wlj-context">,
    resolved SERVER-SIDE from the source-of-truth model (user-scoped). This is the
    Current Context Contract: the page sends a REFERENCE ('app.model:pk'); WLJ resolves
    the deterministic truth. We never treat client-scraped DOM as truth.

    Returns {ref, kind, title, content, source} or None (no ref, or it didn't resolve to
    an owned object). No reasoning, no summary, no LLM — pure canonical read."""
    if not user or not isinstance(page_context, dict):
        return None
    ref = (page_context.get("focus_ref") or "").strip()
    if not ref:
        return None
    try:
        from apps.core.current_context import resolve_current_context
        resolved = resolve_current_context(user, ref=ref)
    except Exception:  # pragma: no cover - defensive
        logger.warning("CurrentContext: focus resolve failed ref=%s", ref, exc_info=True)
        return None
    if not resolved or not (resolved.get("title") or resolved.get("content")):
        return None
    return {
        "ref": resolved.get("ref") or ref,
        "kind": (resolved.get("kind") or "").strip(),
        "title": (resolved.get("title") or "").strip(),
        "content": (resolved.get("content") or "").strip()[:_FOCUS_CONTENT_CAP],
        "source": "canonical",
    }


def _current_screen(user, page_context) -> dict:
    """The structured WLJ page the user is currently viewing. Two deterministic parts:
    WHERE (location: url/module/title) and WHAT (focus: the canonical object the page
    declared, resolved server-side). A declared reference that failed to resolve is a
    possible sync/ownership issue — reported as focus=None with the ref preserved, never
    as 'this does not exist'."""
    if not page_context:
        return {"status": "none",
                "note": "no current page reported for this turn"}
    location = _location(page_context)
    focus = _resolve_focus(user, page_context)
    declared_ref = (page_context.get("focus_ref") or "").strip() \
        if isinstance(page_context, dict) else ""
    screen = {"status": "present", "location": location, "focus": focus}
    if focus is None and declared_ref:
        # The page declared a focus but WLJ could not resolve it to an owned object.
        screen["note"] = (f"page declared focus '{declared_ref}' but it did not resolve "
                          "(sync/ownership) — do not assume the object is absent")
    elif focus is None:
        screen["note"] = "page did not declare a focused object (Current Context Contract)"
    return screen


def get_current_context_baseline(user, *, page_context=None, now=None) -> dict:
    """Assemble the fast-tier Current Context: clock, current screen, capability index.
    Pure, cheap, request-path-safe. No deterministic understanding here (that is a
    separate owned interface)."""
    return {
        "schema_version": CURRENT_CONTEXT_SCHEMA_VERSION,
        "clock": _clock(user, now=now),
        "current_screen": _current_screen(user, page_context),
        "capabilities": _capabilities(),
    }
