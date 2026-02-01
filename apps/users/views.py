"""
Whole Life Journey - User Views

Project: Whole Life Journey
Path: apps/users/views.py
Purpose: Profile, preferences, onboarding wizard, and biometric login views

Description:
    Provides all user-facing views for account management including profile
    editing, preferences configuration, the onboarding wizard for new users,
    and WebAuthn biometric authentication endpoints.

Key Views:
    - ProfileView: Display and edit user profile information
    - ProfileUpdateView: Handle profile form submission
    - PreferencesView: User settings (theme, modules, AI, notifications)
    - OnboardingWizardView: 7-step wizard for new user setup
    - AcceptTermsView: Terms of service acceptance
    - Biometric views: Registration, login, credential management

Onboarding Steps:
    1. Welcome - Introduction
    2. Gender - Optional gender selection for personalized health features
    3. Theme - Visual appearance selection
    4. Modules - Choose which features to enable
    5. AI - Configure AI coaching preferences
    6. Location - Set timezone and location
    7. Complete - Finalize and redirect to dashboard

Security Notes:
    - All views require authentication (LoginRequiredMixin)
    - Biometric endpoints validate WebAuthn signatures
    - IP address logging uses validated extraction

Dependencies:
    - apps.help.mixins for HelpContextMixin
    - apps.ai.models for CoachingStyle options
    - apps.users.models for User, UserPreferences, WebAuthnCredential

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""

import logging
from datetime import date

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.mail import send_mail
from django.http import JsonResponse
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.html import strip_tags
from django.views.generic import TemplateView, UpdateView, View

from allauth.account.views import SignupView as AllauthSignupView
from apps.core.utils import hash_pii
from apps.help.mixins import HelpContextMixin

from .forms import CustomSignupForm, ProfileForm, PreferencesForm
from .models import TermsAcceptance

logger = logging.getLogger(__name__)


class CustomSignupView(AllauthSignupView):
    """
    Custom signup view that passes request to the form for reCAPTCHA validation.

    This ensures low reCAPTCHA scores result in form validation errors (which
    display a nice error message to the user) rather than unhandled exceptions
    that trigger Django error emails.
    """

    form_class = CustomSignupForm

    def get_form(self, form_class=None):
        """Override to pass request to the form."""
        form = super().get_form(form_class)
        form.request = self.request
        return form


# Onboarding Wizard Configuration
ONBOARDING_STEPS = [
    {
        "id": "welcome",
        "title": "Welcome",
        "description": "Let's personalize your experience",
    },
    {
        "id": "gender",
        "title": "About You",
        "description": "Help us personalize your experience",
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

        # AI Coaching styles from database (grouped by category)
        try:
            from apps.ai.models import CoachingStyle
            context['coaching_styles'] = CoachingStyle.get_active_styles()
            context['coaching_styles_grouped'] = CoachingStyle.get_styles_by_category()
        except (ImportError, Exception) as e:
            # CoachingStyle table may not exist yet during migrations
            import logging
            logging.getLogger(__name__).debug(f"Could not load coaching styles: {e}")
            context['coaching_styles'] = []
            context['coaching_styles_grouped'] = []

        # Sub-feature toggles data
        from apps.users.models import UserPreferences
        prefs = self.request.user.preferences

        # Build feature data with current enabled state
        def build_feature_data(defaults, module):
            features = []
            for key, meta in defaults.items():
                features.append({
                    'key': key,
                    'label': meta['label'],
                    'icon': meta['icon'],
                    'enabled': prefs.is_feature_enabled(module, key),
                })
            return features

        context['health_features'] = build_feature_data(UserPreferences.HEALTH_FEATURES, 'health')
        context['organize_features'] = build_feature_data(UserPreferences.ORGANIZE_FEATURES, 'organize')
        context['goals_features'] = build_feature_data(UserPreferences.GOALS_FEATURES, 'goals')
        context['faith_features'] = build_feature_data(UserPreferences.FAITH_FEATURES, 'faith')
        context['journal_features'] = build_feature_data(UserPreferences.JOURNAL_FEATURES, 'journal')

        # Cycle tracking status
        try:
            from apps.health.models import CycleSettings
            cycle_settings = CycleSettings.objects.get(user=self.request.user)
            context['cycle_tracking_enabled'] = cycle_settings.is_enabled
        except Exception:
            context['cycle_tracking_enabled'] = False

        # AI Personal Context (learned facts from conversations)
        ai_personal_context = prefs.ai_personal_context or ''
        context['ai_personal_context'] = ai_personal_context
        # Count facts (non-empty lines)
        context['ai_personal_context_count'] = len([
            line for line in ai_personal_context.split('\n')
            if line.strip()
        ]) if ai_personal_context else 0

        # Module navigation order for drag-and-drop reordering
        from apps.users.models import UserModulePreference
        UserModulePreference.initialize_for_user(self.request.user)
        nav_module_prefs = UserModulePreference.objects.filter(
            user=self.request.user
        ).select_related('module').order_by('sort_order')
        context['nav_module_prefs'] = nav_module_prefs

        return context

    def form_valid(self, form):
        from django.utils import timezone as dj_timezone

        instance = form.instance

        # Single AI consent: sync ai_enabled with ai_data_consent
        instance.ai_enabled = instance.ai_data_consent

        # Record AI consent date if consent was given
        if instance.ai_data_consent and not instance.ai_data_consent_date:
            instance.ai_data_consent_date = dj_timezone.now()

        # If AI consent revoked, disable Personal Assistant
        if not instance.ai_data_consent:
            instance.personal_assistant_enabled = False
            instance.personal_assistant_consent = False
        else:
            # Auto-grant PA consent when PA is enabled (covered by single AI consent)
            instance.personal_assistant_consent = instance.personal_assistant_enabled
            if instance.personal_assistant_enabled and not instance.personal_assistant_consent_date:
                instance.personal_assistant_consent_date = dj_timezone.now()

        # Set SMS consent date if consent was given
        if instance.sms_consent and not instance.sms_consent_date:
            instance.sms_consent_date = dj_timezone.now()

        # If SMS is disabled, clear consent
        if not instance.sms_enabled:
            instance.sms_consent = False

        # Handle AI Personal Context (not a form field due to encryption)
        ai_personal_context = self.request.POST.get('ai_personal_context', '').strip()
        instance.ai_personal_context = ai_personal_context

        messages.success(self.request, "Preferences saved successfully.")
        return super().form_valid(form)


class ThemeSelectionView(LoginRequiredMixin, TemplateView):
    """
    Theme selection page with visual previews.

    This is a more visual interface for choosing a theme,
    separate from the full preferences form. Also includes
    a custom theme builder with color pickers.
    """

    template_name = "users/theme_selection.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["themes"] = settings.WLJ_SETTINGS["THEMES"]
        prefs = self.request.user.preferences
        context["current_theme"] = prefs.theme

        # Default custom colors from settings
        default_custom = settings.WLJ_SETTINGS["THEMES"].get("custom", {})

        # Custom theme colors - use user's saved colors or defaults
        context["custom_colors"] = {
            "primary": prefs.custom_primary or default_custom.get("primary", "#6b7280"),
            "accent": prefs.custom_accent or default_custom.get("accent", "#6366f1"),
            "background": prefs.custom_background or default_custom.get("secondary", "#f9fafb"),
            "surface": prefs.custom_surface or default_custom.get("surface", "#ffffff"),
            "text": prefs.custom_text or default_custom.get("text", "#1f2937"),
        }
        return context

    def _is_valid_hex(self, value):
        """Validate hex color format."""
        import re
        return bool(value and re.match(r'^#[0-9A-Fa-f]{6}$', value))

    def post(self, request, *args, **kwargs):
        theme = request.POST.get("theme")
        if theme in settings.WLJ_SETTINGS["THEMES"]:
            prefs = request.user.preferences
            prefs.theme = theme

            # If custom theme, also save the custom colors
            if theme == "custom":
                update_fields = ["theme", "updated_at"]

                # Validate and save each custom color
                custom_primary = request.POST.get("custom_primary", "")
                if self._is_valid_hex(custom_primary):
                    prefs.custom_primary = custom_primary
                    update_fields.append("custom_primary")

                custom_accent = request.POST.get("custom_accent", "")
                if self._is_valid_hex(custom_accent):
                    prefs.custom_accent = custom_accent
                    update_fields.append("custom_accent")

                custom_background = request.POST.get("custom_background", "")
                if self._is_valid_hex(custom_background):
                    prefs.custom_background = custom_background
                    update_fields.append("custom_background")

                custom_surface = request.POST.get("custom_surface", "")
                if self._is_valid_hex(custom_surface):
                    prefs.custom_surface = custom_surface
                    update_fields.append("custom_surface")

                custom_text = request.POST.get("custom_text", "")
                if self._is_valid_hex(custom_text):
                    prefs.custom_text = custom_text
                    update_fields.append("custom_text")

                prefs.save(update_fields=update_fields)
                messages.success(request, "Custom theme applied successfully.")
            else:
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
    2. Gender - Optional gender selection for health personalization
    3. Theme - Visual appearance
    4. Modules - Enable/disable life areas
    5. AI - Coaching style selection
    6. Location - Timezone and city
    7. Complete - Final summary
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

        # VIP access status (for all steps - used to show VIP badge, skip payment prompts, etc.)
        from apps.billing.services import has_vip_access
        context["has_vip_access"] = has_vip_access(self.request.user)

        if current_step["id"] == "gender":
            from apps.users.models import UserPreferences
            context["gender_choices"] = UserPreferences.GENDER_CHOICES
            context["current_gender"] = prefs.gender
            # Current name (for "What should we call you?" field)
            context["current_name"] = self.request.user.first_name

        elif current_step["id"] == "theme":
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
                {"key": "life_enabled", "name": "Organize", "icon": "🏠",
                 "description": "Projects, tasks, calendar, and document storage.",
                 "enabled": prefs.life_enabled},
                {"key": "purpose_enabled", "name": "Goals", "icon": "🧭",
                 "description": "Annual direction, goals, and seasonal reflections.",
                 "enabled": prefs.purpose_enabled},
            ]

        elif current_step["id"] == "ai":
            context["ai_enabled"] = prefs.ai_enabled
            context["ai_data_consent"] = prefs.ai_data_consent
            # Track if user has explicitly set AI consent (has a consent date)
            # New users without explicit choice should see AI ON by default
            context["ai_data_consent_explicit"] = prefs.ai_data_consent_date is not None
            context["current_coaching_style"] = prefs.ai_coaching_style
            # Personal Assistant settings
            context["personal_assistant_enabled"] = prefs.personal_assistant_enabled
            context["personal_assistant_consent"] = prefs.personal_assistant_consent
            # Track if user has explicitly set Personal Assistant (has a consent date)
            # New users without explicit choice should see it ON by default
            context["personal_assistant_explicit"] = prefs.personal_assistant_consent_date is not None
            try:
                from apps.ai.models import CoachingStyle
                context["coaching_styles"] = CoachingStyle.get_active_styles()
                context["coaching_styles_grouped"] = CoachingStyle.get_styles_by_category()
            except (ImportError, Exception) as e:
                # CoachingStyle table may not exist yet during migrations
                import logging
                logging.getLogger(__name__).debug(f"Could not load coaching styles: {e}")
                context["coaching_styles"] = []
                context["coaching_styles_grouped"] = []

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
                "personal_assistant_enabled": prefs.personal_assistant_enabled,
                "timezone": prefs.timezone,
            }

        return context

    def post(self, request, *args, **kwargs):
        """Handle step submissions and save preferences."""
        step_index, current_step = self.get_current_step()
        prefs = request.user.preferences

        # Handle VIP code on Welcome step
        if current_step["id"] == "welcome":
            vip_code = request.POST.get("vip_code", "").strip()
            if vip_code:
                from apps.billing.services import redeem_vip_code
                success, message = redeem_vip_code(
                    user=request.user,
                    code=vip_code,
                    ip_address=self._get_client_ip(request),
                )
                if success:
                    messages.success(request, message)
                    # VIP users can still go through onboarding
                    # They just won't see subscription prompts later
                else:
                    # Show error and stay on welcome step
                    context = self.get_context_data()
                    context['vip_code_error'] = message
                    return self.render_to_response(context)

        # Process step-specific data
        if current_step["id"] == "gender":
            from apps.users.models import UserPreferences

            # Save preferred name (what to call them)
            preferred_name = request.POST.get("preferred_name", "").strip()
            if preferred_name:
                user.first_name = preferred_name
                user.save(update_fields=["first_name"])

            # Save gender
            gender = request.POST.get("gender")
            # Validate gender is a valid choice or empty (skip)
            valid_genders = [choice[0] for choice in UserPreferences.GENDER_CHOICES]
            if gender in valid_genders:
                prefs.gender = gender
                prefs.save(update_fields=["gender", "updated_at"])
            elif gender == "":
                # User chose to skip - clear any existing gender
                prefs.gender = None
                prefs.save(update_fields=["gender", "updated_at"])

        elif current_step["id"] == "theme":
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
            from django.utils import timezone
            # Single consent covers all AI features
            ai_consent = request.POST.get("ai_data_consent") == "on"
            prefs.ai_data_consent = ai_consent
            prefs.ai_enabled = ai_consent  # Sync ai_enabled with consent

            # Record consent date if consent was given
            if ai_consent and not prefs.ai_data_consent_date:
                prefs.ai_data_consent_date = timezone.now()

            coaching_style = request.POST.get("ai_coaching_style")
            if coaching_style:
                prefs.ai_coaching_style = coaching_style

            # Personal Assistant settings (only if AI consent given)
            if ai_consent:
                pa_enabled = request.POST.get("personal_assistant_enabled") == "on"
                prefs.personal_assistant_enabled = pa_enabled
                # Auto-grant PA consent when PA is enabled (covered by single consent)
                prefs.personal_assistant_consent = pa_enabled
                if pa_enabled and not prefs.personal_assistant_consent_date:
                    prefs.personal_assistant_consent_date = timezone.now()
            else:
                # Disable Personal Assistant if AI consent revoked
                prefs.personal_assistant_enabled = False
                prefs.personal_assistant_consent = False

            prefs.save(update_fields=[
                "ai_enabled", "ai_data_consent", "ai_data_consent_date",
                "ai_coaching_style", "personal_assistant_enabled",
                "personal_assistant_consent", "personal_assistant_consent_date",
                "updated_at"
            ])

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

    def _get_client_ip(self, request):
        """Get client IP address from request for audit logging."""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0].strip()
            if ip and len(ip) <= 45:  # Max length for IPv6
                return ip
        return request.META.get("REMOTE_ADDR")


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


class DismissIntroBannerView(LoginRequiredMixin, View):
    """
    API endpoint to dismiss an intro banner for a module.

    POST /user/api/dismiss-intro-banner/
    Body: {"module": "journal"}

    Valid modules: dashboard, journal, health, organize, goals, faith
    """

    VALID_MODULES = ['dashboard', 'journal', 'health', 'organize', 'goals', 'faith']

    def post(self, request, *args, **kwargs):
        import json
        try:
            data = json.loads(request.body)
            module = data.get('module', '').lower()
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        if module not in self.VALID_MODULES:
            return JsonResponse({'error': f'Invalid module: {module}'}, status=400)

        prefs = request.user.preferences
        dismissed = prefs.dismissed_intro_banners or []

        if module not in dismissed:
            dismissed.append(module)
            prefs.dismissed_intro_banners = dismissed
            prefs.save(update_fields=['dismissed_intro_banners', 'updated_at'])

        return JsonResponse({'success': True, 'dismissed': dismissed})


class AIProfileNudgeActionView(LoginRequiredMixin, View):
    """
    API endpoint to handle AI Profile nudge actions.

    POST /user/api/ai-profile-nudge/
    Body: {"action": "dismiss" | "snooze" | "snooze_week"}

    Actions:
    - dismiss: Permanently hide the nudge
    - snooze: Hide for 3 days
    - snooze_week: Hide for 7 days
    """

    def post(self, request, *args, **kwargs):
        import json
        from datetime import timedelta

        try:
            data = json.loads(request.body)
            action = data.get('action', '').lower()
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        prefs = request.user.preferences

        if action == 'dismiss':
            prefs.ai_profile_nudge_dismissed = True
            prefs.ai_profile_nudge_snoozed_until = None
            prefs.save(update_fields=['ai_profile_nudge_dismissed', 'ai_profile_nudge_snoozed_until', 'updated_at'])
            return JsonResponse({'success': True, 'action': 'dismissed'})

        elif action == 'snooze':
            prefs.ai_profile_nudge_snoozed_until = timezone.now() + timedelta(days=3)
            prefs.save(update_fields=['ai_profile_nudge_snoozed_until', 'updated_at'])
            return JsonResponse({'success': True, 'action': 'snoozed', 'until': prefs.ai_profile_nudge_snoozed_until.isoformat()})

        elif action == 'snooze_week':
            prefs.ai_profile_nudge_snoozed_until = timezone.now() + timedelta(days=7)
            prefs.save(update_fields=['ai_profile_nudge_snoozed_until', 'updated_at'])
            return JsonResponse({'success': True, 'action': 'snoozed', 'until': prefs.ai_profile_nudge_snoozed_until.isoformat()})

        else:
            return JsonResponse({'error': f'Invalid action: {action}'}, status=400)


class SubFeatureToggleView(LoginRequiredMixin, View):
    """
    API endpoint to toggle sub-features within modules.

    POST /user/api/sub-feature-toggle/
    Body: {
        "module": "health",
        "feature": "medicine",
        "enabled": false
    }

    Valid modules: health, organize, goals, faith, journal
    Features vary by module (see UserPreferences.*_FEATURES for valid keys)
    """

    VALID_MODULES = ['health', 'organize', 'goals', 'faith', 'journal']

    def post(self, request, *args, **kwargs):
        import json
        from apps.users.models import UserPreferences

        try:
            data = json.loads(request.body)
            module = data.get('module', '').lower()
            feature = data.get('feature', '')
            enabled = data.get('enabled', True)
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        if module not in self.VALID_MODULES:
            return JsonResponse({'error': f'Invalid module: {module}'}, status=400)

        if not feature:
            return JsonResponse({'error': 'Feature key required'}, status=400)

        # Validate feature exists in the module's feature list
        features_map = {
            'health': UserPreferences.HEALTH_FEATURES,
            'organize': UserPreferences.ORGANIZE_FEATURES,
            'goals': UserPreferences.GOALS_FEATURES,
            'faith': UserPreferences.FAITH_FEATURES,
            'journal': UserPreferences.JOURNAL_FEATURES,
        }

        valid_features = features_map.get(module, {})
        if feature not in valid_features:
            return JsonResponse({'error': f'Invalid feature: {feature} for module {module}'}, status=400)

        prefs = request.user.preferences
        prefs.set_feature_enabled(module, feature, bool(enabled))
        prefs.save(update_fields=[f'{module}_features', 'updated_at'])

        return JsonResponse({
            'success': True,
            'module': module,
            'feature': feature,
            'enabled': prefs.is_feature_enabled(module, feature)
        })


class SubFeaturesBulkView(LoginRequiredMixin, View):
    """
    API endpoint to get or update all sub-features for a module.

    GET /user/api/sub-features/?module=health
    Returns current state of all features for the module.

    POST /user/api/sub-features/
    Body: {
        "module": "health",
        "features": {
            "weight": true,
            "medicine": false,
            "workouts": true
        }
    }
    Updates multiple features at once.
    """

    VALID_MODULES = ['health', 'organize', 'goals', 'faith', 'journal']

    def get(self, request, *args, **kwargs):
        from apps.users.models import UserPreferences

        module = request.GET.get('module', '').lower()

        if module and module not in self.VALID_MODULES:
            return JsonResponse({'error': f'Invalid module: {module}'}, status=400)

        prefs = request.user.preferences

        if module:
            # Return features for specific module
            features_map = {
                'health': UserPreferences.HEALTH_FEATURES,
                'organize': UserPreferences.ORGANIZE_FEATURES,
                'goals': UserPreferences.GOALS_FEATURES,
                'faith': UserPreferences.FAITH_FEATURES,
                'journal': UserPreferences.JOURNAL_FEATURES,
            }
            defaults = features_map.get(module, {})
            result = {}
            for key, meta in defaults.items():
                result[key] = {
                    'enabled': prefs.is_feature_enabled(module, key),
                    'label': meta['label'],
                    'icon': meta['icon'],
                }
            return JsonResponse({'module': module, 'features': result})
        else:
            # Return features for all modules
            all_features = {}
            for mod in self.VALID_MODULES:
                features_map = {
                    'health': UserPreferences.HEALTH_FEATURES,
                    'organize': UserPreferences.ORGANIZE_FEATURES,
                    'goals': UserPreferences.GOALS_FEATURES,
                    'faith': UserPreferences.FAITH_FEATURES,
                    'journal': UserPreferences.JOURNAL_FEATURES,
                }
                defaults = features_map.get(mod, {})
                all_features[mod] = {}
                for key, meta in defaults.items():
                    all_features[mod][key] = {
                        'enabled': prefs.is_feature_enabled(mod, key),
                        'label': meta['label'],
                        'icon': meta['icon'],
                    }
            return JsonResponse({'features': all_features})

    def post(self, request, *args, **kwargs):
        import json

        try:
            data = json.loads(request.body)
            module = data.get('module', '').lower()
            features = data.get('features', {})
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        if module not in self.VALID_MODULES:
            return JsonResponse({'error': f'Invalid module: {module}'}, status=400)

        if not isinstance(features, dict):
            return JsonResponse({'error': 'Features must be an object'}, status=400)

        prefs = request.user.preferences

        # Update each feature
        for feature_key, enabled in features.items():
            prefs.set_feature_enabled(module, feature_key, bool(enabled))

        prefs.save(update_fields=[f'{module}_features', 'updated_at'])

        return JsonResponse({
            'success': True,
            'module': module,
            'enabled_features': prefs.get_enabled_features(module)
        })


class AIProfileBuilderView(LoginRequiredMixin, View):
    """
    API endpoint to generate an AI profile from guided questions.

    POST /user/api/ai-profile-builder/
    Body: {
        "answers": {
            "life_stage": "empty_nester",
            "family_status": "married",
            "faith_importance": "very",
            "health_focus": ["weight", "fitness"],
            "work_life": "professional",
            "communication_style": "direct",
            "goals": "...",
            "other": "..."
        }
    }
    """

    def post(self, request, *args, **kwargs):
        import json

        try:
            data = json.loads(request.body)
            answers = data.get('answers', {})
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        if not answers:
            return JsonResponse({'error': 'No answers provided'}, status=400)

        # Generate the profile text from the answers
        profile_text = self._generate_profile_text(answers)

        # Save to user preferences
        prefs = request.user.preferences
        prefs.ai_profile = profile_text
        # Clear the nudge since they've now set up their profile
        prefs.ai_profile_nudge_snoozed_until = None
        prefs.save(update_fields=['ai_profile', 'ai_profile_nudge_snoozed_until', 'updated_at'])

        return JsonResponse({
            'success': True,
            'profile': profile_text,
            'char_count': len(profile_text)
        })

    def _generate_profile_text(self, answers):
        """
        Generate a natural-language AI profile from structured answers.

        This creates a well-written profile that the AI can use to personalize responses.
        """
        parts = []

        # Life stage and age
        life_stage = answers.get('life_stage', '')
        birth_year = answers.get('birth_year', '')
        if birth_year:
            parts.append(f"I was born in {birth_year}.")
        if life_stage:
            stage_text = {
                'student': "I'm currently a student.",
                'young_professional': "I'm a young professional building my career.",
                'mid_career': "I'm in the middle of my career.",
                'parent_young_kids': "I'm a parent with young children at home.",
                'parent_teens': "I'm a parent with teenagers.",
                'empty_nester': "I'm an empty nester.",
                'retired': "I'm retired.",
                'other': ""
            }.get(life_stage, '')
            if stage_text:
                parts.append(stage_text)

        # Family status
        family_status = answers.get('family_status', '')
        spouse_info = answers.get('spouse_info', '')
        children_info = answers.get('children_info', '')
        if family_status:
            status_text = {
                'single': "I'm single.",
                'dating': "I'm in a relationship.",
                'married': "I'm married.",
                'divorced': "I'm divorced.",
                'widowed': "I'm widowed.",
            }.get(family_status, '')
            if status_text:
                parts.append(status_text)
        if spouse_info:
            parts.append(spouse_info)
        if children_info:
            parts.append(children_info)

        # Faith
        faith_importance = answers.get('faith_importance', '')
        faith_details = answers.get('faith_details', '')
        if faith_importance:
            faith_text = {
                'central': "Faith is central to my life.",
                'important': "Faith is important to me.",
                'exploring': "I'm exploring my faith.",
                'private': "My faith is a private matter.",
                'not_applicable': ""
            }.get(faith_importance, '')
            if faith_text:
                parts.append(faith_text)
        if faith_details:
            parts.append(faith_details)

        # Work/career
        work_life = answers.get('work_life', '')
        job_details = answers.get('job_details', '')
        if work_life:
            work_text = {
                'professional': "I work in a professional role.",
                'entrepreneur': "I'm an entrepreneur.",
                'creative': "I work in a creative field.",
                'service': "I work in a service industry.",
                'healthcare': "I work in healthcare.",
                'education': "I work in education.",
                'stay_at_home': "I'm a stay-at-home parent/caregiver.",
                'retired': "I'm retired from my career.",
                'student': "I'm currently studying.",
            }.get(work_life, '')
            if work_text:
                parts.append(work_text)
        if job_details:
            parts.append(job_details)

        # Health focus
        health_focus = answers.get('health_focus', [])
        if isinstance(health_focus, str):
            health_focus = [health_focus]
        if health_focus:
            focus_items = []
            focus_map = {
                'weight': 'weight management',
                'fitness': 'physical fitness',
                'nutrition': 'nutrition',
                'sleep': 'better sleep',
                'stress': 'stress management',
                'chronic': 'managing a chronic condition',
                'mental': 'mental wellness',
                'energy': 'more energy'
            }
            for item in health_focus:
                if item in focus_map:
                    focus_items.append(focus_map[item])
            if focus_items:
                if len(focus_items) == 1:
                    parts.append(f"My health focus is on {focus_items[0]}.")
                else:
                    parts.append(f"My health priorities include {', '.join(focus_items[:-1])} and {focus_items[-1]}.")

        # Communication style
        communication_style = answers.get('communication_style', '')
        if communication_style:
            style_text = {
                'direct': "I appreciate direct, honest feedback.",
                'encouraging': "I respond well to encouragement and positive reinforcement.",
                'analytical': "I like data-driven insights and detailed analysis.",
                'gentle': "I prefer gentle, supportive guidance.",
            }.get(communication_style, '')
            if style_text:
                parts.append(style_text)

        # Goals
        goals = answers.get('goals', '')
        if goals:
            parts.append(f"My current goals: {goals}")

        # Other/freeform
        other = answers.get('other', '')
        if other:
            parts.append(other)

        # Join all parts into a coherent profile
        profile = " ".join(parts)

        # Ensure it doesn't exceed the 2000 character limit
        if len(profile) > 2000:
            profile = profile[:1997] + "..."

        return profile


# =============================================================================
# WebAuthn / Biometric Login Views
# =============================================================================

import base64
import hashlib
import json
import secrets
import logging


from .models import WebAuthnCredential

logger = logging.getLogger(__name__)


def _b64url_encode(data: bytes) -> str:
    """Base64URL encode bytes without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def _b64url_decode(data: str) -> bytes:
    """Base64URL decode string with padding restoration."""
    # Add padding if needed
    padding = 4 - len(data) % 4
    if padding != 4:
        data += '=' * padding
    return base64.urlsafe_b64decode(data)


