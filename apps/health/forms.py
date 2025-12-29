"""
Health Forms - Entry forms for health metrics.
"""

import pytz
from django import forms
from django.utils import timezone

from .models import (
    CustomFood,
    DailyNutritionSummary,
    FastingWindow,
    FoodEntry,
    FoodItem,
    GlucoseEntry,
    HeartRateEntry,
    Medicine,
    MedicineLog,
    MedicineSchedule,
    NutritionGoals,
    WeightEntry,
)


def get_user_timezone(user):
    """Get user's timezone as a pytz timezone object."""
    if not user:
        return pytz.UTC
    try:
        tz_name = user.preferences.timezone or "UTC"
        return pytz.timezone(tz_name)
    except (AttributeError, pytz.UnknownTimeZoneError):
        return pytz.UTC


def get_local_now_string(user=None):
    """
    Get current datetime as a string formatted for datetime-local input.
    Uses user's timezone if available, otherwise UTC.
    """
    now = timezone.now()
    user_tz = get_user_timezone(user)
    local_now = now.astimezone(user_tz)
    # Format for datetime-local input (YYYY-MM-DDTHH:MM)
    return local_now.strftime("%Y-%m-%dT%H:%M")


def interpret_as_user_timezone(dt, user):
    """
    Interpret a datetime as being in the user's timezone and convert to UTC.
    
    The datetime-local input sends a time like "2025-12-25T17:42" which Django
    interprets as UTC. But the user meant it as their local time. So we need to:
    1. Strip any timezone info (treat as naive)
    2. Localize to user's timezone
    3. Convert to UTC
    """
    if dt is None:
        return None
    
    user_tz = get_user_timezone(user)
    
    # Strip timezone info to get naive datetime with same numbers
    # e.g., 17:42+00:00 becomes naive 17:42
    if timezone.is_aware(dt):
        naive_dt = dt.replace(tzinfo=None)
    else:
        naive_dt = dt
    
    # Now localize to user's timezone (17:42 Eastern)
    local_dt = user_tz.localize(naive_dt)
    
    # Convert to UTC (17:42 Eastern = 22:42 UTC)
    utc_dt = local_dt.astimezone(pytz.UTC)
    
    return utc_dt


