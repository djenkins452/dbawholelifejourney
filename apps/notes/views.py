"""
Whole Life Journey - Notes Views

Project: Whole Life Journey
Path: apps/notes/views.py
Purpose: CRUD views for notes management
"""

import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.core.models import Tag
from apps.core.views import SaveAddAnotherMixin
from apps.help.mixins import HelpContextMixin

from .forms import NoteForm
from .models import Note, NoteImage

logger = logging.getLogger(__name__)


class NoteListView(HelpContextMixin, LoginRequiredMixin, ListView):
    """List all active notes for the current user."""

    model = Note
    template_name = "notes/note_list.html"
    context_object_name = "notes"
    paginate_by = 24
    help_context_id = "NOTES_LIST"

    def get_queryset(self):
        queryset = Note.objects.filter(user=self.request.user)

        tag_id = self.request.GET.get("tag")
        if tag_id:
            queryset = queryset.filter(tags__id=tag_id)

        color = self.request.GET.get("color")
        if color:
            queryset = queryset.filter(color=color)

        pinned = self.request.GET.get("pinned")
        if pinned == "1":
            queryset = queryset.filter(is_pinned=True)

        # Substring search — matches partial words (e.g. "thanks" finds "Thanksgiving")
        search = self.request.GET.get("q", "").strip()
        if not search:
            search = self.request.GET.get("search", "").strip()
        if search:
            # Each word must appear somewhere in title, body, tags, or attachments
            for word in search.split():
                queryset = queryset.filter(
                    Q(title__icontains=word)
                    | Q(body__icontains=word)
                    | Q(tags__name__icontains=word)
                    | Q(attachments_text__icontains=word)
                )
            queryset = queryset.order_by("-is_pinned", "-updated_at")

        return queryset.distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tags"] = Tag.objects.filter(user=self.request.user)
        context["color_choices"] = Note.COLOR_CHOICES
        search_q = self.request.GET.get("q", "")
        context["active_filters"] = {
            "tag": self.request.GET.get("tag", ""),
            "color": self.request.GET.get("color", ""),
            "pinned": self.request.GET.get("pinned", ""),
            "q": search_q,
            "search": self.request.GET.get("search", ""),
        }
        context["is_searching"] = bool(search_q)
        context["total_count"] = Note.objects.filter(user=self.request.user).count()
        return context


class NoteCreateView(
    HelpContextMixin, SaveAddAnotherMixin, LoginRequiredMixin, CreateView
):
    """Create a new note."""

    model = Note
    form_class = NoteForm
    template_name = "notes/note_form.html"
    help_context_id = "NOTES_CREATE"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        # Handle optional image upload
        image_file = form.cleaned_data.get("image")
        if image_file:
            NoteImage.objects.create(note=self.object, image=image_file)
        messages.success(self.request, "Note created.")
        return response


class NoteDetailView(HelpContextMixin, LoginRequiredMixin, DetailView):
    """View a single note with its attachments."""

    model = Note
    template_name = "notes/note_detail.html"
    context_object_name = "note"
    help_context_id = "NOTES_DETAIL"

    def get_queryset(self):
        return Note.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["attachments"] = (
            self.object.attachments.select_related("content_type").all()
        )
        context["note_images"] = self.object.images.all()
        # Load image analyses for this note's images
        from apps.scan.models import ImageAnalysis
        from django.contrib.contenttypes.models import ContentType
        note_image_ct = ContentType.objects.get_for_model(NoteImage)
        image_ids = list(self.object.images.values_list("id", flat=True))
        context["image_analyses"] = {
            a.object_id: a
            for a in ImageAnalysis.objects.filter(
                content_type=note_image_ct,
                object_id__in=image_ids,
                status="completed",
            )
        } if image_ids else {}
        return context


class NoteUpdateView(HelpContextMixin, LoginRequiredMixin, UpdateView):
    """Edit an existing note."""

    model = Note
    form_class = NoteForm
    template_name = "notes/note_form.html"
    help_context_id = "NOTES_EDIT"

    def get_queryset(self):
        return Note.objects.filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        image_file = form.cleaned_data.get("image")
        if image_file:
            NoteImage.objects.create(note=self.object, image=image_file)
        messages.success(self.request, "Note updated.")
        return response


class NoteDeleteView(LoginRequiredMixin, View):
    """Soft delete a note (POST only)."""

    def post(self, request, pk):
        note = get_object_or_404(
            Note.objects.filter(user=request.user),
            pk=pk,
        )
        note.soft_delete()
        messages.success(request, "Note deleted.")
        return redirect("notes:note_list")


class NoteTogglePinView(LoginRequiredMixin, View):
    """Toggle pinned status on a note (POST only)."""

    def post(self, request, pk):
        note = get_object_or_404(
            Note.objects.filter(user=request.user),
            pk=pk,
        )
        note.is_pinned = not note.is_pinned
        note.save(update_fields=["is_pinned", "updated_at"])
        action = "pinned" if note.is_pinned else "unpinned"
        messages.success(request, f"Note {action}.")
        next_url = request.POST.get("next", reverse("notes:note_list"))
        return redirect(next_url)
