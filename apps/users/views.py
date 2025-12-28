"""
Users Views - Profile, preferences, and user management.
"""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import TemplateView, UpdateView, View

from apps.help.mixins import HelpContextMixin

from .forms import ProfileForm, PreferencesForm
from .models import TermsAcceptance, UserPreferences


# Onboarding Wizard Configuration
ONBOARDING_STEPS = [
    {
        "id": "welcome",
        "title": "Welcome",
        "description": "Let's personalize your experience",
    },
    {
        "id": "theme",
        "title": "Appearance",
        "description": "Choose your visual theme",
    },
    {
        "id": "modules",
        "title": "Modules",
        "description": "Select the areas you want to focus on",
    },
    {
        "id": "ai",
        "title": "AI Coaching",
        "description": "Personalize your AI companion",
    },
    {
        "id": "location",
        "title": "Location",
        "description": "Set your timezone and location",
    },
    {
        "id": "complete",
        "title": "All Set",
        "description": "You're ready to begin",
    },
]


class ProfileView(HelpContextMixin, LoginRequiredMixin, TemplateView):
    """
    Display user profile information.
    """

    template_name = "users/profile.html"
    help_context_id = "SETTINGS_PROFILE"
    
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


class ProfileEditView(HelpContextMixin, LoginRequiredMixin, UpdateView):
    """
    Edit user profile (name, email, avatar).
    """

    template_name = "users/profile_edit.html"
    form_class = ProfileForm
    success_url = reverse_lazy("users:profile")
    help_context_id = "SETTINGS_PROFILE_EDIT"

    def get_object(self):
        return self.request.user

    def form_valid(self, form):
        messages.success(self.request, "Profile updated successfully.")
        return super().form_valid(form)


class PreferencesView(HelpContextMixin, LoginRequiredMixin, UpdateView):
    """
    Edit user preferences (theme, Faith toggle, AI toggle, location).
    """

    template_name = "users/preferences.html"
    form_class = PreferencesForm
    success_url = reverse_lazy("users:preferences")
    help_context_id = "SETTINGS_PREFERENCES"

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
        except (ImportError, GoogleCalendarCredential.DoesNotExist, AttributeError):
            # Google Calendar not configured or credential doesn't exist
            context['google_calendar_connected'] = False
            context['google_calendar_name'] = None

        # NOTE: Bible API key is NO LONGER sent to frontend (Security Fix C-2)
        # Bible API is now accessed via server-side proxy at /faith/api/bible/

        # AI Coaching styles from database
        try:
            from apps.ai.models import CoachingStyle
            context['coaching_styles'] = CoachingStyle.get_active_styles()
        except (ImportError, Exception) as e:
            # CoachingStyle table may not exist yet during migrations
            import logging
            logging.getLogger(__name__).debug(f"Could not load coaching styles: {e}")
            context['coaching_styles'] = []

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
        """
        Get the client IP address from the request.

        Note: X-Forwarded-For can be spoofed by clients. In production behind
        a trusted proxy (like Railway), the first IP in the chain after the
        proxy should be trusted. For audit logging purposes, we take the
        leftmost IP which represents the original client (or spoofed value).

        For stricter security, consider using django-ipware or configuring
        SECURE_PROXY_HEADER with trusted proxy IPs.
        """
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            # Take the first IP in the chain (original client)
            # Note: This can be spoofed if not behind a trusted proxy
            ip = x_forwarded_for.split(",")[0].strip()
            # Basic validation: check it looks like an IP
            if ip and len(ip) <= 45:  # Max length for IPv6
                return ip
        return request.META.get("REMOTE_ADDR", "unknown")


class OnboardingView(LoginRequiredMixin, TemplateView):
    """
    Guided onboarding for new users - redirects to wizard.
    """

    def get(self, request, *args, **kwargs):
        # Redirect to the wizard
        return redirect("users:onboarding_wizard")


