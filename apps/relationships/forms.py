"""
Whole Life Journey - Relationships Forms

Project: Whole Life Journey
Path: apps/relationships/forms.py
Purpose: Forms for Person CRUD operations

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

from django import forms

from .models import Person, PersonGroup


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


class PersonGroupForm(forms.ModelForm):
    """Form for creating/editing a PersonGroup."""

    members = forms.ModelMultipleChoiceField(
        queryset=Person.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Members",
    )

    class Meta:
        model = PersonGroup
        fields = ['name', 'description', 'members']
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'Group name',
                'autofocus': True,
            }),
            'description': forms.Textarea(attrs={
                'placeholder': 'Description (optional)',
                'rows': 2,
            }),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user:
            self.fields['members'].queryset = (
                Person.objects.filter(owner=user).order_by('first_name', 'last_name')
            )

    def clean_name(self):
        name = self.cleaned_data['name']
        qs = PersonGroup.objects.filter(owner=self.user, name__iexact=name)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f'A group named "{name}" already exists.')
        return name


class ContactImportForm(forms.Form):
    """Form for uploading a vCard (.vcf) file to import contacts."""

    file = forms.FileField(
        label="Contacts File",
        help_text="Upload a .vcf (vCard) file exported from your phone's Contacts app",
        widget=forms.FileInput(attrs={
            "accept": ".vcf",
            "class": "form-input",
        }),
    )

    def clean_file(self):
        f = self.cleaned_data.get("file")
        if f:
            if not f.name.lower().endswith(".vcf"):
                raise forms.ValidationError("Only .vcf (vCard) files are supported.")
            if f.size > 10 * 1024 * 1024:
                raise forms.ValidationError("File too large. Maximum size is 10MB.")
        return f
