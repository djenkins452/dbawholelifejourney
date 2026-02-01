# ==============================================================================
# File: apps/faith/views.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Faith module views for Scripture, prayers, reading plans, and
#              Bible study tools
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2024-01-01
# Last Updated: 2026-01-01
# ==============================================================================
"""
Faith Views - Scripture, prayers, reading plans, and spiritual growth.
"""

import json
import logging
import random
from urllib.parse import quote

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import (
    CreateView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
    View,
)

from apps.core.models import Category
from apps.help.mixins import HelpContextMixin
from apps.journal.models import JournalEntry
from apps.journal.forms import JournalEntryForm

from .forms import (
    BibleBookmarkForm,
    BibleHighlightForm,
    BibleStudyNoteForm,
    FaithMilestoneForm,
    PrayerRequestForm,
    SavedVerseForm,
)
from .models import (
    BibleBookmark,
    BibleHighlight,
    BibleStudyNote,
    DailyVerse,
    FaithMilestone,
    PrayerRequest,
    ReadingPlanAssessment,
    ReadingPlanDay,
    ReadingPlanTemplate,
    SavedVerse,
    ScriptureVerse,
    UserAssessmentResponse,
    UserReadingPlan,
    UserReadingProgress,
)

logger = logging.getLogger(__name__)

# YouVersion Bible API base URL
BIBLE_API_BASE = "https://api.youversion.com/v1"

# Blocklist of Bible translation IDs that are known to not work properly
# Note: YouVersion API uses numeric IDs (e.g., 12, 3034) - add any problematic ones here
BLOCKED_BIBLE_TRANSLATIONS = set()  # Currently empty - all YouVersion translations work


class FaithRequiredMixin(UserPassesTestMixin):
    """
    Mixin to ensure user has Faith module enabled.

    Redirects to preferences if Faith is not enabled.
    Requires user to be authenticated first (use with LoginRequiredMixin).
    """

    def test_func(self):
        # Only check faith_enabled for authenticated users
        # LoginRequiredMixin should handle unauthenticated users first
        if not self.request.user.is_authenticated:
            return False
        return self.request.user.preferences.faith_enabled

    def handle_no_permission(self):
        # If user is not authenticated, let LoginRequiredMixin handle it
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        messages.info(
            self.request,
            "Enable the Faith module in your preferences to access this feature."
        )
        return redirect("users:preferences")


class FaithHomeView(HelpContextMixin, LoginRequiredMixin, FaithRequiredMixin, TemplateView):
    """
    Faith module home - overview of spiritual journey.
    """

    template_name = "faith/home.html"
    help_context_id = "FAITH_HOME"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        # Today's verse
        context["todays_verse"] = self.get_todays_verse()
        
        # Active prayer requests
        context["active_prayers"] = PrayerRequest.objects.filter(
            user=user,
            is_answered=False,
        ).order_by("-priority", "-created_at")[:5]
        
        # Recent answered prayers
        context["answered_prayers_count"] = PrayerRequest.objects.filter(
            user=user,
            is_answered=True,
        ).count()
        
        # Faith reflections (journal entries with faith category)
        faith_category = Category.objects.filter(slug="faith").first()
        if faith_category:
            context["recent_reflections"] = JournalEntry.objects.filter(
                user=user,
                categories=faith_category,
            ).order_by("-entry_date")[:3]
        
        # Milestones
        context["milestones"] = FaithMilestone.objects.filter(user=user)[:5]

        # Active reading plan
        context["active_reading_plan"] = UserReadingPlan.objects.filter(
            user=user,
            plan_status="active",
        ).select_related("template").first()

        # Generate AI insight if user has AI enabled and consented
        context['ai_insight'] = None
        context['ai_enabled'] = False
        try:
            prefs = user.preferences
            if prefs.ai_enabled and prefs.ai_data_consent:
                context['ai_enabled'] = True
                from apps.ai.services import ai_service
                todays_verse = context.get('todays_verse')
                faith_data = {
                    'active_prayers': context['active_prayers'].count() if hasattr(context.get('active_prayers'), 'count') else len(context.get('active_prayers', [])),
                    'answered_prayers': context.get('answered_prayers_count', 0),
                    'recent_reflections': len(context.get('recent_reflections', [])),
                    'milestones': context['milestones'].count() if hasattr(context.get('milestones'), 'count') else len(context.get('milestones', [])),
                    'todays_verse': todays_verse['verse'].reference if todays_verse and todays_verse.get('verse') else None,
                }
                context['ai_insight'] = ai_service.generate_faith_home_insight(
                    faith_data,
                    coaching_style=prefs.ai_coaching_style
                )
        except Exception:
            pass

        return context

    def get_todays_verse(self):
        """
        Get today's verse, or a random one if none assigned.

        The verse is cached per-user per-day so the same verse shows all day.
        It refreshes on the first access of each new day.
        """
        from apps.core.utils import get_user_today
        today = get_user_today(self.request.user)
        user_id = self.request.user.id

        # Try to get assigned verse for today (no caching needed - same for all users)
        try:
            daily = DailyVerse.objects.get(date=today)
            return {
                "verse": daily.verse,
                "prompt": daily.reflection_prompt,
            }
        except DailyVerse.DoesNotExist:
            pass

        # Check cache for user's random verse for today
        cache_key = f"todays_verse_{user_id}_{today.isoformat()}"
        cached_verse_id = cache.get(cache_key)

        if cached_verse_id:
            # Return cached verse
            try:
                verse = ScriptureVerse.objects.get(id=cached_verse_id, is_active=True)
                return {"verse": verse, "prompt": ""}
            except ScriptureVerse.DoesNotExist:
                # Cached verse no longer exists, will select new one below
                pass

        # Select a random verse and cache it for the day
        verses = ScriptureVerse.objects.filter(is_active=True)
        if verses.exists():
            selected_verse = random.choice(list(verses))
            # Cache until end of day (24 hours is safe since key includes date)
            cache.set(cache_key, selected_verse.id, 60 * 60 * 24)
            return {"verse": selected_verse, "prompt": ""}

        return None


class TodaysVerseView(LoginRequiredMixin, FaithRequiredMixin, TemplateView):
    """
    Display today's Scripture verse with reflection.

    The verse is cached per-user per-day so the same verse shows all day.
    It refreshes on the first access of each new day.
    """

    template_name = "faith/todays_verse.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.core.utils import get_user_today
        today = get_user_today(self.request.user)
        user_id = self.request.user.id

        try:
            daily = DailyVerse.objects.get(date=today)
            context["daily_verse"] = daily
            context["verse"] = daily.verse
        except DailyVerse.DoesNotExist:
            # Check cache for user's random verse for today
            cache_key = f"todays_verse_{user_id}_{today.isoformat()}"
            cached_verse_id = cache.get(cache_key)

            if cached_verse_id:
                try:
                    context["verse"] = ScriptureVerse.objects.get(
                        id=cached_verse_id, is_active=True
                    )
                except ScriptureVerse.DoesNotExist:
                    cached_verse_id = None

            if not cached_verse_id:
                # Select a random verse and cache it for the day
                verses = ScriptureVerse.objects.filter(is_active=True)
                if verses.exists():
                    selected_verse = random.choice(list(verses))
                    cache.set(cache_key, selected_verse.id, 60 * 60 * 24)
                    context["verse"] = selected_verse

        return context


