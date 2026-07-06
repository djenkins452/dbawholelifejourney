# ==============================================================================
# File: apps/core/current_context.py
# Capability: CURRENT CONTEXT CONTRACT — Page Awareness as a platform capability.
#
# A WLJ page DECLARES the canonical object in focus (a ContentType reference); the server
# RESOLVES its content, user-scoped, from the canonical model; Beth consumes the uniform
# result. No page-specific logic in Beth or the client — a new page becomes conversational
# by implementing this ONE contract. See docs/WLJ_CURRENT_CONTEXT_CONTRACT.md.
#
# Three generic layers:
#   1. Declaration — CurrentContextMixin on a view emits <meta name="wlj-context">.
#   2. Transport   — the chat widget reads that reference and sends it (never scraped truth).
#   3. Resolution  — resolve_current_context() fetches the object and calls its
#                    get_context_summary() (the Narratable protocol), user-scoped.
# ==============================================================================
import contextvars
import logging
import re

logger = logging.getLogger(__name__)

# TURN-SCOPED CURRENT CONTEXT. Resolved ONCE at the top of a CoS turn (before lane routing)
# and read at the shared LLM-call choke point, so EVERY reasoning lane's answer begins with
# the same grounded context — Current Context is a Chief-of-Staff capability, not a per-lane
# or tool-loop-only one. See docs/WLJ_CURRENT_CONTEXT_CONTRACT.md.
_CURRENT_FOCUS = contextvars.ContextVar("wlj_current_focus", default=None)


def set_current_focus(focus):
    """Set (or clear, with None) the object in focus for the current turn."""
    _CURRENT_FOCUS.set(focus if (focus and (focus.get("content") or "").strip()) else None)


def get_current_focus():
    try:
        return _CURRENT_FOCUS.get()
    except Exception:
        return None


def current_context_preamble():
    """The leading system-prompt block every reasoning lane starts with when an object is in
    focus. Authoritative: if the message is about what's on screen, the lane answers about
    THIS object even when its own specialization is narrower. Empty when nothing is in focus."""
    focus = get_current_focus()
    if not focus:
        return ""
    content = (focus.get("content") or "").strip()
    if not content:
        return ""
    title = focus.get("title") or focus.get("kind") or "this"
    kind = focus.get("kind") or ""
    label = f'"{title}"' + (f" ({kind})" if kind else "")
    return (
        f"CURRENT CONTEXT — RIGHT NOW the user is viewing {label} in Whole Life Journey. "
        "This is the object their message is about when they say 'this/that/it' or ask any "
        "question that fits what's on screen (e.g. 'am I making progress?', 'what do you "
        "think?', 'should I change anything?', 'how was I feeling?'). When the message is "
        "about what they're viewing, answer about THIS object, grounded in the content below "
        "— even if a more specialized instruction further down is narrower in scope. If the "
        "message is clearly unrelated to it, follow the instruction below instead.\n"
        "--- OBJECT IN FOCUS ---\n"
        f"{content[:3500]}\n"
        "--- END OBJECT ---\n\n"
    )

# Canonical reference shape: "app_label.model:pk" (e.g. "purpose.lifegoal:42").
_REF_RE = re.compile(r"^([a-z_]+)\.([a-z_]+):(\d+)$", re.IGNORECASE)

# Generic text fields that don't need a label when composing content.
_GENERIC_FIELDS = {"description", "body", "content", "text", "notes", "summary", "details"}


