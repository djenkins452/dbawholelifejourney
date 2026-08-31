# ==============================================================================
# File: apps/finance/services/finance_calc/reconciliation.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Where did that number come from? Read-only source reconciliation.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Proving a total against the records that produced it.

A net-worth figure is the most quotable number WLJ produces and the least checkable:
it is one line standing on dozens of records, and if one of those records should not be
there, the total is confidently wrong. Danny's reported 532,421.42 sits against an
earlier verified state of roughly 46,968.05 in financial assets with no tangible assets,
which is a gap large enough that the figure has to be defended rather than repeated.

So this module walks the total back to its sources and reports every one, redacted. It
writes nothing.

**Artifact detection is deliberately conservative.** It flags what LOOKS like
verification data — test-shaped names, round-number valuations created in the same
minute, records with no provenance — and it never deletes. A real asset with a tidy name
is indistinguishable from a fixture at a glance, and deleting a person's actual house
because it was called "Test House" is a far worse failure than leaving a stray row.
"""
from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal

ZERO = Decimal("0.00")

RECONCILIATION_VERSION = "1.0.0"

#: Names that look like something a developer typed, not something a person owns.
ARTIFACT_NAME_PATTERNS = (
    r"\btest\b", r"\bdemo\b", r"\bsample\b", r"\bfixture\b", r"\bdummy\b",
    r"\bexample\b", r"\bfoo\b", r"\bbar\b", r"\bverif", r"\btemp\b", r"\btmp\b",
    r"\bxxx\b", r"\bplaceholder\b", r"\bseed\b", r"\bqa\b",
)
_ARTIFACT_RE = re.compile("|".join(ARTIFACT_NAME_PATTERNS), re.IGNORECASE)


def _looks_like_artifact_name(name):
    return bool(_ARTIFACT_RE.search(name or ""))


def _round_number(amount):
    """A valuation that is suspiciously tidy. Real assets rarely value at exactly 100k."""
    if amount is None:
        return False
    return amount >= Decimal("1000") and amount % Decimal("1000") == ZERO


def reconcile_net_worth(user, *, today=None):
    """Walk the net-worth total back to every record that produced it. Read-only."""
    from apps.core.utils import get_user_today
    from apps.finance.models import FinancialAccount, TangibleAsset
    from apps.finance.services import asset_registry
    from apps.finance.services.finance_calc import net_worth as NW

    today = today or get_user_today(user)
    position = NW.compose(user, today=today)

    accounts = list(FinancialAccount.objects.filter(user=user))
    assets = list(TangibleAsset.objects.filter(user=user)
                  .prefetch_related("valuations", "loan_links__account"))

    return {
        "as_of": str(today),
        "reported": {
            "cash_and_financial": str(position["cash_and_financial"]),
            "investments": str(position["investments"]),
            "tangible_assets": str(position["tangible_assets"]),
            "gross_assets": str(position["gross_assets"]),
            "liabilities": str(position["liabilities"]),
            "net_worth": str(position["net_worth"]),
        },
        "financial_accounts": _financial_accounts(accounts),
        "tangible_assets": _tangible_assets(user, assets, today),
        "liabilities": _liabilities(accounts),
        "arithmetic": _arithmetic(position),
        "ownership": _ownership(user, accounts, assets),
        "artifacts": _artifacts(user, accounts, assets, today),
        "authority": _authority(user),
        "calculation_version": NW.NET_WORTH_VERSION,
        "reconciliation_version": RECONCILIATION_VERSION,
    }


def _financial_accounts(accounts):
    """By type and by institution. Names of institutions only — no identifiers."""
    from apps.finance.models import FinancialAccount
    from apps.finance.services.finance_calc import net_worth as NW

    by_type = defaultdict(lambda: {"count": 0, "total": ZERO, "included": 0})
    by_institution = defaultdict(lambda: {"count": 0, "total": ZERO})
    archived = {"count": 0, "total": ZERO}

    for account in accounts:
        balance = account.current_balance or ZERO
        if account.status != "active":
            archived["count"] += 1
            archived["total"] += balance
            continue
        if account.is_liability:
            continue
        bucket = by_type[account.account_type]
        bucket["count"] += 1
        bucket["total"] += balance
        if account.account_type in (NW.CASH_TYPES | NW.INVESTMENT_TYPES):
            bucket["included"] += 1

        institution = (getattr(account, "institution", "") or "").strip() \
            or "(no institution recorded)"
        by_institution[institution]["count"] += 1
        by_institution[institution]["total"] += balance

    return {
        "by_type": {k: {"count": v["count"], "total": str(v["total"]),
                        "counted_in_net_worth": v["included"]}
                    for k, v in sorted(by_type.items())},
        "by_institution": {k: {"count": v["count"], "total": str(v["total"])}
                           for k, v in sorted(by_institution.items())},
        "archived_or_deleted": {"count": archived["count"],
                                "total": str(archived["total"])},
    }


def _tangible_assets(user, assets, today):
    from apps.finance.services import asset_registry

    by_type = defaultdict(lambda: {"count": 0, "valued": 0, "total": ZERO})
    unvalued, excluded, stale, sources = [], [], [], defaultdict(int)
    effective_dates = []
    archived = 0

    for asset in assets:
        if asset.status != "active":
            archived += 1
            continue
        bucket = by_type[asset.asset_type or "(untyped)"]
        bucket["count"] += 1

        valuation = asset_registry.current_valuation(asset)
        value = asset_registry.current_value(asset)

        if not asset.include_in_net_worth:
            excluded.append({"name": asset.name, "type": asset.asset_type})
            continue
        if value is None:
            unvalued.append({"name": asset.name, "type": asset.asset_type})
            continue

        bucket["valued"] += 1
        bucket["total"] += value
        sources[getattr(valuation, "source", "") or "(none)"] += 1
        effective_dates.append(str(valuation.effective_date))
        age = asset_registry.valuation_age_days(asset, today)
        if age is not None and age > 365:
            stale.append({"name": asset.name, "age_days": age})

    return {
        "by_type": {k: {"count": v["count"], "valued": v["valued"],
                        "valuation_total": str(v["total"])}
                    for k, v in sorted(by_type.items())},
        # Per-asset provenance, redacted. WHEN a record was created is the decisive
        # evidence for whether it is a person's own entry or something a script left
        # behind, and it cannot be inferred from the total.
        "records": _asset_records(assets, today),
        "unvalued": unvalued,
        "excluded": excluded,
        "stale": stale,
        "archived_or_deleted": archived,
        "valuation_sources": dict(sources),
        "valuation_effective_dates": sorted(set(effective_dates)),
    }


def _asset_records(assets, today):
    """One redacted line per asset: what it is, what it is worth, and where it came from.

    Deliberately includes creation timestamps to the minute. A cluster of records created
    in the same few seconds is the signature of a script; records entered over minutes,
    with differing values, is the signature of a person sitting at a keyboard.
    """
    from apps.finance.services import asset_registry

    rows = []
    for asset in assets:
        if asset.status != "active":
            continue
        valuation = asset_registry.current_valuation(asset)
        value = asset_registry.current_value(asset)
        created = getattr(asset, "created_at", None)
        valued_at = getattr(valuation, "created_at", None) if valuation else None
        rows.append({
            "name_redacted": _redact(asset.name),
            "name_length": len(asset.name or ""),
            "type": asset.asset_type,
            "value": str(value) if value is not None else None,
            "valuation_source": getattr(valuation, "source", None),
            "valuation_effective": (str(valuation.effective_date)
                                    if valuation else None),
            "asset_created": created.isoformat(timespec="seconds") if created else None,
            "valuation_created": (valued_at.isoformat(timespec="seconds")
                                  if valued_at else None),
            "created_via": getattr(asset, "created_via", None),
            "looks_like_test_name": _looks_like_artifact_name(asset.name),
            "round_thousand": _round_number(value),
            "has_purchase_detail": bool(getattr(asset, "purchase_date", None)
                                        or getattr(asset, "purchase_price", None)),
            "has_identifying_detail": bool(
                (getattr(asset, "vin", "") or "").strip()
                or (getattr(asset, "street_address", "") or "").strip()
                or (getattr(asset, "hull_identification_number", "") or "").strip()),
        })
    return sorted(rows, key=lambda r: r["asset_created"] or "")


def _liabilities(accounts):
    by_type = defaultdict(lambda: {"count": 0, "total": ZERO})
    archived = 0
    for account in accounts:
        if not account.is_liability:
            continue
        if account.status != "active":
            archived += 1
            continue
        bucket = by_type[account.account_type]
        bucket["count"] += 1
        bucket["total"] += abs(account.current_balance or ZERO)
    return {
        "by_type": {k: {"count": v["count"], "total": str(v["total"])}
                    for k, v in sorted(by_type.items())},
        "archived_or_deleted": archived,
    }


def _arithmetic(position):
    """The exact sum, step by step, so the total can be checked by eye."""
    cash = position["cash_and_financial"]
    investments = position["investments"]
    tangible = position["tangible_assets"]
    liabilities = position["liabilities"]
    gross = cash + investments + tangible
    net = gross - liabilities
    return {
        "steps": [
            {"label": "cash and financial", "sign": "+", "amount": str(cash)},
            {"label": "investments", "sign": "+", "amount": str(investments)},
            {"label": "tangible assets", "sign": "+", "amount": str(tangible)},
            {"label": "gross assets", "sign": "=", "amount": str(gross)},
            {"label": "liabilities", "sign": "-", "amount": str(liabilities)},
            {"label": "net worth", "sign": "=", "amount": str(net)},
        ],
        "computed_gross": str(gross),
        "reported_gross": str(position["gross_assets"]),
        "computed_net": str(net),
        "reported_net": str(position["net_worth"]),
        "balances": (gross == position["gross_assets"]
                     and net == position["net_worth"]),
    }


def _ownership(user, accounts, assets):
    """Every record counted must belong to this user. Stated, not assumed."""
    foreign_accounts = [a.pk for a in accounts if a.user_id != user.pk]
    foreign_assets = [a.pk for a in assets if a.user_id != user.pk]
    return {
        "accounts_checked": len(accounts),
        "assets_checked": len(assets),
        "foreign_accounts": len(foreign_accounts),
        "foreign_assets": len(foreign_assets),
        "all_owned": not (foreign_accounts or foreign_assets),
    }


def _artifacts(user, accounts, assets, today):
    """Records that LOOK like verification data. Flagged for a human; never deleted.

    Every signal here is circumstantial on its own. A real boat can be called "Test
    Boat" and a real house can be worth exactly 400,000. So the report says WHY each row
    was flagged and how many signals it tripped, and leaves the deleting to a person.
    """
    from apps.finance.services import asset_registry

    suspects = []

    for account in accounts:
        if account.status != "active":
            continue
        reasons = []
        if _looks_like_artifact_name(account.name):
            reasons.append("name looks like test data")
        if account.current_balance is not None and _round_number(
                abs(account.current_balance)):
            reasons.append("balance is a round thousand")
        if not (getattr(account, "plaid_account_id", "") or "").strip():
            reasons.append("no provider link — created by hand or by a script")
        if len(reasons) >= 2:
            suspects.append({
                "kind": "account", "id": account.pk,
                "name_redacted": _redact(account.name),
                "type": account.account_type,
                "amount": str(abs(account.current_balance or ZERO)),
                "created": str(account.created_at.date())
                if getattr(account, "created_at", None) else None,
                "signals": reasons, "signal_count": len(reasons),
            })

    for asset in assets:
        if asset.status != "active":
            continue
        value = asset_registry.current_value(asset)
        valuation = asset_registry.current_valuation(asset)
        reasons = []
        if _looks_like_artifact_name(asset.name):
            reasons.append("name looks like test data")
        if _round_number(value):
            reasons.append("valuation is a round thousand")
        if valuation is not None and getattr(valuation, "source", "") in ("", "test"):
            reasons.append("valuation has no recorded source")
        if getattr(asset, "created_at", None) and valuation is not None \
                and getattr(valuation, "created_at", None) \
                and abs((valuation.created_at - asset.created_at).total_seconds()) < 5:
            reasons.append("asset and valuation created in the same instant")
        if len(reasons) >= 2:
            suspects.append({
                "kind": "asset", "id": asset.pk,
                "name_redacted": _redact(asset.name),
                "type": asset.asset_type,
                "amount": str(value) if value is not None else None,
                "created": str(asset.created_at.date())
                if getattr(asset, "created_at", None) else None,
                "signals": reasons, "signal_count": len(reasons),
            })

    return {
        "suspects": sorted(suspects, key=lambda s: -s["signal_count"]),
        "suspect_count": len(suspects),
        "suspect_value": str(sum(
            (Decimal(s["amount"]) for s in suspects if s["amount"]), ZERO)),
        "note": ("Flagged, never deleted. Every signal is circumstantial: a real boat "
                 "can be called 'Test Boat' and a real house can be worth exactly "
                 "400,000. Deleting a person's actual asset is a far worse failure "
                 "than leaving a stray row."),
    }


def _redact(name):
    """Enough to recognise your own record; not enough to identify it to anyone else."""
    name = (name or "").strip()
    if len(name) <= 2:
        return "**"
    return f"{name[0]}{'*' * (len(name) - 2)}{name[-1]}"


def _authority(user):
    """Does the stored snapshot agree with a live composition, on the same version?"""
    from apps.finance.models import NetWorthSnapshot
    from apps.finance.services.finance_calc import net_worth as NW

    snapshot = NetWorthSnapshot.objects.filter(
        user=user, status="active").order_by("-as_of").first()
    live = NW.compose(user)

    if snapshot is None:
        return {"snapshot": None, "agrees": None,
                "note": "No snapshot recorded yet."}

    return {
        "snapshot_as_of": str(snapshot.as_of),
        "snapshot_net_worth": str(snapshot.net_worth),
        "live_net_worth": str(live["net_worth"]),
        "snapshot_version": snapshot.calculation_version,
        "live_version": NW.NET_WORTH_VERSION,
        "same_version": snapshot.calculation_version == NW.NET_WORTH_VERSION,
        "agrees": snapshot.net_worth == live["net_worth"],
        "note": ("A snapshot older than today may legitimately differ — balances move. "
                 "A snapshot taken TODAY that disagrees means two authorities."),
    }
