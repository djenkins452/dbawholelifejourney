# WLJ Travel Intelligence — Canonical Domain Architecture & Product Vision

**Version:** 0.1 (DRAFT — for Danny's review; not yet ratified, not yet built)
**Authority:** Proposed governing architecture for a new first-class WLJ domain. Nothing in here is implemented. This document is the design artifact that precedes any code.
**Audience:** Danny (product/architecture judgment), and the engineers who will eventually build any travel, trip, route, itinerary, packing, or live-travel capability in WLJ.
**Scope note:** This defines Travel Intelligence as a Personal Truth Domain and its Chief of Staff behaviors. It conforms to the WLJ Constitution v1.0; the "Constitutional Compliance" appendix shows exactly how. No Constitutional Review is required — this domain fits inside the existing Articles.
**Existing foundations salvaged (not started from scratch):** the `TravelActiveRule` proactive insight (`apps/core/ai_insights/rules_context.py:502`), `travel` as a life category/tag (`apps/life/models.py`), and the `DomainClass.CONTEXT` placeholder that already names *"Travel, future"* (`apps/core/domain_registry/descriptors.py:26`). We reuse the geospatial stack (Legacy `Place`, Esri geocoder, `haversine_m`), the multimodal truth spine, the mobile ingest/audit pattern, the Journal draft lifecycle, and the session-grouping pattern. What is genuinely greenfield is called out honestly (device GPS).

---

## Executive Vision

Travel Intelligence is the Whole Life Journey domain responsible for a person's **entire relationship with travel across their lifetime** — not a single trip, and not a booking tool. Its purpose is to become a **lifelong Travel Chief of Staff**: an elite travel agent, executive assistant, tour guide, historian, logistics coordinator, and close friend who already knows everything about the traveler, folded into one relationship.

It is explicitly **not** Expedia (no booking engine), **not** Google Maps (no turn-by-turn navigation product), **not** Garmin (no fitness-device franchise), and **not** an itinerary spreadsheet. Those are transaction and utility products. Travel Intelligence is a **truth and relationship** product. The itinerary is a by-product; the accumulated understanding of *how this person travels, who they travel to see, and what makes a trip meaningful to them* is the asset.

The domain is organized around one governing idea:

> **A trip is a lifespan, not a document. Travel Intelligence owns the trip's envelope and its travel-native truth, and composes everything else a trip touches from the domains that already own it. Every completed trip makes the next trip better — deterministically, not by AI memory.**

Where Meal Intelligence's defining principle is *Capture Once, Reuse Everywhere*, Travel Intelligence's defining principle is **Compose, Don't Duplicate**. A trip is the one place in WLJ where health, people, journal, faith, finance, calendar, meals, and legacy all converge on a single stretch of a person's life. Travel Intelligence is the **orchestrating lens** over that convergence — it links and projects, it does not re-own. And it separates what is **permanent about the traveler** (durable, person-scoped preferences that outlive any trip) from what is **specific to one trip** (lifecycle-bound truth).

---

## Travel Is a Platform Consumer, Not a Parallel Architecture (the ratified framing)

**Strategic direction, ratified this session (2026-07-21):** Travel is **not "a Travel module with AI added to it."** It is one of the first flagship domains **built on top of the evolving Chief of Staff platform** — a *showcase* of the new architecture, never a parallel one. This is the direct application of the governing mental model in `01 §6` ("One Chief of Staff, many workspaces — the relationship never changes; only the workspace changes"), and it is now the intended pattern for **every future domain**.

**Travel introduces none of these** — doing so would violate the Constitution (multiple assistants / duplicate conversation systems / domain-specific reasoning are already forbidden):
- ❌ a Travel AI · ❌ a Travel conversation engine · ❌ Travel-specific reasoning · ❌ a second assistant · ❌ a duplicate memory system · ❌ a duplicate conversation system.

**Travel exposes only four kinds of platform-shaped capability**, and the one Chief of Staff reasons over them exactly as it does for every other domain:
1. **Deterministic travel truth** (the entities below).
2. **Travel workspaces** (surfaces the user works within).
3. **Travel actions/tools** (the safe, audited write path).
4. **Travel Current Context** (what the user is looking at, per workspace).

**The reusable platform capabilities Travel will consume — never reimplement:** Current Context · conversation continuity · workspace navigation · the discovery framework · the draft/workflow framework · the confirmation framework · multimodal intake · truth extraction · shared action execution. Every one of these is being generalized *now* out of Journal (the reference implementation). Travel is designed **after** those capabilities are reusable, so it lands as evidence that the platform generalizes — the success test is that a customer *never feels they changed assistants* moving from journaling to planning a motorcycle trip.

**Sequencing (do not misread this doc as a build order):** Travel is **not the next implementation milestone.** The current priority remains the CoS platform evolution (one continuous Chief of Staff · workspace-driven interaction · Current Context as a defining capability · generic reusable conversation/discovery/draft/confirmation/multimodal/action capabilities). Travel is designed here so that, while that platform work proceeds, we know which capabilities Travel will consume — and so the platform is shaped with a second real consumer in mind, not just Journal.

---

## The One Big Architectural Decision (read this first)

**Travel Intelligence must be a first-class `BEHAVIORAL` life domain that participates in the Chief of Staff — not a `CONTEXT` enrichment domain.**

Today the domain registry reserves Travel as `DomainClass.CONTEXT` ("Contextual enrichment (Travel, future)", `descriptors.py:26`). As written, `CONTEXT` is **not** in `USER_LIFE_DOMAINS`, `CROSS_DOMAIN_SOURCES`, or `COS_PARTICIPATING`. A `CONTEXT` Travel domain would be a passive tag on other data — it could *color* a health reading ("you were traveling") but could never be dreamed about, planned with, acted in, or reasoned over as its own life area.

That is the wrong altitude for the product described above. The vision — dream, research, plan, prepare, travel, adapt, remember, improve — is the behavior of a **primary life domain the CoS actively serves**, exactly like Health or Faith. It has its own entities, its own lifecycle, its own conversation, its own actions, and its own retrievable truth.

**Recommendation:** classify Travel Intelligence as `BEHAVIORAL`, register a full `DomainCapability`, and update the `descriptors.py:26` comment. Retain the *idea* behind `CONTEXT` — travel genuinely does enrich other domains ("this weight reading happened on the road") — but express that as **cross-domain projection/linking**, which every behavioral domain already does, not as a second-class classification. This is a normal in-Constitution decision (Article III lets each domain own its truth); it needs Danny's product sign-off, not a Constitutional Review.

---

## Guiding Principles

Nine principles govern every design decision in this domain. They inherit the platform discipline (WLJ owns truth; the model reasons) and specialize it for travel.

**T1 — Compose, don't duplicate.**
A trip touches health, people, journal, finance, calendar, meals, faith, and legacy. Travel Intelligence **owns only travel-native truth** (the trip envelope, route/geography, stops, itinerary intent, packing, vehicle/logistics, the travel session). Everything else it **links or projects** from the domain that already owns it. A "trip expense" is a Finance record tagged to a trip; a "person visited" is a People visit-event; a "trip journal" is a Journal entry scoped to the trip. Duplicating any of these would fork a truth authority — prohibited by Article III.1.

**T2 — Permanent traveler truth is separate from trip truth.**
Two partitions, always declared. **Traveler Profile** = durable, person-scoped preferences and constraints that persist across all trips (prefers scenic roads, comfortable daily mileage, hotel style, motorcycle vs car, relationship-first, remote-work-capable, never-arrive-late-to-family). **Trip Truth** = everything bound to one trip's lifecycle. The Profile is the compounding asset; each completed Trip is where the Profile learns. This mirrors Meal Intelligence's *supply is household / consumption is personal* split — the boundary is load-bearing and enables the "every trip makes the next better" promise without magic.

**T3 — The conversation creates the truth; forms are the fallback.**
The planning conversation is more valuable than the itinerary. *"I'm thinking about riding out west"* is a complete, valid beginning. The CoS discovers purpose, people, budget, timing, transport, and constraints **naturally, over days or months**, and each confirmed fact becomes structured trip truth through the existing multimodal spine (perceive → validate → confirm → persist → audit). A trip is never blocked on a form; a form is only ever an optional accelerator.

**T4 — A trip is a long-lived object with a lifecycle, not a draft that becomes final.**
Unlike a journal entry (a same-day draft that materializes once), a trip lives for weeks or months and moves through explicit stages (Dreaming → … → Completed → Story). The `Trip` is durable from the Dream stage; a `lifecycle_stage` state machine tracks where it is; the planning conversation continuously mutates it. (We reuse the Journal draft's hard-won mechanics — a dedicated lifecycle field, autosave that never fabricates empty records, one active object — but the shape is "durable object with stages," not "draft → entry.")

**T5 — WLJ owns deterministic travel truth; the model interprets it.**
Where you are, how far you've ridden, when you arrived, which places you've visited before, how long since you last saw someone — these are **deterministic facts** WLJ computes (from geography, breadcrumbs, and other domains' truth). *"Enjoy your visit," "you've earned this view," "maybe call Kelly"* is **interpretation** the model performs over those facts. WLJ never renders a verdict on the experience (Article I.4); it states the fact ("first visit to this place," "1,004 days since you last saw Kelly") and the model reasons.

**T6 — The Travel Session captures; it never interprets.**
A Travel Session is an **organizational construct** that groups the canonical rows produced during a trip (breadcrumbs, stops, place-visits, fuel, expenses, photos, voice notes, journal, weather, health) — it is explicitly **not** itself a source of truth, exactly as `BodyMeasurementSession` is documented today. The canonical truth lives in the owning domains; the session is the deterministic index that makes a trip a coherent chapter.

**T7 — Live truth is a fold of an append-only track.**
The GPS breadcrumb stream is an immutable, append-only ledger. "Current position," "distance traveled," "route so far," and "arrived at X" are always a **reproducible fold** of that ledger — never independently authored state. This is the Meal Intelligence *ledger-and-fold* discipline applied to geography, and it is what keeps live mode honest and replayable.

**T8 — The Trip Story is composed truth, never AI fiction.**
After a trip, WLJ generates a timeline, route, people visited, mileage, expenses, weather summary, favorite places, and lessons — **grounded entirely in the deterministically captured session truth**. The model narrates *from* these facts in the traveler's voice; it may not invent a place, a person, a number, or an event. A trip story is a projection, with provenance, not a generated story.

**T9 — Learning is explicit-first and default-deny.**
"Knowledge extracted" from a completed trip (new permanent preferences) is **proposed to the user and confirmed**, never silently absorbed. Reflection observes trips; it never learns around a deterministic defect, and it never rewrites the Traveler Profile on its own. This keeps the compounding-intelligence promise inside the Executive Reflection architecture (learning is default-deny; the user's explicit confirmation is the gate).

---

## Travel Domain Architecture

### The orchestrator shape

Most WLJ domains are **vertical**: they own a slice of life (medications, weight, journal entries) top to bottom. Travel Intelligence is **horizontal** — it is the one domain whose primary object (`Trip`) is a *time-and-place window that other domains' truth falls inside*. This is the same architectural role Calendar plays for time (the Calendar Projection Law: Calendar owns calendar-native objects and projects the rest) — Travel plays it for **a bounded stretch of life away from home**.

That yields a three-ring model:

1. **Core (Travel owns):** the trip envelope and travel-native truth — `Trip`, `TripStop`, `RouteSegment`, breadcrumb `TrackPoint`, `TravelSession`, `PackingList`/`PackingItem`, `TravelLeg`/transport, `Vehicle` logistics, `TravelerProfile` and its preferences.
2. **Linked (Travel references):** truth another domain owns, tagged to a trip — Finance expenses, People visit-events, Journal entries, Health readings, Meals eaten, Calendar events, Documents (reservations, tickets), Faith observations, Capture uploads.
3. **Projected (Travel composes):** read-only derived views that fuse core + linked into trip-level truth — the Trip Story, the trip timeline, "people I saw," "what this trip cost," "how far I rode."

### The two partitions (permanent vs trip)

```
TRAVELER PROFILE (person-scoped, durable, cross-trip)   TRIP TRUTH (trip-scoped, lifecycle-bound)
├─ Travel philosophy / purpose defaults                 ├─ Trip (envelope + lifecycle_stage)
├─ Preferred transport (motorcycle / car / air)         ├─ TripStop / RouteSegment / TrackPoint
├─ Comfortable daily mileage / pace                     ├─ TravelSession (organizational index)
├─ Lodging style / budget posture                       ├─ PackingList / PackingItem
├─ Relationship-first vs solitude-first                 ├─ Linked: expenses, people-visited,
├─ Scenic-road preference, music, food                  │   journal, health, meals, docs
├─ Health/mobility constraints                          └─ Projected: Trip Story, timeline, totals
├─ Remote-work capability
└─ Standing "rules" (never arrive late to family)
        ▲                                                       │
        └───────── knowledge extraction (explicit, T9) ────────┘
                    every completed trip proposes Profile updates
```

The arrow is the product. A trip is where the Profile *learns*; the Profile is what makes the next trip's conversation start miles ahead.

---

## Domain Objects (Canonical Model)

Entities are grouped by the *nature* of their truth (following the Meal Intelligence layering method). Layer assignment is the first decision for any new entity.

**Traveler standing truth (person, durable)**
`TravelerProfile` · `TravelPreference` (typed key/value with provenance + confidence) · `TravelConstraint` (health/mobility/temporal) · `TravelRule` (standing directive, e.g. "never arrive after dark on family visits") · `Vehicle` (the bike/car as a reusable asset with maintenance intervals).

**Trip envelope (trip, durable through lifecycle)**
`Trip` (name, purpose, `lifecycle_stage`, date window (soft while dreaming), home anchor, primary mission link) · `TripParticipant` (who's going — links People) · `TripPurpose` (why — links Goals/Missions/People).

**Itinerary intent (trip, revisable, not yet fact)**
`TripLeg` (a movement between two places, with transport mode) · `TripStop` (a place + planned dwell, ordered) · `RouteSegment` (planned path, distance estimate) · `Reservation` (lodging/tickets — a lightweight record that *links* a Document + optional Finance commitment; Travel does not become a booking ledger) · `PackingList` / `PackingItem` (generated from trip shape + Traveler Profile + weather).

**Execution / live truth (trip, immutable spine)**
`TravelSession` (the window: `started_at`/`ended_at`, `source`, `sync_id`, groups-canonical-rows — an organizational construct, **not** truth) · `TrackPoint` (append-only breadcrumb: lat/lon/ts/accuracy/speed/battery — the ledger) · `PlaceVisit` (a detected/confirmed arrival at a `Place`, with arrival/departure, provenance) · `FuelStop` / `MaintenanceEvent` (vehicle events) · `Detour` / `Waypoint` (unplanned stop).

**Linked truth (owned elsewhere, tagged to a trip)**
`TripExpense` → Finance · `TripJournalLink` → Journal · `TripPersonVisit` → People visit-event · `TripHealthWindow` → Health readings in-window · `TripMeal` → Meals · `TripDocument` → Documents/Capture · `TripCalendarLink` → Calendar events.

**Derived & outcome truth (read-computed, never authored, always reproducible)**
`TripTimeline` · `TripRoute` (fold of TrackPoints) · `TripTotals` (miles, days, cost, places, people) · `TripWeatherSummary` · `TripStory` (composed narrative + provenance) · `TripLessons` (candidate Profile updates awaiting confirmation).

**Salvaged / reused (not new):**
Legacy `Place` (+ `set_coordinates` provenance discipline) is the **canonical destination anchor** — Travel never invents a second place model. The Esri geocoder (`apps/legacy/services/geocode.py`) and `haversine_m` (`location_review.py:19`) are reused verbatim for naming and geofencing. The multimodal artifact spine ingests reservations/receipts/screenshots. `TravelActiveRule` becomes one signal into the domain.

---

## Truth Model — Ownership

**Owner** is the single authoritative producer (Article III.1). **Scope** is Person (durable traveler truth), Trip (lifecycle-bound), or Projection (read-computed, never authored). Anything marked *link* is owned by another domain and only *referenced* here.

| Entity | Owner | Scope |
|---|---|---|
| TravelerProfile · TravelPreference · TravelConstraint · TravelRule | **Travel** | Person |
| Vehicle (asset + maintenance intervals) | **Travel** | Person |
| Trip (envelope + lifecycle_stage) | **Travel** | Trip |
| TripLeg · TripStop · RouteSegment · PackingList/Item | **Travel** | Trip |
| TravelSession (organizational index) | **Travel** | Trip |
| TrackPoint (breadcrumb ledger) | **Travel** | Trip |
| PlaceVisit · FuelStop · MaintenanceEvent · Detour | **Travel** | Trip |
| `Place` (destination anchor) | **Legacy** | link (Person) |
| Reservation *meaning*/document | **Documents/Capture** | link |
| Trip expenses | **Finance** | link |
| Trip journal entries | **Journal** | link |
| People visited (visit-event, "last saw") | **People** | link |
| Health readings during a trip | **Health** | link |
| Meals eaten during a trip | **Meals** | link |
| Calendar events for the trip | **Calendar** | link |
| Faith observations during a trip | **Faith** | link |
| TripTimeline · TripRoute · TripTotals · TripWeatherSummary | **Travel (projection)** | Projection |
| TripStory · TripLessons | **Travel (projection)** | Projection |

**Ledgers (T7):** `TrackPoint` is the one append-only geospatial ledger; `TripRoute`, `TripTotals.miles`, and "current position" are folds of it. `PlaceVisit` is a thin confirmed record emitted from the fold (arrival detected → candidate → confirmed), never authored blind.

---

## Conversation Model

The conversation is the product (Article V), so the conversation is designed, not incidental.

**Discovery, not interrogation.** The CoS treats travel talk as a **long-running, resumable subject**. A single sentence opens a Trip in the Dreaming stage. From there the model asks *one natural question at a time, only when it advances the trip* — never a form, never a batch. Each answer that is a durable fact is written to the Trip (or, if cross-trip, proposed to the Traveler Profile) through the confirmation-gated spine.

**Two write channels, one trip (Journal-draft insight).** The planning conversation carries both the **transcript** (what was said) and any **typed/structured notes** (a pasted itinerary, a photographed reservation, a list of stops). Both compose into the trip's structured truth — the model reads what's already on the trip and does not re-ask, exactly as the Journal conversation reads `written_body` before responding.

**Multimodal by default.** "Here's my hotel confirmation" (screenshot), "this is the route I'm thinking" (map photo), "here's the group text about dates" — each is perceived by the model and flows through the existing artifact spine into structured trip truth (`Reservation`, `TripStop`, dates), tagged `source_artifact_id` + `confidence`. Travel adds **no new upload path** (Multimodal Intake architecture).

**Conversation State, not a new memory.** "The trip we're planning" is tracked in Conversation State (the deterministic "what are we talking about / waiting on" authority) as the active subject — a reference to the `Trip`, not a summary. The model reasons over it; it is not a second retrieval surface.

**The lifecycle mechanics (reused from Journal, generalized):**
- A dedicated lifecycle field on `Trip` (call it `lifecycle_stage`) — **never** reuse `UserOwnedModel.status`, which is owned by soft-delete (`SoftDeleteManager`); the Journal domain learned this the hard way (`journal/models.py:330`).
- Autosave of the in-progress trip is request-path-safe and **never fabricates an empty trip** — merely mentioning travel does not create a record; a Trip is created only when there is real content or an explicit "start planning this."
- At most one *active planning conversation* per trip; returning always resumes it (durability), so a trip can be built across months.

---

## Travel Lifecycle

`Trip.lifecycle_stage` is the state machine. Stages are deterministic truth (the model narrates them; it never invents them). Transitions are mostly explicit (user or confirmed action); a few are event-driven (Traveling begins when a Travel Session opens).

| Stage | What is true | Primary CoS role |
|---|---|---|
| **Dreaming** | A wish exists; dates/route soft or absent | Expand the dream, surface possibilities, connect to missions/people |
| **Researching** | Options being gathered (places, routes, seasons, costs) | Elite travel-agent research over facts; capture findings as structured options |
| **Planning** | A shape is forming — legs, stops, rough dates, budget | Logistics coordinator: sequence, feasibility, conflicts, Profile-fit |
| **Booked** | Reservations/commitments exist (linked Documents/Finance) | Confirm coverage, flag gaps, assemble the trip's document set |
| **Preparing** | Trip is near; readiness work outstanding | Checklists, vehicle maintenance, health prep, people heads-up |
| **Packing** | Departure imminent | Generate/adapt packing from trip + Profile + weather |
| **Traveling** | A Travel Session is open; the person is on the trip | Live contextual awareness (GPS mode), adaptation, in-the-moment capture |
| **Completed** | Session closed; person home | Reconcile captured truth; nothing more required of the user |
| **Trip Story** | Deterministic story composed from session truth | Narrate the trip in the traveler's voice, from facts |
| **Knowledge Extracted** | Candidate Profile updates confirmed | Fold confirmed lessons into the Traveler Profile (T9) |

"Future recommendations" is not a stage — it is the **standing effect** of an updated Traveler Profile on the *next* trip's Dreaming/Planning conversation. That closed loop is the whole point.

---

## GPS / Live Travel Architecture

This is the flagship capability and the **most greenfield**. Be honest: today WLJ has **zero device location** — no CoreLocation, no location entitlement, no background-location mode, and HealthKit workouts are ingested *without* their GPS routes. Everything below is new device + storage + ingest plumbing. It is also the heaviest (battery, privacy, iOS review), which is why the MVP does **not** start here.

**GPS is not a navigation product, and location truth is not a Travel-only capability (ratified direction).** WLJ is not building another Apple Maps / Google Maps / Garmin — turn-by-turn navigation belongs to them. WLJ becomes **context-aware** instead ("I see you've arrived at Aunt Janice's," "you've ridden almost 5,000 miles," "oil service due soon," "rain begins around 2 PM," "enjoy your visit"). And the underlying **deterministic location truth should be a shared *platform* capability that multiple domains can consume** — Health ("this reading happened while traveling"), People ("you were near Kelly"), Legacy ("a memory at this place"), Faith, Capture — not a silo owned by Travel. **Travel is expected to be the first major consumer of that platform capability, not its owner.** Architecture first; no implementation this session. When it is built, it lands as a shared location-truth service behind the platform, and Travel reads it exactly as any domain would.

### The division of labor (constitutional)

- **iOS captures** raw location (CoreLocation), batches it, and hands it to the backend. The device never interprets.
- **WLJ owns deterministic geospatial truth:** the breadcrumb ledger, distance (Esri/haversine), current position, arrival/departure detection, "first visit," "days since last visit here," fuel/range math, next-service mileage.
- **The model interprets:** *"Enjoy your visit," "you've earned Beartooth Pass," "maybe text Steve you're 40 minutes out."* WLJ supplies the facts; the model supplies the warmth (T5).

### Ingestion (reuse the health-ingest pattern exactly)

A new `POST /api/mobile/travel/ingest/` mirrors `health/ingest/`: batched `TrackPoint` uploads, **idempotent via `sync_id`**, audited by a `TravelIngestionRun` (copy `HealthIngestionRun`'s status lifecycle + per-batch result JSON + `client_debug` glass-box telemetry). The `wljBridge` WKWebView message handler (`MainWebView.swift`) gains `startTrip` / `stopTrip` / location-permission actions — the transport already exists; we extend it, we don't reinvent it.

### Arrival detection ("I see you've arrived at Aunt Janice's")

Deterministic, reusing salvaged code:
1. Fold recent `TrackPoint`s → a dwell cluster (stationary > N minutes within R meters — `haversine_m`).
2. Match the cluster centroid against the user's `Place`s (Legacy) within radius → candidate `PlaceVisit`.
3. If no known place, **reverse-geocode** the centroid (Esri `reverse(lat,lon)`) to a candidate name; offer to save it as a `Place` (through `set_coordinates(source="reviewed")` provenance).
4. Emit a `PlaceVisit` candidate; the model narrates. "First visit" and "days since last visit" are joins against `PlaceVisit` history and the People domain's "last saw" truth.

### Battery, privacy, offline, iOS (research posture — not implemented)

- **Battery:** significant-location-change + region monitoring while idle; high-frequency GPS only during an *active Travel Session*; adaptive sampling (dense on movement, sparse at dwell). Batch-upload on wifi/charging where possible.
- **Privacy (non-negotiable):** live tracking is **opt-in per trip**, never always-on; a visible "tracking this trip" state; local-first buffering; the user can pause, redact a segment, or discard a session. Location is the most sensitive data in WLJ — it gets its own consent, its own retention policy, and never leaves the user's ownership boundary. (Coordinates never go in URLs/query strings — platform rule.)
- **Offline:** the phone will lose signal (that's the point of "out west"). The device buffers `TrackPoint`s locally and reconciles on reconnect via `sync_id` idempotency; live-mode narration degrades gracefully to "last known" with honest freshness.
- **iOS:** requires adding the `location` background mode, a location entitlement, and `NSLocation*UsageDescription` strings — none exist today. A dedicated CoreLocation manager (sibling of `HealthKitManager`) with its own `BGTaskScheduler` identifier.

### What WLJ deterministically knows in live mode (facts the model narrates)

Position · route-so-far · distance today / trip-total · current place (matched or reverse-geocoded) · first-visit vs return · days-since-last-visit (here / this person) · planned-dwell vs actual · next fuel/range (vehicle range − miles since fill) · next service (interval − odometer) · weather-at-position (Dashboard weather service) · who/what is associated with this place (People/Legacy memories). **Everything narratable in the prompt's examples is a deterministic join — none of it is the model guessing.**

---

## Travel Session Architecture

A **Travel Session** is the continuous-capture window that turns a trip into a coherent, permanent chapter. It is a **new data shape** for WLJ (a time-series stream — nothing today continuously captures one), modeled on the framing that already works for `BodyMeasurementSession` and `WorkoutSession`.

**It is an organizational construct, not a source of truth (T6).** Like `BodyMeasurementSession` ("groups… but is NOT a source of truth"), the session **groups canonical rows** produced by the owning domains during the window. Delete the session and the underlying truth still stands; the session is the deterministic *index* that says "these belong to the same trip."

**Shape (reused):**
- `started_at` / `ended_at` (the window), `source`, `sync_id` with a partial unique constraint for idempotent ingest (copy `BodyMeasurementSession`).
- Opens when travel starts (explicit "start trip" or first sustained departure from home); closes on return home or explicit stop. **Operator controls required** (Administrator Experience Checklist): start, stop/cancel (cooperative — never an orphaned open session), monitor (live status + freshness heartbeat), recover (resume after app kill / signal loss), understand (active vs finished vs interrupted).

**What it groups (all owned elsewhere, tagged in-window):** `TrackPoint` route · `PlaceVisit` stops · `FuelStop`/`MaintenanceEvent` · Meals eaten · Journal entries · Capture photos/voice notes · Finance expenses · Health readings · Weather observations · People visited · Documents/receipts.

**The fold:** at any moment (live) and at close, the session's derived truth (`TripRoute`, `TripTotals`, `TripTimeline`) is a **reproducible fold** of its grouped rows. Close → the fold is materialized into the durable projections that feed the Trip Story.

---

## Domain Relationships

Travel is the horizontal domain; here is how it composes each vertical. In every row Travel **links/projects** — it never re-owns.

| Domain | What Travel composes | Direction |
|---|---|---|
| **People** | Participants, people visited, "last saw," relationship-first purpose, "haven't seen Kelly in 3 years" | People owns; Travel tags visit-events + reads recency |
| **Legacy / Places** | Destination anchors, place memories, first-visit, "this is where…" | Legacy owns `Place`; Travel creates `PlaceVisit` and can promote a Trip Story to a Legacy preservation artifact |
| **Health** | Readings/sleep/activity during the window; mobility constraints inform planning | Health owns; Travel tags in-window + reads constraints |
| **Journal** | Trip journal entries, voice notes on the road | Journal owns; Travel scopes entries to the trip |
| **Faith** | Observations/readings while traveling; pilgrimage-type trips | Faith owns; Travel tags in-window |
| **Finance** | Trip budget, expenses, "what this trip cost" | Finance owns; Travel tags expenses + projects totals |
| **Calendar** | Trip dates, legs as events, conflict detection | Calendar owns time; Travel projects legs, reads conflicts (Calendar Projection Law) |
| **Meals** | Restaurants and meals on the trip; food preferences inform planning | Meals owns; Travel tags in-window + reads prefs |
| **Goals / Purpose** | Trips that serve a mission ("see every national park"); Mission Link | Goals owns missions; Travel links a trip to the mission it serves |
| **Capture / Documents** | Reservations, tickets, receipts, boarding passes | Capture/Documents owns artifacts; Travel references them per trip |
| **Tasks / Life** | Prep tasks, packing tasks, vehicle maintenance to-dos | Tasks owns; Travel generates trip-scoped tasks |

---

## UI / UX Concepts

The product is the conversation, so most of the UI is the CoS. The visual surfaces exist to make trip truth **glanceable and trustworthy**, never to become a dashboard (Danny's rule).

**Travel exposes many workspaces, not one page (ratified direction).** Consistent with "One Chief of Staff, many workspaces," Travel is a *family of workspaces* the user moves between; the **one** Chief of Staff stays constant and **Current Context adapts naturally** as the user changes workspace. Each workspace declares its own Current Context (detail object or overview `summary:` provider) so the CoS always knows what the user is working on. Anticipated workspaces:

| Workspace | What the user is doing | Current Context |
|---|---|---|
| **Travel Home** | Surveying travel life (dreams, active, history) | `summary:travel.home` |
| **Active Trip** | Working the trip that's happening/next | `travel.trip:pk` |
| **Trip Planning** | Building a trip's shape and logistics | `travel.trip:pk` (planning) |
| **Route Planner** | Sequencing legs, stops, mileage | `travel.trip:pk` (route) |
| **People** | Who's on the trip / who to visit | links People truth |
| **Packing** | Packing list for a trip | `summary:travel.packing` |
| **Reservations** | Lodging/tickets/documents for a trip | links Documents |
| **Budget** | Trip cost and expenses | links Finance |
| **Live Trip** | On the road, session active | `travel.session:pk` |
| **Trip Story** | Reliving/sharing a completed trip | `travel.trip:pk` (story) |
| **Memories** | Photos/notes/places across trips | `summary:travel.memories` |
| **Map** | Where I've been / where I'm going | `summary:travel.map` |

- **Live Travel Mode (the Live Trip workspace)** — a full-screen, glanceable "on the road" surface: map with breadcrumb trail, current place, today's miles, next fuel/service, weather ahead, and the CoS's contextual notes as a calm feed (not alerts spam). Reuses the Leaflet-over-Esri viewer. **Only exists while a Travel Session is active** (see below).
- **Trip Story** — a timeline + route + people + photos + totals, narrated in the traveler's voice, every element traceable to a fact. Shareable; promotable to Legacy.
- **Visual Truth Contract** applies: only an actually-completed leg/packing-item/trip may *look* completed; planned-but-not-done and behind-schedule use badges/dimming, never completion visuals.

### Workspace ≠ Session (an important distinction that emerged this session)

**A Travel *Workspace* exists forever; a Travel *Session* is active only while the user is actually traveling.** The workspaces above are permanent surfaces the user can open any time (dream a trip in January, relive one in December). A **Travel Session** (defined in its own section) is a *transient capture window* that opens when travel starts and closes on return home — during which the platform collects deterministic truth (GPS breadcrumbs, stops, fuel, hotels, restaurants, photos, voice notes, journal, expenses, weather, health context, people visited, documents, receipts). When the session ends, its captured truth becomes **permanent trip history** that the Trip Story and Memories workspaces render forever. Confusing the two would either make live-capture always-on (wrong: privacy + battery) or make the workspaces disappear when not traveling (wrong: dreaming/planning/reliving are the majority of a trip's life). Keep them separate.

---

## Chief of Staff Behaviors

What the world's best human travel chief of staff would do — expressed as CoS behaviors over deterministic truth.

**Before the trip**
- Turn a wish into a shaped plan through natural conversation; do the research and the triage, present *the* recommendation, not a list.
- Connect the trip to what matters: *"This is your relationship-first travel — you haven't seen Kelly in almost three years and you'll be 20 minutes away. Want to build in a night?"* (People recency + geography + Traveler Profile rule).
- Anticipate readiness: vehicle service due before departure, health/meds for the road, documents assembled, people given a heads-up, packing generated from trip shape + weather + Profile.

**During the trip (live mode)**
- Contextual, warm, deterministic: *"You've arrived at Aunt Janice's — first visit. Enjoy."* / *"4,998 miles in; oil change due within ~200."* / *"Rain around 2 PM near Cody — the pass'll be cold."* / *"You planned two nights here."* / *"Remember to ask Steve about the cabin."*
- Adapt, don't just report: reroute suggestions honor the scenic-road preference; a delay reconciles the plan; a detour is captured, not scolded.
- Capture in the moment: voice notes, photos, and journal all land in the session without breaking the ride.

**After the trip**
- Compose the Trip Story from facts, in the traveler's voice.
- Propose (never impose) what it learned: *"You rode ~320 miles/day comfortably and always chose the scenic route — should I make that your default? You also said you'd never arrive late to family again — want that as a standing rule?"* → confirmed lessons become Traveler Profile truth (T9).
- Make the next trip start smarter — the compounding loop.

**Standing / proactive**
- Extend `TravelActiveRule` into real travel awareness (journal/calendar/health signals already feed it).
- Executive drift: *"You've dreamed three trips this year and taken none — is travel actually a priority, or should we stop surfacing it?"* (Danny's "tell me when I'm fooling myself").

---

## Future Roadmap

Phased, foundations-first. Each phase is a shippable increment of trust; no phase depends on the flashy one.

- **Phase 0 — Domain skeleton.** `Trip` + `TravelerProfile` + lifecycle; `BEHAVIORAL` registration; `TravelDomainTruth` + `TravelQueries` (CoS can answer "what trips do I have," "how do I like to travel"); semantics entry; Current Context. *No GPS.*
- **Phase 1 — Conversational planning.** Planning conversation over the Trip (Journal-draft mechanics generalized); multimodal capture of reservations/routes; Mission Link + People/Calendar composition; write-actions (create/plan trip, add stop, set preference).
- **Phase 2 — Trip execution + manual session.** `TravelSession` grouping *without* GPS: manual/multimodal capture of stops, expenses, journal, photos in-window; Trip Story v1 (composed from grouped truth); Traveler Profile learning loop.
- **Phase 3 — Live GPS mode.** CoreLocation manager + `travel/ingest/` + `TrackPoint` ledger + arrival detection + live surface. The heavy, greenfield phase — deliberately last, gated on real use of Phases 0–2.
- **Phase 4 — Ambient intelligence.** Vehicle range/service math, weather-ahead, proactive relationship/geography nudges, richer Trip Stories, Legacy promotion.
- **Phase 5 — Multi-traveler / household trips.** Shared trips (Space model, when authorization framework lands) — Travel already scoped person-first, so this extends cleanly.

Certification-gated per the Layer 1 framework: no phase is "done" until it passes the domain-certification steps and Danny's production validation.

---

## MVP Recommendation

**Build the truth spine and the conversation first; hold GPS for Phase 3.** (Phases 0–2 above.)

Rationale — this is the Constitution's "improve truth before adding intelligence" and Danny's "simplicity is a feature" applied honestly:

1. **The conversation is the product, not the map.** A CoS that can dream, research, plan, and remember a trip — grounded in real People/Calendar/Finance/Journal truth — is already a product a paying customer would use again tomorrow. That needs *zero* GPS.
2. **GPS is the heaviest, riskiest, most greenfield piece** (new iOS entitlements, background location, App Store review, battery, privacy, a brand-new data shape). Leading with it would stall the whole domain behind device work.
3. **The compounding loop (T2/T9) delivers the vision** — every trip making the next better — and it works entirely on captured/confirmed truth, not tracks.
4. **It de-risks CoS.** A read-only `TravelDomainTruth` provider participates through the existing catalog with *no* changes to the CoS pipeline — Travel becomes answerable the moment the provider registers. Write-actions and live mode are added deliberately, behind flags, without touching the reasoning core. **CoS is not put at risk to ship Travel.**

**Concrete MVP slice:** `Trip` + `TravelerProfile` + lifecycle; `TravelDomainTruth`/`TravelQueries` (+ semantics + Current Context) so the CoS can answer trip and travel-preference questions; the planning conversation that turns *"I'm thinking about riding out west"* into a structured, resumable Trip; a manual/multimodal Travel Session; and a Trip Story v1 composed from that truth. That is a flagship-feeling domain with no device dependency.

---

## Long-Term Vision

A lifetime in WLJ accumulates a **travel autobiography that is also a planning engine**. The Traveler Profile knows how this person moves through the world; the trip history knows every place they've been, everyone they've visited, every mile and dollar and memory. Dreaming a new trip is a conversation with someone who remembers all of it and invents none of it. Live mode makes the road itself feel accompanied. The Trip Story makes every journey a preserved chapter that can outlive the traveler (Legacy). And because it is deterministic truth under a reasoning model — not an AI that "remembers" — it is trustworthy at the scale of a life: **the model reasons, WLJ knows, and Travel Intelligence knows the whole road behind and ahead.**

---

## Appendix A — Constitutional Compliance (no Review required)

| Article | How Travel Intelligence conforms |
|---|---|
| I.1–I.4 (truth/reasoning division) | Travel owns deterministic geospatial/trip truth and calculations (distance, totals, recency, service math); the model interprets and narrates; WLJ never renders a verdict on the experience. |
| I.5 (perception) | Reservations/routes/receipts are perceived by the model through the existing multimodal spine; Travel adds no parser. |
| I.6–I.7 (validate/execute) | Trip writes and Profile updates run the confirmation-gated, audited action path; place coordinates use `set_coordinates` provenance. |
| I.8 (provider-agnostic) | No provider/AI name is a Travel identity. |
| II (Current Context) | Trip = detail object (`travel.trip:pk`); Trips/Profile = overview `summary:` providers from one deterministic source. |
| III.1 (one authority per domain) | Travel **composes, never re-owns**; expenses/people/journal/health/etc. stay with their owners. |
| III.2 (one Execution Decision Authority) | Trip prep tasks flow through the existing Decision Authority; Travel does not add a second "what to do now." |
| III.3 (Mission Link) | A trip's connection to the mission it serves is deterministic link truth. |
| IV (engineering discipline) | Reuses Places/Esri/haversine, the multimodal spine, the mobile-ingest/audit pattern, the Journal-draft lifecycle, and the session pattern — expose/reuse before inventing. |
| V (product governance) | Conversation-first; Visual Truth Contract honored; failures fixed top-down (truth → reasoning → action → experience). |

**The only governance action needed is Danny's product decision to classify Travel `BEHAVIORAL`** (and update the `descriptors.py:26` comment). That is in-Constitution — Article III lets each domain own its truth — so **no Constitutional Review is triggered.**

## Appendix B — Concrete Extension Points (when build begins)

Read-truth (makes Travel CoS-answerable automatically): `apps/travel/services/travel_domain_truth.py` (`@register_domain_truth class TravelDomainTruth(DomainTruth)` with `current_metrics`/`history_metrics`/`entity_types`/`analysis_subjects`); `apps/travel/services/travel_queries.py` (deterministic `CompleteEntity` layer + `describe_one` by-name resolver, mirroring `medicine_queries.py`); add the module to `_KNOWN_PROVIDER_MODULES` in `apps/core/truth/domain.py:25`; add a `travel` entry to `DOMAIN_SEMANTICS` in `apps/core/truth/semantics.py` (**required or the capability test fails**). Current Context: `apps/travel/page_summaries.py` (`@register_page_summary`) imported in `apps/travel/apps.py` `ready()`. Registry: `apps/travel/capabilities.py` (`registry.register(DomainCapability(name="travel", domain_class=DomainClass.BEHAVIORAL, …))`, auto-discovered). Write-actions (Phase 1+): `apps/ai/intents/travel_intents.py` → wire into `apps/ai/intents/__init__.py` (`ALL_INTENT_TOOLS`, `INTENT_HANDLERS`, `DOMAIN_INTENT_TOOLS`) → `execute_intent` branches in `apps/ai/intent_service.py` → `handle_*` methods in `apps/ai/action_handlers.py` → prompt examples → intent-registration gate test. iOS/GPS (Phase 3): new CoreLocation manager + `location` background mode/entitlement/usage strings; `wljBridge` actions; `POST /api/mobile/travel/ingest/` + `TravelIngestionRun` (copy `HealthIngestionRun`).

## Appendix C — Open Questions for Danny

1. **Classification:** confirm `BEHAVIORAL` (recommended) over the reserved `CONTEXT`. Single biggest call.
2. **Vehicle scope:** is `Vehicle` (bike/car + maintenance intervals) part of Travel, or its own small asset domain that Travel references? (Recommend: start inside Travel; extract later if cars/boats/RVs multiply.)
3. **Trip Story ↔ Legacy:** should a completed Trip Story auto-offer promotion to a Legacy preservation artifact? (Recommend: yes, as an explicit user action.)
4. **Live-mode privacy default:** confirm opt-in-per-trip, never always-on. (Strongly recommended.)
5. **First real trip to design against:** the September 2026 motorcycle trip out west is the ideal MVP proving ground — use it as the acceptance scenario.