class ScriptureListView(LoginRequiredMixin, FaithRequiredMixin, ListView):
    """
    Browse user's saved Scripture verses with Bible API lookup.
    """

    model = SavedVerse
    template_name = "faith/scripture_list.html"
    context_object_name = "verses"
    paginate_by = 20

    def get_queryset(self):
        # Filter by current user's saved verses only
        queryset = SavedVerse.objects.filter(user=self.request.user)

        # Filter by theme (use icontains on the JSON field as string for SQLite compatibility)
        theme = self.request.GET.get("theme")
        if theme:
            # For SQLite, we filter by checking if the theme appears in the JSON string
            queryset = queryset.filter(themes__icontains=theme)

        # Filter by book
        book = self.request.GET.get("book")
        if book:
            queryset = queryset.filter(book_name=book)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Get unique themes and books for filtering from user's saved verses
        user_verses = SavedVerse.objects.filter(user=self.request.user)
        themes = set()
        books = set()
        for verse in user_verses:
            themes.update(verse.themes)
            books.add(verse.book_name)
        context["available_themes"] = sorted(themes)
        context["available_books"] = sorted(books)
        context["selected_theme"] = self.request.GET.get("theme", "")
        context["selected_book"] = self.request.GET.get("book", "")
        # NOTE: API key is NO LONGER sent to frontend (Security Fix C-2)
        # Bible API is now accessed via server-side proxy at /faith/api/bible/
        # User's default translation preference
        context["default_translation"] = self.request.user.preferences.default_bible_translation
        # Auto-lookup parameter (e.g., "Luke 18:1-8")
        context["lookup_reference"] = self.request.GET.get("lookup", "")
        return context


class ScriptureDetailView(LoginRequiredMixin, FaithRequiredMixin, DetailView):
    """
    View a single Scripture verse with context.
    """

    model = ScriptureVerse
    template_name = "faith/scripture_detail.html"
    context_object_name = "verse"


class ScriptureSaveView(LoginRequiredMixin, FaithRequiredMixin, View):
    """
    Save a looked-up Scripture verse to the user's personal library.
    """

    # Book order mapping for Bible books
    BOOK_ORDER = {
        'Genesis': 1, 'Exodus': 2, 'Leviticus': 3, 'Numbers': 4, 'Deuteronomy': 5,
        'Joshua': 6, 'Judges': 7, 'Ruth': 8, '1 Samuel': 9, '2 Samuel': 10,
        '1 Kings': 11, '2 Kings': 12, '1 Chronicles': 13, '2 Chronicles': 14,
        'Ezra': 15, 'Nehemiah': 16, 'Esther': 17, 'Job': 18, 'Psalms': 19,
        'Proverbs': 20, 'Ecclesiastes': 21, 'Song of Solomon': 22, 'Isaiah': 23,
        'Jeremiah': 24, 'Lamentations': 25, 'Ezekiel': 26, 'Daniel': 27,
        'Hosea': 28, 'Joel': 29, 'Amos': 30, 'Obadiah': 31, 'Jonah': 32,
        'Micah': 33, 'Nahum': 34, 'Habakkuk': 35, 'Zephaniah': 36, 'Haggai': 37,
        'Zechariah': 38, 'Malachi': 39, 'Matthew': 40, 'Mark': 41, 'Luke': 42,
        'John': 43, 'Acts': 44, 'Romans': 45, '1 Corinthians': 46, '2 Corinthians': 47,
        'Galatians': 48, 'Ephesians': 49, 'Philippians': 50, 'Colossians': 51,
        '1 Thessalonians': 52, '2 Thessalonians': 53, '1 Timothy': 54, '2 Timothy': 55,
        'Titus': 56, 'Philemon': 57, 'Hebrews': 58, 'James': 59, '1 Peter': 60,
        '2 Peter': 61, '1 John': 62, '2 John': 63, '3 John': 64, 'Jude': 65,
        'Revelation': 66,
    }

    def post(self, request):
        reference = request.POST.get('reference', '')
        text = request.POST.get('text', '')
        book_name = request.POST.get('book_name', '')
        chapter = request.POST.get('chapter', '')
        verse_start = request.POST.get('verse_start', '')
        verse_end = request.POST.get('verse_end', '')
        translation = request.POST.get('translation', '')
        themes_str = request.POST.get('themes', '')
        notes = request.POST.get('notes', '')

        # Parse themes
        themes = [t.strip() for t in themes_str.split(',') if t.strip()]

        # Parse verse numbers
        try:
            verse_start_int = int(verse_start) if verse_start else 1
            verse_end_int = int(verse_end) if verse_end else None
            chapter_int = int(chapter) if chapter else 1
        except ValueError:
            verse_start_int = 1
            verse_end_int = None
            chapter_int = 1

        # Get book order (default to 1 if not found)
        book_order = self.BOOK_ORDER.get(book_name, 1)

        # Extract translation abbreviation from full name (e.g., "KJV - King James Version" -> "KJV")
        translation_abbrev = translation.split(' - ')[0].strip() if ' - ' in translation else translation[:10]

        # Create the user's saved verse
        SavedVerse.objects.create(
            user=request.user,
            reference=reference,
            text=text,
            book_name=book_name,
            book_order=book_order,
            chapter=chapter_int,
            verse_start=verse_start_int,
            verse_end=verse_end_int,
            translation=translation_abbrev,
            themes=themes,
            notes=notes,
        )

        messages.success(request, f'"{reference}" saved to your Scripture library.')
        return redirect('faith:scripture_list')


class SavedVerseUpdateView(LoginRequiredMixin, FaithRequiredMixin, UpdateView):
    """
    Edit a saved Scripture verse.
    """

    model = SavedVerse
    form_class = SavedVerseForm
    template_name = "faith/saved_verse_form.html"

    def get_queryset(self):
        return SavedVerse.objects.filter(user=self.request.user)

    def get_success_url(self):
        return reverse_lazy("faith:scripture_list")

    def form_valid(self, form):
        messages.success(self.request, "Verse updated.")
        return super().form_valid(form)


class SavedVerseDeleteView(LoginRequiredMixin, FaithRequiredMixin, View):
    """
    Delete a saved Scripture verse.
    """

    def post(self, request, pk):
        verse = get_object_or_404(
            SavedVerse.objects.filter(user=request.user),
            pk=pk
        )
        reference = verse.reference
        verse.soft_delete()
        messages.success(request, f'"{reference}" removed from your Scripture library.')
        return redirect("faith:scripture_list")


# Prayer Request Views

class PrayerListView(LoginRequiredMixin, FaithRequiredMixin, ListView):
    """
    List active prayer requests.
    """

    model = PrayerRequest
    template_name = "faith/prayer_list.html"
    context_object_name = "prayers"
    paginate_by = 20

    def get_queryset(self):
        return PrayerRequest.objects.filter(
            user=self.request.user,
            is_answered=False,
        ).order_by("-priority", "-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["answered_count"] = PrayerRequest.objects.filter(
            user=self.request.user,
            is_answered=True,
        ).count()
        return context


class AnsweredPrayersView(LoginRequiredMixin, FaithRequiredMixin, ListView):
    """
    List answered prayers - a record of God's faithfulness.
    """

    model = PrayerRequest
    template_name = "faith/answered_prayers.html"
    context_object_name = "prayers"
    paginate_by = 20

    def get_queryset(self):
        return PrayerRequest.objects.filter(
            user=self.request.user,
            is_answered=True,
        ).order_by("-answered_at")


class PrayerDetailView(LoginRequiredMixin, FaithRequiredMixin, DetailView):
    """
    View a prayer request.
    """

    model = PrayerRequest
    template_name = "faith/prayer_detail.html"
    context_object_name = "prayer"

    def get_queryset(self):
        return PrayerRequest.objects.filter(user=self.request.user)


class PrayerCreateView(LoginRequiredMixin, FaithRequiredMixin, CreateView):
    """
    Create a new prayer request.
    """

    model = PrayerRequest
    form_class = PrayerRequestForm
    template_name = "faith/prayer_form.html"
    success_url = reverse_lazy("faith:prayer_list")

    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, "Prayer request added.")
        return super().form_valid(form)


