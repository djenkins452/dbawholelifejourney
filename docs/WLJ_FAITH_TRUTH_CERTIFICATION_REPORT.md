# WLJ Faith Domain — Truth Certification Report (Step 1 of 5)

**Domain:** Faith & Spiritual
**Certification step:** **Step 1 — Verify Deterministic Truth** (only)
**Standard:** `docs/WLJ_COS_DOMAIN_CERTIFICATION_STANDARD.md` (RATIFIED 2026-07-19)
**Date:** 2026-07-19
**Status:** Step 1 COMPLETE. Steps 2–5 NOT started. **No implementation performed.**
**Method:** Runtime traces (not guesses) through the real registry, catalog, semantics, and
`FaithDomainTruth` provider with live records, per the certification standard and
`docs/WLJ_RUNTIME_TRACE_DEBUGGING.md`.

---

## 0. Executive Summary

Faith is **already one of the more mature CoS truth domains** — materially further along at
the start of certification than Nutrition or Journal were. It has a registered
`FaithDomainTruth` provider (4 current metrics, 1 history metric, 2 entity types), a canonical
`FaithQueries` authority, a canonical unified-completion source (reading plan **+** routine→faith
bridge), plain-language `domain_semantics`, three Discovery-Suite prompts, keyword search wiring
(`search_faith`), and a full SAE state builder. Entity completeness (prayer + reading_plan),
CompleteEntity composition, and by-name resolution are all present and **runtime-proven** below.

The gaps are therefore **overwhelmingly exposure, not construction** — exactly the pattern the
standard predicts. The headline findings:

| # | Finding | Class | Layer |
|---|---------|-------|-------|
| **A** | Faith `current()` metrics read the pre-computed SAE snapshot with **no `ensure_fresh` self-heal** (faith is not in `_MANUAL_MODULE_SOURCES`), yet prayer/reading logging is manual entry → stale-read risk (same class as the fixed journal-snapshot bug). | Exists but fragile | Truth (freshness) |
| **B** | The `studying` current metric reads `template.name` (field is `title`) → falls through to `str(plan)` = **`"user@email: Plan Title"`**, leaking the email and mis-naming the plan. | Truth-quality defect | Truth |
| **C** | Faith declares **no `analysis_subjects`** → it does **not participate in `get_analysis`**. "How's my prayer life trending / analyze my Bible-reading consistency / themes in what I pray about" have no analyze tool (Journal and Nutrition both have one). | Exists but not exposed | Truth exposure |
| **D** | **Zero Current Context page-summary providers.** Every Faith *overview* page is Beth-blind (only the model `DetailView`s auto-declare). | Exists but not exposed | Experience |
| **E** | Entity surfaces cover only **prayer + reading_plan**. `FaithMilestone`, `SavedVerse` (incl. memory verses), `BibleStudyNote`, `BibleHighlight`, `BibleBookmark`, and the **Journey** sub-domain have **no `get_entity` surface** (keyword search partially covers some). | Mixed (mostly not-exposed) | Truth exposure |
| **F** | The `faith.journey` ("Walking With God") sub-domain registers as a capability + builds SAE state, but has **no `DomainTruth` entity/history surface** — its rich per-arc/day progress is not CoS-retrievable as truth. | Exists but not exposed | Truth exposure |

**No capability was found to be a genuine, from-scratch truth gap.** Every candidate below is
either already exposed, or an *aggregate/surface over records WLJ already stores*.

---

## 1. Existing Data Model

### 1.1 Canonical models (`apps/faith/models.py`, 1063 lines)

