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
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, TemplateView, UpdateView

from django.template.loader import render_to_string

from apps.legacy.forms import ContributorForm, OutputForm, PersonForm, PlaceForm
from apps.legacy.models import (
    Contributor, Media, Memory, MemoryDiscovery, MemoryRevision, Output, Person, Place,
    Relationship,
)
from apps.legacy.services import discovery as discovery_svc
from apps.legacy.services.home import build_home_context
from apps.legacy.services.media_utils import guess_media_type


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
        ctx["all_people"] = Person.objects.filter(user=self.request.user)
        ctx["all_places"] = Place.objects.filter(user=self.request.user)
        ctx["selected_people"] = set(memory.people.values_list("pk", flat=True)) if memory else set()
        ctx["selected_places"] = set(memory.places.values_list("pk", flat=True)) if memory else set()
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

        # Graph links (who's in it / where it happened) — validated to the owner.
        if "people" in request.POST:
            ids = request.POST.getlist("people")
            memory.people.set(Person.objects.filter(user=user, pk__in=ids))
        if "places" in request.POST:
            ids = request.POST.getlist("places")
            memory.places.set(Place.objects.filter(user=user, pk__in=ids))

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


class MemoryDiscoverView(LegacyContextMixin, View):
    """
    Story Discovery Engine entry point. Upserts the memory, runs discovery, and
    returns the rendered Discovery Review panel (HTML). Proposal-first: nothing
    is promoted to canonical truth here.
    """

    def post(self, request, *args, **kwargs):
        user = request.user
        pk = request.POST.get("pk") or None
        title = (request.POST.get("title") or "").strip()
        body = request.POST.get("body") or ""

        if pk:
            memory = get_object_or_404(Memory.all_objects, pk=pk, user=user)
        else:
            memory = Memory(user=user, created_via=Memory.CREATED_VIA_MANUAL,
                            source_kind=Memory.SourceKind.OWNER)
        memory.title = title
        memory.body = body
        if memory.pk:
            memory.updated_by = user
        memory.save()

        status, _ = discovery_svc.run_discovery(memory)
        groups = discovery_svc.grouped_proposals(memory)
        html = render_to_string("legacy/_discovery_review.html", {
            "memory": memory,
            "groups": groups,
            "status": status,
            "summary": discovery_svc.summary_text(groups),
        }, request=request)
        return JsonResponse({"ok": True, "pk": memory.pk, "status": status, "html": html})


class DiscoveryConfirmView(LegacyContextMixin, View):
    """Promotion gate — accept selected (or all) discoveries, reject the rest."""

    def post(self, request, pk, *args, **kwargs):
        memory = get_object_or_404(Memory.all_objects, pk=pk, user=request.user)
        accept_all = request.POST.get("accept_all") == "1"
        accepted_ids = request.POST.getlist("accept")
        resolutions = {k[len("resolve_"):]: v for k, v in request.POST.items()
                       if k.startswith("resolve_")}
        n = discovery_svc.confirm_discoveries(
            memory, accepted_ids, accept_all=accept_all, resolutions=resolutions)
        if n:
            messages.success(request, f"Added {n} connection{'s' if n != 1 else ''} to this memory.")
        else:
            messages.success(request, "Nothing added.")
        return redirect("legacy:editor", pk=memory.pk)