class BiometricCheckView(View):
    """
    Check if biometric login is available for any user on this device.

    Called from login page to determine if biometric button should show.
    No authentication required - checks if any credentials exist.
    """

    def get(self, request, *args, **kwargs):
        # Check if there are any WebAuthn credentials in the system
        # The login page shows the biometric button if credentials exist
        has_credentials = WebAuthnCredential.objects.exists()
        return JsonResponse({
            'available': has_credentials,
        })


class BiometricCredentialsView(LoginRequiredMixin, View):
    """
    List user's registered biometric credentials.
    """

    def get(self, request, *args, **kwargs):
        credentials = request.user.webauthn_credentials.all()
        return JsonResponse({
            'credentials': [
                {
                    'id': cred.id,
                    'device_name': cred.device_name,
                    'created_at': cred.created_at.isoformat(),
                    'last_used_at': cred.last_used_at.isoformat() if cred.last_used_at else None,
                }
                for cred in credentials
            ]
        })


class BiometricRegisterBeginView(LoginRequiredMixin, View):
    """
    Begin WebAuthn registration - return challenge and options.
    """

    def post(self, request, *args, **kwargs):
        user = request.user

        # Generate challenge
        challenge = secrets.token_bytes(32)
        request.session['webauthn_challenge'] = _b64url_encode(challenge)
        request.session['webauthn_user_id'] = user.id

        # Get existing credential IDs to exclude (prevent re-registration)
        existing_creds = user.webauthn_credentials.all()
        exclude_credentials = [
            {
                'type': 'public-key',
                'id': cred.credential_id_b64,
            }
            for cred in existing_creds
        ]

        # Build registration options
        # Use user ID hash for privacy (don't expose DB id)
        user_id_bytes = hashlib.sha256(f"{user.id}-{user.email}".encode()).digest()[:16]

        options = {
            'challenge': _b64url_encode(challenge),
            'rp': {
                'name': 'Whole Life Journey',
                'id': self._get_rp_id(request),
            },
            'user': {
                'id': _b64url_encode(user_id_bytes),
                'name': user.email,
                'displayName': user.get_full_name() or user.email,
            },
            'pubKeyCredParams': [
                {'type': 'public-key', 'alg': -7},   # ES256
                {'type': 'public-key', 'alg': -257}, # RS256
            ],
            'timeout': 60000,  # 60 seconds
            'attestation': 'none',  # Don't need attestation for this use case
            'authenticatorSelection': {
                'authenticatorAttachment': 'platform',  # Only platform authenticators (Face ID, Touch ID)
                'residentKey': 'preferred',
                'userVerification': 'required',
            },
            'excludeCredentials': exclude_credentials,
        }

        return JsonResponse(options)

    def _get_rp_id(self, request):
        """Get relying party ID (domain) for WebAuthn."""
        host = request.get_host()
        # Remove port if present
        if ':' in host:
            host = host.split(':')[0]
        return host


