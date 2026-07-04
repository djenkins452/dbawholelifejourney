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
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, TemplateView, UpdateView

from django.template.loader import render_to_string

from apps.legacy.forms import ContributorForm, ImportForm, OutputForm, PersonForm, PlaceForm
from apps.legacy.models import (
    Contributor, ImportBatch, ImportChunk, LifeMilestone, Media, Memory, MemoryDiscovery,
    MemoryRevision, Output, Person, Place, Relationship,
)
from apps.legacy.services import discovery as discovery_svc
from apps.legacy.services import family_tree
from apps.legacy.services import import_engine
from apps.legacy.services.home import build_home_context
from apps.legacy.services.media_utils import (
    guess_media_type, is_narrative_text, is_visual_media,
)


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


def build_story_connections(memory):
    """The PERSISTENT connections for a memory (what is now attached), for the
    Connections panel after Discovery is applied. Reads the memory's real
    relations (people/places/milestones/media) plus accepted enriched
    discoveries (themes/quotes/time/…) as read-only chips. Empty sections are
    omitted — an empty 'Relationships' must never look broken."""
    if memory is None or not memory.pk:
        return []

    people = list(memory.people.all())
    places = list(memory.places.all())
    milestones = list(memory.milestones.all())
    media = list(memory.media.all())

    # Relationships that involve people in this story (a mention is NOT a
    # relationship — only real Relationship rows count).
    rels = []
    if people:
        pids = [p.pk for p in people]
        rels = list(Relationship.objects.filter(user=memory.user).filter(
            Q(from_person_id__in=pids) | Q(to_person_id__in=pids)
        ).select_related("from_person", "to_person"))

    # Accepted enriched discoveries → read-only chips.
    chips = {}
    for d in MemoryDiscovery.objects.filter(
            memory=memory, status=MemoryDiscovery.Status.ACCEPTED):
        chips.setdefault(d.kind, []).append(d.label)

    sections = []
    if people:
        sections.append({"key": "people", "label": "People", "kind": "people",
            "count": len(people), "open": True, "items": [{
                "name": p.display_name, "sub": p.relationship_label,
                "letter": (p.display_name or "?")[:1].upper(),
                "url": reverse("legacy:person_detail", args=[p.pk])} for p in people]})
    if places:
        sections.append({"key": "places", "label": "Places", "kind": "places",
            "count": len(places), "open": True, "items": [{
                "name": p.name, "sub": p.location_text,
                "url": reverse("legacy:place_detail", args=[p.pk])} for p in places]})
    if rels:
        sections.append({"key": "relationships", "label": "Relationships",
            "kind": "relationships", "count": len(rels), "open": True, "items": [{
                "name": "%s & %s" % (r.from_person.display_name, r.to_person.display_name),
                "sub": r.relationship_type,
                "url": reverse("legacy:person_detail", args=[r.from_person.pk])} for r in rels]})
    if milestones:
        sections.append({"key": "milestones", "label": "Life Milestones",
            "kind": "milestones", "count": len(milestones), "open": True, "items": [{
                "name": m.title,
                "sub": m.get_kind_display() + ((" · %s" % m.year) if m.year else ""),
                "url": reverse("legacy:milestone_detail", args=[m.pk])} for m in milestones]})
    if media:
        sections.append({"key": "media", "label": "Media", "kind": "media",
            "count": len(media), "open": True, "items": [{
                "is_photo": m.media_type == Media.MediaType.PHOTO,
                "thumb": m.file.url if (m.media_type == Media.MediaType.PHOTO and m.file) else "",
                "kind_display": m.get_media_type_display(), "type": m.media_type,
                "url": reverse("legacy:media_detail", args=[m.pk])} for m in media]})

    def chip_section(key, label, kinds):
        labels = []
        for k in kinds:
            labels += chips.get(k, [])
        if labels:
            sections.append({"key": key, "label": label, "kind": "chips",
                             "count": len(labels), "open": False, "chips": labels})

    chip_section("time", "Time", ["human_time", "calendar_time", "relative_time", "life_stage"])
    chip_section("events", "Events", ["event"])
    chip_section("quotes", "Quotes", ["quote"])
    chip_section("themes", "Themes", ["theme"])
    chip_section("values", "Values", ["value"])
    chip_section("traditions", "Traditions", ["tradition"])
    chip_section("emotions", "Emotions", ["emotion"])
    chip_section("artifacts", "Artifacts", ["artifact"])
    return sections


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
        # Persistent Story Connections — what is now attached to this memory.
        ctx["connections"] = build_story_connections(memory)
        # If discovery already ran (e.g. an imported story), show the existing
        # proposals on load — review & apply without re-running (or re-charging).
        if memory and MemoryDiscovery.objects.filter(
                memory=memory, status=MemoryDiscovery.Status.PROPOSED).exists():
            groups = discovery_svc.grouped_proposals(memory)
            ctx["discovery_groups"] = groups
            ctx["discovery_summary"] = discovery_svc.summary_text(groups)
            ctx["discovery_prompts"] = memory.discovery_prompts
            # Surface the cleanup undo if the story was tidied and not yet reverted.
            if memory.cleanup_original_body and memory.cleanup_original_body != memory.body:
                ctx["discovery_cleanup"] = {"changed": True, "changes": [],
                                            "original": memory.cleanup_original_body}
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
        title_was_empty = not title
        memory.title = title
        memory.body = body
        if memory.pk:
            memory.updated_by = user
        memory.save()

        # Phase 1 — Cleanup: gently copy-edit the writing before Discovery runs.
        # Never changes voice/meaning; always safe; the original is preserved.
        from apps.legacy.services import cleanup as cleanup_svc
        cleanup = cleanup_svc.run_cleanup(body)
        if cleanup["changed"]:
            memory.cleanup_original_body = cleanup["original"]
            memory.body = cleanup["cleaned"]
            memory.save(update_fields=["cleanup_original_body", "body", "updated_at"])

        # Phase 2 & 3 — Discovery runs on the cleaned text; place verification is
        # folded into the place discoveries.
        status, _ = discovery_svc.run_discovery(memory)
        groups = discovery_svc.grouped_proposals(memory)
        html = render_to_string("legacy/_discovery_review.html", {
            "memory": memory,
            "groups": groups,
            "status": status,
            "summary": discovery_svc.summary_text(groups),
            "prompts": memory.discovery_prompts,
            "cleanup": cleanup,
        }, request=request)
        # Auto-title: only offered when the author left the title blank.
        suggested_title = memory.title if (title_was_empty and (memory.title or "").strip()) else None
        return JsonResponse({
            "ok": True, "pk": memory.pk, "status": status, "html": html,
            "cleaned_body": memory.body if cleanup["changed"] else None,
            "suggested_title": suggested_title,
        })


