# Walking With God Through Scripture — Specification

**Status:** Specification only. No models, no code, no content packs yet.
**User-facing name:** Walking With God Through Scripture
**Internal name:** Journey
**Owner:** Danny Jenkins
**Created:** 2026-05-24
**Last updated:** 2026-05-24

> This document is the single source of truth for the Journey architecture, content schema, editorial workflow, and Beth boundaries. Subsequent commits (models, content packs, views, signals) must conform to this spec. Changes to the spec require revisiting this document before changing code.

---

## 1. Mission and Product Principles

### Mission

Build a guided Bible understanding journey that helps users:

1. Finish the Bible
2. Understand the Bible
3. Stay engaged when Scripture becomes difficult
4. Grow spiritually
5. Apply biblical principles to daily life
6. Avoid overwhelm and discouragement
7. Build long-term biblical literacy

The system targets users who struggle with Old Testament laws, genealogies, confusing passages, older wording, historical confusion, loss of momentum, and feeling overwhelmed. The diagnosed root cause is rarely discipline — it is **"I stopped understanding, so I stopped reading."** This system exists to solve that.

### Desired feel

Warm. Approachable. Wise. Deeply understandable. Faith-centered. Non-intimidating. Encouraging. High trust. Biblically grounded.

The experience should feel like: *"I am walking with God and finally understanding Scripture."*

Not: *"I am completing another reading program."*

### Product principles

| # | Principle | Implication |
|---|---|---|
| 1 | **Understanding > volume** | Reading load may vary by content difficulty. Not every day is equal. |
| 2 | **Consistency > streaks** | No streak gamification on the reading surface. |
| 3 | **Reverence > engagement-gaming** | No celebrations, badges, or animations on the reading surface. |
| 4 | **Deterministic > generative** | All Scripture and explanation content is authored, reviewed, and stored. Nothing generated at request time. |
| 5 | **Scripture first, Beth second** | Beth is silent on the journey surface in Phase 1. Future phases may add invited retrieval, never proactive presence. |
| 6 | **Plain English** | Assume an intelligent, non-specialist reader. No seminary language. |
| 7 | **User-paced** | No day expires. No auto-skip. No "you're behind." |
| 8 | **Non-denominational, Christ-centered** | Teach consensus historic Christian readings; name where mainstream traditions differ; do not advocate for one tradition. |

---

## 2. Isolation-First Architecture

The Journey is architecturally isolated from the existing reading-plan system. This isolation is deliberate and load-bearing. It exists to eliminate regression risk to the five deployed plans (Jonah, Ruth, Noah, Daniel, Ten Commandments) and the existing reading-plan infrastructure (`ReadingPlanTemplate`, `ReadingPlanDay`, `UserReadingPlan`, `UserReadingProgress`, `ReadingPlanAssessment`, loaders, calendar projection, admin).

### Hard boundary rules

- Journey code lives in `apps/faith/journey/`
- Journey code **must not import** `ReadingPlanTemplate`, `ReadingPlanDay`, `UserReadingPlan`, `UserReadingProgress`, `ReadingPlanAssessment`, or any service that operates on them
- Existing reading-plan code **must not import** anything from `apps/faith/journey/`
- The two systems may coexist for any user: one active Journey plus any number of active reading plans, without interaction

### What Journey may safely reuse

| Existing capability | Reuse allowed | Notes |
|---|---|---|
| `BibleHighlight` | Yes (Phase 2 or later) | Reference-keyed, per-user, not coupled to plans |
| `BibleBookmark` | Yes (Phase 2 or later) | Same |
| `BibleStudyNote` | Yes (Phase 2 or later) | Same |
| `SavedVerse` | Yes (Phase 2 or later) | Same |
| `ScriptureVerse` (curated) | Yes (read-only) | Canonical verse text source |
| SAE state-building pattern | Yes | New `build_journey_state()` lives in `apps/faith/journey/state.py` |
| CoS context-building pattern | Yes | New `build_journey_context_block()` lives in `apps/faith/journey/context.py` |
| Signal/observability pattern | Yes (pattern only) | Journey defines its own signals; does not subscribe to plan signals |
| Calendar projection pattern | Yes (pattern only, Phase 2) | Journey defines its own projection handlers; does not subscribe to plan signals |
| Capability registry | Yes (extension) | Add journey signals to existing faith capability |

