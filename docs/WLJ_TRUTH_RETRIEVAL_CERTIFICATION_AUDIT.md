# WLJ Truth Retrieval Certification — Architecture Validation & Coverage Audit

**Date:** 2026-07-17
**Scope:** Validate (not redesign) the existing universal truth-retrieval architecture, audit every canonical domain against real customer questions, and identify the *smallest additive* work to make the Chief of Staff answer any straightforward factual question about the user's life.
**Verdict up front:** The architecture is **sound and already scales correctly**. Every gap found is **additive coverage**, plus one certification-target fix and one runtime-consolidation decision. **No redesign is warranted.**

---

## 1. Inventory — the existing retrieval architecture

There is exactly one universal retrieval contract. Every consumer asks the same object the same way.

| Layer | Component | File |
|---|---|---|
| Contract | `DomainTruth` base — `current()` / `history()` / `describe()` / `analysis_subjects`, introspected via `supports()` | `apps/core/truth/domain.py:64` |
| Registry | `@register_domain_truth` + lazy self-registration from `_KNOWN_PROVIDER_MODULES` | `apps/core/truth/domain.py:22` |
| Introspection | `truth_catalog()` — enumerates every domain's answerable `current`/`history`/`entities` | `apps/core/truth/catalog.py:15` |
| Entity law | `describe()` returns `CompleteEntity` objects (single deterministic retrieval that fully answers a record) | `apps/core/truth/entity.py` |
| Model read tools | `get_domain_state` · `get_history` · `get_entity` · `get_analysis` · `get_user_truth` · `get_foundational_health_facts` · `search_history` | `apps/ai/model_interface/constitution.py:693` |
| Read services | `domain_state.py` · `domain_entity.py` · `domain_history.py` · `domain_analysis.py` | `apps/ai/cos_services/` |
| Certification (architecture) | Layer manifest + `certify_layers` CI gate | `apps/core/truth/certification.py`, `apps/core/management/commands/certify_layers.py` |
| Certification (per-question) | Acceptance question bank → expected deterministic answers, graded RED/YELLOW/GREEN | `apps/ai/chatgpt_cos/acceptance_rules.py`, `acceptance_service.py` |

**Routing:** There is **no hardcoded per-module routing in the model path.** The model picks a domain by choosing an enum value, and those enums are generated from `truth_catalog()` (`constitution.py:448`). A domain that registers a surface participates automatically. This is the property the milestone requires — confirmed present.

---

## 2. Architecture validation — does it already satisfy the long-term goal?

> *"A new WLJ module should become CoS-accessible simply by exposing its canonical truth through the existing retrieval contract."*

**YES — explicitly confirmed.** Evidence:

1. Ten domains today (health, medicine, finance, legacy, journal, calendar, tasks, faith, relationships, nutrition) ride the **same four generic tools** with **zero per-domain plumbing** in the CoS.
2. Tool domain-enums are **catalog-driven** (`constitution.py:448`, `domain_entity.py:94`, `domain_history.py:95`) — registering `entity_types` / `history_metrics` / `analysis_subjects` makes a domain reachable with **no CoS change**.
3. The `describe()` Entity Completeness Law is reusable and domain-owned; the generic `get_entity` composer holds no domain logic.

**Scalability test (objective 8) — PASSES as-is.** A future `Pets`, `Vehicles`, `Travel`, or `Home Maintenance` module becomes CoS-accessible by registering one `DomainTruth` subclass:

```python
@register_domain_truth
class PetDomainTruth(DomainTruth):
    domain = "pets"
    current_metrics = ("pet_count", ...)
    history_metrics = ("weight", ...)
    entity_types    = ("pet",)
    def current(self, m): ...
    def history(self, m, period): ...
    def describe(self, t): ...   # CompleteEntity per pet
```

…and adding its module to `_KNOWN_PROVIDER_MODULES`. Immediately: "Tell me about Charlie" (`get_entity`), "Show Charlie's weight history" (`get_history`), "What meds is Charlie on" (`describe`) all resolve with **no Chief-of-Staff modification.** The architecture is not the bottleneck — **coverage is.**

**Conclusion:** This is a validation-and-coverage milestone, not an architecture milestone. Do not replace `DomainTruth`. Do not rebuild routing.