class PrayerUpdateView(LoginRequiredMixin, FaithRequiredMixin, UpdateView):
    """
    Edit a prayer request.
    """

    model = PrayerRequest
    form_class = PrayerRequestForm
    template_name = "faith/prayer_form.html"

    def get_queryset(self):
        return PrayerRequest.objects.filter(user=self.request.user)

    def get_success_url(self):
        return reverse_lazy("faith:prayer_detail", kwargs={"pk": self.object.pk})

    def form_valid(self, form):
        messages.success(self.request, "Prayer request updated.")
        return super().form_valid(form)


class MarkPrayerAnsweredView(LoginRequiredMixin, FaithRequiredMixin, View):
    """
    Mark a prayer as answered.
    """

    def post(self, request, pk):
        prayer = get_object_or_404(
            PrayerRequest.objects.filter(user=request.user),
            pk=pk
        )
        notes = request.POST.get("notes", "")
        prayer.mark_answered(notes)
        messages.success(
            request,
            "Praise God! Prayer marked as answered."
        )
        return redirect("faith:answered_prayers")


class PrayerDeleteView(LoginRequiredMixin, FaithRequiredMixin, View):
    """
    Delete a prayer request.
    """

    def post(self, request, pk):
        prayer = get_object_or_404(
            PrayerRequest.objects.filter(user=request.user),
            pk=pk
        )
        prayer.soft_delete()
        messages.success(request, "Prayer request deleted.")
        return redirect("faith:prayer_list")


# Milestone Views

class MilestoneListView(LoginRequiredMixin, FaithRequiredMixin, ListView):
    """
    List faith milestones - significant moments in the journey.
    """

    model = FaithMilestone
    template_name = "faith/milestone_list.html"
    context_object_name = "milestones"

    def get_queryset(self):
        return FaithMilestone.objects.filter(user=self.request.user)


class MilestoneDetailView(LoginRequiredMixin, FaithRequiredMixin, DetailView):
    """
    View a faith milestone.
    """

    model = FaithMilestone
    template_name = "faith/milestone_detail.html"
    context_object_name = "milestone"

    def get_queryset(self):
        return FaithMilestone.objects.filter(user=self.request.user)