### What Journey explicitly may not do

- May not add fields to `ReadingPlanTemplate` or `ReadingPlanDay`
- May not alter `UserReadingPlan` or `UserReadingProgress` semantics
- May not change existing plan loaders
- May not change existing reading-plan view or template behavior
- May not migrate existing plan data into Journey models
- May not surface existing topical plans inside the Journey UI (nor vice versa)
- May not reuse existing reading-plan admin (Journey has its own)

### Module structure (proposed)

```
apps/faith/journey/
  __init__.py
  models.py              # Five new models (see §4)
  admin.py               # Journey admin
  views.py               # Journey reading view, dashboard card, settings
  urls.py                # /faith/journey/ namespace
  services.py            # Progression, momentum, content retrieval helpers
  signals.py             # Journey signal definitions and handlers
  state.py               # build_journey_state() — called by faith SAE
  context.py             # build_journey_context_block() — called by CoS
  content/               # JSON content packs (see §5)
    walking_with_god/
      path.json
      arcs/
        arc_01_egypt_to_tabernacle.json
  management/
    commands/
      load_journey_path.py
  tests/
```

### Integration points with existing faith code

Only two additive touch-points in existing `apps/faith/` modules:

1. **SAE faith state builder** — calls `from .journey.state import build_journey_state` and adds the `journey` block to the faith state. Wrapped in try/except per WLJ exception-handling rule so a Journey-side failure does not break faith state.
2. **CoS faith context builder** — calls `from .journey.context import build_journey_context_block` and adds the `journey` block to the faith CoS context. Same exception isolation.

These two integration points are the **only** places existing faith code becomes aware that Journey exists.

---

## 3. Explicit Protection of Existing Bible Plans

The five deployed reading plans (Jonah, Ruth, Noah, Daniel, Ten Commandments) and the reading-plan infrastructure must continue working exactly as they do today.

### Non-negotiable preservations

- No behavioral change to any existing reading-plan view, template, model, or service
- No schema migration affecting any existing reading-plan table
- No data migration of existing plans into Journey models
- No coupling between Journey progression and reading-plan progression
- No reinterpretation of existing reading-plan content as "journey content"
- No new shared dependency that could introduce cross-impact

### Concurrent use guarantee

A user may simultaneously:

- Be on an active Journey (single, ongoing)
- Be on any number of active topical reading plans
- Complete days in either independently
- Have both reflected on the faith dashboard as distinct cards

Neither system causes side effects in the other.

### Enforcement

- Code review: any PR introducing cross-module imports between `apps/faith/journey/` and the rest of `apps/faith/` (other than the two listed integration points) is rejected
- Optional follow-up: CI lint rule preventing such imports (deferred; not blocking MVP)

---

## 4. Proposed Data Model

Five new models. Zero existing models modified.

### `JourneyPath`

The user-facing journey container. Phase 1 ships exactly one instance: *Walking With God Through Scripture*.

| Field | Type | Notes |
|---|---|---|
| `slug` | SlugField, unique | e.g., `walking_with_god` |
| `name` | CharField | Display name |
| `narrative_overview` | TextField | One-paragraph framing |
| `cover_image_url` | URLField, blank | Optional |
| `estimated_weeks` | PositiveIntegerField | Informational only |
| `difficulty_default` | CharField (`gentle` / `standard` / `deep`) | Starting tier when user begins |
| `is_active` | BooleanField, default True | Available to users when True |
| `is_featured` | BooleanField, default False | Promoted on faith dashboard |

Inherits SoftDeleteModel pattern per WLJ convention.

### `JourneyArc`

A narratively coherent span within a path. Phase 1 ships one arc: *Egypt to the Tabernacle*.

