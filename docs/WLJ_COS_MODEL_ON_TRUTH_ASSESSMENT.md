# WLJ Chief of Staff — Model-on-Truth Product Assessment

**Type:** Investigation only. No production behavior changed. No code modified. No Constitutional change proposed.
**Date:** 2026-08-12
**Author:** Claude (Chief Architect seat)
**Runtime evidence:** production `cos-run` (real `ModelInterfaceRuntime` + gpt-4o) and `truth-probe`, web+worker on commit `e486eaa8` (aligned); local capability-registry introspection.
**Governing docs obeyed:** WLJ Constitution (Articles I–V), `01_READ_FIRST…ARCHITECTURE`, `03_ENGINEERING_OPERATING_GUIDE`, `04_DANNY_WORKING_PREFERENCES`, `WLJ_TRUTH_SURFACES.md`, `WLJ_EXECUTIVE_TRUTH_OWNERSHIP_BLUEPRINT.md`, `WLJ_LLM_TRUTH_ACTION_CONTRACT.md`.

---

## 1. Executive conclusion

**Danny's desired product — "ChatGPT sitting directly on top of the complete deterministic truth of my life" — is exactly what the architecture already intends, and about 80% of what it already IS.** The runtime is a single conversational model driving the turn over WLJ truth tools; the Constitution mandates precisely this division. This is not a redesign problem.

But the runtime proves a specific, narrow gap that is currently the product's biggest trust-breaker, and it is **the opposite of what you'd expect**. The model is not under-served by the truth layer — when it *engages* the truth tools, the answers are excellent (finances: "income +122.2%, net cashflow +181.4%"; relationships: "53 interactions with Heather, 26 days since last contact"; weight: "285.5 → 274.9 lb, −10.6 lb"). The gap is that **a piece of scaffolding built to fix an older failure now over-steers the frontier model on exactly the whole-life questions you care most about** — collapsing "How am I doing?", "What am I neglecting?", and "I want to get healthier, where should I focus?" into a single pre-computed micro-action: *"drink your protein shake."*

Two conclusions follow, both evidence-backed:

1. **The truth surface and tool loop are working and largely complete.** The model can discover and retrieve truth across most of Danny's life. Do not redesign the Retrieval Platform.
2. **The constraint is over-scaffolding, not under-capability.** A high-salience standing-context lead (`_executive_lead`) and a legacy heuristic understanding tier are steering the model *away* from exploration on broad questions. Removing/narrowing that steering — and grounding the whole-life read on the certified authorities — is the smallest path to the product Danny is describing. **This is fully inside the Constitution; it makes WLJ *simpler* (IV.2) and returns judgment to the model (I.4).** No Article changes.

> The one-line finding: **The model already sits on the truth. WLJ is standing on the model's shoulders on the broad questions — telling it "you already know the answer" before it can look.**

---

## 2. Runtime architecture — what actually happens today

Traced end-to-end through the production path (not documentation):

```
User message
  → CoSGateway.respond(surface="chat")                       apps/ai/cos_gateway/gateway.py
  → resolve_runtime(user) → ModelInterfaceRuntime            (Danny: use_model_interface=True)
      · typed-confirmation short-circuit (deterministic yes/no) — no model call
      · multimodal ingest (artifacts, perception frames)
  → ModelInterfaceService.generate()                         apps/ai/model_interface/service.py
      1. build_standing_context()   → the Executive Context Envelope (§3)
      2. _system_prompt()           = CONSTITUTION + 6 salience "leads" + JSON(context)
      3. all_tools(writes_enabled)  → 12 truth tools + 6 write intents + 3 flow tools (§4)
      4. AIService._call_api_with_tools(...)  → OpenAI tool loop (gpt-4o)
           · each truth read wrapped in the canonical envelope + AUDITED (ToolCallLog)
           · each retrieval deterministically sets the ACTIVE SUBJECT (conversation_state)
      5. record response in the audit ledger; advance conversation_state
  → CoSResponse(text, meta{tools_called, turn_id})
```

