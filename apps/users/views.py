"""
Users Views - Profile, preferences, and user management.
"""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import TemplateView, UpdateView, View

from .forms import ProfileForm, PreferencesForm
from .models import TermsAcceptance, UserPreferences


class ProfileView(LoginRequiredMixin, TemplateView):
    """
    Display user profile information.
    """

    template_name = "users/profile.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        # Get stats for the profile page
        from apps.journal.models import JournalEntry
        context["journal_count"] = JournalEntry.objects.filter(user=user).count()
        
        # Faith stats (if enabled)
        if user.preferences.faith_enabled:
            from apps.faith.models import PrayerRequest
            context["prayer_count"] = PrayerRequest.objects.filter(user=user).count()
        
        # Health stats
        from apps.health.models import WeightEntry, HeartRateEntry, GlucoseEntry
        weight_count = WeightEntry.objects.filter(user=user).count()
        hr_count = HeartRateEntry.objects.filter(user=user).count()
        glucose_count = GlucoseEntry.objects.filter(user=user).count()
        context["weight_count"] = weight_count + hr_count + glucose_count
        
        return context


class ProfileEditView(LoginRequiredMixin, UpdateView):
    """
    Edit user profile (name, email, avatar).
    """

    template_name = "users/profile_edit.html"
    form_class = ProfileForm
    success_url = reverse_lazy("users:profile")

    def get_object(self):
        return self.request.user

    def form_valid(self, form):
        messages.success(self.request, "Profile updated successfully.")
        return super().form_valid(form)


class PreferencesView(LoginRequiredMixin, UpdateView):
    """
    Edit user preferences (theme, Faith toggle, AI toggle, location).
    """

    template_name = "users/preferences.html"
    form_class = PreferencesForm
    success_url = reverse_lazy("users:preferences")

    def get_object(self):
        return self.request.user.preferences

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Google Calendar integration status
        try:
            from apps.life.models import GoogleCalendarCredential
            credential = self.request.user.google_calendar_credential
            context['google_calendar_connected'] = credential.is_connected
            context['google_calendar_name'] = credential.selected_calendar_name
        except:
            context['google_calendar_connected'] = False
            context['google_calendar_name'] = None

        # Bible API key for faith settings
        context['api_key'] = getattr(settings, 'BIBLE_API_KEY', '')

        return context

    def form_valid(self, form):
        messages.success(self.request, "Preferences saved successfully.")
        return super().form_valid(form)


class ThemeSelectionView(LoginRequiredMixin, TemplateView):
    """
    Theme selection page with visual previews.
    
    This is a more visual interface for choosing a theme,
    separate from the full preferences form.
    """

    template_name = "users/theme_selection.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["themes"] = settings.WLJ_SETTINGS["THEMES"]
        context["current_theme"] = self.request.user.preferences.theme
        return context

    def post(self, request, *args, **kwargs):
        theme = request.POST.get("theme")
        if theme in settings.WLJ_SETTINGS["THEMES"]:
            prefs = request.user.preferences
            prefs.theme = theme
            prefs.save(update_fields=["theme", "updated_at"])
            messages.success(request, f"Theme changed to {settings.WLJ_SETTINGS['THEMES'][theme]['name']}.")
        return redirect("users:preferences")


class AcceptTermsView(LoginRequiredMixin, TemplateView):
    """
    Terms of Service acceptance page.
    
    Users must accept the current terms to continue using the app.
    Creates an audit record of the acceptance.
    """

    template_name = "users/accept_terms.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["terms_version"] = settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0")
        return context

    def post(self, request, *args, **kwargs):
        if request.POST.get("accept") == "yes":
            # Create acceptance record
            TermsAcceptance.objects.create(
                user=request.user,
                terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
                ip_address=self.get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
            messages.success(request, "Thank you for accepting the Terms of Service.")
            
            # Redirect to onboarding if first time, otherwise dashboard
            if not request.user.preferences.has_completed_onboarding:
                return redirect("users:onboarding")
            return redirect("dashboard:home")
        
        messages.error(request, "You must accept the Terms of Service to continue.")
        return self.get(request, *args, **kwargs)

    def get_client_ip(self, request):
        """Get the client IP address from the request."""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR")


class OnboardingView(LoginRequiredMixin, TemplateView):
    """
    Guided onboarding for new users.
    
    A simple walkthrough introducing key features:
    - Dashboard
    - Journal
    - Preferences (theme, Faith toggle)
    """

    template_name = "users/onboarding.html"


class CompleteOnboardingView(LoginRequiredMixin, View):
    """
    Mark onboarding as complete and redirect to dashboard.
    """

    def post(self, request, *args, **kwargs):
        prefs = request.user.preferences
        prefs.has_completed_onboarding = True
        prefs.save(update_fields=["has_completed_onboarding", "updated_at"])
        messages.success(request, "Welcome to Whole Life Journey!")
        return redirect("dashboard:home")

    def get(self, request, *args, **kwargs):
        # If accessed via GET, just redirect
        return redirect("users:onboarding")
