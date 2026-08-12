# WLJ Chief of Staff — Truth Access Architecture Investigation

**Type:** Investigation only. No production behavior changed. No code modified. No Constitutional change proposed.
**Date:** 2026-08-12
**Author:** Claude (Chief Architect seat)
**Runtime evidence:** production `cos-run` (real `ModelInterfaceRuntime` + gpt-4o) single-turn and multi-turn (`?script=`) probes; `truth-probe`; local capability-registry + capability-index introspection; code trace of the tool loop. Web+worker aligned on `f7c2da68`.
**Governing docs obeyed:** WLJ Constitution (I–V), `01_READ_FIRST…ARCHITECTURE`, `03_ENGINEERING_OPERATING_GUIDE`, `04_DANNY_WORKING_PREFERENCES`, `WLJ_TRUTH_SURFACES.md`, `WLJ_RETRIEVAL_PLATFORM_CERTIFICATION.md`, `WLJ_COS_MODEL_ON_TRUTH_ASSESSMENT.md`.

---

## 1. Executive conclusion

**The architecture Danny is describing — "OpenAI as Chief of Staff sitting directly on top of WLJ's enterprise personal-truth platform" — is roughly 90% present in the running system, and closer than expected.** The central question of this investigation — *can the model efficiently discover and access the complete deterministic truth WLJ possesses, at whatever detail the conversation requires, without WLJ predetermining what matters?* — is answered **largely yes, with four specific, bounded gaps**, none of which requires a new subsystem, a reasoning engine, or a Retrieval-Platform redesign.

The runtime already does the thing the North Star asks for:

- **Model-directed retrieval is real and working.** For "How am I doing overall?" the model itself chose six life domains (health, finance, relationships, tasks, goals, life), requested them **in a single reasoning round** (parallel tool-calling), and synthesized its own verdict. WLJ did **not** decide which domains mattered. (§10)
- **The capability index IS the model's map of the truth platform** — a compact, plain-language catalog of every answerable (domain, metric/entity/subject) tuple, catalog-driven so a new registration self-advertises. (§7)
- **Latency is not the feared problem.** The 35–45 s concern **did not reproduce**: measured end-to-end was ~5–7 s for single-domain answers and **~11 s for a six-domain whole-life synthesis**. (§13)

The four bounded gaps, in descending trust impact:

1. **Broad-answer continuity breaks (Working Context).** A follow-up to a *multi-domain* synthesis — "Why do you think that?" — **lost the thread** and asked the user to clarify. Root cause is deterministic and precise: `conversation_state.active_subject` is **single-subject, last-retrieval-wins**, so a six-analysis synthesis leaves only the *last* domain as the referent. Single-subject follow-ups ("weight loss → why slowing?") work perfectly. (§12)
2. **Three narrow truth-exposure gaps** where user-facing truth EXISTS but the model is blind to it: **Finance has no record-level entity** (transactions/accounts unreachable), **Projects exposes task *counts* but not the task records**, **Relationships has no history/trend** despite holding the cleanest dated series in WLJ (`RelationshipInteraction`). All are "expose existing truth via the existing `DomainTruth` pattern," not new architecture. (§8, §9, §12)
3. **A residual over-steer of the same class we just fixed:** proactive-framed and execution-phrased follow-ups ("Is there anything you'd proactively bring up?", "What should I focus on most there?") still collapse onto `current_action` ("write in your journal") with zero retrieval. (§10, §20)
4. **Serial tool dispatch** — the model batches its requests into one round, but WLJ executes them **serially** (`for tc in tool_calls`), so a six-domain answer runs six heavy live `get_analysis` calls back-to-back. This is a latency *optimization opportunity*, not a correctness defect. (§14)

**The headline:** WLJ is already a good enterprise truth platform for the model to reason over. The next work is **completing truth access (exposure) and fixing broad-answer continuity**, not building intelligence. Truth first, exactly as Danny framed it. All four gaps are inside the Constitution (§23).

> One line: **The model already reasons over WLJ's truth and picks its own evidence. What remains is to stop it going blind in three specific corners, and to let a broad answer survive the next question.**

---

## 2. Product north star (restated, as the yardstick)

WLJ = the deterministic enterprise truth platform for one life (canonical truth, common definitions, deterministic calculations, history, records, provenance, freshness, integrity, state, actions, efficient storage/retrieval). The conversational model = the Chief of Staff that reasons, interprets, synthesizes, judges, prioritizes, advises, **decides which truth matters and when it needs more**, asks questions, and holds the relationship. *The model reasons. WLJ knows.* No deterministic function for a judgment the model should make. This investigation measures the running system against exactly that division.

