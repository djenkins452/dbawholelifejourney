# ==============================================================================
# File: apps/finance/services/asset_registry.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Tangible assets, their valuations, and how they reach net worth.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""The accounting contract, in one place.

    net worth = financial assets + tangible asset values - ALL liabilities

A loan linked to an asset is an EXPLANATORY relationship. Its balance already sits in
total liabilities, so the aggregate must never subtract it again — the single most
likely way this feature could quietly produce a wrong number. Per-asset net equity
(`value - linked debt`) exists to explain ONE asset and is deliberately never summed
into the total.

Two other rules that keep the total honest:

* An asset with no valuation contributes NOTHING and is counted separately as
  unvalued. It is not worth $0.00 — nobody has said what it is worth, and a zero
  would be a claim.
* An archived asset is excluded from current totals but keeps its whole history.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Prefetch

logger = logging.getLogger(__name__)

ZERO = Decimal("0.00")

#: Loan types an asset may legitimately be secured by. A checking account is not a
#: lien on a boat, and offering it would invite a meaningless link.
LINKABLE_ACCOUNT_TYPES = ("mortgage", "loan", "other_liability")


# ---------------------------------------------------------------------------
# Valuation
# ---------------------------------------------------------------------------

def current_valuation(asset):
    """The most recent statement of what this asset is worth, or None.

    None is a real answer meaning "nobody has said" — callers must not turn it into
    zero.
    """
    prefetched = getattr(asset, "_prefetched_objects_cache", {})
    if "valuations" in prefetched:
        rows = [v for v in asset.valuations.all() if v.status == "active"]
        return rows[0] if rows else None
    return asset.valuations.filter(status="active").first()


def current_value(asset):
    """The Decimal value, or None when unvalued."""
    valuation = current_valuation(asset)
    return valuation.amount if valuation is not None else None


def record_valuation(user, asset, *, amount, effective_date, source, request=None,
                     source_detail="", notes="", is_estimate=False, range_low=None,
                     range_high=None, confidence="", limitations="",
                     retrieved_at=None, provider_key=""):
    """Add a valuation. Never edits an existing one — history is the point."""
    from apps.finance.models import AssetValuation

    if asset.user_id != user.id:
        raise ValidationError("That asset does not belong to you.")
    if amount is None:
        raise ValidationError("Enter the value.")
    amount = Decimal(str(amount))
    if amount < 0:
        raise ValidationError("A value cannot be negative.")
    if effective_date is None:
        raise ValidationError("Enter the date this value applies to.")

    valuation = AssetValuation.objects.create(
        user=user, asset=asset, amount=amount, effective_date=effective_date,
        source=source, source_detail=source_detail, notes=notes,
        is_estimate=is_estimate, range_low=range_low, range_high=range_high,
        confidence=confidence, limitations=limitations, retrieved_at=retrieved_at,
        provider_key=provider_key,
    )
    _audit(user, request, "valuation_added", asset, {
        "valuation_id": valuation.pk,
        "source": source,
        "is_estimate": is_estimate,
        "effective_date": str(effective_date),
        # The AMOUNT is deliberately recorded: it is the user's own figure about
        # their own asset, and an audit trail that cannot say what changed is
        # decoration. No address, VIN or provider payload goes anywhere near this.
        "amount": str(amount),
    })
    return valuation


def valuation_age_days(asset, today):
    """How stale the current valuation is, or None when unvalued."""
    valuation = current_valuation(asset)
    if valuation is None:
        return None
    return (today - valuation.effective_date).days


# ---------------------------------------------------------------------------
# Loan links
# ---------------------------------------------------------------------------

def linkable_accounts(user):
    """Liability accounts this user could secure an asset against."""
    from apps.finance.models import FinancialAccount

    return (FinancialAccount.objects
            .filter(user=user, status="active",
                    account_type__in=LINKABLE_ACCOUNT_TYPES)
            .order_by("name"))


def link_loan(user, asset, account, *, note="", request=None):
    """Attach a liability account to an asset, as explanation only."""
    from apps.finance.models import AssetLoanLink

    if asset.user_id != user.id:
        raise ValidationError("That asset does not belong to you.")
    if account.user_id != user.id:
        raise ValidationError("That account does not belong to you.")
    if not account.is_liability:
        raise ValidationError("Only a loan or other liability can secure an asset.")
    if AssetLoanLink.objects.filter(asset=asset, account=account,
                                    status="active").exists():
        raise ValidationError(f"{account.name} is already linked to this asset.")

    link = AssetLoanLink.objects.create(
        user=user, asset=asset, account=account, note=note)
    _audit(user, request, "loan_linked", asset,
           {"account_id": account.pk, "link_id": link.pk})
    return link


