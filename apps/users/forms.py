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

from django import forms
from django.contrib.auth import get_user_model

from .models import UserPreferences

User = get_user_model()


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

    class Meta:
        model = UserPreferences
        fields = [
            "theme",
            "accent_color",
            # Module toggles
            "journal_enabled",
            "faith_enabled",
            "health_enabled",
            "life_enabled",
            "purpose_enabled",
            "goals_enabled",
            "finances_enabled",
            "relationships_enabled",
            "habits_enabled",
            # AI
            "ai_enabled",
            "ai_data_consent",
            'ai_coaching_style',
            'ai_profile',
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
            # Weight Goals
            "weight_goal",
            "weight_goal_unit",
            "weight_goal_target_date",
            # Nutrition Goals
            "daily_calorie_goal",
            "protein_percentage",
            "carbs_percentage",
            "fat_percentage",
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
            "relationships_enabled": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "habits_enabled": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "ai_enabled": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "ai_data_consent": forms.CheckboxInput(attrs={
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
            # Weight Goals
            "weight_goal": forms.NumberInput(attrs={
                "class": "form-input",
                "placeholder": "Target weight",
                "step": "0.1",
                "min": "50",
                "max": "500",
            }),
            "weight_goal_unit": forms.Select(attrs={
                "class": "form-select",
            }),
            "weight_goal_target_date": forms.DateInput(attrs={
                "class": "form-input",
                "type": "date",
            }),
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
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Generate timezone choices
        common_timezones = [
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
