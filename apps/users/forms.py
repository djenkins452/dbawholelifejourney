"""
Users Forms - Profile and preferences editing.
"""

from django import forms
from django.contrib.auth import get_user_model

from .models import UserPreferences

User = get_user_model()


class ProfileForm(forms.ModelForm):
    """
    Form for editing user profile (name, email).
    """

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]
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
        }


class PreferencesForm(forms.ModelForm):
    """
    Form for editing user preferences.
    """

    class Meta:
        model = UserPreferences
        fields = [
            "theme",
            "accent_color",
            "faith_enabled",
            "ai_enabled",
            "location_city",
            "location_country",
            "timezone",
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
            "faith_enabled": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "ai_enabled": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
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
        }
        help_texts = {
            "faith_enabled": "Enable the Faith module and faith-aware content throughout the app.",
            "ai_enabled": "Enable AI-powered insights and reflections based on your entries.",
            "accent_color": "Leave blank to use the theme's default accent color.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Generate timezone choices
        import pytz
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
