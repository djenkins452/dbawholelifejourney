"""
Legacy views.

Slice 1: Home (the Hearth).
Slice 2: Memory Library (card/list, search, filters, sort, empty states,
archive/restore) + Memory Editor (create/edit, status handling, autosave,
basic media upload, voice/analyze placeholders). Fully inside the Legacy
experience; no assistant, no CoS, no changes to the WLJ dashboard.
"""

from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.legacy.models import Media, Memory, MemoryRevision
from apps.legacy.services.home import build_home_context


# ── Shared ─────────────────────────────────────────────────────────────────
class LegacyContextMixin(LoginRequiredMixin):
    """Shared context for every Legacy page (drives sidebar active-state)."""

    nav_active = None

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.setdefault("nav_active", self.nav_active)
        return ctx


class HearthView(LegacyContextMixin, TemplateView):
    template_name = "legacy/home.html"
    nav_active = "home"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(build_home_context(self.request.user))
        return ctx


class LegacyPlaceholderView(LegacyContextMixin, TemplateView):
    """Graceful placeholder for destinations arriving in later Phase-1 slices."""

    template_name = "legacy/_placeholder.html"


# ── Library ────────────────────────────────────────────────────────────────
STATUS_CHOICES = [
    ("all", "All"),
    ("draft", "Draft"),
    ("legacy", "Legacy"),
    ("archived", "Archived"),
]
TIMEFRAME_CHOICES = [
    ("all", "All time"),
    ("today", "Today"),
    ("week", "This week"),
    ("month", "This month"),
    ("year", "This year"),
    ("custom", "Custom"),
]
SORT_CHOICES = [
    ("recent", "Newest first"),
    ("oldest", "Oldest first"),
    ("updated", "Recently updated"),
    ("title", "Title A–Z"),
]
SORT_FIELDS = {
    "recent": "-created_at",
    "oldest": "created_at",
    "updated": "-updated_at",
    "title": "title",
}


def _parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


class LibraryView(LegacyContextMixin, TemplateView):
    template_name = "legacy/library.html"
    nav_active = "stories"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        req = self.request.GET

        status = req.get("status", "all")
        if status not in dict(STATUS_CHOICES):
            status = "all"
        timeframe = req.get("tf", "all")
        if timeframe not in dict(TIMEFRAME_CHOICES):
            timeframe = "all"
        sort = req.get("sort", "recent")
        if sort not in SORT_FIELDS:
            sort = "recent"
        view_mode = "list" if req.get("view") == "list" else "cards"
        q = (req.get("q") or "").strip()

        # Base queryset by status (archived uses the soft-delete manager escape hatch).
        if status == "archived":
            qs = Memory.all_objects.filter(user=user, status="archived")
        else:
            qs = Memory.objects.filter(user=user)  # active only
            if status == "draft":
                qs = qs.filter(entry_state=Memory.EntryState.DRAFT)
            elif status == "legacy":
                qs = qs.filter(entry_state__in=[Memory.EntryState.LEGACY, Memory.EntryState.SHARED])

        # Time frame (by capture time).
        now = timezone.now()
        start = None
        custom_start = _parse_date(req.get("start"))
        custom_end = _parse_date(req.get("end"))
        if timeframe == "today":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif timeframe == "week":
            monday = (now - timedelta(days=now.weekday()))
            start = monday.replace(hour=0, minute=0, second=0, microsecond=0)
        elif timeframe == "month":
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif timeframe == "year":
            start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        if start is not None:
            qs = qs.filter(created_at__gte=start)
        if timeframe == "custom":
            if custom_start:
                qs = qs.filter(created_at__date__gte=custom_start)
            if custom_end:
                qs = qs.filter(created_at__date__lte=custom_end)

        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(body__icontains=q))

        qs = qs.select_related("attributed_to", "primary_media").order_by(SORT_FIELDS[sort])

        # Preserve non-status params when rendering status pills.
        base_params = req.copy()
        base_params.pop("status", None)
        base_params.pop("page", None)

        ctx.update({
            "memories": qs,
            "total_count": qs.count(),
            "view_mode": view_mode,
            "status": status,
            "timeframe": timeframe,
            "sort": sort,
            "q": q,
            "custom_start": req.get("start", ""),
            "custom_end": req.get("end", ""),
            "status_choices": STATUS_CHOICES,
            "timeframe_choices": TIMEFRAME_CHOICES,
            "sort_choices": SORT_CHOICES,
            "base_query": base_params.urlencode(),
            "is_archived_view": status == "archived",
            "has_any_memories": Memory.all_objects.filter(user=user).exclude(status="deleted").exists(),
        })
        return ctx


