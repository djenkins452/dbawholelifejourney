"""
Health Forms - Entry forms for health metrics.
"""

from django import forms
from django.utils import timezone

from .models import FastingWindow, GlucoseEntry, HeartRateEntry, WeightEntry


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.initial["recorded_at"] = timezone.now()


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ended_at"].required = False


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.initial["recorded_at"] = timezone.now()


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.initial["recorded_at"] = timezone.now()