This is a clean, correct realization of the Constitution: **one author (the model), one composed-truth envelope, deterministic tools, full audit.** There is no reasoning engine inside WLJ on this path. The gateway is the single runtime owner. The tool loop is the model's; the truth is WLJ's.

**Deploy topology confirmed:** `truth-probe` reports web `e486eaa8` and worker `e486eaa8` aligned — the CoS runtime (worker) is on the tested commit, so the runtime evidence below is trustworthy.

---

## 3. What the model knows automatically (every turn)

`build_standing_context()` assembles the **Executive Context Envelope** — structured DATA, not instructions — from independently-owned interfaces, each at its own freshness. Every meaningful turn carries all of this before the model calls a single tool:

| Field | Contains | Freshness | Always present? | Authority | Helps holistic understanding? |
|---|---|---|---|---|---|
| `ai_relationship` | Chosen name, default relationship, coaching/communication style | slow (projection) | Yes | Preference truth | Sets voice, not content |
| `deterministic_understanding` | `executive` (primary_challenge, biggest_risk, workload, cognitive_load, health_read, recovery_needed), `priority` (executive + clinical), `patterns`, `predictions`, `wins`, `opportunity`, `direction` (goal_pace/momentum), `continuity` (material_changes) | medium (cache; `pending` on cold) | Yes (or `pending`) | **Legacy heuristic** `interpret()`/`ExecutiveSignals`/`cos_intelligence`/`Insight`/`Prediction` — **NOT** the certified authorities | Intends to; but ungrounded (§11) |
| `current_context` | Clock, `current_screen.location` + `focus` (the on-screen object, resolved canonically), capability index, attachments, conversation_artifacts | fast | Yes | Current Context (Article II) | Yes — page awareness |
| `conversation_state` | active_subject, active artifacts, guided_review — "what we're doing/waiting on" | per-turn | When active | Conversation State authority | Continuity |
| `personal_truth` | Nutrition targets, dietary restrictions/allergies, active conditions, medications, active goals/priorities, coaching style | cache-first | Yes | Personal Truth composer | Yes — durable "who they are" |
| `missions` | Full mission facts (goals) | per-turn | Yes | Mission map | Yes — long-term anchor |
| `execution_state` | Day's execution facts (buckets) | per-turn | Yes | Decision Authority / execution_state | Today's doing |
| `current_action` | The single "what to do now" (`decision_authority.current_action`) + mission link | per-turn | Yes (if any) | **Execution Decision Authority (Article III.2)** | The micro-now — **over-weighted (§7)** |
| `pending_confirmations` | Open confirmations awaiting yes/no | per-turn | writes only | Confirmation authority | Action safety |

