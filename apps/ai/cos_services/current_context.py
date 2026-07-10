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

OWNERSHIP MODEL (the CURRENT REQUEST always wins):
  1. current request's declared focus (resolves) → AUTHORITATIVE (`authority: current_request`),
     and it is remembered as this conversation's last-seen object;
  2. current request declared a focus that FAILED → report the sync/ownership issue, never mask it;
  3. current request declared NO focus → priority-2 SAFETY NET: the conversation's last-seen
     object (`authority: conversation_fallback`, marked with freshness/age), used ONLY to survive
     an intermittent client omission. Conversation state is NEVER the authoritative source.
"""

import logging

logger = logging.getLogger(__name__)

CURRENT_CONTEXT_SCHEMA_VERSION = "2.2"

# Max chars of resolved canonical content to hand the model (bounds tokens; the model
# can always call a truth tool for the full record).
_FOCUS_CONTENT_CAP = 3500

# A priority-2 fallback older than this is flagged STALE: the user has likely navigated
# away from the last-seen object, so the model must confirm rather than assume.
_FALLBACK_STALE_AFTER_SECONDS = 15 * 60


def _day_significance(user) -> dict:
    """Deterministic 'is today a significant day?' FACT (name/theme/scripture) — e.g. Good
    Friday, Easter. Faith-gated. Facts only: the model decides how much to emphasize it (the
    old renderer's defining/highlighted tone-level was judgment and is NOT exposed). Returns
    {} when there is nothing significant or faith is disabled."""
    try:
        prefs = getattr(user, "preferences", None)
        if prefs is not None and not getattr(prefs, "faith_enabled", True):
            return {}
        from apps.core.utils import get_user_today
        from apps.faith.biblical_calendar import get_biblical_day
        sig = get_biblical_day(get_user_today(user)) or {}
        if not sig or not sig.get("name"):
            return {}
        return {k: sig.get(k) for k in ("name", "theme", "scripture_reference")
                if sig.get(k)}
    except Exception:  # pragma: no cover - defensive
        return {}


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
        # PRIORITY 1 — the current request is authoritative and live.
        "authority": "current_request",
    }


def _resolve_fallback(user, conversation, now):
    """PRIORITY 2 (safety net only). The last object the user was AUTHORITATIVELY seen
    looking at in THIS conversation — used ONLY because the client reported no focus this
    turn (an intermittent omission). Never authoritative: the identity may be stale
    (they may have navigated away), so it is marked `source: fallback`,
    `authority: conversation_fallback`, with a freshness verdict + age. Content is
    re-resolved FRESH from canonical truth, so a fallback never serves stale content or a
    deleted/unowned object. Returns the marked focus dict or None."""
    if not user or conversation is None:
        return None
    try:
        from apps.ai.cos_services import current_focus_store as store
        remembered = store.recall_focus(conversation)
    except Exception:  # pragma: no cover - defensive
        return None
    if not remembered:
        return None
    ref = (remembered.get("ref") or "").strip()
    if not ref:
        return None
    # Re-resolve the REFERENCE to fresh canonical content (identity may be stale; content
    # is not). Ownership is re-checked inside resolve_current_context.
    try:
        from apps.core.current_context import resolve_current_context
        resolved = resolve_current_context(user, ref=ref)
    except Exception:  # pragma: no cover - defensive
        logger.warning("CurrentContext: fallback resolve failed ref=%s", ref, exc_info=True)
        return None
    if not resolved or not (resolved.get("title") or resolved.get("content")):
        return None

    from apps.core.truth import freshness
    as_of = remembered.get("at")
    age_seconds = None
    verdict = freshness.STALE  # cautious default when we cannot age it
    try:
        from datetime import datetime
        at_dt = datetime.fromisoformat(as_of) if as_of else None
        if at_dt is not None and now is not None:
            age_seconds = int((now - at_dt).total_seconds())
            verdict = freshness.classify_sync_freshness(
                has_data=True, last_sync=at_dt, now=now,
                stale_after_seconds=_FALLBACK_STALE_AFTER_SECONDS,
            )
    except Exception:  # pragma: no cover - defensive
        pass

    return {
        "ref": resolved.get("ref") or ref,
        "kind": (resolved.get("kind") or "").strip(),
        "title": (resolved.get("title") or "").strip(),
        "content": (resolved.get("content") or "").strip()[:_FOCUS_CONTENT_CAP],
        "source": "fallback",
        "authority": "conversation_fallback",
        "freshness": verdict,          # 'current' | 'stale' (canonical vocabulary)
        "age_seconds": age_seconds,
        "as_of": as_of,
        "note": ("the client reported no focus this turn — this is the last object seen in "
                 "this conversation, not a confirmed current view; if it matters, confirm "
                 "the user still means it, especially if stale"),
    }


def _remember_focus(conversation, ref, now):
    """Record an AUTHORITATIVE focus as the conversation's fallback. Only the current
    request's resolved focus is ever remembered — never a fallback (so age keeps growing
    from the last real sighting). Never raises."""
    if conversation is None or not ref:
        return
    try:
        from apps.ai.cos_services import current_focus_store as store
        store.remember_focus(
            conversation, ref,
            now_iso=now.isoformat() if now is not None else None,
        )
    except Exception:  # pragma: no cover - defensive
        logger.debug("CurrentContext: remember focus skipped", exc_info=True)


def _current_screen(user, page_context, conversation=None, now=None) -> dict:
    """The structured WLJ page the user is currently viewing. Two deterministic parts:
    WHERE (location: url/module/title) and WHAT (focus). Focus follows a strict ownership
    model — the CURRENT REQUEST always wins; the conversation store only fills a gap:

      1. Current request declared a focus that resolves  → authoritative (and remembered).
      2. Current request declared a focus that FAILED     → report the sync/ownership issue;
         NEVER fall back (don't mask it with a different object).
      3. Current request declared NO focus                → priority-2 fallback (safety net),
         clearly marked stale-able; never authoritative.
    """
    if not page_context and conversation is None:
        return {"status": "none",
                "note": "no current page reported for this turn"}
    location = _location(page_context)
    declared_ref = (page_context.get("focus_ref") or "").strip() \
        if isinstance(page_context, dict) else ""

    # 1) PRIORITY 1 — the current request is authoritative.
    focus = _resolve_focus(user, page_context)
    if focus is not None:
        _remember_focus(conversation, focus.get("ref"), now)
        return {"status": "present", "location": location, "focus": focus}

    # 2) A declared-but-unresolved ref is a sync/ownership signal — surface it, never mask
    #    it with a possibly-different remembered object.
    if declared_ref:
        return {"status": "present", "location": location, "focus": None,
                "note": (f"page declared focus '{declared_ref}' but it did not resolve "
                         "(sync/ownership) — do not assume the object is absent")}

    # 3) PRIORITY 2 — safety net for an intermittent client omission ONLY.
    fallback = _resolve_fallback(user, conversation, now)
    if fallback is not None:
        return {"status": "present", "location": location, "focus": fallback}

    # Nothing in focus this turn and nothing remembered.
    if location:
        return {"status": "present", "location": location, "focus": None,
                "note": "page did not declare a focused object (Current Context Contract)"}
    return {"status": "none", "focus": None,
            "note": "no current page reported for this turn"}


def get_current_context_baseline(user, *, page_context=None, conversation=None,
                                 now=None) -> dict:
    """Assemble the fast-tier Current Context: clock, current screen, capability index.
    Pure, cheap, request-path-safe. No deterministic understanding here (that is a
    separate owned interface).

    `conversation` enables the priority-2 safety net: the current request's declared
    focus is authoritative and remembered; a turn with no declared focus falls back to
    the conversation's last-seen object, clearly marked stale-able. Omit it and Current
    Context is purely request-scoped (the fallback is simply unavailable)."""
    if now is None:
        try:
            from apps.core.utils import get_user_now
            now = get_user_now(user)
        except Exception:  # pragma: no cover - defensive
            now = None
    return {
        "schema_version": CURRENT_CONTEXT_SCHEMA_VERSION,
        "clock": _clock(user, now=now),
        "day_significance": _day_significance(user),
        "current_screen": _current_screen(user, page_context, conversation=conversation,
                                          now=now),
        "capabilities": _capabilities(),
    }
