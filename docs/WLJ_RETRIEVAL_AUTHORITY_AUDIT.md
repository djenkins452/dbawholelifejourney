# WLJ Retrieval Authority Audit — the permanent Retrieval Topology

**Date:** 2026-07-22
**Milestone:** Truth Retrieval Certification — Milestone 2 (**audit only; nothing eliminated**)
**Baseline audited:** `f7cad624` (HEAD — committed/deployable state). In-flight uncommitted work is listed separately in §8 and is **not** treated as the baseline.
**Governing principle:** optimize for **fewer deterministic authorities**, not fewer tools. Multiple tools are fine. Multiple authorities for the same truth are not.

> **The audit is the deliverable.** Once complete, elimination proceeds mechanically from this document rather than through further architectural investigation.

---

## 1. Deliverable 1 — Complete Retrieval Surface Inventory

Every surface that produces or exposes deterministic truth to the model. Three tiers: surfaces the model **calls**, surfaces **injected** into every turn without a tool call, and the **producer** layer beneath both.

### Tier A — Model-callable tools (the model chooses these)

| # | Surface | Purpose | Truth category | Canonical? | Produces | Projects | Computes | Delegates | Consumers | Implementation | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A1 | `get_history` | Aggregate/time-series over a period | Historical metric | **Yes** | Yes | No | Yes (aggregates) | `DomainTruth.history()` | model | `domain_history.py` | **Canonical** |
| A2 | `get_entity` | Record detail / list / by-name | Record | **Yes** | Yes | No | No | `DomainTruth.describe()` | model | `domain_entity.py` | **Canonical** |
| A3 | `get_analysis` | Composed evidence bundle for a subject | Analytical composition | No | No | Yes | No | reuses A1+A2 | model | `domain_analysis.py` | **Projection** (compliant) |
| A4 | `get_user_truth` | Durable explicit cross-domain facts | Personal truth | **Yes** (for durable facts) | Yes | Yes (of module facts) | No | module authorities | model + standing ctx | `personal_truth.py` | **Canonical + compliant projection** |
| A5 | `get_domain_state` | Module "now" summary | Domain summary | No | No | Yes (SAE snapshot) | No | `get_module_state` | model | `domain_state.py` | **Projection** (see §4 caveat) |
| A6 | `get_foundational_health_facts` | Convenience curated facts | Mixed (current + metric-on-day + medication + execution) | **No** | **Yes (some keys)** | Yes (some keys) | **Yes** | partially | model | `health_facts.py` + `fact_registry` | **⚠ Shadow Authority** |
| A7 | `search_history` | Keyword/substring search | Search | No | Yes | No | Yes | legacy `SearchService` | model | `history_search.py` | **⚠ Parallel registry** |

### Tier B — Context-injected surfaces (reach the model every turn, no tool call)

Assembled by `ModelInterfaceService.build_standing_context` (`service.py:121`). **The assembler owns nothing** — each field is an owned interface at its own freshness.

| # | Surface | Purpose | Truth category | Canonical? | Projects | Consumers | Implementation | Status |
|---|---|---|---|---|---|---|---|---|
| B1 | `current_context` | What the user is looking at now + clock + capability index | Situational | **Yes** (for "what page") | Yes | model | `current_context.py` + 15 `@register_page_summary` providers | **Canonical (situational)** |
| B2 | `personal_truth` | Durable explicit facts | Personal truth | shares A4's composer | Yes | model | `personal_truth.py` | **Compliant projection** (ONE composer feeds both) |
| B3 | `deterministic_understanding` | WLJ's *assessments* of facts | Assessment | **Yes** | Yes | model | `understanding.py` (cache-first; `interpret()`/`cos_intelligence`) | **Canonical (assessment tier)** |
| B4 | `current_action` | "What to do now" | Decision | **Yes** | No | model + dashboard | `decision_authority.current_action` | **Canonical** (CI rejects a 2nd selector) |
| B5 | `execution_state` | Day's execution facts | Execution | **Yes** | Yes | model | `execution_facts(user, state)` ← `build_execution_state` | **Canonical** |
| B6 | `missions` | Mission facts | Goal/mission | **Yes** | No | model | `mission_link.get_mission_map` | **Canonical** |
| B7 | `conversation_state` | What we're discussing / waiting on | Conversational | **Yes** | No | model | `conversation_state.py` | **Canonical** (explicitly *not* a retrieval surface; no tool) |
| B8 | `ai_relationship` | Relationship/persona config | Preference | No | Yes | model | `ai_relationship.py` | **Projection** |
| B9 | `pending_confirmations` | Open confirmations | Action state | **Yes** | No | model | `confirmation.list_open` | **Canonical** |
| B10 | `standing_context` | Always-loaded package | Composed context | No | Yes | CoS (ChatGPT runtime) | `standing_context.py` (projects `cos_context`/`executive`) | **Projection** |