class DiscoveryConfirmView(LegacyContextMixin, View):
    """Promotion gate — accept selected (or all) discoveries, reject the rest."""

    def post(self, request, pk, *args, **kwargs):
        memory = get_object_or_404(Memory.all_objects, pk=pk, user=request.user)
        accept_all = request.POST.get("accept_all") == "1"
        accepted_ids = request.POST.getlist("accept")
        resolutions = {k[len("resolve_"):]: v for k, v in request.POST.items()
                       if k.startswith("resolve_")}
        edits = {}
        for k, v in request.POST.items():
            for prefix, field in (("edit_label_", "label"), ("edit_rel_", "relationship"),
                                  ("edit_loc_", "location"), ("edit_notes_", "notes"),
                                  ("edit_year_", "year")):
                if k.startswith(prefix):
                    edits.setdefault(k[len(prefix):], {})[field] = v
        n = discovery_svc.confirm_discoveries(
            memory, accepted_ids, accept_all=accept_all,
            resolutions=resolutions, edits=edits)
        if n:
            messages.success(request, f"Added {n} connection{'s' if n != 1 else ''} to this memory.")
        else:
            messages.success(request, "Nothing added.")
        return redirect("legacy:editor", pk=memory.pk)


class MemoryCleanupUndoView(LegacyContextMixin, View):
    """Undo the gentle copy-edit and restore the user's original wording."""

    def post(self, request, pk, *args, **kwargs):
        memory = get_object_or_404(Memory.all_objects, pk=pk, user=request.user)
        if memory.cleanup_original_body:
            memory.body = memory.cleanup_original_body
            memory.cleanup_original_body = ""
            memory.updated_by = request.user
            memory.save(update_fields=["body", "cleanup_original_body", "updated_at"])
        if _is_ajax(request):
            return JsonResponse({"ok": True, "body": memory.body})
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


