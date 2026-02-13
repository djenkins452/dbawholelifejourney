"""
Whole Life Journey - Medical Forms

Project: Whole Life Journey
Path: apps/medical/forms.py
Purpose: Forms for medical lab upload and filtering
"""

from django import forms


class LabUploadForm(forms.Form):
    """Form for uploading a lab PDF."""

    file = forms.FileField(
        label="Lab Results PDF",
        help_text="Upload a PDF of your lab results (max 20MB)",
        widget=forms.FileInput(attrs={
            "accept": ".pdf",
            "class": "form-control",
        }),
    )

    def clean_file(self):
        f = self.cleaned_data.get("file")
        if f:
            if not f.name.lower().endswith(".pdf"):
                raise forms.ValidationError("Only PDF files are supported.")
            if f.size > 20 * 1024 * 1024:
                raise forms.ValidationError("File too large. Maximum size is 20MB.")
        return f


class LabResultFilterForm(forms.Form):
    """Filter form for labs summary page."""

    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )
    panel_type = forms.ChoiceField(
        required=False,
        choices=[("", "All Panels")],
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    category = forms.ChoiceField(
        required=False,
        choices=[("", "All Categories")],
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    abnormal_only = forms.BooleanField(
        required=False,
        initial=False,
        label="Abnormal only",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Search test name...",
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.medical.models import LabPanel, LabTestCatalog

        # Dynamic panel type choices
        panel_choices = [("", "All Panels")]
        panel_choices.extend(LabPanel.PANEL_TYPE_CHOICES)
        self.fields["panel_type"].choices = panel_choices

        # Dynamic category choices
        cat_choices = [("", "All Categories")]
        cat_choices.extend(LabTestCatalog.CATEGORY_CHOICES)
        self.fields["category"].choices = cat_choices
