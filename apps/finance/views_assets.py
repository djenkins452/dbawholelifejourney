# ==============================================================================
# File: apps/finance/views_assets.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The tangible asset registry — list, detail, CRUD, valuations, loans.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Ordinary Finance permissions throughout — `finance_enabled_required`, never staff.

Ownership is enforced in every LOOKUP, so another user's asset is not found rather
than found-and-refused.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.core.utils import get_user_today
from apps.finance.access import finance_enabled_required
from apps.finance.models import (AssetLoanLink, FinancialAccount, TangibleAsset)
from apps.finance.services import asset_registry as registry
from apps.finance.services import valuation_providers as providers


class TangibleAssetForm(forms.ModelForm):
    """Only the fields the chosen type actually uses.

    Nobody is asked for a VIN on a house. The irrelevant fields are removed from the
    form entirely rather than hidden, so they cannot be posted either.
    """

    class Meta:
        model = TangibleAsset
        fields = [
            'name', 'asset_type', 'description', 'entity',
            'street_address', 'city', 'state_region', 'postal_code',
            'year_built', 'square_feet',
            'make', 'model', 'model_year', 'vin', 'hull_identification_number',
            'mileage', 'engine_hours', 'length_feet',
            'condition', 'purchase_date', 'purchase_price', 'notes',
            'include_in_net_worth',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
            'notes': forms.Textarea(attrs={'rows': 3}),
            'purchase_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        from apps.finance.models import FinancialEntity
        self.fields['entity'].queryset = FinancialEntity.objects.filter(
            user=user, status='active')
        self.fields['entity'].required = False
        self.fields['entity'].empty_label = "Not tracked"

        asset_type = (self.data.get('asset_type')
                      or self.initial.get('asset_type')
                      or getattr(self.instance, 'asset_type', None)
                      or TangibleAsset.TYPE_OTHER)
        keep = set(TangibleAsset.TYPE_FIELDS.get(asset_type, []))
        for name in ('street_address', 'city', 'state_region', 'postal_code',
                     'year_built', 'square_feet', 'make', 'model', 'model_year',
                     'vin', 'hull_identification_number', 'mileage',
                     'engine_hours', 'length_feet'):
            if name not in keep:
                self.fields.pop(name, None)

        for field in self.fields.values():
            css = 'form-select' if isinstance(
                field.widget, forms.Select) else 'form-input'
            field.widget.attrs.setdefault('class', css)

    def clean_name(self):
        name = " ".join((self.cleaned_data.get('name') or "").split())
        if not name:
            raise forms.ValidationError("Give the asset a name.")
        return name

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.user = self.user
        if commit:
            instance.save()
        return instance


def _owned(request, pk):
    """This user's asset, ARCHIVED ONES INCLUDED.

    The default manager filters to `status='active'`, so looking an asset up through
    it makes an archived one a 404 — which would mean the Assets page could link to
    an archived asset that could then never be opened, and Restore could never
    reach the thing it restores. Soft-deleted rows stay excluded.
    """
    return get_object_or_404(
        TangibleAsset.all_objects.exclude(status='deleted'),
        pk=pk, user=request.user)


def _context(request, asset):
    today = get_user_today(request.user)
    loans = registry.linked_loans(asset)
    return {
        'asset': asset,
        'current_valuation': registry.current_valuation(asset),
        'current_value': registry.current_value(asset),
        'valuation_age_days': registry.valuation_age_days(asset, today),
        'valuations': asset.valuations.filter(status='active'),
        'linked_loans': loans,
        'linked_debt': registry.linked_debt(asset),
        'net_equity': registry.net_equity(asset),
        'linkable_accounts': registry.linkable_accounts(request.user),
        'provider_status': providers.provider_status(),
        'today': today,
    }


@login_required
@finance_enabled_required
def asset_list(request):
    """Every asset, grouped by kind, with the registry's own totals."""
    assets = list(registry.active_assets(request.user))
    archived = list(TangibleAsset.objects.filter(
        user=request.user, status='archived').order_by('asset_type', 'name'))

    groups = {}
    for asset in assets:
        label = asset.get_asset_type_display()
        bucket = groups.setdefault(label, {'label': label, 'assets': [],
                                           'total': Decimal('0.00'),
                                           'unvalued': 0})
        value = registry.current_value(asset)
        asset.display_value = value
        asset.display_equity = registry.net_equity(asset)
        asset.display_debt = registry.linked_debt(asset)
        bucket['assets'].append(asset)
        if value is None:
            bucket['unvalued'] += 1
        else:
            bucket['total'] += value

    return render(request, 'finance/asset_list.html', {
        'asset_groups': sorted(groups.values(), key=lambda g: g['label']),
        'archived_assets': archived,
        'breakdown': registry.net_worth_breakdown(request.user),
        'provider_status': providers.provider_status(),
    })


@login_required
@finance_enabled_required
def asset_detail(request, pk):
    asset = _owned(request, pk)
    return render(request, 'finance/asset_detail.html', _context(request, asset))


@login_required
@finance_enabled_required
def asset_create(request):
    if request.method == 'POST':
        form = TangibleAssetForm(request.user, request.POST)
        if form.is_valid():
            asset = form.save()
            registry._audit(request.user, request, 'asset_created', asset,
                            {'asset_type': asset.asset_type})
            messages.success(request, f'"{asset.name}" added.')
            return redirect('finance:asset_detail', pk=asset.pk)
    else:
        form = TangibleAssetForm(
            request.user,
            initial={'asset_type': request.GET.get('type')
                     or TangibleAsset.TYPE_OTHER})
    return render(request, 'finance/asset_form.html',
                  {'form': form, 'asset_types': TangibleAsset.ASSET_TYPE_CHOICES})


@login_required
@finance_enabled_required
def asset_update(request, pk):
    asset = _owned(request, pk)
    if request.method == 'POST':
        form = TangibleAssetForm(request.user, request.POST, instance=asset)
        if form.is_valid():
            asset = form.save()
            registry._audit(request.user, request, 'asset_updated', asset,
                            {'fields': sorted(form.changed_data)})
            messages.success(request, 'Saved.')
            return redirect('finance:asset_detail', pk=asset.pk)
    else:
        form = TangibleAssetForm(request.user, instance=asset)
    return render(request, 'finance/asset_form.html',
                  {'form': form, 'asset': asset,
                   'asset_types': TangibleAsset.ASSET_TYPE_CHOICES})


@login_required
@finance_enabled_required
@require_POST
def asset_archive(request, pk):
    """Out of current totals, all history kept."""
    asset = _owned(request, pk)
    asset.archive()
    registry._audit(request.user, request, 'asset_archived', asset, {})
    messages.success(
        request,
        f'"{asset.name}" archived — out of your totals, history kept.')
    return redirect('finance:asset_list')


@login_required
@finance_enabled_required
@require_POST
def asset_restore(request, pk):
    asset = _owned(request, pk)
    asset.restore()
    registry._audit(request.user, request, 'asset_restored', asset, {})
    messages.success(request, f'"{asset.name}" restored.')
    return redirect('finance:asset_detail', pk=asset.pk)


@login_required
@finance_enabled_required
@require_POST
def asset_delete(request, pk):
    """Only when there is no financial history to destroy."""
    asset = _owned(request, pk)
    valuations = asset.valuations.filter(status='active').count()
    links = asset.loan_links.filter(status='active').count()
    if valuations or links:
        parts = []
        if valuations:
            parts.append(f"{valuations} valuation{'s' if valuations != 1 else ''}")
        if links:
            parts.append(f"{links} linked loan{'s' if links != 1 else ''}")
        messages.error(
            request,
            f'"{asset.name}" has ' + " and ".join(parts) +
            '. Archive it instead — that keeps the history and takes it out of '
            'your totals.')
        return redirect('finance:asset_detail', pk=asset.pk)

    name = asset.name
    registry._audit(request.user, request, 'asset_deleted', asset,
                    {'asset_type': asset.asset_type})
    asset.delete()
    messages.success(request, f'"{name}" deleted.')
    return redirect('finance:asset_list')


@login_required
@finance_enabled_required
@require_POST
def valuation_add(request, pk):
    asset = _owned(request, pk)
    try:
        amount = Decimal((request.POST.get('amount') or '').strip())
    except (InvalidOperation, TypeError):
        messages.error(request, 'Enter the value as a number.')
        return redirect('finance:asset_detail', pk=pk)

    effective = request.POST.get('effective_date') or None
    if not effective:
        effective = get_user_today(request.user)

    try:
        registry.record_valuation(
            request.user, asset, amount=amount, effective_date=effective,
            source=request.POST.get('source') or 'manual',
            source_detail=(request.POST.get('source_detail') or '').strip(),
            notes=(request.POST.get('notes') or '').strip(),
            request=request)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(request, 'Value recorded.')
    return redirect('finance:asset_detail', pk=pk)


@login_required
@finance_enabled_required
@require_POST
def valuation_refresh(request, pk):
    """User-triggered only — there is no scheduled job and so no silent cost."""
    asset = _owned(request, pk)
    outcome = providers.fetch_estimate(asset)

    if isinstance(outcome, providers.ValuationUnavailable):
        # The existing valuation is deliberately untouched.
        messages.info(request, outcome.reason)
        return redirect('finance:asset_detail', pk=pk)

    registry.record_valuation(
        request.user, asset, amount=outcome.amount,
        effective_date=outcome.effective_date, source='provider',
        source_detail=outcome.provider_name, is_estimate=True,
        range_low=outcome.range_low, range_high=outcome.range_high,
        confidence=outcome.confidence, limitations=outcome.limitations,
        provider_key=outcome.provider_key, request=request)
    messages.success(request, f'Estimate from {outcome.provider_name} recorded.')
    return redirect('finance:asset_detail', pk=pk)


@login_required
@finance_enabled_required
@require_POST
def loan_link(request, pk):
    asset = _owned(request, pk)
    account = get_object_or_404(
        FinancialAccount, pk=request.POST.get('account_id'),
        user=request.user, status='active')
    try:
        registry.link_loan(request.user, asset, account,
                           note=(request.POST.get('note') or '').strip(),
                           request=request)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(request, f'{account.name} linked.')
    return redirect('finance:asset_detail', pk=pk)


@login_required
@finance_enabled_required
@require_POST
def loan_unlink(request, pk, link_id):
    asset = _owned(request, pk)
    link = get_object_or_404(AssetLoanLink, pk=link_id, asset=asset,
                             user=request.user)
    registry.unlink_loan(request.user, link, request=request)
    messages.success(request, 'Loan unlinked.')
    return redirect('finance:asset_detail', pk=pk)


@login_required
@finance_enabled_required
def net_worth_detail(request):
    """The reconciliation behind the headline numbers."""
    return render(request, 'finance/net_worth_detail.html', {
        'breakdown': registry.net_worth_breakdown(request.user),
        'provider_status': providers.provider_status(),
    })