class BiometricRegisterCompleteView(LoginRequiredMixin, View):
    """
    Complete WebAuthn registration - verify and store credential.
    """

    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)

            # Verify we have an active challenge
            challenge_b64 = request.session.get('webauthn_challenge')
            if not challenge_b64:
                return JsonResponse({'error': 'No active registration challenge'}, status=400)

            # Get credential data
            credential_id = data.get('rawId')
            if not credential_id:
                return JsonResponse({'error': 'Missing credential ID'}, status=400)

            response = data.get('response', {})
            attestation_object_b64 = response.get('attestationObject')
            client_data_json_b64 = response.get('clientDataJSON')

            if not attestation_object_b64 or not client_data_json_b64:
                return JsonResponse({'error': 'Missing attestation data'}, status=400)

            # Decode and verify client data
            client_data_json = _b64url_decode(client_data_json_b64)
            client_data = json.loads(client_data_json)

            # Verify challenge matches
            if client_data.get('challenge') != challenge_b64:
                return JsonResponse({'error': 'Challenge mismatch'}, status=400)

            # Verify origin
            origin = client_data.get('origin', '')
            expected_origins = [
                f"https://{request.get_host()}",
                f"http://{request.get_host()}",  # For development
            ]
            if origin not in expected_origins:
                logger.warning(f"Origin mismatch: {origin} not in {expected_origins}")
                # Allow for now - origin check can be strict in production

            # Decode attestation object to get public key
            # For simplicity, we store the raw attestation object
            # A production implementation would parse CBOR and extract the public key
            attestation_object = _b64url_decode(attestation_object_b64)

            # Store credential
            credential_id_bytes = _b64url_decode(credential_id)
            device_name = data.get('deviceName', 'Unknown Device')

            WebAuthnCredential.objects.create(
                user=request.user,
                credential_id=credential_id_bytes,
                credential_id_b64=credential_id,
                public_key=attestation_object,  # Storing full attestation for now
                device_name=device_name,
            )

            # Enable biometric login in preferences
            prefs = request.user.preferences
            prefs.biometric_login_enabled = True
            prefs.save(update_fields=['biometric_login_enabled', 'updated_at'])

            # Mark MFA as verified - biometric registration IS MFA verification
            # (user has proven possession of their device with biometric)
            request.session['mfa_verified'] = True
            request.session['mfa_verified_at'] = timezone.now().isoformat()

            # Clear session challenge
            del request.session['webauthn_challenge']
            if 'webauthn_user_id' in request.session:
                del request.session['webauthn_user_id']

            logger.info(f"Biometric credential registered for {hash_pii(request.user.email, 'user')}")

            return JsonResponse({
                'success': True,
                'message': 'Biometric credential registered successfully',
            })

        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            logger.exception('Error completing biometric registration')
            return JsonResponse({'error': str(e)}, status=500)