class NarratableMixin:
    """Opt-in protocol that makes a model Beth-aware. The default reads the title plus the
    fields named in CONTEXT_FIELDS (or common text fields); models override
    get_context_summary() for richer narration. Mixed into UserOwnedModel, so all user data
    is narratable by default."""

    # Ordered field names whose text composes the object's narratable content. Override per model.
    CONTEXT_FIELDS = ()

    def context_kind(self):
        try:
            return str(self._meta.verbose_name)
        except Exception:
            return self.__class__.__name__

    def context_title(self):
        for attr in ("title", "name", "headline"):
            v = getattr(self, attr, "")
            if isinstance(v, str) and v.strip():
                return v.strip()
        return str(self)

    def context_ref(self):
        return f"{self._meta.app_label}.{self._meta.model_name}:{self.pk}"

    def is_owned_by(self, user):
        """Generic ownership check. UserOwnedModel has a `user` FK; override if different."""
        owner_id = getattr(self, "user_id", None)
        return owner_id is not None and owner_id == getattr(user, "id", None)

    def _default_context_fields(self):
        return [f for f in ("description", "body", "content", "notes", "summary", "text")
                if self._has_field(f)]

    def _has_field(self, name):
        try:
            self._meta.get_field(name)
            return True
        except Exception:
            return False

    def get_context_summary(self):
        """The uniform shape Beth consumes: {title, content, kind}."""
        title = self.context_title()
        lines = []
        for f in (self.CONTEXT_FIELDS or self._default_context_fields()):
            val = getattr(self, f, "")
            if isinstance(val, str) and val.strip():
                label = ""
                if f not in _GENERIC_FIELDS:
                    try:
                        label = f"{str(self._meta.get_field(f).verbose_name).capitalize()}: "
                    except Exception:
                        label = ""
                lines.append(f"{label}{val.strip()}")
        content = "\n\n".join([title] + lines).strip()
        return {"title": title, "content": content, "kind": self.context_kind()}


def resolve_current_context(user, ref=None, url=None):
    """THE generic resolver. Given the canonical reference a page declared
    ('app_label.model:pk'), return {title, content, kind, ref} for the focused object —
    fetched user-scoped from the canonical model (the source of truth). No module branches.
    Returns None when nothing is in focus, the ref is malformed, or the object isn't owned."""
    if not user or not ref:
        return None
    m = _REF_RE.match(str(ref).strip())
    if not m:
        return None
    app_label, model_name, pk = m.group(1).lower(), m.group(2).lower(), int(m.group(3))
    try:
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_by_natural_key(app_label, model_name)
        model = ct.model_class()
        if model is None:
            return None
        obj = model.objects.filter(pk=pk).first()
    except Exception:
        logger.warning("current_context: lookup failed ref=%s", ref, exc_info=True)
        return None
    if obj is None:
        return None

    # Ownership — never leak another user's record.
    if hasattr(obj, "is_owned_by"):
        owned = obj.is_owned_by(user)
    else:
        owned = getattr(obj, "user_id", None) == getattr(user, "id", None)
    if not owned:
        logger.warning("current_context: ownership denied ref=%s user=%s",
                       ref, getattr(user, "id", None))
        return None

    if not hasattr(obj, "get_context_summary"):
        return None
    try:
        summ = obj.get_context_summary() or {}
    except Exception:
        logger.warning("current_context: summary failed ref=%s", ref, exc_info=True)
        return None
    if not (summ.get("title") or summ.get("content")):
        return None
    summ.setdefault("ref", obj.context_ref() if hasattr(obj, "context_ref") else ref)
    return summ


class CurrentContextMixin:
    """Declare the page's focused canonical object. A DetailView gets it from self.object;
    override get_current_context_object() otherwise. Emits `current_context_descriptor` into
    the template context; base.html renders the <meta name="wlj-context"> from it. This one
    line is ALL a new page implements to become Beth-aware."""

    def get_current_context_object(self):
        return getattr(self, "object", None)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        obj = self.get_current_context_object()
        if obj is not None and hasattr(obj, "context_ref"):
            try:
                ctx["current_context_descriptor"] = {
                    "ref": obj.context_ref(),
                    "kind": obj.context_kind() if hasattr(obj, "context_kind") else "",
                    "title": obj.context_title() if hasattr(obj, "context_title") else str(obj),
                }
            except Exception:
                logger.warning("CurrentContextMixin: descriptor build failed", exc_info=True)
        return ctx