| Field | Type | Notes |
|---|---|---|
| `journey_path` | FK → JourneyPath, `related_name='arcs'` | Parent path |
| `slug` | SlugField | Unique within path |
| `name` | CharField | Display name |
| `era_label` | CharField | Short story-position label (e.g., "Exodus") |
| `order` | PositiveIntegerField | Position within path |
| `opening_note` | TextField | Shown when user begins this arc |
| `closing_note` | TextField | Shown when user completes this arc |
| `estimated_days` | PositiveIntegerField | Informational |
| `is_active` | BooleanField, default True | Available to users when True |

Constraints: `unique_together = (journey_path, order)`, `unique_together = (journey_path, slug)`.

### `JourneyDay`

The atomic unit of content. One record per day per arc.

| Field | Type | Notes |
|---|---|---|
| `arc` | FK → JourneyArc, `related_name='days'` | Parent arc |
| `day_number` | PositiveIntegerField | 1-indexed within arc |
| `scripture_refs` | JSONField | List of reference strings: `["Exodus 12:1-13"]` |
| `scripture_content` | JSONField | Pre-embedded WEB translation (see §5 schema) |
| `context_before` | TextField, required | "Context First" step (plain English, before reading) |
| `plain_english_gentle` | TextField, required | Tier 1 commentary |
| `plain_english_standard` | TextField, required | Tier 2 commentary |
| `plain_english_deep` | TextField, required | Tier 3 commentary |
| `key_insight` | CharField (~200), required | One-sentence takeaway |
| `reflection_prompt` | TextField, required | Single personal question |
| `application_action` | CharField (~280), required | One small concrete action |
| `confusion_topics` | JSONField | List of `{topic, plain_english_answer}` objects |
| `retention_anchor` | TextField, blank | Optional connection to story arc |

Constraints: `unique_together = (arc, day_number)`.

### `UserJourney`

A user's instance of a journey path. One active row per user per path (enforced by service layer, not unique constraint, to allow historical rows).

Inherits UserOwnedModel.

| Field | Type | Notes |
|---|---|---|
| `journey_path` | FK → JourneyPath | The path the user is on |
| `current_arc` | FK → JourneyArc, nullable | The currently active arc |
| `current_day_number` | PositiveIntegerField, default 1 | 1-indexed within current arc |
| `status` | CharField (`active` / `paused` / `completed` / `abandoned`) | Lifecycle |
| `preferred_difficulty` | CharField (`gentle` / `standard` / `deep`) | User choice; defaults to path default |
| `reminder_time` | TimeField, nullable | Off by default; user opts in |
| `started_at` | DateTimeField, auto_now_add | When created |
| `last_engaged_at` | DateTimeField, nullable | Set when user reads or interacts |
| `completed_at` | DateTimeField, nullable | Set when path completes |
| `momentum_score` | FloatField, default 1.0 | Internal observability only; never displayed |

### `UserJourneyDayProgress`

Per-day completion record. One row per (user_journey, journey_day).

Inherits UserOwnedModel.

| Field | Type | Notes |
|---|---|---|
| `user_journey` | FK → UserJourney | Parent journey instance |
| `journey_day` | FK → JourneyDay | The day completed |
| `is_completed` | BooleanField, default False | Completion flag |
| `completed_at` | DateTimeField, nullable | When marked complete |
| `reflection_notes` | TextField, blank | User's free-text reflection |
| `application_committed` | BooleanField, default False | User affirmed the application action |
| `difficulty_at_completion` | CharField | Snapshot of tier in use when completed |

Constraints: `unique_together = (user_journey, journey_day)`.

### Progression rules

- Linear, strictly ordered. No branches.
- `current_day_number` advances by 1 when `UserJourneyDayProgress.is_completed` becomes True for the current day.
- When `current_day_number > arc.estimated_days` (or when the highest-numbered day in the arc is complete), `current_arc` advances to the next `JourneyArc` (by `order` within the same path) and `current_day_number` resets to 1.
- When no next arc exists, `status` becomes `completed` and `completed_at` is set.
- The user may navigate freely to any past day (read-only review).
- Future days are not navigable until reached. Rationale: each day's `context_before` assumes yesterday's reading was just read.