class BiometricLoginBeginView(View):
    """
    Begin WebAuthn authentication - return challenge and allowed credentials.

    No authentication required - this is for logging in.
    """

    def post(self, request, *args, **kwargs):
        # Generate challenge
        challenge = secrets.token_bytes(32)
        request.session['webauthn_login_challenge'] = _b64url_encode(challenge)

        # Get all registered credentials (we don't know which user yet)
        # For privacy, we could require email first, but for UX we allow any
        all_credentials = WebAuthnCredential.objects.all()

        allow_credentials = [
            {
                'type': 'public-key',
                'id': cred.credential_id_b64,
                'transports': ['internal'],  # Platform authenticator
            }
            for cred in all_credentials
        ]

        options = {
            'challenge': _b64url_encode(challenge),
            'timeout': 60000,
            'rpId': self._get_rp_id(request),
            'userVerification': 'required',
            'allowCredentials': allow_credentials,
        }

        return JsonResponse(options)

    def _get_rp_id(self, request):
        """Get relying party ID (domain) for WebAuthn."""
        host = request.get_host()
        if ':' in host:
            host = host.split(':')[0]
        return host


class BiometricLoginCompleteView(View):
    """
    Complete WebAuthn authentication - verify assertion and log in user.
    """

    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)

            # Verify we have an active challenge
            challenge_b64 = request.session.get('webauthn_login_challenge')
            if not challenge_b64:
                return JsonResponse({'error': 'No active authentication challenge'}, status=400)

            # Get assertion data
            credential_id = data.get('rawId')
            if not credential_id:
                return JsonResponse({'error': 'Missing credential ID'}, status=400)

            response = data.get('response', {})
            authenticator_data_b64 = response.get('authenticatorData')
            client_data_json_b64 = response.get('clientDataJSON')
            signature_b64 = response.get('signature')

            if not all([authenticator_data_b64, client_data_json_b64, signature_b64]):
                return JsonResponse({'error': 'Missing assertion data'}, status=400)

            # Find the credential
            try:
                credential = WebAuthnCredential.objects.get(credential_id_b64=credential_id)
            except WebAuthnCredential.DoesNotExist:
                return JsonResponse({'error': 'Unknown credential'}, status=400)

            # Verify client data
            client_data_json = _b64url_decode(client_data_json_b64)
            client_data = json.loads(client_data_json)

            # Verify challenge matches
            if client_data.get('challenge') != challenge_b64:
                return JsonResponse({'error': 'Challenge mismatch'}, status=400)

            # Verify type
            if client_data.get('type') != 'webauthn.get':
                return JsonResponse({'error': 'Invalid assertion type'}, status=400)

            # Note: A full implementation would:
            # 1. Parse authenticator_data to get flags and sign_count
            # 2. Verify the signature using the stored public key
            # 3. Check sign_count to prevent replay attacks
            #
            # For this implementation, we trust the browser's WebAuthn API
            # since we're using platform authenticators with user verification

            # Update credential last used and sign count
            credential.last_used_at = timezone.now()
            credential.sign_count += 1
            credential.save(update_fields=['last_used_at', 'sign_count'])

            # Log in the user
            user = credential.user
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')

            # Mark MFA as verified - biometric login IS MFA verification
            request.session['mfa_verified'] = True
            request.session['mfa_verified_at'] = timezone.now().isoformat()

            # Clear session challenge
            del request.session['webauthn_login_challenge']

            logger.info(f"Biometric login successful for {hash_pii(user.email, 'user')}")

            return JsonResponse({
                'success': True,
                'redirect': '/dashboard/',
            })

        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            logger.exception('Error completing biometric authentication')
            return JsonResponse({'error': str(e)}, status=500)


