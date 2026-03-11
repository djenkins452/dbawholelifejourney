"""
Whole Life Journey - Journal Views

Project: Whole Life Journey
Path: apps/journal/views.py
Purpose: Views for journal entry CRUD operations and management

Description:
    Provides all views for creating, reading, updating, and deleting
    journal entries. Includes filtering, searching, prompts, and
    statistics views.

Key Views:
    - EntryListView: List entries with category/tag/date filtering
    - EntryCreateView: Create new journal entry with speech-to-text
    - EntryDetailView: View a single entry with edit options
    - EntryUpdateView: Edit an existing entry
    - EntryDeleteView: Soft delete with confirmation
    - RandomPromptView: HTMX endpoint for random prompt
    - JournalStatsView: Statistics and mood patterns

Security Notes:
    - All views require authentication (LoginRequiredMixin)
    - Entries are user-scoped in all queries
    - Random prompt response is HTML-escaped to prevent XSS

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""

import calendar
import json
import random
from datetime import date
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import models
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy

from apps.core.events.domain_events import safe_emit_event, EventTypes
from django.views.generic import (
    CreateView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
    View,
)

from apps.core.models import Category, Tag
from apps.core.views import SaveAddAnotherMixin
from apps.help.mixins import HelpContextMixin

from .forms import JournalEntryForm, TagForm
from .models import JournalEntry, JournalPrompt
from django.db.models import Count




class EntryListView(HelpContextMixin, LoginRequiredMixin, ListView):
    """
    List all active journal entries for the current user.
    """

    model = JournalEntry
    template_name = "journal/entry_list.html"
    context_object_name = "entries"
    paginate_by = 20
    help_context_id = "JOURNAL_ENTRY_LIST"

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
        entries_data = [
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
        # Pass raw data - json_script filter handles serialization
        context["entries_data"] = entries_data
        context["total_entries"] = len(entries)
        return context


class CalendarView(HelpContextMixin, LoginRequiredMixin, TemplateView):
    """
    Calendar view - displays journal entries in a monthly calendar format.
    """

    template_name = "journal/calendar_view.html"
    help_context_id = "JOURNAL_CALENDAR"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.core.utils import get_user_today

        user = self.request.user
        today = get_user_today(user)

        # Get month/year from query params or default to current month
        try:
            year = int(self.request.GET.get("year", today.year))
            month = int(self.request.GET.get("month", today.month))
            # Validate month range
            if month < 1 or month > 12:
                month = today.month
                year = today.year
        except (ValueError, TypeError):
            year = today.year
            month = today.month

        # Get first and last day of the month
        first_day = date(year, month, 1)
        if month == 12:
            last_day = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day = date(year, month + 1, 1) - timedelta(days=1)

        # Get entries for this month
        entries = JournalEntry.objects.filter(
            user=user,
            entry_date__gte=first_day,
            entry_date__lte=last_day
        ).order_by('entry_date')

        # Build a dict mapping dates to entries
        entries_by_date = {}
        for entry in entries:
            date_key = entry.entry_date
            if date_key not in entries_by_date:
                entries_by_date[date_key] = []
            entries_by_date[date_key].append(entry)

        # Build calendar weeks
        cal = calendar.Calendar(firstweekday=6)  # Sunday first
        weeks = []
        for week in cal.monthdayscalendar(year, month):
            week_data = []
            for day in week:
                if day == 0:
                    week_data.append({"day": None, "entries": [], "is_today": False})
                else:
                    day_date = date(year, month, day)
                    week_data.append({
                        "day": day,
                        "date": day_date,
                        "entries": entries_by_date.get(day_date, []),
                        "is_today": day_date == today,
                    })
            weeks.append(week_data)

        # Calculate prev/next month
        if month == 1:
            prev_month = 12
            prev_year = year - 1
        else:
            prev_month = month - 1
            prev_year = year

        if month == 12:
            next_month = 1
            next_year = year + 1
        else:
            next_month = month + 1
            next_year = year

        context["weeks"] = weeks
        context["current_month"] = first_day
        context["year"] = year
        context["month"] = month
        context["month_name"] = calendar.month_name[month]
        context["prev_month"] = prev_month
        context["prev_year"] = prev_year
        context["next_month"] = next_month
        context["next_year"] = next_year
        context["today"] = today
        context["total_count"] = JournalEntry.objects.filter(user=user).count()
        context["month_entry_count"] = entries.count()

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


class EntryDetailView(HelpContextMixin, LoginRequiredMixin, DetailView):
    """
    View a single journal entry.
    """

    model = JournalEntry
    template_name = "journal/entry_detail.html"
    context_object_name = "entry"
    help_context_id = "JOURNAL_ENTRY_DETAIL"

    def get_queryset(self):
        # Allow viewing archived entries too
        return JournalEntry.objects.include_archived().filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Check for milestone suggestion in session
        suggestion = self.request.session.pop('milestone_suggestion', None)
        if suggestion and suggestion.get('entry_id') == self.object.id:
            context['milestone_suggestion'] = suggestion

        return context


class EntryCreateView(HelpContextMixin, SaveAddAnotherMixin, LoginRequiredMixin, CreateView):
    """
    Create a new journal entry.
    """

    model = JournalEntry
    form_class = JournalEntryForm
    template_name = "journal/entry_form.html"
    help_context_id = "JOURNAL_ENTRY_CREATE"
    save_add_another_message = "Journal entry created. Add another!"

    def get_success_url(self):
        return reverse("journal:entry_detail", kwargs={"pk": self.object.pk})

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        # Default entry_date to today (in user's timezone)
        from apps.core.utils import get_user_today
        initial["entry_date"] = get_user_today(self.request.user)
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

        # Pre-fill body with @mentions from ?people=1,2,3
        people_param = self.request.GET.get("people", "")
        if people_param:
            try:
                from apps.relationships.models import Person
                person_ids = [int(pid) for pid in people_param.split(",") if pid.strip().isdigit()]
                people = Person.objects.filter(pk__in=person_ids, owner=self.request.user)
                if people.exists():
                    mentions = " ".join(f"@{p.get_display_name()}" for p in people)
                    initial["body"] = mentions + " "
            except Exception:
                pass

        return initial

    def form_valid(self, form):
        form.instance.user = self.request.user

        # If title is empty, default to the entry_date
        if not form.instance.title:
            from apps.core.utils import get_user_today
            entry_date = form.cleaned_data.get('entry_date', get_user_today(self.request.user))
            form.instance.title = entry_date.strftime("%A, %B %d, %Y")

        # Track if created via AI Camera scan
        source = self.request.GET.get('source')
        if source == 'ai_camera':
            from apps.core.models import UserOwnedModel
            form.instance.created_via = UserOwnedModel.CREATED_VIA_AI_CAMERA

        # Only show success message if not using "Save & Add Another"
        # (the mixin handles the message for that case)
        if 'save_add_another' not in self.request.POST:
            messages.success(self.request, "Journal entry created.")

        response = super().form_valid(form)

        # Fire intelligence chain (SAE → PIE → PRIE)
        from apps.core.ai_orchestrator.intelligence_hook import fire_intelligence
        fire_intelligence(self.request.user, "journal", self.object.id, "create_journal_entry")

        safe_emit_event(EventTypes.JOURNAL_ENTRY_CREATED, self.request.user, {
            "entry_id": self.object.id, "source": "web_view",
        })

        # Check for potential milestone completion (async-safe, non-blocking)
        self._check_milestone_completion(form.instance)

        return response

    def _check_milestone_completion(self, entry):
        """
        Check if journal entry indicates a milestone might be completed.
        Stores suggestion in session for display on entry detail page.
        """
        try:
            prefs = self.request.user.preferences
            if not prefs.purpose_enabled or not prefs.ai_enabled:
                return

            from apps.purpose.models import GoalMilestone

            # Get active milestones for the user
            active_milestones = GoalMilestone.objects.filter(
                goal__user=self.request.user,
                goal__status='active',
                completed=False
            ).select_related('goal')[:10]

            if not active_milestones:
                return

            # Prepare milestone data for AI
            milestones_data = [
                {
                    'id': m.id,
                    'title': m.title,
                    'description': m.description,
                    'goal_title': m.goal.title,
                }
                for m in active_milestones
            ]

            # Get entry content
            entry_text = f"{entry.title}\n\n{entry.body}" if entry.body else entry.title

            # Use AI service to detect milestone completion
            from apps.ai.services import AIService
            ai_service = AIService()
            result = ai_service.detect_milestone_completion(
                entry_text=entry_text,
                milestones=milestones_data,
                coaching_style=prefs.ai_coaching_style
            )

            if result and result.get('detected'):
                milestone_index = result.get('milestone_index', 0)
                if 0 <= milestone_index < len(milestones_data):
                    matched_milestone = milestones_data[milestone_index]
                    self.request.session['milestone_suggestion'] = {
                        'entry_id': entry.id,
                        'milestone_id': matched_milestone['id'],
                        'milestone_title': matched_milestone['title'],
                        'goal_title': matched_milestone['goal_title'],
                        'confidence': result.get('confidence', 'medium'),
                        'explanation': result.get('explanation', ''),
                    }
        except Exception:
            # Don't let milestone detection errors break journal creation
            import logging
            logging.getLogger(__name__).exception("Error in milestone detection")

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
        from django.utils.html import escape

        queryset = JournalPrompt.objects.filter(is_active=True)
        if not request.user.preferences.faith_enabled:
            queryset = queryset.filter(is_faith_specific=False)

        if queryset.exists():
            prompt = random.choice(list(queryset))
            # Escape all dynamic content to prevent XSS
            scripture_html = ''
            if prompt.scripture_reference:
                scripture_html = f'<p class="prompt-scripture">{escape(prompt.scripture_reference)}: {escape(prompt.scripture_text or "")}</p>'

            return HttpResponse(f"""
                <div class="prompt-card" id="random-prompt">
                    <p class="prompt-text">{escape(prompt.text)}</p>
                    {scripture_html}
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