class WeightEntryForm(forms.ModelForm):
    """
    Form for logging weight.
    """

    class Meta:
        model = WeightEntry
        fields = ["value", "unit", "recorded_at", "notes"]
        widgets = {
            "value": forms.NumberInput(attrs={
                "class": "form-input",
                "placeholder": "Enter weight",
                "step": "0.1",
            }),
            "unit": forms.Select(attrs={
                "class": "form-select",
            }),
            "recorded_at": forms.DateTimeInput(attrs={
                "class": "form-input",
                "type": "datetime-local",
            }),
            "notes": forms.Textarea(attrs={
                "class": "form-textarea",
                "placeholder": "Any notes? (optional)",
                "rows": 2,
            }),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        # Always set default for new entries
        if not self.instance.pk:
            self.initial["recorded_at"] = get_local_now_string(user)
    
    def clean_recorded_at(self):
        """Convert datetime from user's timezone to UTC."""
        recorded_at = self.cleaned_data.get('recorded_at')
        return interpret_as_user_timezone(recorded_at, self.user)


class QuickWeightForm(forms.ModelForm):
    """
    Simplified weight form for quick logging.
    """

    class Meta:
        model = WeightEntry
        fields = ["value", "unit"]
        widgets = {
            "value": forms.NumberInput(attrs={
                "class": "form-input",
                "placeholder": "Weight",
                "step": "0.1",
            }),
            "unit": forms.Select(attrs={
                "class": "form-select",
            }),
        }


class FastingWindowForm(forms.ModelForm):
    """
    Form for starting/editing a fasting window.
    """

    class Meta:
        model = FastingWindow
        fields = ["fasting_type", "started_at", "ended_at", "notes"]
        widgets = {
            "fasting_type": forms.Select(attrs={
                "class": "form-select",
            }),
            "started_at": forms.DateTimeInput(attrs={
                "class": "form-input",
                "type": "datetime-local",
            }),
            "ended_at": forms.DateTimeInput(attrs={
                "class": "form-input",
                "type": "datetime-local",
            }),
            "notes": forms.Textarea(attrs={
                "class": "form-textarea",
                "placeholder": "Any notes? (optional)",
                "rows": 2,
            }),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ended_at"].required = False
        self.user = user

        if self.instance.pk:
            # Editing existing - convert UTC times to user's local timezone for display
            user_tz = get_user_timezone(user)
            if self.instance.started_at:
                local_started = self.instance.started_at.astimezone(user_tz)
                self.initial["started_at"] = local_started.strftime("%Y-%m-%dT%H:%M")
            if self.instance.ended_at:
                local_ended = self.instance.ended_at.astimezone(user_tz)
                self.initial["ended_at"] = local_ended.strftime("%Y-%m-%dT%H:%M")
        else:
            # New entry - set current time as default
            self.initial["started_at"] = get_local_now_string(user)
    
    def clean_started_at(self):
        """Convert datetime from user's timezone to UTC."""
        started_at = self.cleaned_data.get('started_at')
        return interpret_as_user_timezone(started_at, self.user)
    
    def clean_ended_at(self):
        """Convert datetime from user's timezone to UTC."""
        ended_at = self.cleaned_data.get('ended_at')
        return interpret_as_user_timezone(ended_at, self.user)


class HeartRateEntryForm(forms.ModelForm):
    """
    Form for logging heart rate.
    """

    class Meta:
        model = HeartRateEntry
        fields = ["bpm", "context", "recorded_at", "notes"]
        widgets = {
            "bpm": forms.NumberInput(attrs={
                "class": "form-input",
                "placeholder": "BPM",
                "min": 30,
                "max": 250,
            }),
            "context": forms.Select(attrs={
                "class": "form-select",
            }),
            "recorded_at": forms.DateTimeInput(attrs={
                "class": "form-input",
                "type": "datetime-local",
            }),
            "notes": forms.Textarea(attrs={
                "class": "form-textarea",
                "placeholder": "Any notes? (optional)",
                "rows": 2,
            }),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        # Always set default for new entries
        if not self.instance.pk:
            self.initial["recorded_at"] = get_local_now_string(user)
    
    def clean_recorded_at(self):
        """Convert datetime from user's timezone to UTC."""
        recorded_at = self.cleaned_data.get('recorded_at')
        return interpret_as_user_timezone(recorded_at, self.user)


class GlucoseEntryForm(forms.ModelForm):
    """
    Form for logging blood glucose.
    """

    class Meta:
        model = GlucoseEntry
        fields = ["value", "unit", "context", "recorded_at", "notes"]
        widgets = {
            "value": forms.NumberInput(attrs={
                "class": "form-input",
                "placeholder": "Glucose reading",
                "step": "0.1",
            }),
            "unit": forms.Select(attrs={
                "class": "form-select",
            }),
            "context": forms.Select(attrs={
                "class": "form-select",
            }),
            "recorded_at": forms.DateTimeInput(attrs={
                "class": "form-input",
                "type": "datetime-local",
            }),
            "notes": forms.Textarea(attrs={
                "class": "form-textarea",
                "placeholder": "Any notes? (optional)",
                "rows": 2,
            }),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        # Always set default for new entries
        if not self.instance.pk:
            self.initial["recorded_at"] = get_local_now_string(user)

    def clean_recorded_at(self):
        """Convert datetime from user's timezone to UTC."""
        recorded_at = self.cleaned_data.get('recorded_at')
        return interpret_as_user_timezone(recorded_at, self.user)


# =============================================================================
# Medicine Forms
# =============================================================================


class MedicineForm(forms.ModelForm):
    """
    Form for adding/editing a medicine.
    """

    class Meta:
        model = Medicine
        fields = [
            "name",
            "purpose",
            "dose",
            "frequency",
            "is_prn",
            "start_date",
            "end_date",
            "current_supply",
            "refill_threshold",
            "prescribing_doctor",
            "pharmacy",
            "rx_number",
            "instructions",
            "notes",
            "grace_period_minutes",
        ]
        widgets = {
            "name": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "Medicine name (e.g., Lisinopril)",
            }),
            "purpose": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "What is this for? (e.g., blood pressure)",
            }),
            "dose": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "Dose (e.g., 10mg, 1 tablet)",
            }),
            "frequency": forms.Select(attrs={
                "class": "form-select",
            }),
            "is_prn": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
            "start_date": forms.DateInput(attrs={
                "class": "form-input",
                "type": "date",
            }),
            "end_date": forms.DateInput(attrs={
                "class": "form-input",
                "type": "date",
            }),
            "current_supply": forms.NumberInput(attrs={
                "class": "form-input",
                "placeholder": "Number of doses remaining",
                "min": 0,
            }),
            "refill_threshold": forms.NumberInput(attrs={
                "class": "form-input",
                "placeholder": "Alert when supply drops to this level",
                "min": 1,
            }),
            "prescribing_doctor": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "Doctor's name (optional)",
            }),
            "pharmacy": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "Pharmacy name (optional)",
            }),
            "rx_number": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "Prescription number (optional)",
            }),
            "instructions": forms.Textarea(attrs={
                "class": "form-textarea",
                "placeholder": "Special instructions (e.g., take with food)",
                "rows": 2,
            }),
            "notes": forms.Textarea(attrs={
                "class": "form-textarea",
                "placeholder": "Personal notes",
                "rows": 2,
            }),
            "grace_period_minutes": forms.NumberInput(attrs={
                "class": "form-input",
                "min": 0,
                "max": 480,
            }),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        # Set optional fields
        self.fields["purpose"].required = False
        self.fields["end_date"].required = False
        self.fields["current_supply"].required = False
        self.fields["prescribing_doctor"].required = False
        self.fields["pharmacy"].required = False
        self.fields["rx_number"].required = False
        self.fields["instructions"].required = False
        self.fields["notes"].required = False

        # Set default start date for new medicines
        if not self.instance.pk:
            self.initial["start_date"] = timezone.now().date()
            self.initial["refill_threshold"] = 7
            self.initial["grace_period_minutes"] = 60


