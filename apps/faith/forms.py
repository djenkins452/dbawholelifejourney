"""
Faith Forms - Prayer requests and milestones.
"""

from django import forms

from .models import FaithMilestone, PrayerRequest


class PrayerRequestForm(forms.ModelForm):
    """
    Form for creating and editing prayer requests.
    """

    class Meta:
        model = PrayerRequest
        fields = [
            "title",
            "description",
            "is_personal",
            "person_or_situation",
            "priority",
            "remind_daily",
        ]
        widgets = {
            "title": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "What would you like to pray for?",
            }),
            "description": forms.Textarea(attrs={
                "class": "form-textarea",
                "placeholder": "Add details about this prayer request...",
                "rows": 4,
            }),
            "is_personal": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "person_or_situation": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "Person or situation you're praying for",
            }),
            "priority": forms.Select(attrs={
                "class": "form-select",
            }),
            "remind_daily": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
        }
        labels = {
            "is_personal": "This is a personal prayer",
            "remind_daily": "Include in daily prayer reminders",
        }


class MarkAnsweredForm(forms.Form):
    """
    Form for marking a prayer as answered.
    """

    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            "class": "form-textarea",
            "placeholder": "How did God answer this prayer?",
            "rows": 4,
        }),
        label="Answer Notes",
    )


class FaithMilestoneForm(forms.ModelForm):
    """
    Form for creating and editing faith milestones.
    """

    class Meta:
        model = FaithMilestone
        fields = [
            "title",
            "milestone_type",
            "date",
            "description",
            "scripture_reference",
        ]
        widgets = {
            "title": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "Name this moment",
            }),
            "milestone_type": forms.Select(attrs={
                "class": "form-select",
            }),
            "date": forms.DateInput(attrs={
                "class": "form-input",
                "type": "date",
            }),
            "description": forms.Textarea(attrs={
                "class": "form-textarea",
                "placeholder": "Describe this moment in your faith journey...",
                "rows": 6,
            }),
            "scripture_reference": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "e.g., Romans 8:28",
            }),
        }
