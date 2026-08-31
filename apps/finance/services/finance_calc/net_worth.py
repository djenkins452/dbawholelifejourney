# ==============================================================================
# File: apps/finance/services/finance_calc/net_worth.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Net worth composed from named authorities. Never double-subtracts debt.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""What the household is worth, and exactly which parts of it are unknown.

Composed, never re-derived: financial balances come from `FinancialAccount`, tangible
values from `asset_registry.current_value`, and debt from the liability accounts. This
module adds them up and reports the holes.

**The trap this module exists to avoid is subtracting a debt twice.** A mortgage is a
liability account AND it is linked to a house. Netting it against the house and then
subtracting total liabilities counts it twice and understates the household by the size
of its largest debt. So asset equity is EXPLANATORY — shown per asset, never summed into
the total — and the top-level arithmetic is the simple one:

    net worth = cash + investments + tangible assets - liabilities

**An unvalued asset is not worth zero.** It is worth an unknown amount, it is counted
out of the total, and it is reported as a named gap. A house nobody has valued would
otherwise silently erase itself.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

ZERO = Decimal("0.00")

NET_WORTH_VERSION = "1.0.0"

#: Past this, a valuation is stale enough to say so. Not wrong — stale. A car valued
#: eighteen months ago is a real number about a different car.
STALE_VALUATION_DAYS = 365

#: Asset-side account types that hold money rather than things.
CASH_TYPES = frozenset({"checking", "savings", "cash"})
INVESTMENT_TYPES = frozenset({"investment"})


def compose(user, *, today=None):
    """The current position: totals, composition, and every stated gap."""
    from apps.core.utils import get_user_today
    from apps.finance.models import FinancialAccount, TangibleAsset
    from apps.finance.services import asset_registry

    today = today or get_user_today(user)

    accounts = list(FinancialAccount.objects.filter(user=user, status="active"))
    cash, investments, liabilities = ZERO, ZERO, ZERO
    account_rows = []
    for account in accounts:
        balance = account.current_balance
        if balance is None:
            account_rows.append({"name": account.name,
                                 "type": account.account_type,
                                 "amount": None, "included": False,
                                 "reason": "no balance recorded"})
            continue
        if account.is_liability:
            # Liability balances are stored negative; the total is a magnitude.
            liabilities += abs(balance)
            account_rows.append({"name": account.name, "type": account.account_type,
                                 "amount": str(abs(balance)), "included": True,
                                 "side": "liability"})
            continue
        if account.account_type in INVESTMENT_TYPES:
            investments += balance
        elif account.account_type in CASH_TYPES:
            cash += balance
        else:
            # Property/other-asset ACCOUNTS are excluded: tangible value comes from the
            # Asset Registry, and counting both is how a house gets added twice.
            account_rows.append({"name": account.name, "type": account.account_type,
                                 "amount": str(balance), "included": False,
                                 "reason": "tangible value comes from the Asset Registry"})
            continue
        account_rows.append({"name": account.name, "type": account.account_type,
                             "amount": str(balance), "included": True, "side": "asset"})

    assets = list(TangibleAsset.objects.filter(user=user, status="active")
                  .prefetch_related("valuations", "loan_links__account"))
    tangible, unvalued, excluded, stale = ZERO, [], [], []
    asset_rows = []
    for asset in assets:
        value = asset_registry.current_value(asset)
        valuation = asset_registry.current_valuation(asset)
        age = asset_registry.valuation_age_days(asset, today)
        linked = [link.account for link in asset.loan_links.all()
                  if link.status == "active" and link.account is not None]
        linked_debt = sum((abs(a.current_balance) for a in linked
                           if a.current_balance is not None), ZERO)

        row = {
            "name": asset.name, "type": asset.asset_type,
            "value": str(value) if value is not None else None,
            "source": getattr(valuation, "source", None),
            "as_of": str(valuation.effective_date) if valuation else None,
            "age_days": age,
            "linked_debt": str(linked_debt) if linked else None,
            # Explanatory only. Never added into the total — see the module docstring.
            "equity": (str(value - linked_debt) if value is not None and linked
                       else None),
            "included": False,
        }

        if not asset.include_in_net_worth:
            excluded.append(asset.name)
            row["reason"] = "you excluded this from net worth"
        elif value is None:
            unvalued.append(asset.name)
            row["reason"] = "no value recorded — counted as unknown, not as zero"
        else:
            tangible += value
            row["included"] = True
            if age is not None and age > STALE_VALUATION_DAYS:
                stale.append(asset.name)
                row["stale"] = True
        asset_rows.append(row)

    net = cash + investments + tangible - liabilities

    return {
        "as_of": str(today),
        "cash_and_financial": cash,
        "investments": investments,
        "tangible_assets": tangible,
        "gross_assets": cash + investments + tangible,
        "liabilities": liabilities,
        "net_worth": net,
        "unvalued_assets": unvalued,
        "excluded_assets": excluded,
        "stale_valuations": stale,
        "accounts": account_rows,
        "asset_rows": asset_rows,
        "calculation_version": NET_WORTH_VERSION,
        "confidence": _confidence(unvalued, stale, accounts),
        "assumptions": _assumptions(unvalued, excluded, stale, assets),
        "inputs_missing": (["asset_valuation"] if unvalued else []),
    }