class MemoryDeleteForeverView(LegacyContextMixin, View):
    """Two-stage delete: only a memory ALREADY set aside (archived) can be
    permanently removed. Outside the archive, 'delete' means Set aside."""

    def post(self, request, pk, *args, **kwargs):
        memory = get_object_or_404(Memory.all_objects, pk=pk, user=request.user)
        if memory.status != "archived":
            messages.error(request, "Set the memory aside first — only set-aside memories can be permanently deleted.")
            return redirect("legacy:editor", pk=memory.pk)
        memory.delete()  # hard delete — gone for good
        messages.success(request, "Memory permanently deleted.")
        return redirect("%s?status=archived" % reverse("legacy:library"))


def _is_ajax(request):
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


class MediaAddView(LegacyContextMixin, View):
    """Attach one or more media files to a memory (drag-drop / multi-upload aware)."""

    def post(self, request, pk, *args, **kwargs):
        memory = get_object_or_404(Memory.all_objects, pk=pk, user=request.user)
        files = request.FILES.getlist("file")
        items, skipped = [], None
        for f in files:
            # Written life belongs in Import — guide, never 500.
            if is_narrative_text(f.name):
                skipped = ("That looks like written text — bring memoirs, journals, "
                           "and exports in through Import your life.")
                continue
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
            is_photo = media.media_type == Media.MediaType.PHOTO
            items.append({
                "id": media.pk,
                "type": media.media_type,
                "kind_display": media.get_media_type_display(),
                "is_photo": is_photo,
                "thumb_url": media.file.url if (is_photo and media.file) else "",
                "name": media.original_filename,
            })
        if _is_ajax(request):
            return JsonResponse({"ok": True, "items": items, "skipped": skipped})
        if items:
            messages.success(request, "Added to this memory.")
        if skipped:
            messages.info(request, skipped)
        return redirect("legacy:editor", pk=memory.pk)


class MemoryMediaRemoveView(LegacyContextMixin, View):
    """Detach media from a memory before saving. Media is shared, so we only
    unlink it here — the file stays in the library and with any other stories."""

    def post(self, request, pk, media_pk, *args, **kwargs):
        memory = get_object_or_404(Memory.all_objects, pk=pk, user=request.user)
        media = get_object_or_404(Media.all_objects, pk=media_pk, user=request.user)
        memory.media.remove(media)
        # If the cover was removed, promote the next attached photo so the story
        # tile keeps a consistent thumbnail instead of falling back to a placeholder.
        if memory.primary_media_id == media.pk:
            memory.primary_media = memory.media.filter(
                media_type=Media.MediaType.PHOTO).exclude(pk=media.pk).order_by("pk").first()
            memory.save(update_fields=["primary_media", "updated_at"])
        if _is_ajax(request):
            return JsonResponse({"ok": True})
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
        # Aliases the keeper has taught Legacy for this person ("Dad" → Marvin).
        ctx["aliases"] = list(person.aliases.all())
        # Life milestones this person is part of (through their stories).
        ctx["milestones"] = LifeMilestone.objects.filter(memories__in=memories).distinct()
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
        # A Google Maps link (new tab) when we have coordinates or an address.
        from urllib.parse import quote
        if place.latitude is not None and place.longitude is not None:
            ctx["map_url"] = "https://www.google.com/maps?q=%s,%s" % (place.latitude, place.longitude)
        elif place.location_text:
            q = quote("%s %s" % (place.name, place.location_text))
            ctx["map_url"] = "https://www.google.com/maps/search/?api=1&query=%s" % q
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
        status = "archived" if req.get("status") == "archived" else "active"
        if status == "archived":
            media = Media.all_objects.filter(user=self.request.user, status="archived")
        else:
            media = Media.objects.filter(user=self.request.user)
        if mtype != "all":
            media = media.filter(media_type=mtype)
        if q:
            media = media.filter(Q(caption__icontains=q) | Q(original_filename__icontains=q))
        ctx["media"] = media.order_by("-created_at")
        ctx["q"] = q
        ctx["mtype"] = mtype
        ctx["status"] = status
        ctx["archived_count"] = Media.all_objects.filter(user=self.request.user, status="archived").count()
        ctx["type_choices"] = MEDIA_TYPE_CHOICES
        ctx["total_count"] = media.count()
        return ctx