### Tier C — Producer layer (beneath A and B; not model-facing)

| # | Surface | Purpose | Status |
|---|---|---|---|
| C1 | `DomainTruth` registry (`current/history/describe/analysis_subjects`) | **THE** canonical truth contract; catalog-driven | **Canonical contract** |
| C2 | Domain `*_queries.py` (`DailyHealthQueries`, `NutritionQueries`, `WorkoutQueries`, `MedicineQueries`, `sleep_queries`, `TaskQueries`, …) | Per-domain deterministic authorities | **Canonical producers** |
| C3 | SAE `state_engine.get_module_state` | Pre-computed module snapshots (request-path-safe substrate) | **Store** (not an authority) |
| C4 | `execution_facts.py` (`EXECUTION_FACT_KEYS`) | Curated "did I / what's on" keys | **Projection** (reads C1/C3) — watch for drift |
| C5 | Page summary registry (15 providers) | Overview-page summaries → B1 | **Projection** (contract mandates ONE shared builder feeds page + provider) |
| C6 | `history_search` → legacy `SearchService` | Keyword engine, **separate registry from C1** | **⚠ Parallel registry** |
| C7 | `current_focus_store.py` | Focus persistence | Support |
| C8 | `metric_date.py` — *in-flight, uncommitted* | Date-scoped metric authority | **See §8** |

---

## 2. Deliverable 2 — Retrieval Authority Topology (question-level)

The permanent topology. Each row is proven at runtime (six-question trace `952598ba`; weight-yesterday trace 2026-07-22).

```
Question → Tool Selected → Retrieval Surface → Canonical Authority → Truth Producer → Presentation
```

| Question | Tool selected | Retrieval surface | Canonical authority | Truth producer | Verdict |
|---|---|---|---|---|---|
| **current weight** | `get_foundational_health_facts(current_weight)` | A6 | *(none designated)* | **SAE snapshot** `health.weight_current` | ❌ **Shadow** — envelope-less, not date-scoped; reported a 105-day-old value as current |
| **weight on July 4** | `get_history(period="July 4")` | A1 | `get_history` | `WeightEntry` via `HealthDomainTruth.history` | ✅ **Correct** (fixed in M1 `f7cad624`) |
| **protein yesterday** | `get_foundational_health_facts(protein_today)` | A6 | *should be* `get_history` | SAE `nutrition.daily_protein_g` | ❌ **Shadow** — false 0 g; live authority holds 75 g |
| **latest blood pressure** | `get_foundational_health_facts(last_blood_pressure_reading)` | A6 | **`get_history(bp_systolic/diastolic/pulse)`** *(corrected)* | SAE `health.bp_systolic` | ❌ **Missing Projection** — authority exists and works; the curated key does not delegate (see §3.5 correction) |
| **last pizza** | `get_entity(nutrition, meal, contains=pizza)` | A2 | `get_entity` | `NutritionQueries` → `FoodEntry` | ✅ **Correct** |
| **calf raises** | `get_entity(health, workout, period=yesterday)` | A2 | `get_entity` | `WorkoutQueries.describe` → `WorkoutSession/Exercise/Set` | ✅ **Correct** |
| **current mission** | `get_user_truth(section=goals)` | A4 | `personal_truth` | `LifeGoal(is_primary_mission)` | ✅ **Correct** (latent dup: `top_goal` in A6) |

---

## 3. Deliverable 3 — Authority Classification Matrix

Every exposed value classified as **exactly one** of the five conditions.

### 3.1 Canonical Authority (owns truth, may be referenced)
`get_history` (aggregate/period) · `get_entity` (record detail) · `personal_truth`/`get_user_truth` (durable explicit facts) · `decision_authority.current_action` · `execution_facts`/`build_execution_state` · `mission_link` · `conversation_state` · `current_context` (situational) · `understanding` (assessment tier) · `DomainTruth` + domain `*_queries` (producers).

### 3.2 Projection (delegates; never computes, snapshots, defaults, or disagrees)
`get_analysis` (reuses A1+A2 — compliant) · `personal_truth` standing view (**ONE composer** shared with the tool — compliant) · page summaries (contract mandates one shared builder — **compliant by contract, unverified per-page**) · `ai_relationship` · `standing_context` · `execution_facts` curated keys.

### 3.3 Shadow Authority (independently computes/stores truth owned elsewhere — **defects**)

