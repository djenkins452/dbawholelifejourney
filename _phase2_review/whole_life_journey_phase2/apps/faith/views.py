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
from apps.journal.models import JournalEntry

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


class FaithHomeView(LoginRequiredMixin, FaithRequiredMixin, TemplateView):
    """
    Faith module home - overview of spiritual journey.
    """

    template_name = "faith/home.html"

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
        today = date.today()
        
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
        today = date.today()
        
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
    Browse all available Scripture verses.
    """

    model = ScriptureVerse
    template_name = "faith/scripture_list.html"
    context_object_name = "verses"
    paginate_by = 20

    def get_queryset(self):
        queryset = ScriptureVerse.objects.filter(is_active=True)
        
        # Filter by theme
        theme = self.request.GET.get("theme")
        if theme:
            queryset = queryset.filter(themes__contains=[theme])
        
        # Filter by book
        book = self.request.GET.get("book")
        if book:
            queryset = queryset.filter(book_name=book)
        
        return queryset

    def get_context_data(self, **kwargs):
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
        return context


class ScriptureDetailView(LoginRequiredMixin, FaithRequiredMixin, DetailView):
    """
    View a single Scripture verse with context.
    """

    model = ScriptureVerse
    template_name = "faith/scripture_detail.html"
    context_object_name = "verse"


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
