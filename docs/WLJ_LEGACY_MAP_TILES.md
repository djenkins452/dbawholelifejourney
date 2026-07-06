# Legacy Map Tiles — provider evaluation & OSM retirement plan

**Status:** ✅ DECIDED & IMPLEMENTED — **Esri** (World Street Map default + World Imagery satellite). Comparison mode removed; `tile.openstreetmap.org` + `export/embed.html` retired. · **Owner:** Legacy/Places
**Goal:** the map must let the keeper *immediately understand where a Place is* — not imitate Google Maps.

## Decision (2026-07-06)

Danny chose **Esri as the single map provider** — Esri Streets (default) + Esri World Imagery (satellite), toggled on every Place. Rationale was architectural, not cosmetic: one ecosystem / attribution / (future) API key / licensing relationship, and consistent rendering, zoom, and labels across Streets ↔ Satellite. (CARTO Voyager was marginally cleaner for streets, but single-vendor consistency won.)

**Shipped:** every Place detail now has ONE interactive Leaflet map (self-hosted Leaflet, Esri tiles) — read-only until you search or move the pin, then an editable Current → New preview with Save / Cancel (nothing commits until Save). The separate "resolve" and temporary "compare" modes are gone; the map is simply part of editing a Place. Geocoding (search/reverse) stays on keyless Nominatim, server-side. The historical evaluation + retirement plan below is kept as the decision record.

---

## 1. Why this exists

Legacy renders Place maps two ways today, both on the **public OpenStreetMap tile server** (`tile.openstreetmap.org`, directly or via `openstreetmap.org/export/embed.html`):

- **Resolver** (unresolved Place): a self-hosted **Leaflet** map for search + drop-a-pin.
- **Resolved Place**: a static `export/embed.html` **iframe** centred on the saved coordinates.

**Problem:** the OSMF Tile Usage Policy **prohibits heavy/commercial/production use** of that public server — no SLA, aggressive rate-limiting, and they can block apps. So it's a latent **reliability + licensing risk** regardless of aesthetics, and the plain OSM style is also busier/less readable than the alternatives.

---

## 2. Temporary comparison mode (shipped)

Opt-in, evidence-based evaluation on the **same real Place**:

- Visit a **resolved** Place and append **`?compare=1`** (or click **"Compare map styles →"** on the map card).
- The static map is replaced by an interactive Leaflet map with a base-layer switcher:
  **Current OSM · CARTO Voyager · Esri Streets · Esri Satellite** (starts on OSM).
- Keyless endpoints are used **for evaluation only** (fine for light/eval traffic; not the production posture — see §4).
- No CSP change needed: tiles are `img-src https:` images; Leaflet is self-hosted (`static/legacy/vendor/leaflet/`).

**This mode is temporary.** Once a provider is chosen, remove the `?compare=1` branch (`PlaceProfileView.tile_compare`, the `place-compare` template block, the compare link + CSS) and this section.

### Evaluation summary (for reference)

| Criterion | OSM Standard | CARTO Voyager | Esri Streets | Esri Satellite |
|---|---|---|---|---|
| Readability | busy | **cleanest** | very good | n/a (imagery) |
| Water clarity | good | **clear/calm** | very good | **actual imagery** |
| Satellite | ✗ | ✗ | ✗ | ✅ |
| Reliability | poor (policy) | good (CDN) | very good (CDN) | very good (CDN) |
| Licensing | tile server bans prod use | free + attribution; account at scale | free tier via ArcGIS key | free tier via ArcGIS key |

**Leading recommendation (pending Danny's eval):** a **Streets / Satellite toggle** — CARTO Voyager (streets, default) + Esri World Imagery (satellite). Single-vendor fallback: Esri (Topographic + Imagery under one key).

---

## 3. Where OSM tiles are referenced today (retirement surface)

1. `apps/legacy/models.py :: Place.maps_embed_url` → `openstreetmap.org/export/embed.html` (resolved-place iframe).
2. `templates/legacy/place_detail.html` → resolver Leaflet `L.tileLayer('…tile.openstreetmap.org…')`.
3. `templates/legacy/place_detail.html` → comparison mode "Current OSM" layer (temporary; removed with the mode).

Attribution today: `© OpenStreetMap contributors`.

---

## 4. Retirement plan — drop `tile.openstreetmap.org` for production

Independent of the final style choice, production must stop calling OSM's public tiles.

1. **Choose provider(s)** from the comparison mode (streets ± satellite).
2. **Register a free account / API key** with the chosen provider (CARTO free tier; and/or Esri ArcGIS Location Platform free tier ~millions of basemap tiles/month). Store the key in **env → settings** (e.g. `WLJ_MAP_TILE_KEY`, exposed to templates via context, never hard-coded).
3. **Convert the resolved-place map from the OSM `embed.html` iframe to a self-hosted Leaflet map** using the chosen provider (the comparison mode already proves this path). This is the key structural change — the iframe can't switch providers, so retiring OSM means owning the tile layer in Leaflet. `Place.maps_embed_url` can be retired or repurposed; keep `maps_link_url` (the Google *link*) as-is.
4. **Point the resolver's tile layer** at the chosen provider (one-line URL + attribution swap).
5. **Attribution**: render the provider's required string in Leaflet's attribution control (CARTO: `© OpenStreetMap contributors © CARTO`; Esri: `Tiles © Esri, …`).
6. **If a Streets/Satellite toggle is chosen**, keep a minimal `L.control.layers` with just those two — not the full four-way comparison.
7. **Remove** the temporary comparison mode and §2 of this doc.

**Acceptance:** no production request to `tile.openstreetmap.org` or `openstreetmap.org/export/embed.html`; maps render from the chosen CDN with correct attribution; the resolver + resolved views share one tile configuration; keys come from env.

**Non-goals:** self-hosting tiles (Protomaps) — revisit only if vendor cost/limits ever bite.