# ── Editor ─────────────────────────────────────────────────────────────────
class EditorView(LegacyContextMixin, TemplateView):
    template_name = "legacy/editor.html"
    nav_active = "stories"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        memory = None
        pk = kwargs.get("pk")
        if pk is not None:
            memory = get_object_or_404(
                Memory.all_objects, pk=pk, user=self.request.user
            )
        ctx["memory"] = memory
        ctx["media_items"] = list(memory.media.all()) if memory else []
        return ctx


class MemorySaveView(LegacyContextMixin, View):
    """Create/update a memory. Handles autosave (JSON) and button actions (redirect)."""

    def post(self, request, *args, **kwargs):
        user = request.user
        pk = request.POST.get("pk") or None
        action = request.POST.get("action", "autosave")
        title = (request.POST.get("title") or "").strip()
        body = request.POST.get("body") or ""

        if pk:
            memory = get_object_or_404(Memory.all_objects, pk=pk, user=user)
        else:
            memory = Memory(
                user=user,
                created_via=Memory.CREATED_VIA_MANUAL,
                source_kind=Memory.SourceKind.OWNER,
            )

        content_changed = (memory.title != title) or (memory.body != body)

        # Append/supersede: snapshot prior telling before editing a canonical memory.
        if memory.pk and content_changed and memory.entry_state == Memory.EntryState.LEGACY:
            MemoryRevision.objects.create(
                memory=memory,
                title=memory.title,
                body=memory.body,
                entry_state=memory.entry_state,
                edited_by=user,
            )

        memory.title = title
        memory.body = body
        if memory.pk:
            memory.updated_by = user

        if action == "legacy":
            memory.entry_state = Memory.EntryState.LEGACY
            if memory.status != "active":
                memory.status = "active"
        elif action == "draft":
            memory.entry_state = Memory.EntryState.DRAFT
            if memory.status != "active":
                memory.status = "active"
        elif action == "archive":
            memory.status = "archived"
        # autosave: leave entry_state/status as-is (new memories default to DRAFT).

        memory.save()

        if action == "autosave" or request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({
                "ok": True,
                "pk": memory.pk,
                "saved_at": timezone.localtime(memory.updated_at).strftime("%-I:%M %p"),
                "edit_url": reverse("legacy:editor", args=[memory.pk]),
            })

        if action == "legacy":
            messages.success(request, "Added to your Legacy.")
            return redirect("legacy:library")
        if action == "archive":
            messages.success(request, "Memory set aside.")
            return redirect("legacy:library")
        messages.success(request, "Draft saved.")
        return redirect("legacy:editor", pk=memory.pk)


class MemoryArchiveView(LegacyContextMixin, View):
    def post(self, request, pk, *args, **kwargs):
        memory = get_object_or_404(Memory.all_objects, pk=pk, user=request.user)
        memory.archive()
        messages.success(request, "Memory set aside.")
        return redirect(request.POST.get("next") or "legacy:library")


class MemoryRestoreView(LegacyContextMixin, View):
    def post(self, request, pk, *args, **kwargs):
        memory = get_object_or_404(Memory.all_objects, pk=pk, user=request.user)
        memory.restore()
        messages.success(request, "Memory restored.")
        return redirect(request.POST.get("next") or "legacy:library")


class MediaAddView(LegacyContextMixin, View):
    """Basic media upload attached to an existing memory."""

    _EXT_TYPE = {
        "jpg": Media.MediaType.PHOTO, "jpeg": Media.MediaType.PHOTO, "png": Media.MediaType.PHOTO,
        "gif": Media.MediaType.PHOTO, "webp": Media.MediaType.PHOTO, "heic": Media.MediaType.PHOTO,
        "mp4": Media.MediaType.VIDEO, "mov": Media.MediaType.VIDEO, "m4v": Media.MediaType.VIDEO,
        "mp3": Media.MediaType.AUDIO, "m4a": Media.MediaType.AUDIO, "wav": Media.MediaType.AUDIO,
        "pdf": Media.MediaType.DOCUMENT, "doc": Media.MediaType.DOCUMENT, "docx": Media.MediaType.DOCUMENT,
    }

    def post(self, request, pk, *args, **kwargs):
        memory = get_object_or_404(Memory.all_objects, pk=pk, user=request.user)
        f = request.FILES.get("file")
        if f:
            ext = (f.name.rsplit(".", 1)[-1] if "." in f.name else "").lower()
            media = Media.objects.create(
                user=request.user,
                media_type=self._EXT_TYPE.get(ext, Media.MediaType.OTHER),
                file=f,
                original_filename=f.name[:255],
                created_via=Media.CREATED_VIA_MANUAL,
            )
            memory.media.add(media)
            if media.media_type == Media.MediaType.PHOTO and not memory.primary_media_id:
                memory.primary_media = media
                memory.save(update_fields=["primary_media", "updated_at"])
            messages.success(request, "Added to this memory.")
        return redirect("legacy:editor", pk=memory.pk)