---

## 5. Content-Pack JSON Schema

JSON content packs are the source of truth for all Journey content. They are version-controlled in `apps/faith/journey/content/<journey_slug>/` and loaded into the database via the `load_journey_path` management command. The DB serves the app; the JSON serves review, edit, and version-control.

### Folder layout

```
apps/faith/journey/content/walking_with_god/
  path.json
  arcs/
    arc_01_egypt_to_tabernacle.json
    arc_02_<future>.json
```

### `path.json` schema

```json
{
  "slug": "walking_with_god",
  "name": "Walking With God Through Scripture",
  "narrative_overview": "A guided walk through the story of God, from creation to the early church...",
  "cover_image_url": "",
  "estimated_weeks": 52,
  "difficulty_default": "standard",
  "is_active": true,
  "is_featured": true
}
```

### `arcs/<arc_slug>.json` schema

```json
{
  "journey_path": "walking_with_god",
  "slug": "egypt_to_tabernacle",
  "name": "Out of Egypt to the Tabernacle",
  "era_label": "Exodus",
  "order": 1,
  "opening_note": "You are about to walk with Israel out of slavery...",
  "closing_note": "You've walked from Egypt to the foot of Sinai...",
  "estimated_days": 21,
  "is_active": true,
  "days": [
    {
      "day_number": 1,
      "scripture_refs": ["Exodus 1:1-22"],
      "scripture_content": {
        "translation": "WEB",
        "blocks": [
          {
            "ref": "Exodus 1:1",
            "verse": 1,
            "text": "Now these are the names of the sons of Israel...",
            "red_letter": false
          }
        ]
      },
      "context_before": "Four hundred years have passed since Joseph...",
      "plain_english_gentle": "Israel has grown into a large group of people in Egypt...",
      "plain_english_standard": "What started as 70 family members has grown to a nation...",
      "plain_english_deep": "The Hebrew text emphasizes the fulfillment of God's promise to Abraham...",
      "key_insight": "God's promises don't depend on circumstances — they unfold over generations.",
      "reflection_prompt": "Where in your life are you waiting on a promise that feels delayed?",
      "application_action": "Take 5 minutes today to write down one promise of God you're trusting.",
      "confusion_topics": [
        {
          "topic": "Why does Pharaoh suddenly fear the Israelites?",
          "plain_english_answer": "Egypt's rulers had changed..."
        },
        {
          "topic": "What were the midwives doing?",
          "plain_english_answer": "..."
        }
      ],
      "retention_anchor": "You're at the beginning of the Exodus story..."
    }
  ]
}
```

### Schema validation rules

The loader (`load_journey_path`) must validate before upserting:

- All required fields present on every day
- `day_number` values are sequential starting from 1 with no gaps
- `confusion_topics` contains at least 2 entries per day
- All three `plain_english_*` tiers populated
- `scripture_refs` is non-empty
- `scripture_content.translation` is `"WEB"` (Phase 1 only)
- `key_insight` ≤ 200 characters
- `application_action` ≤ 280 characters

Loader is idempotent: re-running upserts; never duplicates.

---

## 6. Editorial Workflow

### Roles

| Role | Responsibility |
|---|---|
| **Drafter** | LLM-assisted first-draft authoring of day content from Scripture + style guidelines |
| **Writing reviewer** | Edits for plain-English standard, voice, conciseness, readability |
| **Theological reviewer** | Verifies biblical accuracy, ensures non-denominational consensus position, removes contested theological claims, signs off |
| **Maintainer (Danny)** | Final approval and merge |

### Workflow

1. **Draft** — Drafter generates a day's full content using a structured prompt with: Scripture passage, target difficulty tier guidelines, voice/style examples, prohibition list. Output conforms to the JSON schema for one day.
2. **Writing review** — Reviewer edits draft for plain English, removes academic terminology, ensures each tier is appropriately differentiated, validates `confusion_topics` are *specific* (not generic).
3. **Theological review** — Reviewer verifies biblical accuracy, checks that no contested theological position is asserted as consensus, flags any tradition-specific claims. Signs off explicitly in PR.
4. **Maintainer merge** — Danny reviews and merges PR. Deploy runs `load_journey_path` automatically. Day becomes live.