On top of the JSON, `_system_prompt()` prepends **six high-salience "leads"** (restatements of facts already in the envelope, raised near the user's turn because the JSON is ~60k chars): `_attachment_lead`, `_conversation_state_lead`, `_executive_lead`, `_focus_lead`, `_profile_lead`, `_grounding_lead`. These exist because facts buried deep in a 60k-char prompt were measurably overlooked. **Each lead was a correct fix for a specific past failure.** One of them — `_executive_lead` — is now the primary constraint (§7).

**Verdict:** The model is handed a genuinely rich, holistic, deterministic picture every turn — arguably *too much*. The problem is not missing context; it's that one slice of context (the pre-computed `current_action`, amplified by its lead) is instructed to dominate.

---

## 4. What truth the model can retrieve autonomously (the tool surface)

`all_tools()` exposes **12 truth tools + 6 write intents + 3 action-flow tools**. Discovery is real: valid domains/metrics/subjects are advertised as JSON-Schema **enums** built live from the capability registries, and the per-turn `capabilities` index (`truth_history`, `truth_entities`, `truth_readings`, `truth_analysis`, `truth_comparison`, `truth_event_frequency`, `truth_adherence`, `domain_semantics`) tells the model exactly which (domain, metric/subject) pairs are answerable. The model does **not** have to know implementation terminology or guess a metric.

| Tool | Answers | Progressive exploration? |
|---|---|---|
| `get_analysis(domain, subject\|'overall')` | The whole investigation in one call: trends across windows + all-time span/change + record detail + `holds_data` verdict | **The model's power tool.** One call = a domain assessment |
| `get_history(domain, metric, period)` | Aggregate/time-series: counts, totals, averages, change, trend; natural-date resolution | Yes |
| `get_entity(domain, entity_type\|name, filters)` | Record-level detail (a workout's exercises, a person, a medication, an artifact) | Yes |
| `get_readings(domain, metric, window)` | Intra-day timestamped readings + window stats + excursions (glucose) | Yes |
| `get_event_frequency` | Cross-window event-count trend (lows getting more frequent) | Yes |
| `get_comparison` | Period-vs-period delta/direction | Yes |
| `get_adherence` | Actual-vs-target for a metric with a stored target | Yes |
| `get_domain_state(domain)` | Current deterministic state for a domain | Yes |
| `search_history(query, domain)` | Keyword/content search over records that MENTION a topic | Yes |
| `get_user_truth(section)` | Full durable personal profile | Yes |
| `get_foundational_health_facts(keys)` | Non-date-scoped canonical health facts | Yes |
| `get_execution_review(day)` | The complete intended execution for a day (reconciliation) | Read-only |
| Writes | `mutate_task`, `create_task`, `complete_task`, `log_weight`, `log_body_measurements`, `import_journal_entries` + `resolve_pending_action`, `complete_execution_item`, `next_review_item` | Safe path |

**Assessment:** This is a strong, discoverable, progressively-explorable truth surface. It supports exactly the loop Danny wants: understand → decide what truth would help → retrieve → follow related truth → cross domains → reason. **Runtime proof it works (§6): every targeted analytical question retrieved the right truth and answered well.** The catalog-driven enums mean a new domain that registers a capability participates automatically — the surface is designed to *expose*, not to *anticipate*.

The one structural weakness is subtle and covered in §5: `get_foundational_health_facts` is a curated, partial key-list that historically shadowed the systematic `get_history` authority (the "protein yesterday" class). It survives as a narrow surface but remains a redundant door.

---

## 5. Whole-life truth accessibility matrix

Built from **live capability-registry introspection** (not docs). ✓ = the model can retrieve it through the named tool today.

| Domain | State | History (agg/trend) | Entity (records) | Analysis (`get_analysis`) | Compare | Readings | Adherence | Search | Primary gap |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|---|
| **Health** (vitals/sleep/workouts) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | Fully accessible |
| **Nutrition** (consumption) | ✓ | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | Fully accessible |
| **Faith** | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | ✓ | Fully accessible |
| **Journal** | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | ✓ | Fully accessible |
| **Goals / Missions** | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | ✓ | Fully accessible |
| **Tasks** | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | ✓ | Fully accessible |
| **Habits** | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | — | Accessible |
| **Medical / Medications** | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | — | Accessible |
| **Calendar** | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | — | Accessible |
| **Brain Training** | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | — | Accessible |
| **Finance** | ✓ | ✓ | **✗** | ✓ | ✓ | — | — | ✓ | **No record-level entity** — "show my restaurant transactions" not retrievable as records; aggregates/analysis only |
| **People / Relationships** | ✓ | **✗** | ✓ | ✓ | **✗** | — | — | **✗** | **No history/trend/compare** — "am I contacting Haley less over time?" not answerable as a series (analysis gives a 90-day snapshot) |
| **Meals** (supply/recipes) | ✓ | ✗ | ✓ | ✗ | ✗ | — | — | — | Supply domain by design; consumption lives in Nutrition |
| **Legacy** | ✗ | ✗ | ✓ | ✓ | ✗ | — | — | — | No state summary; entity+analysis only |
| **Capture / Notes** | ✓ | ✗ | ✓ | ✗ | ✗ | — | — | ✓ | No analysis/trend over captures |
| **Projects** | **✗** | ✗ | ✓ | ✗ | ✗ | — | — | — | **Entity only** — no state, history, or analysis; least accessible tracked domain |
| **Fitness / Sports / Fasting** | ✓ (state alias) | — | — | — | — | — | — | — | Thin aliases; real fitness truth lives under Health (workouts) |
| **Artifacts** (multimodal) | — | — | ✓ | — | — | — | — | — | Retrievable as entities |

**Reading the matrix:** The high-frequency life domains (Health, Nutrition, Faith, Journal, Goals, Tasks, Finance, People) are broadly accessible. The genuine accessibility gaps, in priority order of likely conversational impact:

1. **People has no history/trend** — relationship *drift over time* (the thing Danny most wants a CoS to catch) can only be seen as a current snapshot, not a trend series.
2. **Finance has no record-level entity** — the model can assess finances beautifully in aggregate but cannot pull individual transactions.
3. **Projects is entity-only** — nearly blind.
4. **Domain aliasing** (see §7) — `health`/`medical`/`medicine`/`fitness`/`nutrition`/`sports`, `tasks`/`life`, `goals`/`purpose` are separate domain keys; the model routes by `domain_semantics` meaning, but the surface area for a wrong turn is real.

Crucially: **a missing capability is not a missing answer** (the WLJ_TRUTH_SURFACES lesson) — People drift can still be *narrated* from the 90-day analysis snapshot, as the runtime showed. But it cannot be *quantified as a trend*, which is a real ceiling on "detect drift early."

---

## 6. Natural whole-life conversation findings (runtime)

Nine natural questions run through the **real production CoS**. `TOOLS` = the actual `tool_calls` recorded; answers are verbatim (truncated).

| # | Question | Tools called | Quality |
|---|---|---|---|
| 1 | How am I doing? | **(none)** | ✗ "The single most important thing for you right now is to drink your protein shake." |
| 2 | What am I neglecting? | **(none)** | ✗ "...drink your protein shake. This is the upcoming task..." |
| 3 | Am I living according to the priorities I say matter? | get_analysis | ◐ Opens with protein shake, then generic 1-2-3 synthesis |
| 4 | What has changed about me over the last month? | get_analysis | ◐ Opens with protein shake, then vague "health, nutrition, tasks" |
| 5 | Why have I been struggling lately? | get_analysis | ◐ "...focus on drinking your protein shake..." then "reflect on your goals/health/habits" |
| 6 | What's the single most important thing today? | **(none)** | ✓ "...drink your protein shake." (correct use of `current_action`) |
| 7 | I want to get healthier. Where should I focus? | **(none)** | ✗ "The most important step right now is to drink your protein shake." |
| 8 | How am I doing with my relationships? | get_analysis | ✓✓ "53 interactions with Heather (26 days since last contact)... Haley 48 (31 days)... 50 days since Mike Snyder... reach out to friends/extended family." |
| 9 | Analyze my weight trend (3 months) / Assess my finances | get_analysis | ✓✓ Precise, grounded, genuinely useful |

**The pattern is unambiguous:**

- **Targeted questions (6, 8, 9, finances) are excellent.** The model retrieves the right truth in one `get_analysis` call and reasons well. This *proves the model-on-truth product already works* when the model engages.
- **Broad/drift/investigation questions (1, 2, 7) fail** — zero retrieval, answered from the pre-computed `current_action`. "What am I neglecting?" and "Where should I focus to get healthier?" — the two most CoS-defining questions — return *"drink your protein shake."*
- **The middle (3, 4, 5) is contaminated** — even when the model does call `get_analysis`, it opens the answer with the protein shake because it is instructed to LEAD with `current_action` on any assessment.

This is the single most important finding in the investigation, and it has a precise cause (§7).

---

## 7. Where the CoS is constrained, and WHY

### 7.1 The primary constraint: `_executive_lead` over-steers broad questions (Layer 4 → Layer 2)

`_system_prompt()` injects `_executive_lead(standing_context)` at high salience whenever `current_action` exists (i.e. almost always). Its text (service.py:555–582) instructs, for the phrases *"check in", "status", "overall status", "where do things stand", "what should I do", "how am I doing", "how am I doing across everything", "give me an overall assessment of my life"*:

> "...you ALREADY KNOW the answer: lead with the item above and give ONE clear next action. NEVER ask them what to check in on, to narrow the request, or to pick an area..."

This lead was built to fix **Blocker #3** (the CoS replied "what would you like to check in on?" after its own proactive check-in). That was a real trust failure and the fix was correct *for that class*. But the lead is now **over-broad**: it captures "how am I doing," "what should I do," and "overall assessment" — the exact questions that in §6 of the CONSTITUTION are defined as **EXECUTIVE ASSESSMENT** ("GATHER silently... use `deterministic_understanding` for cross-domain... use `get_analysis('overall')`... synthesize") and in another CONSTITUTION section as **INVESTIGATE-BEFORE-CONCLUDING** ("I want to get healthier" → retrieve first, never generic).

**The result is a direct contradiction inside the same prompt:** one section says *investigate and synthesize across the whole life*; the higher-salience `_executive_lead` says *you already know — lead with the one action and don't ask*. The lead is positioned near the top and is emphatic ("ALREADY KNOW," "NEVER ask"), so it wins. The model obeys the loudest instruction and answers "drink your protein shake."

- **Failing layer:** primarily **Layer 4 (Experience/steering)** — the scaffolding, not the truth. Secondarily Layer 2 (the model complies with the over-steer instead of resolving the conflict).
- **Class, not symptom:** the class is *"a scaffolding lead built for a narrow past failure now suppresses the frontier model's own judgment on a whole category of questions."* The condition that makes it possible is a **fixed, keyword-triggered instruction that asserts the answer is already known**, applied to questions whose whole point is exploration.

### 7.2 The secondary constraint: the whole-life read is ungrounded (Layer 1)

`deterministic_understanding` — the field the CONSTITUTION tells the model to reason FROM for cross-domain questions — is composed (understanding.py:50–119) entirely from the **legacy heuristic pipeline** (`interpret()`/`ExecutiveSignals`, `cos_intelligence`, `day_continuity`, `Insight`/`Prediction`), which shares **no code** with the certified retrieval authorities (`get_analysis`/`get_history`/`metric_date`) that produce the excellent §6 answers. So on a broad question the model is handed a heuristic whole-life summary *and* a single decision-authority action — neither drawn from the certified truth that actually works. This is precisely the open gap the **Executive Truth Ownership Blueprint** names: the machinery exists, but the executive read is not yet grounded on the certified authorities, and WLJ still pre-decides a minority of I.4 verdict fields (`primary_challenge`, `biggest_risk`, `priority.executive`).

### 7.3 Minor constraints (real, lower impact)

- **Redundant door:** `get_foundational_health_facts` remains a curated partial key-list beside the systematic `get_history` (the "protein yesterday" shadow class — contained, not eliminated).
- **People drift is un-trended; Finance records are unreachable; Projects is near-blind** (§5).
- **Prompt weight:** the CONSTITUTION is ~60k chars with six leads; every fix adds salience, and salience is a finite budget. The leads are individually justified but collectively they crowd the model's own judgment — the exact thing that should *shrink* as the model improves (IV.2).

---

## 8. What infrastructure is essential and must remain

These are load-bearing and correct. **Do not touch them.**

- **The Model Interface seam + gateway** (one runtime owner; provider-agnostic). Constitutional I.8.
- **The Executive Context Envelope** as a *data* structure — AI Relationship, Current Context, Personal Truth, missions, execution_state, conversation_state, pending_confirmations. Architecturally complete.
- **The 12 truth tools + capability-index discovery** (catalog-driven enums). This is the working heart of model-on-truth (§6 proves it).
- **The Retrieval Platform + Authority Metadata Contract** (`truth/authority.py`, build-gate ratchet). Certified permanent infrastructure. Consume, do not redesign.
- **The safe action path** (`action_interface → execute_intent → UAIO → confirmation → audit`) and **ToolCallLog** (the audit that made this very investigation possible).
- **Current Context / Execution Decision Authority / Mission Link** — the single-authority pillars (Articles II, III).
- **Conversation State** as an envelope field (not a retrieval surface).
- **The truth-tool "leads" mechanism** in principle — raising buried facts near the turn is legitimate and often necessary (attachment/focus/profile/grounding leads are well-targeted).

---

## 9. What infrastructure may be over-scaffolding the model

Candidates for narrowing/grounding (NOT deletion — evidence-gated, one at a time):

1. **`_executive_lead` scope** *(highest impact)* — it should fire on **genuine check-in/proactive-continuation** intents (its original Blocker #3 purpose) and **stop capturing exploratory assessment/investigation questions** ("how am I doing," "what should I focus on," "what am I neglecting," "where should I focus"). Those must fall through to the CONSTITUTION's EXECUTIVE-ASSESSMENT / INVESTIGATE-BEFORE-CONCLUDING behavior (retrieve `get_analysis`, synthesize). Classify: **model-constraining complexity.**
2. **`deterministic_understanding` grounding** — re-source the executive read from the certified authorities (or clearly demote it to orientation-only so the model treats it as a hint, not the answer), and stop pre-deciding the I.4 verdict fields. Classify: **model-constraining complexity + latent duplicate authority** (two executive stacks). This is the Executive Truth grounding milestone.
3. **`get_foundational_health_facts`** — retire or delegate its keys into `get_history` (finish eliminating the shadow class). Classify: **harmless-to-constraining complexity.**
4. **Prompt/lead weight budget** — as the above land, the leads can likely *shrink*. Classify: **useful model support trending toward harmless complexity.**

Everything else in the audit falls into **necessary deterministic infrastructure** or **useful model support** — it should stay.

---

## 10. Proper role of Question Certification

**Question Certification is sound and should stay — but its role is to certify TRUTH SUFFICIENCY, not to enumerate every question the CoS may reason about.** The runtime supports this precisely:

- The correct boundary: *"WLJ possesses the deterministic truth/capabilities necessary for this CLASS of question."* The Question Catalog already works this way — each `Question` declares the `(capability, domain, target)` truth it requires, and `certified` is **computed** against the live capability registries. That is exactly right: it certifies that the *truth exists and is exposed*, then lets the model reason.
- The failure mode to avoid: letting the catalog drift toward *"WLJ must explicitly anticipate every question"* — i.e. treating a not-yet-certified *phrasing* as a signal to build a bespoke capability per question. That would re-import the retired "anticipate the conclusion" architecture the pivot killed.
- **Evidence-based refinement:** §6 shows the catalog is measuring the *wrong altitude* for the current gap. Health is at 74/80 on **capability** questions, yet the CoS fails "how am I doing" and "what am I neglecting" — because those failures are **not truth gaps at all** (the truth is present and excellent). They are **steering/experience** failures the catalog cannot see, because it validates capability wiring, not conversational behavior. This is the same lesson as the Truth Validation Center: *validate at the altitude you're certifying.* Keep the Question Catalog for capability sufficiency; add **natural-conversation certification** (the §6-style probes, scored on whether a paying customer would trust the answer) for the experience altitude.

**Recommendation:** Question Certification = the deterministic **truth-sufficiency** gate (keep, per domain). It is *necessary but not sufficient* for CoS quality. The whole-life experience is certified by natural-conversation runs, not by adding more catalogued questions.

---

## 11. Proper role of Executive Truth

**The remaining Executive Truth work IS the bridge to the product Danny is describing — and this investigation independently re-derived that from runtime, not doctrine.** The Ownership Blueprint's conclusions are confirmed by the live path:

- The machinery exists (`interpret()`/`ExecutiveSignals`, `understanding.py`, the Executive Context Envelope). **No new subsystem, no "Executive Brain," no Constitutional change.**
- **WLJ currently pre-decides I.4 verdict fields** (`primary_challenge`, `biggest_risk`, `priority.executive`) — confirmed in `understanding.py:59–72`. These are *judgments* the model should form from exposed facts (I.4). The model then narrates a verdict WLJ made, which is why broad answers feel like a canned read rather than the model's own reasoning.
- **The executive read is ungrounded** — it runs on the legacy heuristic pipeline, not the certified authorities that produce the good §6 answers. This is the concrete "two truth stacks" gap the Blueprint names.

So the three Executive Truth jobs the Blueprint specifies are exactly what §7 demands: **(a) stop pre-deciding the I.4 verdict fields; (b) ground the executive assessments on `get_analysis`/`get_history`/`metric_date`; (c) certify end-to-end with natural cross-domain conversation.** Runtime evidence pulls this forward: it is not a "later, after Health" nicety — the ungrounded, verdict-pre-deciding executive read is *causing* the §6 broad-question failures today.

**WLJ pre-decides conclusions that should belong to the model in exactly one place: the `deterministic_understanding.executive` verdict fields and the `current_action`-as-the-whole-answer steering.** Fix those and the model reasons holistically over certified truth — which is the desired product.

---

## 12. The smallest path from today's system to "ChatGPT on top of Danny's complete WLJ truth"

Ordered by trust-impact-per-unit-effort. Each step is in-Constitution, evidence-gated, reversible, and independently shippable. **None is a redesign.**

1. **Narrow `_executive_lead` to its real intent (the single highest-leverage change).** Make it fire on genuine check-in / proactive-continuation intents (Blocker #3's purpose) and **release** exploratory assessment/investigation questions to the CONSTITUTION's existing EXECUTIVE-ASSESSMENT + INVESTIGATE-BEFORE-CONCLUDING behavior. Expected effect: "how am I doing," "what am I neglecting," "where should I focus" begin retrieving `get_analysis` and synthesizing across domains instead of returning "drink your protein shake." *This alone likely closes most of the perceived gap.*
2. **Ground `deterministic_understanding` on the certified authorities and stop pre-deciding I.4 verdicts** (Executive Truth job a+b). Let the model form `primary_challenge`/`biggest_risk`/priority from exposed facts; demote the heuristic read to orientation-only.
3. **Certify the whole-life experience by natural conversation** (Executive Truth job c) — the §6 probe set as a permanent Owner-2 harness scored on trust, not layer-correctness. This becomes the acceptance gate for steps 1–2.
4. **Close the two real accessibility gaps that block drift-detection:** People **history/trend** (so relationship drift is quantifiable over time) and Finance **record-level entity**. Both are "expose existing truth," not new architecture.
5. **Retire the `get_foundational_health_facts` shadow** into `get_history` (finish the "protein yesterday" elimination).
6. **Only then** resume adding Health capability questions (Excursion Frequency et al.) — they are real, but they are *not* what stands between today's system and Danny's felt product.

**Sequencing note:** the current bootloader names **Excursion Frequency Trend (P1)** as the next milestone. Runtime evidence says the trust-limiting factor is not a missing Health capability — it is the executive over-steer. Recommend re-ordering: **steps 1–3 before more Health capabilities.**

---

## 13. Constitutional assessment

**Can this be achieved entirely inside the existing Constitution? — YES. Unambiguously.**

Every recommended change *strengthens* the constitutional division rather than weakening it:

- **Article I.4 (the model owns judgment):** narrowing `_executive_lead` and un-pre-deciding the verdict fields *returns* judgment to the model — more compliant, not less.
- **Article IV.2 (improve truth before intelligence; simpler as models improve):** these changes make WLJ *smaller* (less steering, one executive stack instead of two).
- **Article IV.4 (expose, don't invent):** grounding the executive read on certified authorities and exposing People-history/Finance-records is exposure, not invention.
- **Article III (single authority):** collapsing the legacy heuristic executive stack onto the certified authorities *removes* a latent duplicate authority.
- **Article II (Current Context) and I.7 (safe actions):** untouched.

**No Article is changed, weakened, removed, or inverted. No Constitutional Review is required.** The Constitution does not merely *permit* this work — in the Ownership Blueprint's words, it *prescribes* it (I.3 keeps the scalars, I.4 relocates the verdicts, IV.3 reuses the one authority, IV.4 exposes facts instead of inventing verdicts).

One caution for implementation (not a Constitutional issue): narrowing `_executive_lead` is a **behavior-touching** change on the highest-traffic path. It must be done as the smallest safe diff, parity-tested with the §6 probe set, and validated by Danny in production before the next step — per the engineering guide's investigation order and Danny's "preserve existing behavior" rule.

---

## 14. Recommended next milestone

> **Executive Assessment Grounding — release the model to reason on broad questions.**

A single coherent milestone (steps 1–3 of §12), in strict order, each gated by the §6 natural-conversation probes on Danny's own account:

1. **Scope `_executive_lead`** to genuine check-in/continuation intents; let assessment/investigation questions fall through to the CONSTITUTION's existing whole-life behavior.
2. **Ground `deterministic_understanding`** on `get_analysis`/`get_history`; stop pre-deciding `primary_challenge`/`biggest_risk`/`priority.executive`.
3. **Stand up natural-conversation certification** (the probe set as a permanent Owner-2 harness) as the acceptance gate.

**Definition of done:** on Danny's production account, "How am I doing?", "What am I neglecting?", and "Where should I focus to get healthier?" each **retrieve deterministic truth and return a synthesized, prioritized, cross-domain answer** a paying customer would trust — and none of them answers "drink your protein shake." Health capability work (Excursion Frequency et al.) resumes after this lands.

This is the smallest change that turns the runtime you already have — a strong model on a strong truth surface — into the product Danny is describing: **ChatGPT sitting directly on top of the complete deterministic truth of his life, free to look.**

---

## Appendix A — Runtime evidence log (reproducible)

- **Path:** `CoSGateway.respond` → `ModelInterfaceRuntime.respond` → `ModelInterfaceService.generate` (`use_model_interface=True` for Danny; migrations 0088/0089).
- **Deploy:** `truth-probe` → web `e486eaa8`, worker `e486eaa8` (aligned).
- **Probes:** `POST /admin-console/api/claude/cos-run/?email=…&message=…` (real gpt-4o via production worker); `tool_calls` read from the returned audit.
- **Capability registries (local introspection, commit e486eaa8):**
  - STATE: brain_training, calendar, capture, execution, faith, fasting, finance, fitness, goals, habits, health, journal, life, meals, medical, medicine, notes, nutrition, purpose, relationships, routine, sports, tasks
  - HISTORY: brain_training, calendar, faith, finance, goals, habits, health, journal, medical, medicine, nutrition, tasks
  - ENTITY: artifacts, brain_training, calendar, capture, events, faith, goals, habits, health, journal, legacy, meals, medical, medicine, notes, nutrition, projects, relationships, tasks
  - ANALYSIS: brain_training, calendar, faith, finance, goals, habits, health, journal, legacy, medical, medicine, nutrition, relationships, tasks
  - READINGS: health · EVENT_FREQ: health · ADHERENCE: health, nutrition
  - COMPARISON: brain_training, calendar, faith, finance, goals, habits, health, journal, medical, medicine, nutrition, tasks
- **Key contradiction located:** `service.py::_executive_lead` (555–582) vs the CONSTITUTION's EXECUTIVE ASSESSMENT + INVESTIGATE-BEFORE-CONCLUDING sections (`constitution.py`) — both govern "how am I doing / what should I do," with opposite instructions; the higher-salience lead wins.
- **Ungrounded executive read:** `understanding.py::_compose` sources `executive`/`priority`/`patterns` from `interpret()`/`cos_intelligence`/`day_continuity` — disjoint from the certified `get_analysis`/`get_history` authorities.