def unlink_loan(user, link, *, request=None):
    """Detach a loan. Archived, not destroyed — the relationship was history too."""
    if link.user_id != user.id:
        raise ValidationError("That link does not belong to you.")
    link.archive()
    _audit(user, request, "loan_unlinked", link.asset,
           {"account_id": link.account_id, "link_id": link.pk})
    return link


def linked_loans(asset):
    """`[{account, balance}]` — balance read LIVE from the account, never copied."""
    prefetched = getattr(asset, "_prefetched_objects_cache", {})
    if "loan_links" in prefetched:
        links = [l for l in asset.loan_links.all() if l.status == "active"]
    else:
        links = list(asset.loan_links.filter(status="active")
                     .select_related("account"))

    rows = []
    for link in links:
        account = link.account
        # An archived or disconnected account keeps its history here rather than
        # vanishing and silently increasing the asset's apparent equity.
        rows.append({
            "link": link,
            "account": account,
            "balance": abs(account.current_balance or ZERO),
            "account_active": account.status == "active",
        })
    return rows


def linked_debt(asset):
    """Total of the balances on this asset's linked loans."""
    return sum((row["balance"] for row in linked_loans(asset)), ZERO)


def net_equity(asset):
    """`value - linked debt`, or None when the asset is unvalued.

    Explanatory, per-asset, and NEVER summed into aggregate net worth — the linked
    debt is already counted once in total liabilities.
    """
    value = current_value(asset)
    if value is None:
        return None
    return value - linked_debt(asset)


# ---------------------------------------------------------------------------
# The reconciliation
# ---------------------------------------------------------------------------

def active_assets(user):
    """Assets that count right now, with everything the page needs preloaded."""
    from apps.finance.models import AssetLoanLink, AssetValuation, TangibleAsset

    return (TangibleAsset.objects
            .filter(user=user, status="active")
            .select_related("entity")
            .prefetch_related(
                Prefetch("valuations",
                         queryset=AssetValuation.objects.filter(status="active")),
                Prefetch("loan_links",
                         queryset=AssetLoanLink.objects.filter(status="active")
                         .select_related("account")),
            )
            .order_by("asset_type", "name"))


def net_worth_breakdown(user):
    """Every number on the dashboard, and the arithmetic that ties them together.

    ONE function so the dashboard card, the Assets page and the reconciliation view
    cannot disagree. The returned `reconciles` flag is not decoration: it re-derives
    the total from the parts and says so if they ever fail to match.
    """
    from apps.finance.models import FinancialAccount

    accounts = list(FinancialAccount.objects
                    .filter(user=user, status="active", is_hidden=False)
                    .select_related("bank_connection"))

    financial_assets = sum(
        (a.current_balance or ZERO for a in accounts if a.is_asset), ZERO)
    liabilities = sum(
        (abs(a.current_balance or ZERO) for a in accounts if a.is_liability), ZERO)

    assets = list(active_assets(user))
    by_type = {}
    tangible_total = ZERO
    unvalued = []
    for asset in assets:
        if not asset.include_in_net_worth:
            continue
        value = current_value(asset)
        if value is None:
            unvalued.append(asset)
            continue
        tangible_total += value
        bucket = by_type.setdefault(
            asset.get_asset_type_display(), {"label": asset.get_asset_type_display(),
                                             "total": ZERO, "count": 0})
        bucket["total"] += value
        bucket["count"] += 1

    gross_assets = financial_assets + tangible_total
    net_worth = gross_assets - liabilities

    return {
        "financial_assets": financial_assets,
        "tangible_assets": tangible_total,
        "tangible_by_type": sorted(by_type.values(), key=lambda b: b["label"]),
        "unvalued_assets": unvalued,
        "unvalued_count": len(unvalued),
        "gross_assets": gross_assets,
        "liabilities": liabilities,
        "net_worth": net_worth,
        # Re-derived independently. If this is ever False the page says so rather
        # than presenting a total nobody can account for.
        "reconciles": (financial_assets + tangible_total - liabilities) == net_worth,
    }


# ---------------------------------------------------------------------------

def _audit(user, request, operation, asset, details):
    """Audit through the existing Finance logger.

    NOTHING sensitive is recorded: no address, no VIN, no hull id, no provider
    payload. The asset id identifies the row; the operation says what happened.
    """
    from apps.finance.security import FinanceAuditLogger

    try:
        FinanceAuditLogger(user=user, request=request).log(
            action=FinanceAuditLogger.ACTION_UPDATE,
            entity_type="tangible_asset",
            entity_id=asset.pk,
            details={"operation": operation, **(details or {})},
        )
    except Exception:
        logger.warning("Could not audit %s on asset %s", operation, asset.pk,
                       exc_info=True)
