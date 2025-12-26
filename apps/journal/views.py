"""
Journal Views - CRUD operations and entry management.
"""

import random
from datetime import date
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import models
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
from django.db.models import Count
from django.views.generic import TemplateView




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


class PageView(LoginRequiredMixin, ListView):
    """
    Page view - displays all entries in a continuous scrollable format.
    """

    model = JournalEntry
    template_name = "journal/page_view.html"
    context_object_name = "entries"
    paginate_by = 50  # More entries per page for continuous reading

    def get_queryset(self):
        return JournalEntry.objects.filter(user=self.request.user).order_by('-entry_date')


class BookView(LoginRequiredMixin, ListView):
    """
    Book view - displays entries one at a time like pages in a book.
    Desktop only feature.
    """

    model = JournalEntry
    template_name = "journal/book_view.html"
    context_object_name = "entries"

    def get_queryset(self):
        return JournalEntry.objects.filter(user=self.request.user).order_by('-entry_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        entries = list(self.get_queryset())
        context["entries_json"] = [
            {
                "id": e.pk,
                "title": e.title,
                "date": e.entry_date.strftime("%B %d, %Y"),
                "body": e.body,
                "mood": e.get_mood_display() if e.mood else None,
                "mood_emoji": e.mood_emoji if e.mood else None,
            }
            for e in entries
        ]
        context["total_entries"] = len(entries)
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
        # Default entry_date to today
        initial["entry_date"] = date.today()
        # Title will be set dynamically based on date (handled in form/template)
        initial["title"] = ""
        
        # If coming from a prompt, pre-fill it and set category
        prompt_id = self.request.GET.get("prompt")
        if prompt_id:
            try:
                prompt = JournalPrompt.objects.get(pk=prompt_id)
                initial["prompt"] = prompt
                # Pre-select the prompt's category if it has one
                if prompt.category:
                    initial["category"] = prompt.category
            except JournalPrompt.DoesNotExist:
                pass
        
        return initial

    def form_valid(self, form):
        form.instance.user = self.request.user
        
        # If title is empty, default to the entry_date
        if not form.instance.title:
            entry_date = form.cleaned_data.get('entry_date', date.today())
            form.instance.title = entry_date.strftime("%A, %B %d, %Y")
        
        messages.success(self.request, "Journal entry created.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_edit"] = False
        context["page_title"] = "New Journal Entry"
        
        # Random prompt suggestion
        prompts = JournalPrompt.objects.filter(is_active=True)
        if not self.request.user.preferences.faith_enabled:
            prompts = prompts.filter(is_faith_specific=False)
        if prompts.exists():
            context["suggested_prompt"] = random.choice(list(prompts))
        
        # Pass prompt info if coming from a prompt
        prompt_id = self.request.GET.get("prompt")
        if prompt_id:
            try:
                context["selected_prompt"] = JournalPrompt.objects.get(pk=prompt_id)
            except JournalPrompt.DoesNotExist:
                pass
        
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
        context["page_title"] = "Edit Entry"
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
        
        # Filter by faith setting
        if not self.request.user.preferences.faith_enabled:
            queryset = queryset.filter(is_faith_specific=False)
        
        # Filter by category if specified
        category_slug = self.request.GET.get("category")
        if category_slug:
            queryset = queryset.filter(category__slug=category_slug)
        
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get all categories that have prompts
        base_queryset = JournalPrompt.objects.filter(is_active=True)
        if not self.request.user.preferences.faith_enabled:
            base_queryset = base_queryset.filter(is_faith_specific=False)
        
        # Get unique categories from prompts
        category_ids = base_queryset.exclude(category__isnull=True).values_list('category_id', flat=True).distinct()
        context["prompt_categories"] = Category.objects.filter(id__in=category_ids)
        context["active_category"] = self.request.GET.get("category")
        
        return context


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

# =============================================================================
# JOURNAL HOME VIEW (apps/journal/views.py)
# =============================================================================




class JournalHomeView(LoginRequiredMixin, TemplateView):
    template_name = "journal/home.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        from .models import JournalEntry, Tag
        
        now = timezone.now()
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)
        today = now.date()
        
        entries = JournalEntry.objects.filter(user=user)
        
        context["stats"] = {
            "total": entries.count(),
            "this_week": entries.filter(created_at__gte=week_ago).count(),
            "this_month": entries.filter(created_at__gte=month_ago).count(),
            "streak": self._calculate_streak(entries, today),
        }
        
        context["recent_entries"] = entries.order_by("-entry_date")[:5]
        context["mood_stats"] = self._get_mood_stats(entries, week_ago)
        
        # Prompts - skip if model doesn't exist
        context["suggested_prompt"] = None
        
        context["popular_tags"] = Tag.objects.filter(
            user=user
        ).annotate(entry_count=Count('journal_entries')).order_by('-entry_count')[:10]
        
        return context
    
    def _calculate_streak(self, entries, today):
        dates = entries.order_by('-entry_date').values_list('entry_date', flat=True).distinct()[:60]
        if not dates:
            return 0
        streak = 0
        expected_date = today
        for entry_date in dates:
            if entry_date == expected_date:
                streak += 1
                expected_date -= timedelta(days=1)
            elif entry_date < expected_date:
                break
        return streak
    
    def _get_mood_stats(self, entries, since):
        MOOD_EMOJIS = {'great': '😄', 'good': '🙂', 'okay': '😐', 'low': '😔', 'difficult': '😢'}
        moods = entries.filter(created_at__gte=since).exclude(mood='').values('mood').annotate(count=Count('mood')).order_by('-count')
        if not moods:
            return []
        total = sum(m['count'] for m in moods)
        return [{'mood': m['mood'], 'emoji': MOOD_EMOJIS.get(m['mood'], '😐'), 'count': m['count'], 'percentage': round((m['count'] / total) * 100)} for m in moods]