---

## 3. Per-domain audit

Registered `DomainTruth` providers (auto-loaded): **health, medicine, finance, legacy, journal, calendar, tasks, faith, relationships, nutrition.**

| Domain | Registered | current | history | entity/`describe` | `describe_one` | Assessment |
|---|---|---|---|---|---|---|
| **health** | ✅ own module | 6 metrics (steps/sleep/weight/glucose/calories — *yesterday*-scoped) | steps, sleep, weight, workouts | `workout` (30d/20, exercise+set detail) | name/type only | **Partial** — strong core; no body-measurements, no BP, no time-of-day, no exercise-level lookup |
| **medicine** | ✅ own module | inventory+execution+profile+adherence (rich) | declared `adherence` but **raises KeyError** ⚠️ | medication/supplement/otc/wellness | any category | **Partial→strong** — best entity coverage; history bug; no "last dose" |
| **nutrition** | ✅ rollout | **none** (no `current()`) | **none** | `food` (recent 40, **no date filter**) | last match only | **Partial** — entity-only; no current/history; day-scoping left to model |
| **finance** | ✅ own module | net_worth, month_spending | **none** ("pending") | **none** | — | **Partial** — bills/transactions only via SAE `get_domain_state` blob |
| **legacy** | ✅ via `apps.py ready()` (⚠️ not in `_KNOWN_…`) | 4 counts | none (by design) | memory/person/place (rich) | **none** | **Partial** — no by-name lookup; `birth_date` hidden; reachability fragile |
| **journal** | ✅ rollout | days_since_entry, last_entry | none | `entry` (30d, body in extensions) | date **or** title | **Partial** — no topic/body search; no relative-date parse |
| **tasks** | ✅ rollout | overdue_count, tasks_due_today (*today*) | none | none | — | **Partial** — today-only; no window/entity/history |
| **calendar** | ✅ rollout | today_event_count, next_event (*today*) | none | none | — | **Partial** — today-only; no date filter/entity |
| **faith** | ✅ rollout | reading_streak, days_since_reading, unanswered_prayers | none | none | — | **Partial** — counts only; prayer list not an entity |
| **relationships** | ✅ rollout | neglected_count, birthdays_today | none | **none** | — | **Missing (records)** — aggregate counts only; no person retrieval |
| **purpose / goals / missions** | ❌ **not registered** | — | — | — | — | **Missing** — no provider anywhere; universal retrieval returns `unsupported_domain` |
| **people** (canonical identity) | ❌ **not in truth registry** | — | — | — | — | **Missing** — the designated sole Person authority exposes no truth surface; role resolvers inert in prod |
| **medical** (labs/vitals/providers) | ❌ no DomainTruth | — | — | — | — | **Missing (surfaces)** — reachable only via `get_domain_state("medical")` SAE blob |
| **documents** (scan/medical docs) | ❌ no domain at all | — | — | — | — | **Missing** — not in catalog/registry |
| **body measurements** (waist/arm/chest) | ❌ no exposure | — | — | — | — | **Missing** — `BodyMeasurementSession` model exists; zero truth-layer presence |

---

## 4. Certification — architecture → product

**Two certification systems exist:**

1. **Architectural layer certification** (`certification.py`) — proves capabilities exist (Freshness/Confidence/Stability/Current/History). Layer 1 = certified & frozen. This proves *APIs*, not *questions*.
2. **Per-question acceptance harness** (`acceptance_rules.py`) — a real question bank mapping customer questions → expected deterministic answers, organized by category (intent/truth/freshness/deterministic-retrieval/stability/regression), graded RED/YELLOW/GREEN, run through the **live chat path**. This is the correct instrument for the milestone — and it already exists.

**Two gaps make it not yet fit-for-purpose for bottom-up Truth Retrieval Certification:**

- **It tests the wrong runtime.** The harness drives `ChatGPTCoSService` (`acceptance_service.py:441`), whose tool registry has **no `get_entity` / `get_history` / `get_analysis`**. The current/target runtime — `ModelInterfaceService` — is where the full retrieval surface is live. **Certification is not exercising the surface the milestone cares about.**
- **The question bank is Health/Goals-weighted.** Effectively **zero** deterministic-retrieval questions for finance, life/tasks, documents, medical/labs, people. Non-health domains are not proven by question.