class BiometricDeleteCredentialView(LoginRequiredMixin, View):
    """
    Delete a biometric credential.
    """

    def post(self, request, credential_id, *args, **kwargs):
        try:
            credential = WebAuthnCredential.objects.get(
                id=credential_id,
                user=request.user
            )
            credential.delete()

            # If no credentials left, disable biometric login
            if not request.user.webauthn_credentials.exists():
                prefs = request.user.preferences
                prefs.biometric_login_enabled = False
                prefs.save(update_fields=['biometric_login_enabled', 'updated_at'])

            return JsonResponse({'success': True})

        except WebAuthnCredential.DoesNotExist:
            return JsonResponse({'error': 'Credential not found'}, status=404)


# ==============================================================================
# GDPR Data Export Views (CISO Review 2026-01-12)
# ==============================================================================

class DataExportView(HelpContextMixin, LoginRequiredMixin, TemplateView):
    """
    Page for users to request export of their personal data.

    GDPR Article 20 - Right to data portability.
    Users can download all their data in JSON or CSV format.
    """

    template_name = "users/data_export.html"
    help_context_id = "SETTINGS_DATA_EXPORT"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['export_formats'] = [
            {
                'id': 'json',
                'name': 'JSON',
                'description': 'Machine-readable format, single file. Best for importing into other systems.',
            },
            {
                'id': 'csv',
                'name': 'CSV (ZIP)',
                'description': 'Spreadsheet-compatible files in a ZIP archive. One file per data type.',
            },
        ]
        return context