class MemorySetStateView(LegacyContextMixin, View):
    """Change a memory's entry_state (draft/legacy) without touching its content."""

    def post(self, request, pk, *args, **kwargs):
        memory = get_object_or_404(Memory.all_objects, pk=pk, user=request.user)
        to = request.POST.get("to")
        if to == "legacy":
            memory.entry_state = Memory.EntryState.LEGACY
        elif to == "draft":
            memory.entry_state = Memory.EntryState.DRAFT
        else:
            return redirect(request.POST.get("next") or "legacy:studio")
        if memory.status != "active":
            memory.status = "active"
        memory.updated_by = request.user
        memory.save()
        messages.success(request, "Added to your Legacy." if to == "legacy" else "Moved to drafts.")
        return redirect(request.POST.get("next") or "legacy:studio")


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

    def post(self, request, pk, *args, **kwargs):
        memory = get_object_or_404(Memory.all_objects, pk=pk, user=request.user)
        f = request.FILES.get("file")
        if f:
            media = Media.objects.create(
                user=request.user,
                media_type=guess_media_type(f.name),
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


# ── People ─────────────────────────────────────────────────────────────────
class PeopleView(LegacyContextMixin, TemplateView):
    template_name = "legacy/people.html"
    nav_active = "people"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        q = (self.request.GET.get("q") or "").strip()
        people = Person.objects.filter(user=self.request.user)
        if q:
            people = people.filter(Q(display_name__icontains=q) | Q(also_known_as__icontains=q))
        ctx["people"] = people.select_related("primary_photo")
        ctx["q"] = q
        ctx["total_count"] = people.count()
        return ctx


class PersonFormMixin(LegacyContextMixin):
    model = Person
    form_class = PersonForm
    template_name = "legacy/person_form.html"
    nav_active = "people"

    def get_success_url(self):
        return reverse("legacy:person_detail", args=[self.object.pk])


class PersonCreateView(PersonFormMixin, CreateView):
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["heading"] = "Add someone"
        return ctx

    def form_valid(self, form):
        form.instance.user = self.request.user
        form.instance.created_via = Person.CREATED_VIA_MANUAL
        messages.success(self.request, "Person added.")
        return super().form_valid(form)


class PersonEditView(PersonFormMixin, UpdateView):
    def get_queryset(self):
        return Person.all_objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["heading"] = "Edit person"
        return ctx

    def form_valid(self, form):
        messages.success(self.request, "Saved.")
        return super().form_valid(form)


class PersonProfileView(LegacyContextMixin, DetailView):
    model = Person
    template_name = "legacy/person_detail.html"
    context_object_name = "person"
    nav_active = "people"

    def get_queryset(self):
        return Person.all_objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        person = self.object
        memories = person.memories.all().select_related("primary_media").order_by("-created_at")
        ctx["memories"] = memories
        ctx["media"] = Media.objects.filter(memories__in=memories).distinct()[:12]
        ctx["places"] = Place.objects.filter(memories__in=memories).distinct()
        ctx["relationships"] = (
            Relationship.objects.filter(Q(from_person=person) | Q(to_person=person))
            .select_related("from_person", "to_person")
        )
        # Contributor attribution seen across this person's memories.
        contributors = set()
        for m in memories:
            if m.contributor_id:
                contributors.add(m.contributor.name)
        ctx["contributors"] = sorted(contributors)
        return ctx


class PersonArchiveView(LegacyContextMixin, View):
    def post(self, request, pk, *args, **kwargs):
        p = get_object_or_404(Person.all_objects, pk=pk, user=request.user)
        p.archive()
        messages.success(request, "Person set aside.")
        return redirect("legacy:people")


class PersonRestoreView(LegacyContextMixin, View):
    def post(self, request, pk, *args, **kwargs):
        p = get_object_or_404(Person.all_objects, pk=pk, user=request.user)
        p.restore()
        messages.success(request, "Person restored.")
        return redirect("legacy:person_detail", pk=p.pk)


# ── Places ─────────────────────────────────────────────────────────────────
class PlacesView(LegacyContextMixin, TemplateView):
    template_name = "legacy/places.html"
    nav_active = "places"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        q = (self.request.GET.get("q") or "").strip()
        places = Place.objects.filter(user=self.request.user)
        if q:
            places = places.filter(Q(name__icontains=q) | Q(location_text__icontains=q))
        ctx["places"] = places.select_related("primary_photo")
        ctx["q"] = q
        ctx["total_count"] = places.count()
        return ctx


class PlaceFormMixin(LegacyContextMixin):
    model = Place
    form_class = PlaceForm
    template_name = "legacy/place_form.html"
    nav_active = "places"

    def get_success_url(self):
        return reverse("legacy:place_detail", args=[self.object.pk])


class PlaceCreateView(PlaceFormMixin, CreateView):
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["heading"] = "Add a place"
        return ctx

    def form_valid(self, form):
        form.instance.user = self.request.user
        form.instance.created_via = Place.CREATED_VIA_MANUAL
        messages.success(self.request, "Place added.")
        return super().form_valid(form)


class PlaceEditView(PlaceFormMixin, UpdateView):
    def get_queryset(self):
        return Place.all_objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["heading"] = "Edit place"
        return ctx

    def form_valid(self, form):
        messages.success(self.request, "Saved.")
        return super().form_valid(form)


class PlaceProfileView(LegacyContextMixin, DetailView):
    model = Place
    template_name = "legacy/place_detail.html"
    context_object_name = "place"
    nav_active = "places"

    def get_queryset(self):
        return Place.all_objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        place = self.object
        memories = place.memories.all().select_related("primary_media").order_by("-created_at")
        ctx["memories"] = memories
        ctx["media"] = Media.objects.filter(memories__in=memories).distinct()[:12]
        ctx["people"] = Person.objects.filter(memories__in=memories).distinct()
        ctx["dated_memories"] = memories.exclude(occurred_on__isnull=True).order_by("occurred_on")
        return ctx


class PlaceArchiveView(LegacyContextMixin, View):
    def post(self, request, pk, *args, **kwargs):
        p = get_object_or_404(Place.all_objects, pk=pk, user=request.user)
        p.archive()
        messages.success(request, "Place set aside.")
        return redirect("legacy:places")


class PlaceRestoreView(LegacyContextMixin, View):
    def post(self, request, pk, *args, **kwargs):
        p = get_object_or_404(Place.all_objects, pk=pk, user=request.user)
        p.restore()
        messages.success(request, "Place restored.")
        return redirect("legacy:place_detail", pk=p.pk)


# ── Media ──────────────────────────────────────────────────────────────────
MEDIA_TYPE_CHOICES = [("all", "All")] + list(Media.MediaType.choices)


class MediaLibraryView(LegacyContextMixin, TemplateView):
    template_name = "legacy/media.html"
    nav_active = "media"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        req = self.request.GET
        q = (req.get("q") or "").strip()
        mtype = req.get("type", "all")
        if mtype not in dict(MEDIA_TYPE_CHOICES):
            mtype = "all"
        media = Media.objects.filter(user=self.request.user)
        if mtype != "all":
            media = media.filter(media_type=mtype)
        if q:
            media = media.filter(Q(caption__icontains=q) | Q(original_filename__icontains=q))
        ctx["media"] = media.order_by("-created_at")
        ctx["q"] = q
        ctx["mtype"] = mtype
        ctx["type_choices"] = MEDIA_TYPE_CHOICES
        ctx["total_count"] = media.count()
        return ctx


class MediaUploadView(LegacyContextMixin, View):
    def post(self, request, *args, **kwargs):
        files = request.FILES.getlist("file")
        count = 0
        for f in files:
            Media.objects.create(
                user=request.user,
                media_type=guess_media_type(f.name),
                file=f,
                original_filename=f.name[:255],
                created_via=Media.CREATED_VIA_MANUAL,
            )
            count += 1
        if count:
            messages.success(request, f"Added {count} item{'s' if count != 1 else ''}.")
        return redirect("legacy:media")


class MediaDetailView(LegacyContextMixin, DetailView):
    model = Media
    template_name = "legacy/media_detail.html"
    context_object_name = "item"
    nav_active = "media"

    def get_queryset(self):
        return Media.all_objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["memories"] = self.object.memories.all()
        return ctx


# ── Timeframe helper (shared) ────────────────────────────────────────────────
def filter_timeframe(qs, tf, start_str, end_str, field="created_at"):
    now = timezone.now()
    start = None
    if tf == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif tf == "week":
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    elif tf == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif tf == "year":
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    if start is not None:
        qs = qs.filter(**{f"{field}__gte": start})
    if tf == "custom":
        cs, ce = _parse_date(start_str), _parse_date(end_str)
        if cs:
            qs = qs.filter(**{f"{field}__date__gte": cs})
        if ce:
            qs = qs.filter(**{f"{field}__date__lte": ce})
    return qs


# ── Dashboard (overview) ─────────────────────────────────────────────────────
class StudioView(LegacyContextMixin, TemplateView):
    """Operational overview — counts, filters, recent activity, pending review, quick actions."""

    template_name = "legacy/dashboard.html"
    nav_active = "dashboard"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        req = self.request.GET
        tf = req.get("tf", "all")
        if tf not in dict(TIMEFRAME_CHOICES):
            tf = "all"
        status = req.get("status", "all")
        if status not in dict(STATUS_CHOICES):
            status = "all"

        active_mem = Memory.objects.filter(user=user)
        archived_mem = Memory.all_objects.filter(user=user, status="archived")

        ctx["counts"] = {
            "memories": active_mem.count(),
            "drafts": active_mem.filter(entry_state=Memory.EntryState.DRAFT).count(),
            "legacy": active_mem.filter(entry_state__in=[Memory.EntryState.LEGACY, Memory.EntryState.SHARED]).count(),
            "archived": archived_mem.count(),
            "people": Person.objects.filter(user=user).count(),
            "places": Place.objects.filter(user=user).count(),
            "media": Media.objects.filter(user=user).count(),
            "contributors": Contributor.objects.filter(user=user).count(),
            "outputs": Output.objects.filter(user=user).count(),
        }

        # Recent activity — memories in the selected time frame / status.
        recent = active_mem if status != "archived" else archived_mem
        if status == "draft":
            recent = recent.filter(entry_state=Memory.EntryState.DRAFT)
        elif status == "legacy":
            recent = recent.filter(entry_state__in=[Memory.EntryState.LEGACY, Memory.EntryState.SHARED])
        recent = filter_timeframe(recent, tf, req.get("start"), req.get("end"))
        ctx["recent"] = recent.order_by("-updated_at")[:8]

        # Pending review counts (drives the Studio review queue).
        ctx["review"] = {
            "drafts": active_mem.filter(entry_state=Memory.EntryState.DRAFT).count(),
            "submissions": active_mem.filter(source_kind=Memory.SourceKind.CONTRIBUTOR).count(),
            "media_no_context": Media.objects.filter(user=user, memories__isnull=True).distinct().count(),
            "unlinked": active_mem.filter(people__isnull=True, places__isnull=True).distinct().count(),
        }

        ctx.update({
            "tf": tf, "status": status,
            "start": req.get("start", ""), "end": req.get("end", ""),
            "timeframe_choices": TIMEFRAME_CHOICES, "status_choices": STATUS_CHOICES,
        })
        return ctx


# ── Studio / Review Queue ────────────────────────────────────────────────────
class ReviewView(LegacyContextMixin, TemplateView):
    """The workshop: one warm place to tend drafts, submissions, and gaps."""

    template_name = "legacy/review.html"
    nav_active = "studio"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        active = Memory.objects.filter(user=user)
        ctx["drafts"] = active.filter(entry_state=Memory.EntryState.DRAFT).order_by("-updated_at")
        ctx["submissions"] = (
            active.filter(source_kind=Memory.SourceKind.CONTRIBUTOR)
            .select_related("contributor").order_by("-created_at")
        )
        ctx["media_no_context"] = Media.objects.filter(user=user, memories__isnull=True).distinct()
        ctx["unlinked"] = active.filter(people__isnull=True, places__isnull=True).distinct().order_by("-created_at")
        return ctx


# ── Contributors / Family ────────────────────────────────────────────────────
class ContributorsView(LegacyContextMixin, TemplateView):
    template_name = "legacy/contributors.html"
    nav_active = "contributors"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["contributors"] = Contributor.objects.filter(user=self.request.user)
        return ctx


class ContributorFormMixin(LegacyContextMixin):
    model = Contributor
    form_class = ContributorForm
    template_name = "legacy/contributor_form.html"
    nav_active = "contributors"

    def get_success_url(self):
        return reverse("legacy:contributor_detail", args=[self.object.pk])


class ContributorCreateView(ContributorFormMixin, CreateView):
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["heading"] = "Add a contributor"
        return ctx

    def form_valid(self, form):
        import uuid
        form.instance.user = self.request.user
        form.instance.created_via = Contributor.CREATED_VIA_MANUAL
        form.instance.invite_token = uuid.uuid4().hex
        form.instance.invite_status = Contributor.InviteStatus.INVITED
        messages.success(self.request, "Contributor added.")
        return super().form_valid(form)


class ContributorEditView(ContributorFormMixin, UpdateView):
    def get_queryset(self):
        return Contributor.all_objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["heading"] = "Edit contributor"
        return ctx

    def form_valid(self, form):
        messages.success(self.request, "Saved.")
        return super().form_valid(form)


class ContributorDetailView(LegacyContextMixin, DetailView):
    model = Contributor
    template_name = "legacy/contributor_detail.html"
    context_object_name = "contributor"
    nav_active = "contributors"

    def get_queryset(self):
        return Contributor.all_objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        memories = self.object.memories.all().order_by("-created_at")
        ctx["memories"] = memories
        ctx["media"] = Media.objects.filter(memories__in=memories).distinct()[:12]
        return ctx


class ContributorArchiveView(LegacyContextMixin, View):
    def post(self, request, pk, *args, **kwargs):
        c = get_object_or_404(Contributor.all_objects, pk=pk, user=request.user)
        c.archive()
        messages.success(request, "Contributor set aside.")
        return redirect("legacy:contributors")


# ── Output Generator / Create ────────────────────────────────────────────────
class OutputsView(LegacyContextMixin, TemplateView):
    template_name = "legacy/outputs.html"
    nav_active = "outputs"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["outputs"] = Output.objects.filter(user=self.request.user).order_by("-created_at")
        return ctx


class OutputCreateView(LegacyContextMixin, CreateView):
    model = Output
    form_class = OutputForm
    template_name = "legacy/output_form.html"
    nav_active = "outputs"

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["user"] = self.request.user
        return kw

    def get_success_url(self):
        return reverse("legacy:output_detail", args=[self.object.pk])

    def form_valid(self, form):
        form.instance.user = self.request.user
        form.instance.created_via = Output.CREATED_VIA_MANUAL
        form.instance.generation_status = Output.GenerationStatus.DRAFT
        messages.success(self.request, "Output created (placeholder — generation comes later).")
        return super().form_valid(form)


class OutputDetailView(LegacyContextMixin, DetailView):
    model = Output
    template_name = "legacy/output_detail.html"
    context_object_name = "output"
    nav_active = "outputs"

    def get_queryset(self):
        return Output.all_objects.filter(user=self.request.user)


class OutputArchiveView(LegacyContextMixin, View):
    def post(self, request, pk, *args, **kwargs):
        o = get_object_or_404(Output.all_objects, pk=pk, user=request.user)
        o.archive()
        messages.success(request, "Output set aside.")
        return redirect("legacy:outputs")
