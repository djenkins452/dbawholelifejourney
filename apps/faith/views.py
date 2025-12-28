"""
Faith Views - Scripture, prayers, and spiritual growth.
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

from apps.core.models import Category
from apps.help.mixins import HelpContextMixin
from apps.journal.models import JournalEntry
from apps.journal.forms import JournalEntryForm

from .forms import FaithMilestoneForm, PrayerRequestForm, SavedVerseForm
from .models import DailyVerse, FaithMilestone, PrayerRequest, SavedVerse, ScriptureVerse

logger = logging.getLogger(__name__)

# Bible API base URL
BIBLE_API_BASE = "https://api.scripture.api.bible/v1"


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