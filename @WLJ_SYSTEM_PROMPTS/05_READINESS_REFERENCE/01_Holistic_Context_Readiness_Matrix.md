# Document 1 — ChatGPT Holistic Context Readiness Matrix

**Audit:** Does WLJ already expose sufficient deterministic truth for ChatGPT to act as Danny's holistic Chief of Staff?
**Method:** Read-only code verification. Code is authoritative. Every claim carries `file:line` evidence. No code was modified.
**Readiness scale:** COMPLETE = all required fields produced deterministically by an existing provider · PARTIAL = provider exists but some required fields absent (or computed but not reachable) · MISSING = no deterministic provider.

---

## A. The one structural fact that colors every row

The canonical state layer (SAE) already computes a per-domain state dict for **every** domain via `build_*_state(user)` in `apps/core/ai_state/state_builder.py`, reachable internally through `get_module_state(user, module)` (`apps/core/ai_state/state_engine.py:74`; module registry `MODULE_BUILDERS` `state_builder.py:5576`).

**But almost none of it is serialized over HTTP.** The only state-flavored external surfaces are:
- `GET /calendar/api/*` — calendar/event JSON (`apps/calendar_engine/urls.py:16-19`)
- `GET /ai/api/state/` — a *summarized* assessment, not the module dicts (`StateAssessmentView`, `apps/ai/views.py:1590`)
- `POST /ai/api/cos/decision/` — deterministic decision, "NO LLM" (`CosDecisionView`, `apps/ai/views.py:2221`)

So for most functions below, the deterministic **data exists** but is **internal-only** — consumed inside the Python chat loop, not exposed as a contract an external ChatGPT could call. This is a *serialization/wiring* gap, not a *truth* gap, and it recurs throughout the matrix.

---

## B. Readiness Matrix

| Context Function | Status | Existing Providers (file:line) | Gaps |
|---|---|---|---|
| **get_health_context()** | **PARTIAL** | `build_health_state` `state_builder.py:321` (weight `:358`, weight_trend `:375`, glucose `:907/1018`, sleep `:598`, recovery/HRV `:671/1126`); `build_fitness_state:2213` (workouts `:2232/2299`); `build_medicine_state:3512` (meds `:3549`); `build_medical_state:4911` (labs/abnormal `:4980`) | No aggregated **"recent changes"** delta object; **medical risks** only as lab flags + per-metric status verdicts, no unified risk object; spread across 4 modules; no HTTP serialization |
| **get_faith_context()** | **PARTIAL** | `build_faith_state` `state_builder.py:1622` (prayer `:1655`, scripture `:1647-1652`, faith trust signal `:1678`) | **saved verses**, **spiritual trends**, **faith learning** all absent from state; devotion only via optional journey submodule `:1686` |
| **get_journal_context()** | **PARTIAL** | `build_journal_state` `state_builder.py:1731` (mood_trend `:1818`, stress_score `:1883`, anxiety mentions `:1849`, entry counts `:1760/1795`) | **recent-entry content/text**, **major themes**, **gratitude trends** (no `GratitudeEntry` model — confirmed absent), **recent reflections** all MISSING; state stores aggregates, not entry bodies |
| **get_goal_context()** | **PARTIAL** | `build_goal_state` `state_builder.py:1424` (active `:1438/1507`, momentum `:1526`, overdue `:1509`); `build_habit_state:1534` (streaks `:1617`, completion `:1577`) | **priorities** (foundational flag only; ranking lives in `DailyPrioritiesView`, separate), no explicit **stalled** classification (only overdue), no directional **discipline-trend** field |
| **get_relationship_context()** | **PARTIAL** | `build_relationships_state` `state_builder.py:4671` (people `:4777`, signals/neglect `:4774/4781`, engagement gaps `:4709`); `RelationalHealthService.compute_health` `apps/relationships/services.py:219` | **family state** aggregate MISSING; **recent interactions** only as days-since recency (`:4703`), no interaction log/feed |
| **get_calendar_context()** | **COMPLETE** | `build_calendar_state` `state_builder.py:3833` (upcoming `:3943`, density `:3928`, conflicts `:3964`, next `:3918`); `get_active_block` `apps/core/execution/active_block.py:145`; execution module `build_today_execution` `today_execution.py:34`; **HTTP APIs** `apps/calendar_engine/urls.py:16-19` | None on fields; uniquely also has HTTP exposure |
| **get_dashboard_context()** | **COMPLETE** (internal) | `build_executive_context` `cos_context.py:9079` (summary `:9093`, risks `:9094`, momentum/opportunities `:9095`, focus `:9100`); `build_cos_intelligence` `apps/ai/cos_intelligence.py:253` | All five fields present deterministically; **internal-only** (needs serialization); "opportunities" maps to momentum/recommendation-effectiveness, not a literal opportunities array |
| **get_document()** | **PARTIAL** | By-id HTML detail views per domain: notes `apps/notes/urls.py:18`, capture `CaptureDetailView`, medical `apps/medical/urls.py:21-29`; deterministic search **exists**: `SearchService` `apps/ai/search_service.py:30`, `search_notes_cos` `apps/notes/services.py:419` | Search engines are **dead code** (zero production callers); no JSON document API; no unified fetch-by-id-or-query contract; detail views render HTML, not data |
| **search_history()** | **PARTIAL** | Time-based lookup via `query_event_history` intent → `EventResolver` (16 health/life adapters) `apps/core/ai_events/resolver.py:24-47`; handler `apps/ai/action_handlers.py:6626`; conversation semantic recall `apps/ai/memory_service.py:314` | **No keyword search**, **no unified history search**; insights/guidance are list-views only (`ai_insights/views.py:13`, `ai_guidance/views.py:26`); briefings searchable in **admin only** (`ai_briefing/admin.py:22`); predictions/recommendations have no search |
| **search_capture()** | **PARTIAL → MISSING** | Transcripts/summaries stored `apps/capture/models.py:109/114`; `CaptureSignal` themes `:475`; transcript-searching `SearchService.search_capture` `apps/ai/search_service.py:1383` | Only **live** capture search (`CaptureListView` `apps/capture/views.py:313`) **excludes transcripts**; `SearchService` unwired; **no action-items entity** (none in models); **no full-text index** (only `icontains`); `CaptureSignal` unsearchable |
| **get_screen_context()** | **PARTIAL** | Real in-app pipeline: client `getFullPageContext()` `templates/components/assistant_panel.html:686` → `page_context` in chat body `apps/ai/views.py:766/1091` → `_build_page_awareness_instruction` `apps/ai/personal_assistant.py:166` | Per-page-type **DOM-scraping**, not authoritative widget serialization; **no** server-side widget/composer JSON; **in-app only** — no standalone endpoint, unreachable by an external CoS |

---

## C. Tally

| Status | Count | Functions |
|---|---|---|
| **COMPLETE** | 2 | get_calendar_context, get_dashboard_context (latter internal-only) |
| **PARTIAL** | 8 | health, faith, journal, goal, relationship, get_document, search_history, search_capture, get_screen_context |
| **MISSING** | 0 (full) | — (search_capture is PARTIAL leaning MISSING for the CoS) |

No function is wholly MISSING. The dominant pattern is **PARTIAL because of two recurring causes**: (1) deterministic data exists but is **not serialized over HTTP** for an external consumer, and (2) SAE stores **aggregates/verdicts, not raw text/content**, so content-bearing fields (journal bodies, reflections, saved verses, interaction logs, transcripts, action items) are absent from state.

See Document 2 for the consolidated gap list and Document 3 for the cross-domain reasoning verdict.
