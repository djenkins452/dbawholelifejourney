"""
Faith Forms - Prayer requests, milestones, and saved verses.
"""

from django import forms

from .models import FaithMilestone, PrayerRequest, SavedVerse


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


class SavedVerseForm(forms.ModelForm):
    """
    Form for editing saved Scripture verses.
    """

    themes_text = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-input",
            "placeholder": "e.g., faith, hope, love (comma-separated)",
        }),
        label="Themes",
        help_text="Add themes to help organize your verses (comma-separated)",
    )

    class Meta:
        model = SavedVerse
        fields = [
            "reference",
            "text",
            "translation",
            "notes",
        ]
        widgets = {
            "reference": forms.TextInput(attrs={
                "class": "form-input",
            }),
            "text": forms.Textarea(attrs={
                "class": "form-textarea",
                "rows": 4,
            }),
            "translation": forms.Select(attrs={
                "class": "form-select",
            }),
            "notes": forms.Textarea(attrs={
                "class": "form-textarea",
                "placeholder": "What does this verse mean to you?",
                "rows": 3,
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Convert themes list to comma-separated string for editing
        if self.instance and self.instance.pk and self.instance.themes:
            self.initial["themes_text"] = ", ".join(self.instance.themes)

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Convert comma-separated themes back to list
        themes_str = self.cleaned_data.get("themes_text", "")
        instance.themes = [t.strip() for t in themes_str.split(",") if t.strip()]
        if commit:
            instance.save()
        return instance