| Shadow | Owned elsewhere by | Evidence | Class |
|---|---|---|---|
| `get_foundational_health_facts` **metric-on-a-day keys** (`protein_today`, `calories_yesterday`, `steps_yesterday`, `weight_yesterday`, …) | `get_history` / date-scoped authority | protein → false **0 g** vs live 75 g (runtime) | **D2** |
| `get_foundational_health_facts` **`current_weight`** (A2) | date-scoped weight authority | **envelope-less**, not date-scoped, snapshot-backed; reported 105-day-old value as current | **D2** |
| `DailyHealthQueries.weight_on` **carry-forward** (A1) vs `get_history` **windowed** (A3) | one date-scoped semantic | A1 → `298.3 "yesterday"`, A3 → `empty`, same instant, **no model involved** | **D2** |
| `get_foundational_health_facts` `top_goal` | `personal_truth` / goals | both answer "my mission" | **D2 (latent)** |
| `search_history` | `get_entity(contains=)` | separate registry from `DomainTruth`; drifts | **D2 (latent)** |

### 3.4 Missing Projection (canonical authority exists; nothing exposes it)
- **Body measurements / waist** — `question_specs` + fixtures certify them; verify a model-reachable surface advertises them.
- **Sleep stage/efficiency detail** — `sleep_queries` is canonical; confirm entity exposure.
- **Medical labs history** — `LabResult` authority exists; `get_history` exposure unconfirmed.
- *(Each requires a one-line capability-index check to confirm; listed as candidates, not asserted.)*

### 3.5 Missing Authority (no canonical deterministic owner at all)
- ~~**Blood pressure**~~ — **❌ CORRECTED 2026-07-23 (this entry was WRONG).** BP is **Missing Projection**, not Missing Authority. This audit probed the metric name `blood_pressure` (which does not exist) and read a **truncated** `supported_metrics` list. The real metrics are **`bp_systolic` / `bp_diastolic` / `bp_pulse`**, all registered health history metrics that return `ready` with units, and both `metric_on_date` and `latest_observation_on_or_before` resolve them. A canonical authority **does** exist; only the projection is missing (`last_blood_pressure_reading` still reads the SAE snapshot). See `WLJ_RETRIEVAL_AUTHORITY_VERIFICATION.md` §5. **Lesson: a metric-name miss is not an absent authority — always enumerate `supported_metrics` in full before classifying.**
- **Arbitrary windowed counts** ("how many X this week") — no surface owns this generally.
- **Cross-domain comparison** — no comparison authority.

> **Missing Projection ≠ Missing Authority.** Blood pressure proved the distinction: a projection fix (delegating A6 → `get_history`) is a *no-op* for BP because the target does not exist. Conflating them produces plans that cannot work.

---

## 4. Deliverable 4 — Constitutional Audit ("owns truth, or merely exposes it?")

For each projection: does it **delegate**, and can it **drift / compute / disagree**?

| Surface | Delegates? | Can drift? | Can compute? | Can disagree? | Verdict |
|---|---|---|---|---|---|
| `get_analysis` | ✅ reuses A1+A2 | No | No | No | **Compliant projection** |
| `personal_truth` standing view | ✅ same composer as tool | No | No | No | **Compliant projection** |
| Page summaries | ✅ by contract (one shared builder) | **Possible if a page re-derives** | — | — | **Compliant by contract; per-page verification outstanding** |
| `get_domain_state` | ✅ reads SAE only | **Yes — a populated-but-stale snapshot is never refreshed by a read** | No | **Yes** (vs live authority) | **Projection with a freshness defect** |
| `get_foundational_health_facts` | ❌ **partially** | **Yes** | **Yes** | **Yes (proven)** | **⚠ SHADOW AUTHORITY** |
| `search_history` | ❌ separate registry | **Yes** | Yes | Yes | **⚠ Parallel registry** |
| `standing_context` | ✅ projects `cos_context` | Cache-pending only | No | No | **Compliant projection** |

**The single structural finding:** a projection is only safe if it *cannot* answer independently. `get_foundational_health_facts` answers from its own curated key map with its own contracts and its own store — so it is an authority wearing a projection's name. `get_domain_state` is a genuine projection, but its substrate (SAE) has no read-time freshness guarantee, so it can silently disagree with a live authority.

### 4.1 Audit-layer finding (blocks certification of everything above)
- **Values are not recorded.** For `get_foundational_health_facts`, `result_digest` stores only `{"keys": [...]}` — never the returned values. `ToolCallLog`'s stated purpose ("what truth was provided?") is unmet for the most-used health tool.
- **`turn_id` is not per-turn.** `turn_id = request_id or f"conv-{conversation.id}"`, and the production gateway passes **no** `request_id` → every turn in a conversation shares one id. *(Independently corroborated: my six-question harness used a fresh conversation per question, which is the only reason those traces were cleanly separable.)*
- **Consequence:** this entire class is currently **undetectable in production**. Certification (Milestone 4) depends on fixing this.

---

## 5. Deliverable 5 — Shadow Authority Elimination Plan *(plan only; nothing eliminated)*

