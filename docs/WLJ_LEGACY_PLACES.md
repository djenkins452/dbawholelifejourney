# WLJ Legacy — Places Domain (as-built reference)

**Status:** Complete & production-verified (2026-07-06). **App:** `apps/legacy` · **URL namespace:** `/legacy/places/`
**Read this if:** you are working on Place maps, coordinates, geocoding, or any feature that needs a location.

Places are the locations that mattered in a life — homes, towns, a family farm, a favorite table. A Place is a **canonical Legacy entity**: it owns its identity, its story, and — the focus of this document — **its coordinates**. Every other feature (Stories, Timeline, People, Memories, Events, and the assistant) *consumes* a Place; none stores its own copy of a location.

---

## 1. The governing principles

1. **The Place is the single owner of its coordinates.** No separate location model, no duplicated lat/long anywhere else. Consumers read `Place.latitude`/`Place.longitude`.
2. **One interactive map, always.** The map is simply part of editing a Place (the same CRUD philosophy as every canonical entity) — not a special "resolve" or "compare" workflow. It is read-only until you interact, then an editable *Current → New* preview with Save / Cancel. Nothing commits until Save.
3. **One mapping provider: Esri.** Esri tiles (Streets + Satellite) and the Esri World Geocoding Service — chosen for a single ecosystem, attribution, and (future) API key. The retired OpenStreetMap tile server and Nominatim geocoder are no longer used in the product.
4. **Coordinates always carry provenance.** Every write records *how* the coordinate was set (`coordinate_source`). This exists because the absence of provenance was the root cause of a long debugging saga.
5. **Provider-independent maintenance.** The one-time location review asks "is the *current* coordinate correct?" using only Esri as a second opinion — it never re-calls the retired Nominatim.

---

## 2. Data dictionary — `Place` (`apps/legacy/models.py`)

`Place(LegacyOwnedModel)` — user-owned, soft-deletable.

| Field | Type | Notes |
|---|---|---|
| `name` | CharField(200), indexed | Display name ("The lake house"). |
| `location_text` | CharField(255), blank | The address/city the map geocodes from. NOT the name — a bare personal name ("Grandma's house") is never geocoded. |
| `description` | TextField, blank | "What it was" narrative. |
| `latitude` | Decimal(9,6), null | WGS84, 6 dp (~0.1 m). Owned here; consumed everywhere. |
| `longitude` | Decimal(9,6), null | WGS84, 6 dp. |
| `coordinate_source` | CharField(12), choices, default `''` | Provenance — see below. Migration `0035`. |
| `primary_photo` | FK→Media, null | Optional photo. |
| `significance` | PositiveSmallInt | Ranking hint. |

**`coordinate_source` values (`Place.CoordinateSource`):**
- `''` **Unknown / legacy** — set before provenance existed; the *only* rows the location review considers.
- `esri` — auto-geocode, a chosen search result, or an accepted review suggestion.
- `pin` — the keeper dropped a pin on the map.
- `manual` — lat/long typed on the Place form.
- `reviewed` — confirmed correct in the location review (coordinates kept as-is).