**There is no per-domain × per-question-type certification matrix yet.** Building that (against the ModelInterface runtime) is the core deliverable of "shift certification from architecture to product."

---

## 5. Coverage matrix (Certified / Partially Certified / Missing / N/A)

*Certification here = full retrieval surface **and** covered by a per-question suite pointed at the live retrieval runtime. By that definition nothing is fully Certified yet — the harness targets the old runtime. The column below rates retrieval-surface completeness; §4 is the harness gap that caps all of them.*

| Domain | Status | Evidence |
|---|---|---|
| Medicine | **Partially Certified** | rich current + entities; history bug; no last-dose |
| Health | **Partially Certified** | core current+history+workout entity; missing BP/body-meas/time-of-day/exercise-lookup |
| Journal | **Partially Certified** | entity describe; no topic search / relative-date |
| Legacy | **Partially Certified** | rich entities; no `describe_one`; fragile reachability |
| Nutrition | **Partially Certified** | entity-only; no current/history/date-filter |
| Finance | **Partially Certified** | 2 current metrics; bills/txns only via SAE blob |
| Tasks | **Partially Certified** | today-only current |
| Calendar | **Partially Certified** | today-only current |
| Faith | **Partially Certified** | counts only |
| Relationships | **Missing (records)** | aggregate counts; no person retrieval |
| Purpose / Goals / Missions | **Missing** | no provider — hard failure |
| People (identity) | **Missing** | canonical authority not in truth registry |
| Medical (labs/vitals) | **Missing (surfaces)** | SAE blob only, no entity/history |
| Documents | **Missing** | no domain |
| Body measurements | **Missing** | model exists, zero exposure |

---

## 6. Question-type certification matrix

| Question type | Supported | Partial | Missing / failing |
|---|---|---|---|
| **Current Fact** ("what do I weigh?") | health(core), medicine, finance, tasks/calendar/faith(scalars), legacy(counts) | glucose "this morning" (day-avg only) | body measurements, blood pressure, goals, people/person |
| **Historical Fact** ("what did I weigh July 4?") | health (weight/steps/sleep/workouts) | — | everything else (`history_metrics` empty for finance/nutrition/journal/tasks/calendar/faith/relationships); medicine declared-but-raises |
| **Latest** ("last workout / last meal") | health workout, nutrition (last match), medicine | bench-press / per-exercise latest (must scan 30d) | goals, labs |
| **Timeline** ("weight this month") | health (4 metrics) | — | all non-health domains |
| **List** ("meds / active goals") | medicine, legacy, journal, nutrition | faith (count, not list), tasks (count) | **goals/missions**, prayer contents, transactions, documents |
| **Count** ("how many workouts this week") | some current scalars (overdue, streak) | — | arbitrary windowed counts are not a surface anywhere |
| **Existence** ("have I ever eaten lasagna / journaled about anxiety") | — | nutrition (last-occurrence only, no all-time/count); | journal topic search (no `body__icontains`); most domains |
| **Comparison** ("which arm is larger / waist vs last month") | — | — | no comparison surface anywhere; **body measurements entirely absent** |

**Structural read:** the contract is strong on **Current** and (Health) **History/Timeline/Entity-list**; weak-to-missing on **history for non-health**, **date/window-scoped retrieval**, **existence/count**, **comparison**, and has **five whole missing domains** (goals, people, medical-labs, documents, body-measurements).

---

## 7. True gaps — smallest additive fixes (no redesign)

Ranked by trust impact. All are additive: register a provider, or add a surface to an existing one, or point the harness at the live runtime.

**Tier 1 — hard failures on required questions**
1. **Register a Purpose/Goals `DomainTruth`** — goals/missions currently return `unsupported_domain`. `apps/purpose/services/goal_queries.py` + `mission_link.py` already hold the truth; wrap them in `current()`/`describe()`. Add module to `_KNOWN_PROVIDER_MODULES`.
2. **Register a People `DomainTruth` with `describe_one(name)`** — the canonical identity authority is absent from the truth registry. Reuse `apps/people/services/resolution.py :: resolve()`. This resolves the 3-way Person authority split (people/relationships/legacy) at the retrieval seam and makes "Who is Emily?" / "Who is my sister?" answerable.
3. **Register a Medical `DomainTruth`** (labs/vitals/providers) with `describe()` + `history()` — data is composed in `build_medical_state` but has no entity/history surface ("trend my A1C" is unreachable).

