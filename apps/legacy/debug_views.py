"""Glass-box debug endpoint for the Place resolution pipeline (Runtime-Trace protocol,
docs/WLJ_RUNTIME_TRACE_DEBUGGING.md). Temporary — remove when the two Place incidents close.

`/legacy/debug/map/?place=<pk>` — proves five-way agreement for Issue 1 (Open in Google
Maps lands off the Esri pin): raw DB coords → Place object → the ACTUAL rendered page
(cache-bypassing origin GET) data-lat/data-lon + the Open-in-Maps href → the coords inside
that href. Also lists every candidate Google URL format side-by-side so the coordinate that
Google honours is determined IN PRODUCTION by clicking, not assumed here.

`/legacy/debug/map/?q=<address>` — proves Issue 2 (search) with the EXACT geocoder request
URL, HTTP status, raw response body, candidate count, and how many were dropped.

Never composes or summarises — it shows deterministic raw truth only.
"""

import html as _html
import re
import subprocess
from urllib.parse import quote, urlparse, parse_qs

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View

from apps.legacy.models import Place
from apps.legacy.services import geocode


def _git_commit():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL,
            timeout=2).decode().strip()
    except Exception:
        return "unknown"


def _google_url_candidates(lat, lon):
    """Every plausible Google Maps URL for a coordinate — Danny clicks each in production
    to find the one that pins EXACTLY on the Esri location. No assumptions."""
    ll = "%s,%s" % (lat, lon)
    enc = quote(ll)
    return [
        ("search_api_encoded  (docs-recommended · current default)",
         "https://www.google.com/maps/search/?api=1&query=%s" % enc),
        ("q_plain  (previous attempt)", "https://www.google.com/maps?q=%s" % ll),
        ("q_encoded", "https://www.google.com/maps?q=%s" % enc),
        ("place_path", "https://www.google.com/maps/place/%s" % ll),
        ("place_at_zoom", "https://www.google.com/maps/place/%s/@%s,18z" % (ll, ll)),
        ("ll_and_q", "https://maps.google.com/?ll=%s&q=%s&z=18" % (ll, ll)),
    ]


def _origin_render(place):
    """Cache-bypassing GET of the REAL place-detail page via the test client, so we read
    what the browser actually receives — not what we assume. Extracts the Esri map's
    data-lat/data-lon and the Open-in-Maps href from the rendered HTML."""
    from django.test import Client
    out = {"view_class": None, "template": None, "status": None,
           "data_lat": None, "data_lon": None, "maps_href": None, "error": None}
    try:
        url = reverse("legacy:place_detail", args=[place.pk])
        from django.urls import resolve
        match = resolve(url)
        out["view_class"] = getattr(match.func, "view_class", match.func).__name__
        out["template"] = getattr(getattr(match.func, "view_class", None), "template_name", None)
        c = Client()
        c.force_login(place.user)
        resp = c.get(url, HTTP_HOST="wholelifejourney.com", secure=True)
        out["status"] = resp.status_code
        body = resp.content.decode("utf-8", "replace")
        tag = re.search(r'<section[^>]*id="placeMapCard"[^>]*>', body)
        if tag:
            t = tag.group(0)
            m_lat = re.search(r'data-lat="([^"]*)"', t)
            m_lon = re.search(r'data-lon="([^"]*)"', t)
            out["data_lat"] = m_lat.group(1) if m_lat else "(missing)"
            out["data_lon"] = m_lon.group(1) if m_lon else "(missing)"
        href = re.search(r'href="([^"]*google\.com/maps[^"]*)"', body)
        out["maps_href"] = _html.unescape(href.group(1)) if href else "(no Open-in-Maps link)"
    except Exception as exc:  # debug endpoint must never 500
        out["error"] = repr(exc)
    return out


