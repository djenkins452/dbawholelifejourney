"""
Journal Views - CRUD operations and entry management.
"""

import random
from datetime import date

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
    View,
)

from apps.core.models import Category, Tag

from .forms import JournalEntryForm, TagForm
from .models import JournalEntry, JournalPrompt


class EntryListView(LoginRequiredMixin, ListView):
    """
    List all active journal entries for the current user.
    """

    model = JournalEntry
    template_name = "journal/entry_list.html"
    context_object_name = "entries"
    paginate_by = 20

    def get_queryset(self):
        queryset = JournalEntry.objects.filter(user=self.request.user)
        
        # Filter by category if specified
        category_slug = self.request.GET.get("category")
        if category_slug:
            queryset = queryset.filter(categories__slug=category_slug)
        
        # Filter by tag if specified
        tag_id = self.request.GET.get("tag")
        if tag_id:
            queryset = queryset.filter(tags__id=tag_id)
        
        # Filter by mood if specified
        mood = self.request.GET.get("mood")
        if mood:
            queryset = queryset.filter(mood=mood)
        
        # Search
        search = self.request.GET.get("search")
        if search:
            queryset = queryset.filter(
                models.Q(title__icontains=search) |
                models.Q(body__icontains=search)
            )
        
        return queryset.distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["categories"] = Category.objects.all()
        context["tags"] = Tag.objects.filter(user=self.request.user)
        context["mood_choices"] = JournalEntry.MOOD_CHOICES
        context["active_filters"] = {
            "category": self.request.GET.get("category"),
            "tag": self.request.GET.get("tag"),
            "mood": self.request.GET.get("mood"),
            "search": self.request.GET.get("search"),
        }
        context["total_count"] = JournalEntry.objects.filter(user=self.request.user).count()
        context["archived_count"] = JournalEntry.objects.archived_only().filter(user=self.request.user).count()
        return context


class ArchivedEntryListView(LoginRequiredMixin, ListView):
    """
    List archived journal entries.
    """

    model = JournalEntry
    template_name = "journal/archived_list.html"
    context_object_name = "entries"
    paginate_by = 20

    def get_queryset(self):
        return JournalEntry.objects.archived_only().filter(user=self.request.user)


class DeletedEntryListView(LoginRequiredMixin, ListView):
    """
    List deleted journal entries (within 30-day grace period).
    """

    model = JournalEntry
    template_name = "journal/deleted_list.html"
    context_object_name = "entries"
    paginate_by = 20

    def get_queryset(self):
        return JournalEntry.objects.deleted_only().filter(user=self.request.user)


class EntryDetailView(LoginRequiredMixin, DetailView):
    """
    View a single journal entry.
    """

    model = JournalEntry
    template_name = "journal/entry_detail.html"
    context_object_name = "entry"

    def get_queryset(self):
        # Allow viewing archived entries too
        return JournalEntry.objects.include_archived().filter(user=self.request.user)


class EntryCreateView(LoginRequiredMixin, CreateView):
    """
    Create a new journal entry.
    """

    model = JournalEntry
    form_class = JournalEntryForm
    template_name = "journal/entry_form.html"
    success_url = reverse_lazy("journal:entry_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        # Default title to current date
        initial["title"] = timezone.now().strftime("%A, %B %d, %Y")
        initial["entry_date"] = date.today()
        
        # If coming from a prompt, pre-fill it
        prompt_id = self.request.GET.get("prompt")
        if prompt_id:
            try:
                prompt = JournalPrompt.objects.get(pk=prompt_id)
                initial["prompt"] = prompt
            except JournalPrompt.DoesNotExist:
                pass
        
        return initial

    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, "Journal entry created.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_edit"] = False
        
        # Random prompt suggestion
        prompts = JournalPrompt.objects.filter(is_active=True)
        if not self.request.user.preferences.faith_enabled:
            prompts = prompts.filter(is_faith_specific=False)
        if prompts.exists():
            context["suggested_prompt"] = random.choice(list(prompts))
        
        return context


class EntryUpdateView(LoginRequiredMixin, UpdateView):
    """
    Edit an existing journal entry.
    """

    model = JournalEntry
    form_class = JournalEntryForm
    template_name = "journal/entry_form.html"

    def get_queryset(self):
        return JournalEntry.objects.include_archived().filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Journal entry updated.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_edit"] = True
        return context

    def get_success_url(self):
        return reverse_lazy("journal:entry_detail", kwargs={"pk": self.object.pk})