### Acceptance criteria for a day

A day is publish-ready when:

- All required fields populated and pass schema validation
- `plain_english_gentle` is genuinely accessible to a non-specialist
- `plain_english_standard` adds depth without academic vocabulary
- `plain_english_deep` adds historical, linguistic, or cross-reference depth
- `key_insight` is one specific takeaway, not generic
- `application_action` is concrete and achievable in under 15 minutes
- `confusion_topics` contains at least 2 *specific* day-relevant confusions, each with a complete plain-English answer
- Theological reviewer has signed off in PR

### Phase 1 ship blocker

**Phase 1 content cannot ship publicly until a named theological reviewer is in place.** This is non-negotiable. Code may be built and tested with draft content internally, but the journey path's `is_active` flag must remain False (or feature-flag-gated) for non-internal users until reviewer is named and content is signed off.

### Editorial framework (theological)

- Teach **consensus historic Christian readings**. Where the major Christian traditions (Catholic, Orthodox, mainline Protestant, evangelical) agree, present the consensus.
- Where they differ on a passage's meaning, **name the differences plainly** without advocating for one tradition.
- Avoid contested theological terms in plain-English tiers. Where a term must appear (e.g., "atonement"), define it in the day's plain English before using it.
- Christ-centered framing is appropriate when a passage is genuinely Christological (e.g., Messianic prophecies, types in the law). Avoid Christological readings where the text does not support them.
- Do not adopt any position on contested modern issues (eschatology systems, predestination vs free will systems, denominational distinctives) unless the passage requires it. If it does, name the spectrum.

---

## 7. Theological Reviewer Guidelines

A reviewer's job is **to protect the user's trust**, not to perfect theology. The bar is: would this content be received as faithful, fair, and trustworthy by a reasonable Christian from any major tradition?

### What the reviewer verifies

- **Biblical accuracy** — Every factual claim about the text is verifiable from the passage or established biblical scholarship.
- **Non-denominational stance** — No content asserts a tradition-specific position as universal.
- **Plain-English faithfulness** — Translation into plain English preserves meaning; does not flatten or distort.
- **Tone** — No guilt language, no comparison to other readers, no "should" framing, no spiritual coaching outside the authored reflection/application.
- **Absence of prohibited Beth behaviors** — Authored content does not contain anything Beth herself would be prohibited from saying (see §9).

### Sign-off mechanism

Each PR introducing a day or set of days requires explicit reviewer comment: *"Theological review complete. Approved for publish. — [Reviewer Name], [Date]."* Merge gated on this.

### Recusal and disagreement

If the reviewer cannot in good conscience approve a day's framing of a contested passage, the day returns to drafter with reviewer comments. If structural disagreement exists between drafter and reviewer (e.g., on whether a particular reading is "consensus"), Danny mediates and may request a second reviewer.

---

## 8. Beth Prohibition List

This list governs both **authored content** and **Beth's spoken/written output** in any future phase where Beth interacts with journey content. It is referenced in §9.

Beth (and authored content) must **never**:

1. Paraphrase, summarize, or quote Scripture from internal model knowledge — only from authored or canonical sources
2. Make theological claims not present in retrieved authored content
3. Tell the user what God thinks of them or their behavior
4. Use "should" language about spiritual practice
5. Compare the user to other users ("most people," "users like you," "people who succeed at this")
6. Reframe questions of doubt with "trust more" or similar dismissive language
7. Use guilt phrasing: "you're behind," "you missed," "you haven't read in X days," "you should be on day Y"
8. Proactively reference the journey unless the user invoked Beth from a journey page
9. Add new theological framing when conversationally re-presenting authored content
10. Suggest spiritual practices, disciplines, or commitments beyond the day's authored `application_action`
11. Take a position on contested theological systems (eschatology, predestination/free will, denominational distinctives)
12. Promise spiritual outcomes ("if you do this, God will...")
13. Substitute for a pastor, counselor, or human spiritual director in matters of personal crisis

