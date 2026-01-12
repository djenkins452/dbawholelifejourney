"""
Billing forms.
"""

from django import forms

from .models import FeatureSuggestion


class FeatureSuggestionForm(forms.ModelForm):
    """Form for submitting feature suggestions."""

    class Meta:
        model = FeatureSuggestion
        fields = ['suggestion_text', 'public_credit_consent']
        widgets = {
            'suggestion_text': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 5,
                'placeholder': 'What feature would make Whole Life Journey better for you?',
                'maxlength': 2000,
            }),
            'public_credit_consent': forms.CheckboxInput(attrs={
                'class': 'form-checkbox',
            }),
        }
        labels = {
            'suggestion_text': 'Your Idea',
            'public_credit_consent': 'I consent to being credited publicly if this feature is implemented',
        }
        help_texts = {
            'suggestion_text': 'Describe your feature idea in detail. What problem does it solve?',
            'public_credit_consent': 'Optional: Let us thank you publicly when we implement your idea!',
        }


class PayoutPreferencesForm(forms.Form):
    """Form for Founding Members to set payout preferences."""

    PAYOUT_METHOD_CHOICES = [
        ('paypal', 'PayPal'),
        ('venmo', 'Venmo'),
        ('zelle', 'Zelle'),
        ('bank', 'Bank Transfer'),
    ]

    payout_method = forms.ChoiceField(
        choices=PAYOUT_METHOD_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Preferred Payout Method',
    )
    payout_email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            'class': 'form-input',
            'placeholder': 'your@email.com',
        }),
        label='PayPal/Venmo Email',
        help_text='Required for PayPal or Venmo payouts',
    )
    payout_phone = forms.CharField(
        required=False,
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': '555-123-4567',
        }),
        label='Zelle Phone Number',
        help_text='Required for Zelle payouts',
    )

    def clean(self):
        cleaned_data = super().clean()
        method = cleaned_data.get('payout_method')
        email = cleaned_data.get('payout_email')
        phone = cleaned_data.get('payout_phone')

        if method in ['paypal', 'venmo'] and not email:
            raise forms.ValidationError(
                f'{method.title()} requires an email address.'
            )
        if method == 'zelle' and not phone:
            raise forms.ValidationError(
                'Zelle requires a phone number.'
            )

        return cleaned_data
