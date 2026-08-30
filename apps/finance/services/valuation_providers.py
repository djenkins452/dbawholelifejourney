# ==============================================================================
# File: apps/finance/services/valuation_providers.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The seam an external valuation source would plug into. None is active.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""A boundary, deliberately with nothing behind it yet.

**No provider is enabled, and that is the correct state today.** Every legitimate
market-value source for the asset types WLJ supports is a paid B2B contract:

* Real estate — ATTOM (from ~$95/month), HouseCanary and CoreLogic (custom,
  institutional). No free official AVM exists.
* Vehicles — Kelley Blue Book's InfoDriver Web Service is approved-partner only,
  J.D. Power and Black Book are licensed data contracts.
* Boats — J.D. Power (formerly NADA Guides) marine and ABOS are licensed.

Two things this module refuses to do, because both would produce a confident number
that is not a valuation:

1. **VIN decoding is not a value.** NHTSA's vPIC API is free and official, but it
   returns make/model/trim — what the vehicle IS, never what it is WORTH. Presenting
   a decode as a valuation would be inventing money.
2. **No generic depreciation curve.** Substituting `purchase price × 0.85^years`
   would fabricate a figure that looks researched. If nobody has said what an asset
   is worth, the honest answer is that nobody has said.

Scraping a consumer site (Zillow, KBB's public pages, Redfin) is not an option: it
breaks their terms, and this is Danny's money data, not a place to take that risk.

So the registry ships complete on the MANUAL valuation path, and this seam stays
empty until a provider is deliberately chosen and paid for. When one is, it
implements `ValuationProvider` and is registered here — the asset model never learns
its name.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ValuationEstimate:
    """What a provider returns — always labelled as an estimate."""
    amount: Decimal
    effective_date: object
    provider_key: str
    provider_name: str
    range_low: Optional[Decimal] = None
    range_high: Optional[Decimal] = None
    confidence: str = ""
    limitations: str = ""


@dataclass(frozen=True)
class ValuationUnavailable:
    """Why no estimate could be produced. A first-class outcome, not an exception.

    The caller's job on receiving this is to change NOTHING: the last known
    valuation stands, and the UI reports its age. A failed lookup must never blank a
    value or write a zero.
    """
    reason: str
    provider_key: str = ""
    retryable: bool = True


class ValuationProvider:
    """What a real provider would implement. Nothing implements it yet."""

    key: str = ""
    name: str = ""
    supported_types: tuple = ()

    def supports(self, asset) -> bool:
        return asset.asset_type in self.supported_types

    def estimate(self, asset):                      # pragma: no cover - no impl yet
        raise NotImplementedError


#: Deliberately empty. Adding an entry here is the switch that turns on spend, so it
#: is a decision Danny makes, not a default the code drifts into.
PROVIDERS: dict = {}


def provider_for(asset):
    """The provider that would value this asset, or None when none is configured."""
    for provider in PROVIDERS.values():
        if provider.supports(asset):
            return provider
    return None


def fetch_estimate(asset):
    """Ask for an estimate. Returns `ValuationEstimate` or `ValuationUnavailable`.

    With no provider configured this always reports unavailable — honestly, and
    without touching the existing valuation history.
    """
    provider = provider_for(asset)
    if provider is None:
        return ValuationUnavailable(
            reason=("No valuation provider is connected. Every source for this "
                    "kind of asset requires a paid subscription, so WLJ does not "
                    "guess — add a value yourself instead."),
            retryable=False,
        )

    try:
        return provider.estimate(asset)
    except Exception as exc:                        # a provider fault is not our bug
        logger.warning("Valuation provider %s failed for asset %s: %s",
                       provider.key, asset.pk, type(exc).__name__)
        return ValuationUnavailable(
            reason="That valuation service could not be reached just now.",
            provider_key=provider.key, retryable=True)


def provider_status():
    """What the UI tells a person about external estimates, in plain words."""
    return {
        "any_configured": bool(PROVIDERS),
        "providers": sorted(p.name for p in PROVIDERS.values()),
        "explanation": (
            "Values are the ones you enter. Automatic estimates for homes, vehicles "
            "and boats all come from paid subscription services, and none is "
            "connected."
        ),
    }