This list must live in code as a constant (e.g., `JOURNEY_BETH_PROHIBITIONS`) and be embedded verbatim in any system prompt for Beth interactions involving journey context, when such interactions are added in a future phase.

---

## 9. Beth Phase 1 Boundary

**Phase 1: Beth is silent on the journey surface.**

- No "Ask the assistant" prompts appear on journey reading pages
- No Beth icon, name, or chat affordance is rendered on the journey surface
- Beth has **no tool** that retrieves journey day content in Phase 1
- Beth's CoS context **does** include the journey state (passive awareness), so if the user invokes Beth from elsewhere and asks "where am I in my journey," she can answer factually from state. She cannot retrieve or paraphrase day content.

### Why

This posture removes the operational fragility of "Beth-aware-but-silent." There is no way for Beth to accidentally surface on the journey because no surface is provided. We validate the deterministic spine first.

### Phase 2 retrieval boundary (forward reference, not part of Phase 1)

When a future phase adds Beth retrieval, the boundary is:

- One tool only: `get_journey_day_content(arc_slug, day_number, field=None)`
- Beth's system prompt includes the prohibition list (§8) verbatim
- Every Beth response involving journey content cites the `source_id` (arc_slug + day_number + field) of retrieved content
- Beth never generates Scripture explanation from her own knowledge — only retrieves
- If retrieval returns nothing matching the user's question, Beth says so plainly

---

## 10. MVP Scope

### Phase 1 ships

