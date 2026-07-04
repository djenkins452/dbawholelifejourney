"""Forms for Legacy people & places (Slice 3)."""

from django import forms

from apps.legacy.models import (
    RELATIONSHIP_TYPE_CHOICES, Contributor, Output, Person, Place, Relationship,
)


class RelationshipForm(forms.ModelForm):
    """Edit what KIND of relationship this is, plus its status, span, and notes."""

    relationship_type = forms.ChoiceField(
        choices=[("", "Unknown")] + list(RELATIONSHIP_TYPE_CHOICES),
        required=False, label="Relationship",
        widget=forms.Select(attrs={"class": "lg-input"}))

    class Meta:
        model = Relationship
        fields = ["relationship_type", "rel_status", "started_year", "ended_year", "notes"]
        widgets = {
            "rel_status": forms.Select(attrs={"class": "lg-input"}),
            "started_year": forms.NumberInput(attrs={"class": "lg-input", "placeholder": "Started (year)"}),
            "ended_year": forms.NumberInput(attrs={"class": "lg-input", "placeholder": "Ended (year)"}),
            "notes": forms.Textarea(attrs={"class": "lg-textarea", "rows": 3, "placeholder": "Anything worth remembering about this relationship…"}),
        }


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


class ContributorForm(forms.ModelForm):
    class Meta:
        model = Contributor
        fields = ["name", "email", "relationship_label", "permission_level"]
        widgets = {
            "name": forms.TextInput(attrs={
                "class": "lg-input", "placeholder": "Their name", "autocomplete": "off"}),
            "email": forms.EmailInput(attrs={
                "class": "lg-input", "placeholder": "Email (for a future invitation)"}),
            "relationship_label": forms.TextInput(attrs={
                "class": "lg-input", "placeholder": "e.g. your daughter, an old friend"}),
            "permission_level": forms.Select(attrs={"class": "lg-input"}),
        }


class OutputForm(forms.ModelForm):
    class Meta:
        model = Output
        fields = ["title", "output_type", "scope_kind", "scope_person", "scope_place", "audience"]
        widgets = {
            "title": forms.TextInput(attrs={
                "class": "lg-input", "placeholder": "Give it a name (optional)", "autocomplete": "off"}),
            "output_type": forms.Select(attrs={"class": "lg-input"}),
            "scope_kind": forms.Select(attrs={"class": "lg-input"}),
            "scope_person": forms.Select(attrs={"class": "lg-input"}),
            "scope_place": forms.Select(attrs={"class": "lg-input"}),
            "audience": forms.Select(attrs={"class": "lg-input"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["scope_person"].queryset = Person.objects.filter(user=user)
            self.fields["scope_place"].queryset = Place.objects.filter(user=user)
        self.fields["scope_person"].required = False
        self.fields["scope_place"].required = False
        self.fields["scope_person"].empty_label = "—"
        self.fields["scope_place"].empty_label = "—"


class ImportForm(forms.Form):
    """Create an import from an uploaded text file or pasted text."""

    from apps.legacy.models import ImportBatch as _IB

    source_name = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={
            "class": "lg-input", "autocomplete": "off",
            "placeholder": "What is this document? (e.g. My autobiography)"}))
    source_type = forms.ChoiceField(
        choices=_IB.SourceType.choices,
        widget=forms.Select(attrs={"class": "lg-input"}))
    file = forms.FileField(
        required=False,
        widget=forms.ClearableFileInput(attrs={
            "class": "editor-media-input",
            "accept": ".txt,.md,.markdown,.doc,.docx,.pdf,.ged,.gedcom,text/plain,text/markdown"}))
    paste = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            "class": "lg-textarea", "rows": 10,
            "placeholder": "…or paste the text of the document here"}))

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("file") and not (cleaned.get("paste") or "").strip():
            raise forms.ValidationError("Upload a text file or paste the document's text.")
        return cleaned