class MediaUploadView(LegacyContextMixin, View):
    def post(self, request, *args, **kwargs):
        files = request.FILES.getlist("file")
        count, skipped = 0, 0
        for f in files:
            # Written life belongs in Import — don't quietly file it as a document.
            if is_narrative_text(f.name):
                skipped += 1
                continue
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
        if skipped:
            messages.info(request, "Some written-text files were skipped — bring "
                                   "memoirs and journals in through Import your life.")
        return redirect("legacy:media")


def suggest_stories_for_media(media, limit=6):
    """Stories worth linking this media to — those that share a person, place, or
    life milestone with the stories it's already on. Helpful, not exhaustive."""
    attached = list(media.memories.all())
    if not attached:
        return []
    attached_ids = [m.pk for m in attached]
    person_ids = set(Person.objects.filter(memories__in=attached).values_list("pk", flat=True))
    place_ids = set(Place.objects.filter(memories__in=attached).values_list("pk", flat=True))
    ms_ids = set(LifeMilestone.objects.filter(memories__in=attached).values_list("pk", flat=True))
    q = Q()
    if person_ids:
        q |= Q(people__in=person_ids)
    if place_ids:
        q |= Q(places__in=place_ids)
    if ms_ids:
        q |= Q(milestones__in=ms_ids)
    if not q:
        return []
    return list(Memory.objects.filter(user=media.user).filter(q)
                .exclude(pk__in=attached_ids).distinct().order_by("-updated_at")[:limit])


class MediaDetailView(LegacyContextMixin, DetailView):
    model = Media
    template_name = "legacy/media_detail.html"
    context_object_name = "item"
    nav_active = "media"

    def get_queryset(self):
        return Media.all_objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        media = self.object
        attached = list(media.memories.all())
        ctx["memories"] = attached           # backwards-compatible key
        ctx["attached_stories"] = attached
        # People / places / milestones reached THROUGH the attached stories.
        ctx["rel_people"] = Person.objects.filter(memories__in=attached).distinct()
        ctx["rel_places"] = Place.objects.filter(memories__in=attached).distinct()
        ctx["rel_milestones"] = LifeMilestone.objects.filter(memories__in=attached).distinct()
        # Associate-more picker: suggestions first, then the rest to search through.
        attached_ids = {m.pk for m in attached}
        suggested = suggest_stories_for_media(media)
        suggested_ids = {m.pk for m in suggested}
        ctx["suggested_stories"] = suggested
        ctx["other_stories"] = list(Memory.objects.filter(user=self.request.user)
                                    .exclude(pk__in=attached_ids | suggested_ids)
                                    .order_by("-updated_at")[:60])
        return ctx


class MediaAssociateView(LegacyContextMixin, View):
    """Link one media item to one or more stories — additive, never duplicates
    the file, one photo can belong to many stories."""

    def post(self, request, pk, *args, **kwargs):
        media = get_object_or_404(Media.all_objects, pk=pk, user=request.user)
        ids = request.POST.getlist("story")
        added = 0
        for story in Memory.all_objects.filter(user=request.user, pk__in=ids):
            if story.media.filter(pk=media.pk).exists():
                continue
            story.media.add(media)
            if media.media_type == Media.MediaType.PHOTO and not story.primary_media_id:
                story.primary_media = media
                story.save(update_fields=["primary_media", "updated_at"])
            added += 1
        if added:
            messages.success(request, "Linked to %d %s." % (added, "story" if added == 1 else "stories"))
        else:
            messages.info(request, "No new stories linked.")
        return redirect("legacy:media_detail", pk=media.pk)