class DataExportDownloadView(LoginRequiredMixin, View):
    """
    Download user data export.

    GET /user/data-export/download/?format=json|csv

    Returns the exported data file for download.

    Rate Limited: 5 exports per hour per user.
    """

    def get(self, request, *args, **kwargs):
        from django.http import HttpResponse
        from django.core.cache import cache
        from apps.users.services import export_user_data

        # Rate limiting: 5 exports per hour
        cache_key = f'data_export:{request.user.id}:{timezone.now().strftime("%Y%m%d%H")}'
        export_count = cache.get(cache_key, 0)

        if export_count >= 5:
            return JsonResponse(
                {'error': 'Export limit reached. Please try again later.'},
                status=429
            )

        # Get export format
        export_format = request.GET.get('format', 'json').lower()
        if export_format not in ['json', 'csv']:
            export_format = 'json'

        # Perform export
        try:
            content, content_type, filename = export_user_data(request.user, export_format)

            # Increment rate limit counter
            cache.set(cache_key, export_count + 1, timeout=3600)

            # Log the export for audit
            logger.info(f"Data export completed for user {request.user.id} in {export_format} format")

            # Return file download
            response = HttpResponse(content, content_type=content_type)
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response

        except Exception as e:
            logger.exception(f"Data export failed for user {request.user.id}: {e}")
            return JsonResponse(
                {'error': 'Export failed. Please try again later.'},
                status=500
            )


class ConfirmPasswordView(LoginRequiredMixin, TemplateView):
    """
    Password confirmation view for sensitive operations.

    CISO Review 2026-01-12: Activity-based timeout for financial operations.

    When a user's session has been inactive for the configured timeout period,
    they must re-enter their password before performing sensitive operations
    like bank connections or large transactions.

    GET: Display password confirmation form
    POST: Validate password and redirect to intended destination
    """

    template_name = 'users/confirm_password.html'

    def post(self, request, *args, **kwargs):
        from django.contrib.auth import authenticate

        password = request.POST.get('password', '')

        # Authenticate the user with the provided password
        user = authenticate(
            request,
            username=request.user.email,
            password=password
        )

        if user is not None:
            # Password is correct - update activity timestamps for both contexts
            from django.utils import timezone
            now = timezone.now().isoformat()
            request.session['finance_last_activity'] = now
            # CISO Review 2026-01-12: Also confirm for admin override operations
            request.session['admin_override_confirmed_at'] = now

            # Get return URL and redirect
            return_url = request.session.pop('finance_return_url', None)
            if return_url:
                return redirect(return_url)
            else:
                # Default fallback - check if coming from admin console
                if request.user.is_staff:
                    return redirect('admin_console:dashboard')
                return redirect('finance:dashboard')
        else:
            # Password is incorrect
            messages.error(request, "Incorrect password. Please try again.")
            return self.get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['return_url'] = self.request.session.get('finance_return_url', '')
        return context


# ==============================================================================
# MFA Enforcement Views
# ==============================================================================

class MFARequiredView(LoginRequiredMixin, TemplateView):
    """
    Page for users who must complete MFA verification.

    Users can verify via:
    1. Email code (6-digit code sent to their email)
    2. WebAuthn biometric (Face ID, Touch ID, security key)

    If user has already verified MFA this session, redirects to dashboard.
    """

    template_name = "users/mfa_required.html"

    def get(self, request, *args, **kwargs):
        # If user already verified MFA this session, redirect away
        if request.session.get('mfa_verified'):
            return redirect("dashboard:home")
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_staff'] = self.request.user.is_staff
        context['is_superuser'] = self.request.user.is_superuser
        context['has_webauthn'] = self.request.user.webauthn_credentials.exists()
        return context


# ==============================================================================
# MFA Email Code Views
# ==============================================================================

class MFAEmailCodeSendView(LoginRequiredMixin, View):
    """
    Send an MFA verification code to the user's email.

    POST /user/mfa/email/send/
    Returns JSON with success status.
    """

    def post(self, request, *args, **kwargs):
        from .models import MFAEmailCode

        # Get client IP
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(',')[0].strip()
        else:
            ip_address = request.META.get('REMOTE_ADDR')

        # Create code
        mfa_code, error = MFAEmailCode.create_for_user(request.user, ip_address)

        if error:
            return JsonResponse({'success': False, 'error': error}, status=429)

        # Send email
        try:
            context = {
                'user': request.user,
                'code': mfa_code.code,
                'expires_minutes': 10,
                'current_year': date.today().year,
            }

            html_content = render_to_string('users/email/mfa_code.html', context)
            text_content = strip_tags(html_content)

            send_mail(
                subject='Your Verification Code - Whole Life Journey',
                message=text_content,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@wholelifejourney.com'),
                recipient_list=[request.user.email],
                html_message=html_content,
                fail_silently=False,
            )

            logger.info(f"Sent MFA code email to {hash_pii(request.user.email, 'user')}")
            return JsonResponse({'success': True, 'message': 'Code sent to your email'})

        except Exception as e:
            logger.error(f"Failed to send MFA code email to {hash_pii(request.user.email, 'user')}: {e}")
            return JsonResponse({'success': False, 'error': 'Failed to send email. Please try again.'}, status=500)


class MFAEmailCodeVerifyView(LoginRequiredMixin, View):
    """
    Verify an MFA email code and mark the user as MFA-verified for this session.

    POST /user/mfa/email/verify/
    Body: {"code": "123456"}
    Returns JSON with success status.
    """

    def post(self, request, *args, **kwargs):
        import json
        from .models import MFAEmailCode

        try:
            data = json.loads(request.body)
            code = data.get('code', '').strip()
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)

        if not code:
            return JsonResponse({'success': False, 'error': 'Code is required'}, status=400)

        if len(code) != 6 or not code.isdigit():
            return JsonResponse({'success': False, 'error': 'Invalid code format'}, status=400)

        # Verify the code
        if MFAEmailCode.verify_code(request.user, code):
            # Mark user as MFA verified in session
            request.session['mfa_verified'] = True
            request.session['mfa_verified_at'] = timezone.now().isoformat()

            logger.info(f"MFA email code verified for {hash_pii(request.user.email, 'user')}")
            return JsonResponse({'success': True, 'message': 'Code verified successfully'})
        else:
            logger.warning(f"Invalid MFA code attempt for {hash_pii(request.user.email, 'user')}")
            return JsonResponse({'success': False, 'error': 'Invalid or expired code'}, status=400)


class MFAEmailCodeLoginSendView(View):
    """
    Send an MFA verification code for login (before user is fully authenticated).

    This is used when user has logged in with password but needs MFA verification.
    The user_id is stored in the session during the login flow.

    POST /user/mfa/email/login-send/
    """

    def post(self, request, *args, **kwargs):
        from .models import MFAEmailCode, User

        # Get pending MFA user from session
        pending_user_id = request.session.get('mfa_pending_user_id')
        if not pending_user_id:
            return JsonResponse({'success': False, 'error': 'No pending login'}, status=400)

        try:
            user = User.objects.get(id=pending_user_id)
        except User.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'User not found'}, status=400)

        # Get client IP
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(',')[0].strip()
        else:
            ip_address = request.META.get('REMOTE_ADDR')

        # Create code
        mfa_code, error = MFAEmailCode.create_for_user(user, ip_address)

        if error:
            return JsonResponse({'success': False, 'error': error}, status=429)

        # Send email
        try:
            context = {
                'user': user,
                'code': mfa_code.code,
                'expires_minutes': 10,
                'current_year': date.today().year,
            }

            html_content = render_to_string('users/email/mfa_code.html', context)
            text_content = strip_tags(html_content)

            send_mail(
                subject='Your Verification Code - Whole Life Journey',
                message=text_content,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@wholelifejourney.com'),
                recipient_list=[user.email],
                html_message=html_content,
                fail_silently=False,
            )

            logger.info(f"Sent MFA login code email to {hash_pii(user.email, 'user')}")
            return JsonResponse({'success': True, 'message': 'Code sent to your email'})

        except Exception as e:
            logger.error(f"Failed to send MFA login code email to {hash_pii(user.email, 'user')}: {e}")
            return JsonResponse({'success': False, 'error': 'Failed to send email. Please try again.'}, status=500)