class MedicineScheduleForm(forms.ModelForm):
    """
    Form for adding/editing a medicine schedule.
    """

    DAYS_CHOICES = [
        (0, "Monday"),
        (1, "Tuesday"),
        (2, "Wednesday"),
        (3, "Thursday"),
        (4, "Friday"),
        (5, "Saturday"),
        (6, "Sunday"),
    ]

    days = forms.MultipleChoiceField(
        choices=DAYS_CHOICES,
        widget=forms.CheckboxSelectMultiple(attrs={
            "class": "form-checkbox-group",
        }),
        required=False,
        help_text="Select which days this schedule applies to",
    )

    class Meta:
        model = MedicineSchedule
        fields = ["scheduled_time", "label", "is_active"]
        widgets = {
            "scheduled_time": forms.TimeInput(attrs={
                "class": "form-input",
                "type": "time",
            }),
            "label": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "e.g., morning, bedtime, with dinner",
            }),
            "is_active": forms.CheckboxInput(attrs={
                "class": "form-checkbox",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["label"].required = False

        # Parse existing days_of_week to pre-select checkboxes
        if self.instance.pk and self.instance.days_of_week:
            self.initial["days"] = [
                str(d) for d in self.instance.days_list
            ]
        else:
            # Default to all days
            self.initial["days"] = ["0", "1", "2", "3", "4", "5", "6"]

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Convert selected days to comma-separated string
        days = self.cleaned_data.get("days", [])
        # If no days selected, default to all days
        if not days:
            days = ["0", "1", "2", "3", "4", "5", "6"]
        instance.days_of_week = ",".join(sorted(days))
        if commit:
            instance.save()
        return instance


class MedicineLogForm(forms.ModelForm):
    """
    Form for logging a medicine dose.
    """

    class Meta:
        model = MedicineLog
        fields = ["log_status", "prn_reason", "notes"]
        widgets = {
            "log_status": forms.Select(attrs={
                "class": "form-select",
            }),
            "prn_reason": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "Reason for taking (for PRN medicines)",
            }),
            "notes": forms.Textarea(attrs={
                "class": "form-textarea",
                "placeholder": "Any notes about this dose (side effects, etc.)",
                "rows": 2,
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["prn_reason"].required = False
        self.fields["notes"].required = False


class PRNDoseForm(forms.Form):
    """
    Simple form for logging a PRN (as-needed) dose.
    """

    medicine = forms.ModelChoiceField(
        queryset=Medicine.objects.none(),
        widget=forms.Select(attrs={
            "class": "form-select",
        }),
    )
    reason = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-input",
            "placeholder": "Why are you taking this? (optional)",
        }),
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            "class": "form-textarea",
            "placeholder": "Any notes?",
            "rows": 2,
        }),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            # Only show PRN medicines that are active
            self.fields["medicine"].queryset = Medicine.objects.filter(
                user=user,
                is_prn=True,
                medicine_status=Medicine.STATUS_ACTIVE,
            )