| Model | Owner | Kind | Key fields | Notes |
|-------|-------|------|-----------|-------|
| `ScriptureVerse` | **System** (not user) | Curated verse library | reference, text, translation, book_order, themes[], contexts[], is_active | Global content, not personal truth |
| `DailyVerse` | **System** | Daily verse assignment | date (unique), verse FK, theme, reflection_prompt | Global content |
| `PrayerRequest` | **User** (`UserOwnedModel`, `RichTextMixin`) | Personal | title, description(+_plain), is_personal, person_or_situation, priority, is_answered, answered_at, answer_notes(+_plain), remind_daily | `CONTEXT_FIELDS` = plain shadows; `mark_answered()` |
| `SavedVerse` | **User** | Personal | reference, text, translation, book_order, themes[], notes, **is_memory_verse** | Memory-verse flag drives dashboard |
| `FaithMilestone` | **User** (`RichTextMixin`) | Personal | title, milestone_type (salvation/baptism/rededication/…), date, description(+_plain), scripture_reference | Faith-journey moments |
| `ReadingPlanTemplate` | **System** | Plan definition | title, **slug**, description, category, difficulty, source/series, allowed_emails[], duration_days, topics[] | `validate_day_integrity()`; **has `title`, not `name`** (root of Finding B) |
| `ReadingPlanDay` | **System** | Plan day | plan FK, day_number, scripture_references[], scripture_content[] (red-letter), context_summary, commentary_{beginner,intermediate,advanced}, reflection_prompt | `get_commentary_for_level()` |
| `UserReadingPlan` | **User** | Personal instance | template FK, **plan_status** (active/completed/paused/abandoned), started_at, completed_at, **current_day**, reminder_time | `get_context_summary()` (Current Context for the day), `progress_percentage`, `days_completed`, `is_complete`, `mark_complete()` |
| `UserReadingProgress` | **User** | Per-day completion | user_plan FK, plan_day FK, is_completed, completed_at, **notes** (reflection) | `mark_complete()` advances `current_day` + completes plan |
| `ReadingPlanAssessment` | **System** | In-plan assessment | plan_day FK, questions[], score_ranges[], scoring config, is_reflection_only | `get_score_interpretation()` |
| `UserAssessmentResponse` | **User** | Personal | assessment FK, user_plan FK, responses{}, total_score, completed_at | `interpretation` property |
| `BibleHighlight` | **User** | Study tool | reference, text, translation, book_order, color | |
| `BibleBookmark` | **User** | Study tool | reference, translation, book_order, title, notes | |
| `BibleStudyNote` | **User** (`RichTextMixin`) | Study tool | reference, translation, book_order, title, content(+_plain), tags[] | Longer-form notes |

### 1.2 Journey sub-app (`apps/faith/journey/models.py`) — "Walking With God Through Scripture"

Registered as its **own** domain `faith.journey` in the registry. Models (per SAE `state.py`):
`JourneyPath`, `JourneyArc`, `JourneyDay`, `UserJourney` (journey_status, current_arc,
current_day_number, preferred_difficulty, last_engaged_at), `UserJourneyDayProgress`
(application_committed, completed_at, `context_ref()`). Isolated: a journey failure never breaks
faith state (`try/except` in `build_faith_state`).

### 1.3 Canonical truth owners & relationships

- **Prayer truth owner:** `PrayerRequest` (person-scoped).
- **Bible-reading completion truth owner:** the **union** of `UserReadingProgress.is_completed`
  **and** the routine→faith bridge (`RoutineLog` named in `FAITH_BIBLE_NAMES`). This union is the
  canonical source — see `FaithQueries.bible_completion_dates` / `is_bible_complete_on`. It exists
  specifically to prevent the "22 days since scripture while reading daily via a routine" trust
  bug (2026-06-16). **Any consumer of "was Bible reading done on date X" must go through
  `FaithQueries`.**
- **Faith task completion:** faith-module `life.Task` (`completion_status='completed'`,
  `module='faith'`).
- **Study-tool truth owners:** `BibleHighlight` / `BibleBookmark` / `BibleStudyNote` (person-scoped).
- **Journey truth owner:** `UserJourney` + `UserJourneyDayProgress` (person-scoped, sub-domain).

---

## 2. Existing Deterministic Truth

### 2.1 Canonical query authority — `apps/faith/services/faith_queries.py :: FaithQueries`

