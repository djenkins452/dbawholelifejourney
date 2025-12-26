"""
Journal Forms
"""

from django import forms

from apps.core.models import Category, Tag

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
                "placeholder": "Entry title",
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
