# ==============================================================================
# File: apps/faith/views.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Faith module views for Scripture, prayers, reading plans, and
#              Bible study tools
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2024-01-01
# Last Updated: 2026-01-01
# ==============================================================================
"""
Faith Views - Scripture, prayers, reading plans, and spiritual growth.
"""

import json
import logging
import random
from datetime import date
from urllib.parse import quote

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
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
    ReadingProgressForm,
    SavedVerseForm,
    StartReadingPlanForm,
)
from .models import (
    BibleBookmark,
    BibleHighlight,
    BibleStudyNote,
    DailyVerse,
    FaithMilestone,
    PrayerRequest,
    ReadingPlanDay,
    ReadingPlanTemplate,
    SavedVerse,
    ScriptureVerse,
    UserReadingPlan,
    UserReadingProgress,
)

logger = logging.getLogger(__name__)

# Bible API base URL (api.bible uses rest.api.bible endpoint)
BIBLE_API_BASE = "https://rest.api.bible/v1"


class FaithRequiredMixin(UserPassesTestMixin):
    """
    Mixin to ensure user has Faith module enabled.
    
    Redirects to preferences if Faith is not enabled.
    """

    def test_func(self):
        return self.request.user.preferences.faith_enabled

    def handle_no_permission(self):
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
        
        return context

    def get_todays_verse(self):
        """Get today's verse, or a random one if none assigned."""
        from apps.core.utils import get_user_today
        today = get_user_today(self.request.user)
        
        # Try to get assigned verse for today
        try:
            daily = DailyVerse.objects.get(date=today)
            return {
                "verse": daily.verse,
                "prompt": daily.reflection_prompt,
            }
        except DailyVerse.DoesNotExist:
            pass
        
        # Fall back to random verse
        verses = ScriptureVerse.objects.filter(is_active=True)
        if verses.exists():
            return {
                "verse": random.choice(list(verses)),
                "prompt": "",
            }
        
        return None


class TodaysVerseView(LoginRequiredMixin, FaithRequiredMixin, TemplateView):
    """
    Display today's Scripture verse with reflection.
    """

    template_name = "faith/todays_verse.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.core.utils import get_user_today
        today = get_user_today(self.request.user)

        try:
            daily = DailyVerse.objects.get(date=today)
            context["daily_verse"] = daily
            context["verse"] = daily.verse
        except DailyVerse.DoesNotExist:
            # Random verse
            verses = ScriptureVerse.objects.filter(is_active=True)
            if verses.exists():
                context["verse"] = random.choice(list(verses))

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
    Mixin providing Bible API proxy functionality.

    Security: Keeps Bible API key server-side, never exposed to frontend.
    """

    def get_api_key(self):
        """Get the Bible API key from settings."""
        return getattr(settings, 'BIBLE_API_KEY', '')

    def is_api_configured(self):
        """Check if Bible API is configured."""
        return bool(self.get_api_key())

    def make_api_request(self, endpoint, params=None):
        """
        Make a request to the Bible API.

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
        headers = {"api-key": api_key}

        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            return True, response.json()
        except requests.exceptions.Timeout:
            logger.warning(f"Bible API timeout: {endpoint}")
            return False, {"error": "Request timed out"}
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                logger.error("Bible API: Invalid or expired API key")
                return False, {"error": "Bible API key is invalid or expired. Please contact the administrator."}
            logger.error(f"Bible API HTTP error: {e}")
            return False, {"error": f"Bible API error: {e.response.status_code}"}
        except requests.exceptions.RequestException as e:
            logger.error(f"Bible API error: {e}")
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
    Proxy for Bible API /bibles endpoint.

    Returns list of available Bible translations.
    """

    def get(self, request):
        if not self.is_api_configured():
            return JsonResponse(
                {"error": "Bible API is not configured"},
                status=503
            )

        success, data = self.make_api_request("/bibles")
        if success:
            return JsonResponse(data)
        return JsonResponse(data, status=500)


class BibleAPIBooksView(LoginRequiredMixin, FaithRequiredMixin, BibleAPIProxyMixin, View):
    """
    Proxy for Bible API /bibles/{bibleId}/books endpoint.

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
            return JsonResponse(data)
        return JsonResponse(data, status=500)