class MediaStoryDetachView(LegacyContextMixin, View):
    """Remove the link between a media item and ONE story. The file stays in the
    library and on any other stories — only the relationship is removed."""

    def post(self, request, pk, story_pk, *args, **kwargs):
        media = get_object_or_404(Media.all_objects, pk=pk, user=request.user)
        story = get_object_or_404(Memory.all_objects, pk=story_pk, user=request.user)
        story.media.remove(media)
        if story.primary_media_id == media.pk:
            story.primary_media = story.media.filter(
                media_type=Media.MediaType.PHOTO).exclude(pk=media.pk).order_by("pk").first()
            story.save(update_fields=["primary_media", "updated_at"])
        messages.success(request, "Removed from that story — the photo stays in your library.")
        return redirect("legacy:media_detail", pk=media.pk)


class MediaArchiveView(LegacyContextMixin, View):
    def post(self, request, pk, *args, **kwargs):
        media = get_object_or_404(Media.all_objects, pk=pk, user=request.user)
        media.archive()
        messages.success(request, "Set aside.")
        return redirect("legacy:media_detail", pk=media.pk)


class MediaRestoreView(LegacyContextMixin, View):
    def post(self, request, pk, *args, **kwargs):
        media = get_object_or_404(Media.all_objects, pk=pk, user=request.user)
        media.restore()
        messages.success(request, "Restored.")
        return redirect("legacy:media_detail", pk=media.pk)


class MediaDeleteForeverView(LegacyContextMixin, View):
    """Two-stage delete for media — only a set-aside item can be removed for good.
    The file leaves the library and every story it was attached to."""

    def post(self, request, pk, *args, **kwargs):
        media = get_object_or_404(Media.all_objects, pk=pk, user=request.user)
        if media.status != "archived":
            messages.error(request, "Set it aside first — only set-aside media can be permanently deleted.")
            return redirect("legacy:media_detail", pk=media.pk)
        media.delete()  # hard delete — gone for good
        messages.success(request, "Permanently deleted.")
        return redirect("%s?status=archived" % reverse("legacy:media"))


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
            "relationships": Relationship.objects.filter(user=user).count(),
            "media": Media.objects.filter(user=user).count(),
            "contributors": Contributor.objects.filter(user=user).count(),
            "outputs": Output.objects.filter(user=user).count(),
            "imports": ImportBatch.objects.filter(user=user).count(),
            "imported_stories": active_mem.filter(import_batch__isnull=False).count(),
            "waiting_review": active_mem.filter(
                import_batch__isnull=False, entry_state=Memory.EntryState.DRAFT).count(),
            "suggestions": MemoryDiscovery.objects.filter(
                memory__user=user, status=MemoryDiscovery.Status.PROPOSED).count(),
            "milestones": LifeMilestone.objects.filter(user=user).count(),
        }
        top = list(LifeMilestone.objects.filter(user=user)
                   .annotate(n=Count("memories", distinct=True)).order_by("-n", "-year")[:5])
        ctx["top_milestones"] = top
        ctx["most_connected"] = top[0] if top else None
        ctx["recently_imported"] = (
            active_mem.filter(import_batch__isnull=False)
            .select_related("import_batch").order_by("-created_at")[:5])

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


# ── Import Engine ────────────────────────────────────────────────────────────
class ImportsView(LegacyContextMixin, TemplateView):
    template_name = "legacy/imports.html"
    nav_active = "studio"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["batches"] = ImportBatch.objects.filter(user=self.request.user)
        return ctx


