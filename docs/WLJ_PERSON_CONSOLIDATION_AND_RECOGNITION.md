# WLJ Person Consolidation & Universal People Recognition — Canonical Design

**Status:** ✅ APPROVED — Phase 0b (foundation) IMPLEMENTED & VERIFIED; awaiting Danny's product validation. Consumer migration (0c+) not started.
**Author:** Claude (Chief Architect)
**Date:** 2026-07-16
**Absorbs:** the scattered alias stores (`legacy.RelationshipAlias`, `legacy.Person.also_known_as`, `relationships.MentionParserService` name-matching) into ONE Recognition Phrase authority.

> Reviewable artifact required before any migration. Captures the rounds of direction: (1) universal non-blocking
> people-mention recognition in the shared editor; (2) canonical Person consolidation; (3) a hybrid
> deterministic-inline + flagged-AI pipeline; (4) a self-learning Recognition Phrase system; (5) — Person is a
> foundational Layer-1 Core truth domain, NOT a Relationships concept, owned by no optional module;
> **(6) — no `person_kind` catch-all: model visibility/status as independent truths resolved by deterministic UI
> rules; migrate capabilities, not tables; design Person for the next five years as extensions.** Governing:
> Constitution Articles I (Truth/Reasoning), III (Single Authority), IV (Discipline);
> `docs/LAYER1_DOMAIN_FRAMEWORK.md` (Person is developed as a certified L1 domain).

---

## 0. The one-sentence goal

**One always-on Core Person authority every module consumes, one Recognition Phrase system, one shared-editor mention capability — recognition learns and improves through normal use, identity stays deterministic and owned by WLJ, the model only perceives.**

---

## 1. Constitutional posture & Layer-1 framing — NOT a Constitutional Review

Three competing `Person` stores owned by optional modules is *tension with* **Article III.1** ("one deterministic authority per truth domain") and **I.1** ("WLJ owns deterministic truth"). Establishing one always-on Core authority moves the codebase **into** compliance — it strengthens the Articles, so no ⚠️ review gate is triggered.

**Person becomes a Layer-1 truth domain** (peer of Medication, Current Context, Execution, Mission Link), built per `docs/LAYER1_DOMAIN_FRAMEWORK.md` with its certification gates. People are not optional; identity must never disappear or relocate because a feature flag is off.

The hybrid recognition pipeline respects **I.2 / I.5**: the model *perceives and proposes*; WLJ *validates and owns* identity. AI never writes durable identity or a durable Recognition Phrase — enforced as a code-level authority chain (§4.3), not a convention.

---

## 2. Current state — the three Person models (all owned by optional modules — the problem)

| | **A · `relationships.Person`** | **B · `legacy.Person`** | **C · `ai_relationships.Person`** |
|---|---|---|---|
| Owner module | Relationships (**optional**) | Legacy (**optional**) | ai_relationships (**optional**) |
| Role | Visible **People** nav; contacts | Family-tree / preservation graph | AI drift signals (extraction-only) |
| Base | `RichTextMixin, SoftDeleteModel` (`owner` FK) | `RichTextMixin, LegacyOwnedModel` (`user` FK) | plain `Model` (`is_active` — **no soft-delete**) |
| Identity | first/last/display, email, phone, `relationship_type`, notes | display, `also_known_as`, sex, birth/death, bio, portrait, `is_self`, GEDCOM xref, significance | display, `person_type`, notes, `is_active` |
| Relationship model | none (flat enum) | **`Relationship`** (typed edges + category classifier) | `Relationship` (`importance_tier`, cadence) |
| Aliases | none | **`RelationshipAlias`** + `also_known_as` | none |
| Self-anchor | none | **`LegacyProfile.self_person`** + `is_self` | none |
| Interaction spine | **`Mention`** (GenericFK) + **`RelationshipInteraction`** | `Memory`/`MemoryPerson`, `Contributor` | `InteractionSignal` |
| CRUD | full | full + GEDCOM + **`person_merge`** | admin + extraction only |
| Migrations / tests | 5 / 5 | 37 / 24 | 1 / 1 |

**The problem in one line:** a user who never enables Relationships or Legacy still *has* a spouse, children, doctors, coworkers, journal mentions — those are **Person** facts, currently trapped inside optional modules.