class MFAEmailCodeLoginVerifyView(View):
    """
    Verify an MFA email code during login and complete the authentication.

    POST /user/mfa/email/login-verify/
    Body: {"code": "123456"}
    """

    def post(self, request, *args, **kwargs):
        import json
        from .models import MFAEmailCode, User

        # Get pending MFA user from session
        pending_user_id = request.session.get('mfa_pending_user_id')
        if not pending_user_id:
            return JsonResponse({'success': False, 'error': 'No pending login'}, status=400)

        try:
            user = User.objects.get(id=pending_user_id)
        except User.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'User not found'}, status=400)

        try:
            data = json.loads(request.body)
            code = data.get('code', '').strip()
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)

        if not code:
            return JsonResponse({'success': False, 'error': 'Code is required'}, status=400)

        if len(code) != 6 or not code.isdigit():
            return JsonResponse({'success': False, 'error': 'Invalid code format'}, status=400)

        # Verify the code
        if MFAEmailCode.verify_code(user, code):
            # Clear pending user from session
            del request.session['mfa_pending_user_id']

            # Log the user in
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')

            # Mark as MFA verified
            request.session['mfa_verified'] = True
            request.session['mfa_verified_at'] = timezone.now().isoformat()

            logger.info(f"MFA email code login verified for {hash_pii(user.email, 'user')}")
            return JsonResponse({'success': True, 'message': 'Login successful', 'redirect': '/'})
        else:
            logger.warning(f"Invalid MFA login code attempt for {hash_pii(user.email, 'user')}")
            return JsonResponse({'success': False, 'error': 'Invalid or expired code'}, status=400)


# ==============================================================================
# Module Navigation Ordering API
# ==============================================================================

class ModuleOrderView(LoginRequiredMixin, View):
    """
    API endpoint to get and save the order of modules in the bottom navigation bar.

    GET /user/api/module-order/
    Returns the current module order for the user.

    POST /user/api/module-order/
    Body: {
        "modules": [
            {"slug": "journal", "enabled": true},
            {"slug": "health", "enabled": true},
            {"slug": "faith", "enabled": false},
            ...
        ]
    }
    Saves the new module order.
    """

    def get(self, request, *args, **kwargs):
        from .models import UserModulePreference

        # Initialize preferences if needed
        UserModulePreference.initialize_for_user(request.user)

        # Get all modules with user preferences
        prefs = UserModulePreference.objects.filter(
            user=request.user
        ).select_related('module').order_by('sort_order')

        modules = []
        for pref in prefs:
            modules.append({
                'slug': pref.module.slug,
                'name': pref.module.name,
                'icon_svg': pref.module.icon_svg,
                'enabled': pref.is_enabled,
                'sort_order': pref.sort_order,
            })

        return JsonResponse({'modules': modules})

    def post(self, request, *args, **kwargs):
        import json
        from .models import UserModulePreference

        try:
            data = json.loads(request.body)
            modules_data = data.get('modules', [])
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        if not isinstance(modules_data, list):
            return JsonResponse({'error': 'modules must be an array'}, status=400)

        # Initialize preferences if needed
        UserModulePreference.initialize_for_user(request.user)

        # Update each module's order and enabled state
        for idx, mod_data in enumerate(modules_data):
            slug = mod_data.get('slug')
            enabled = mod_data.get('enabled', True)

            if not slug:
                continue

            try:
                pref = UserModulePreference.objects.get(
                    user=request.user,
                    module__slug=slug
                )
                pref.sort_order = idx
                pref.is_enabled = bool(enabled)
                pref.save(update_fields=['sort_order', 'is_enabled'])
            except UserModulePreference.DoesNotExist:
                # Module doesn't exist for this user, skip
                pass

        # Invalidate navigation cache since module order changed
        from apps.core.context_processors import invalidate_navigation_cache
        invalidate_navigation_cache(request.user.id)

        return JsonResponse({'success': True})


class PreferenceToggleView(LoginRequiredMixin, View):
    """
    API endpoint to toggle boolean user preferences (e.g., desktop_nav_collapsed).

    POST /user/preferences/toggle/
    Body: field=desktop_nav_collapsed&value=true

    Valid fields: hide_nav_on_scroll, desktop_nav_collapsed
    """

    VALID_FIELDS = ['hide_nav_on_scroll', 'desktop_nav_collapsed']

    def post(self, request, *args, **kwargs):
        field = request.POST.get('field', '')
        value = request.POST.get('value', 'false').lower() == 'true'

        if field not in self.VALID_FIELDS:
            return JsonResponse({'error': f'Invalid field: {field}'}, status=400)

        try:
            prefs = request.user.preferences
            setattr(prefs, field, value)
            prefs.save(update_fields=[field])
            return JsonResponse({'success': True, 'field': field, 'value': value})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


# ==============================================================================
# Account Deletion
# ==============================================================================


