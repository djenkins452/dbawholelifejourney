"""One-time location review — provider-INDEPENDENT of the retired Nominatim geocoder.

The question is not "where did the old coordinate come from" but "is the CURRENT coordinate
correct". For each legacy Place (coordinates set before provenance existed) we ask Esri for a
fresh suggestion from its `location_text` and surface the two side by side with the distance
between them, so the keeper decides: Keep Current, or Use Suggested. Nothing is changed until
they choose. Only Esri + plain geometry are used — Nominatim is never called.
"""

import logging
import math

from apps.legacy.models import Place
from apps.legacy.services import geocode

logger = logging.getLogger(__name__)


def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres between two lat/long points."""
    r = 6371000.0
    p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dl = math.radians(float(lon2) - float(lon1))
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def review_candidates(user, min_distance_m=25, max_places=80):
    """Legacy Places whose CURRENT coordinates differ from Esri's fresh suggestion (from
    their location_text) by more than `min_distance_m`. Only rows with `coordinate_source`
    unset (legacy) are considered — anything the keeper has already resolved/reviewed
    (esri/pin/manual/reviewed) is excluded, so the review is self-terminating.

    Returns [{place, cur_lat, cur_lon, sug_lat, sug_lon, sug_label, distance_m}] ordered by
    largest discrepancy first. One Esri call per candidate — an explicit maintenance scan,
    never the hot request path."""
    qs = (Place.objects.filter(user=user, latitude__isnull=False, longitude__isnull=False)
          .filter(coordinate_source="")            # legacy only
          .exclude(location_text="")               # need text to re-suggest
          .order_by("name")[:max_places])
    out = []
    for p in qs:
        try:
            hits = geocode.search(p.location_text.strip(), limit=1)
        except Exception as exc:  # a scan must never break on one place
            logger.warning("location review: geocode failed for place %s: %s", p.pk, exc)
            continue
        if not hits:
            continue
        s = hits[0]
        dist = haversine_m(p.latitude, p.longitude, s["lat"], s["lon"])
        if dist < min_distance_m:
            continue
        out.append({
            "place": p, "cur_lat": p.latitude, "cur_lon": p.longitude,
            "sug_lat": s["lat"], "sug_lon": s["lon"], "sug_label": s["label"],
            "distance_m": int(round(dist)),
        })
    out.sort(key=lambda c: c["distance_m"], reverse=True)
    return out


def distance_phrase(metres):
    """Human distance for the UI."""
    if metres < 1000:
        return "%d m" % metres
    return "%.1f km" % (metres / 1000.0)