**Derived helpers on `Place`:**
- `has_coordinates` → both lat & lon set.
- `map_query` → `location_text` (the geocodable string) or `""`.
- `maps_link_url` → "Open in Google Maps" href. Coordinate form: `https://www.google.com/maps/search/?api=1&query=<lat>%2C<lng>` (Google's documented raw-coordinate pin; comma URL-encoded). Text-only Places use the location name.
- `set_coordinates(lat, lon, source, save=True)` — **the single write point**; a coordinate never lands without a source.

---

## 3. The interactive map (`templates/legacy/place_detail.html`)

One Leaflet map per Place (`#placeMapCard`). Leaflet is **self-hosted** at `static/legacy/vendor/leaflet/` (served from `'self'` — no CSP change; images under `vendor/leaflet/images/`).

- **Tiles (Esri):** Streets = `World_Street_Map` (default), Satellite = `World_Imagery` — `server.arcgisonline.com/ArcGIS/rest/services/<layer>/MapServer/tile/{z}/{y}/{x}` (note `y/x` order), allowed by CSP `img-src https:`. A Streets/Satellite toggle switches layers.
- **Read-only until interaction.** Searching or moving the pin enters edit state showing **Current location → New location (preview)** with **Save changes / Cancel**. Cancel reverts; nothing commits until Save.
- **Pin** = a Leaflet `circleMarker` (no marker-image assets needed).
- **Provenance:** the client sends `source` on save — a chosen search result → `esri`, a map click → `pin`.

CSP note: no changes were needed — Leaflet is same-origin, tiles are https images, and all geocoding goes through our own endpoints (`connect-src 'self'`).

---

## 4. Geocoding pipeline (`apps/legacy/services/geocode.py`)

**Provider: Esri ArcGIS World Geocoding Service** (`geocode.arcgis.com/.../findAddressCandidates` and `.../reverseGeocode`). Chosen because Nominatim returns empty for many valid US residential addresses (proven: "3242 Old Plantation Way, Maryville, TN 37804" → Nominatim `[]`, Esri → score-100 PointAddress). Esri location coordinates are `x=lon, y=lat` (do not swap).

Public API (best-effort, guarded, **never raises**; every call logs the exact request URL (token redacted), HTTP status, and candidate/returned counts):
- `search(query, limit=5)` → `[{label, lat, lon, score}]`. Nothing filtered by score.
- `reverse(lat, lon)` → address string.
- `geocode(query)` → single best `(lat, lon)` or `None`.
- `parse_latlon(lat, lon)` → validated `(Decimal, Decimal)` or `None`.
- `ensure_place_coordinates(place)` → one-time auto-geocode of `location_text`, cached on the Place with `source='esri'` (called from `PlaceProfileView`).

Optional `ARCGIS_API_KEY` (`settings` or env) is sent automatically when configured; token-free works for display. Licensing: persisting geocodes at scale should use an API key (same posture as the keyless tiles).

**The browser never calls a geocoder directly.** Search and reverse go through our own endpoints so the request stays server-side.

---

## 5. One-time location review (`apps/legacy/services/location_review.py`)

`/legacy/places/review-locations/` (linked from the Places header). **Provider-independent** — Esri + plane geometry only, never Nominatim.

For each *legacy* Place (`coordinate_source=''`) with `location_text`, it asks Esri for a fresh suggestion and, when it differs from the current coordinate by **> 25 m**, surfaces: Current coords, Esri-suggested coords, the distance apart, and a comparison map (grey pin = current, gold pin = suggested, connector line). The keeper chooses:
- **Keep current** → `coordinate_source='reviewed'` (coordinates untouched).
- **Use suggested** → adopts the Esri coordinates, `coordinate_source='esri'`.

Nothing changes without an explicit choice. Reviewed/sourced rows are excluded, so the list is **self-terminating**. `haversine_m()` / `distance_phrase()` are the geometry helpers. One Esri call per candidate — an explicit maintenance scan, never the hot request path.

---

## 6. URLs / views / services inventory

**URLs (`apps/legacy/urls.py`, namespace `legacy:`):**
- `places/` `places` · `places/new/` `place_new` · `places/<pk>/` `place_detail` · `places/<pk>/edit/` `place_edit`
- `places/<pk>/locate/search/` `place_locate_search` · `.../reverse/` `place_locate_reverse` · `.../save/` `place_locate_save`
- `places/review-locations/` `location_review` · `places/<pk>/review-location/` `location_review_apply`
- `places/<pk>/archive/` `place_archive` · `places/<pk>/restore/` `place_restore`

**Views (`apps/legacy/views.py`):** `PlacesView`, `PlaceCreateView`, `PlaceEditView`, `PlaceProfileView`, `PlaceLocateSearchView`/`ReverseView`/`SaveView` (JSON/redirect), `LocationReviewView`, `LocationReviewApplyView`, `PlaceArchiveView`/`RestoreView`.

**Services:** `services/geocode.py`, `services/location_review.py`.

**Endpoints (JSON, own-scoped, POST):** `place_locate_search` `{q}`→`{results:[{label,lat,lon}]}`; `place_locate_reverse` `{lat,lon}`→`{address}`; `place_locate_save` `{lat,lon,source}`→redirect.

There is **no public/mobile API** for Places beyond these session-authenticated endpoints.

---

## 7. History that shaped the design (so earlier docs make sense)

- Google's keyless embed is dead (404 + X-Frame-Options) → the map is self-hosted Leaflet, not an iframe. "Open in Google Maps" is a *link* only.
- The provider comparison (`?compare=1`, OSM/CARTO/Esri Streets/Esri Satellite) was a **temporary** evaluation tool, now removed; Esri won. Evaluation record: `docs/WLJ_LEGACY_MAP_TILES.md`.
- A temporary glass-box debug endpoint (`/legacy/debug/map/`) was used to prove the pipeline during the coordinate investigation; removed once the incidents closed (Runtime-Trace protocol).
- The "Open in Google Maps lands nearby" bug was **stale Nominatim coordinates**, not the URL — fixed by re-geocoding with Esri and saving. This is why provenance + the location review exist.

---

## 8. Related documentation
- `docs/WLJ_LEGACY_MAP_TILES.md` — tile/geocoder provider evaluation + decision record (Esri).
- `docs/WLJ_LEGACY_DOMAIN_ARCHITECTURE.md` — the Legacy canonical-truth model Places belongs to.
- `docs/WLJ_RUNTIME_TRACE_DEBUGGING.md` — the protocol used to fix the coordinate bugs by evidence.
- Tests: `apps/legacy/tests/test_places_map.py`, `test_connections.py::PlaceMapLinkTests`.