1. **Five new models + migrations** (`JourneyPath`, `JourneyArc`, `JourneyDay`, `UserJourney`, `UserJourneyDayProgress`) in `apps/faith/journey/models.py`
2. **One fully authored journey path**: *Walking With God Through Scripture*
3. **One fully authored arc**: *Out of Egypt to the Tabernacle* — Exodus 1 through Leviticus 10, approximately 21 days. Authored, writing-reviewed, theologically-reviewed, signed off. Cannot publish publicly until reviewer is named (§6).
4. **WEB translation pre-embedded** in each day's `scripture_content`
5. **Daily reading view** at `/faith/journey/today/` — single scroll-column UX with: location header, context_before, scripture, plain_english (user's tier), key_insight, reflection, application_action, done state
6. **"I'm stuck" deterministic surface** — chips from each day's `confusion_topics`, inline answers from authored content
7. **Dashboard card** on the faith dashboard showing active journey, current arc + day, "continue reading" CTA
8. **Journey settings page** — difficulty tier, optional reminder time (off by default)
9. **Five engagement signals** (`journey_started`, `journey_day_completed`, `journey_arc_completed`, `journey_application_committed`, `journey_confusion_flagged`) firing to PIE for internal observability
10. **SAE journey state block** (`build_journey_state`) and **CoS journey context block** (`build_journey_context_block`) — Beth is passively aware
11. **"Welcome back" recovery flow** for users returning after 3+ day gap — two equal-weight options (continue / recap past week), never "you're behind"
12. **Admin** for `JourneyPath`, `JourneyArc`, `JourneyDay` (separate from existing reading-plan admin)
13. **Management command** `load_journey_path <slug>` — idempotent loader
14. **End-to-end test path** — start journey → complete 3 days → reach arc end → see completion screen
15. **Spec doc** (this document)

### Phase 1 exclusions

The following are explicitly out of scope for Phase 1:

- Beth invocation on the journey surface (any chat affordance, icon, link)
- Beth `get_journey_day_content` tool
- More than one arc (only "Egypt to the Tabernacle" ships)
- Calendar projection of journey days
- ESV / NIV / NLT translations
- Audio narration
- Per-day "thread to yesterday/tomorrow" connection text (handled at arc level via opening/closing notes)
- Difficulty tier auto-suggestion
- Mobile-specific UI tuning beyond responsive defaults
- Social sharing
- Branching paths or conditional days
- Push notifications (opt-in or otherwise)
- Highlight / bookmark / note integration inside journey reading
- Streak visibility on the journey surface
- Any proactive Beth behavior involving the journey

### Phase 2 candidates (priority order, not commitments)

1. Second arc authored ("Wilderness Years" — Numbers + Deuteronomy excerpts) + arc transition flow
2. Beth `get_journey_day_content` retrieval tool + prohibition-list-enforced system prompt for journey-context conversations
3. Highlight / bookmark / note reuse within journey reading (via existing `BibleHighlight` / `BibleBookmark` / `BibleStudyNote`)
4. Calendar projection of journey days (with clear labeling to distinguish from topical plan projections)
5. ESV / NIV / NLT translation switching with API fetching and caching
6. Difficulty tier prompt after each arc completes ("Try a deeper version of the next arc?")
7. Mobile-tuned reading surface (long-press behavior, iPhone SE width validation)
8. Audio narration of reading + plain-English layers
9. Subsequent arcs (continuing the chronological journey)

---

## 11. Risks and Trust Safeguards

### Tier 1 — would seriously hurt mission or trust

| Risk | Safeguard |
|---|---|
| **Theological reviewer not named** | Phase 1 content cannot publish publicly until reviewer is named. `JourneyPath.is_active` False or feature-flag-gated until then. |
| **AI-Bible perception risk** | Scripture text and authored explanation rendered with visually distinct treatment (different fonts, colors, "WEB Translation" attribution beneath Scripture blocks). |
| **Beth crossing silence boundary in future phases** | Prohibition list (§8) lives as a code constant. Future phase tests assert it appears verbatim in Beth's journey-context system prompts. |
| **Editorial volume bottleneck** | Architecture only ships one arc in Phase 1. Sustainable pipeline must exist before scaling. |
| **Contested theology surfacing as consensus** | Theological reviewer sign-off gates every PR. Editorial framework (§6) is explicit. |

### Tier 2 — would degrade experience or accumulate technical risk

| Risk | Safeguard |
|---|---|
| **Isolation discipline erosion over time** | Code review rejects cross-module imports. Optional CI lint rule deferred but recommended. |
| **Streak/gamification creep** | Reverence rationale documented in this spec; visible to anyone proposing such features. |
| **Confusion topics quality drift** | Acceptance criteria require ≥2 *specific* topics per day. Writing reviewer enforces. |
| **Difficulty tier becoming permanent label** | Opt-in difficulty prompt after each arc (Phase 2 candidate). |
| **Generic content failing the "Leviticus test"** | MVP arc deliberately includes Leviticus 1–10. If authored content cannot make this material feel meaningful, the format itself is invalidated and revised. |

### Tier 3 — known but tolerable

| Risk | Note |
|---|---|
| WEB translation lock-in for MVP | Acceptable; public domain removes licensing risk during validation |
| iOS rendering of long reading surfaces | Verify at 375px width during view implementation |
| Internationalization | All content English; future expansion = re-authoring, not translation |
| Calendar projection deferred | Journey card on faith dashboard suffices for MVP |

---

## 12. Testing Strategy

### Scoped per WLJ testing policy

Tests live in `apps/faith/journey/tests/`. The full test suite is **not** run for journey changes. Only journey tests and any directly impacted faith integration tests run.

### Test categories

| Category | Coverage |
|---|---|
| **Model tests** | Model validation, constraints, progression methods (`mark_day_complete`, `advance_to_next_arc`), state transitions, momentum_score decay/recovery |
| **Loader tests** | `load_journey_path` is idempotent; schema validation catches malformed packs (missing fields, gap in day_number, <2 confusion topics, oversized fields, wrong translation) |
| **View tests** | Daily reading view renders all seven content elements; tier-appropriate plain_english served based on `preferred_difficulty`; "I'm stuck" surface renders confusion_topics; welcome-back flow triggers after 3+ day gap; future days are not navigable |
| **Service tests** | Progression advances day → arc → completion correctly; reflection notes and application_committed persist; difficulty tier change does not affect past day records |
| **Signal tests** | All five signals fire on the correct triggers; no `journey_momentum_at_risk` PGE nudge exists |
| **State/context tests** | `build_journey_state` returns expected shape; `build_journey_context_block` populates correctly; both wrapped in try/except so failure does not break faith state |
| **Isolation tests** | Assert that no Journey module imports from existing reading-plan modules, and vice versa (excepting the two listed faith integration points) |
| **Beth boundary tests (Phase 1)** | Assert that Beth has no `get_journey_day_content` tool registered; no journey chat affordance renders on journey pages; assertion test that the prohibition-list constant exists for future-phase use |

### End-to-end smoke test

A single integration test exercises the full happy path:

1. Create test user with TermsAcceptance + completed onboarding
2. Start the Walking With God journey
3. Read and complete days 1, 2, 3
4. Tap a confusion topic, verify authored answer renders
5. Submit a reflection note
6. Affirm an application action
7. Verify dashboard card shows "Day 3 of 21"
8. Advance days programmatically to last day of arc
9. Mark complete; verify arc closing screen, `UserJourney.status` updates appropriately

### Performance and observability

Per WLJ rules: nothing on the journey request path computes heavy analytics. `build_journey_state` reads `UserJourney` and counts `UserJourneyDayProgress` records — both cheap point queries. No background workers required for MVP.

### Migration check

After model commits, run `python3 manage.py makemigrations --check --dry-run` per WLJ migration policy. Journey models must have generated migrations before commit.

---

## 13. Commit Sequence After Spec

This document is **Commit 1**. The sequence after:

| Commit | Scope | Notes |
|---|---|---|
| **2** | First authored day in JSON (`arc_01_egypt_to_tabernacle.json` with day 1 only) | Reality-check the schema before models exist. No code. |
| **3** | Five models + migrations + admin + `load_journey_path` command + content pack loaded | Foundational data layer. Includes isolation test. |
| **4** | Daily reading view + templates + "I'm stuck" surface + dashboard card + journey settings page | Core UX. WEB translation only. |
| **5** | Five signals + state/context integration + Beth boundary tests | Observability + Beth silence enforcement. |
| **6** | Authoring of remaining ~20 days of Egypt → Tabernacle arc | Spread across multiple PRs as authored. Each PR theologically-reviewed before merge. |
| **7** (gate) | Public launch — flip `JourneyPath.is_active` once theological reviewer is named and full arc signed off | Not a code commit; an editorial milestone. |

Each commit follows WLJ Task Completion rules: changelog entry, scoped tests, migration check (where applicable), commit and push to main.

---

## Appendix A — Decisions Locked at Commit 1

| # | Decision | Choice |
|---|---|---|
| 1 | MVP arc scope | Egypt → Tabernacle (Exodus 1 – Leviticus 10, ~21 days) |
| 2 | Authoring workflow | LLM-drafted + theological reviewer sign-off |
| 3 | Theological reviewer | Not named; required before public launch |
| 4 | Translation for MVP | WEB only |
| 5 | Beth in Phase 1 | Silent on journey surface; no tool |
| 6 | Reminder default | Off; user opts in |
| 7 | Nav placement | Faith → Journey |
| 8 | Calendar projection in MVP | No; deferred to Phase 2 |
| 9 | Difficulty prompt cadence | After each arc completes |
| 10 | Streak visibility on journey surface | None |

---

## Appendix B — Open Questions for Future Phases

These are not blocking Phase 1 but should be settled before Phase 2 begins:

- Theological reviewer name(s) and editorial agreement framework
- Whether to add CI lint rule preventing cross-module imports between journey and existing reading-plan code
- Whether to permit Beth retrieval (Phase 2 candidate) before or after second arc authoring
- Translation licensing path for ESV / NIV / NLT
- Mobile reading UX choices (long-press behavior, highlight invocation)
- Dashboard treatment when user has both an active journey and active topical plans (visual hierarchy)
- Whether arc completion deserves any user-facing celebration (current default: muted closing screen only)