class HTMXTagCreateModalView(LoginRequiredMixin, View):
    """
    HTMX endpoint for tag creation modal.
    Returns the modal form on GET, processes tag creation on POST.
    """

    def get(self, request):
        form = TagForm()
        return render(request, "journal/partials/tag_create_modal.html", {"form": form})

    def post(self, request):
        form = TagForm(request.POST)
        if form.is_valid():
            tag = form.save(commit=False)
            tag.user = request.user
            tag.save()
            # Return updated tag selector to swap into the form
            tags = Tag.objects.filter(user=request.user)
            return render(
                request,
                "journal/partials/tag_selector.html",
                {"tags": tags, "new_tag_id": tag.pk},
            )
        # Return form with errors
        return render(
            request,
            "journal/partials/tag_create_modal.html",
            {"form": form},
            status=422,
        )


# =============================================================================
# JOURNAL HOME VIEW (apps/journal/views.py)
# =============================================================================




class JournalHomeView(HelpContextMixin, LoginRequiredMixin, TemplateView):
    template_name = "journal/home.html"
    help_context_id = "JOURNAL_HOME"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        from .models import JournalEntry, Tag
        from apps.core.utils import get_user_today

        today = get_user_today(user)
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)

        entries = JournalEntry.objects.filter(user=user)

        context["stats"] = {
            "total": entries.count(),
            "this_week": entries.filter(entry_date__gte=week_ago).count(),
            "this_month": entries.filter(entry_date__gte=month_ago).count(),
            "streak": self._calculate_streak(entries, today),
        }

        context["recent_entries"] = entries.order_by("-entry_date")[:5]
        context["mood_stats"] = self._get_mood_stats(entries, week_ago)
        
        # Daily writing prompt — rotate based on day of year
        try:
            from apps.journal.models import JournalPrompt
            prompts = JournalPrompt.objects.filter(is_active=True)
            # Filter faith-specific prompts if user doesn't have faith enabled
            try:
                if not user.preferences.faith_enabled:
                    prompts = prompts.filter(is_faith_specific=False)
            except Exception:
                prompts = prompts.filter(is_faith_specific=False)
            prompt_count = prompts.count()
            if prompt_count > 0:
                day_index = today.toordinal() % prompt_count
                context["suggested_prompt"] = prompts.order_by("pk")[day_index]
            else:
                context["suggested_prompt"] = None
        except Exception:
            context["suggested_prompt"] = None
        
        context["popular_tags"] = Tag.objects.filter(
            user=user
        ).annotate(entry_count=Count('journal_entries')).order_by('-entry_count')[:10]

        # AI insight — engine-first: read latest PIE insight (no OpenAI)
        from apps.core.ai_insights.services import get_module_insight
        context['ai_insight'] = get_module_insight(user, 'journal')
        context['ai_enabled'] = getattr(user.preferences, 'ai_enabled', False)

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
        """Build mood stats from emotions ManyToMany field on entries."""
        from apps.journal.models import Emotion
        week_entries = entries.filter(entry_date__gte=since)
        # Count each emotion across all entries this week
        emotion_counts = (
            Emotion.objects.filter(
                journal_entries__in=week_entries,
                is_active=True,
            )
            .values('name', 'emoji', 'slug')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        if not emotion_counts:
            return []
        total = sum(e['count'] for e in emotion_counts)
        return [
            {
                'mood': e['name'],
                'emoji': e['emoji'],
                'count': e['count'],
                'percentage': round((e['count'] / total) * 100),
            }
            for e in emotion_counts
        ]


# =============================================================================
# BULK ACTION VIEWS
# =============================================================================


class BulkDeleteEntriesView(LoginRequiredMixin, View):
    """
    Bulk delete journal entries (soft delete).
    Accepts JSON body with 'ids' array.
    """

    def post(self, request):
        try:
            data = json.loads(request.body)
            ids = data.get('ids', [])
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

        if not ids:
            return JsonResponse({'success': False, 'error': 'No items selected'}, status=400)

        # Get entries owned by this user
        entries = JournalEntry.objects.filter(user=request.user, pk__in=ids)
        count = entries.count()

        if count == 0:
            return JsonResponse({'success': False, 'error': 'No entries found'}, status=404)

        # Soft delete each entry
        for entry in entries:
            entry.soft_delete()

        return JsonResponse({
            'success': True,
            'message': f'{count} entr{"y" if count == 1 else "ies"} deleted',
            'count': count
        })


class BulkArchiveEntriesView(LoginRequiredMixin, View):
    """
    Bulk archive journal entries.
    Accepts JSON body with 'ids' array.
    """

    def post(self, request):
        try:
            data = json.loads(request.body)
            ids = data.get('ids', [])
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

        if not ids:
            return JsonResponse({'success': False, 'error': 'No items selected'}, status=400)

        # Get entries owned by this user
        entries = JournalEntry.objects.filter(user=request.user, pk__in=ids)
        count = entries.count()

        if count == 0:
            return JsonResponse({'success': False, 'error': 'No entries found'}, status=404)

        # Archive each entry
        for entry in entries:
            entry.archive()

        return JsonResponse({
            'success': True,
            'message': f'{count} entr{"y" if count == 1 else "ies"} archived',
            'count': count
        })