class UpdateSupplyForm(forms.Form):
    """
    Quick form for updating medicine supply count.
    """

    current_supply = forms.IntegerField(
        min_value=0,
        widget=forms.NumberInput(attrs={
            "class": "form-input",
            "placeholder": "Number of doses",
        }),
    )


# =============================================================================
# Food Tracking Forms
# =============================================================================


class FoodEntryForm(forms.ModelForm):
    """
    Form for logging a food entry.
    """

    class Meta:
        model = FoodEntry
        fields = [
            "food_name",
            "food_brand",
            "quantity",
            "serving_size",
            "serving_unit",
            "total_calories",
            "total_protein_g",
            "total_carbohydrates_g",
            "total_fiber_g",
            "total_sugar_g",
            "total_fat_g",
            "total_saturated_fat_g",
            "logged_date",
            "logged_time",
            "meal_type",
            "location",
            "eating_pace",
            "hunger_level_before",
            "fullness_level_after",
            "notes",
        ]
        widgets = {
            "food_name": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "What did you eat?",
            }),
            "food_brand": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "Brand (optional)",
            }),
            "quantity": forms.NumberInput(attrs={
                "class": "form-input",
                "step": "0.25",
                "min": "0.25",
                "value": "1",
            }),
            "serving_size": forms.NumberInput(attrs={
                "class": "form-input",
                "step": "0.1",
                "placeholder": "e.g., 100",
            }),
            "serving_unit": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "e.g., grams, oz, cups",
            }),
            "total_calories": forms.NumberInput(attrs={
                "class": "form-input",
                "step": "1",
                "min": "0",
                "placeholder": "Calories",
            }),
            "total_protein_g": forms.NumberInput(attrs={
                "class": "form-input",
                "step": "0.1",
                "min": "0",
                "placeholder": "Protein (g)",
            }),
            "total_carbohydrates_g": forms.NumberInput(attrs={
                "class": "form-input",
                "step": "0.1",
                "min": "0",
                "placeholder": "Carbs (g)",
            }),
            "total_fiber_g": forms.NumberInput(attrs={
                "class": "form-input",
                "step": "0.1",
                "min": "0",
                "placeholder": "Fiber (g)",
            }),
            "total_sugar_g": forms.NumberInput(attrs={
                "class": "form-input",
                "step": "0.1",
                "min": "0",
                "placeholder": "Sugar (g)",
            }),
            "total_fat_g": forms.NumberInput(attrs={
                "class": "form-input",
                "step": "0.1",
                "min": "0",
                "placeholder": "Fat (g)",
            }),
            "total_saturated_fat_g": forms.NumberInput(attrs={
                "class": "form-input",
                "step": "0.1",
                "min": "0",
                "placeholder": "Sat. Fat (g)",
            }),
            "logged_date": forms.DateInput(attrs={
                "class": "form-input",
                "type": "date",
            }),
            "logged_time": forms.TimeInput(attrs={
                "class": "form-input",
                "type": "time",
            }),
            "meal_type": forms.Select(attrs={
                "class": "form-select",
            }),
            "location": forms.Select(attrs={
                "class": "form-select",
            }),
            "eating_pace": forms.Select(attrs={
                "class": "form-select",
            }),
            "hunger_level_before": forms.NumberInput(attrs={
                "class": "form-input",
                "min": "1",
                "max": "5",
                "placeholder": "1-5",
            }),
            "fullness_level_after": forms.NumberInput(attrs={
                "class": "form-input",
                "min": "1",
                "max": "5",
                "placeholder": "1-5",
            }),
            "notes": forms.Textarea(attrs={
                "class": "form-textarea",
                "placeholder": "Any notes? (optional)",
                "rows": 2,
            }),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        # Set optional fields
        self.fields["food_brand"].required = False
        self.fields["logged_time"].required = False
        self.fields["location"].required = False
        self.fields["eating_pace"].required = False
        self.fields["hunger_level_before"].required = False
        self.fields["fullness_level_after"].required = False
        self.fields["notes"].required = False
        # Make all nutritional fields optional
        self.fields["total_calories"].required = False
        self.fields["total_protein_g"].required = False
        self.fields["total_carbohydrates_g"].required = False
        self.fields["total_fat_g"].required = False
        self.fields["total_fiber_g"].required = False
        self.fields["total_sugar_g"].required = False
        self.fields["total_saturated_fat_g"].required = False

        # Set defaults for new entries
        if not self.instance.pk:
            from apps.core.utils import get_user_today
            self.initial["logged_date"] = get_user_today(user) if user else timezone.now().date()
            now = timezone.now()
            if user:
                user_tz = get_user_timezone(user)
                local_now = now.astimezone(user_tz)
                self.initial["logged_time"] = local_now.strftime("%H:%M")
            else:
                self.initial["logged_time"] = now.strftime("%H:%M")
            # Default serving values
            self.initial["quantity"] = 1
            self.initial["serving_size"] = 1
            self.initial["serving_unit"] = "serving"


