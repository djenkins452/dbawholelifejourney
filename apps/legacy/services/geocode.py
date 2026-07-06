"""Geocoding for canonical Places — turn a location string into coordinates (search) and
coordinates into an address (reverse), so the map can centre on a Place and the keeper can
find one.

Provider: **Esri ArcGIS World Geocoding Service** — the same vendor as the map tiles, and
(unlike OpenStreetMap Nominatim, which returns EMPTY for many valid US residential
addresses — evidence: "3242 Old Plantation Way, Maryville, TN 37804" → Nominatim `[]`,
Esri → score-100 PointAddress) it has USPS-grade US address coverage.

Every call is INSTRUMENTED: the exact request URL (token redacted), HTTP status, raw
candidate count, and returned count are logged at INFO so the pipeline is observable in
production. Best-effort and non-blocking by design — every call is guarded, short-timeout,
and NEVER raises; a failure just returns nothing and the caller degrades gracefully. Use
`probe()` for a full request/response dump (the debug view).

Licensing note: token-free geocoding works for display; persisting coordinates at scale
should use an ArcGIS API key (`settings.ARCGIS_API_KEY` / env `ARCGIS_API_KEY`), which is
sent automatically when configured. Same posture as the keyless Esri tiles.
"""

import json
import logging
import os
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation

from django.conf import settings

logger = logging.getLogger(__name__)

_FIND = "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"
_REVERSE = "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/reverseGeocode"
_Q6 = Decimal("0.000001")


def _token():
    return (getattr(settings, "ARCGIS_API_KEY", "") or os.environ.get("ARCGIS_API_KEY", "")).strip()


def _redact(url):
    tok = _token()
    return url.replace(tok, "***") if tok else url


def _build(base, params):
    p = dict(params)
    tok = _token()
    if tok:
        p["token"] = tok
    return "%s?%s" % (base, urllib.parse.urlencode(p))


def _dec(value):
    try:
        return Decimal(str(value)).quantize(_Q6)
    except (InvalidOperation, TypeError, ValueError):
        return None


def _http_get(url, timeout):
    """GET → (status:int|None, body:str|None). Never raises."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "WholeLifeJourney-Legacy/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except Exception as exc:  # network / parse — geocoding is always best-effort
        logger.warning("Legacy geocode HTTP failed url=%s err=%s", _redact(url), exc)
        return None, None


def _candidates(query, limit, timeout):
    """Raw Esri findAddressCandidates → (request_url, status, body, [candidate dicts])."""
    url = _build(_FIND, {
        "SingleLine": query, "f": "json",
        "maxLocations": max(1, min(int(limit), 10)),
        "outFields": "Match_addr,Addr_type",
    })
    status, body = _http_get(url, timeout)
    cands = []
    if body:
        try:
            cands = json.loads(body).get("candidates", []) or []
        except (ValueError, AttributeError) as exc:
            logger.warning("Legacy geocode parse err q=%r: %s", query, exc)
    return url, status, body, cands


def search(query, limit=5, timeout=6):
    """Candidate locations for a query. Returns [{label, lat, lon, score}] (best first),
    empty on miss/failure. Never raises. Nothing is filtered by score — every candidate
    with valid coordinates is returned so the keeper chooses."""
    query = (query or "").strip()
    if not query:
        return []
    url, status, _body, cands = _candidates(query, limit, timeout)
    out = []
    for c in cands:
        loc = c.get("location") or {}
        lat, lon = _dec(loc.get("y")), _dec(loc.get("x"))   # Esri: x=lon, y=lat
        if lat is None or lon is None:
            continue
        out.append({"label": c.get("address") or query, "lat": lat, "lon": lon,
                    "score": c.get("score")})
    logger.info("Legacy geocode SEARCH q=%r url=%s status=%s raw_candidates=%d returned=%d",
                query, _redact(url), status, len(cands), len(out))
    return out


def reverse(lat, lon, timeout=5):
    """Coordinates → best-known address string, or "". Never raises."""
    la, lo = _dec(lat), _dec(lon)
    if la is None or lo is None:
        return ""
    url = _build(_REVERSE, {"location": "%s,%s" % (lo, la), "f": "json"})  # Esri wants lon,lat
    status, body = _http_get(url, timeout)
    addr = ""
    if body:
        try:
            a = json.loads(body).get("address") or {}
            addr = a.get("LongLabel") or a.get("Match_addr") or ""
        except (ValueError, AttributeError):
            addr = ""
    logger.info("Legacy geocode REVERSE lat=%s lon=%s url=%s status=%s addr=%r",
                la, lo, _redact(url), status, addr)
    return addr


def parse_latlon(lat, lon):
    """Validate + normalise a client-supplied pin. Returns (Decimal, Decimal) or None."""
    la, lo = _dec(lat), _dec(lon)
    if la is None or lo is None:
        return None
    if not (Decimal("-90") <= la <= Decimal("90")):
        return None
    if not (Decimal("-180") <= lo <= Decimal("180")):
        return None
    return (la, lo)


def geocode(query, timeout=4):
    """Single best match of a location string → (lat, lon) Decimals, or None. Never raises."""
    hits = search(query, limit=1, timeout=timeout)
    return (hits[0]["lat"], hits[0]["lon"]) if hits else None


def ensure_place_coordinates(place):
    """Populate a Place's latitude/longitude from its location text, once, and cache it on
    the Place. No-op if it already has coordinates or has no location text. Best-effort —
    on any failure the Place is left unchanged. Returns True only when newly stored."""
    if place.has_coordinates:
        return False
    if not (place.location_text or "").strip():
        return False
    hit = geocode(place.location_text.strip())
    if not hit:
        return False
    place.latitude, place.longitude = hit
    place.save(update_fields=["latitude", "longitude", "updated_at"])
    return True


def probe(query, limit=5, timeout=8):
    """Full observability dump for the debug view — the EXACT request URL, HTTP status,
    raw response body, and parsed results. Never raises."""
    query = (query or "").strip()
    url, status, body, cands = _candidates(query, limit, timeout) if query else ("", None, None, [])
    results = search(query, limit=limit, timeout=timeout) if query else []
    return {
        "provider": "esri", "submitted": query,
        "request_url": _redact(url), "http_status": status,
        "raw_response": (body or "")[:4000],
        "raw_candidate_count": len(cands),
        "returned_count": len(results),
        "dropped_no_coords": len(cands) - len(results),
        "results": [{"label": r["label"], "lat": str(r["lat"]), "lon": str(r["lon"]),
                     "score": r["score"]} for r in results],
        "token_configured": bool(_token()),
    }
