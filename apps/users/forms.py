"""
Whole Life Journey - User Forms

Project: Whole Life Journey
Path: apps/users/forms.py
Purpose: Forms for user profile and preferences editing

Description:
    Provides Django forms for editing user profile information (name, email,
    avatar) and user preferences (theme, modules, AI settings, etc.).

Key Forms:
    - ProfileForm: Edit user profile (name, email, avatar)
    - PreferencesForm: Edit user preferences (theme, modules, AI, timezone)

Validation:
    - Avatar uploads validated for file type (JPG, PNG, GIF, HEIC, WebP) and size (2MB max)
    - Email uniqueness enforced by model
    - Form preserves existing avatar when no new file uploaded

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""

from datetime import date

from allauth.account.forms import SignupForm
from django import forms
from django.contrib.auth import get_user_model

from .models import UserPreferences

User = get_user_model()


class CustomSignupForm(SignupForm):
    """
    Custom signup form that adds date of birth for COPPA compliance.
    Users must be 13 years or older to create an account.

    Also validates reCAPTCHA score during form validation to prevent
    bot signups without triggering Django error emails.
    """

    date_of_birth = forms.DateField(
        label="Date of Birth",
        required=True,
        widget=forms.DateInput(attrs={
            "class": "form-input",
            "type": "date",
            "max": date.today().isoformat(),
        }),
        help_text="You must be 13 years or older to use this service.",
    )

    def clean_date_of_birth(self):
        """Validate that user is at least 13 years old."""
        dob = self.cleaned_data.get("date_of_birth")
        if dob:
            today = date.today()
            # Calculate age
            age = today.year - dob.year
            # Adjust if birthday hasn't occurred yet this year
            if (today.month, today.day) < (dob.month, dob.day):
                age -= 1

            if age < 13:
                raise forms.ValidationError(
                    "You must be 13 years or older to create an account. "
                    "If you are under 13, please ask a parent or guardian for assistance."
                )

            # Sanity check - reject obviously invalid dates (e.g., claiming to be 150 years old)
            if age > 120:
                raise forms.ValidationError(
                    "Please enter a valid date of birth."
                )

        return dob

    def __init__(self, *args, **kwargs):
        """Store request for reCAPTCHA validation."""
        super().__init__(*args, **kwargs)
        # Request will be set by the view
        self.request = None

    def clean(self):
        """
        Validate form data including honeypot, reCAPTCHA, geo-blocking, and disposable emails.

        Validates during form validation rather than in adapter.save_user() so that
        blocked signups result in form validation errors instead of unhandled
        exceptions that trigger error emails.
        """
        from django.conf import settings
        from apps.users.services import RecaptchaService
        from apps.core.security_logging import log_security_event

        cleaned_data = super().clean()

        # Skip validation if no request (e.g., in tests)
        if not self.request:
            return cleaned_data

        email = cleaned_data.get('email', '')

        # Check honeypot field - bots will fill this hidden field
        honeypot_value = self.request.POST.get("website", "")
        if honeypot_value:
            # Log the blocked attempt
            self._log_honeypot_block(email)
            # Raise generic error to not reveal honeypot detection
            raise forms.ValidationError(
                "Unable to create account. Please try again later."
            )

        # Check for disposable email domains
        if email and self._is_disposable_email(email):
            self._log_blocked_attempt(email, "disposable_email")
            raise forms.ValidationError(
                "Please use a non-temporary email address to create your account."
            )

        # Check geo-blocking (USA only, unless whitelisted)
        geo_error = self._check_geo_blocking(email)
        if geo_error:
            raise forms.ValidationError(geo_error)

        # Get reCAPTCHA token from POST data
        token = self.request.POST.get("recaptcha_token", "")
        if not token:
            # No token - let adapter handle logging, don't block here
            return cleaned_data

        # Verify reCAPTCHA
        try:
            from apps.users.adapters import get_client_ip
            ip = get_client_ip(self.request)
            service = RecaptchaService()
            result = service.verify(token, ip)

            if result.success and result.score is not None:
                threshold = getattr(settings, 'RECAPTCHA_SCORE_THRESHOLD', 0.5)
                if result.score < threshold:
                    # Log the blocked attempt
                    log_security_event(
                        event_type='bot_activity',
                        severity='warning',
                        message=f'Signup blocked due to low reCAPTCHA score: {result.score:.2f} (threshold: {threshold})',
                        request=self.request,
                        details={'score': result.score, 'threshold': threshold},
                    )

                    # Store score for adapter's logging
                    self._recaptcha_score = result.score
                    self._recaptcha_blocked = True

                    # Raise validation error (handled cleanly, no error email)
                    raise forms.ValidationError(
                        "Unable to create account. Please try again later."
                    )

                # Store score for adapter's logging
                self._recaptcha_score = result.score
                self._recaptcha_blocked = False

        except forms.ValidationError:
            raise  # Re-raise validation errors
        except Exception as e:
            # Fail open - don't block signup if reCAPTCHA fails
            import logging
            logger = logging.getLogger(__name__)
            logger.error("reCAPTCHA verification error in form: %s", e)

        return cleaned_data

    def _is_disposable_email(self, email: str) -> bool:
        """Check if email uses a disposable/temporary domain."""
        from apps.users.models import DisposableEmailDomain
        return DisposableEmailDomain.is_disposable(email)

    def _check_geo_blocking(self, email: str):
        """
        Check if signup should be blocked based on geographic location.

        Returns error message if blocked, None if allowed.
        Fails open - allows signup if geolocation fails.
        """
        import logging
        from apps.users.adapters import get_client_ip
        from apps.users.services import GeoIPService
        from apps.users.models import AllowedInternationalEmail

        logger = logging.getLogger(__name__)

        try:
            ip = get_client_ip(self.request)
            service = GeoIPService()
            result = service.get_country_from_ip(ip)

            # Store country code for logging
            self._country_code = result.country_code

            # If geolocation failed, fail open (allow signup)
            if not result.success:
                logger.info("GeoIP lookup failed, allowing signup: %s", result.error)
                return None

            # USA is always allowed
            if result.is_usa:
                return None

            # Check if email is whitelisted for international signup
            if AllowedInternationalEmail.is_allowed(email):
                logger.info(
                    "International signup allowed for whitelisted email from %s",
                    result.country_code
                )
                return None

            # Block non-US signups that aren't whitelisted
            self._log_blocked_attempt(email, "geo_blocked", result.country_code)
            return "Whole Life Journey is currently only available in the United States."

        except Exception as e:
            # Fail open - don't block signup if geo check fails
            logger.error("Geo-blocking check failed: %s", e)
            return None

    def _log_blocked_attempt(self, email: str, block_reason: str, country_code: str = ""):
        """Log a blocked signup attempt to SignupAttempt."""
        import logging
        from apps.users.adapters import get_client_ip
        from apps.users.models import SignupAttempt
        from apps.users.security import hash_email, hash_ip
        from apps.core.security_logging import log_security_event

        logger = logging.getLogger(__name__)

        try:
            ip = get_client_ip(self.request)
            user_agent = self.request.META.get("HTTP_USER_AGENT", "")[:500]

            SignupAttempt.objects.create(
                email_hash=hash_email(email) if email else "",
                ip_hash=hash_ip(ip),
                user_agent=user_agent,
                country_code=country_code,
                status="blocked",
                block_reason=block_reason,
                risk_level="medium" if block_reason == "geo_blocked" else "high",
                risk_score=0.7 if block_reason == "geo_blocked" else 0.9,
            )

            # Log security event
            log_security_event(
                event_type='signup_blocked',
                severity='warning',
                message=f'Signup blocked: {block_reason}',
                request=self.request,
                details={
                    'block_reason': block_reason,
                    'country_code': country_code,
                },
            )

            logger.warning(
                "Signup blocked (%s) from IP: %s, country: %s",
                block_reason, ip[:20], country_code,
            )
        except Exception as e:
            logger.error("Failed to log blocked signup attempt: %s", e)

    def _log_honeypot_block(self, email=None):
        """
        Log a blocked signup attempt due to honeypot trigger.

        Args:
            email: Optional email address (may not be available)
        """
        import logging
        from apps.core.security_logging import log_security_event
        from apps.users.adapters import get_client_ip
        from apps.users.models import SignupAttempt
        from apps.users.security import hash_email, hash_ip

        logger = logging.getLogger(__name__)

        try:
            ip = get_client_ip(self.request)
            user_agent = self.request.META.get("HTTP_USER_AGENT", "")[:500]

            SignupAttempt.objects.create(
                email_hash=hash_email(email) if email else "",
                ip_hash=hash_ip(ip),
                user_agent=user_agent,
                status="blocked",
                block_reason="honeypot",
                risk_level="high",
                risk_score=1.0,
            )

            # Send security notification for bot detection
            log_security_event(
                event_type='bot_activity',
                severity='warning',
                message='Bot signup blocked via honeypot',
                request=self.request,
                details={'email_provided': bool(email)},
            )

            logger.warning(
                "Honeypot triggered - blocking signup attempt from IP: %s",
                ip,
            )
        except Exception as e:
            # Don't let logging failures break the validation
            logger.error("Failed to log honeypot block: %s", e)

    def save(self, request):
        """Save the user with the date of birth."""
        user = super().save(request)
        user.date_of_birth = self.cleaned_data.get("date_of_birth")
        user.save()
        return user


class ProfileForm(forms.ModelForm):
    """
    Form for editing user profile (name, email, avatar).
    """

    # Add a clear avatar checkbox
    clear_avatar = forms.BooleanField(
        required=False,
        label="Remove current photo",
        widget=forms.CheckboxInput(attrs={"class": "form-checkbox"})
    )

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "avatar"]
        widgets = {
            "first_name": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "First name",
            }),
            "last_name": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "Last name",
            }),
            "email": forms.EmailInput(attrs={
                "class": "form-input",
                "placeholder": "Email address",
            }),
            "avatar": forms.FileInput(attrs={
                "class": "form-file-input",
                "accept": "image/*",
            }),
        }
        help_texts = {
            "email": "Changing your email will update your login credentials.",
            "avatar": "Upload a profile picture (JPG, PNG, GIF, HEIC). Max 2MB.",
        }

    def clean_avatar(self):
        avatar = self.cleaned_data.get('avatar')
        if avatar and avatar is not False:
            # Only validate if a new file was actually uploaded
            # avatar is False when no new file is selected (keeping existing)
            if hasattr(avatar, 'size'):
                # Check file size (2MB limit)
                if avatar.size > 2 * 1024 * 1024:
                    raise forms.ValidationError("Image file too large. Maximum size is 2MB.")
            if hasattr(avatar, 'content_type') and avatar.content_type:
                # Check file type - allow common image types including HEIC from iPhone
                allowed_types = (
                    'image/jpeg', 'image/jpg', 'image/png', 'image/gif',
                    'image/webp', 'image/heic', 'image/heif',
                    'application/octet-stream',  # Some browsers don't set content_type
                )
                if not avatar.content_type.startswith('image/') and avatar.content_type not in allowed_types:
                    raise forms.ValidationError("Please upload an image file.")
        return avatar

    def save(self, commit=True):
        user = super().save(commit=False)

        # Handle clear avatar checkbox - explicitly remove avatar
        if self.cleaned_data.get('clear_avatar'):
            # Delete old avatar file if it exists
            if user.avatar:
                user.avatar.delete(save=False)
            user.avatar = None
        else:
            # Check if no new file was uploaded (avatar is False or None)
            # In this case, preserve the existing avatar
            avatar_value = self.cleaned_data.get('avatar')
            if avatar_value is False or avatar_value is None:
                # Restore the original avatar from the instance
                if self.instance and self.instance.pk:
                    user.avatar = self.instance.avatar

        if commit:
            user.save()
        return user


class PreferencesForm(forms.ModelForm):
    """
    Form for editing user preferences.
    """

    # notification_reminder_time - not required in form, will default to 7:00 AM
    notification_reminder_time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={"class": "form-input", "type": "time", "step": "900"}),
    )

    # SMS quiet hours - not required in form, will use model defaults
    sms_quiet_start = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={"class": "form-input", "type": "time", "step": "900"}),
    )
    sms_quiet_end = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={"class": "form-input", "type": "time", "step": "900"}),
    )

    def clean_notification_reminder_time(self):
        """Provide default if empty, normalize to 15-minute increments."""
        import datetime
        from apps.core.utils import normalize_to_quarter_hour
        value = self.cleaned_data.get('notification_reminder_time')
        if value is None:
            return datetime.time(7, 0)  # Default to 7:00 AM
        return normalize_to_quarter_hour(value)

    def clean_sms_quiet_start(self):
        """Provide default if empty, normalize to 15-minute increments."""
        import datetime
        from apps.core.utils import normalize_to_quarter_hour
        value = self.cleaned_data.get('sms_quiet_start')
        if value is None:
            return datetime.time(22, 0)  # Default to 10:00 PM
        return normalize_to_quarter_hour(value)

    def clean_sms_quiet_end(self):
        """Provide default if empty, normalize to 15-minute increments."""
        import datetime
        from apps.core.utils import normalize_to_quarter_hour
        value = self.cleaned_data.get('sms_quiet_end')
        if value is None:
            return datetime.time(7, 0)  # Default to 7:00 AM
        return normalize_to_quarter_hour(value)

    class Meta:
        model = UserPreferences
        fields = [
            "theme",
            "accent_color",
            # Navigation behavior
            "hide_nav_on_scroll",
            # Personal information
            "gender",
            # Module toggles
            "journal_enabled",
            "faith_enabled",
            "health_enabled",
            "life_enabled",
            "purpose_enabled",
            "goals_enabled",
            "finances_enabled",
            "capture_enabled",
            "relationships_enabled",
            "habits_enabled",
            "sports_enabled",
            # AI
            "ai_enabled",
            "ai_data_consent",
            'ai_coaching_style',
            'cos_response_style',
            'ai_profile',
            # Personal Assistant (sub-module of AI)
            "personal_assistant_enabled",
            "personal_assistant_consent",
            # Location
            "location_city",
            "location_country",
            "timezone",
            # Faith
            "default_bible_translation",
            # Notifications
            "show_whats_new",
            # Security
            "biometric_login_enabled",
            # Health
            "default_fasting_type",
            # Weight Goals — moved to Health Profile (apps/health/models.py HealthProfile)
            # Nutrition Goals
            "daily_calorie_goal",
            "protein_percentage",
            "carbs_percentage",
            "fat_percentage",
            # SMS Notifications
            "sms_enabled",
            "sms_consent",
            "sms_medicine_reminders",
            "sms_medicine_refill_alerts",
            "sms_task_reminders",
            "sms_event_reminders",
            "sms_prayer_reminders",
            "sms_fasting_reminders",
            "sms_significant_event_reminders",
            "sms_quiet_hours_enabled",
            "sms_quiet_start",
            "sms_quiet_end",
            # In-App & Email Notifications
            "notifications_enabled",
            "email_notifications_enabled",
            "email_notification_frequency",
            "notification_reminder_time",
            "notify_inapp_medicine",
            "notify_inapp_task",
            "notify_inapp_event",
            "notify_inapp_prayer",
            "notify_inapp_reading_plan",
            "notify_inapp_milestone",
            "notify_inapp_significant_event",
            "notify_inapp_finance",
            "notify_inapp_journal",
            "notify_email_medicine",
            "notify_email_task",
            "notify_email_event",
            "notify_email_prayer",
            "notify_email_reading_plan",
            "notify_email_milestone",
            "notify_email_significant_event",
            "notify_email_finance",
            "notify_email_journal",
        ]
        widgets = {
            "theme": forms.Select(attrs={
                "class": "form-select",
            }),
            "accent_color": forms.TextInput(attrs={
                "class": "form-input",
                "type": "color",
                "placeholder": "#6366f1",
            }),
            # Personal information
            "gender": forms.Select(attrs={
                "class": "form-select",
            }),
            # Module toggles
            "journal_enabled": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "faith_enabled": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "health_enabled": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "life_enabled": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "purpose_enabled": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "goals_enabled": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "finances_enabled": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "capture_enabled": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "relationships_enabled": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "habits_enabled": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "sports_enabled": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "ai_enabled": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "ai_data_consent": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "personal_assistant_enabled": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "personal_assistant_consent": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "ai_profile": forms.Textarea(attrs={
                "class": "form-textarea",
                "rows": 5,
                "placeholder": "Tell the AI about yourself to personalize your experience...\n\nExamples:\n• Age and life stage (e.g., 'I'm in my 40s with two teenagers')\n• Family situation (e.g., 'married, work-from-home parent')\n• Health focus (e.g., 'managing blood pressure, trying to lose 20lbs')\n• Faith journey (e.g., 'growing Christian seeking deeper prayer life')\n• Interests (e.g., 'love hiking, cooking, woodworking')\n• Work/career (e.g., 'software developer, often stressed about deadlines')",
                "maxlength": "2000",
            }),
            # Location
            "location_city": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "City",
            }),
            "location_country": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "Country",
            }),
            "timezone": forms.Select(attrs={
                "class": "form-select",
            }),
            "default_bible_translation": forms.HiddenInput(),
            # Notifications
            "show_whats_new": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            # Security
            "biometric_login_enabled": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            # Health
            "default_fasting_type": forms.Select(attrs={
                "class": "form-select",
            }),
            # Weight Goals — moved to Health Profile
            # Nutrition Goals
            "daily_calorie_goal": forms.NumberInput(attrs={
                "class": "form-input",
                "placeholder": "Daily calories",
                "min": "500",
                "max": "10000",
            }),
            "protein_percentage": forms.NumberInput(attrs={
                "class": "form-input",
                "placeholder": "% protein",
                "min": "0",
                "max": "100",
            }),
            "carbs_percentage": forms.NumberInput(attrs={
                "class": "form-input",
                "placeholder": "% carbs",
                "min": "0",
                "max": "100",
            }),
            "fat_percentage": forms.NumberInput(attrs={
                "class": "form-input",
                "placeholder": "% fat",
                "min": "0",
                "max": "100",
            }),
            # SMS Notifications
            "sms_enabled": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "sms_consent": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "sms_medicine_reminders": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "sms_medicine_refill_alerts": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "sms_task_reminders": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "sms_event_reminders": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "sms_prayer_reminders": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "sms_fasting_reminders": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "sms_significant_event_reminders": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "sms_quiet_hours_enabled": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "sms_quiet_start": forms.TimeInput(attrs={
                "class": "form-input",
                "type": "time",
                "step": "900",
            }),
            "sms_quiet_end": forms.TimeInput(attrs={
                "class": "form-input",
                "type": "time",
                "step": "900",
            }),
            # In-App & Email Notifications
            "notifications_enabled": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "email_notifications_enabled": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "email_notification_frequency": forms.Select(attrs={
                "class": "form-select",
            }),
            "notification_reminder_time": forms.TimeInput(attrs={
                "class": "form-input",
                "type": "time",
                "step": "900",
            }),
            "notify_inapp_medicine": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "notify_inapp_task": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "notify_inapp_event": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "notify_inapp_prayer": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "notify_inapp_reading_plan": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "notify_inapp_milestone": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "notify_inapp_significant_event": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "notify_inapp_finance": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "notify_inapp_journal": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "notify_email_medicine": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "notify_email_task": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "notify_email_event": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "notify_email_prayer": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "notify_email_reading_plan": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "notify_email_milestone": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "notify_email_significant_event": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "notify_email_finance": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "notify_email_journal": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Generate timezone choices - IANA format required for PostgreSQL compatibility
        common_timezones = [
            ("America/New_York", "Eastern Time (US)"),
            ("America/Chicago", "Central Time (US)"),
            ("America/Denver", "Mountain Time (US)"),
            ("America/Los_Angeles", "Pacific Time (US)"),
            ("America/Anchorage", "Alaska Time"),
            ("Pacific/Honolulu", "Hawaii Time"),
            ("Europe/London", "London (UK)"),
            ("Europe/Paris", "Paris (France)"),
            ("Europe/Berlin", "Berlin (Germany)"),
            ("Asia/Tokyo", "Tokyo (Japan)"),
            ("Asia/Shanghai", "Shanghai (China)"),
            ("Australia/Sydney", "Sydney (Australia)"),
            ("UTC", "UTC"),
        ]
        self.fields["timezone"].widget = forms.Select(
            choices=common_timezones,
            attrs={"class": "form-select"},
        )

        # Load coaching style choices from database
        try:
            from apps.ai.models import CoachingStyle
            coaching_choices = [
                (style.key, f"{style.name} - {style.description}")
                for style in CoachingStyle.get_active_styles()
            ]
            if coaching_choices:
                self.fields["ai_coaching_style"].widget = forms.Select(
                    choices=coaching_choices,
                    attrs={"class": "form-select"},
                )
        except Exception:
            # Fallback if CoachingStyle table doesn't exist yet
            fallback_choices = [
                ('gentle', 'Gentle Guide'),
                ('supportive', 'Supportive Partner'),
                ('direct', 'Direct Coach'),
            ]
            self.fields["ai_coaching_style"].widget = forms.Select(
                choices=fallback_choices,
                attrs={"class": "form-select"},
            )

        # CoS response style widget
        from apps.users.models import UserPreferences
        self.fields["cos_response_style"].widget = forms.Select(
            choices=UserPreferences.COS_RESPONSE_STYLE_CHOICES,
            attrs={"class": "form-select"},
        )

    def clean(self):
        """Validate form data, especially macro percentages."""
        cleaned_data = super().clean()

        # Validate macro percentages sum to 100% if all are provided
        protein = cleaned_data.get('protein_percentage')
        carbs = cleaned_data.get('carbs_percentage')
        fat = cleaned_data.get('fat_percentage')

        # If any macro percentage is set, encourage setting all of them
        if any([protein, carbs, fat]) and not all([protein, carbs, fat]):
            # Don't error, just allow partial entry
            pass
        elif all([protein, carbs, fat]):
            total = protein + carbs + fat
            if total != 100:
                raise forms.ValidationError(
                    f"Macro percentages must add up to 100%. Current total: {total}%"
                )

        return cleaned_data
