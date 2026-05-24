"""
Journey forms — minimal forms for settings and completion.
"""

from django import forms

from apps.faith.journey.models import UserJourney


class JourneySettingsForm(forms.ModelForm):
    """User-controlled journey preferences: difficulty + optional reminder time."""

    class Meta:
        model = UserJourney
        fields = ["preferred_difficulty", "reminder_time"]
        widgets = {
            "preferred_difficulty": forms.RadioSelect(),
            "reminder_time": forms.TimeInput(attrs={"type": "time"}),
        }
        labels = {
            "preferred_difficulty": "Difficulty",
            "reminder_time": "Daily reminder (optional)",
        }
        help_texts = {
            "preferred_difficulty": (
                "Simple is approachable. Standard is the default. Deeper adds "
                "historical context, original-language notes, and cross-references."
            ),
            "reminder_time": (
                "Leave blank for no reminder. The journey is paced by you."
            ),
        }


class CompleteDayForm(forms.Form):
    """The reflection + application form posted at the bottom of each day."""

    reflection_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Your reflection..."}),
        max_length=10_000,
    )
    application_committed = forms.BooleanField(required=False)
