# ==============================================================================
# File: apps/finance/forms.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Finance module forms for accounts, transactions, budgets, goals
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-02
# Last Updated: 2026-01-02
# ==============================================================================
from decimal import Decimal

from django import forms
from django.utils import timezone

from .models import (
    FinancialAccount,
    TransactionCategory,
    Transaction,
    Budget,
    FinancialGoal,
)


class FinancialAccountForm(forms.ModelForm):
    """Form for creating and editing financial accounts."""

    class Meta:
        model = FinancialAccount
        fields = [
            'name', 'account_type', 'institution', 'current_balance',
            'currency', 'account_number_last4', 'color', 'sort_order',
            'include_in_net_worth', 'is_hidden', 'notes'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g., Chase Checking'
            }),
            'institution': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g., Chase Bank'
            }),
            'current_balance': forms.NumberInput(attrs={
                'class': 'form-input',
                'step': '0.01',
                'placeholder': '0.00'
            }),
            'account_number_last4': forms.TextInput(attrs={
                'class': 'form-input',
                'maxlength': '4',
                'placeholder': 'Last 4 digits'
            }),
            'color': forms.TextInput(attrs={
                'class': 'form-input',
                'type': 'color'
            }),
            'sort_order': forms.NumberInput(attrs={
                'class': 'form-input',
                'min': '0'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 3,
                'placeholder': 'Optional notes...'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Flatten the grouped choices for the select widget
        flat_choices = []
        for group_name, choices in FinancialAccount.ACCOUNT_TYPE_CHOICES:
            flat_choices.append((group_name, choices))
        self.fields['account_type'].widget = forms.Select(
            attrs={'class': 'form-select'},
            choices=FinancialAccount.ACCOUNT_TYPE_CHOICES
        )
        self.fields['currency'].widget.attrs['class'] = 'form-select'


class TransactionForm(forms.ModelForm):
    """Form for creating and editing transactions."""

    # Use a positive amount field, with separate type selection
    amount_value = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal('0.01'),
        widget=forms.NumberInput(attrs={
            'class': 'form-input',
            'step': '0.01',
            'placeholder': '0.00'
        })
    )

    transaction_type = forms.ChoiceField(
        choices=[
            ('expense', 'Expense (money out)'),
            ('income', 'Income (money in)'),
        ],
        initial='expense',
        widget=forms.RadioSelect(attrs={'class': 'form-radio'})
    )

    class Meta:
        model = Transaction
        fields = [
            'account', 'date', 'description', 'category',
            'payee', 'notes', 'reference', 'is_cleared', 'is_recurring', 'tags'
        ]
        widgets = {
            'date': forms.DateInput(attrs={
                'class': 'form-input',
                'type': 'date'
            }),
            'description': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Transaction description'
            }),
            'payee': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Payee name (optional)'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 2,
                'placeholder': 'Optional notes...'
            }),
            'reference': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Check #, confirmation code, etc.'
            }),
        }

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        # Filter accounts to user's accounts
        self.fields['account'].queryset = FinancialAccount.objects.filter(
            user=user, status='active'
        )
        self.fields['account'].widget.attrs['class'] = 'form-select'

        # Filter categories to user's + system categories
        self.fields['category'].queryset = TransactionCategory.get_for_user(user)
        self.fields['category'].widget.attrs['class'] = 'form-select'

        # Set default date to today
        if not self.instance.pk:
            self.fields['date'].initial = timezone.now().date()

        # If editing, set amount_value and type from existing amount
        if self.instance.pk and self.instance.amount:
            self.fields['amount_value'].initial = abs(self.instance.amount)
            self.fields['transaction_type'].initial = (
                'income' if self.instance.amount > 0 else 'expense'
            )

    def clean(self):
        cleaned_data = super().clean()
        amount_value = cleaned_data.get('amount_value')
        transaction_type = cleaned_data.get('transaction_type')

        if amount_value:
            # Convert to signed amount based on type
            if transaction_type == 'expense':
                cleaned_data['amount'] = -abs(amount_value)
            else:
                cleaned_data['amount'] = abs(amount_value)

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.amount = self.cleaned_data['amount']
        instance.user = self.user

        if commit:
            instance.save()
        return instance