class OnboardingWizardView(LoginRequiredMixin, TemplateView):
    """
    Step-by-step onboarding wizard for new users.

    Walks users through personalization:
    1. Welcome - Introduction
    2. Theme - Visual appearance
    3. Modules - Enable/disable life areas
    4. AI - Coaching style selection
    5. Location - Timezone and city
    6. Complete - Final summary
    """

    template_name = "users/onboarding_wizard.html"

    def get_current_step(self):
        """Get the current step from session or URL."""
        step_id = self.kwargs.get("step", "welcome")
        # Find step index
        for i, step in enumerate(ONBOARDING_STEPS):
            if step["id"] == step_id:
                return i, step
        return 0, ONBOARDING_STEPS[0]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        step_index, current_step = self.get_current_step()

        context["steps"] = ONBOARDING_STEPS
        context["current_step"] = current_step
        context["current_step_index"] = step_index
        context["total_steps"] = len(ONBOARDING_STEPS)
        context["progress_percent"] = int((step_index / (len(ONBOARDING_STEPS) - 1)) * 100)

        # Previous/next step navigation
        if step_index > 0:
            context["prev_step"] = ONBOARDING_STEPS[step_index - 1]
        if step_index < len(ONBOARDING_STEPS) - 1:
            context["next_step"] = ONBOARDING_STEPS[step_index + 1]

        # Step-specific context
        prefs = self.request.user.preferences

        if current_step["id"] == "theme":
            context["themes"] = settings.WLJ_SETTINGS["THEMES"]
            context["current_theme"] = prefs.theme

        elif current_step["id"] == "modules":
            context["modules"] = [
                {"key": "journal_enabled", "name": "Journal", "icon": "📝",
                 "description": "Daily reflections, guided prompts, and mood tracking.",
                 "enabled": prefs.journal_enabled},
                {"key": "faith_enabled", "name": "Faith", "icon": "✝️",
                 "description": "Scripture reading, prayer requests, and faith milestones.",
                 "enabled": prefs.faith_enabled},
                {"key": "health_enabled", "name": "Health", "icon": "❤️",
                 "description": "Track weight, fasting, heart rate, and blood glucose.",
                 "enabled": prefs.health_enabled},
                {"key": "life_enabled", "name": "Life", "icon": "🏠",
                 "description": "Projects, tasks, calendar, and document storage.",
                 "enabled": prefs.life_enabled},
                {"key": "purpose_enabled", "name": "Purpose", "icon": "🧭",
                 "description": "Annual direction, goals, and seasonal reflections.",
                 "enabled": prefs.purpose_enabled},
            ]

        elif current_step["id"] == "ai":
            context["ai_enabled"] = prefs.ai_enabled
            context["current_coaching_style"] = prefs.ai_coaching_style
            try:
                from apps.ai.models import CoachingStyle
                context["coaching_styles"] = CoachingStyle.get_active_styles()
            except (ImportError, Exception) as e:
                # CoachingStyle table may not exist yet during migrations
                import logging
                logging.getLogger(__name__).debug(f"Could not load coaching styles: {e}")
                context["coaching_styles"] = []

        elif current_step["id"] == "location":
            context["current_timezone"] = prefs.timezone
            context["current_city"] = prefs.location_city
            context["current_country"] = prefs.location_country
            # Common timezone choices
            context["timezone_choices"] = [
                ("UTC", "UTC"),
                ("US/Eastern", "US Eastern"),
                ("US/Central", "US Central"),
                ("US/Mountain", "US Mountain"),
                ("US/Pacific", "US Pacific"),
                ("Europe/London", "London"),
                ("Europe/Paris", "Paris"),
                ("Europe/Berlin", "Berlin"),
                ("Asia/Tokyo", "Tokyo"),
                ("Asia/Shanghai", "Shanghai"),
                ("Australia/Sydney", "Sydney"),
            ]

        elif current_step["id"] == "complete":
            # Summary of what was configured
            context["summary"] = {
                "theme": settings.WLJ_SETTINGS["THEMES"].get(prefs.theme, {}).get("name", prefs.theme),
                "modules_enabled": sum([
                    prefs.journal_enabled,
                    prefs.faith_enabled,
                    prefs.health_enabled,
                    prefs.life_enabled,
                    prefs.purpose_enabled,
                ]),
                "ai_enabled": prefs.ai_enabled,
                "timezone": prefs.timezone,
            }

        return context

    def post(self, request, *args, **kwargs):
        """Handle step submissions and save preferences."""
        step_index, current_step = self.get_current_step()
        prefs = request.user.preferences

        # Process step-specific data
        if current_step["id"] == "theme":
            theme = request.POST.get("theme")
            if theme in settings.WLJ_SETTINGS["THEMES"]:
                prefs.theme = theme
                prefs.save(update_fields=["theme", "updated_at"])

        elif current_step["id"] == "modules":
            # Update module toggles
            prefs.journal_enabled = request.POST.get("journal_enabled") == "on"
            prefs.faith_enabled = request.POST.get("faith_enabled") == "on"
            prefs.health_enabled = request.POST.get("health_enabled") == "on"
            prefs.life_enabled = request.POST.get("life_enabled") == "on"
            prefs.purpose_enabled = request.POST.get("purpose_enabled") == "on"
            prefs.save(update_fields=[
                "journal_enabled", "faith_enabled", "health_enabled",
                "life_enabled", "purpose_enabled", "updated_at"
            ])

        elif current_step["id"] == "ai":
            prefs.ai_enabled = request.POST.get("ai_enabled") == "on"
            coaching_style = request.POST.get("ai_coaching_style")
            if coaching_style:
                prefs.ai_coaching_style = coaching_style
            prefs.save(update_fields=["ai_enabled", "ai_coaching_style", "updated_at"])

        elif current_step["id"] == "location":
            prefs.timezone = request.POST.get("timezone", "UTC")
            prefs.location_city = request.POST.get("location_city", "")
            prefs.location_country = request.POST.get("location_country", "")
            prefs.save(update_fields=[
                "timezone", "location_city", "location_country", "updated_at"
            ])

        # Determine next action
        action = request.POST.get("action", "next")

        if action == "skip":
            # Skip to next step without saving (already at default values)
            pass

        if action == "complete" or current_step["id"] == "complete":
            # Mark onboarding as complete
            prefs.has_completed_onboarding = True
            prefs.save(update_fields=["has_completed_onboarding", "updated_at"])
            messages.success(request, "Welcome to Whole Life Journey!")
            return redirect("dashboard:home")

        # Navigate to next step
        if step_index < len(ONBOARDING_STEPS) - 1:
            next_step = ONBOARDING_STEPS[step_index + 1]
            return redirect("users:onboarding_wizard_step", step=next_step["id"])

        return redirect("dashboard:home")


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
        return redirect("users:onboarding_wizard")