Ordered so each step is mechanical and independently verifiable.

1. **Designate ONE date-scoped metric authority** answering "metric X on date D" for every consumer. *(Implementation already in flight — §8.)*
2. **Resolve the carry-forward contract once, explicitly.** A1 carries forward indefinitely; A3 does not. Pick one semantic; make the other conform. If carry-forward survives, `exact:false` must be **structurally un-ignorable**, not an optional field.
3. **Reduce `get_foundational_health_facts` to a pure projection** — every metric-on-a-day and current-value key delegates to (1); derive the key set from `history_metrics × periods` so it can never again be incomplete or asymmetric. **No key may compute, snapshot, or default.**
4. **No health fact without an envelope.** `current_weight` must carry `freshness`/`confidence`/`as_of` like its peers; a snapshot-sourced fact must degrade honestly rather than present as current.
5. **Collapse `top_goal`** into `personal_truth` (mission identity) vs goals SAE (progress).
6. **Resolve `search_history` vs `get_entity(contains=)`** to one substring/keyword authority.
7. **Fix the audit layer** (record values; per-turn `request_id`) — prerequisite for Milestone 4.

**Explicitly out of scope here:** blood pressure. It is **Missing Authority**, not shadow; steps 1–4 cannot fix it. → Milestone 3.

---

## 6. Deliverable 6 — Missing Projection / Missing Authority Inventories
See §3.4 (Missing Projection — candidates requiring a capability-index check) and §3.5 (Missing Authority — BP **proven**, plus windowed counts and comparison).

---

## 7. Deliverable 7 — Recommended implementation order

| Order | Work | Class | Gate |
|---|---|---|---|
| 0 | **Converge with the in-flight session** (§8) before any elimination | — | avoids duplicate authorities being *created* |
| 1 | Audit layer: record values + per-turn `request_id` | detection | makes 2–5 verifiable in prod |
| 2 | One date-scoped metric authority + explicit carry-forward semantic | D2 | §5.1–5.2 |
| 3 | `get_foundational_health_facts` → pure projection; envelope on every fact | D2 | §5.3–5.4 |
| 4 | Blood-pressure authority investigation → expose existing authority | **D3** | Milestone 3 |
| 5 | `top_goal` + `search_history` collapse | D2 latent | §5.5–5.6 |
| 6 | Single-authority certification gate | certification | Milestone 4 |

---

## 8. In-flight concurrent work (NOT in the audited baseline — flagged, untouched)

A parallel session is implementing in exactly this territory. **Nothing below was staged, committed, or modified by this audit.**

| Path | State | Relevance |
|---|---|---|
| `apps/ai/cos_services/metric_date.py` | **untracked (new)** | The Date-Scoped Metric Authority — implements §5.1/§5.2 (`metric_on_date` = `exact_date`, explicit carry-forward semantics) |
| `apps/ai/cos_services/health_facts.py` | modified | Delegating day-keys to `metric_date` — implements §5.3 |
| `apps/health/services/daily_health_queries.py` | modified | A1 carry-forward contract |
| `apps/ai/migrations/0037_toolcalllog_conversation_id_and_more.py` | untracked | Audit layer — implements §4.1/§7.1 |
| `apps/ai/{models,cos_services/audit,model_interface/service,model_interface/conversation_state}.py` | modified | Audit ledger + subject anchoring |
| `apps/ai/tests/test_metric_date_authority.py`, `test_truth_subject_anchoring.py` | untracked | Their coverage |
| `docs/WLJ_WEIGHT_YESTERDAY_INVESTIGATION.md` | untracked | Runtime proof of the 4-authority weight divergence (§3.3) |

**Baseline integrity:** HEAD's `health_facts.py` does **not** import `metric_date`, so the committed/deployed state is self-consistent — there is no production `ImportError` risk from the untracked file.

**Consequence for Milestone 2:** §5 steps 1–3 are **already being implemented** by that session. This audit should be used to *verify* their result against the classification matrix, not to re-implement it.

---

## 9. Constitutional check
- **WLJ owns truth; the model reasons** — unchanged; this audit adds no capability.
- **One authority per truth** — the audit's entire purpose; §3.3 enumerates the current violations with runtime evidence.
- **Optimize for fewer authorities, not fewer tools** — honored: `get_analysis`, `get_user_truth`, and page summaries are *kept* as compliant projections; only independently-computing surfaces are marked for elimination.
- **Nothing eliminated in this milestone** — audit only, per instruction.

---

*Baseline `f7cad624`. Tier A/B inventories read directly from `constitution.py` (tool schemas) and `service.py:121` (context envelope). Topology rows are runtime-proven (`952598ba` six-question trace; 2026-07-22 weight-yesterday trace). No production code modified by this audit.*
