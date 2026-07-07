# ==============================================================================
# File: apps/ai/chatgpt_cos/page_reference.py
# Capability: PAGE-AWARE CONTEXTUAL CONVERSATION. When the user is looking at a WLJ page
# and says "summarize this", "explain this", "what do you think?", "should I still do
# this?" — the deictic "this/that/it" refers to the ENTITY CURRENTLY IN FOCUS on that
# page. Beth must resolve it against the current page's content, not restate it.
#
# Production failure that motivated this: on the Faith "Today's Reading" page (Isaiah
# 6:1-8 / 53:1-12), "Summarize this scripture" was misrouted to the SANDBOXED general
# lane (no personal/page data) → "I can't see specific content…", and the follow-up fell
# to a generic sleep recommendation. The page content was actually present in
# `page_context.page_content` — it just never reached a handler that could use it.
#
# GENERAL, NOT FAITH-SPECIFIC: resolves the focused entity across modules (scripture,
# journal entry, goal/milestone, task, health record, transaction) from the content the
# client already captured. Deterministic gate; one grounded LLM call to answer about the
# focused content; degrades to an honest "I see the page but not its details" (never
# abandons the thread). Consumes page_context; no new state.
# ==============================================================================
import logging
import re

logger = logging.getLogger(__name__)

# Deixis + page-action language that refers to what's ON the page.
_PAGE_VERBS = (
    "summarize", "summarise", "explain", "what does", "what do you think",
    "what are your thoughts", "tell me about", "break this down", "break it down",
    "should i still", "what should i do", "help me understand", "what's this",
    "whats this", "what is this", "walk me through", "unpack", "your take on",
)
_DEIXIS = ("this", "that", "these", "those", "it")

# Where to find the focused entity's text, across the page_content shapes the client
# sends for different modules. Ordered: single-text fields first, then list-shaped.
_TEXT_FIELDS = ("scripture_text", "body", "content", "description", "text", "summary",
                "entry_text", "note", "details", "message")
_LIST_FIELDS = ("scriptures", "milestones", "items", "verses")


def _cos_name(user):
    try:
        prefs = getattr(user, "preferences", None)
        if prefs is not None:
            return (getattr(prefs, "cos_display_name", "") or "Chief of Staff")
    except Exception:
        pass
    return "Chief of Staff"


def is_page_reference(message):
    """True when the message refers to what's on the current page — a page-action verb
    ('summarize/explain/what do you think'), or a SHORT deictic ('this'/'that') message
    (short so a long general question that merely contains 'this' isn't hijacked)."""
    n = (message or "").lower().strip()
    if not n:
        return False
    if any(v in n for v in _PAGE_VERBS):
        return True
    if len(n.split()) <= 8 and any(re.search(rf"\b{d}\b", n) for d in _DEIXIS):
        return True
    return False


def _narrate_journey_day(user, url):
    """FAITH JOURNEY (the PRODUCTION reading system) — resolve + narrate the JourneyDay in
    focus. `/faith/journey/today/` → the user's CURRENT day (user-scoped via their active
    journey); `/faith/journey/<arc_slug>/day/<n>/` → that specific day. JourneyDay is shared
    content (not a Narratable UserOwnedModel), so we narrate it here from its own fields:
    scripture refs + verse text (scripture_content.blocks) + context_before + key_insight +
    reflection_prompt. Nested JSON is coerced with str(...). Returns {title, content, kind,
    ref} or None."""
    if not user:
        return None
    u = (url or "").lower().rstrip("/")
    try:
        from apps.faith.journey.services import (
            get_active_journey, get_current_day, get_day_in_arc,
        )
        day = None
        m = re.search(r"/faith/journey/([^/]+)/day/(\d+)", u)
        if m:
            day = get_day_in_arc(m.group(1), int(m.group(2)))
        else:
            # 'today' (or any other journey URL) → the user's OWN current day.
            uj = get_active_journey(user)
            day = get_current_day(uj) if uj is not None else None
    except Exception:
        logger.warning("focused_object: journey resolve failed url=%s", url, exc_info=True)
        return None
    if day is None:
        return None

    head = "Today's reading"
    arc = getattr(day, "arc", None)
    if arc is not None:
        head = (getattr(arc, "name", "") or "").strip() or head
        jp = getattr(arc, "journey_path", None)
        if jp is not None:
            head = (getattr(jp, "name", "") or "").strip() or head
    title = f"{head} — Day {day.day_number}"

    parts = [title]
    refs = day.scripture_refs or []
    if isinstance(refs, list) and refs:
        parts.append("Scripture: " + ", ".join(str(r) for r in refs))
    sc = day.scripture_content if isinstance(day.scripture_content, dict) else {}
    blocks = sc.get("blocks") or []
    verses = []
    if isinstance(blocks, list):
        for b in blocks:
            if isinstance(b, dict):
                text = str(b.get("text") or "").strip()
                if text:
                    ref = str(b.get("ref") or "").strip()
                    verses.append((f"{ref} " if ref else "") + text)
    if verses:
        parts.append("\n".join(verses)[:2500])
    for label, attr in (("Context: ", "context_before"), ("Key insight: ", "key_insight"),
                        ("Reflection: ", "reflection_prompt")):
        val = str(getattr(day, attr, "") or "").strip()
        if val:
            parts.append(f"{label}{val[:800]}")
    return {"title": title, "content": "\n\n".join(parts).strip(),
            "kind": "scripture reading", "ref": None}