class ArchiveEntryView(LoginRequiredMixin, View):
    """
    Archive a journal entry.
    """

    def post(self, request, pk):
        entry = get_object_or_404(
            JournalEntry.objects.filter(user=request.user),
            pk=pk
        )
        entry.archive()
        messages.success(request, "Entry archived. You can restore it from the Archives.")
        return redirect("journal:entry_list")


class RestoreEntryView(LoginRequiredMixin, View):
    """
    Restore an archived or deleted entry.
    """

    def post(self, request, pk):
        entry = get_object_or_404(
            JournalEntry.all_objects.filter(user=request.user),
            pk=pk
        )
        entry.restore()
        messages.success(request, "Entry restored.")
        return redirect("journal:entry_detail", pk=pk)


class DeleteEntryView(LoginRequiredMixin, View):
    """
    Soft delete a journal entry.
    
    Entry will be permanently deleted after 30 days.
    """

    def post(self, request, pk):
        entry = get_object_or_404(
            JournalEntry.objects.include_archived().filter(user=request.user),
            pk=pk
        )
        entry.soft_delete()
        messages.success(
            request, 
            "Entry deleted. You have 30 days to restore it from Recently Deleted."
        )
        return redirect("journal:entry_list")


class PermanentDeleteEntryView(LoginRequiredMixin, View):
    """
    Permanently delete a journal entry.
    
    This cannot be undone.
    """

    def post(self, request, pk):
        entry = get_object_or_404(
            JournalEntry.all_objects.filter(user=request.user),
            pk=pk
        )
        entry.delete()  # Hard delete
        messages.success(request, "Entry permanently deleted.")
        return redirect("journal:entry_list")


class PromptListView(LoginRequiredMixin, ListView):
    """
    List available journal prompts.
    """

    model = JournalPrompt
    template_name = "journal/prompt_list.html"
    context_object_name = "prompts"

    def get_queryset(self):
        queryset = JournalPrompt.objects.filter(is_active=True)
        if not self.request.user.preferences.faith_enabled:
            queryset = queryset.filter(is_faith_specific=False)
        return queryset


class RandomPromptView(LoginRequiredMixin, View):
    """
    Get a random prompt (HTMX endpoint).
    """

    def get(self, request):
        queryset = JournalPrompt.objects.filter(is_active=True)
        if not request.user.preferences.faith_enabled:
            queryset = queryset.filter(is_faith_specific=False)
        
        if queryset.exists():
            prompt = random.choice(list(queryset))
            return HttpResponse(f"""
                <div class="prompt-card" id="random-prompt">
                    <p class="prompt-text">{prompt.text}</p>
                    {f'<p class="prompt-scripture">{prompt.scripture_reference}: {prompt.scripture_text}</p>' if prompt.scripture_reference else ''}
                    <a href="{reverse_lazy('journal:entry_create')}?prompt={prompt.pk}" class="btn btn-secondary">
                        Write about this
                    </a>
                </div>
            """)
        return HttpResponse("<p>No prompts available.</p>")


class TagListView(LoginRequiredMixin, ListView):
    """
    List user's custom tags.
    """

    model = Tag
    template_name = "journal/tag_list.html"
    context_object_name = "tags"

    def get_queryset(self):
        return Tag.objects.filter(user=self.request.user)


class TagCreateView(LoginRequiredMixin, CreateView):
    """
    Create a new tag.
    """

    model = Tag
    form_class = TagForm
    template_name = "journal/tag_form.html"
    success_url = reverse_lazy("journal:tag_list")

    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, "Tag created.")
        return super().form_valid(form)


class TagDeleteView(LoginRequiredMixin, View):
    """
    Delete a tag.
    """

    def post(self, request, pk):
        tag = get_object_or_404(
            Tag.objects.filter(user=request.user),
            pk=pk
        )
        tag.delete()
        messages.success(request, "Tag deleted.")
        return redirect("journal:tag_list")


# HTMX Views

class HTMXEntryFormView(LoginRequiredMixin, TemplateView):
    """
    HTMX endpoint for dynamically loading entry form fields.
    """

    template_name = "journal/partials/entry_form_fields.html"


class HTMXMoodSelectView(LoginRequiredMixin, TemplateView):
    """
    HTMX endpoint for mood selection component.
    """

    template_name = "journal/partials/mood_select.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["mood_choices"] = JournalEntry.MOOD_CHOICES
        context["selected_mood"] = self.request.GET.get("current", "")
        return context