**Tier 2 — thin providers missing obvious surfaces**
4. **Body measurements** — expose `BodyMeasurementSession` (waist/arm/chest) as health current metrics + a `measurement` entity; unlocks the whole **Comparison** column ("which arm is larger").
5. **Blood pressure** — add as a health current metric (data already collected).
6. **Nutrition `current()` + `history()` + date-filtered `describe()`** — daily totals and "today vs yesterday" should be deterministic, not model-inferred over a 40-row window.
7. **Finance `history()` + transaction/bill entities** — recent transactions and "bills due this week" are Layer-1 accessibility gaps today.
8. **Date/window scoping across tasks, calendar, journal, health** — "this week", "tomorrow", "Monday", "yesterday". Add relative-date resolution (journal's `describe_one` can't parse "yesterday") and window params. This is the single highest-leverage cross-domain fix — it lifts the entire **Timeline / Count / Historical** columns.
9. **Legacy `describe_one(name)`** + surface `birth_date` (not just `birth_year`).
10. **Faith prayer entity** (`describe("prayer")`) so the list, not just the count, is retrievable.

**Tier 3 — correctness / robustness (small)**
11. **Fix medicine `history()`** — it declares `history_metrics=("adherence",)` but raises `KeyError`. Introspection/behavior parity: implement it or drop the declaration. (`truth_catalog()` currently advertises a surface that fails.)
12. **Add `apps.legacy.services.legacy_domain_truth` to `_KNOWN_PROVIDER_MODULES`** — today reachability depends solely on `apps.py ready()` succeeding, and the registry's self-heal can't recover it.
13. **Documents `DomainTruth`** — lowest urgency; register when document Q&A becomes a target.

**Certification deliverable (objective 4)**
14. **Point the acceptance harness at the `ModelInterfaceService` runtime** (the one with `get_entity`/`get_history`), and **build a per-domain × per-question-type question bank** covering all eight categories for every domain. This is what turns "APIs exist" into "customer questions are proven."

**One strategic (non-additive) decision — RESOLVED by Phase 2 proof (see addendum below)**
15. **Runtime alignment.** Three runtimes coexist (`ModelInterface` / `ChatGPTCoS` / `LegacyBeth`, selected per-user in `cos_gateway/gateway.py:49`). Entity/history/analysis retrieval exists **only** in `ModelInterface`. **Phase 2 proof (2026-07-17) confirms the actual production customer runs on `ModelInterface`** (owner enabled via migration `0090`/`0091`), while the certification harness tests `ChatGPTCoS`. This is **Case A** — one production-authoritative runtime — so the fix is to align the harness to `ModelInterface`, not to consolidate runtimes. A rollout/flag matter, not an architecture change.

---

## 8. Constitutional check