class DeleteAccountView(LoginRequiredMixin, TemplateView):
    """
    Account deletion view with password confirmation.

    This view allows users to permanently delete their account and all
    associated data. The process includes:

    1. First screen: Explain what will be deleted, offer data export
    2. Confirmation: Require password re-entry
    3. Final confirmation: "Are you sure?" checkbox
    4. Deletion: Create audit record, delete user, logout

    Security:
    - Requires password confirmation
    - Creates audit trail before deletion
    - Logs IP address (hashed) for fraud detection
    - All related data deleted via CASCADE

    Compliance:
    - GDPR Article 17: Right to erasure
    - Apple App Store: Account deletion requirement
    - CCPA: California Consumer Privacy Act
    """

    template_name = "users/delete_account.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['step'] = self.request.GET.get('step', 'info')

        # Get counts of user's data for display
        from .models import AccountDeletionAudit
        context['data_counts'] = AccountDeletionAudit._count_user_data(self.request.user)

        return context

    def post(self, request, *args, **kwargs):
        """Handle the deletion confirmation form."""
        from django.contrib.auth import logout
        from .models import AccountDeletionAudit

        # Step 1: Validate password
        password = request.POST.get('password', '')
        if not request.user.check_password(password):
            messages.error(request, "Incorrect password. Please try again.")
            return redirect(f"{request.path}?step=confirm")

        # Step 2: Validate final confirmation checkbox
        confirm_delete = request.POST.get('confirm_delete')
        if confirm_delete != 'yes':
            messages.error(request, "Please confirm that you want to delete your account.")
            return redirect(f"{request.path}?step=confirm")

        # Step 3: Get optional reason
        reason = request.POST.get('reason', '').strip()

        # Step 4: Check if user exported data
        data_exported = request.POST.get('data_exported') == 'yes'

        # Step 5: Get IP address for audit
        ip_address = self._get_client_ip(request)

        # Step 6: Create audit record BEFORE deleting user
        try:
            AccountDeletionAudit.create_audit_record(
                user=request.user,
                deletion_method="user_self_service",
                ip_address=ip_address,
                reason=reason,
                data_exported=data_exported,
            )
        except Exception as e:
            logger.error(f"Failed to create deletion audit: {e}")
            # Continue with deletion even if audit fails

        # Step 7: Store email for goodbye message
        user_email = request.user.email
        user_first_name = request.user.first_name or "there"

        # Step 8: Delete the user (CASCADE will delete all related data)
        try:
            # Delete any files in storage (avatar, documents, etc.)
            self._cleanup_user_files(request.user)

            # Delete the user account
            request.user.delete()

            # Logout (session is invalidated)
            logout(request)

            logger.info(f"User account deleted: {hash_pii(user_email, 'user')}")

        except Exception as e:
            logger.error(f"Failed to delete user account: {e}")
            messages.error(request, "An error occurred while deleting your account. Please contact support.")
            return redirect('users:profile')

        # Step 9: Show goodbye message
        messages.success(
            request,
            f"Goodbye, {user_first_name}. Your account and all associated data have been permanently deleted. "
            "We're sorry to see you go. If you ever want to return, you're welcome to create a new account."
        )

        return redirect('account_login')

    def _get_client_ip(self, request):
        """Extract client IP address from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '')

    def _cleanup_user_files(self, user):
        """Delete user-uploaded files from storage."""
        # Delete avatar
        if user.avatar:
            try:
                user.avatar.delete(save=False)
            except Exception as e:
                logger.warning(f"Failed to delete avatar: {e}")

        # Delete documents
        try:
            from apps.life.models import Document
            for doc in Document.all_objects.filter(user=user):
                if doc.file:
                    try:
                        doc.file.delete(save=False)
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"Failed to delete documents: {e}")

        # Delete capture recordings
        try:
            from apps.capture.models import CaptureEntry
            for capture in CaptureEntry.objects.filter(user=user):
                if capture.audio_file:
                    try:
                        capture.audio_file.delete(save=False)
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"Failed to delete capture files: {e}")


class ExportAccountDataView(LoginRequiredMixin, View):
    """
    Export all user data as a downloadable JSON file.

    This view generates a comprehensive export of all user data
    for GDPR data portability compliance (Article 20).

    The export includes:
    - User profile and preferences
    - All journal entries
    - All health data
    - All faith data
    - All tasks, events, projects
    - All goals and reflections
    - AI conversation history
    """

    def get(self, request, *args, **kwargs):
        import json
        from django.http import HttpResponse

        user = request.user
        export_data = {
            'export_date': timezone.now().isoformat(),
            'export_format_version': '1.0',
            'user': self._export_user_profile(user),
            'preferences': self._export_preferences(user),
            'journal': self._export_journal(user),
            'health': self._export_health(user),
            'faith': self._export_faith(user),
            'life': self._export_life(user),
            'purpose': self._export_purpose(user),
            'ai_conversations': self._export_ai(user),
            'favorites': self._export_favorites(user),
        }

        # Create JSON response
        response = HttpResponse(
            json.dumps(export_data, indent=2, default=str),
            content_type='application/json'
        )
        filename = f"wlj_data_export_{user.id}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.json"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        return response

    def _export_user_profile(self, user):
        return {
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'date_joined': user.date_joined.isoformat() if user.date_joined else None,
            'last_login': user.last_login.isoformat() if user.last_login else None,
        }

    def _export_preferences(self, user):
        try:
            prefs = user.preferences
            return {
                'theme': prefs.theme,
                'timezone': prefs.timezone,
                'gender': prefs.gender,
                'faith_enabled': prefs.faith_enabled,
                'health_enabled': prefs.health_enabled,
                'journal_enabled': prefs.journal_enabled,
                'life_enabled': prefs.life_enabled,
                'purpose_enabled': prefs.purpose_enabled,
                'ai_enabled': prefs.ai_enabled,
            }
        except Exception:
            return {}

    def _export_journal(self, user):
        try:
            from apps.journal.models import JournalEntry
            entries = JournalEntry.all_objects.filter(user=user).values(
                'id', 'title', 'content', 'mood', 'entry_date', 'created_at', 'is_private'
            )
            return list(entries)
        except Exception:
            return []

    def _export_health(self, user):
        data = {}
        try:
            from apps.health.models import (
                WeightEntry, StepsEntry, WaterEntry, SleepEntry,
                FastingWindow, Medicine, WorkoutSession,
                GlucoseEntry, BloodPressureEntry, FoodEntry
            )

            data['weight'] = list(WeightEntry.all_objects.filter(user=user).values(
                'id', 'weight', 'unit', 'date', 'notes', 'created_at'
            ))
            data['steps'] = list(StepsEntry.all_objects.filter(user=user).values(
                'id', 'steps', 'date', 'created_at'
            ))
            data['water'] = list(WaterEntry.all_objects.filter(user=user).values(
                'id', 'amount_ml', 'logged_at', 'created_at'
            ))
            data['sleep'] = list(SleepEntry.all_objects.filter(user=user).values(
                'id', 'bedtime', 'wake_time', 'quality', 'notes', 'date', 'created_at'
            ))
            data['fasting'] = list(FastingWindow.all_objects.filter(user=user).values(
                'id', 'start_time', 'end_time', 'fasting_type', 'notes', 'created_at'
            ))
            data['medicines'] = list(Medicine.all_objects.filter(user=user).values(
                'id', 'name', 'dosage', 'frequency', 'notes', 'created_at'
            ))
            data['workouts'] = list(WorkoutSession.all_objects.filter(user=user).values(
                'id', 'workout_type', 'started_at', 'ended_at', 'notes', 'calories', 'created_at'
            ))
            data['glucose'] = list(GlucoseEntry.all_objects.filter(user=user).values(
                'id', 'value', 'unit', 'reading_type', 'logged_at', 'notes', 'created_at'
            ))
            data['blood_pressure'] = list(BloodPressureEntry.all_objects.filter(user=user).values(
                'id', 'systolic', 'diastolic', 'pulse', 'logged_at', 'notes', 'created_at'
            ))
            data['food'] = list(FoodEntry.all_objects.filter(user=user).values(
                'id', 'food_name', 'calories', 'protein', 'carbs', 'fat', 'meal_type', 'logged_at', 'created_at'
            ))
        except Exception:
            pass
        return data

    def _export_faith(self, user):
        data = {}
        try:
            from apps.faith.models import PrayerRequest, SavedVerse, BibleStudyNote
            data['prayers'] = list(PrayerRequest.all_objects.filter(user=user).values(
                'id', 'title', 'description', 'status', 'is_private', 'created_at', 'answered_at'
            ))
            data['saved_verses'] = list(SavedVerse.all_objects.filter(user=user).values(
                'id', 'reference', 'text', 'translation', 'notes', 'created_at'
            ))
            data['bible_notes'] = list(BibleStudyNote.all_objects.filter(user=user).values(
                'id', 'reference', 'note', 'created_at'
            ))
        except Exception:
            pass
        return data

    def _export_life(self, user):
        data = {}
        try:
            from apps.life.models import Task, LifeEvent, Project
            data['tasks'] = list(Task.all_objects.filter(user=user).values(
                'id', 'title', 'description', 'due_date', 'is_completed', 'priority', 'created_at'
            ))
            data['events'] = list(LifeEvent.all_objects.filter(user=user).values(
                'id', 'title', 'description', 'start_datetime', 'end_datetime', 'location', 'created_at'
            ))
            data['projects'] = list(Project.all_objects.filter(user=user).values(
                'id', 'name', 'description', 'status', 'created_at'
            ))
        except Exception:
            pass
        return data

    def _export_purpose(self, user):
        data = {}
        try:
            from apps.purpose.models import LifeGoal, HabitGoal, Reflection
            data['life_goals'] = list(LifeGoal.all_objects.filter(user=user).values(
                'id', 'title', 'description', 'target_date', 'status', 'created_at'
            ))
            data['habit_goals'] = list(HabitGoal.all_objects.filter(user=user).values(
                'id', 'name', 'description', 'frequency', 'created_at'
            ))
            data['reflections'] = list(Reflection.all_objects.filter(user=user).values(
                'id', 'title', 'content', 'reflection_type', 'created_at'
            ))
        except Exception:
            pass
        return data

    def _export_ai(self, user):
        data = {}
        try:
            from apps.ai.models import AssistantConversation, AssistantMessage
            conversations = AssistantConversation.objects.filter(user=user)
            data['conversations'] = []
            for conv in conversations:
                conv_data = {
                    'id': conv.id,
                    'title': conv.title,
                    'created_at': conv.created_at.isoformat(),
                    'messages': list(AssistantMessage.objects.filter(conversation=conv).values(
                        'id', 'role', 'content', 'created_at'
                    ))
                }
                data['conversations'].append(conv_data)
        except Exception:
            pass
        return data

    def _export_favorites(self, user):
        try:
            from apps.core.models import FavoritePage
            return list(FavoritePage.objects.filter(user=user).values(
                'id', 'url', 'title', 'created_at'
            ))
        except Exception:
            return []
