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

CURRENT_CONTEXT_SCHEMA_VERSION = "2.3"

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
    """What truth WLJ can deterministically answer (static; no user data).

    The capability index — metric NAMES only, never data (the shrink-principle
    permanent resident: "what data exists so the model knows what to pull"). It
    advertises, per domain, which metrics are answerable as HISTORY via the
    get_history tool, so the model never guesses a (domain, metric) pair."""
    domains, truth_history, truth_entities = [], {}, {}
    try:
        from apps.core.truth import catalog
        cat = catalog.truth_catalog()
        if isinstance(cat, dict):
            domains = sorted(cat.keys())
            truth_history = {
                d: sorted(s.get("history", ()))
                for d, s in cat.items()
                if isinstance(s, dict) and s.get("history")
            }
            truth_entities = {
                d: sorted(s.get("entities", ()))
                for d, s in cat.items()
                if isinstance(s, dict) and s.get("entities")
            }
    except Exception:  # pragma: no cover - defensive
        domains, truth_history, truth_entities = [], {}, {}
    return {
        "answerable_domains": domains,
        "truth_history": truth_history,
        "truth_entities": truth_entities,
        # Semantic roles — so two similarly-named capabilities are never treated as
        # equivalent (e.g. health 'workouts' aggregate vs 'workout' record detail).
        "surface_roles": {
            "truth_history": ("AGGREGATE truth over a period — counts, totals, averages, "
                              "trends. NOT the contents of any individual record."),
            "truth_entities": ("DETAIL of an individual record — its identity, contents, "
                               "and child records (e.g. a workout's exercises, sets, reps, "
                               "weights)."),
        },
        "note": ("For 'how many / how much / average / trend' use get_history (metric "
                 "names in truth_history). For 'what / which / did I / the contents of a "
                 "specific record' use get_entity (record types in truth_entities). A "
                 "metric and a record type can share a domain — e.g. health 'workouts' "
                 "(aggregate session count) vs 'workout' (one workout's exercise detail) "
                 "— these are DIFFERENT surfaces; pick by whether the question is a count/"
                 "trend or a record's contents. Call a truth tool for anything not in this "
                 "baseline."),
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


def _resolve_fallback(user, conversation, now, current_url=None):
    """PRIORITY 2 (safety net only). The last object the user was AUTHORITATIVELY seen
    looking at in THIS conversation — used ONLY because the client reported no focus this
    turn (an intermittent omission ON THE SAME PAGE, e.g. an HTMX swap staled the <head>).
    Never authoritative, marked `source: fallback` / `authority: conversation_fallback`.

    NAVIGATION GUARD (the lifecycle rule): the fallback is honored ONLY when the current
    turn is on the SAME url the focus was authoritatively seen on. If the user has
    navigated to a DIFFERENT page (different url) that simply declared no focus, the
    previous object is NOT what they are viewing now — return None so a stale object can
    never be presented as the current screen. This makes "navigation replaces/clears the
    previous focus" structural, not advisory. Returns the marked focus dict or None."""
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

    # NAVIGATION GUARD — only a same-page transient omission may use the fallback. We must
    # be able to POSITIVELY confirm the current turn is on the page where this focus lived;
    # if the urls are absent or differ, the user has navigated and we do NOT serve it.
    remembered_url = (remembered.get("url") or "").strip()
    cur_url = (current_url or "").strip()
    if not (remembered_url and cur_url and remembered_url == cur_url):
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


def _remember_focus(conversation, ref, now, url=None):
    """Record an AUTHORITATIVE focus as the conversation's fallback, tagged with the PAGE
    URL it was seen on (the navigation discriminator). Only the current request's resolved
    focus is ever remembered — never a fallback (so age keeps growing from the last real
    sighting). Never raises."""
    if conversation is None or not ref:
        return
    try:
        from apps.ai.cos_services import current_focus_store as store
        store.remember_focus(
            conversation, ref,
            now_iso=now.isoformat() if now is not None else None,
            url=url,
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

    # 1) PRIORITY 1 — the current request is authoritative. Remember it tagged with THIS
    #    page's url so a later same-page omission (only) may fall back to it.
    focus = _resolve_focus(user, page_context)
    if focus is not None:
        _remember_focus(conversation, focus.get("ref"), now, url=location.get("url"))
        return {"status": "present", "location": location, "focus": focus}

    # 2) A declared-but-unresolved ref is a sync/ownership signal — surface it, never mask
    #    it with a possibly-different remembered object.
    if declared_ref:
        return {"status": "present", "location": location, "focus": None,
                "note": (f"page declared focus '{declared_ref}' but it did not resolve "
                         "(sync/ownership) — do not assume the object is absent")}

    # 3) PRIORITY 2 — safety net for an intermittent SAME-PAGE client omission ONLY. The
    #    navigation guard inside _resolve_fallback drops it if this turn is on a new page.
    fallback = _resolve_fallback(user, conversation, now, current_url=location.get("url"))
    if fallback is not None:
        return {"status": "present", "location": location, "focus": fallback}

    # Nothing in focus this turn and nothing remembered.
    if location:
        return {"status": "present", "location": location, "focus": None,
                "note": "page did not declare a focused object (Current Context Contract)"}
    return {"status": "none", "focus": None,
            "note": "no current page reported for this turn"}


def get_current_context_baseline(user, *, page_context=None, conversation=None,
                                 now=None, attachments=None) -> dict:
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
    baseline = {
        "schema_version": CURRENT_CONTEXT_SCHEMA_VERSION,
        "clock": _clock(user, now=now),
        "day_significance": _day_significance(user),
        "current_screen": _current_screen(user, page_context, conversation=conversation,
                                          now=now),
        "capabilities": _capabilities(),
    }
    # Attachments the user uploaded THIS turn (images/docs). They are the current FOCUS of
    # the turn — WLJ has already stored each as an artifact (provenance). The model perceives
    # the image directly; this tells it the `source_artifact_id` to tag on any candidate it
    # extracts (e.g. log_weight from a scale photo). WLJ never interprets the pixels.
    if attachments:
        baseline["attachments"] = list(attachments)
    return baseline