- **WLJ owns deterministic truth; the model owns reasoning** — preserved. Every fix adds *truth surfaces*, none add WLJ reasoning.
- **One authority per truth domain** — the People provider (gap #2) *strengthens* this by resolving the Person authority split at the retrieval seam.
- **Reuse before rebuild / improve truth before adding intelligence** — every recommendation reuses an existing canonical query layer behind the existing contract.
- **No redesign** — the retrieval architecture is validated as correct and scalable; the work is coverage + certification, executed bottom-up.

---

---

## Phase 2 Addendum — Production Runtime Path Proof (2026-07-17)

Traced end-to-end against the repository (not inferred from class names). Five-way agreement established.

### CONFIRMED runtime facts (file:line evidence)

| # | Question | Answer | Evidence |
|---|---|---|---|
| 1 | Which service handles a normal production CoS message? | For the **owner (production customer)**: `ModelInterfaceService.generate` | `runtime.py:197`, dispatched by `ModelInterfaceRuntime` |
| 2 | How is the active service chosen? | `CoSGateway.resolve_runtime(user)` — precedence: `use_model_interface` → else `evidence_tools_enabled` (`use_chatgpt_cos` / global override) → else legacy | `gateway.py:48-63` |
| 3 | What flags/prefs alter the choice? | `UserPreferences.use_model_interface` (precedence), `use_chatgpt_cos`, `use_model_interface_writes` (read vs write), global `WLJ_COS_EVIDENCE_TOOLS_ENABLED` | `users/models.py:709-732`, `tool_registry.py` |
| 4 | Can different users reach different runtimes? | **Yes** — per-user flags. Owner = ModelInterface (via migration); flags-off users = LegacyBeth | `migrations/0090`, `0091`; `gateway.py:58-63` |
| 5 | Which runtime exposes the truth tools? | **ModelInterface only.** Model-facing tool names: `get_domain_state`, `get_history`, `get_entity`, `get_analysis`, `get_user_truth`, `get_foundational_health_facts`, `search_history` | `constitution.py:503-649`; dispatch `service.py:321-407` (`get_entity`→`get_domain_entity`, `get_history`→`get_domain_history`, `get_analysis`→analysis composer) |
| 6 | Which runtime does the acceptance harness exercise? | **`ChatGPTCoSService`** — hardwired, bypasses the gateway | `acceptance_service.py:441,462`, `svc.generate` `:337` |
| 7 | Does worker/queue change the path? | **Streaming** dispatches a Celery task (`run_model_interface_generation.delay`) → runs in the **worker** service; **non-streaming** runs synchronously in **web**. Same service class + tool surface either way | `runtime.py:162-201` |
| 8 | Streaming vs non-streaming parity? | **Same service, same tools** within a runtime; only the execution location differs (worker vs web) | `runtime.py:162` (stream) vs `:180` (sync) |
| 9 | Can fallback silently bypass the universal truth interface? | **Yes, structurally** — a user on `LegacyBethRuntime` (both flags off, the default) uses `PersonalAssistant.send_message`, which has **none** of the truth tools; `ChatGPTCoSRuntime` lacks `get_entity`/`get_history`/`get_analysis`. Not a fallback *within* ModelInterface, but a different runtime selection yields a materially different truth capability | `runtime.py:223-282`, `tool_registry.py` |

### Five-way trace (owner / production path)
`AssistantChatView`/`AssistantChatStreamView` (`views.py:997`, `:1269`) → `CoSGateway.respond` → `resolve_runtime` picks `ModelInterfaceRuntime` (owner `use_model_interface=True`) → `ModelInterfaceService.generate` tool loop (`service.py:321-407`) → `get_domain_entity`/`get_domain_history`/`get_domain_state` services → `DomainTruth.describe()/.history()/.state()` provider → `CompleteEntity`/`CurrentTruth` → final answer. **Agreement holds at every hop.**

### Phase 6 classification: **Case A — one production-authoritative runtime**
`ModelInterface` is the intended and effectively authoritative production path for the real customer (owner, via migration `0090`/`0091`; `use_model_interface` takes precedence). `ChatGPTCoS` and `LegacyBeth` remain as coexisting rollback / not-yet-migrated runtimes with a **documented capability gap** (no entity/history/analysis). Action per Case A: align the certification harness to `ModelInterface`; document the fallback capability gap; add regression protection so the harness cannot silently revert to the retired `ChatGPTCoS` path. **No broad runtime rewrite; no revival of retired in-process reasoning.**

### The certification gap (structural, confirmed)
The per-question harness runs on `ChatGPTCoS`, which **cannot** call `get_entity`/`get_history`/`get_analysis`. Therefore entity/history/analysis questions are **untestable on the harness today** even though they work on the owner's real runtime. This is the first thing Phase 3 must fix — point the harness at the production (`ModelInterface`) path.

### LIKELY gaps requiring further runtime proof (not yet confirmed at runtime)
- Whether `get_entity`/`get_history` return correctly-grounded answers for each domain **through a live model turn** (vs. the provider returning data) — this is exactly what the Phase 5 vertical slice will prove.
- Whether the medicine `history()` `KeyError` (confirmed at provider level, `medicine_domain_truth.py:118-120`) surfaces as a tool error or a silent empty in the ModelInterface loop — to be observed in the slice.

---

*Produced as a read-only audit + Phase 2 runtime proof. No production application code was modified. Implementation (Phase 3+) proceeds on the proven `ModelInterface` path, domain by domain, bottom-up.*
