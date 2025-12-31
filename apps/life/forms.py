# ==============================================================================
# File: forms.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Forms for life module - significant events
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-31
# Last Updated: 2025-12-31
# ==============================================================================
"""
Life Forms - Forms for life module models.
"""

from django import forms

from .models import SignificantEvent


# Reminder days options for checkbox selection
REMINDER_DAYS_CHOICES = [
    (14, '14 days before'),
    (7, '7 days before (1 week)'),
    (3, '3 days before'),
    (1, '1 day before'),
    (0, 'Day of event'),
]


class SignificantEventForm(forms.ModelForm):
    """
    Form for creating and editing significant events (birthdays, anniversaries, etc.).
    """

    # Multi-select checkbox for reminder days
    reminder_days_choices = forms.MultipleChoiceField(
        choices=REMINDER_DAYS_CHOICES,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'reminder-checkbox'}),
        required=False,
        label="Remind me"
    )

    class Meta:
        model = SignificantEvent
        fields = [
            'title',
            'event_type',
            'event_date',
            'original_year',
            'person_name',
            'description',
            'sms_reminder_enabled',
            'custom_message',
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': "e.g., Mom's Birthday"
            }),
            'event_type': forms.Select(attrs={
                'class': 'form-control'
            }),
            'event_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'original_year': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., 1999 (for calculating years)',
                'min': 1900,
                'max': 2100
            }),
            'person_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': "e.g., Mom, John & Jane"
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Optional notes about this event'
            }),
            'sms_reminder_enabled': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'custom_message': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'e.g., Gift ideas: Books, flowers'
            }),
        }
        labels = {
            'title': 'Event Title',
            'event_type': 'Event Type',
            'event_date': 'Date',
            'original_year': 'Original Year (optional)',
            'person_name': 'Person / People (optional)',
            'description': 'Notes',
            'sms_reminder_enabled': 'Enable SMS Reminders',
            'custom_message': 'Custom Reminder Message',
        }
        help_texts = {
            'event_date': 'The date of the event. Year is used to calculate age/anniversary years.',
            'original_year': 'For calculating "years since" (e.g., birth year for age, wedding year for anniversary).',
            'person_name': 'Who this event is for. Used in SMS messages.',
            'custom_message': 'Added to SMS reminders. Good for gift ideas or notes.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # If editing an existing event, pre-populate the reminder days checkboxes
        if self.instance and self.instance.pk:
            # Convert stored list to string values for the checkbox field
            stored_days = self.instance.reminder_days or []
            self.initial['reminder_days_choices'] = [str(d) for d in stored_days]

    def clean_reminder_days_choices(self):
        """Convert selected checkbox values to integers for storage."""
        values = self.cleaned_data.get('reminder_days_choices', [])
        return [int(v) for v in values]

    def save(self, commit=True):
        """Save the form, converting reminder_days_choices to the model field."""
        instance = super().save(commit=False)

        # Store the selected reminder days as a list
        instance.reminder_days = self.cleaned_data.get('reminder_days_choices', [])

        if commit:
            instance.save()

        return instance
