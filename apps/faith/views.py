"""
Faith Views - Scripture, prayers, and spiritual growth.
"""

import random
from datetime import date

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
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

from .forms import FaithMilestoneForm, PrayerRequestForm
from .models import DailyVerse, FaithMilestone, PrayerRequest, ScriptureVerse


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
    Browse all available Scripture verses with Bible API lookup.
    """

    model = ScriptureVerse
    template_name = "faith/scripture_list.html"
    context_object_name = "verses"
    paginate_by = 20

    def get_queryset(self):
        queryset = ScriptureVerse.objects.filter(is_active=True)
        
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
        from django.conf import settings
        context = super().get_context_data(**kwargs)
        # Get unique themes for filtering
        all_verses = ScriptureVerse.objects.filter(is_active=True)
        themes = set()
        books = set()
        for verse in all_verses:
            themes.update(verse.themes)
            books.add(verse.book_name)
        context["available_themes"] = sorted(themes)
        context["available_books"] = sorted(books)
        context["selected_theme"] = self.request.GET.get("theme", "")
        context["selected_book"] = self.request.GET.get("book", "")
        # Add API key for Bible API
        context["api_key"] = getattr(settings, 'BIBLE_API_KEY', '')
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
    Save a looked-up Scripture verse to the library.
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
        
        # Create the verse
        verse = ScriptureVerse.objects.create(
            reference=reference,
            text=text,
            book_name=book_name,
            book_order=book_order,
            chapter=chapter_int,
            verse_start=verse_start_int,
            verse_end=verse_end_int,
            translation=translation_abbrev,
            themes=themes,
            contexts=[],  # Empty contexts list
            is_active=True,
        )
        
        messages.success(request, f'"{reference}" saved to your Scripture library.')
        return redirect('faith:scripture_list')


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