**Five reconciliation hotspots (same human in ≥2 tables):**
1. **The user themselves** — self-anchor in B, a contact in A, a `known_people` row in C. No linkage.
2. **`life.SignificantEvent.person` → C** — the **only** cross-app FK into any of the three (`SET_NULL`, `person_name` fallback). `apps/life/models.py:1867`.
3. **A↔C `display_name` string-join** — `relationships/services.py:99-107` (the only runtime "join," and it's by name string).
4. **A-primary / C-fallback drift** — `state_builder.build_relationships_state` reads A then C for the *same* SAE domain (`:5153`).
5. **Three ingestion paths, one human** — @mentions→A, extraction→C, GEDCOM/memories→B, keyed only by `display_name`.

---

## 3. Target architecture — one Core Person authority (Layer-1)

> **Architectural correction (2026-07-16):** the end state is **NOT** "relationships.Person becomes canonical." It is: **one Core Person authority; every feature consumes it; optional modules extend it; no feature module owns it.**

### 3.1 Canonical home

Create **`apps/people`** — a new, **always-installed (never feature-flagged)** Layer-1 domain. Person joins the certified L1 domains per `docs/LAYER1_DOMAIN_FRAMEWORK.md`. The single answer to "where do I get a Person?": `from apps.people.models import Person`.

> Alternative home: `apps/core.models`. Rejected as primary — `apps/core` is already very large and mixes many concerns; a dedicated always-on `apps/people` gives the one obvious import and clean L1 certification. Both satisfy "always available"; **flag if you prefer it inside `core`.**

### 3.2 Ownership split (per your spec)

**`apps/people` (Core Person) OWNS:** canonical identity (names, `person_kind` lifecycle, self-anchor `is_self`); basic contact info (email, phone); photos (`PersonPhoto`); **RecognitionPhrase** (§4); identity + **mention resolution** service (the one resolver); merge / duplicate resolution; canonical Person **APIs** + lookup services.

**Core Person does NOT own** (stay in feature modules, all FK → `people.Person`): marriages, parent/child, genealogy, interaction history, relationship strength, family-tree visualization.

| Module (optional) | Owns — references `people.Person` |
|---|---|
| **Relationships** | `Relationship` (Person A↔B, type, status, dates, **strength**), `RelationshipInteraction`, **interaction intelligence / drift** (absorbs today's C), `PersonGroup` |
| **Legacy** | Genealogy extension: GEDCOM ids, source citations, historical metadata, **family-tree graph** (`Relationship` edges), import provenance, **Memories**, **PreservedFacts**, ancestral relationships |
| **Journal / Faith / Tasks / Meals** | mentions (via the Core mention store + Core resolver) |
| **Health / Calendar / Purpose / Finance / CoS** | future FK consumers (Doctor, Attendee, Mentor, Advisor, Person Context) |

### 3.3 All three existing Person tables RETIRE as identity authorities

None of A/B/C survives as an identity owner (the key change from the prior draft, which had elevated A):

- **`relationships.Person` (A)** → identity migrates to Core Person. Relationships keeps only relationship concepts (`Relationship`, `RelationshipInteraction`, `PersonGroup.members`), all FK → Core Person.
- **`legacy.Person` (B)** → identity migrates to Core Person. Genealogy-specific attributes move to a **`LegacyPersonProfile`** extension (FK → Core Person) holding GEDCOM / historical / source metadata; family-tree `Relationship` edges, `Memory`/`MemoryPerson`, `PreservedFact`, `Contributor`, `Output.scope_person` all re-point to Core Person. Legacy's self-anchor becomes Core Person `is_self`.
- **`ai_relationships.Person` (C)** → fully dissolved; its `Relationship` (importance/cadence) + `InteractionSignal` + drift move into the **Relationships** module as interaction intelligence, referencing Core Person. This *removes* hotspots #3 and #4 by construction.

### 3.4 Dependency direction (must never reverse — enforced)

```
                 apps/people  (Core Person — foundational, ALWAYS ON)
                   ▲    ▲    ▲    ▲    ▲    ▲    ▲    ▲    ▲
   Relationships  Legacy  Journal  Health  Goals  Calendar  Finance  Purpose  CoS
        (all optional — all consumers; none owns identity, none imports another's Person)
```
Core Person imports **no** feature module. Disabling any feature flag must not remove or relocate identity. Enforce with an architecture/import contract test (mirrors the spirit of `test_request_path_safety_contract`): fail CI if `apps/people` imports a feature app, or if any feature module defines its own Person identity table.

### 3.5 Capability-preservation matrix (nothing lost — "one *stronger* Person")

| Capability | Today | After |
|---|---|---|
| Canonical identity, contact info, photos | split A/B/C | **people.Person** |
| Aliases / nicknames | B (`RelationshipAlias`, `also_known_as`) | **people.RecognitionPhrase** |
| Self-anchor ("who is the user") | B (`LegacyProfile.self_person`) | **people.Person.is_self** + accessor |
| Identity / mention resolution | A (`MentionParserService`), scattered | **people** resolution service (one) |
| Merge / dedup | B (`person_merge`, legacy-only) | **people** merge (extended, PreservedFact-safe) |
| Visible People CRUD, groups | A | Relationships/People UI over Core Person |
| Typed relationship graph, strength, drift, interaction history | A + C (split) | **Relationships** module (unified), FK → Core Person |
| GEDCOM, memories, preserved facts, family tree | B | **Legacy** module extension, FK → Core Person |
| SAE relationship state, proactive check-ins, `known_people` | A primary / C fallback | Core Person + Relationships (no A/C drift) |

### 3.6 Canonical Person shape (`apps/people.Person`) — independent truths, NO catch-all field

`SoftDeleteModel`-based; `owner`/`user` FK; `first_name`, `last_name`, `display_name`, `email`, `phone`, `is_self`, photo(s) (`PersonPhoto`), RecognitionPhrase relation.

**Model visibility/status as independent truths — NOT one `person_kind` classification.** A person can be deceased *and* GEDCOM-imported *and* a People-page member *and* still referenced historically — all at once. Independent truths, modeled independently:
- `is_deceased` (bool) — independent of everything else. **Death never revokes People membership** (Grandma is still part of your life).
- `origin` / provenance — how they entered (`manual` · `contact_import` · `gedcom` · `extraction` · `mention` · `promotion`); for audit + reprocessing.
- **genealogy participation is derived** — true iff a `LegacyPersonProfile` / family-graph edge exists; never a stored flag on Person.
- **People membership** — a first-class deterministic truth (§3.6.1), not a filter over "everyone."
- ("active contact," relationship strength, drift = relationship *intelligence*, owned by the Relationships module — not a Core visibility field.)

### 3.6.1 People Membership (the deterministic People-vs-Legacy boundary)

The People page and Legacy have **different purposes** and must not be one filtered view of every Person. **People = the current-life relationship view; Legacy = the complete genealogy/history view.** The same canonical Person may appear in **both**, **only People**, or **only Legacy** — all valid states; only the surface differs, the canonical record is identical.

A person is a **People member** when they become part of the user's life — granted deterministically by any life-path and stored as WLJ-owned truth (auditable, event-driven, never AI-decided):
manually created · imported as a contact · a resolved mention in a journal/entry · referenced or interacted-with by the user · added by another WLJ feature · **explicitly promoted from Legacy**.

Membership is **granted, never auto-revoked**: a deceased member stays (Grandma). A person who exists **only** via GEDCOM import and has never been referenced outside genealogy is **not** a member — they remain in Legacy without cluttering People, until explicitly promoted. Modeled as a `PersonMembership` record (grant + provenance); GEDCOM import alone never sets it. Examples that *are* members: Heather, Haley, Doctor Smith, Pastor Mike, the financial advisor, a coworker, a friend, mother, grandfather. Example that is *not* (yet): a 6th-generation GEDCOM ancestor never referenced outside the tree.

**Does not** carry `relationship_type`, marriages, genealogy, or interaction counts — those live in consuming modules.

### 3.7 Design for the future — extensions, not another redesign

Person is designed so the next five years arrive as **extensions that FK → Core Person**, never as a reason to re-open the identity schema: face recognition, voice identification, household collaboration, shared journals, emergency contacts, care teams, doctors, business contacts, mentors, advisors, interaction analytics, relationship intelligence, CoS memory, future entity recognition. Core Person stays small and stable; capability accretes around it.

---

## 4. The Recognition Phrase system (owned by Core Person)

A **RecognitionPhrase** maps a normalized phrase → canonical Person, user-scoped, with a `source`. Replaces every alias store.

### 4.1 Three sources
1. **Derived (computed, read-only, never stored durably).** At resolve-time from deterministic truth: first name, full name, `@handle`, and **unique** relationship roles ("wife" when exactly one spouse; "daughter" when exactly one daughter — read from the Relationships module). Auto-updates when relationships change; zero maintenance.
2. **Custom (durable rows).** User-typed on the Person page — "Honey", "Sweetie", "Babe", "Hot Momma".
3. **Learned (durable rows).** Created **only** at the confirmation moment during Save/Review ("Always recognize this phrase"). Never by AI, never by implicit acceptance.

### 4.2 Resolution order (deterministic, inline, no LLM)
`exact canonical name` → `unique first name` → `@handle` → `derived role (if unique)` → `custom phrase` → `learned phrase`. Exactly-one match auto-links. **>1** active match → **ambiguous** → review candidate (self-healing collision rule: two people taught "Honey" ⇒ it stops auto-resolving and re-asks).

### 4.3 Authority chain (enforced, not conventional)
```
AI proposes → WLJ validates against deterministic truth → user confirms → WLJ stores
```
Durable RecognitionPhrase rows are written **only** by (a) explicit user confirmation or (b) derivation from truth. No code path lets an AI response write a durable phrase. The background enrichment task (§5) produces *proposals* only.

### 4.4 Re-ask triggers
Another active person gains the same name; another shares the phrase; a role stops being unique (2nd daughter); the relationship changes; the person is merged/deactivated/deleted; the user edits/removes the phrase. All deterministic consequences of §4.2 — no separate detector.

### 4.5 Person page
Exposes all three tiers transparently: **Derived** (read-only), **Custom** (editable), **Learned** (editable/removable), "+ Add Recognition Phrase." Derived is read-only *because* it is deterministic truth.

---

## 5. Hybrid save pipeline (deterministic inline + flagged AI enrichment)

```
User presses Save
      │  (inline, fast, NO LLM — cannot block or fail the save)
      ▼
Deterministic Recognition → Deterministic Resolution (names, unique roles, confirmed phrases)
      │
      ▼
Save entry immediately  ──►  "saved" the instant the deterministic write completes
      │  (safe_enqueue — fire-and-forget, additive only, never overwrites the entry)
      ▼
Background Enrichment [FEATURE-FLAGGED; may ship disabled]
      → Model Perception → Candidate Proposals ("my better half", "the girls", "he/she", "my boss")
      → WLJ Deterministic Validation (accept only when identity is deterministically unique)
      → Auto-resolve  OR  route to Optional Review
```
**Guarantees:** save never depends on LLM/network/Redis; enrichment is additive and writes only *mention/candidate* rows (never `body`/`body_plain`, so "never overwrite a newer version" holds by construction — idempotency-gated, re-read-by-pk, mirrors `extract_journal_signals`); the AI task runs in a Celery worker (no inline LLM) and must pass `test_request_path_safety_contract`; enabling AI later is a **flag flip, not a redesign**.

**Fix in passing (real bug):** `journal/signals.py` & `relationships/signals.py` feed sanitized **HTML** to the extractors instead of the `*_plain` shadow. Recognition reads `body_plain`.

---

## 6. Live @mentions restored in the shared editor

- Add `@tiptap/extension-mention` + `@tiptap/suggestion` to `frontend/tiptap/`, rebuild `tiptap.bundle.js` (run `collectstatic` locally per the vendored-assets rule).
- Keyboard-first: `@` opens suggestions; arrows navigate; **Tab** completes the unique match; Enter accepts while open; Esc dismisses; mouse optional. Normalized `@Heather` / `@Heather Jenkins` / `@HeatherJenkins`.
- The mention **node stores the canonical `people.Person` ID** (not just text). Add its markup to the `nh3` allow-list (`rich_text.py`), sanitizing `data-person-id` to an integer.
- **Retire the orphaned path:** `_global_mention_autocomplete.html` (bound to `<textarea>`, dead on RTE fields) is replaced by the in-editor extension; the generic mention store becomes real, read structured data.
- Structured mention retains: canonical Person ID, visible text, `source_type` (`explicit_at_mention`|`exact_name`|`relationship_role`|`confirmed_alias`|`reviewed_resolution`), timestamp/version, provenance. Plain-text shadow preserved for CoS/search/export/narration — the CoS never parses editor HTML.

---

## 7. Optional batch review + the teaching moment

- Normal **Save** == **Save Now** (non-blocking). Post-save: *"Saved — 16 people linked. 3 references need review."* with `Review` · `Dismiss`.
- **Save & Review** / post-save **Review** opens ONE batch panel (never sequential). Each candidate: assign / leave plain text / ignore / assign-and-learn.
- **Teaching moment:** "☑ Always recognize \"daughter\" as Haley Jenkins" — default ON only when the resolution is *safe* (single deterministic target). Confirming writes a **Learned** RecognitionPhrase (§4.3). The user never edits the Person record manually.

---

## 8. Consumer-migration map (from the exhaustive inventory)

**Migrate capabilities, not tables.** Each capability below was inventoried for *what it does, who consumes it, whether it survives, and where it belongs* — the matrix in §3.5 is that ledger, and Phase 0b opens with the full capability-migration matrix. Repoint target is now **`people.Person`** (not A). Every consumer keeps working identically. Temporary migration bridges are acceptable; permanent bridges are not. Order: build Core Person + migrate identity rows, then repoint module-by-module (extension before redirect).

**Core Person creation & identity reconciliation**
- Create `people.Person` (+ `RecognitionPhrase`, `PersonPhoto`, resolution service, merge). Data-migrate identity rows from A, B, C, deduped by identity (name + birth/self anchor), **never blindly by `display_name`**; preservation-safe (nothing discarded).

**Relationships (A) → consumer**
- `Mention.person`, `RelationshipInteraction.person`, `PersonGroup.members` → `people.Person`.
- `MentionParserService` resolution → Core Person resolution service.
- `relationships/*` views/forms/templates/admin/services, `mobile/views.py:3276` contact import, `dashboard/views.py:137`, `ai_eae/signal_aggregation.py:910` → identity from Core Person, relationship data from Relationships.

**ai_relationships (C) → Relationships interaction intelligence, FK → Core Person**
- `life.SignificantEvent.person` (`life/models.py:1867`) → Core Person; keep `person_name` fallback.
- `state_builder.build_relationships_state` (`:5153,5196`) → Core Person + Relationships; delete C fallback.
- `ai/views.py:2205` `known_people`, `rules_cross_domain.py:387`, `signal_collector.py:411`, `scheduler_runner.py:477`, `proactive_checkins.py:2252`, `reflection_engine.py:394`, `journal/signals.py` → Core Person + Relationships.
- **Delete** the A→C `display_name` write (`relationships/services.py:99-107`).

**Legacy (B) → genealogy extension, FK → Core Person**
- `Relationship.from_person`/`to_person`, `Memory.attributed_to`, `MemoryPerson.person`, `MemoryDiscovery.linked_person`, `Contributor.person`, `Output.scope_person`, `PreservedFact.person`, `RelationshipAlias.person`, `LegacyProfile.self_person` → `people.Person`.
- New **`LegacyPersonProfile`** (FK → Core Person) holds birth/death, sex, GEDCOM xref, `source_batch`, significance, bio. Legacy views/services/templates read genealogy via the extension, identity via Core Person.
- `RelationshipAlias` + `also_known_as` retired into `people.RecognitionPhrase`.

**Current Context gap:** ship `@register_page_summary` providers for People / Relationship Insights / Legacy overviews in the same change (all three are Current-Context blind today).

---

## 9. Reconciliation & merge (preservation-safe)

- **Build the platform merge in Core Person**, re-pointing every consumer relation: A (`Mention`, `RelationshipInteraction`, `PersonGroup.members`), C-origin (drift/importance/`SignificantEvent`), B (all legacy relations + `LegacyPersonProfile`), and RecognitionPhrases. (Extends the logic of `legacy.person_merge`, which today handles only B.)
- **Fix the `PreservedFact` CASCADE bug first:** `legacy.person_merge` hard-`delete()`s the loser while `PreservedFact.person` is `CASCADE` and **not** re-pointed → preserved facts silently destroyed (violates "nothing is ever lost"). Re-point `PreservedFact`, `source_batch`, `gedcom_xref` before delete; prefer soft-delete of the loser.
- Dedupe by canonical identity (name + birth/self anchor), never blindly by `display_name`. Uncertain matches → review, never auto-merged.

---

## 10. Phasing & sequencing (with gates)

| Phase | Deliverable | Gate to proceed |
|---|---|---|
| **0a** | *(this doc)* + approval | **Danny approves Core Person strategy** |
| **0b** | Capability-migration matrix (capability→consumer→survives?→home); create `apps/people` L1 domain: `Person` (independent status truths, **no `person_kind`**), `RecognitionPhrase`, `PersonPhoto`, resolution service, merge (PreservedFact-safe); architecture/import contract test | matrix reviewed; migrations green; L1 gates + contract test pass |
| **0c** | Migrate identity rows (A+B+C → Core Person), deduped, preservation-safe | reconciliation runtime-verified; zero identity loss |
| **0d** | Repoint Relationships (A) + dissolve C into Relationships interaction intelligence; remove A→C join; SAE reads Core Person | People / relationship / drift / SAE / proactive verified identical; **C zero readers** |
| **0e** | Legacy (B) → `LegacyPersonProfile` extension; repoint all B relations to Core Person; fix PreservedFact CASCADE | Legacy tree / import / merge / memories / places verified identical |
| **0f** | Retire A, B, C identity tables (zero readers) | exactly one Person authority remains |
| **1** | Shared-editor deterministic mentions (@ restore + inline recognition/resolution + non-blocking Save Now + shadow fix) | Journal end-to-end verified |
| **2** | Hybrid enrichment scaffold (flagged, additive, idempotent) | flag-off ships safely; contract test green |
| **3** | Batch review + teaching moment (Learned phrases) | review is batch/optional; no sequential prompts |
| **4** | Roll out to all 20 rich fields; verify every RTE screen; ship together | all inherit the shared layer; docs/changelog/release notes |

Multi-week program. Phase 0 alone is large; it lands in reviewable stages, not one commit.

### As-built status (2026-07-18)

| Phase | Status | Notes |
|---|---|---|
| **0b** | ✅ shipped | `apps/people` models + services + read APIs (`api/lookup`, `api/resolve`). |
| **0c-A** | ✅ shipped | `people/0002_backfill_living_people` — relationships (A) + ai_relationships (C) → canonical, via `ingest_source_person` with the new `NAME_IDENTITY` match mode (unify a bare extraction "Heather" with the contact "Heather Jenkins"; ambiguous → review; never merge two full names sharing a first name). Idempotent, PersonSourceLink-keyed, no consumer redirect. |
| **0c-B** | ✅ shipped | `people/0003_backfill_legacy_genealogy` — legacy (B) → canonical, `SOURCE_LINK_ONLY` (create-distinct, never name-merge; GEDCOM = source_batch+xref). No People membership; only display_name projected (never collides with a living person on a bare first name); `also_known_as` + `RelationshipAlias` → `RecognitionPhrase(custom)`. Verified on the local snapshot: 111 legacy people migrated create-distinct. |
| **1 (Journal slice — explicit @mention)** | ✅ shipped | Canonical @mention in the shared editor + `people.PersonMention` (the canonical mention store) + `reconcile_journal_person_mentions`. Journal's legacy recognition paths (ai_relationships + relationships.Mention) retired for Journal. **Name + custom-phrase recognition only** — role phrases ("my wife") deferred: the inventory proved no role resolver is registered and the relationship graph is not canonical until 0d proper. Browser-verified end-to-end (autocomplete → token → save → PersonMention → visible chip on reopen → deletion reconciles). |
| **1 (Journal slice — passive prose recognition)** | ✅ shipped | `recognize_prose_mentions` — server-side prose scanner producing the *identical* mention token, reconciled by the same writer, all identity delegated to the ONE `resolution.resolve`. Deterministic-only (ambiguous → plain text, never guess); scoped to People **members** (genealogy-only never auto-recognized); records faithful `source_type` (`exact_name`/`confirmed_alias`, never a false `explicit_at_mention`); idempotent (skips existing tokens/links). No second recognition system. No model change. Browser-verified the reproduction: "Today I had dinner with Heather." (no @) → reopened → gold chip; five-way agreement. |
| **1 (Recognition-phrase management UI)** | ✅ shipped | Custom `RecognitionPhrase` CRUD is now reachable by users — the missing piece (the `phrases` service existed but had no endpoint/UI). Canonical endpoints `people:phrase_add/edit/delete` operate on `people.Person` (ownership-scoped, single `services.phrases` write path, duplicate/derived-collision guarded, host-agnostic `?next`). A reusable **Recognition** section (`templates/people/_recognition_section.html`) shows derived (read-only) + custom (add/edit/delete) phrases; hosted on the new canonical Person page **`/people/<pk>/`** (`PersonDetailView`, auto-declared Current Context) and embedded on the **production** People page (legacy `relationships:person_detail`, where the "People" menu goes). That page now **ensures** the canonical mirror on view (`_ensure_canonical_person` → idempotent `ingest_source_person`, `MATCH_NAME_IDENTITY`, grants membership) so Recognition ALWAYS appears — not only for backfill-covered contacts. ONE shared editor partial on both surfaces (no duplicate UI). Adding a phrase makes it recognized EVERYWHERE with zero Journal changes — the resolver, lookup API and passive recognition already consume `RecognitionPhrase`. Browser-verified: on `/relationships/2/` the section renders + add/edit/remove work, bridging to the EXISTING canonical Person (no dup); `@bab`→"Babe" chip (pid 112); passive "Dinner with honey, walk with Babe and Sweetie" → three canonical chips, ONE `PersonMention`, `confirmed_alias`. **Transition:** relationships pages host Recognition now; at 0d the People UI (menu/list/detail) migrates to canonical `apps/people` (`/people/<pk>/` already uses the same partial) → single unified experience; `PersonSourceLink` retired at 0f. |
| **0c self-anchor / 0d consumer repoint / 0e legacy / 0f retire** | ⏳ pending | Identity rows now exist canonically, but relationships/legacy/ai_relationships identity tables are **not** yet retired and consumers (SAE, dashboards, mobile import, relationship graph) still read their own stores. Role-phrase resolution ("my wife" → canonical) needs the relationship graph repointed (0d) + a role resolver registered. The full canonical People browse UI (list + nav) also lands with 0d; `/people/<pk>/` is the first canonical Person page. |

**Not run in 0c-A/0c-B:** contact self-anchor (A/C have no `is_self`; the self-anchor comes from legacy B in 0c-B). **Deferred deliberately:** role-phrase resolution; consumer redirection; legacy-table retirement.

---

## 11. Retirement criteria (per Decision 1)

Retire an identity table **only** when: exactly one canonical authority exists (`people.Person`); no production code reads the retired table; functionality and behavior are preserved (unless intentionally improved); runtime verification confirms every major workflow; the old table can be removed without breaking any feature. **A, B, and C identity tables are all retired.** The Relationships and Legacy **modules survive** — as consumers/extensions that reference Core Person, never re-deriving identity independently.

**Migration-complete checklist (all must be true):** one canonical Person authority; one recognition system; one identity resolution service; one merge service; every surviving capability references Core Person; every FK migrated; every consumer migrated; runtime verification proves existing workflows function; **genealogy intact · relationship intelligence intact · mentions intact · Current Context intact · CoS truth intact**; all **temporary migration bridges removed** (permanent bridges are not acceptable); retired Person models safely deletable — **zero production readers and zero production writers**.

---

## 12. Verification plan (results, not intentions — Article IV.1)

Prove the runtime path, not just tests. Per phase, browser-drive the affected screens (Journal save/@mention, People page phrases, Legacy tree/import/merge, CoS drift check-in), with console/network/log checks and five-way agreement where truth is displayed. Scoped test runs only (changed apps + directly impacted): `people`, `relationships`, `legacy`, `journal`, `core.ai_relationships`, `core.ai_state`, `life`, `mobile`, plus contract tests (`test_request_path_safety_contract`, `test_constitution_contract`, `test_current_context_contract`, and the new Person-architecture import test). `makemigrations --check --dry-run` on every model-touching commit.

---

## 13. Risks & the living-vs-deceased product concern

- **Biggest product risk:** surfacing **GEDCOM-imported historical ancestors** in the People list once Legacy identity joins Core Person. Resolved by the **People Membership** truth (§3.6.1): People shows members (people who became part of the user's life); Legacy shows the full genealogy graph. Deceased members are retained; GEDCOM-only, never-referenced people stay in Legacy until promoted. Deliberately *not* a "living-only" rule and *not* an "everyone" rule.
- **Blast radius:** 0d/0e touch SAE, proactive check-ins, and the Legacy graph — high-value surfaces. Staged gates + runtime verification bound it; the Legacy **extension** pattern (not full merge) is the deliberate reducer.
- **Larger migration than "elevate A":** all three identity tables retire. Justified — it's the only end-state with one owner and correct dependency direction. Sequenced so each module is verified before the next.
- **Reconciliation ambiguity:** cross-table identity matching will have uncertain cases → surfaced for review, never auto-merged (preservation-safe).
- **TipTap rebuild:** vendored-asset `collectstatic` must pass locally before push (prior Leaflet incident).

---

## 14. Obligations on completion (per CLAUDE.md)

Changelog (every commit); release notes / help / teaching-destinations / features doc as applicable; `ENGINE_COS_REFERENCE.md` (SAE/relationship-engine changes); Data Dictionary + Layer-1 truth inventory; `LAYER1_DOMAIN_FRAMEWORK.md` (Person as a new certified L1 domain); this doc kept current. **Not** declared finished until Danny reviews and approves the resulting product behavior.

---

## Success criteria (your bar)

Exactly one answer to every one of these:
- "Where do I get a Person?" → `apps.people.Person`
- "How do I resolve a Person?" → the Core Person resolution service
- "Where do Recognition Phrases live?" → Core Person (`people.RecognitionPhrase`)
- "How do I merge duplicate people?" → the Core Person merge service
- "How do I identify someone mentioned in a journal?" → the Core Person mention resolver

One Person model, one identity authority, one resolution service, one recognition system, one merge service, one canonical API. Every feature references that same Person.

---

## Already decided by you (recorded — not re-asking)

- Core Person is a Layer-1 domain at **`apps/people`**; retire A/B/C as identity authorities; Relationships & Legacy become consumers/extensions.
- **No `person_kind`** — independent status truths.
- **People vs Legacy = a deterministic `PersonMembership` truth** (§3.6.1), not a visibility filter. People = current-life view; Legacy = full genealogy view; same canonical Person, different surfaces. Death doesn't revoke membership; GEDCOM-only never grants it.
- Ownership split (Core owns identity/phrases/resolution/merge/membership/APIs; Relationships owns the graph + interaction intelligence; Legacy owns genealogy). Authority chain: AI proposes → WLJ validates → user confirms → WLJ stores.

## Proceeding this way unless you object (my call, low-risk)

- **People management UI moves to `apps/people`** (always-on), so identity/People stays reachable when Relationships is disabled; Relationships adds relationship-specific views on top. The "People" nav points at the Core People page.
- **The generic content→Person mention/reference store lives in `apps/people`** (one canonical store; resolution is already Core), created by modules via the Core resolver — not a per-module table.
- **Reconciliation is conservative:** exact identity match (name + self/birth anchor) auto-merges; anything uncertain stays separate and is surfaced for review (preservation-safe, never auto-merged blindly).

## Genuinely needs your judgment

None outstanding. The People-vs-Legacy boundary is resolved by the **People Membership** truth (§3.6.1, per your direction). Approved and implemented — see the Phase 0b as-built appendix below.

---

# Appendix A — Capability-Migration Matrix (migrate capabilities, not tables)

Every Person-related capability from the three retiring models, its consumers, whether it survives, and its canonical home. This is the ledger the consumer-migration phases (0c+) execute against. Source: the exhaustive consumer inventory.

| Capability | Current home | Key consumers | Survives? | Canonical home (after) |
|---|---|---|---|---|
| Canonical identity (name/email/phone) | A, B, C (all three) | everything | ✅ | **`people.Person`** |
| Rich identity notes/bio + plain shadow | A (`notes`), B (`bio`) | detail pages, search, AI | ✅ | `people.Person.notes` (+ `notes_plain`) |
| Photos / portrait | B (`portrait`→Media) | person detail | ✅ | `people.PersonPhoto` |
| Aliases / nicknames | B (`RelationshipAlias`, `also_known_as`) | resolution | ✅ (unified) | `people.RecognitionPhrase` (custom/learned) + derived |
| Self-anchor ("who is the user") | B (`LegacyProfile.self_person`, `is_self`) | self-binding, family tree | ✅ | `people.Person.is_self` + `identity.get/set_self_person` |
| Identity/name resolution | A (`MentionParserService`) | signals, mentions | ✅ (one resolver) | `people.services.resolution.resolve` |
| Merge / dedup | B (`person_merge`, legacy-only) | merge view | ✅ (extended, preservation-safe) | `people.services.merge.merge_persons` (+ legacy fix retained) |
| Lifecycle provenance | — (none existed) | new: debugging, trust, merge confidence | ✅ (new) | `people.PersonEvent` |
| **People membership boundary** | — (implicit / nav flag) | People list vs Legacy | ✅ (new, first-class) | `people.PersonMembership` |
| `Mention` (content→Person GenericFK) | A (`relationships.Mention`) | (write-only today) | ✅ → becomes real | `people` generic mention store (Phase 1) |
| `RelationshipInteraction` (GenericFK) | A | analytics, SAE, dashboard | ✅ (as relationship data) | **Relationships module**, FK → `people.Person` |
| Typed relationship graph + category | B (`Relationship`, `classify_category`) | family tree | ✅ | **Legacy** (edges) / **Relationships** (social), FK → `people.Person` |
| Relationship strength / importance / drift | C (`Relationship`, `InteractionSignal`) | proactive check-ins, SAE, cross-domain rules | ✅ (as interaction intelligence) | **Relationships module**, FK → `people.Person` |
| `PersonGroup` | A | groups UI | ✅ | Relationships (members M2M → `people.Person`) |
| GEDCOM / import provenance / Smart Refresh | B (`gedcom_xref`, `source_batch`, `ImportBatch`) | import, refresh | ✅ | **Legacy** extension (`LegacyPersonProfile`), FK → `people.Person` |
| Memories / MemoryPerson / PreservedFacts | B | Legacy stories, roadmap | ✅ | **Legacy**, FK → `people.Person` |
| `known_people` (CoS settings) | C | AI settings view | ✅ | Relationships / Core Person |
| SAE relationship state | A primary / C fallback | CoS context | ✅ (drift removed) | Core Person + Relationships |
| Contact import (VCF) | A (`ContactImportService`), mobile | mobile, web | ✅ | targets `people.Person` (Phase 0d) |
| **Cross-app FK** `life.SignificantEvent.person` | C | Life events | ✅ | re-point → `people.Person` (Phase 0d) |
| A↔C `display_name` string-join | `relationships/services.py:99-107` | — | ❌ deleted | (removed — hotspot eliminated) |

**Bridge:** `people.PersonSourceLink(source_domain, source_pk)` maps each retiring row to its canonical Person. Temporary; retired when every consumer reads `people.Person` (explicit gate).

---

# Appendix B — Phase 0b as-built (foundation)

**Delivered & verified (this milestone). Consumers NOT yet redirected — that is 0c+.**

- **Legacy `person_merge` data-loss fix** — re-points `PreservedFact` (was CASCADE-destroyed) and `LegacyProfile.self_person` (was SET_NULL-nulled) onto the survivor, and inherits `gedcom_xref`/`source_batch` provenance, before the existing hard-delete. Behavior + tests preserved; 3 regression tests added. **10/10 legacy merge tests pass.**
- **`apps/people` Layer-1 domain created** (always-on, no feature flag, registered SYSTEM domain):
  - Models: `Person` (independent truths: `is_deceased`, `is_self`, `origin`; no `person_kind`), `PersonMembership`, `RecognitionPhrase` (custom/learned; derived computed), `PersonPhoto`, `PersonEvent` (bounded lifecycle provenance), `PersonSourceLink` (bridge).
  - Services: `resolution.resolve` (the one resolver), `merge.merge_persons` (preservation-safe soft-delete), `membership`, `phrases` (derived/custom/learned + authority chain), `identity` (create + self-anchor), `provenance`, `reconciliation.ingest_source_person` (conservative bridge), and `hooks` (dependency-inverted extension points for role resolvers + merge participants — how features extend Core without Core importing them).
  - API: `people:lookup`, `people:resolve` (request-path-safe, read-only).
  - Migration `people.0001_initial`.
- **Contract test** `test_architecture_boundary` — fails CI if Core Person imports any feature module (incl. the three retiring Person homes).
- **Verification:** 39 `people` tests + 10 legacy merge tests pass; `makemigrations --check` clean; request-path-safety and constitution contracts pass.
- **Deferred (by design, not redirected):** bulk backfill across production data; consumer repointing; the always-on People management UI; the generic mention store; live `@` editor mentions; hybrid enrichment — all Phase 0c+ / Phase 1+.
- **Retirement status:** A/B/C identity tables — **still live authorities** (zero consumers migrated yet). `PersonSourceLink` bridge established. Nothing retired.