class ImportCreateView(LegacyContextMixin, View):
    template_name = "legacy/import_new.html"
    nav_active = "studio"

    def get(self, request, *args, **kwargs):
        from django.shortcuts import render
        return render(request, self.template_name, {"form": ImportForm(), "nav_active": "studio"})

    def post(self, request, *args, **kwargs):
        from django.shortcuts import render
        form = ImportForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form, "nav_active": "studio"})

        f = form.cleaned_data.get("file")
        if f and is_visual_media(f.name):
            messages.error(request, "That looks like a photo, video, or audio clip — "
                                    "add it under Add Photos & Media. Import is for "
                                    "written stories like memoirs, journals, and exports.")
            return render(request, self.template_name, {"form": form, "nav_active": "studio"})
        if f:
            try:
                raw = f.read().decode("utf-8", errors="replace")
            except Exception:
                messages.error(request, "Couldn't read that file as text.")
                return render(request, self.template_name, {"form": form, "nav_active": "studio"})
            name = form.cleaned_data["source_name"] or f.name
        else:
            raw = form.cleaned_data["paste"]
            name = form.cleaned_data["source_name"]

        from apps.legacy.services.import_adapters import ImportNotAvailable
        try:
            batch = import_engine.create_batch(
                request.user, name, form.cleaned_data["source_type"], raw)
        except ImportNotAvailable as e:
            messages.error(request, str(e))
            return render(request, self.template_name, {"form": form, "nav_active": "studio"})

        messages.success(
            request,
            f"Legacy read this and understood {batch.total_chunks} "
            f"{'piece' if batch.total_chunks == 1 else 'pieces'} of information. "
            "They're sorted into review queues below — nothing enters your Legacy until you review it.")
        return redirect("legacy:import_detail", pk=batch.pk)


class ImportDetailView(LegacyContextMixin, DetailView):
    model = ImportBatch
    template_name = "legacy/import_detail.html"
    context_object_name = "batch"
    nav_active = "studio"

    def get_queryset(self):
        return ImportBatch.all_objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["chunks"] = self.object.chunks.select_related("memory").all()
        ctx["pending"] = self.object.chunks.filter(status=ImportChunk.Status.PENDING).count()
        # Classification → review queues grouped by what each unit was understood to be.
        ctx["queues"] = import_engine.review_queues(self.object)
        ctx["narrative_pending"] = import_engine.narrative_pending(self.object)
        ctx["genealogy_pending"] = self.object.chunks.filter(
            chunk_kind__in=["gedcom_person", "gedcom_family"],
            status=ImportChunk.Status.PENDING).count()
        ctx["stats"] = import_engine.batch_stats(self.object)
        ctx["next_review"] = (
            self.object.memories.filter(entry_state=Memory.EntryState.DRAFT)
            .order_by("import_chunk").first())
        return ctx


class ImportRunView(LegacyContextMixin, View):
    """Import a chosen set of chunks — never everything implicitly."""

    def post(self, request, pk, *args, **kwargs):
        batch = get_object_or_404(ImportBatch.all_objects, pk=pk, user=request.user)
        indices = request.POST.getlist("index")
        limit = None
        if request.POST.get("mode") == "next":
            limit = int(request.POST.get("count") or 2)
            indices = None
        elif request.POST.get("mode") == "all":
            indices = None  # all pending
        memories = import_engine.import_chunks(batch, indices=indices, limit=limit)
        messages.success(
            request,
            f"Imported {len(memories)} {'story' if len(memories) == 1 else 'stories'} as drafts. "
            "Review each, run its discoveries, then add it to your Legacy.")
        return redirect("legacy:import_detail", pk=batch.pk)


class GenealogyCommitView(LegacyContextMixin, View):
    """Commit a GEDCOM batch's genealogy queues into canonical People + Relationships."""

    def post(self, request, pk, *args, **kwargs):
        batch = get_object_or_404(ImportBatch.all_objects, pk=pk, user=request.user)
        people, links = import_engine.commit_genealogy(batch)
        if people or links:
            messages.success(
                request,
                f"Added {people} {'person' if people == 1 else 'people'} and "
                f"{links} family {'connection' if links == 1 else 'connections'} to your family.")
        else:
            messages.info(request, "Everyone from this file is already in your family.")
        return redirect("legacy:family")


# ── Family View (a window into Canonical Truth, not a genealogy database) ─────
class FamilyView(LegacyContextMixin, TemplateView):
    template_name = "legacy/family.html"
    nav_active = "family"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["graph"] = family_tree.build_family_view(
            self.request.user, self.request.GET.get("focus"))
        # Search spans the WHOLE family, not just the rendered neighborhood.
        ctx["search_index"] = family_tree.family_search_index(self.request.user)
        return ctx


