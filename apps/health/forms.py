"""
Health Forms - Entry forms for health metrics.
"""

import pytz
from django import forms
from django.utils import timezone

from .models import FastingWindow, GlucoseEntry, HeartRateEntry, WeightEntry


def get_user_timezone(user):
    """Get user's timezone as a pytz timezone object."""
    if not user:
        return pytz.UTC
    try:
        tz_name = user.preferences.timezone or "UTC"
        return pytz.timezone(tz_name)
    except (AttributeError, pytz.UnknownTimeZoneError):
        return pytz.UTC


def get_local_now_string(user=None):
    """
    Get current datetime as a string formatted for datetime-local input.
    Uses user's timezone if available, otherwise UTC.
    """
    now = timezone.now()
    user_tz = get_user_timezone(user)
    local_now = now.astimezone(user_tz)
    # Format for datetime-local input (YYYY-MM-DDTHH:MM)
    return local_now.strftime("%Y-%m-%dT%H:%M")


def interpret_as_user_timezone(dt, user):
    """
    Interpret a datetime as being in the user's timezone and convert to UTC.
    
    The datetime-local input sends a time like "2025-12-25T17:42" which Django
    interprets as UTC. But the user meant it as their local time. So we need to:
    1. Strip any timezone info (treat as naive)
    2. Localize to user's timezone
    3. Convert to UTC
    """
    if dt is None:
        return None
    
    user_tz = get_user_timezone(user)
    
    # Strip timezone info to get naive datetime with same numbers
    # e.g., 17:42+00:00 becomes naive 17:42
    if timezone.is_aware(dt):
        naive_dt = dt.replace(tzinfo=None)
    else:
        naive_dt = dt
    
    # Now localize to user's timezone (17:42 Eastern)
    local_dt = user_tz.localize(naive_dt)
    
    # Convert to UTC (17:42 Eastern = 22:42 UTC)
    utc_dt = local_dt.astimezone(pytz.UTC)
    
    return utc_dt


class WeightEntryForm(forms.ModelForm):
    """
    Form for logging weight.
    """

    class Meta:
        model = WeightEntry
        fields = ["value", "unit", "recorded_at", "notes"]
        widgets = {
            "value": forms.NumberInput(attrs={
                "class": "form-input",
                "placeholder": "Enter weight",
                "step": "0.1",
            }),
            "unit": forms.Select(attrs={
                "class": "form-select",
            }),
            "recorded_at": forms.DateTimeInput(attrs={
                "class": "form-input",
                "type": "datetime-local",
            }),
            "notes": forms.Textarea(attrs={
                "class": "form-textarea",
                "placeholder": "Any notes? (optional)",
                "rows": 2,
            }),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        # Always set default for new entries
        if not self.instance.pk:
            self.initial["recorded_at"] = get_local_now_string(user)
    
    def clean_recorded_at(self):
        """Convert datetime from user's timezone to UTC."""
        recorded_at = self.cleaned_data.get('recorded_at')
        return interpret_as_user_timezone(recorded_at, self.user)


class QuickWeightForm(forms.ModelForm):
    """
    Simplified weight form for quick logging.
    """

    class Meta:
        model = WeightEntry
        fields = ["value", "unit"]
        widgets = {
            "value": forms.NumberInput(attrs={
                "class": "form-input",
                "placeholder": "Weight",
                "step": "0.1",
            }),
            "unit": forms.Select(attrs={
                "class": "form-select",
            }),
        }


class FastingWindowForm(forms.ModelForm):
    """
    Form for starting/editing a fasting window.
    """

    class Meta:
        model = FastingWindow
        fields = ["fasting_type", "started_at", "ended_at", "notes"]
        widgets = {
            "fasting_type": forms.Select(attrs={
                "class": "form-select",
            }),
            "started_at": forms.DateTimeInput(attrs={
                "class": "form-input",
                "type": "datetime-local",
            }),
            "ended_at": forms.DateTimeInput(attrs={
                "class": "form-input",
                "type": "datetime-local",
            }),
            "notes": forms.Textarea(attrs={
                "class": "form-textarea",
                "placeholder": "Any notes? (optional)",
                "rows": 2,
            }),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ended_at"].required = False
        self.user = user
        
        # Set timezone-aware default for started_at
        if not self.instance.pk:
            self.initial["started_at"] = get_local_now_string(user)
    
    def clean_started_at(self):
        """Convert datetime from user's timezone to UTC."""
        started_at = self.cleaned_data.get('started_at')
        return interpret_as_user_timezone(started_at, self.user)
    
    def clean_ended_at(self):
        """Convert datetime from user's timezone to UTC."""
        ended_at = self.cleaned_data.get('ended_at')
        return interpret_as_user_timezone(ended_at, self.user)


class HeartRateEntryForm(forms.ModelForm):
    """
    Form for logging heart rate.
    """

    class Meta:
        model = HeartRateEntry
        fields = ["bpm", "context", "recorded_at", "notes"]
        widgets = {
            "bpm": forms.NumberInput(attrs={
                "class": "form-input",
                "placeholder": "BPM",
                "min": 30,
                "max": 250,
            }),
            "context": forms.Select(attrs={
                "class": "form-select",
            }),
            "recorded_at": forms.DateTimeInput(attrs={
                "class": "form-input",
                "type": "datetime-local",
            }),
            "notes": forms.Textarea(attrs={
                "class": "form-textarea",
                "placeholder": "Any notes? (optional)",
                "rows": 2,
            }),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        # Always set default for new entries
        if not self.instance.pk:
            self.initial["recorded_at"] = get_local_now_string(user)
    
    def clean_recorded_at(self):
        """Convert datetime from user's timezone to UTC."""
        recorded_at = self.cleaned_data.get('recorded_at')
        return interpret_as_user_timezone(recorded_at, self.user)


class GlucoseEntryForm(forms.ModelForm):
    """
    Form for logging blood glucose.
    """

    class Meta:
        model = GlucoseEntry
        fields = ["value", "unit", "context", "recorded_at", "notes"]
        widgets = {
            "value": forms.NumberInput(attrs={
                "class": "form-input",
                "placeholder": "Glucose reading",
                "step": "0.1",
            }),
            "unit": forms.Select(attrs={
                "class": "form-select",
            }),
            "context": forms.Select(attrs={
                "class": "form-select",
            }),
            "recorded_at": forms.DateTimeInput(attrs={
                "class": "form-input",
                "type": "datetime-local",
            }),
            "notes": forms.Textarea(attrs={
                "class": "form-textarea",
                "placeholder": "Any notes? (optional)",
                "rows": 2,
            }),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        # Always set default for new entries
        if not self.instance.pk:
            self.initial["recorded_at"] = get_local_now_string(user)
    
    def clean_recorded_at(self):
        """Convert datetime from user's timezone to UTC."""
        recorded_at = self.cleaned_data.get('recorded_at')
        return interpret_as_user_timezone(recorded_at, self.user)