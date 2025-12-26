"""
Users Forms - Profile and preferences editing.
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
            "avatar": "Upload a profile picture (JPG, PNG, GIF). Max 2MB.",
        }
    
    def clean_avatar(self):
        avatar = self.cleaned_data.get('avatar')
        if avatar:
            # Check file size (2MB limit)
            if avatar.size > 2 * 1024 * 1024:
                raise forms.ValidationError("Image file too large. Maximum size is 2MB.")
            # Check file type
            if not avatar.content_type.startswith('image/'):
                raise forms.ValidationError("Please upload an image file.")
        return avatar
    
    def save(self, commit=True):
        user = super().save(commit=False)
        
        # Handle clear avatar checkbox
        if self.cleaned_data.get('clear_avatar'):
            # Delete old avatar file if it exists
            if user.avatar:
                user.avatar.delete(save=False)
            user.avatar = None
        
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
            'ai_coaching_style',
            # Location
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