class QuickAddFoodForm(forms.Form):
    """
    Quick calorie-only food logging form.
    """

    food_name = forms.CharField(
        max_length=300,
        widget=forms.TextInput(attrs={
            "class": "form-input",
            "placeholder": "What did you eat?",
        }),
    )
    calories = forms.IntegerField(
        min_value=0,
        widget=forms.NumberInput(attrs={
            "class": "form-input",
            "placeholder": "Calories",
        }),
    )
    meal_type = forms.ChoiceField(
        choices=FoodEntry.MEAL_CHOICES,
        initial=FoodEntry.MEAL_SNACK,
        widget=forms.Select(attrs={
            "class": "form-select",
        }),
    )
    logged_date = forms.DateField(
        widget=forms.DateInput(attrs={
            "class": "form-input",
            "type": "date",
        }),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user:
            from apps.core.utils import get_user_today
            self.initial["logged_date"] = get_user_today(user)
        else:
            self.initial["logged_date"] = timezone.now().date()


class CustomFoodForm(forms.ModelForm):
    """
    Form for creating/editing a custom food.
    """

    class Meta:
        model = CustomFood
        fields = [
            "name",
            "description",
            "serving_size",
            "serving_unit",
            "calories",
            "protein_g",
            "carbohydrates_g",
            "fiber_g",
            "sugar_g",
            "fat_g",
            "saturated_fat_g",
            "sodium_mg",
        ]
        widgets = {
            "name": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "Food name (e.g., Mom's Chicken Soup)",
            }),
            "description": forms.Textarea(attrs={
                "class": "form-textarea",
                "placeholder": "Description or recipe notes (optional)",
                "rows": 2,
            }),
            "serving_size": forms.NumberInput(attrs={
                "class": "form-input",
                "step": "0.1",
                "placeholder": "e.g., 1",
            }),
            "serving_unit": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "e.g., cup, bowl, serving",
            }),
            "calories": forms.NumberInput(attrs={
                "class": "form-input",
                "step": "1",
                "min": "0",
                "placeholder": "Calories per serving",
            }),
            "protein_g": forms.NumberInput(attrs={
                "class": "form-input",
                "step": "0.1",
                "min": "0",
                "placeholder": "Protein (g)",
            }),
            "carbohydrates_g": forms.NumberInput(attrs={
                "class": "form-input",
                "step": "0.1",
                "min": "0",
                "placeholder": "Carbs (g)",
            }),
            "fiber_g": forms.NumberInput(attrs={
                "class": "form-input",
                "step": "0.1",
                "min": "0",
                "placeholder": "Fiber (g)",
            }),
            "sugar_g": forms.NumberInput(attrs={
                "class": "form-input",
                "step": "0.1",
                "min": "0",
                "placeholder": "Sugar (g)",
            }),
            "fat_g": forms.NumberInput(attrs={
                "class": "form-input",
                "step": "0.1",
                "min": "0",
                "placeholder": "Fat (g)",
            }),
            "saturated_fat_g": forms.NumberInput(attrs={
                "class": "form-input",
                "step": "0.1",
                "min": "0",
                "placeholder": "Saturated Fat (g)",
            }),
            "sodium_mg": forms.NumberInput(attrs={
                "class": "form-input",
                "step": "1",
                "min": "0",
                "placeholder": "Sodium (mg)",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set optional fields
        self.fields["description"].required = False
        self.fields["fiber_g"].required = False
        self.fields["sugar_g"].required = False
        self.fields["saturated_fat_g"].required = False
        self.fields["sodium_mg"].required = False

        # Set defaults for new entries
        if not self.instance.pk:
            self.initial["serving_size"] = 1
            self.initial["serving_unit"] = "serving"
            self.initial["protein_g"] = 0
            self.initial["carbohydrates_g"] = 0
            self.initial["fat_g"] = 0


class NutritionGoalsForm(forms.ModelForm):
    """
    Form for setting nutrition goals.
    """

    class Meta:
        model = NutritionGoals
        fields = [
            "daily_calorie_target",
            "daily_protein_target_g",
            "daily_carb_target_g",
            "daily_fat_target_g",
            "daily_fiber_target_g",
            "daily_sodium_limit_mg",
            "daily_sugar_limit_g",
            "notes",
        ]
        widgets = {
            "daily_calorie_target": forms.NumberInput(attrs={
                "class": "form-input",
                "min": "0",
                "placeholder": "e.g., 2000",
            }),
            "daily_protein_target_g": forms.NumberInput(attrs={
                "class": "form-input",
                "min": "0",
                "placeholder": "e.g., 150",
            }),
            "daily_carb_target_g": forms.NumberInput(attrs={
                "class": "form-input",
                "min": "0",
                "placeholder": "e.g., 200",
            }),
            "daily_fat_target_g": forms.NumberInput(attrs={
                "class": "form-input",
                "min": "0",
                "placeholder": "e.g., 65",
            }),
            "daily_fiber_target_g": forms.NumberInput(attrs={
                "class": "form-input",
                "min": "0",
                "placeholder": "e.g., 30",
            }),
            "daily_sodium_limit_mg": forms.NumberInput(attrs={
                "class": "form-input",
                "min": "0",
                "placeholder": "e.g., 2300",
            }),
            "daily_sugar_limit_g": forms.NumberInput(attrs={
                "class": "form-input",
                "min": "0",
                "placeholder": "e.g., 50",
            }),
            "notes": forms.Textarea(attrs={
                "class": "form-textarea",
                "placeholder": "Notes about your goals (optional)",
                "rows": 2,
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # All fields are optional
        for field in self.fields.values():
            field.required = False


class FoodSearchForm(forms.Form):
    """
    Form for searching foods.
    """

    query = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-input",
            "placeholder": "Search foods...",
            "autofocus": True,
        }),
    )