class RelationshipsView(LegacyContextMixin, TemplateView):
    """Relationships explorer. Family lives in the Family view (no duplication);
    this is where the OTHER relationships in a life will grow — friends, coworkers,
    mentors, faith, neighbours, service. v1 points to Family + shows the roadmap
    and any non-family connections already captured."""

    template_name = "legacy/relationships.html"
    nav_active = "relationships"

    _FAMILY = (
        "parent", "father", "mother", "mom", "dad", "mum", "child", "son",
        "daughter", "married", "spouse", "husband", "wife", "wed", "partner",
        "brother", "sister", "sibling", "grand", "aunt", "uncle", "cousin",
        "niece", "nephew", "in-law", "step", "half",
    )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        fam = 0
        non_family = []
        for r in (Relationship.objects.filter(user=user)
                  .select_related("from_person", "to_person")):
            t = (r.relationship_type or "").lower()
            if any(k in t for k in self._FAMILY):
                fam += 1
            else:
                non_family.append(r)
        ctx["family_count"] = fam
        ctx["non_family"] = non_family
        ctx["people_count"] = Person.objects.filter(user=user).count()
        ctx["roadmap"] = [
            ("Friends", "The people you chose"),
            ("Coworkers & managers", "Who you worked alongside"),
            ("Mentors & teachers", "Who shaped you"),
            ("Faith", "Pastors, small groups, church family"),
            ("Neighbors", "The people next door"),
            ("Military & service", "Those you served with"),
        ]
        return ctx


class PersonSetSelfView(LegacyContextMixin, View):
    """Mark a person as the keeper (the 'me' / home node in the Family tree)."""

    def post(self, request, pk, *args, **kwargs):
        person = get_object_or_404(Person.all_objects, pk=pk, user=request.user)
        Person.objects.filter(user=request.user, is_self=True).exclude(pk=person.pk).update(is_self=False)
        if not person.is_self:
            person.is_self = True
            person.save(update_fields=["is_self", "updated_at"])
        messages.success(request, f"Got it — you're {person.display_name} in your family tree.")
        nxt = request.POST.get("next")
        return redirect(nxt) if nxt else redirect("legacy:person_detail", pk=person.pk)


# ── Timeline & Milestones (emergent chapters) ────────────────────────────────
class TimelineView(LegacyContextMixin, TemplateView):
    """A life timeline that emerges from Life Milestones — not manually maintained."""

    template_name = "legacy/timeline.html"
    nav_active = "timeline"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        milestones = LifeMilestone.objects.filter(user=user)

        rows = []
        for m in milestones:
            memories = m.memories.all()
            rows.append({
                "m": m,
                "stories": memories.count(),
                "photos": Media.objects.filter(
                    memories__in=memories, media_type=Media.MediaType.PHOTO).distinct().count(),
                "people": Person.objects.filter(memories__in=memories).distinct().count(),
            })

        # Group by year (most recent first); undated last.
        years, undated = {}, []
        for r in rows:
            y = r["m"].year
            (years.setdefault(y, []) if y else undated).append(r)
        ctx["year_groups"] = [
            {"year": y, "rows": years[y]}
            for y in sorted(years.keys(), reverse=True)
        ]
        ctx["undated"] = undated
        ctx["milestone_count"] = milestones.count()
        return ctx


class MilestoneDetailView(LegacyContextMixin, DetailView):
    """A chapter of a life — everything connected through this milestone."""

    model = LifeMilestone
    template_name = "legacy/milestone_detail.html"
    context_object_name = "milestone"
    nav_active = "timeline"

    def get_queryset(self):
        return LifeMilestone.all_objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        memories = self.object.memories.all().select_related("primary_media").order_by("-created_at")
        ctx["memories"] = memories
        ctx["people"] = Person.objects.filter(memories__in=memories).distinct()
        ctx["places"] = Place.objects.filter(memories__in=memories).distinct()
        ctx["media"] = Media.objects.filter(memories__in=memories).distinct()[:12]
        ctx["quotes"] = list(MemoryDiscovery.objects.filter(
            memory__in=memories, kind=MemoryDiscovery.Kind.QUOTE,
            status=MemoryDiscovery.Status.ACCEPTED).values_list("label", flat=True)[:8])
        return ctx