class QuickTransactionForm(forms.Form):
    """Simplified form for quick transaction entry."""

    account = forms.ModelChoiceField(
        queryset=FinancialAccount.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': 'form-input',
            'step': '0.01',
            'placeholder': 'Amount'
        })
    )
    description = forms.CharField(
        max_length=300,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'What was this for?'
        })
    )
    category = forms.ModelChoiceField(
        queryset=TransactionCategory.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    is_expense = forms.BooleanField(
        initial=True,
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-checkbox'})
    )

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields['account'].queryset = FinancialAccount.objects.filter(
            user=user, status='active'
        )
        self.fields['category'].queryset = TransactionCategory.get_for_user(
            user, category_type='expense'
        )

    def save(self):
        amount = self.cleaned_data['amount']
        if self.cleaned_data.get('is_expense', True):
            amount = -abs(amount)
        else:
            amount = abs(amount)

        transaction = Transaction.objects.create(
            user=self.user,
            account=self.cleaned_data['account'],
            date=timezone.now().date(),
            amount=amount,
            description=self.cleaned_data['description'],
            category=self.cleaned_data.get('category'),
        )
        return transaction


class BudgetForm(forms.ModelForm):
    """Form for creating and editing budgets."""

    class Meta:
        model = Budget
        fields = [
            'month', 'category', 'budgeted_amount',
            'rollover_enabled', 'notes'
        ]
        widgets = {
            'month': forms.DateInput(attrs={
                'class': 'form-input',
                'type': 'month'
            }),
            'budgeted_amount': forms.NumberInput(attrs={
                'class': 'form-input',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 2,
                'placeholder': 'Budget notes...'
            }),
        }

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        # Filter categories to expense categories only
        self.fields['category'].queryset = TransactionCategory.get_for_user(
            user, category_type='expense'
        )
        self.fields['category'].widget.attrs['class'] = 'form-select'

        # Default to current month
        if not self.instance.pk:
            today = timezone.now().date()
            self.fields['month'].initial = today.replace(day=1)

    def clean_month(self):
        """Ensure month is stored as first day of month."""
        month = self.cleaned_data['month']
        return month.replace(day=1)

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.user = self.user

        if commit:
            instance.save()
        return instance


class FinancialGoalForm(forms.ModelForm):
    """Form for creating and editing financial goals."""

    class Meta:
        model = FinancialGoal
        fields = [
            'name', 'goal_type', 'description', 'target_amount',
            'current_amount', 'target_date', 'linked_account',
            'color', 'icon', 'notes'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g., Emergency Fund'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 2,
                'placeholder': 'What is this goal for?'
            }),
            'target_amount': forms.NumberInput(attrs={
                'class': 'form-input',
                'step': '0.01',
                'min': '0.01',
                'placeholder': '10000.00'
            }),
            'current_amount': forms.NumberInput(attrs={
                'class': 'form-input',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00'
            }),
            'target_date': forms.DateInput(attrs={
                'class': 'form-input',
                'type': 'date'
            }),
            'color': forms.TextInput(attrs={
                'class': 'form-input',
                'type': 'color'
            }),
            'icon': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': '💰'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 2,
                'placeholder': 'Additional notes...'
            }),
        }

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        self.fields['goal_type'].widget.attrs['class'] = 'form-select'

        # Filter linked accounts to user's accounts
        self.fields['linked_account'].queryset = FinancialAccount.objects.filter(
            user=user, status='active'
        )
        self.fields['linked_account'].widget.attrs['class'] = 'form-select'
        self.fields['linked_account'].required = False

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.user = self.user

        if commit:
            instance.save()
        return instance


class TransactionFilterForm(forms.Form):
    """Form for filtering transactions list."""

    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-input',
            'type': 'date'
        })
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-input',
            'type': 'date'
        })
    )
    account = forms.ModelChoiceField(
        queryset=FinancialAccount.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    category = forms.ModelChoiceField(
        queryset=TransactionCategory.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    transaction_type = forms.ChoiceField(
        choices=[
            ('', 'All'),
            ('income', 'Income'),
            ('expense', 'Expense'),
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Search transactions...'
        })
    )

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['account'].queryset = FinancialAccount.objects.filter(
            user=user, status='active'
        )
        self.fields['category'].queryset = TransactionCategory.get_for_user(user)


class TransferForm(forms.Form):
    """Form for transferring money between accounts."""

    from_account = forms.ModelChoiceField(
        queryset=FinancialAccount.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    to_account = forms.ModelChoiceField(
        queryset=FinancialAccount.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal('0.01'),
        widget=forms.NumberInput(attrs={
            'class': 'form-input',
            'step': '0.01',
            'placeholder': 'Transfer amount'
        })
    )
    date = forms.DateField(
        widget=forms.DateInput(attrs={
            'class': 'form-input',
            'type': 'date'
        })
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-textarea',
            'rows': 2,
            'placeholder': 'Transfer notes...'
        })
    )

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        accounts = FinancialAccount.objects.filter(user=user, status='active')
        self.fields['from_account'].queryset = accounts
        self.fields['to_account'].queryset = accounts
        self.fields['date'].initial = timezone.now().date()

    def clean(self):
        cleaned_data = super().clean()
        from_account = cleaned_data.get('from_account')
        to_account = cleaned_data.get('to_account')

        if from_account and to_account and from_account == to_account:
            raise forms.ValidationError(
                "Cannot transfer to the same account."
            )

        return cleaned_data

    def save(self):
        """Create paired transfer transactions."""
        from_account = self.cleaned_data['from_account']
        to_account = self.cleaned_data['to_account']
        amount = self.cleaned_data['amount']
        date = self.cleaned_data['date']
        notes = self.cleaned_data.get('notes', '')

        # Get or create transfer category
        transfer_category, _ = TransactionCategory.objects.get_or_create(
            category_type='transfer',
            is_system=True,
            user=None,
            defaults={'name': 'Transfer'}
        )

        # Create outgoing transaction
        outgoing = Transaction.objects.create(
            user=self.user,
            account=from_account,
            date=date,
            amount=-abs(amount),
            description=f'Transfer to {to_account.name}',
            category=transfer_category,
            notes=notes,
        )

        # Create incoming transaction
        incoming = Transaction.objects.create(
            user=self.user,
            account=to_account,
            date=date,
            amount=abs(amount),
            description=f'Transfer from {from_account.name}',
            category=transfer_category,
            notes=notes,
        )

        # Link them together
        outgoing.transfer_pair = incoming
        outgoing.save(update_fields=['transfer_pair'])
        incoming.transfer_pair = outgoing
        incoming.save(update_fields=['transfer_pair'])

        return outgoing, incoming
