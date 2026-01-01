# ==============================================================================
# File: forms.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Forms for faith module - prayer requests, milestones, saved verses,
#              reading plans, and Bible study tools
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2024-01-01
# Last Updated: 2026-01-01
# ==============================================================================
"""
Faith Forms - Prayer requests, milestones, saved verses, reading plans,
and Bible study tools (highlights, bookmarks, notes).
"""

from django import forms

from apps.core.utils import get_user_today

from .models import (
    BibleBookmark,
    BibleHighlight,
    BibleStudyNote,
    FaithMilestone,
    PrayerRequest,
    SavedVerse,
    UserReadingPlan,
    UserReadingProgress,
)


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

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        # Set default date to user's local date for new entries
        if not self.instance.pk and user:
            self.initial["date"] = get_user_today(user)


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


# =============================================================================
# READING PLAN FORMS
# =============================================================================


class StartReadingPlanForm(forms.Form):
    """
    Form for starting a new reading plan.

    User can optionally set a daily reminder time.
    """

    reminder_time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={
            "class": "form-input",
            "type": "time",
        }),
        label="Daily Reminder Time",
        help_text="Optional: Set a time to be reminded to complete your daily reading",
    )


class ReadingProgressForm(forms.ModelForm):
    """
    Form for recording notes on a reading plan day.
    """

    class Meta:
        model = UserReadingProgress
        fields = ["notes"]
        widgets = {
            "notes": forms.Textarea(attrs={
                "class": "form-textarea",
                "placeholder": "What stood out to you in today's reading?",
                "rows": 4,
            }),
        }
        labels = {
            "notes": "Reflection Notes",
        }


# =============================================================================
# BIBLE STUDY TOOLS FORMS
# =============================================================================


class BibleHighlightForm(forms.ModelForm):
    """
    Form for creating and editing Bible highlights.
    """

    class Meta:
        model = BibleHighlight
        fields = [
            "reference",
            "text",
            "translation",
            "color",
        ]
        widgets = {
            "reference": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "e.g., John 3:16",
            }),
            "text": forms.Textarea(attrs={
                "class": "form-textarea",
                "placeholder": "The verse text to highlight...",
                "rows": 3,
            }),
            "translation": forms.Select(attrs={
                "class": "form-select",
            }),
            "color": forms.Select(attrs={
                "class": "form-select",
            }),
        }


class BibleBookmarkForm(forms.ModelForm):
    """
    Form for creating and editing Bible bookmarks.
    """

    class Meta:
        model = BibleBookmark
        fields = [
            "reference",
            "translation",
            "title",
            "notes",
        ]
        widgets = {
            "reference": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "e.g., Psalm 23 or Romans 8:28",
            }),
            "translation": forms.Select(attrs={
                "class": "form-select",
            }),
            "title": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "Optional label (e.g., 'My favorite psalm')",
            }),
            "notes": forms.Textarea(attrs={
                "class": "form-textarea",
                "placeholder": "Why are you bookmarking this passage?",
                "rows": 3,
            }),
        }


class BibleStudyNoteForm(forms.ModelForm):
    """
    Form for creating and editing Bible study notes.
    """

    tags_text = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-input",
            "placeholder": "e.g., theology, application, context (comma-separated)",
        }),
        label="Tags",
        help_text="Add tags to help organize your notes (comma-separated)",
    )

    class Meta:
        model = BibleStudyNote
        fields = [
            "reference",
            "translation",
            "title",
            "content",
        ]
        widgets = {
            "reference": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "e.g., John 3:16-21",
            }),
            "translation": forms.Select(attrs={
                "class": "form-select",
            }),
            "title": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "Optional title for this note",
            }),
            "content": forms.Textarea(attrs={
                "class": "form-textarea",
                "placeholder": "Your study notes...",
                "rows": 8,
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Convert tags list to comma-separated string for editing
        if self.instance and self.instance.pk and self.instance.tags:
            self.initial["tags_text"] = ", ".join(self.instance.tags)

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Convert comma-separated tags back to list
        tags_str = self.cleaned_data.get("tags_text", "")
        instance.tags = [t.strip() for t in tags_str.split(",") if t.strip()]
        if commit:
            instance.save()
        return instance
