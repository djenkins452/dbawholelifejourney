"""
Whole Life Journey - Notes Forms

Project: Whole Life Journey
Path: apps/notes/forms.py
Purpose: Form for creating and editing notes
"""

from django import forms

from apps.core.models import Tag

from .models import Note


class NoteForm(forms.ModelForm):
    """Form for creating and editing notes."""

    class Meta:
        model = Note
        fields = ["title", "body", "color", "is_pinned", "tags"]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Title (optional — auto-generated if blank)",
                }
            ),
            "body": forms.Textarea(
                attrs={
                    "class": "form-textarea",
                    "placeholder": "Write your note...",
                    "rows": 8,
                }
            ),
            "color": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
            "is_pinned": forms.CheckboxInput(
                attrs={
                    "class": "form-checkbox",
                }
            ),
            "tags": forms.CheckboxSelectMultiple(
                attrs={
                    "class": "form-checkbox-group",
                }
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["title"].required = False
        self.fields["tags"].required = False
        if user:
            self.fields["tags"].queryset = Tag.objects.filter(user=user)