class MilestoneCreateView(LoginRequiredMixin, FaithRequiredMixin, CreateView):
    """
    Add a new faith milestone.
    """

    model = FaithMilestone
    form_class = FaithMilestoneForm
    template_name = "faith/milestone_form.html"
    success_url = reverse_lazy("faith:milestone_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, "Milestone added to your faith journey.")
        return super().form_valid(form)


class MilestoneUpdateView(LoginRequiredMixin, FaithRequiredMixin, UpdateView):
    """
    Edit a faith milestone.
    """

    model = FaithMilestone
    form_class = FaithMilestoneForm
    template_name = "faith/milestone_form.html"

    def get_queryset(self):
        return FaithMilestone.objects.filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_success_url(self):
        return reverse_lazy("faith:milestone_detail", kwargs={"pk": self.object.pk})


class MilestoneDeleteView(LoginRequiredMixin, FaithRequiredMixin, View):
    """
    Delete a faith milestone.
    """

    def post(self, request, pk):
        milestone = get_object_or_404(
            FaithMilestone.objects.filter(user=request.user),
            pk=pk
        )
        milestone.soft_delete()
        messages.success(request, "Milestone deleted.")
        return redirect("faith:milestone_list")


class FaithReflectionsView(LoginRequiredMixin, FaithRequiredMixin, ListView):
    """
    View journal entries tagged with Faith category.
    
    This is a filtered view of the Journal, showing only
    faith-related reflections.
    """

    model = JournalEntry
    template_name = "faith/reflections.html"
    context_object_name = "entries"
    paginate_by = 20

    def get_queryset(self):
        faith_category = Category.objects.filter(slug="faith").first()
        if faith_category:
            return JournalEntry.objects.filter(
                user=self.request.user,
                categories=faith_category,
            ).order_by("-entry_date")
        return JournalEntry.objects.none()


class ReflectionCreateView(LoginRequiredMixin, FaithRequiredMixin, CreateView):
    """
    Create a new faith reflection (journal entry with Faith category pre-selected).
    """

    model = JournalEntry
    form_class = JournalEntryForm
    template_name = "faith/reflection_form.html"
    success_url = reverse_lazy("faith:reflections")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        from apps.core.utils import get_user_today
        initial["entry_date"] = get_user_today(self.request.user)
        initial["title"] = ""
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_edit"] = False
        return context

    def form_valid(self, form):
        form.instance.user = self.request.user

        # If title is empty, default to the entry_date
        if not form.instance.title:
            from apps.core.utils import get_user_today
            entry_date = form.cleaned_data.get('entry_date', get_user_today(self.request.user))
            form.instance.title = entry_date.strftime("%A, %B %d, %Y")
        
        # Save first to get the instance
        response = super().form_valid(form)
        
        # Ensure Faith category is added
        faith_category = Category.objects.filter(slug="faith").first()
        if faith_category:
            self.object.categories.add(faith_category)
        
        messages.success(self.request, "Faith reflection saved.")
        return response


# =============================================================================
# Bible API Proxy Views
# =============================================================================
# These views proxy requests to the Bible API, keeping the API key server-side.
# This fixes Critical Security Finding C-2: API key exposure to frontend.


class BibleAPIProxyMixin:
    """
    Mixin providing YouVersion Bible API proxy functionality.

    Security: Keeps Bible API key server-side, never exposed to frontend.
    """

    def get_api_key(self):
        """Get the YouVersion API key from settings."""
        return getattr(settings, 'YOUVERSION_API_KEY', '')

    def is_api_configured(self):
        """Check if YouVersion API is configured."""
        return bool(self.get_api_key())

    def make_api_request(self, endpoint, params=None):
        """
        Make a request to the YouVersion Bible API.

        Args:
            endpoint: API endpoint path (e.g., '/bibles')
            params: Optional query parameters

        Returns:
            tuple: (success: bool, data: dict or error message)
        """
        api_key = self.get_api_key()
        if not api_key:
            return False, {"error": "Bible API is not configured"}

        url = f"{BIBLE_API_BASE}{endpoint}"
        headers = {"X-YVP-App-Key": api_key}

        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            return True, response.json()
        except requests.exceptions.Timeout:
            logger.warning(f"YouVersion API timeout: {endpoint}")
            return False, {"error": "Request timed out"}
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                logger.error("YouVersion API: Invalid or expired API key")
                return False, {"error": "Bible API key is invalid or expired. Please contact the administrator."}
            # Try to extract error details from response body
            error_detail = ""
            try:
                error_body = e.response.json()
                if isinstance(error_body, dict):
                    error_detail = error_body.get('message', error_body.get('error', ''))
            except Exception:
                error_detail = e.response.text[:200] if e.response.text else ""
            logger.error(f"YouVersion API HTTP error: {e.response.status_code} - {error_detail} - URL: {url}")
            # For 404/403 errors, provide user-friendly messages
            if e.response.status_code == 404:
                return False, {"error": "Scripture not found. This translation may not have this passage available."}
            if e.response.status_code == 403:
                return False, {"error": "This translation is not available for this passage. Please try a different translation."}
            return False, {"error": f"Bible API error: {e.response.status_code}"}
        except requests.exceptions.RequestException as e:
            logger.error(f"YouVersion API error: {e}")
            return False, {"error": "Failed to fetch from Bible API"}


class BibleAPIStatusView(LoginRequiredMixin, FaithRequiredMixin, BibleAPIProxyMixin, View):
    """
    Check if Bible API is configured (without exposing the key).

    Returns JSON: {"configured": true/false}
    """

    def get(self, request):
        return JsonResponse({
            "configured": self.is_api_configured()
        })


class BibleAPIBiblesView(LoginRequiredMixin, FaithRequiredMixin, BibleAPIProxyMixin, View):
    """
    Proxy for YouVersion API /bibles endpoint.

    Returns list of available Bible translations.
    Supports language filtering via language_ranges parameter.
    """

    def get(self, request):
        if not self.is_api_configured():
            return JsonResponse(
                {"error": "Bible API is not configured"},
                status=503
            )

        # YouVersion requires language_ranges parameter
        # Default to English, but allow override via query param
        params = {}
        language = request.GET.get('language', 'en')
        params['language_ranges[]'] = language
        # Include all translations the API key has access to (not just public domain)
        params['all_available'] = 'true'
        # Get more results per page (default is 25)
        params['page_size'] = '100'

        success, data = self.make_api_request("/bibles", params=params)
        if success:
            # Transform YouVersion response to match frontend expectations
            # YouVersion returns: {"data": [...], "next_page_token": ..., "total_size": ...}
            # Frontend expects: {"data": [{"id": ..., "name": ..., "abbreviation": ...}, ...]}
            transformed_data = []
            for bible in data.get('data', []):
                bible_id = str(bible.get('id', ''))
                # Skip blocked translations that have known issues
                if bible_id in BLOCKED_BIBLE_TRANSLATIONS:
                    continue
                transformed_data.append({
                    'id': bible_id,
                    'name': bible.get('title', bible.get('localized_title', '')),
                    'abbreviation': bible.get('abbreviation', bible.get('localized_abbreviation', '')),
                    'language': bible.get('language_tag', ''),
                    'copyright': bible.get('copyright', ''),
                })
            return JsonResponse({'data': transformed_data})
        return JsonResponse(data, status=500)


class BibleAPIBooksView(LoginRequiredMixin, FaithRequiredMixin, BibleAPIProxyMixin, View):
    """
    Proxy for YouVersion API /bibles/{bibleId}/books endpoint.

    Returns list of books in a specific Bible translation.
    """

    def get(self, request, bible_id):
        if not self.is_api_configured():
            return JsonResponse(
                {"error": "Bible API is not configured"},
                status=503
            )

        # Sanitize bible_id to prevent injection
        safe_bible_id = quote(bible_id, safe='')
        success, data = self.make_api_request(f"/bibles/{safe_bible_id}/books")
        if success:
            # Transform YouVersion response to match frontend expectations
            # YouVersion returns array of books with id, title, abbreviation, etc.
            transformed_data = []
            books = data.get('data', data) if isinstance(data, dict) else data
            if isinstance(books, list):
                for book in books:
                    transformed_data.append({
                        'id': book.get('id', book.get('usfm', '')),
                        'name': book.get('title', book.get('full_title', '')),
                        'abbreviation': book.get('abbreviation', ''),
                    })
            return JsonResponse({'data': transformed_data})
        return JsonResponse(data, status=500)


class BibleAPIChaptersView(LoginRequiredMixin, FaithRequiredMixin, BibleAPIProxyMixin, View):
    """
    Proxy for YouVersion API /bibles/{bibleId}/books/{bookId}/chapters endpoint.

    Returns list of chapters in a specific book.
    """

    def get(self, request, bible_id, book_id):
        if not self.is_api_configured():
            return JsonResponse(
                {"error": "Bible API is not configured"},
                status=503
            )

        # Sanitize inputs
        safe_bible_id = quote(bible_id, safe='')
        safe_book_id = quote(book_id, safe='')
        success, data = self.make_api_request(
            f"/bibles/{safe_bible_id}/books/{safe_book_id}/chapters"
        )
        if success:
            # Transform YouVersion response to match frontend expectations
            transformed_data = []
            chapters = data.get('data', data) if isinstance(data, dict) else data
            if isinstance(chapters, list):
                for chapter in chapters:
                    # YouVersion returns chapters with 'usfm' field like "JHN.3"
                    # or sometimes just numeric 'id'. We need USFM format for passages API.
                    chapter_id = chapter.get('usfm', chapter.get('id', chapter.get('passage_id', '')))
                    # If we only got a numeric ID, construct USFM from book_id and chapter number
                    if chapter_id and '.' not in str(chapter_id):
                        # Try to construct from book context
                        chapter_num = chapter.get('number', chapter_id)
                        chapter_id = f"{safe_book_id}.{chapter_num}"
                    transformed_data.append({
                        'id': chapter_id,
                        'number': chapter.get('number', chapter.get('title', chapter_id.split('.')[-1] if '.' in str(chapter_id) else chapter_id)),
                    })
            return JsonResponse({'data': transformed_data})
        return JsonResponse(data, status=500)


class BibleAPIVersesView(LoginRequiredMixin, FaithRequiredMixin, BibleAPIProxyMixin, View):
    """
    Proxy for YouVersion API - get verses in a chapter.

    YouVersion doesn't have a direct verses list endpoint like api.bible.
    We use the passages endpoint to get the full chapter text.
    """

    def get(self, request, bible_id, chapter_id):
        if not self.is_api_configured():
            return JsonResponse(
                {"error": "Bible API is not configured"},
                status=503
            )

        # Sanitize inputs
        safe_bible_id = quote(bible_id, safe='')
        # chapter_id should be in format like "GEN.1"
        safe_chapter_id = quote(chapter_id, safe='')

        # Use passages endpoint to get chapter content
        success, data = self.make_api_request(
            f"/bibles/{safe_bible_id}/passages/{safe_chapter_id}"
        )
        if success:
            # Return passage data - frontend will handle display
            return JsonResponse({
                'data': {
                    'id': data.get('id', chapter_id),
                    'reference': data.get('reference', ''),
                    'content': data.get('content', ''),
                }
            })
        return JsonResponse(data, status=500)


class BibleAPIVerseView(LoginRequiredMixin, FaithRequiredMixin, BibleAPIProxyMixin, View):
    """
    Proxy for YouVersion API /bibles/{bibleId}/passages/{passageId} endpoint.

    Returns a specific verse or verse range.
    YouVersion uses passages endpoint for both single verses and ranges.
    """

    def get(self, request, bible_id, verse_id):
        if not self.is_api_configured():
            return JsonResponse(
                {"error": "Bible API is not configured"},
                status=503
            )

        # Sanitize inputs
        safe_bible_id = quote(bible_id, safe='')
        # verse_id should be in USFM format like "JHN.3.16" or "JHN.3.16-18"
        safe_verse_id = quote(verse_id, safe='')

        # Pass through query params for content options
        params = {}
        if request.GET.get('format'):
            params['format'] = request.GET['format']
        if request.GET.get('include_headings'):
            params['include_headings'] = request.GET['include_headings']
        if request.GET.get('include_notes'):
            params['include_notes'] = request.GET['include_notes']

        # YouVersion uses /passages/ endpoint for verse lookups
        success, data = self.make_api_request(
            f"/bibles/{safe_bible_id}/passages/{safe_verse_id}",
            params=params if params else None
        )
        if success:
            # Transform to match frontend expectations
            return JsonResponse({
                'data': {
                    'id': data.get('id', verse_id),
                    'reference': data.get('reference', ''),
                    'content': data.get('content', ''),
                }
            })
        return JsonResponse(data, status=500)


class BibleAPIPassageView(LoginRequiredMixin, FaithRequiredMixin, BibleAPIProxyMixin, View):
    """
    Proxy for YouVersion API /bibles/{bibleId}/passages/{passageId} endpoint.

    Returns a passage (can span multiple verses/chapters).
    """

    def get(self, request, bible_id, passage_id):
        if not self.is_api_configured():
            return JsonResponse(
                {"error": "Bible API is not configured"},
                status=503
            )

        # Sanitize inputs
        safe_bible_id = quote(bible_id, safe='')
        # passage_id should be in USFM format like "JHN.3.16" or "JHN.3.16-18"
        safe_passage_id = quote(passage_id, safe='')

        # Pass through query params
        params = {}
        if request.GET.get('format'):
            params['format'] = request.GET['format']
        if request.GET.get('include_headings'):
            params['include_headings'] = request.GET['include_headings']
        if request.GET.get('include_notes'):
            params['include_notes'] = request.GET['include_notes']

        logger.debug(f"Fetching passage: bible_id={safe_bible_id}, passage_id={safe_passage_id}")
        success, data = self.make_api_request(
            f"/bibles/{safe_bible_id}/passages/{safe_passage_id}",
            params=params if params else None
        )
        if success:
            # Transform to match frontend expectations
            return JsonResponse({
                'data': {
                    'id': data.get('id', passage_id),
                    'reference': data.get('reference', ''),
                    'content': data.get('content', ''),
                }
            })
        # Return the error with more context
        logger.warning(f"Passage fetch failed: bible_id={safe_bible_id}, passage_id={safe_passage_id}, error={data}")
        return JsonResponse(data, status=500)


class BibleAPISearchView(LoginRequiredMixin, FaithRequiredMixin, BibleAPIProxyMixin, View):
    """
    Search endpoint placeholder.

    Note: YouVersion API does not currently support text search.
    This endpoint returns a helpful message directing users to use
    direct verse lookup instead.
    """

    def get(self, request, bible_id):
        # YouVersion API does not support text search
        return JsonResponse({
            "error": "Text search is not available. Please use direct verse lookup (e.g., John 3:16).",
            "data": {"verses": [], "total": 0}
        }, status=501)


class ToggleMemoryVerseView(LoginRequiredMixin, FaithRequiredMixin, View):
    """
    Toggle a saved verse's memory verse status.

    When marked as memory verse, ensures only one verse is marked at a time.
    Memory verse displays prominently on the Dashboard.
    """

    def post(self, request, pk):
        verse = get_object_or_404(
            SavedVerse.objects.filter(user=request.user),
            pk=pk
        )

        # Toggle the status
        if verse.is_memory_verse:
            # Unmarking as memory verse
            verse.is_memory_verse = False
            verse.save(update_fields=["is_memory_verse", "updated_at"])
            messages.success(request, f'"{verse.reference}" is no longer your memory verse.')
        else:
            # Clear any existing memory verse first (only one at a time)
            SavedVerse.objects.filter(user=request.user, is_memory_verse=True).update(
                is_memory_verse=False
            )
            # Mark this one as the memory verse
            verse.is_memory_verse = True
            verse.save(update_fields=["is_memory_verse", "updated_at"])
            messages.success(request, f'"{verse.reference}" is now your memory verse!')

        # Redirect back to referrer or scripture list
        referer = request.META.get('HTTP_REFERER')
        if referer:
            return redirect(referer)
        return redirect("faith:scripture_list")


# =============================================================================
# READING PLAN VIEWS
# =============================================================================


class ReadingPlanListView(HelpContextMixin, LoginRequiredMixin, FaithRequiredMixin, TemplateView):
    """
    Browse available reading plans and view active plans.

    Shows featured plans, user's active plans, and completed plans.
    Plans with allowed_emails restrictions are only shown to authorized users.
    Plans are grouped by source and series.
    """

    template_name = "faith/reading_plans/list.html"
    help_context_id = "FAITH_READING_PLANS"

    def get_accessible_plans(self, user):
        """
        Return QuerySet of plans the user can access.
        Plans with empty allowed_emails are public.
        Plans with allowed_emails only show to users in that list.
        """
        from django.db.models import Q

        return ReadingPlanTemplate.objects.filter(
            Q(allowed_emails=[]) | Q(allowed_emails__contains=user.email),
            is_active=True,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Get plans accessible to this user
        accessible_plans = self.get_accessible_plans(user)

        # User's active plans
        context["active_plans"] = UserReadingPlan.objects.filter(
            user=user, plan_status="active"
        ).select_related("template")

        # User's completed plans (for the Completed section at bottom)
        context["completed_plans"] = UserReadingPlan.objects.filter(
            user=user, plan_status="completed"
        ).select_related("template").order_by("-completed_at")

        # Set of completed template IDs - used to exclude from featured and show badge
        completed_template_ids = set(
            UserReadingPlan.objects.filter(
                user=user, plan_status="completed"
            ).values_list("template_id", flat=True)
        )
        context["completed_template_ids"] = completed_template_ids

        # Featured plans - exclude completed ones (they appear in Completed section)
        context["featured_plans"] = accessible_plans.filter(
            is_featured=True
        ).exclude(pk__in=completed_template_ids)

        context["all_plans"] = accessible_plans

        # Filter by topic if requested
        topic = self.request.GET.get("topic")
        if topic:
            context["all_plans"] = context["all_plans"].filter(topics__icontains=topic)
            context["selected_topic"] = topic

        # Get all unique topics for filtering (from accessible plans only)
        topics = set()
        for plan in accessible_plans:
            if plan.topics:
                topics.update(plan.topics)
        context["available_topics"] = sorted(topics)

        # Group plans by source and series for organized display
        # Structure: {source_abbrev: {series_name: [plans], ...}, ...}
        # Completed plans are excluded - they appear in the Completed section
        grouped_plans = {}
        public_plans = []

        for plan in accessible_plans.order_by("source", "series", "series_order"):
            # Note: Completed plans now stay in grouped sections with a "Completed" badge
            # They also appear in the Completed section at the bottom for easy reference

            if plan.source:
                source_key = plan.source_abbreviation or plan.source
                if source_key not in grouped_plans:
                    grouped_plans[source_key] = {
                        "full_name": plan.source,
                        "series": {}
                    }
                series_key = plan.series or "Other"
                if series_key not in grouped_plans[source_key]["series"]:
                    grouped_plans[source_key]["series"][series_key] = []
                grouped_plans[source_key]["series"][series_key].append(plan)
            else:
                public_plans.append(plan)

        context["grouped_plans"] = grouped_plans
        context["public_plans"] = public_plans

        return context


class ReadingPlanDetailView(LoginRequiredMixin, FaithRequiredMixin, DetailView):
    """
    View details of a reading plan template.

    Shows plan description, duration, and option to start.
    """

    model = ReadingPlanTemplate
    template_name = "faith/reading_plans/detail.html"
    context_object_name = "plan"
    slug_url_kwarg = "slug"

    def get_queryset(self):
        return ReadingPlanTemplate.objects.filter(is_active=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Check if user already has this plan active
        context["user_plan"] = UserReadingPlan.objects.filter(
            user=self.request.user,
            template=self.object,
            plan_status="active",
        ).first()

        # Show all days for preview
        context["days"] = self.object.days.all()[:7]  # Preview first week

        return context


class StartReadingPlanView(LoginRequiredMixin, FaithRequiredMixin, View):
    """
    Start a new reading plan.
    """

    def post(self, request, slug):
        template = get_object_or_404(
            ReadingPlanTemplate.objects.filter(is_active=True),
            slug=slug
        )

        # Check if user already has an active plan for this template
        existing = UserReadingPlan.objects.filter(
            user=request.user,
            template=template,
            plan_status="active",
        ).first()

        if existing:
            messages.info(request, f"You already have '{template.title}' in progress.")
            return redirect("faith:reading_plan_progress", pk=existing.pk)

        # Create new user reading plan
        user_plan = UserReadingPlan.objects.create(
            user=request.user,
            template=template,
            plan_status="active",
        )

        # Optionally set reminder time from form
        reminder_time = request.POST.get("reminder_time")
        if reminder_time:
            try:
                from datetime import datetime
                user_plan.reminder_time = datetime.strptime(reminder_time, "%H:%M").time()
                user_plan.save(update_fields=["reminder_time"])
            except ValueError:
                pass

        # Create progress entries for all days
        for plan_day in template.days.all():
            UserReadingProgress.objects.create(
                user=request.user,
                user_plan=user_plan,
                plan_day=plan_day,
            )

        messages.success(request, f"Started '{template.title}'! Happy reading!")
        return redirect("faith:reading_plan_progress", pk=user_plan.pk)


class ReadingPlanProgressView(LoginRequiredMixin, FaithRequiredMixin, DetailView):
    """
    View progress on a reading plan.

    Shows current day's reading and overall progress.
    """

    model = UserReadingPlan
    template_name = "faith/reading_plans/progress.html"
    context_object_name = "user_plan"

    def get_queryset(self):
        return UserReadingPlan.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_plan = self.object

        # Get current day's reading
        current_day_num = user_plan.current_day
        context["current_day"] = ReadingPlanDay.objects.filter(
            plan=user_plan.template,
            day_number=current_day_num,
        ).first()

        # Get progress for current day
        if context["current_day"]:
            context["current_progress"] = UserReadingProgress.objects.filter(
                user_plan=user_plan,
                plan_day=context["current_day"],
            ).first()

            # Get assessments for current day with user responses
            assessments = context["current_day"].assessments.all()
            assessments_with_responses = []
            for assessment in assessments:
                user_response = UserAssessmentResponse.objects.filter(
                    user=self.request.user,
                    assessment=assessment,
                    user_plan=user_plan,
                ).first()
                assessments_with_responses.append({
                    "assessment": assessment,
                    "user_response": user_response,
                })
            context["assessments"] = assessments_with_responses

        # Get all progress entries
        context["all_progress"] = user_plan.day_completions.select_related(
            "plan_day"
        ).order_by("plan_day__day_number")

        # User's default Bible translation for scripture lookups
        context["default_translation"] = self.request.user.preferences.default_bible_translation

        # User's reading plan difficulty level preference
        context["reading_difficulty"] = self.request.user.preferences.reading_plan_difficulty
        context["difficulty_choices"] = [
            ("beginner", "Beginner"),
            ("intermediate", "Intermediate"),
            ("advanced", "Advanced"),
        ]

        # Check if this is a Gospel plan (Matthew, Mark, Luke, John)
        # Only Gospel plans show the difficulty selector per user request
        context["is_gospel_plan"] = user_plan.template.source == "The Four Gospels"

        return context


class MarkDayCompleteView(LoginRequiredMixin, FaithRequiredMixin, View):
    """
    Mark a reading plan day as complete.
    """

    def post(self, request, pk, day_pk):
        user_plan = get_object_or_404(
            UserReadingPlan.objects.filter(user=request.user),
            pk=pk
        )
        progress = get_object_or_404(
            UserReadingProgress.objects.filter(user_plan=user_plan),
            plan_day__pk=day_pk
        )

        # Save any notes first (must save separately since mark_complete uses update_fields)
        notes = request.POST.get("notes", "")
        if notes != progress.notes:
            progress.notes = notes
            progress.save(update_fields=["notes", "updated_at"])

        progress.mark_complete()

        messages.success(request, f"Day {progress.plan_day.day_number} complete!")

        # Check if plan is now complete
        if user_plan.is_complete:
            messages.success(
                request,
                f"Congratulations! You've completed '{user_plan.template.title}'!"
            )

        return redirect("faith:reading_plan_progress", pk=pk)


class PauseReadingPlanView(LoginRequiredMixin, FaithRequiredMixin, View):
    """
    Pause a reading plan.
    """

    def post(self, request, pk):
        user_plan = get_object_or_404(
            UserReadingPlan.objects.filter(user=request.user, plan_status="active"),
            pk=pk
        )
        user_plan.plan_status = "paused"
        user_plan.save(update_fields=["plan_status", "updated_at"])
        messages.info(request, f"'{user_plan.template.title}' has been paused.")
        return redirect("faith:reading_plans")


class ResumeReadingPlanView(LoginRequiredMixin, FaithRequiredMixin, View):
    """
    Resume a paused reading plan.
    """

    def post(self, request, pk):
        user_plan = get_object_or_404(
            UserReadingPlan.objects.filter(user=request.user, plan_status="paused"),
            pk=pk
        )
        user_plan.plan_status = "active"
        user_plan.save(update_fields=["plan_status", "updated_at"])
        messages.success(request, f"Welcome back! '{user_plan.template.title}' resumed.")
        return redirect("faith:reading_plan_progress", pk=pk)


class AbandonReadingPlanView(LoginRequiredMixin, FaithRequiredMixin, View):
    """
    Abandon a reading plan.
    """

    def post(self, request, pk):
        user_plan = get_object_or_404(
            UserReadingPlan.objects.filter(user=request.user),
            pk=pk
        )
        user_plan.plan_status = "abandoned"
        user_plan.save(update_fields=["plan_status", "updated_at"])
        messages.info(request, f"'{user_plan.template.title}' has been removed from your active plans.")
        return redirect("faith:reading_plans")


class UpdateReadingDifficultyView(LoginRequiredMixin, FaithRequiredMixin, View):
    """
    Update user's reading plan difficulty preference via AJAX.

    Expects POST with JSON body:
    {
        "difficulty": "beginner" | "intermediate" | "advanced"
    }
    """

    def post(self, request):
        import json
        try:
            data = json.loads(request.body)
            difficulty = data.get("difficulty")

            valid_choices = ["beginner", "intermediate", "advanced"]
            if difficulty not in valid_choices:
                return JsonResponse(
                    {"success": False, "error": "Invalid difficulty level"},
                    status=400
                )

            prefs = request.user.preferences
            prefs.reading_plan_difficulty = difficulty
            prefs.save(update_fields=["reading_plan_difficulty"])

            return JsonResponse({"success": True, "difficulty": difficulty})
        except json.JSONDecodeError:
            return JsonResponse(
                {"success": False, "error": "Invalid JSON"},
                status=400
            )


class DeleteReadingPlanView(LoginRequiredMixin, FaithRequiredMixin, View):
    """
    Delete a completed reading plan.

    Uses soft delete to remove the plan from the user's history.
    Only allows deletion of completed plans.
    """

    def post(self, request, pk):
        user_plan = get_object_or_404(
            UserReadingPlan.objects.filter(user=request.user, plan_status="completed"),
            pk=pk
        )
        plan_title = user_plan.template.title
        user_plan.soft_delete()
        messages.success(request, f"'{plan_title}' has been removed from your completed plans.")
        return redirect("faith:reading_plans")


class SaveAssessmentResponseView(LoginRequiredMixin, FaithRequiredMixin, View):
    """
    Save user's assessment responses via AJAX.

    Expects POST with JSON body:
    {
        "responses": {"1": 3, "2": 5, ...}
    }
    """

    def post(self, request, plan_pk, assessment_pk):
        try:
            # Validate user has this reading plan
            try:
                user_plan = UserReadingPlan.objects.get(
                    user=request.user,
                    pk=plan_pk
                )
            except UserReadingPlan.DoesNotExist:
                return JsonResponse({"error": "Reading plan not found"}, status=404)

            # Validate assessment exists
            try:
                assessment = ReadingPlanAssessment.objects.get(pk=assessment_pk)
            except ReadingPlanAssessment.DoesNotExist:
                return JsonResponse({"error": "Assessment not found"}, status=404)

            try:
                data = json.loads(request.body)
                responses = data.get("responses", {})
            except json.JSONDecodeError:
                return JsonResponse({"error": "Invalid JSON"}, status=400)

            # Get or create the response object
            user_response, created = UserAssessmentResponse.objects.get_or_create(
                user=request.user,
                assessment=assessment,
                user_plan=user_plan,
                defaults={"responses": responses}
            )

            if not created:
                user_response.responses = responses
                user_response.save()

            # Get interpretation
            interpretation = user_response.interpretation

            return JsonResponse({
                "success": True,
                "total_score": user_response.total_score,
                "max_score": assessment.max_possible_score,
                "interpretation": interpretation,
            })
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.exception("Error saving assessment response")
            return JsonResponse({"error": str(e)}, status=500)


# =============================================================================
# BIBLE STUDY TOOLS VIEWS - Highlights
# =============================================================================


class HighlightListView(LoginRequiredMixin, FaithRequiredMixin, ListView):
    """
    List all Bible highlights for the user.
    """

    model = BibleHighlight
    template_name = "faith/study_tools/highlight_list.html"
    context_object_name = "highlights"
    paginate_by = 50

    def get_queryset(self):
        queryset = BibleHighlight.objects.filter(user=self.request.user)

        # Filter by color
        color = self.request.GET.get("color")
        if color:
            queryset = queryset.filter(color=color)

        # Filter by book
        book = self.request.GET.get("book")
        if book:
            queryset = queryset.filter(book_name=book)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_highlights = BibleHighlight.objects.filter(user=self.request.user)

        # Get unique books for filtering
        context["available_books"] = sorted(
            set(user_highlights.values_list("book_name", flat=True))
        )
        context["color_choices"] = BibleHighlight.COLOR_CHOICES
        context["selected_color"] = self.request.GET.get("color", "")
        context["selected_book"] = self.request.GET.get("book", "")
        return context


class HighlightCreateView(LoginRequiredMixin, FaithRequiredMixin, CreateView):
    """
    Create a new Bible highlight.
    """

    model = BibleHighlight
    form_class = BibleHighlightForm
    template_name = "faith/study_tools/highlight_form.html"
    success_url = reverse_lazy("faith:highlight_list")

    def form_valid(self, form):
        form.instance.user = self.request.user

        # Parse the reference to extract book info
        reference = form.cleaned_data["reference"]
        book_info = self._parse_reference(reference)
        form.instance.book_name = book_info["book_name"]
        form.instance.book_order = book_info["book_order"]
        form.instance.chapter = book_info["chapter"]
        form.instance.verse_start = book_info["verse_start"]
        form.instance.verse_end = book_info.get("verse_end")

        messages.success(self.request, "Highlight saved!")
        return super().form_valid(form)

    def _parse_reference(self, reference):
        """Parse a reference like 'John 3:16-17' into components."""
        from apps.faith.views import ScriptureSaveView

        # Default values
        result = {
            "book_name": reference.split()[0] if reference else "Unknown",
            "book_order": 1,
            "chapter": 1,
            "verse_start": 1,
            "verse_end": None,
        }

        # Try to parse more accurately
        import re
        # Match patterns like "1 John 3:16-17" or "Genesis 1:1"
        match = re.match(r"^(\d?\s?[A-Za-z]+)\s+(\d+):(\d+)(?:-(\d+))?", reference)
        if match:
            book_name = match.group(1).strip()
            result["book_name"] = book_name
            result["book_order"] = ScriptureSaveView.BOOK_ORDER.get(book_name, 1)
            result["chapter"] = int(match.group(2))
            result["verse_start"] = int(match.group(3))
            if match.group(4):
                result["verse_end"] = int(match.group(4))

        return result


class HighlightDeleteView(LoginRequiredMixin, FaithRequiredMixin, View):
    """
    Delete a Bible highlight.
    """

    def post(self, request, pk):
        highlight = get_object_or_404(
            BibleHighlight.objects.filter(user=request.user),
            pk=pk
        )
        highlight.soft_delete()
        messages.success(request, "Highlight removed.")
        return redirect("faith:highlight_list")


# =============================================================================
# BIBLE STUDY TOOLS VIEWS - Bookmarks
# =============================================================================


class BookmarkListView(LoginRequiredMixin, FaithRequiredMixin, ListView):
    """
    List all Bible bookmarks for the user.
    """

    model = BibleBookmark
    template_name = "faith/study_tools/bookmark_list.html"
    context_object_name = "bookmarks"
    paginate_by = 50

    def get_queryset(self):
        return BibleBookmark.objects.filter(user=self.request.user)


class BookmarkCreateView(LoginRequiredMixin, FaithRequiredMixin, CreateView):
    """
    Create a new Bible bookmark.
    """

    model = BibleBookmark
    form_class = BibleBookmarkForm
    template_name = "faith/study_tools/bookmark_form.html"
    success_url = reverse_lazy("faith:bookmark_list")

    def form_valid(self, form):
        form.instance.user = self.request.user

        # Parse the reference
        reference = form.cleaned_data["reference"]
        book_info = self._parse_reference(reference)
        form.instance.book_name = book_info["book_name"]
        form.instance.book_order = book_info["book_order"]
        form.instance.chapter = book_info["chapter"]
        form.instance.verse = book_info.get("verse")

        messages.success(self.request, "Bookmark saved!")
        return super().form_valid(form)

    def _parse_reference(self, reference):
        """Parse a reference like 'John 3' or 'John 3:16' into components."""
        from apps.faith.views import ScriptureSaveView

        result = {
            "book_name": reference.split()[0] if reference else "Unknown",
            "book_order": 1,
            "chapter": 1,
            "verse": None,
        }

        import re
        # Match "1 John 3:16" or "Genesis 1" (chapter only)
        match = re.match(r"^(\d?\s?[A-Za-z]+)\s+(\d+)(?::(\d+))?", reference)
        if match:
            book_name = match.group(1).strip()
            result["book_name"] = book_name
            result["book_order"] = ScriptureSaveView.BOOK_ORDER.get(book_name, 1)
            result["chapter"] = int(match.group(2))
            if match.group(3):
                result["verse"] = int(match.group(3))

        return result


class BookmarkDeleteView(LoginRequiredMixin, FaithRequiredMixin, View):
    """
    Delete a Bible bookmark.
    """

    def post(self, request, pk):
        bookmark = get_object_or_404(
            BibleBookmark.objects.filter(user=request.user),
            pk=pk
        )
        bookmark.soft_delete()
        messages.success(request, "Bookmark removed.")
        return redirect("faith:bookmark_list")


# =============================================================================
# BIBLE STUDY TOOLS VIEWS - Study Notes
# =============================================================================


class StudyNoteListView(LoginRequiredMixin, FaithRequiredMixin, ListView):
    """
    List all Bible study notes for the user.
    """

    model = BibleStudyNote
    template_name = "faith/study_tools/note_list.html"
    context_object_name = "notes"
    paginate_by = 20

    def get_queryset(self):
        queryset = BibleStudyNote.objects.filter(user=self.request.user)

        # Filter by tag
        tag = self.request.GET.get("tag")
        if tag:
            queryset = queryset.filter(tags__icontains=tag)

        # Filter by book
        book = self.request.GET.get("book")
        if book:
            queryset = queryset.filter(book_name=book)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_notes = BibleStudyNote.objects.filter(user=self.request.user)

        # Get unique tags and books for filtering
        tags = set()
        for note in user_notes:
            tags.update(note.tags)
        context["available_tags"] = sorted(tags)
        context["available_books"] = sorted(
            set(user_notes.values_list("book_name", flat=True))
        )
        context["selected_tag"] = self.request.GET.get("tag", "")
        context["selected_book"] = self.request.GET.get("book", "")
        return context


class StudyNoteDetailView(LoginRequiredMixin, FaithRequiredMixin, DetailView):
    """
    View a single study note.
    """

    model = BibleStudyNote
    template_name = "faith/study_tools/note_detail.html"
    context_object_name = "note"

    def get_queryset(self):
        return BibleStudyNote.objects.filter(user=self.request.user)


class StudyNoteCreateView(LoginRequiredMixin, FaithRequiredMixin, CreateView):
    """
    Create a new Bible study note.
    """

    model = BibleStudyNote
    form_class = BibleStudyNoteForm
    template_name = "faith/study_tools/note_form.html"
    success_url = reverse_lazy("faith:study_note_list")

    def form_valid(self, form):
        form.instance.user = self.request.user

        # Parse the reference
        reference = form.cleaned_data["reference"]
        book_info = self._parse_reference(reference)
        form.instance.book_name = book_info["book_name"]
        form.instance.book_order = book_info["book_order"]
        form.instance.chapter = book_info["chapter"]
        form.instance.verse_start = book_info["verse_start"]
        form.instance.verse_end = book_info.get("verse_end")

        messages.success(self.request, "Study note saved!")
        return super().form_valid(form)

    def _parse_reference(self, reference):
        """Parse a reference like 'John 3:16-21' into components."""
        from apps.faith.views import ScriptureSaveView

        result = {
            "book_name": reference.split()[0] if reference else "Unknown",
            "book_order": 1,
            "chapter": 1,
            "verse_start": 1,
            "verse_end": None,
        }

        import re
        match = re.match(r"^(\d?\s?[A-Za-z]+)\s+(\d+):(\d+)(?:-(\d+))?", reference)
        if match:
            book_name = match.group(1).strip()
            result["book_name"] = book_name
            result["book_order"] = ScriptureSaveView.BOOK_ORDER.get(book_name, 1)
            result["chapter"] = int(match.group(2))
            result["verse_start"] = int(match.group(3))
            if match.group(4):
                result["verse_end"] = int(match.group(4))

        return result


class StudyNoteUpdateView(LoginRequiredMixin, FaithRequiredMixin, UpdateView):
    """
    Edit a Bible study note.
    """

    model = BibleStudyNote
    form_class = BibleStudyNoteForm
    template_name = "faith/study_tools/note_form.html"

    def get_queryset(self):
        return BibleStudyNote.objects.filter(user=self.request.user)

    def get_success_url(self):
        return reverse_lazy("faith:study_note_detail", kwargs={"pk": self.object.pk})

    def form_valid(self, form):
        messages.success(self.request, "Study note updated!")
        return super().form_valid(form)


class StudyNoteDeleteView(LoginRequiredMixin, FaithRequiredMixin, View):
    """
    Delete a Bible study note.
    """

    def post(self, request, pk):
        note = get_object_or_404(
            BibleStudyNote.objects.filter(user=request.user),
            pk=pk
        )
        note.soft_delete()
        messages.success(request, "Study note deleted.")
        return redirect("faith:study_note_list")


# =============================================================================
# STUDY TOOLS COMBINED VIEW
# =============================================================================


class StudyToolsHomeView(HelpContextMixin, LoginRequiredMixin, FaithRequiredMixin, TemplateView):
    """
    Combined view of all Bible study tools.

    Shows recent highlights, bookmarks, and notes in one place.
    """

    template_name = "faith/study_tools/home.html"
    help_context_id = "FAITH_STUDY_TOOLS"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Recent highlights
        context["recent_highlights"] = BibleHighlight.objects.filter(
            user=user
        ).order_by("-created_at")[:10]

        # Recent bookmarks
        context["recent_bookmarks"] = BibleBookmark.objects.filter(
            user=user
        ).order_by("-created_at")[:10]

        # Recent study notes
        context["recent_notes"] = BibleStudyNote.objects.filter(
            user=user
        ).order_by("-created_at")[:5]

        # Counts
        context["highlight_count"] = BibleHighlight.objects.filter(user=user).count()
        context["bookmark_count"] = BibleBookmark.objects.filter(user=user).count()
        context["note_count"] = BibleStudyNote.objects.filter(user=user).count()

        return context


# =============================================================================
# Bulk Delete Views
# =============================================================================

class BulkDeletePrayersView(LoginRequiredMixin, View):
    """Bulk delete prayer requests."""

    def post(self, request):
        try:
            data = json.loads(request.body)
            ids = data.get('ids', [])
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

        if not ids:
            return JsonResponse({'success': False, 'error': 'No items selected'}, status=400)

        entries = PrayerRequest.objects.filter(user=request.user, pk__in=ids)
        count = entries.count()

        if count == 0:
            return JsonResponse({'success': False, 'error': 'No entries found'}, status=404)

        for entry in entries:
            entry.soft_delete()

        return JsonResponse({
            'success': True,
            'message': f'{count} prayer{"" if count == 1 else "s"} deleted',
            'count': count
        })


class BulkDeleteSavedVersesView(LoginRequiredMixin, View):
    """Bulk delete saved verses."""

    def post(self, request):
        try:
            data = json.loads(request.body)
            ids = data.get('ids', [])
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

        if not ids:
            return JsonResponse({'success': False, 'error': 'No items selected'}, status=400)

        entries = SavedVerse.objects.filter(user=request.user, pk__in=ids)
        count = entries.count()

        if count == 0:
            return JsonResponse({'success': False, 'error': 'No entries found'}, status=404)

        for entry in entries:
            entry.delete()

        return JsonResponse({
            'success': True,
            'message': f'{count} verse{"" if count == 1 else "s"} deleted',
            'count': count
        })


class BulkDeleteHighlightsView(LoginRequiredMixin, View):
    """Bulk delete highlights."""

    def post(self, request):
        try:
            data = json.loads(request.body)
            ids = data.get('ids', [])
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

        if not ids:
            return JsonResponse({'success': False, 'error': 'No items selected'}, status=400)

        entries = BibleHighlight.objects.filter(user=request.user, pk__in=ids)
        count = entries.count()

        if count == 0:
            return JsonResponse({'success': False, 'error': 'No entries found'}, status=404)

        entries.delete()

        return JsonResponse({
            'success': True,
            'message': f'{count} highlight{"" if count == 1 else "s"} deleted',
            'count': count
        })


class BulkDeleteBookmarksView(LoginRequiredMixin, View):
    """Bulk delete bookmarks."""

    def post(self, request):
        try:
            data = json.loads(request.body)
            ids = data.get('ids', [])
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

        if not ids:
            return JsonResponse({'success': False, 'error': 'No items selected'}, status=400)

        entries = BibleBookmark.objects.filter(user=request.user, pk__in=ids)
        count = entries.count()

        if count == 0:
            return JsonResponse({'success': False, 'error': 'No entries found'}, status=404)

        entries.delete()

        return JsonResponse({
            'success': True,
            'message': f'{count} bookmark{"" if count == 1 else "s"} deleted',
            'count': count
        })


class BulkDeleteStudyNotesView(LoginRequiredMixin, View):
    """Bulk delete study notes."""

    def post(self, request):
        try:
            data = json.loads(request.body)
            ids = data.get('ids', [])
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

        if not ids:
            return JsonResponse({'success': False, 'error': 'No items selected'}, status=400)

        entries = BibleStudyNote.objects.filter(user=request.user, pk__in=ids)
        count = entries.count()

        if count == 0:
            return JsonResponse({'success': False, 'error': 'No entries found'}, status=404)

        for entry in entries:
            entry.delete()

        return JsonResponse({
            'success': True,
            'message': f'{count} note{"" if count == 1 else "s"} deleted',
            'count': count
        })