---

## 3. Current real runtime architecture

Traced end-to-end (not from docs):

```
User turn
 → CoSGateway.respond(surface="chat")                         apps/ai/cos_gateway/gateway.py
 → ModelInterfaceRuntime  (Danny: use_model_interface=True)   apps/ai/cos_gateway/runtime.py
     · deterministic typed-confirmation short-circuit (no model call)
     · multimodal ingest (artifacts + perception frames)
 → ModelInterfaceService.generate()                           apps/ai/model_interface/service.py
     1. build_standing_context()  → the Executive Context Envelope (§4/§5)
     2. _system_prompt() = CONSTITUTION + 6 salience leads + JSON(standing_context)
     3. all_tools() = 12 truth tools + 6 write intents + 3 flow tools
     4. AIService._call_api_with_tools()  → the OpenAI tool loop      apps/ai/services.py:685
          for round in range(max_tool_rounds+1):     # model_interface budget = (7, 3500)
             one model call → if tool_calls: execute them SERIALLY (line 835) → append → continue
             else: final answer (empty-final → one bounded synthesis retry)
          · each truth read wrapped in the canonical envelope + AUDITED (ToolCallLog)
          · each retrieval deterministically sets active_subject (last-wins) in conversation_state
 → CoSResponse(text, meta{tools_called, turn_id})
```

This is a faithful realization of the Constitution: one author (the model), deterministic tools, full audit, no reasoning engine in WLJ. The model drives; WLJ answers.

---

## 4. Standing Personal Context — as built

The "establish once → the CoS knows it until it changes" experience is **already delivered**, assembled fresh every turn from owned interfaces (the OpenAI API is correctly assumed stateless — WLJ re-supplies it):

| Standing element | Source | Cadence |
|---|---|---|
| AI relationship (name, default relationship, style) | `get_ai_relationship` | slow projection |
| Personal Truth (nutrition targets, restrictions/allergies, conditions, meds, active goals/priorities, coaching style) | `personal_truth.py` (one composer → standing block + `get_user_truth`) | cache-first |
| Missions / goals (full mission facts) | `get_mission_map` | per turn |
| Deterministic Understanding (whole-life assessment) | `understanding.py` (legacy heuristic pipeline) | cached 150 s |
| Executive read (`current_action`) | Decision Authority | per turn |

**Assessment:** authoritative, efficient (cache-first), and reasonably complete for durable personal truth. It is a genuine "standing context." The one caveat, already recorded in `WLJ_COS_MODEL_ON_TRUTH_ASSESSMENT.md §11`, is that `deterministic_understanding` runs on the legacy heuristic pipeline rather than the certified authorities — **but the prior milestone proved that is not currently contaminating answers** once the over-steer was removed (the model grounds on live `get_analysis`). No action here.

---

## 5. Working Context — as built

"What's happening now" is delivered by three complementary, already-built mechanisms carried inside the same envelope (no separate memory system):

- **Current Context** — the page/workspace the user is on (`current_screen.location` + `focus`), resolved canonically (Article II).
- **Conversation State** — `active_subject`, active artifacts, `guided_review`, pending confirmations — "what we're discussing / waiting on." Carried as an envelope field, not a retrieval surface.
- **Conversation history** — the last 12 user/assistant turns (`load_conversation_history`), reused as the model's short-term memory.

**Assessment:** the mechanisms exist and are correct in shape. **The one real defect is in Conversation State's `active_subject` model:** it is **single-subject and last-retrieval-wins** (`conversation_state.record_turn`, confirmed at `service.py` turn-capture + `conversation_state.py:242`). This is fine for a focused conversation (weight → "why slowing?") but **structurally cannot represent "the multi-domain assessment we just produced,"** which is what breaks broad-answer continuity (§12). This is a Working-Context limitation, not a truth or reasoning gap.

---

## 6. Deep Truth access — as built

The full deterministic corpus is reached through **12 truth tools**, discovered via the capability index (§7), retrieved on demand — never injected wholesale. The tools already support the drill-through the North Star requires:

`get_domain_state` (current) → `get_history` / `get_comparison` / `get_adherence` (aggregates/trends) → `get_readings` / `get_event_frequency` (intra-day + event trends) → `get_entity` (individual records) → `get_analysis` (the one-call investigation bundle: trends + all-time span + record detail + `holds_data`) → `search_history` (content search) → `get_user_truth` (durable profile) → `get_execution_review` (a day's intended execution).

**Assessment:** this is a strong, progressively-explorable Deep-Truth surface, and the Retrieval Platform behind it is certified permanent infrastructure. The drill-through path (summary → history → entities → analysis) is architecturally present and works in practice (§11). The gaps are **coverage** (three domains under-expose, §8) not **mechanism**.

---

## 7. The capability/truth map supplied to the model

Every turn, Current Context carries a `capabilities` block — the model's **map of WLJ**. Introspected live (commit `f7c2da68`), it advertises, per domain, exactly what is answerable:

- `answerable_domains` (20): artifacts, brain_training, calendar, capture, events, faith, finance, goals, habits, health, journal, legacy, meals, medical, medicine, notes, nutrition, projects, relationships, tasks
- `truth_history` (12 domains) — e.g. **health** exposes 38 metrics (weight, body-fat, glucose, BP, sleep, steps, HR, RHR, SpO2, all circumferences, workouts…), **finance** (income/spending/net_cashflow), **nutrition** (calories/protein/carbs/fat/fiber/sugar), goals, habits, tasks, faith, medical, medicine, calendar, journal, brain_training
- `truth_readings` (health: glucose/BP/HR/SpO2/temperature) · `truth_event_frequency` (health: glucose) · `truth_adherence` (nutrition 7 metrics, health steps/water)
- `truth_entities` (19 domains) — incl. **medicine → medication, otc, supplement, wellness**; health → 11 record types; nutrition → food/meal/frequent_food; faith → 8; meals → 6; legacy → memory/person/place; **projects → project**; **relationships → person**
- `truth_analysis` (14 domains, each with subjects + `overall`) — health has 19 analysis subjects; nutrition 20; faith 14; journal 15
- `domain_semantics` — per-domain meaning/purpose/boundary, so the model routes by MEANING (nutrition vs meals) not name.

**Assessment:** this IS the compact, understandable map the North Star (§10 of the prompt) asks for, and it is catalog-driven — a new registration self-advertises. **The map's coverage gaps ARE the truth-access gaps** (§8): projects advertises only `entity:project`, finance advertises no entity, relationships advertises no history. The model cannot request what the map does not show — so closing the gaps is a matter of registering the truth, which makes it appear in the map automatically.

---

## 8. Truth Accessibility Matrix (model's perspective)

Live registry + a dedicated model-vs-UI exposure audit. ✓ = the model can retrieve it today.

| Domain | State | History/Trend | Entity/Records | Analysis | Readings | Adherence | Search | Primary exposure gap (first failing layer) |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|---|
| Health | ✓ | ✓ (38) | ✓ (11) | ✓ (19) | ✓ | ✓ | — | — |
| Nutrition | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | — |
| Medicine / **Supplements** / OTC | ✓ | ✓ (adherence) | ✓ (medication, otc, **supplement**, wellness) | ✓ | — | — | — | — (supplement records ARE reachable) |
| Medical / Labs | ✓ | ✓ (lab_value) | ✓ (document, lab_panel, lab_result) | ✓ | — | — | — | — |
| Faith | ✓ | ✓ | ✓ (8) | ✓ (14) | — | — | ✓ | — |
| Journal | ✓ | ✓ (mood) | ✓ (entry) | ✓ (15) | — | — | ✓ | — |
| Goals / Missions | ✓ | ✓ | ✓ | ✓ | — | — | ✓ | — |
| Tasks | ✓ | ✓ | ✓ | ✓ | — | — | ✓ | — |
| Habits | ✓ | ✓ | ✓ | ✓ | — | — | — | — |
| Calendar | ✓ | ✓ | ✓ | ✓ | — | — | — | — |
| Brain Training | ✓ | ✓ | ✓ | ✓ | — | — | — | — |
| Meals (supply) | ✓ | — | ✓ (6) | — | — | — | — | supply domain by design; consumption = Nutrition |
| **Finance** | ✓ | ✓ (income/spend/net) | **✗** | ✓ (overall) | — | — | ✓ | **missing-entity-exposure** — no transaction/account/category/budget record is reachable; only aggregates |
| **Relationships / People** | ✓ | **✗** | ✓ (person, rich footprint) | ✓ (state overview) | — | — | ✗ | **missing-history-exposure** — `RelationshipInteraction` is a clean dated series but no trend/comparison surface |
| **Projects** | ✗ | ✗ | ◐ (project + task **counts**, not task records) | ✗ | — | — | — | **missing child-entity + missing-analysis** — task records and portfolio assessment unreachable |
| Legacy | ✗ | ✗ | ✓ (memory/person/place) | ✓ (overall) | — | — | ✗ | no state summary (low impact) |
| Capture / Notes | ✓ | ✗ | ✓ | ✗ | — | — | ✓ | no analysis over captures (low impact) |

**Do not equate "provider exists" with "model can use it."** The three highlighted rows are exactly where a user-facing truth exists but the model is blind (§9).

---

## 9. Known inaccessible-but-existing truth (audited, file-level)

A dedicated audit compared canonical models → app UI → CoS exposure for the three residuals. All three are confirmed and sharpened:

- **Finance (`missing-entity-exposure`).** `apps/finance/models.py` holds `Transaction` (date/amount/category/account), `FinancialAccount` (balances), `TransactionCategory`, `Budget`, `RecurringTransaction` — all with full CRUD UI (`apps/finance/views.py`). The CoS provider (`finance_domain_truth.py`) declares `history_metrics` + `current_metrics` but **no `entity_types`**. The model can say "spending rose 54.8%" but cannot answer "what did I spend at Costco last week", "list my accounts", or "my Dining budget vs actual." Aggregates yes; the records behind them, no.
- **Projects (`missing-truth child-entity` + `missing-analysis`).** `apps/life/models.py` `Project` has `status`/`target_date`/`is_overdue`, and child `Task` records (`completion_status`, `due_date`, `completed_at`); `ProjectDetailView` shows the full task list. But `project_domain_truth.py` exposes `entity_types=("project",)` with only task **counts** in `standing`, `history_metrics=()`, and one `current_metric` (below the ≥2 analysis threshold). The model cannot answer "what's left on the kitchen remodel", "which task is overdue", or "how are my projects going."
- **Relationships (`missing-history-exposure`).** `apps/relationships/models.py` `RelationshipInteraction` is a genuine dated series (`interaction_date`, indexed), and `PersonDetailView` shows interaction analytics. `RelationshipDomainTruth` exposes `person` entity + 4 `current_metrics` but **no `history_metrics`/`analysis_subjects`**, so `get_analysis('overall')` is a current-state snapshot only. The model cannot answer "am I connecting with people more or less than three months ago" or "how many times did I see Heather this quarter" — the exact **drift-detection** Danny wants most, over the cleanest series WLJ owns.

**Cross-cutting pattern:** Projects and Finance are mirror-image gaps (Projects has entity-not-aggregate; Finance has aggregate-not-entity). All three are closed by *registering existing truth* in the existing `DomainTruth` pattern — pure exposure.

---

## 10. Model-directed retrieval behavior (runtime-proven)

The North Star responsibility boundary — *the model decides what it needs; WLJ fulfills deterministic requests* — is **substantially present**:

- "How am I doing overall?" → the model chose **6 `get_analysis` calls across 6 domains it selected itself** (health/finance/relationships/tasks/goals/life) and synthesized. WLJ did not choose the domains.
- "How is my overall health?" → the model chose `get_analysis('health','overall')` and interpreted body-composition, glucose, sleep.
- "How is my weight loss going?" → one focused `get_analysis`; "What did I weigh a month ago?" → one `get_history`. Retrieval scales to the question.

**One residual, runtime-proven:** proactive-framed and execution-phrased questions still collapse onto `current_action` with **zero retrieval**:
- "Is there anything you're seeing that you'd proactively bring up?" → "write in your journal."
- "What should I focus on most there?" (after a health assessment) → "write in your journal."

This is the **same class** as the Executive Over-Steer defect fixed last milestone — the narrowed `_executive_lead` still captures these phrasings into its execution/current_action bucket. It is bounded and now has runtime evidence, but per discipline is **reported, not fixed here** (§20).

---

## 11. Drill-down behavior

Drill-through works when the subject is singular. "How is my weight loss going?" (→ `get_analysis`) followed by "Why might it be slowing?" produced a **second, deeper `get_analysis`** and a genuine trend analysis (weight path Aug 6→11, slowdown reasoning). The model re-retrieves at greater depth when its reasoning needs it — the summary→history→detail path is real. The failure mode is not drill-down per se; it is drill-down **after a multi-domain synthesis**, which is a continuity problem (§12), not a tool problem.

---

## 12. Follow-up / continuity behavior (a real defect)

Multi-turn probes, per-turn tool attribution captured:

| Turn 0 | Turn 1 | Turn-1 tools | Result |
|---|---|:--:|---|
| How is my weight loss going? | Why might it be slowing? | `get_analysis` | ✓ re-retrieved + reasoned (single subject anchored it) |
| How am I doing overall? | Why do you think that? | **(none)** | ✗ "If you could provide more context or specify what you're referring to" |
| How is my overall health? | What should I focus on most there? | **(none)** | ✗ "write in your journal" (current_action) |

**Root cause (deterministic, located):** `conversation_state.active_subject` is **single-subject, last-retrieval-wins**. A six-analysis synthesis leaves only the *last* domain as the active subject, so "Why do you think that?" has no coherent referent and the model deflects. When there IS a single clear subject (weight), continuity is excellent. The third case is the §10 over-steer residual ("what should I focus on" → current_action).

**Classification:** first failing layer = **Layer 1 Working Context** (Conversation State cannot represent "the multi-domain assessment we just produced"). This is high-impact — it breaks continuity on exactly the broad, synthesized answers the last milestone just unlocked, and Danny explicitly prizes follow-up continuity. It is *not* a latency or truth defect.

---

## 13. Latency decomposition (measured)

End-to-end via `cos-run` (includes Celery queue pickup + 2 s poll quantization — so these are **upper bounds**, real model time is lower):

| Class | Question | Latency | Tools | Rounds (inferred) |
|---|---|:--:|:--:|:--:|
| Trivial | "hi" | ~7 s | 0 | 1 |
| Simple lookup | "What did I weigh a month ago?" | ~7 s | 1 (`get_history`) | 2 |
| Focused | "How is my weight loss going?" | ~5 s | 1 (`get_analysis`) | 2 |
| Whole-health | "How is my overall health?" | ~7 s | 1 (`get_analysis` health/overall) | 2 |
| Whole-life | "How am I doing overall?" | **~11 s** | 5–6 (`get_analysis` ×N) | 2 |

**Structural decomposition** (from the tool-loop code): a turn cost ≈ `Σ(model round-trip) + Σ(serial tool executions)`. The model **batches** all its requests into one assistant message (parallel tool-calling), so even a six-domain answer is **2 model rounds** (fan-out round + synthesis round), NOT six. Each round re-sends the ~60 k-char system prompt + accumulating tool outputs. The retrieval portion is **N heavy live `get_analysis` calls run back-to-back** (serial, §14).

**Finding: the feared 35–45 s did not reproduce.** Worst measured case is ~11 s (queue-inflated). Latency is currently acceptable and conversational. It will grow with (a) more domains fanned out and (b) heavier per-domain data — so the serial-dispatch optimization (§14) is a **reserve lever**, not an urgent fix.

---

## 14. Sequential vs parallel retrieval

**The model parallelizes; WLJ serializes.** The model emits multiple tool calls in one assistant message (OpenAI parallel tool-calling), but the tool loop executes them in a plain `for tc in tool_calls:` loop (`apps/ai/services.py:835`) — **one dispatch after another, no concurrency**. So the six independent `get_analysis` calls of a whole-life answer run sequentially. Because they are independent domain reads, they are embarrassingly parallelizable. **This is the single highest-leverage latency optimization available** (concurrent dispatch of independent tool calls within a round), and it is purely an execution detail — it changes no truth, no ownership, no tool contract. Hold it in reserve until latency warrants it.

---

## 15. Caching / precomputation findings

- **Cached:** `deterministic_understanding` (150 s TTL, background warm), standing context, Personal Truth (cache-first), Current Context (fast baseline). These keep the *standing envelope* cheap.
- **Live-composed every call (NOT cached):** `get_analysis`, `get_history`, `get_entity`, and the other truth tools compose deterministically on each request. For a whole-life answer that means 5–6 live heavy composes back-to-back.
- **Assessment:** the standing envelope is well-cached; the *retrieval* surface is fully live. This is defensible (freshness), and per request-path-safety these run in the worker, not the web path. If latency grows, the levers are: (a) concurrent dispatch (§14, biggest win, no freshness cost), then (b) a short-TTL memoization of `get_analysis('overall')` per (user, domain, day) — but only if measurement shows the live composes dominate. **Do not pre-cache proactively; measure first.**

---

## 16. Supplement-image architectural probe

**The supplement-photo flow Danny described is architecturally SUPPORTED today** — no gap blocks it:

- **Perception:** the multimodal path (`ModelInterfaceRuntime` ingest → `perceive_images` → the model SEES the image). ✓
- **Existing supplements + medications:** `get_entity('medicine','supplement')`, `get_entity('medicine','medication')`, `get_entity('medicine','otc')` — all advertised. ✓
- **Medical conditions / allergies:** `personal_truth` (standing) + `get_user_truth('health')`. ✓
- **Relevant measurements / goals:** `get_history`/`get_analysis` (health), `get_analysis('goals')`. ✓

The model can perceive the supplement, retrieve the user's current supplements/medications/conditions/goals, and reason about appropriateness. The only thing WLJ does not (and should not) provide is the **interaction/appropriateness verdict** — that is the model's reasoning over general medical knowledge, correctly bounded by the CONSTITUTION's medical-information policy (attribute to authoritative bodies, defer individualized decisions to a clinician). **This probe validates the architecture:** perception + deterministic truth access + model reasoning already compose. (Not implemented — architectural confirmation only.)

---

## 17. Question Certification assessment

**Question Certification is certifying the TRUTH FOUNDATION, and that is its correct role — keep it there.** Its `Question` objects declare the `(capability, domain, target)` truth a class of question requires and *compute* `certified` against the live registries. That is exactly "does WLJ possess and expose the deterministic capability" — a truth-sufficiency gate, not a reasoning enumeration.

The risk (unchanged from `WLJ_COS_MODEL_ON_TRUTH_ASSESSMENT §10`) is drift toward "WLJ must anticipate every question the CoS may reason about." This investigation adds a concrete guardrail: **the three exposure gaps in §9 are exactly what Question Certification SHOULD catch** — they are truth-foundation gaps (a capability the model needs but WLJ does not expose). Registering Finance-entity, Projects-task, and Relationships-history questions in the catalog would flip them from GAP → PASS the day the exposure ships. Conversely, the **continuity defect (§12) is invisible to Question Certification** because it is a Working-Context/reasoning-continuity issue, not a truth-capability gap — confirming that Question Certification is *necessary but not sufficient* and must be paired with natural-conversation certification (the multi-turn probes used here). **Verdict: certifying the foundation, not constraining the reasoning space — provided it is not asked to grade conversational behavior.**

---

## 18. Frontier-model simplification findings

Classifying the scaffolding against "what still exists mainly because older models needed more help":

| Scaffolding | Classification | Evidence |
|---|---|---|
| Model Interface seam, gateway, safe action path, ToolCallLog audit | **essential deterministic infrastructure** | load-bearing; keep |
| Executive Context Envelope (standing context data) | **essential context** | the model reasons from it every turn |
| 12 truth tools + capability index (catalog-driven) | **essential + the map** | model-directed retrieval works because of it (§10) |
| Retrieval Platform + Authority Metadata Contract | **essential (certified)** | consume, do not redesign |
| The 6 salience "leads" (attachment/focus/profile/grounding/conversation-state/executive) | **mostly useful model guidance** | most are well-targeted; but see next row |
| `_executive_lead`'s residual capture of proactive/execution-phrased questions | **model-constraining scaffolding (runtime-proven)** | §10/§20 — same class as the fixed over-steer |
| `deterministic_understanding` on the legacy heuristic pipeline | **legacy scaffolding (latent, not currently contaminating)** | prior milestone Phase 5 — do not reopen without new evidence |
| Serial tool dispatch | **performance detail (not model-facing)** | §14 — optimize when needed |

**The frontier lesson holds:** the previous milestone proved removing ONE over-prescriptive instruction dramatically improved the product. This investigation finds the **same class continues** in one narrow residual (§20) — runtime-proven, so it is not speculation — plus a genuine truth-*exposure* deficit that is the opposite problem (too little, not too much). Simplification and exposure both point the same way: **less prescription, more truth.**

---

## 19. Essential infrastructure to preserve

Do not touch: the Model Interface seam + gateway; the Executive Context Envelope; the 12 truth tools + capability index; the certified Retrieval Platform + Authority Metadata Contract; the safe action path + audit; Current Context / Execution Decision Authority / Mission Link; Conversation State as an envelope field; multimodal perception. These are the working heart of the model-on-truth product.

---

## 20. Model-constraining scaffolding (runtime-proven)

One item, bounded and evidence-backed: **`_executive_lead` still captures proactive-framed and execution-phrased questions into its current_action bucket** ("Is there anything you'd proactively bring up?", "What should I focus on most there?" → "write in your journal", zero retrieval). This is the same class as the Executive Over-Steer defect and the same fix shape (narrow the trigger so these fall through to investigation). It is real (two runtime probes) but **secondary** to the continuity and exposure gaps, and is reported for a scoped fast-follow — not fixed in this investigation.

---

## 21. Exact first-failing layers (summary)

| Finding | First failing layer | Fix shape (not implemented) |
|---|---|---|
| Broad-answer continuity ("why do you think that?") | **Layer 1 — Working Context** (`active_subject` single-subject) | let Conversation State represent a multi-domain assessment as the active referent |
| Finance record access | **Layer 1 — missing-entity-exposure** | register `transaction`/`account`/`category`/`budget` entity types on `finance_domain_truth` |
| Projects task access + portfolio view | **Layer 1 — missing child-entity + missing-analysis** | expose `Task` records under the project entity; add analysis subjects |
| Relationships trend | **Layer 1 — missing-history-exposure** | register `RelationshipInteraction` as a history metric / analysis subject |
| Proactive / execution-phrased collapse | **Layer 4→2 — model-constraining scaffolding** | narrow `_executive_lead` trigger (same class as prior fix) |
| Whole-life latency | **performance (execution detail)** | concurrent dispatch of independent tool calls |

**Every substantive gap is Layer 1 (truth exposure) or Working Context — exactly where Danny's "truth first" axiom predicts, and none is a reasoning-engine gap.**

---

## 22. Smallest architecture/product path to the desired Chief of Staff

Ordered by trust-impact per unit effort; each is in-Constitution, evidence-gated, reversible, independently shippable, and is *exposure or a small working-state change* — **no new subsystem**:

1. **Broad-answer continuity (Working Context).** Let Conversation State carry a compact "active assessment" referent (the set of subjects a synthesis just covered) so "Why do you think that?" / "What matters most there?" reuse the just-retrieved evidence instead of re-asking. Smallest change with the widest reach — it repairs continuity on every broad answer the last milestone unlocked.
2. **Relationships history exposure.** Register `RelationshipInteraction` as a history/analysis surface — unlocks drift detection over the cleanest dated series in WLJ. Highest-value truth exposure.
3. **Projects task exposure.** Expose `Task` records (not just counts) under the project entity + a projects `overall` analysis — unblocks "what's left / what's next / how are my projects going."
4. **Finance entity exposure.** Register transaction/account/category/budget entities — unblocks record-level financial questions.
5. **Narrow the residual over-steer** (proactive/execution-phrased → investigation) — a scoped fast-follow of the prior milestone's fix, now runtime-proven.
6. **Concurrent tool dispatch** — reserve latency optimization; implement only if measurement shows whole-life latency degrading.

Steps 2–4 each auto-appear in the capability map (§7) and auto-certify in the Question Catalog (§17) the day they ship — the platform is designed for exactly this kind of exposure.

---

## 23. Constitutional assessment

**Everything in §22 is achievable entirely inside the existing Constitution. No Article is changed, weakened, or inverted. No Constitutional Review is required.**

- Exposure of Finance/Projects/Relationships truth = **IV.4 (expose, don't invent)** and **III.1 (one authority per domain)** — each registers the *existing* canonical authority through the existing `DomainTruth` pattern; no second authority, no new truth invented.
- Continuity fix = a compact deterministic index in Conversation State (**already an envelope field**), carrying *references* to truth the model reasons over — it stays facts-only, writes no prose/verdict (consistent with the Conversation State contract). The model still owns the judgment (**I.4**).
- Narrowing the over-steer = returns judgment to the model (**I.4**) and simplifies (**IV.2**).
- Concurrent dispatch = an execution detail; touches no ownership, no tool contract, no truth.

No move puts deterministic truth into the model, makes OpenAI the store, bypasses Current Context or the safe action path, duplicates an authority, or builds a reasoning engine. The work is **truth exposure + one working-state refinement**, which is precisely what the Constitution prescribes.

---

## 24. Recommended next milestone

> **Truth Access Completion + Broad-Answer Continuity** — make the model's access to WLJ truth complete where it is proven blind, and make a broad answer survive the next question.

Lead with the single highest-impact item, then the truth-exposure closures, strictly evidence-gated and certified by natural multi-turn probes on Danny's own account:

1. **Broad-answer continuity** (Working Context) — "Why do you think that?" after a whole-life synthesis must reuse the working context, not re-ask. *(Smallest change, widest reach; repairs the continuity the last milestone unlocked.)*
2. **Relationships history/trend exposure** — the highest-value truth gap (drift detection).
3. **Projects task exposure** and **Finance entity exposure** — close the two mirror-image record-access gaps.

Deferred (report-only this milestone, do not bundle): the proactive/execution-phrased over-steer residual (scoped fast-follow), and concurrent tool dispatch (reserve latency lever — the feared 35–45 s did not reproduce, so latency is not the priority). Voice/format remains explicitly deferred (truth first).

**Definition of done for that milestone:** on Danny's production account, (a) a follow-up to a broad synthesis reasons from the just-retrieved evidence; (b) "am I connecting with people less than I used to?", "what's left on <project>?", and "what did I spend at <merchant>?" each retrieve real deterministic truth; and the CoS transparently names any residual gap ("I can't yet trend your relationship contact") rather than going silently blind.

---

## Refreshed Truth Accessibility Matrix (2026-08-12, after Truth Exposure Completion)

The three proven gaps this investigation named are now **exposed through the existing Retrieval Platform** (commits `bddd6300` + `3879fd85`; governing doc addendum below). Owner-1 certified (6/6 deterministic) and Owner-2 certified (real runtime).

| Domain | Was | Now | Owner-2 result |
|---|---|---|---|
| **Relationships** | entity + analysis snapshot only; no history/trend | `get_history/get_comparison('relationships','interactions')` over the canonical `RelationshipInteraction` dated series | ✓ model discovered + used `get_comparison(relationships,interactions)` for "how has my contact changed" |
| **Projects** | `get_entity('project')` = task **counts** only | `get_entity('projects','project')` now returns the project's canonical **Task records** (`extensions.tasks`) — reference to the Tasks authority, not a duplicate | ✓ "what tasks are open on them?" → `get_entity('projects')` listed projects **with tasks** |
| **Finance** | aggregates only; no record access | `get_entity('finance','transaction')` (period + merchant `contains`) + `get_entity('finance','account')` over canonical `Transaction`/`FinancialAccount`; hidden accounts excluded; no credentials/full-numbers | ✓ "what did I spend at Costco?" → `get_entity('finance',{contains:Costco},transaction)` returned real transactions ($130 / $153.61 / $120) |

**Residual (NEXT — reported, NOT implemented this milestone, per Step 26):** for BROAD analytical questions the model reaches `get_analysis` first and does not always drill into the newly-exposed entity records when the analysis is thin — "how are my projects going?" → `get_analysis(projects)` returns *insufficient* (Projects is not analysis-capable), and "my biggest expenses this month" / "which transactions contributed most?" stay in `get_analysis` rather than `get_entity('finance','transaction')`. Classified: **(a)** Projects analysis-capability (missing — Projects has 1 current metric, below the ≥2 analysis threshold; making the projects overview compose its entities would let "how are my projects going" succeed); **(b)** a **ranked-entity** capability (missing — "the biggest N expenses" is not a single deterministic call today); **(c)** an analysis→entity drill-down behavior (the model's `get_analysis`-first instinct doesn't fall through to `get_entity` on a thin analysis). None is a defect in the shipped exposure (direct entity questions work); all three are follow-up capabilities. **First remaining meaningful limitation to a holistic view:** the analysis→entity drill-down for broad finance/project questions (the entity truth is now reachable and discoverable; the model does not yet consistently route a broad analytical question into it).

---

## Appendix A — Runtime evidence log (reproducible)

- **Path:** `CoSGateway.respond` → `ModelInterfaceRuntime` → `ModelInterfaceService.generate` → tool loop `AIService._call_api_with_tools` (`apps/ai/services.py:685`; model_interface budget `(7, 3500)` at `:89`; serial dispatch `:835`).
- **Deploy:** web + worker on `f7c2da68`.
- **Probes (real gpt-4o via production worker):** single-turn `cos-run?message=`; multi-turn `cos-run?script=` (per-turn tool attribution).
  - Model-directed: "How am I doing overall?" → 6× `get_analysis` (health/finance/relationships/tasks/goals/life), model-selected.
  - Continuity: "weight loss → why slowing?" ✓ (`get_analysis`); "how am I doing → why do you think that?" ✗ (none, deflected); "overall health → what to focus on there?" ✗ (none, current_action).
  - Proactive: "anything you'd proactively bring up?" ✗ (none, current_action).
  - Latency: trivial ~7 s / simple ~7 s / focused ~5 s / whole-health ~7 s / whole-life ~11 s (queue-inflated upper bounds).
- **Capability map:** `apps/ai/cos_services/current_context.py::_capabilities()` — dumped live.
- **Caching:** `understanding.py:42` `_TTL=150`; `get_analysis`/`get_history` — no cache (live compose).
- **Continuity cause:** `conversation_state.record_turn` / `:242` — `active_subject` single-subject, last-retrieval-wins.
- **Domain audit:** `finance_domain_truth.py` (no `entity_types`), `project_domain_truth.py:20-21` (`history_metrics=()`, task counts only), `domain_rollout.py:483` `RelationshipDomainTruth` (no `history_metrics`); user-facing counterparts in `apps/finance/views.py`, `apps/life/views.py:227`, `apps/relationships/views.py:83`.