class BibleAPIChaptersView(LoginRequiredMixin, FaithRequiredMixin, BibleAPIProxyMixin, View):
    """
    Proxy for Bible API /bibles/{bibleId}/books/{bookId}/chapters endpoint.

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
            return JsonResponse(data)
        return JsonResponse(data, status=500)


class BibleAPIVersesView(LoginRequiredMixin, FaithRequiredMixin, BibleAPIProxyMixin, View):
    """
    Proxy for Bible API /bibles/{bibleId}/chapters/{chapterId}/verses endpoint.

    Returns list of verses in a specific chapter.
    """

    def get(self, request, bible_id, chapter_id):
        if not self.is_api_configured():
            return JsonResponse(
                {"error": "Bible API is not configured"},
                status=503
            )

        # Sanitize inputs
        safe_bible_id = quote(bible_id, safe='')
        safe_chapter_id = quote(chapter_id, safe='')
        success, data = self.make_api_request(
            f"/bibles/{safe_bible_id}/chapters/{safe_chapter_id}/verses"
        )
        if success:
            return JsonResponse(data)
        return JsonResponse(data, status=500)


class BibleAPIVerseView(LoginRequiredMixin, FaithRequiredMixin, BibleAPIProxyMixin, View):
    """
    Proxy for Bible API /bibles/{bibleId}/verses/{verseId} endpoint.

    Returns a specific verse or verse range.
    """

    def get(self, request, bible_id, verse_id):
        if not self.is_api_configured():
            return JsonResponse(
                {"error": "Bible API is not configured"},
                status=503
            )

        # Sanitize inputs
        safe_bible_id = quote(bible_id, safe='')
        safe_verse_id = quote(verse_id, safe='')

        # Pass through query params for content options
        params = {}
        if request.GET.get('content-type'):
            params['content-type'] = request.GET['content-type']
        if request.GET.get('include-notes'):
            params['include-notes'] = request.GET['include-notes']
        if request.GET.get('include-titles'):
            params['include-titles'] = request.GET['include-titles']
        if request.GET.get('include-chapter-numbers'):
            params['include-chapter-numbers'] = request.GET['include-chapter-numbers']
        if request.GET.get('include-verse-numbers'):
            params['include-verse-numbers'] = request.GET['include-verse-numbers']

        success, data = self.make_api_request(
            f"/bibles/{safe_bible_id}/verses/{safe_verse_id}",
            params=params if params else None
        )
        if success:
            return JsonResponse(data)
        return JsonResponse(data, status=500)


class BibleAPIPassageView(LoginRequiredMixin, FaithRequiredMixin, BibleAPIProxyMixin, View):
    """
    Proxy for Bible API /bibles/{bibleId}/passages/{passageId} endpoint.

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
        safe_passage_id = quote(passage_id, safe='')

        # Pass through query params
        params = {}
        if request.GET.get('content-type'):
            params['content-type'] = request.GET['content-type']
        if request.GET.get('include-notes'):
            params['include-notes'] = request.GET['include-notes']
        if request.GET.get('include-titles'):
            params['include-titles'] = request.GET['include-titles']
        if request.GET.get('include-chapter-numbers'):
            params['include-chapter-numbers'] = request.GET['include-chapter-numbers']
        if request.GET.get('include-verse-numbers'):
            params['include-verse-numbers'] = request.GET['include-verse-numbers']

        success, data = self.make_api_request(
            f"/bibles/{safe_bible_id}/passages/{safe_passage_id}",
            params=params if params else None
        )
        if success:
            return JsonResponse(data)
        return JsonResponse(data, status=500)


class BibleAPISearchView(LoginRequiredMixin, FaithRequiredMixin, BibleAPIProxyMixin, View):
    """
    Proxy for Bible API /bibles/{bibleId}/search endpoint.

    Searches for text within a Bible translation.
    """

    def get(self, request, bible_id):
        if not self.is_api_configured():
            return JsonResponse(
                {"error": "Bible API is not configured"},
                status=503
            )

        query = request.GET.get('query', '')
        if not query:
            return JsonResponse(
                {"error": "Search query is required"},
                status=400
            )

        # Sanitize bible_id
        safe_bible_id = quote(bible_id, safe='')

        params = {'query': query}
        if request.GET.get('limit'):
            params['limit'] = request.GET['limit']
        if request.GET.get('offset'):
            params['offset'] = request.GET['offset']

        success, data = self.make_api_request(
            f"/bibles/{safe_bible_id}/search",
            params=params
        )
        if success:
            return JsonResponse(data)
        return JsonResponse(data, status=500)


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
    """

    template_name = "faith/reading_plans/list.html"
    help_context_id = "FAITH_READING_PLANS"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Available reading plan templates
        context["featured_plans"] = ReadingPlanTemplate.objects.filter(
            is_active=True, is_featured=True
        )
        context["all_plans"] = ReadingPlanTemplate.objects.filter(
            is_active=True
        )

        # User's active plans
        context["active_plans"] = UserReadingPlan.objects.filter(
            user=user, status="active"
        ).select_related("template")

        # User's completed plans
        context["completed_plans"] = UserReadingPlan.objects.filter(
            user=user, status="completed"
        ).select_related("template")[:5]

        # Filter by topic if requested
        topic = self.request.GET.get("topic")
        if topic:
            context["all_plans"] = context["all_plans"].filter(topics__icontains=topic)
            context["selected_topic"] = topic

        # Get all unique topics for filtering
        topics = set()
        for plan in ReadingPlanTemplate.objects.filter(is_active=True):
            topics.update(plan.topics)
        context["available_topics"] = sorted(topics)

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
            status="active",
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
            status="active",
        ).first()

        if existing:
            messages.info(request, f"You already have '{template.title}' in progress.")
            return redirect("faith:reading_plan_progress", pk=existing.pk)

        # Create new user reading plan
        user_plan = UserReadingPlan.objects.create(
            user=request.user,
            template=template,
            status="active",
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

        # Get all progress entries
        context["all_progress"] = user_plan.day_completions.select_related(
            "plan_day"
        ).order_by("plan_day__day_number")

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

        # Save any notes
        notes = request.POST.get("notes", "")
        progress.notes = notes
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
            UserReadingPlan.objects.filter(user=request.user, status="active"),
            pk=pk
        )
        user_plan.status = "paused"
        user_plan.save(update_fields=["status", "updated_at"])
        messages.info(request, f"'{user_plan.template.title}' has been paused.")
        return redirect("faith:reading_plans")


class ResumeReadingPlanView(LoginRequiredMixin, FaithRequiredMixin, View):
    """
    Resume a paused reading plan.
    """

    def post(self, request, pk):
        user_plan = get_object_or_404(
            UserReadingPlan.objects.filter(user=request.user, status="paused"),
            pk=pk
        )
        user_plan.status = "active"
        user_plan.save(update_fields=["status", "updated_at"])
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
        user_plan.status = "abandoned"
        user_plan.save(update_fields=["status", "updated_at"])
        messages.info(request, f"'{user_plan.template.title}' has been removed from your active plans.")
        return redirect("faith:reading_plans")


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