def resolve_focused_object(user, url, module):
    """DETERMINISTIC URL-BASED resolution of the object in focus — the Current Context
    Contract's server-side fallback for when the page did not DECLARE a focus_ref and no
    client content came through. User-scoped; per-module URL patterns; the object's content
    comes from the Narratable protocol (get_context_summary), so goal/journal/task all
    resolve consistently. Returns {title, content, kind, ref} or None."""
    if not user or not url:
        return None
    u = url.lower()
    m = re.search(r"/(\d+)(?:/|$)", u)
    pk = int(m.group(1)) if m else None

    # FAITH JOURNEY (production reading system) — the focused object is a JourneyDay whose
    # content lives on the day itself, served by function views at /faith/journey/*. Narrate
    # it directly (JourneyDay is not a Narratable UserOwnedModel).
    if "/faith/journey/" in u:
        return _narrate_journey_day(user, url)

    obj = None
    try:
        # GOALS — a goal detail (/goals/<pk>/), or the active mission goal on the goals
        # landing / Purpose dashboard (module 'purpose'/'goals' with no goal pk in the URL).
        if "/goals/" in u or module in ("purpose", "goals"):
            from apps.purpose.models import LifeGoal
            obj = LifeGoal.objects.filter(user=user, pk=pk).first() if (pk and "/goals/" in u) else None
            if obj is None:
                from apps.purpose.mission_selection import select_active_mission_goal
                obj = select_active_mission_goal(user)
        # JOURNAL — a specific entry.
        elif "/journal/" in u and pk:
            from apps.journal.models import JournalEntry
            obj = JournalEntry.objects.filter(user=user, pk=pk).first()
        # FAITH — the reading plan (get_context_summary narrates the current day's reading).
        elif "/reading-plans/progress/" in u and pk:
            from apps.faith.models import UserReadingPlan
            obj = UserReadingPlan.objects.filter(user=user, pk=pk).first()
        # TASKS — a specific task.
        elif "/task" in u and pk:
            from apps.life.models import Task
            obj = Task.objects.filter(user=user, pk=pk).first()
    except Exception:
        logger.warning("focused_object: resolve failed url=%s module=%s", url, module, exc_info=True)
        return None
    if obj is None or not hasattr(obj, "get_context_summary"):
        return None
    try:
        summ = obj.get_context_summary() or {}
    except Exception:
        logger.warning("focused_object: summary failed url=%s", url, exc_info=True)
        return None
    if not (summ.get("title") or summ.get("content")):
        return None
    if hasattr(obj, "context_ref"):
        summ.setdefault("ref", obj.context_ref())
    return summ


