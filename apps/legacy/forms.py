"""Forms for Legacy people & places (Slice 3)."""

from django import forms

from apps.legacy.models import Person, Place


class PersonForm(forms.ModelForm):
    class Meta:
        model = Person
        fields = ["display_name", "also_known_as", "relationship_label",
                  "birth_year", "death_year", "bio"]
        widgets = {
            "display_name": forms.TextInput(attrs={
                "class": "lg-input", "placeholder": "Their name", "autocomplete": "off"}),
            "also_known_as": forms.TextInput(attrs={
                "class": "lg-input", "placeholder": "Nicknames or other names"}),
            "relationship_label": forms.TextInput(attrs={
                "class": "lg-input", "placeholder": "e.g. your father, a dear friend"}),
            "birth_year": forms.NumberInput(attrs={"class": "lg-input", "placeholder": "Born"}),
            "death_year": forms.NumberInput(attrs={"class": "lg-input", "placeholder": "Died (if applicable)"}),
            "bio": forms.Textarea(attrs={
                "class": "lg-textarea", "rows": 6,
                "placeholder": "Who were they? What were they like?"}),
        }


class PlaceForm(forms.ModelForm):
    class Meta:
        model = Place
        fields = ["name", "location_text", "description"]
        widgets = {
            "name": forms.TextInput(attrs={
                "class": "lg-input", "placeholder": "e.g. The lake house", "autocomplete": "off"}),
            "location_text": forms.TextInput(attrs={
                "class": "lg-input", "placeholder": "Where is / was it?"}),
            "description": forms.Textarea(attrs={
                "class": "lg-textarea", "rows": 6,
                "placeholder": "What was this place? What happened here? What did it feel like?"}),
        }