Reading plans: `active_reading_plans`, `has_active_plan`, `reading_completed_on`,
`has_reading_on`, `last_reading`, `reading_completion_dates` (plan-only), **`bible_completion_dates`**
and **`is_bible_complete_on`** (the canonical union), `reading_series` (per-day history).
Prayers: `unanswered_prayers`, `answered_prayers`, `urgent_prayers`.
Entity composition: `describe` / `describe_one` (prayers → CompleteEntity), `describe_plans` /
`describe_plan_one` (reading plans → CompleteEntity, incl. current reading + per-day reflection
notes). Faith tasks: `faith_task_completed_on`, `has_faith_task_completed_on`.

### 2.2 Metrics service — `apps/faith/services/faith_metrics.py :: get_faith_metrics`

Canonical metric bundle used by PA `_get_faith_state`, Executive Briefing, proactive check-ins.
Reads SAE (primary) + Execution Truth Engine (today) + direct queries for
`answered_prayers_month`, `total_prayers`, `faith_milestones`.

### 2.3 SAE state builder — `apps/core/ai_state/state_builder.py :: build_faith_state` (L1892)

Produces the faith snapshot: `active_reading_plans`, `last_scripture_read`,
`days_since_reading`, `reading_streak` (`_calculate_reading_streak`, unified source),
`unanswered_prayers`, `answered_prayers`, `recent_prayer_titles`, `urgent_prayers`,
`bible_plan_name`, `_trust` (signal-trust report), and the nested **`journey`** block
(`apps.faith.journey.state.build_journey_state`).

### 2.4 DomainTruth provider — `apps/core/truth/domain_rollout.py :: FaithDomainTruth` (L372)

**The CoS truth seam.** Runtime-verified `supports()`:

```
current:  ('reading_streak', 'days_since_reading', 'unanswered_prayers', 'studying')
history:  ('reading',)
entities: ('prayer', 'reading_plan')
analysis: ()                      ← EMPTY (Finding C)
```

- `current(metric)` — `studying` reads live via `FaithQueries.active_reading_plans`; the other
  three read `self.state()` (pre-computed SAE, `allow_rebuild=False`).
- `describe('prayer'|'reading_plan')` → `FaithQueries.describe` / `describe_plans`.
- `describe_one(name)` → reading plan by template title first, else prayer (fixed subset defect;
  regression-tested in `test_truth_validation_faith.py::FaithEntityByNameTests`).
- `history('reading', period)` → `FaithQueries.reading_series` (per-day completion, unified source).

### 2.5 Plain-language routing — `apps/core/truth/semantics.py` (faith @ L157)

```
purpose:  "The person's prayers and Scripture reading plans and progress."
entities: prayer → "A prayer the person recorded."
          reading_plan → "A Bible reading plan and its progress."
cues:     ["my prayers", "my reading plan", "my Bible reading"]
```
No `boundary` note and no derived `analyzes` list (because `analysis_subjects` is empty — Finding C).

### 2.6 Discovery Suite — `apps/core/truth/discovery_suite.py` (L246)

Three certified prompts: `faith.reading_plan` (→ `faith.entity(reading_plan)`, active-plan
selection rule), `faith.prayer` (→ `faith.entity(prayer)`, latest), `faith.reading_consistency`
(→ `faith.history(reading)`). Each carries `must_surface` expectations.

### 2.7 Keyword search — `apps/ai/search_service.py :: search_faith` (L976)

Wired into `history_search` via `_SEARCH_DOMAIN_MAP["faith"] = "search_faith"`. Searches prayers,
scriptures, reading plans, milestones by keyword/content_type.

### 2.8 Other deterministic truth

- **Execution Truth Engine** — `truth['domains']['faith']`: `bible_reading_completed`,
  `prayer_completed` (today, incl. routine bridge).
- **Biblical calendar** (`biblical_calendar.py`), **engagement** (`engagement.py`),
  **signal trust** (`assess_faith`), **calendar activities** service.

### 2.9 Runtime proof (live records, rolled back)

Created a user + active reading plan (1 completed day w/ reflection note) + one urgent unanswered
prayer, then drove `FaithDomainTruth` directly:

```
current('studying')          → present=True  value='rt_trace_faith@example.com: RT Trace Plan'  ⚠ Finding B
current('unanswered_prayers')→ present=False  reason='no recent data'                            ⚠ Finding A (no SAE snapshot)
describe('prayer')           → 1 entity  identity='Healing for Mom'  status='unanswered'         ✅
describe('reading_plan')     → 1 entity  identity='RT Trace Plan'  status='active'  progress=33  ✅
describe_one('RT Trace')     → kind='reading_plan'                                                ✅
history('reading','last_7_days') → HistorySeries, 1 point                                         ✅
```

`describe` / `describe_one` / `history` compose real deterministic truth. The two ⚠ lines are the
findings detailed in §5–6. (`test_truth_validation_faith.py` additionally proves active-plan
resolution and by-name retrieval; note that suite currently **errors on a slug collision** with
migration-loaded reading-plan fixtures — a pre-existing test-data issue, unrelated to the truth
layer.)

---

## 3. Existing User Experience

### 3.1 Pages (`apps/faith/urls.py`, `views.py` 2176 lines, + `views_first_light.py`)

**Overview / list pages (TemplateView / ListView):** `home` (First Light dispatch) · `today` ·
`mirror` · `home_classic` (`FaithHomeView`) · `todays_verse` · `scripture_list` · `prayer_list` ·
`answered_prayers` · `milestone_list` · `reflections` · `reading_plans` · `study_tools` ·
`highlight_list` · `bookmark_list` · `study_note_list`.

**Detail pages (`DetailView`):** `scripture_detail` (SavedVerse) · `prayer_detail` (PrayerRequest) ·
`milestone_detail` (FaithMilestone) · `reading_plan_detail` (ReadingPlanTemplate) ·
`reading_plan_progress` (UserReadingPlan) · `study_note_detail` (BibleStudyNote).

**Journey pages** (`faith/journey/urls.py`): `today`, `start`, `settings`, `review_day`,
`complete_day`, annotations, `confusion_flagged`, `_health`.

### 3.2 Current Context declarations

- **Detail pages:** the `UserOwnedModel` `DetailView`s (Prayer, Milestone, SavedVerse, StudyNote,
  UserReadingPlan-progress) are **auto-declared** by `base.html` via `object.context_ref` →
  `<meta name="wlj-context" content="faith.model:pk">`. `UserReadingPlan.get_context_summary()`
  correctly focuses the CURRENT DAY's reading. `ReadingPlanTemplate` detail is system content (not
  user-owned) so it is not a personal context object.
- **Overview pages:** **NONE declare a `summary:<key>`.** A repo-wide scan for
  `@register_page_summary` returns only artifacts/health/meals keys — **zero faith keys**
  (**Finding D**). Every faith overview page is Current-Context blind.
- **Journey:** `UserJourneyDayProgress.context_ref()` is used by `journey_today` (has its own
  Current Context test), but the broader journey overview is not a page summary.

---

## 4. Existing CoS Capabilities (what Beth can answer TODAY)

Given the exposed surfaces, the CoS can already answer, from deterministic faith truth:

| The user asks… | Tool / surface | Backing truth | Verified |
|----------------|----------------|---------------|----------|
| "Tell me everything about my current Bible study" | `get_entity(faith, reading_plan)` | `describe_plans` → CompleteEntity (title, category, duration, current day, %, today's reading, reminder, per-day reflections) | ✅ §2.9 + discovery `faith.reading_plan` |
| "Tell me about my *Journey Through John* plan" | `get_entity(faith, name=…)` | `describe_plan_one` (by template title) | ✅ test `FaithEntityByNameTests` |
| "What have I been praying about?" / "my most recent prayer" | `get_entity(faith, prayer)` | `describe` → CompleteEntity (request, priority, who/what, recorded, answered status, answer notes, remind_daily) | ✅ §2.9 + discovery `faith.prayer` |
| "How consistent has my Bible reading been?" | `get_history(faith, reading)` | `reading_series` (per-day, unified source) | ✅ §2.9 + discovery `faith.reading_consistency` |
| "Is my Bible reading done today?" / streak / days-since | `get_domain_state(faith)` | SAE `build_faith_state` (unified source) | ✅ (SAE-dependent — Finding A) |
| "How many unanswered / urgent prayers do I have?" | `get_domain_state(faith)` | SAE `unanswered_prayers` / `urgent_prayers` | ⚠ SAE-dependent (Finding A) |
| "What am I studying right now?" | `current(faith, studying)` | live `FaithQueries.active_reading_plans` | ⚠ works but leaks email / mis-names (Finding B) |
| "Find the prayer where I mentioned *my job*" | `search_history(faith, keywords)` | `search_faith` (keyword) | ✅ wired |

**Cannot answer today** (the gaps): analyze/trend questions about faith ("how's my prayer life
trending", "analyze my spiritual habits") — **no `get_analysis(faith,…)`** (C); "what are my memory
verses", "tell me about my baptism", "my study notes on Romans 8", "where am I in Walking With God"
— **no entity surface** (E/F); and no faith overview page gives Beth page context (D).

---

## 5. Truth Inventory

### ✅ Already exists AND exposed (CoS-reachable today)
- Active reading plan(s) + progress/%/current-day/current-reading/reminder/reflections — `get_entity(reading_plan)`.
- Prayer records (request, priority, subject, answered status, answer notes, remind flag) — `get_entity(prayer)`.
- By-name retrieval of a plan or prayer — `describe_one`.
- Per-day Bible-reading history (unified plan + routine source) — `get_history(reading)`.
- Aggregate current state (streak, days-since, unanswered/urgent counts, plan name, journey block) — `get_domain_state` (SAE).
- Today's completion (bible_reading_completed / prayer_completed) — Execution Truth Engine.
- Keyword search over prayers/scriptures/plans/milestones — `search_faith`.

### ⚠ Exists (as records/producers) but NOT exposed as CoS truth
- **Faith analysis** — no `analysis_subjects`; the composable inputs (`history('reading')` +
  `describe('prayer'/'reading_plan')`) already exist. **(C)**
- **Faith milestones** — `FaithMilestone` records + `get_faith_metrics` count exist; no `get_entity(milestone)`. **(E)**
- **Memory verses / saved verses** — `SavedVerse` (`is_memory_verse`) records exist; no `get_entity`. **(E)**
- **Bible study notes / highlights / bookmarks** — records exist; keyword-searchable only; no `get_entity`. **(E)**
- **Journey progress** — `UserJourney` state + `build_journey_state` exist; no `DomainTruth` surface. **(F)**
- **Answered-prayer analytics** — `answered_prayers_month`, `total_prayers` computed in `get_faith_metrics`; not surfaced as history/analysis. **(part of C/E)**
- **Faith overview page context** — deterministic page summaries not declared. **(D)**

### ❌ Truly missing deterministic truth (genuine construction)
- **None identified.** Every candidate above is exposure of an existing record set or a small
  aggregate over records WLJ already stores. No new reasoning engine, no free-text extraction, and
  no new store is required to reach conversational completeness. (Two *new small aggregates* may be
  worth adding as domain-owned surfaces — a prayer cadence/answered-rate series and a
  memory-verse/milestone entity — but the underlying truth already exists; these are surface work,
  not missing truth.)

---

## 6. Gap Analysis (exposure vs. genuine truth gap — no implementation proposed)

- **A — SAE freshness (fragility, not a gap).** `FaithDomainTruth.state()` calls
  `ensure_fresh(user, ['faith'])`, **but faith is not in `_MANUAL_MODULE_SOURCES`** → the self-heal
  is a **no-op**. Prayer and reading logging are manual entry, so the `current()` metrics and
  `get_domain_state(faith)` can serve a stale snapshot between a write and the async SAE refresh —
  the **same class** as the fixed journal-snapshot staleness bug (`15860242`). **Exposure/robustness
  problem** (the truth exists; the read path can lag). *Step 2 candidate: register a faith manual
  source so stale reads self-heal.*
- **B — `studying` metric quality defect.** `getattr(template, "name", None) or str(pl)` resolves
  to `str(pl)` = `"email: title"` because the field is `title`, not `name`. **Genuine
  truth-quality bug** (leaks email; mis-names). `describe_plans`/`_plan_to_entity` already do it
  right (`title or name`). *Step 2 candidate: read `template.title`.*
- **C — No faith `analysis_subjects` (biggest CoS-completeness gap).** **Pure exposure.** The
  inputs already exist and analysis would be **pure composition** (identical to Journal's model):
  map faith analysis subjects to `history_metric='reading'` + `entity_type='prayer'/'reading_plan'`.
  WLJ supplies the evidence bundle; the model interprets — WLJ renders no verdict. Once declared,
  the `analyzes` routing list derives automatically from the catalog (drift-proof, per `fabd0dab`).
  *Step 2 candidate: declare `analysis_subjects` (declaration-only; zero new retrieval).*
- **D — No Current Context page summaries.** **Exposure.** Per the Current Context Contract, each
  faith overview page should declare `summary:<key>` via `PageSummaryMixin` + a
  `@register_page_summary` provider fed by ONE deterministic source (reuse `FaithQueries` /
  `build_faith_state` — never re-derive). *Step 2 candidate: prayer-list, reading-plans, faith-home
  summaries.*
- **E — Missing entity surfaces (milestone / saved-verse / study-note).** **Exposure.** Records
  exist; add `entity_types` + `describe`/`describe_one` delegating to new `FaithQueries` composers
  (small, domain-owned; no new store). Keyword search already partially covers these, but not as
  complete retrievable entities. *Step 2 candidate, prioritized by user value (milestones + memory
  verses first).*
- **F — Journey sub-domain not a truth surface.** **Exposure** (the state builder already computes
  it). Decide in Step 2 whether Journey is surfaced as faith entities (`journey`/`journey_day`) or
  as its own `faith.journey` DomainTruth. *Design decision, not missing truth.*

---

## 7. Recommendations for Step 2 (Expose existing truth — exposure beats construction)

Ordered by trust impact; **all are exposure of existing truth**, none is a reasoning engine:

1. **Fix Finding B** (`studying` → `template.title`) — smallest, highest-embarrassment defect.
2. **Register faith in SAE `ensure_fresh`** (Finding A) — closes the stale-read class for
   manual prayer/reading logging.
3. **Declare `analysis_subjects`** (Finding C) — declaration-only; unlocks `get_analysis(faith,…)`
   and the derived `analyzes` routing metadata in one drift-proof step (mirror Journal exactly).
4. **Add missing entity surfaces** (Finding E) — `milestone` + `saved_verse`/`memory_verse` first,
   then `study_note`; reuse/extend `FaithQueries`; update `semantics.py` entities.
5. **Declare Current Context page summaries** (Finding D) for the faith overview pages, each from
   ONE deterministic source.
6. **Decide the Journey surfacing model** (Finding F).

**Invariants to hold in Step 2:** WLJ never renders a verdict (evidence bundle only); the
capability declaration and the plain-language routing metadata derive from ONE source; retrieve
(`get_entity`) vs. search (`search_history`) vs. analyze (`get_analysis`) stay distinct; fix the
first failing layer bounded by blast radius. **Do not proceed to Step 2 until this Step 1 report is
reviewed.**

---

## 8. Certification Ledger

| Step | Status |
|------|--------|
| 1. Verify deterministic truth | ✅ **COMPLETE** (runtime-proven) |
| 2. Expose existing truth | ✅ **COMPLETE** — shipped (see §9) |
| 3. Validate conversational routing | ✅ **COMPLETE** — prod-traced on the real runtime; findings fixed (see §10) |
| 4. Production validation (Danny's gate) | 🔄 IN PROGRESS — first pass done; cleanup fixed; **AWAITING re-validation** |
| 5. Close the milestone | ⛔ NOT STARTED — do NOT declare complete until Danny re-verifies in prod |

---

## 10. Production-Validation Cleanup (2026-07-20)

Danny's first production pass surfaced five findings. Each was **runtime-traced through the REAL
production path** — Danny runs `use_model_interface=True`, so `CoSGateway.respond(surface=chat)`
routes to `ModelInterfaceService` (13 tools incl. `get_entity`/`get_analysis`), with the tool
layer instrumented to capture tool + args + status. No guessing; smallest fix per proven cause;
no new deterministic truth.

| # | Prod symptom | First failing layer (traced) | Fix |
|---|--------------|------------------------------|-----|
| 1 | "most recent prayer" → wrong / "none today" | Model called `get_entity(entity_type='prayer_request')` → `unsupported` (type registered as `prayer`) | Advertise `prayer_request` alias + `describe_one("latest/most recent prayer")` → newest |
| 2 | "prayers about family" → "couldn't retrieve" | NOT a defect — `search_history(faith,'family')`=ready returns the family prayer; the text is the emergency-fallback signature (transient) | Regression lock only; keyword search is literal by design |
| 3 | "study notes" → reading plans | (legacy `chatgpt_cos` runtime) search matched reading-plan **descriptions**; notes absent from `search_faith`. Prod `model_interface` path already retrieves via `get_entity(study_note)` | Add study_note/highlight/bookmark to `search_faith`; reading-plan search matches TITLE only |
| 4 | analysis themes ungrounded (Matthew/John/…) | `get_analysis`→`describe_plans` returned ABANDONED + old plans | `describe_plans` excludes `abandoned` (not study truth) |
| 5 | page-summary questions ignored | `model_interface._focus_lead` only POINTED at the focus JSON buried in a 60k-char prompt → model said "content not provided". (`chatgpt_cos`: `is_page_reference` missed the phrasings → `priority_now` hijack) | `_focus_lead` INLINES the on-screen content (single source, like `_profile_lead`); extend `is_page_reference` |

**Re-verified on the real gateway with the live model** (rolled-back real records): #1 → "your dad's
health… urgent… July 19"; #5 (all three phrasings) → answered from the page summary (9 active, 3
urgent, 9 answered, recent prayers); #4 → prayer-grounded themes, no stale plan names; #2/#3 →
correct. **Faith is NOT production-complete until Danny re-validates these in production.**

---

## 9. Step 2 — Exposure Implemented (2026-07-19)

All Step-1 findings addressed as **exposure only** (no new deterministic truth, no reasoning; WLJ
renders no verdict). Runtime-proven with rolled-back real records + a new regression suite
(`apps/faith/tests/test_faith_cos_exposure.py`, 9/9).

| Finding | Change | Files |
|---------|--------|-------|
| **A** freshness | `faith` registered in `_MANUAL_MODULE_SOURCES` (PrayerRequest + UserReadingProgress); multi-source normalization fixed so either write self-heals a stale snapshot. | `apps/core/ai_state/state_freshness.py` |
| **B** studying leak | `current('studying')` reads `template.title` (never `str(plan)` → no `email: Title`). | `apps/core/truth/domain_rollout.py` |
| **C** analysis | Declared `analysis_subjects` (13 phrasings → reading history + prayer/reading_plan entity); `get_analysis(faith,…)` now composes; `analyzes` routing derived from catalog. | `apps/core/truth/domain_rollout.py` |
| **E** entities | New `entity_types` milestone / saved_verse / study_note / highlight / bookmark + `FaithQueries` composers; `describe_one` resolves them by name; semantics descriptions added. | `apps/faith/services/faith_queries.py`, `apps/core/truth/domain_rollout.py`, `apps/core/truth/semantics.py` |
| **D** page summaries | `faith.prayers` / `faith.reading_plans` / `faith.home` providers (FACTS only, from `FaithQueries`) + `PageSummaryMixin` on the four overview views. | `apps/faith/page_summaries.py` (new), `apps/faith/apps.py`, `apps/faith/views.py` |
| **F** journey | Deliberately deferred (design decision, not missing truth) — out of Step 2 scope. | — |

**No new deterministic truth. No reasoning. STOP before Step 4** — the milestone is
`AWAITING VALIDATION` until Danny runs the questions in production and confirms.
