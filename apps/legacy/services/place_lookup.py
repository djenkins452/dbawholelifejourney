"""
Place verification (Legacy Discovery pipeline, Phase 3 — intentionally small).

When Story Discovery names what looks like a real, public place ("Marie
Callender's"), this helps identify the correct place so the user doesn't have to
type an address by hand. It is NOT research: it retrieves only the NAME and
LOCATION (street, city, state, country, coordinates) — never reviews, ratings,
history, descriptions, hours, or anything unrelated to preserving the memory.

Private places ("Grandma's house", "the old barn") are recognized and never
looked up — the user is offered a Personal Place instead.

Keyless and dependency-light: a single OpenStreetMap (Nominatim) query over
stdlib urllib. Fails safe — any error, timeout, or missing network returns an
empty list so Discovery always completes. No provider abstraction, by design.
"""

import json
import logging
import re
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_USER_AGENT = "WholeLifeJourney-Legacy/1.0 (personal legacy preservation app)"
_TIMEOUT = 4  # seconds — never hold up the Discover action for long

# Relational possessors and generic private nouns signal a PERSONAL place.
# NB: possessive alone is not private ("Marie Callender's" is public) — the
# signal is a family/relational possessor or a generic private location.
_RELATIONAL = (
    r"grandma|grandmas|grandmother|grandpa|grandpas|grandfather|granny|nana|"
    r"papa|mama|mom|mommy|mother|dad|daddy|father|aunt|auntie|uncle|cousin|"
    r"our|my|nana's|the family"
)
_GENERIC_PRIVATE = (
    r"barn|treehouse|tree house|fishing hole|swimming hole|homestead|outhouse|"
    r"smokehouse|the shop|the field|the woods|the creek|the yard|the garden|"
    r"the cabin|our cabin|the cottage|the farmhouse|the porch|back porch|"
    r"the property|the homeplace|the home place|the lake house|the treehouse"
)


def is_personal_place(name):
    """True when a place name looks private/personal and should NOT be searched."""
    n = " " + (name or "").strip().lower() + " "
    if not n.strip():
        return False
    if re.search(r"\b(" + _RELATIONAL + r")\b", n):
        return True
    if re.search(r"\b(" + _GENERIC_PRIVATE + r")\b", n):
        return True
    if re.search(r"\bthe old \w+", n):     # "the old barn", "the old house"
        return True
    return False


def _fmt_address(addr):
    """Build the fields we keep — name + location only — from a Nominatim result."""
    a = addr or {}
    house = a.get("house_number")
    road = a.get("road")
    line1 = " ".join(x for x in (house, road) if x).strip()
    city = a.get("city") or a.get("town") or a.get("village") or a.get("hamlet") or a.get("suburb") or ""
    state = a.get("state") or a.get("region") or ""
    country = a.get("country") or ""
    return line1, city, state, country


def lookup_place(name, limit=4):
    """Return up to `limit` candidate matches for a public place, each a dict of
    NAME + LOCATION only. Empty list on no match or any failure — never raises."""
    q = (name or "").strip()
    if not q:
        return []
    params = urllib.parse.urlencode({
        "q": q, "format": "jsonv2", "addressdetails": 1,
        "namedetails": 1, "limit": max(1, min(limit, 6)),
    })
    req = urllib.request.Request(
        _NOMINATIM_URL + "?" + params,
        headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        results = json.loads(raw)
    except Exception:
        # No network, timeout, rate-limit, bad JSON — degrade silently.
        logger.info("Legacy place lookup unavailable for %r", q, exc_info=True)
        return []

    candidates = []
    for r in results if isinstance(results, list) else []:
        names = r.get("namedetails") or {}
        official = (names.get("name") or names.get("official_name")
                    or (r.get("display_name") or "").split(",")[0]).strip()
        line1, city, state, country = _fmt_address(r.get("address"))
        # Require at least a locality — a bare country match isn't useful.
        if not (city or line1):
            continue
        lat, lon = r.get("lat"), r.get("lon")
        candidates.append({
            "name": official or q,
            "line1": line1,
            "city": city,
            "state": state,
            "country": country,
            "lat": str(lat) if lat is not None else "",
            "lon": str(lon) if lon is not None else "",
            "display": ", ".join(x for x in (line1, city, state) if x),
        })
    # De-dupe identical display lines while preserving order.
    seen, unique = set(), []
    for c in candidates:
        key = (c["name"].lower(), c["display"].lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)
    return unique[:limit]
