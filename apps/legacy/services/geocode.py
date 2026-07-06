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
# Nominatim's usage policy asks for a descriptive User-Agent and light use.
_UA = "WholeLifeJourney-Legacy/1.0 (personal family-history reference)"
_Q6 = Decimal("0.000001")


def geocode(query, timeout=4):
    """Return (lat, lon) as Decimals for a location string, or None. Never raises."""
    query = (query or "").strip()
    if not query:
        return None
    url = "%s?%s" % (_NOMINATIM, urllib.parse.urlencode(
        {"q": query, "format": "json", "limit": 1}))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if not data:
            return None
        lat = Decimal(str(data[0]["lat"])).quantize(_Q6)
        lon = Decimal(str(data[0]["lon"])).quantize(_Q6)
        return (lat, lon)
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError,
            IndexError, InvalidOperation, OSError) as exc:
        logger.info("Legacy geocode miss for %r: %s", query, exc)
        return None
    except Exception as exc:  # never let geocoding break a page render
        logger.warning("Legacy geocode error for %r: %s", query, exc)
        return None


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
