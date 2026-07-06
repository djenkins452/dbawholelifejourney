"""Forward geocoding for canonical Places — turn a best-known location ("Maryville,
Tennessee") into coordinates so the map can centre on it.

Keyless (OpenStreetMap Nominatim). Best-effort and non-blocking-by-design: every call
is guarded, short-timeout, and NEVER raises — a failure just leaves the Place without
coordinates and the map degrades to "Open in Google Maps". The result is cached onto the
canonical Place (its own latitude/longitude), so it's geocoded once and reused everywhere.
"""

import json
import logging
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)

_NOMINATIM = "https://nominatim.openstreetmap.org/search"
_NOMINATIM_REVERSE = "https://nominatim.openstreetmap.org/reverse"
# Nominatim's usage policy asks for a descriptive User-Agent and light use.
_UA = "WholeLifeJourney-Legacy/1.0 (personal family-history reference)"
_Q6 = Decimal("0.000001")


def _get(url, timeout):
    """GET + parse JSON from Nominatim with the required User-Agent. Returns parsed
    JSON or None. Never raises."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # network / parse — geocoding is always best-effort
        logger.info("Legacy geocode request failed (%s): %s", url.split("?")[0], exc)
        return None


def _dec(value):
    try:
        return Decimal(str(value)).quantize(_Q6)
    except (InvalidOperation, TypeError, ValueError):
        return None


def search(query, limit=5, timeout=6):
    """Stage 2 — offer the keeper candidate locations for a description they refine
    ("Tuscaloosa" → "Tuscaloosa, AL"). Returns a list of {label, lat, lon}; empty on
    miss/failure. Never raises."""
    query = (query or "").strip()
    if not query:
        return []
    url = "%s?%s" % (_NOMINATIM, urllib.parse.urlencode(
        {"q": query, "format": "json", "limit": max(1, min(int(limit), 10)),
         "addressdetails": 0}))
    data = _get(url, timeout) or []
    out = []
    for hit in data:
        lat, lon = _dec(hit.get("lat")), _dec(hit.get("lon"))
        if lat is None or lon is None:
            continue
        out.append({"label": hit.get("display_name") or query,
                    "lat": lat, "lon": lon})
    return out


def reverse(lat, lon, timeout=5):
    """Given coordinates (a dropped pin), return the best-known address string, or "".
    Never raises."""
    la, lo = _dec(lat), _dec(lon)
    if la is None or lo is None:
        return ""
    url = "%s?%s" % (_NOMINATIM_REVERSE, urllib.parse.urlencode(
        {"lat": str(la), "lon": str(lo), "format": "json"}))
    data = _get(url, timeout) or {}
    return data.get("display_name") or ""


def parse_latlon(lat, lon):
    """Validate + normalise a client-supplied pin (search result or dropped pin).
    Returns (Decimal, Decimal) within valid ranges, or None."""
    la, lo = _dec(lat), _dec(lon)
    if la is None or lo is None:
        return None
    if not (Decimal("-90") <= la <= Decimal("90")):
        return None
    if not (Decimal("-180") <= lo <= Decimal("180")):
        return None
    return (la, lo)


def geocode(query, timeout=4):
    """Stage 1 (automatic) — return (lat, lon) as Decimals for the single best match of a
    location string, or None. Never raises."""
    hits = search(query, limit=1, timeout=timeout)
    if not hits:
        return None
    return (hits[0]["lat"], hits[0]["lon"])


def ensure_place_coordinates(place):
    """Populate a Place's latitude/longitude from its best-known location, once, and
    cache it on the Place. No-op if it already has coordinates or has no location text
    to geocode. Best-effort — on any failure the Place is left unchanged. Returns True
    only when coordinates were newly stored."""
    if place.has_coordinates:
        return False
    # Only geocode a real location string (a city/address), not a bare personal name
    # like "Grandma's house" — that would just churn misses on every view.
    if not (place.location_text or "").strip():
        return False
    hit = geocode(place.location_text.strip())
    if not hit:
        return False
    place.latitude, place.longitude = hit
    place.save(update_fields=["latitude", "longitude", "updated_at"])
    return True
