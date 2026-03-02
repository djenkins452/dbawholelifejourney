"""
Whole Life Journey - Relationships Forms

Project: Whole Life Journey
Path: apps/relationships/forms.py
Purpose: Forms for Person CRUD operations

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

from django import forms

from .models import Person


class PersonForm(forms.ModelForm):
    """Form for creating/editing a Person contact."""

    class Meta:
        model = Person
        fields = [
            'first_name', 'last_name', 'email', 'phone',
            'relationship_type', 'notes', 'household',
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={
                'placeholder': 'First name',
                'autofocus': True,
            }),
            'last_name': forms.TextInput(attrs={
                'placeholder': 'Last name (optional)',
            }),
            'email': forms.EmailInput(attrs={
                'placeholder': 'Email (optional)',
            }),
            'phone': forms.TextInput(attrs={
                'placeholder': 'Phone (optional)',
            }),
            'notes': forms.Textarea(attrs={
                'placeholder': 'Notes about this person...',
                'rows': 3,
            }),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        # Limit household choices to user's households
        if user:
            from apps.meals.models import HouseholdMembership
            household_ids = HouseholdMembership.objects.filter(
                user=user,
            ).values_list('household_id', flat=True)
            self.fields['household'].queryset = (
                self.fields['household'].queryset.filter(pk__in=household_ids)
            )
            # If no households, hide the field
            if not household_ids:
                self.fields['household'].widget = forms.HiddenInput()


class QuickPersonForm(forms.ModelForm):
    """Minimal form for inline person creation from autocomplete."""

    class Meta:
        model = Person
        fields = ['first_name', 'last_name', 'relationship_type']
        widgets = {
            'first_name': forms.TextInput(attrs={'placeholder': 'First name'}),
            'last_name': forms.TextInput(attrs={'placeholder': 'Last name'}),
        }
