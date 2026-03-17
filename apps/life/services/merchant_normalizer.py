# ==============================================================================
# File: apps/life/services/merchant_normalizer.py
# Description: Phase 6B.5 — Merchant name normalization for transaction dedup
# Created: 2026-03-17
# ==============================================================================
"""
normalize_merchant — Deterministic merchant name cleanup.

Used by:
- _compute_fingerprint() — transaction fingerprint generation
- _create_email_transactions() — description normalization

Extensible: add aliases to MERCHANT_ALIASES as needed.
"""

import re

# --- Known merchant alias map ---
# Canonical name (lowercase) → set of known variants (lowercase, stripped)
MERCHANT_ALIASES = {
    'amazon': {'amzn', 'amzncom', 'amazoncom', 'amznmktplace', 'amazonmarketplace',
               'amzndigital', 'amazonprime', 'amznprime', 'primevideocom'},
    'walmart': {'walmartcom', 'wmtcom', 'wmt'},
    'target': {'targetcom', 'targetcorp'},
    'starbucks': {'starbucksstore', 'starbuckscoffee', 'sbux'},
    'netflix': {'netflixcom'},
    'spotify': {'spotifycom', 'spotifyusa'},
    'apple': {'applecom', 'appleitunes', 'itunes', 'applemusic', 'applebill',
              'applecomstorebill', 'applestorebill'},
    'google': {'googlecom', 'googlepay', 'googlecloud', 'googleone',
               'googleplay', 'googleservices', 'googlestorage'},
    'uber': {'ubercom', 'ubereats', 'ubertrip'},
    'lyft': {'lyftride', 'lyftinc'},
    'doordash': {'doordashcom', 'doordashdasher'},
    'grubhub': {'grubhubcom', 'grubhubinc'},
    'paypal': {'paypalcom', 'paypalinst', 'paypalinstxfer'},
    'venmo': {'venmocom', 'venmopmnt'},
    'costco': {'costcowholesale', 'costcowhse', 'costcocom'},
    'cvs': {'cvspharmacy', 'cvshealthcorp', 'cvspharm'},
    'walgreens': {'walgreenscom', 'walgreenspharm'},
    'att': {'attcom', 'attbill', 'attwireless', 'attmobility'},
    'verizon': {'verizoncom', 'verizonwireless', 'vzwrlss'},
    'tmobile': {'tmobilecom', 'tmobilebill'},
    'comcast': {'comcastcable', 'xfinity', 'xfinitycom'},
    'hulu': {'hulucom', 'hulullc'},
    'disney': {'disneyplus', 'disneypluscom'},
    'hbo': {'hbomax', 'maxcom'},
}

# Build reverse lookup: variant → canonical
_ALIAS_LOOKUP = {}
for canonical, variants in MERCHANT_ALIASES.items():
    _ALIAS_LOOKUP[canonical] = canonical  # self-map
    for v in variants:
        _ALIAS_LOOKUP[v] = canonical

# Common noise tokens to strip
_NOISE_TOKENS = {
    'inc', 'llc', 'ltd', 'corp', 'co', 'company',
    'com', 'org', 'net',
    'payment', 'billing', 'bill', 'charge',
    'online', 'digital', 'store', 'shop',
    'autopay', 'recurring', 'monthly',
    'the', 'of', 'and', 'for',
}

# Non-alphanumeric (for stripping punctuation)
_NON_ALNUM_RE = re.compile(r'[^a-z0-9\s]')
_MULTI_SPACE_RE = re.compile(r'\s+')


def normalize_merchant(merchant):
    """
    Normalize a merchant name for dedup and matching.

    Steps:
        1. Lowercase
        2. Strip non-alphanumeric (keep spaces)
        3. Remove noise tokens
        4. Check alias map
        5. Collapse to single token for fingerprint

    Args:
        merchant: raw merchant name string

    Returns:
        str: normalized merchant name (lowercase, clean)
    """
    if not merchant:
        return ''

    text = merchant.lower().strip()

    # Strip non-alphanumeric except spaces
    text = _NON_ALNUM_RE.sub('', text)
    text = _MULTI_SPACE_RE.sub(' ', text).strip()

    # Check alias map against the fully-stripped version (no spaces)
    collapsed = text.replace(' ', '')
    if collapsed in _ALIAS_LOOKUP:
        return _ALIAS_LOOKUP[collapsed]

    # Remove noise tokens
    tokens = text.split()
    cleaned = [t for t in tokens if t not in _NOISE_TOKENS]
    if not cleaned:
        # All tokens were noise — return the collapsed original
        return collapsed

    # Check alias of cleaned version
    cleaned_collapsed = ''.join(cleaned)
    if cleaned_collapsed in _ALIAS_LOOKUP:
        return _ALIAS_LOOKUP[cleaned_collapsed]

    return cleaned_collapsed


def normalize_merchant_for_fingerprint(merchant):
    """
    Normalize merchant specifically for fingerprint computation.

    Returns a fully-collapsed alphanumeric-only string suitable for hashing.
    This replaces the inline `re.sub(r'[^a-z0-9]', '', ...)` in _compute_fingerprint.
    """
    return normalize_merchant(merchant)
