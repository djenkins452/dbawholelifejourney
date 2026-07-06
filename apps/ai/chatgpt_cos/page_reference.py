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


def resolve_focused_object(user, url, module):
    """FOCUSED OBJECT AWARENESS — resolve the entity IN FOCUS from the page URL, against the
    canonical model, when the client sent only the page LOCATION (not the object content).
    Deterministic, user-scoped, per-module; the URL's /<pk>/ identifies a detail record, and
    a landing page falls back to that module's current object. Returns {title, content,
    kind} or None. GENERAL: extend by adding a module branch — no new context system."""
    if not user or not url:
        return None
    u = url.lower()
    m = re.search(r"/(\d+)(?:/|$)", u)
    pk = int(m.group(1)) if m else None
    try:
        # GOALS — a goal detail, or the mission goal when on the goals landing.
        if "/goals/" in u or module in ("purpose", "goals"):
            from apps.purpose.models import LifeGoal
            g = LifeGoal.objects.filter(user=user, pk=pk).first() if pk else None
            if g is None and (u.rstrip("/").endswith("/goals") or module in ("purpose", "goals")):
                try:
                    from apps.purpose.mission_selection import select_active_mission_goal
                    g = select_active_mission_goal(user)
                except Exception:
                    g = None
            if g is not None:
                bits = [g.title]
                for label, attr in (("", "description"), ("Why it matters: ", "why_it_matters"),
                                    ("Success looks like: ", "success_looks_like")):
                    val = (getattr(g, attr, "") or "").strip()
                    if val:
                        bits.append(f"{label}{val}")
                return {"title": g.title, "content": "\n".join(bits), "kind": "goal"}
        # JOURNAL — a specific entry.
        if "/journal/" in u and pk:
            from apps.journal.models import JournalEntry
            e = JournalEntry.objects.filter(user=user, pk=pk).first()
            if e is not None:
                title = e.title or f"Journal entry — {getattr(e, 'entry_date', '')}"
                head = f"{e.title}\n\n" if e.title else ""
                return {"title": title, "content": head + (e.body or ""), "kind": "journal_entry"}
        # TASKS — a specific task.
        if ("/task" in u) and pk:
            from apps.life.models import Task
            t = Task.objects.filter(user=user, pk=pk).first()
            if t is not None:
                return {"title": t.title, "content": t.title + (f"\n\n{t.notes}" if (t.notes or "").strip() else ""),
                        "kind": "task"}
    except Exception:
        logger.warning("focused_object: resolve failed url=%s module=%s", url, module, exc_info=True)
    return None


def resolve_page_focus(page_context, user=None):
    """The entity currently in focus on the page → {module, title, content, kind, url},
    or None. First reads the content the client captured in `page_content`; if only the
    page LOCATION came through, resolves the FOCUSED OBJECT server-side from the URL
    (`resolve_focused_object`). `content` is '' only when neither source has it."""
    if not page_context or not isinstance(page_context, dict):
        return None
    content = page_context.get("page_content") or {}
    if not isinstance(content, dict):
        content = {}
    module = (page_context.get("module") or "").strip()
    url = (page_context.get("url") or "").strip()
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
    # SERVER-SIDE focused-object resolution — so Beth knows WHICH object even when the
    # client sent only the page location (the Goals "details didn't come through" case).
    if not text and user is not None:
        obj = resolve_focused_object(user, url, module)
        if obj:
            title = title or obj.get("title", "")
            text = (obj.get("content") or "").strip()
            kind = obj.get("kind") or kind
    if not (title or text):
        return None
    return {"module": module, "title": title, "content": text, "kind": kind, "url": url}


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
