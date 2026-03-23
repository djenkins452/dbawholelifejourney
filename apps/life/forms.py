# ==============================================================================
# File: forms.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Forms for life module - significant events
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2025-12-31
# Last Updated: 2025-12-31
# ==============================================================================
"""
Life Forms - Forms for life module models.
"""

from django import forms
from django.forms import inlineformset_factory

from .models import Routine, RoutineSchedule, SignificantEvent


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


# =============================================================================
# Routine Forms
# =============================================================================

DAYS_OF_WEEK_CHOICES = [
    ('0', 'Mon'),
    ('1', 'Tue'),
    ('2', 'Wed'),
    ('3', 'Thu'),
    ('4', 'Fri'),
    ('5', 'Sat'),
    ('6', 'Sun'),
]


class RoutineForm(forms.ModelForm):
    """Form for creating and editing routines."""

    class Meta:
        model = Routine
        fields = ['name', 'description', 'time_of_day', 'is_active', 'sort_order']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g., Morning Routine',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 2,
                'placeholder': 'Optional description',
            }),
            'time_of_day': forms.Select(attrs={'class': 'form-select'}),
            'sort_order': forms.NumberInput(attrs={
                'class': 'form-input',
                'min': 0,
                'style': 'width: 80px;',
            }),
        }
        labels = {
            'time_of_day': 'Time Window',
            'sort_order': 'Order',
            'is_active': 'Active',
        }


class RoutineScheduleForm(forms.ModelForm):
    """Form for a single routine schedule item."""

    active_days = forms.MultipleChoiceField(
        choices=DAYS_OF_WEEK_CHOICES,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'day-checkbox'}),
        required=False,
        label='Days',
    )

    class Meta:
        model = RoutineSchedule
        fields = [
            'name', 'importance', 'scheduled_time', 'grace_period_minutes',
            'is_active', 'sort_order',
            # Activity type (Phase 2)
            'routine_type', 'activity_type',
            # Maintenance bridge
            'creates_maintenance_log', 'maintenance_type', 'maintenance_area',
            'default_maintenance_title', 'follow_up_days',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g., Prayer time',
            }),
            'importance': forms.Select(attrs={
                'class': 'form-select',
            }),
            'scheduled_time': forms.TimeInput(attrs={
                'class': 'form-input',
                'type': 'time',
            }),
            'grace_period_minutes': forms.NumberInput(attrs={
                'class': 'form-input',
                'min': 0,
                'style': 'width: 80px;',
            }),
            'sort_order': forms.NumberInput(attrs={
                'class': 'form-input',
                'min': 0,
                'style': 'width: 80px;',
            }),
            # Activity type widgets
            'routine_type': forms.Select(attrs={
                'class': 'form-select routine-type-select',
            }),
            'activity_type': forms.Select(attrs={
                'class': 'form-select activity-type-select',
            }),
            # Maintenance bridge widgets
            'creates_maintenance_log': forms.CheckboxInput(attrs={
                'class': 'maintenance-bridge-toggle',
            }),
            'maintenance_type': forms.Select(attrs={
                'class': 'form-select',
            }),
            'maintenance_area': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g., HVAC, Jeep, Yard',
            }),
            'default_maintenance_title': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Override title (optional)',
            }),
            'follow_up_days': forms.NumberInput(attrs={
                'class': 'form-input',
                'min': 1,
                'style': 'width: 100px;',
                'placeholder': 'days',
            }),
        }
        labels = {
            'importance': 'Priority',
            'grace_period_minutes': 'Grace (min)',
            'sort_order': 'Order',
            'is_active': 'Active',
            'routine_type': 'Type',
            'activity_type': 'Activity Source',
            'creates_maintenance_log': 'Creates maintenance log',
            'maintenance_type': 'Type',
            'maintenance_area': 'Area',
            'default_maintenance_title': 'Title',
            'follow_up_days': 'Follow-up (days)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pre-populate active_days from days_of_week field
        if self.instance and self.instance.pk and self.instance.days_of_week:
            self.initial['active_days'] = [
                d.strip() for d in self.instance.days_of_week.split(',') if d.strip()
            ]
        elif not self.instance.pk:
            # Default: all days selected for new items
            self.initial['active_days'] = ['0', '1', '2', '3', '4', '5', '6']
            # is_active checkbox is not rendered for new items (only during edit),
            # so POSTed value will be False. Match initial to avoid has_changed()
            # false positive that triggers validation on the empty extra form.
            self.initial['is_active'] = False

    def save(self, commit=True):
        instance = super().save(commit=False)
        active_days = self.cleaned_data.get('active_days', [])
        instance.days_of_week = ','.join(sorted(active_days))
        # is_active checkbox is not rendered for new items (only during edit),
        # so form binding sets it to False. Force True for new schedule items.
        if not instance.pk:
            instance.is_active = True
        if commit:
            instance.save()
        return instance


RoutineScheduleFormSet = inlineformset_factory(
    Routine,
    RoutineSchedule,
    form=RoutineScheduleForm,
    extra=0,
    can_delete=True,
    min_num=0,
    validate_min=False,
)