def _confidence(unvalued, stale, accounts):
    if not accounts:
        return "low"
    if unvalued:
        return "low"
    if stale:
        return "medium"
    return "high"


def _assumptions(unvalued, excluded, stale, assets):
    out = [
        "Debt linked to an asset is subtracted ONCE, in total liabilities. Per-asset "
        "equity is shown to explain the position, never added into the total.",
    ]
    if unvalued:
        out.append(
            f"{len(unvalued)} asset(s) have no recorded value and are NOT in the total. "
            f"An unvalued asset is worth an unknown amount, not nothing.")
    if excluded:
        out.append(f"{len(excluded)} asset(s) are excluded at your request.")
    if stale:
        out.append(
            f"{len(stale)} valuation(s) are over a year old. They are real numbers "
            f"about how things were, not about how things are.")
    if not assets:
        out.append("No tangible assets are recorded, so none are counted.")
    return out


# ---------------------------------------------------------------------------
# Snapshots and history
# ---------------------------------------------------------------------------

def take_snapshot(user, *, today=None, commit=False):
    """Record today's position. One per user per day, updated in place if re-run."""
    from apps.core.utils import get_user_today
    from apps.finance.models import NetWorthSnapshot

    today = today or get_user_today(user)
    position = compose(user, today=today)

    fields = {
        "basis": NetWorthSnapshot.BASIS_OBSERVED,
        "cash_and_financial": position["cash_and_financial"],
        "investments": position["investments"],
        "tangible_assets": position["tangible_assets"],
        "liabilities": position["liabilities"],
        "net_worth": position["net_worth"],
        "unvalued_asset_count": len(position["unvalued_assets"]),
        "excluded_asset_count": len(position["excluded_assets"]),
        "stale_valuation_count": len(position["stale_valuations"]),
        "calculation_version": NET_WORTH_VERSION,
        "composition": {
            "accounts": position["accounts"],
            "assets": position["asset_rows"],
        },
    }

    if not commit:
        return {"as_of": str(today), "committed": False,
                "would_write": {k: str(v) for k, v in fields.items()
                                if isinstance(v, Decimal)}}

    snapshot, created = NetWorthSnapshot.objects.update_or_create(
        user=user, as_of=today, status="active", defaults=fields)
    return {
        "as_of": str(today), "committed": True, "created": created,
        "net_worth": str(snapshot.net_worth),
        "gross_assets": str(snapshot.gross_assets),
        "liabilities": str(snapshot.liabilities),
        "unvalued_assets": snapshot.unvalued_asset_count,
        "stale_valuations": snapshot.stale_valuation_count,
        "calculation_version": NET_WORTH_VERSION,
    }


def history(user, *, days=365):
    """The observed series. Begins at the first snapshot — never before it."""
    from apps.core.utils import get_user_today
    from apps.finance.models import NetWorthSnapshot

    today = get_user_today(user)
    since = today - timedelta(days=days)
    rows = list(NetWorthSnapshot.objects.filter(
        user=user, status="active", as_of__gte=since).order_by("as_of"))

    if not rows:
        return {
            "points": [], "has_history": False,
            "explanation": (
                "No history yet. WLJ records what your position IS on the day it looks; "
                "it cannot reconstruct what your car was worth last March, and drawing "
                "a line from today's numbers would look like history and be fiction. "
                "The series starts with your first snapshot."),
            "calculation_version": NET_WORTH_VERSION,
        }

    points = [{
        "as_of": str(row.as_of), "net_worth": str(row.net_worth),
        "gross_assets": str(row.gross_assets), "liabilities": str(row.liabilities),
        "basis": row.basis, "complete": row.is_complete,
    } for row in rows]

    first, last = rows[0], rows[-1]
    return {
        "points": points, "has_history": True,
        "first": str(first.as_of), "latest": str(last.as_of),
        "change": str(last.net_worth - first.net_worth),
        "change_over_days": (last.as_of - first.as_of).days,
        "single_point": len(rows) == 1,
        "explanation": (
            "One snapshot so far — a position, not yet a trend. A second one gives you "
            "a direction." if len(rows) == 1 else
            f"{len(rows)} snapshots between {first.as_of} and {last.as_of}."),
        "calculation_version": NET_WORTH_VERSION,
    }