@method_decorator(login_required, name="dispatch")
class LegacyMapDebugView(View):
    def get(self, request, *args, **kwargs):
        rows = ["<h1>Legacy Place map — glass box</h1>",
                "<p>commit <code>%s</code></p>" % _git_commit(),
                '<form method="get" style="margin:12px 0"><input name="q" size="60" '
                'placeholder="address to geocode" value="%s"> '
                '<input name="place" size="6" placeholder="place pk" value="%s"> '
                '<button>Run</button></form>'
                % (_html.escape(request.GET.get("q", "")), _html.escape(request.GET.get("place", "")))]

        pk = request.GET.get("place")
        if pk:
            rows.append(self._place_section(request, pk))

        q = request.GET.get("q")
        if q:
            rows.append(self._search_section(q))

        body = ("<style>body{font:14px/1.5 monospace;max-width:960px;margin:24px auto;padding:0 16px}"
                "table{border-collapse:collapse;width:100%%;margin:8px 0}td,th{border:1px solid #ccc;"
                "padding:6px 8px;text-align:left;vertical-align:top}code{background:#f4f4f4;padding:1px 4px}"
                "a{color:#1558b0}.ok{color:#0a7a2f;font-weight:bold}.bad{color:#c0392b;font-weight:bold}"
                "pre{background:#f4f4f4;padding:10px;overflow:auto;white-space:pre-wrap}</style>"
                + "".join(rows))
        return HttpResponse(body)

    def _place_section(self, request, pk):
        try:
            place = Place.all_objects.filter(user=request.user, pk=pk).first()
            if place is None and request.user.is_superuser:
                place = Place.all_objects.filter(pk=pk).first()   # superuser can inspect any
        except (ValueError, TypeError):
            place = None
        if not place:
            return "<h2>Place %s</h2><p class='bad'>not found</p>" % _html.escape(str(pk))

        db_lat, db_lon = place.latitude, place.longitude       # raw DB record
        origin = _origin_render(place)                          # what the browser receives
        link = place.maps_link_url                              # the object's generated link
        link_q = parse_qs(urlparse(link).query).get("query", [""])[0] if link else ""

        # Five-way agreement: DB → object data-attrs (rendered) → the URL's coords.
        db_pair = "%s,%s" % (db_lat, db_lon) if place.has_coordinates else "(none)"
        rendered_pair = "%s,%s" % (origin["data_lat"], origin["data_lon"])
        agree = (place.has_coordinates and str(db_lat) == str(origin["data_lat"])
                 and str(db_lon) == str(origin["data_lon"]))
        verdict = "<span class='ok'>MATCH</span>" if agree else "<span class='bad'>DIVERGENCE</span>"

        s = ["<h2>Place %s — %s</h2>" % (place.pk, _html.escape(place.name)),
             "<table>",
             "<tr><th>Layer</th><th>Value</th></tr>",
             "<tr><td>1. DB record (canonical Place)</td><td>lat=<code>%s</code> lon=<code>%s</code></td></tr>"
             % (db_lat, db_lon),
             "<tr><td>2. Esri map (rendered data-lat/data-lon)</td><td><code>%s</code> / <code>%s</code></td></tr>"
             % (origin["data_lat"], origin["data_lon"]),
             "<tr><td>3. Google URL query coords</td><td><code>%s</code></td></tr>" % _html.escape(link_q),
             "<tr><td>4. Exact Open-in-Maps href (as browser receives it)</td><td><code>%s</code></td></tr>"
             % _html.escape(origin["maps_href"] or ""),
             "<tr><td>DB == rendered Esri coords?</td><td>%s (DB <code>%s</code> vs rendered <code>%s</code>)</td></tr>"
             % (verdict, _html.escape(db_pair), _html.escape(rendered_pair)),
             "<tr><td>origin view / template / status</td><td>%s / %s / %s</td></tr>"
             % (origin["view_class"], origin["template"], origin["status"]),
             "</table>"]
        if origin["error"]:
            s.append("<p class='bad'>origin render error: %s</p>" % _html.escape(origin["error"]))

        if place.has_coordinates:
            s.append("<h3>Candidate Google URLs — click each in PRODUCTION; report which pins on the Esri spot</h3>")
            s.append("<table><tr><th>format</th><th>link</th></tr>")
            for name, url in _google_url_candidates(db_lat, db_lon):
                s.append("<tr><td>%s</td><td><a href='%s' target='_blank' rel='noopener'>%s</a></td></tr>"
                         % (_html.escape(name), _html.escape(url), _html.escape(url)))
            s.append("</table>")
        else:
            s.append("<p>Place has no coordinates yet — resolve it on the map first.</p>")
        return "".join(s)

    def _search_section(self, q):
        p = geocode.probe(q)
        s = ["<h2>Geocode search — %s</h2>" % _html.escape(q),
             "<table>",
             "<tr><td>provider</td><td>%s</td></tr>" % p["provider"],
             "<tr><td>1. exact string submitted</td><td><code>%s</code></td></tr>" % _html.escape(p["submitted"]),
             "<tr><td>2. exact request URL</td><td><code>%s</code></td></tr>" % _html.escape(p["request_url"]),
             "<tr><td>HTTP status</td><td>%s</td></tr>" % p["http_status"],
             "<tr><td>raw candidates</td><td>%s</td></tr>" % p["raw_candidate_count"],
             "<tr><td>returned</td><td>%s</td></tr>" % p["returned_count"],
             "<tr><td>5. dropped (no valid coords)</td><td>%s</td></tr>" % p["dropped_no_coords"],
             "<tr><td>token configured</td><td>%s</td></tr>" % p["token_configured"],
             "</table>",
             "<h3>3. raw response body</h3><pre>%s</pre>" % _html.escape(p["raw_response"] or "(empty)"),
             "<h3>4. parsed results (nothing filtered by score)</h3><pre>%s</pre>"
             % _html.escape("\n".join("%s  (%s, %s)  score=%s" % (r["label"], r["lat"], r["lon"], r["score"])
                                      for r in p["results"]) or "(none)")]
        return "".join(s)