def resolve_page_focus(page_context, user=None):
    """The entity currently in focus on the page → {module, title, content, kind, url, ref},
    or None. Resolution order:
      1. `focus_ref` — the canonical reference the page DECLARED (<meta name="wlj-context">).
      2. Deterministic URL-based server resolution (`resolve_focused_object`) — works on any
         detail pk-URL or known landing WITHOUT the page declaring anything (restored
         fallback; server owns truth over the client scrape).
      3. `page_content` — content the client captured inline (last resort / client-only)."""
    if not page_context or not isinstance(page_context, dict):
        return None
    module = (page_context.get("module") or "").strip()
    url = (page_context.get("url") or "").strip()

    # 1) CONTRACT — the page declared its focused object; resolve it generically, server-side.
    ref = (page_context.get("focus_ref") or "").strip()
    if ref and user is not None:
        from apps.core.current_context import resolve_current_context
        resolved = resolve_current_context(user, ref=ref)
        if resolved and (resolved.get("title") or resolved.get("content")):
            return {"module": module, "title": (resolved.get("title") or "").strip(),
                    "content": (resolved.get("content") or "").strip(),
                    "kind": resolved.get("kind") or module, "url": url,
                    "ref": resolved.get("ref")}

    # 2) Deterministic URL-based server resolution (the restored fallback).
    if user is not None:
        obj = resolve_focused_object(user, url, module)
        if obj and (obj.get("title") or obj.get("content")):
            return {"module": module, "title": (obj.get("title") or "").strip(),
                    "content": (obj.get("content") or "").strip(),
                    "kind": obj.get("kind") or module, "url": url, "ref": obj.get("ref")}

    # 3) Legacy inline content (unmigrated pages / client-only content).
    content = page_context.get("page_content") or {}
    if not isinstance(content, dict):
        content = {}
    title = (page_context.get("page_title") or content.get("title")
             or content.get("reading_title") or "").strip()
    kind = content.get("type") or module or ""
    text = ""
    for k in _TEXT_FIELDS:
        v = content.get(k)
        if isinstance(v, str) and v.strip():
            text = v.strip()
            break
    if not text:
        for k in _LIST_FIELDS:
            v = content.get(k)
            if isinstance(v, list) and v:
                text = "; ".join(str(x).strip() for x in v if str(x).strip())
                if text:
                    break
    if not (title or text):
        return None
    return {"module": module, "title": title, "content": text, "kind": kind, "url": url,
            "ref": None}


def answer_page_reference(user, message, conversation, page_context):
    """Resolve a page-referential request against the focused entity and answer about it,
    grounded in its content. Returns a lane result dict, or None to let normal routing
    proceed (not a page reference, or no focused entity)."""
    if not is_page_reference(message):
        return None
    focus = resolve_page_focus(page_context, user=user)
    if focus is None:
        return None

    where = focus["title"] or (f"the {focus['module']} page" if focus["module"] else "this page")

    # Location came through but not the content — acknowledge WHERE they are and ask for
    # the detail, instead of a generic disclaimer or abandoning the thread.
    if not focus["content"]:
        return {"answer": (f"I can see you're on {where}, but its details didn't come "
                           "through to me — paste it here and I'll dig right in."),
                "tools_called": [], "tools_advertised": [], "lane": "page_reference",
                "page_focus": where}

    # We HAVE the focused content — answer the user's request about THIS, grounded in it.
    text = None
    try:
        from apps.ai.services import ai_service
        system = (
            f"You are {_cos_name(user)}, the user's Chief of Staff. The user is viewing "
            f"\"{where}\" in Whole Life Journey. Here is the content in focus:\n\n"
            f"{focus['content'][:4000]}\n\n"
            "Answer their request about THIS, grounded ONLY in the content above and the "
            "conversation so far. Be warm, specific, and concise — like one person talking, "
            "not a report. Never say you can't see the page or the content; you have it."
        )
        text = ai_service._call_api(system, message, max_tokens=500,
                                    endpoint="cos_page_reference", user=user)
    except Exception:
        logger.warning("page_reference: grounded answer failed", exc_info=True)
        text = None
    if text and str(text).strip():
        return {"answer": str(text).strip(), "tools_called": [], "tools_advertised": [],
                "lane": "page_reference", "page_focus": where}

    # DEGRADE PAGE-AWARE (never fall through to the contextless general lane). We resolved
    # the focused object but the writing model was unavailable (e.g. an LLM outage, or the
    # Celery worker lacking an OpenAI client). Returning None here would let the sandboxed
    # general lane answer as if it had no idea what the user is looking at — losing the
    # executive context. Instead we keep the focus and fail honestly, so the user still
    # gets a page-aware reply and can retry once the model is back.
    kind_label = {"goal": "goal", "journal_entry": "journal entry", "task": "task",
                  "scripture": "scripture"}.get(focus.get("kind") or "", "")
    subject = (f"your {kind_label} “{focus['title']}”"
               if (kind_label and focus.get("title")) else where)
    logger.warning("page_reference: LLM unavailable — page-aware degrade (focus=%s)", where)
    return {"answer": (f"I can see you're looking at {subject}, but my writing service is "
                       "temporarily unavailable right now — try again in a moment and I'll "
                       "dig right in."),
            "tools_called": [], "tools_advertised": [], "lane": "page_reference",
            "page_focus": where, "degraded": True}
