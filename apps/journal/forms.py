# ==============================================================================
# File: forms.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Forms for journal entry creation and editing
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2024-01-01
# Last Updated: 2025-12-29
# ==============================================================================
"""
Journal Forms
"""

from django import forms

from apps.core.models import Category, Tag
from apps.core.utils import get_user_today

from .models import JournalEntry


class JournalEntryForm(forms.ModelForm):
    """
    Form for creating and editing journal entries.
    """

    class Meta:
        model = JournalEntry
        fields = [
            "title",
            "body",
            "entry_date",
            "mood",
            "categories",
            "tags",
        ]
        widgets = {
            "title": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "Leave blank to use the date",
            }),
            "body": forms.Textarea(attrs={
                "class": "form-textarea",
                "placeholder": "Write your thoughts...",
                "rows": 12,
            }),
            "entry_date": forms.DateInput(attrs={
                "class": "form-input",
                "type": "date",
            }),
            "mood": forms.Select(attrs={
                "class": "form-select",
            }),
            "categories": forms.CheckboxSelectMultiple(attrs={
                "class": "form-checkbox-group",
            }),
            "tags": forms.CheckboxSelectMultiple(attrs={
                "class": "form-checkbox-group",
            }),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        # Make title optional - will default to date if empty
        self.fields["title"].required = False

        # Add empty choice for mood
        self.fields["mood"].choices = [("", "Select mood (optional)")] + list(
            JournalEntry.MOOD_CHOICES
        )
        self.fields["mood"].required = False

        # Filter tags to only show user's tags
        if user:
            self.fields["tags"].queryset = Tag.objects.filter(user=user)

        # Make categories and tags optional
        self.fields["categories"].required = False
        self.fields["tags"].required = False

        # Set default entry_date to user's local date for new entries
        if not self.instance.pk and user:
            self.initial["entry_date"] = get_user_today(user)


class TagForm(forms.ModelForm):
    """
    Form for creating custom tags.
    """

    class Meta:
        model = Tag
        fields = ["name", "color"]
        widgets = {
            "name": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "Tag name",
            }),
            "color": forms.TextInput(attrs={
                "class": "form-input",
                "type": "color",
            }),
        }