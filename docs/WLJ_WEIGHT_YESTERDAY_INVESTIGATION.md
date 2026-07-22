# Weight-Yesterday Contradiction — Runtime Investigation

**Date:** 2026-07-22
**Class:** Truth Retrieval Certification — parallel authority (same class as "protein yesterday")
**Status:** INVESTIGATION COMPLETE → **IMPLEMENTED** (see §10) — AWAITING PRODUCTION VALIDATION
**Method:** Hypothesis → Runtime Proof → Architectural Decision (`docs/WLJ_RUNTIME_TRACE_DEBUGGING.md`)

---

## 0. The reported failure

```
User: What is my current weight?
CoS:  Your current weight is 280.4 lb as of July 22, 2026.
User: Yesterday's?
CoS:  Your weight yesterday was 280.4 lb.
User: My weight yesterday was not the same as today.
CoS:  Your weight yesterday was 281.5 lb.
User: (why two numbers?)
CoS:  Could you clarify which two numbers you're referring to?
```

The concern is not that `281.5` is right. It is that **both answers were reachable**.

---

## 1. Runtime method

Reproduced through the REAL production path, not a unit test:

| Element | Value |
|---|---|
| Entry point | `CoSGateway.respond(user=…, surface="chat", conversation=…)` |
| Resolved runtime | `model_interface` (`preferences.use_model_interface = True`, verified at runtime) |
| Model | real OpenAI, `COS_MODEL=gpt-4o` (key from `.env`) |
| Audit | `ToolCallLog` rows read back per turn |
| Data | local `wlj_dev`, seeded to the prod-reported shape: `2026-07-22 = 280.4 lb`, `2026-07-21 = 281.5 lb` |

**Honesty note on the data.** `wlj_dev` is not prod truth (there is no prod read channel for `WeightEntry`/`ToolCallLog`). The seeded rows reconstruct the *shape* the transcript implies. Every claim below about **which surface computes what** is proven directly against code + runtime output and is environment-independent. The one environment-dependent number is the stale SAE value (§3, A2) — locally `298.3` from April, in prod it was fresh; the *contract defect* it exposes is identical either way. **All seeded rows and repro conversations were deleted; `wlj_dev` is back to its pre-investigation state.**

---

## 2. Runtime trace (verbatim)

Four turns, one conversation, real model:

```
TURN 1 USER: What is my current weight?
ASSISTANT:   Your current weight is 298.3 lb, and the trend is decreasing.
tools_called = ['get_foundational_health_facts']
  [truth] get_foundational_health_facts  args = {"keys": ["current_weight"]}

TURN 2 USER: Yesterday's?
ASSISTANT:   Could you please clarify what specific information or record you're
             asking about from yesterday? …
tools_called = []                       <-- NO retrieval at all

TURN 3 USER: My weight yesterday was not the same as today.
ASSISTANT:   Your weight yesterday was 281.5 lb, and your current weight is 298.3 lb.
tools_called = ['get_foundational_health_facts']
  [truth] get_foundational_health_facts  args = {"keys": ["weight_yesterday","current_weight"]}

TURN 4 USER: Why did you give me two different numbers?
ASSISTANT:   Could you let me know which numbers or context you are referring to? …
tools_called = []
```

Turn 2 was probed three more times in fresh conversations, because a single model
sample proves nothing about routing:

```
RUN 0  "Yesterday's?" -> get_entity {"domain":"journal","entity_type":"entry", …}
       "It seems there are no journal entries recorded for yesterday."
RUN 1  "Yesterday's?" -> get_history {"domain":"journal","metric":"entries","period":"yesterday"}
       "It seems there are no journal entries recorded for yesterday."
RUN 2  "Yesterday's?" -> (no tool)  "Could you please clarify …"
```

**0 of 4 runs retrieved weight for "Yesterday's?". 2 of 4 silently switched domain to Journal.**

---

## 3. The authority census — every surface that answers "what did I weigh yesterday"

Run against **identical** seeded data (`2026-07-22 = 280.4`, `2026-07-21 = 281.5`):

| # | Authority | How it computes | Returned |
|---|---|---|---|
| **A1** | `get_foundational_health_facts(["weight_yesterday"])` → `DomainTruth("health").current()` → `CurrentHealth._ROUTES` → `DailyHealthQueries.weight_on(user, yesterday)` | `WeightEntry.filter(recorded_at__date__lte=yesterday).order_by("-recorded_at").first()` — **carry-forward, last-known-value** | `281.5`, `freshness:"current"`, `exact:true`, `as_of:2026-07-21` |
| **A2** | `get_foundational_health_facts(["current_weight"])` → `_FACT_MAP` → **SAE snapshot** `health.weight_current` | latest `WeightEntry` written by the last background `build_health_state` rebuild | `298.3`, **no `freshness`, no `status`, no `confidence`** — bare value + `recorded_at` |
| **A3** | `get_history(domain="health", metric="weight", period="yesterday")` | date-windowed aggregate over `WeightEntry`; **no carry-forward** | `count:1, average:281.5, points:[{2026-07-21, 281.5}]` |
| **A4** | `get_entity(domain="health", entity_type="weight")` | record-level list, newest first | both records: `280.4 (07-22)`, `281.5 (07-21)` |

Four surfaces. The model chooses freely between them, and the tool schemas
actively encourage that: `get_foundational_health_facts` is advertised for
*"what is my current weight?"*, `get_history` for *"what did I weigh on July 4th"*,
`get_entity` for record contents. Nothing designates a **single** authority for
"my weight on date D".

### 3a. Proof that the authorities actually disagree

Deleting only the `2026-07-21` row and re-asking the same question of two authorities:

```
A1  weight_yesterday      -> value 298.3, for_date 2026-07-21, as_of 2026-04-07,
                             exact false, freshness "stale", confidence "low"
A3  get_history yesterday -> status "empty"   (no points, no average)
```

**A1 answers "you weighed 298.3 lb yesterday" (a value from 105 days earlier, carried forward). A3 answers "there is no data for yesterday." Same question, same instant, same user — two deterministic authorities, two contradictory truths.** This is a pure Layer-1 defect with no model involved.

### 3b. Why A2 is a shadow authority

- It is keyed `current_weight`, not `weight_today` — so it is **not date-scoped at all**. It means "the newest row we ever saw," which the model naturally reads as "today."
- It comes from the **SAE snapshot**, and `state_engine.get_user_state()` rebuilds **only when the row is missing or empty** — a populated-but-stale snapshot is never refreshed by a read, at any `allow_rebuild` setting. It depends entirely on a background cycle.
- Unlike every other health fact, **it carries no truth envelope** — no `freshness`, no `confidence`, no `status`. The model cannot tell a value recorded this morning from one recorded in April. In this run it confidently reported a 105-day-old number as "your current weight."

A2 and A1 are returned by the **same tool**, side by side, in the same JSON, under different keys, with different contracts and different underlying stores.

---

## 4. Answers to the ten questions

1. **Tools called.** *"What is my current weight?"* → `get_foundational_health_facts(keys=["current_weight"])` (A2). *"Yesterday's?"* → nothing weight-related (0/4 runs); 2/4 routed to Journal.
2. **Was the first "yesterday" answer retrieved from a tool?** **No.** No yesterday-scoped weight retrieval occurred on that turn.
3. **Which tool?** — n/a.
4. **Why wasn't one called?** *"Yesterday's?"* is elliptical — it carries no subject. WLJ had no deterministic anchor to supply one: `ModelInterfaceService._subject_from_entity_result` (service.py:437) derives the Conversation-State active subject **only from `get_entity`** (`if name != "get_entity": return None`). Turn 1 was answered by `get_foundational_health_facts`, which registers **no subject**. So Conversation State entered turn 2 empty and the model free-associated. In prod it associated with the number already in the transcript (`280.4`); locally it associated with Journal. Same defect, different symptom.
5. **Why did the second attempt retrieve different data?** The user's correction re-supplied the missing subject *and* the missing date scope in plain language, which caused a call to a **different authority** — `weight_yesterday` (A1, live `DailyHealthQueries`) instead of `current_weight` (A2, SAE snapshot).
6. **Did the second answer invoke a different tool?** Same tool *name*, **different fact key = different authority, different store, different contract**: `current_weight` (A2) → `weight_yesterday` (A1). Proven in the ToolCallLog args, turn 1 vs turn 3.
7. **Is this another shadow-authority situation?** **Yes.** `current_weight` (A2) is a non-date-scoped, envelope-less, snapshot-backed shadow of the date-scoped live authority — exactly the shape of the `SAE-facts shadowing get_history` finding in the 2026-07-21 six-question runtime investigation.
8. **More than one deterministic authority for "weight yesterday"?** **Yes — four** (§3).
9. **How each computes its answer.** §3 table + §3a divergence proof.
10. **Classification.** See §6.

---

## 5. Conversation grounding — why it failed to see its own contradiction

**Prior turns were present.** Proven: `load_conversation_history(conv)` returned the complete four-turn transcript, both assistant answers included. `AssistantMessage` rows persist correctly and the gateway loads history *before* persisting the current turn. **Transcript reconstruction did not fail. The model did not lack context.**

The failure is upstream of the model:

- **WLJ handed it two numbers and stamped both valid.** `298.3` was labelled *"current weight"* and `281.5` *"weight yesterday"*. Neither carried anything marking them as competing measurements of one quantity. There is no deterministic cross-turn consistency check — nothing in WLJ compares a fact issued this turn against the same fact issued three turns ago.
- **The audit ledger could not have caught it either.** For `get_foundational_health_facts`, `result_digest` records only `{"keys": [...]}` — **the returned values are never recorded** (service.py:513). `ToolCallLog`'s stated purpose is to answer *"what truth was provided?"*; for the most-used health tool it answers only *"what was asked for."*
- **The ledger cannot even separate turns.** `turn_id = request_id or f"conv-{conversation.id}"` (service.py:630), and the production gateway path calls `generate()` **without** `request_id` (runtime.py:261). Every turn in a conversation shares one `turn_id` — visible in the trace above, where turn 3's query returns turns 1–3's rows. Per-turn forensics in prod is currently impossible.

So "Could you clarify which two numbers?" is not the model ignoring the transcript. It is the model being unable to distinguish a contradiction from two legitimately different facts — because **WLJ never told it they were the same quantity**, and nothing deterministic was watching.

---

## 6. Architectural classification

**Primary: Parallel deterministic authority (Layer 1 — Truth).** Four deterministic surfaces answer "my weight on date D", with different date semantics (carry-forward vs windowed), different stores (live ORM vs SAE snapshot), and different envelopes (full vs none). §3a proves two of them return contradictory answers to the identical question with no model involved. This is a violation of *one deterministic authority per truth domain*.

**Contributing (corrected classification).** The primary defect is parallel authority, but it was not the only failure. The following are each real and each addressed:

1. **Stale-snapshot / freshness-contract defect.** `current_weight` read an SAE snapshot that `get_user_state()` never refreshes once populated, and carried no freshness envelope at all.
2. **Retrieval-selection failure.** *"Yesterday's?"* called no weight tool in 4/4 probes and drifted into the Journal domain in 2 of them — failed subject continuation and tool selection.
3. **Conversation-State anchoring gap.** The active subject was derived only from `get_entity`, so an answer delivered by `get_foundational_health_facts` anchored nothing.
4. **Answer-grounding enforcement gap.** The first "yesterday" answer was stated as fact although no retrieval occurred on that turn. The model may resolve the *referent* conversationally; it may not supply the *value*.
5. **Reasoning miss.** With the full transcript present, asking "which two numbers?" is poor reasoning over visible history — a genuine Layer-2 failure, not merely a truth-delivery one.
6. **Audit blindness.** Values not recorded; `turn_id` not per-turn. Detection of this class in production was impossible.

**What the model did correctly:** it selected a tool WLJ advertises for the question asked and reported what WLJ returned. **Given the truth WLJ supplied, both numbers were "correct."** That remains the heart of the defect — but it does not absolve items 2–5.

---

## 7. Recommended fix — eliminate the condition, not the symptom

The condition that made this possible: **"weight on a date" has no single authority, and one of its shadows is a snapshot with no freshness contract.** Recommendations, ranked, for approval — **nothing implemented**:

1. **Collapse to one date-scoped weight authority.** One function answers "weight on date D" for every consumer (`current_weight`, `weight_yesterday`, `get_history`, `get_entity`). Retire `current_weight` as an independent producer: redefine it as `weight_on(today)` through that authority, or rename it `weight_latest_recorded` so its meaning is honest. This is the class-eliminating change — the same move that killed the *"6:15 AM tonight"* class.
2. **Resolve the carry-forward contract, once, explicitly.** A1 carries values forward indefinitely; A3 does not. Pick one semantic for "weight on date D" and make the other conform. If carry-forward stays, `exact:false` must be *structurally* un-ignorable, not an optional field — §3a shows it currently produces "you weighed 298.3 lb yesterday" from a 105-day-old row.
3. **No health fact without an envelope.** `current_weight` must carry `freshness`/`confidence`/`as_of` like every peer, and a snapshot-sourced fact must degrade honestly when the snapshot is old rather than presenting as current.
4. **Anchor the subject from every truth retrieval, not just `get_entity`.** A `get_foundational_health_facts` answer should set the Conversation-State active subject so *"Yesterday's?"* is deterministically scoped to weight. This directly fixes the 0/4 routing.
5. **Make the audit ledger able to prove this.** Record the returned value in `result_digest` for `get_foundational_health_facts`, and pass a real per-turn `request_id` from the gateway so `turn_id` is per-turn.

(1)–(3) are the elimination. (4) removes the trigger. (5) is how we'd ever have caught it without a user noticing.

---

## 10. Implementation outcome (2026-07-22)

### 10.1 What was built

**One date-scoped metric authority** — `apps/ai/cos_services/metric_date.py`. Two explicitly-named semantics, never conflated:

| Function | `semantics` | Contract |
|---|---|---|
| `metric_on_date(user, domain, metric, on_date)` | `exact_date` | An observation attributed to THAT user-local date. No observation → `status="not_recorded"`. **Never** substitutes another day's value. |
| `latest_observation_on_or_before(user, domain, metric, on_date)` | `latest_on_or_before` | The most recent observation at or before the date, **with** its real `observed_on` and `age_days`. |

Both delegate to the systematic authority already behind `get_history` (`get_domain_history` → `DomainTruth.history`). No new retrieval path, no ORM access, no date math. Envelope is complete by contract: `status, semantics, value, unit, requested_date, user_local_date, observed_on, as_of, age_days, exact, freshness, confidence, source, authority` — plus evidence-integrity validation at composition.

**Shadow keys retired by delegation** (`health_facts.py`): `steps_today`, `steps_yesterday`, `weight_yesterday`, `glucose_yesterday`, `calories_yesterday` → `metric_on_date`. `current_weight` → `latest_observation_on_or_before` (this is what removed the SAE stale-snapshot shadow; it is no longer read from SAE at all).

**Carry-forward removed from the exact-date accessor** — `DailyHealthQueries.weight_on` was `recorded_at__date__lte` (silent carry-forward); it is now exact-date, and the carry-forward contract moved to the new `weight_latest_on_or_before`. This closed the last shadow, `get_domain_truth("health").current("weight_yesterday")`.

**Anchoring** — the active subject is now derived from *every* successful truth retrieval (`get_entity`, `get_history`, `get_analysis`, `get_foundational_health_facts`), carrying compact `{domain, metric}` pointers only (allow-listed in `conversation_state._SUBJECT_REF_FIELDS`; no prose, no summaries). The salience lead tells the model a date-only follow-up is the SAME metric and must be re-retrieved, never reused.

**Grounding** — general rules added to the standing constitution (ANSWER GROUNDING / TRUTH ENVELOPE / SELF-CONSISTENCY) plus an unconditional `_grounding_lead()` after the structured context. No contradiction detector, no per-question rule.

**Audit** — `turn_id` is now unique per turn (`turn-<uuid>`); the conversation is preserved separately in a new `ToolCallLog.conversation_id` (migration `ai.0037`). `audit.truth_digest()` records the returned status/value/unit/semantics/requested-date/observed-on/authority for every truth tool.

### 10.2 Runtime evidence (real model, real gateway)

`CoSGateway.respond(surface="chat")` → `model_interface` → real gpt-4o → `ToolCallLog`.

| Scenario | Before | After |
|---|---|---|
| "current weight" | `298.3` bare, no envelope (105 days stale, presented as current) | *"Your current weight is 280.4 lb, recorded today."* — `semantics: latest_on_or_before`, `age_days: 0` |
| "Yesterday's?" | 0/4 retrieved weight; 2/4 drifted to Journal | **4/4** anchored to weight, retrieved via `get_history(health, weight, yesterday)` |
| Yesterday's data missing | carried a 105-day-old value forward as yesterday's | **2/2** *"Your weight was not recorded yesterday."* |
| Curated key vs `get_history` | contradictory (value vs empty) | identical — one producer |
| Audit row | `{"keys": ["current_weight"]}` | `{"value": 280.4, "semantics": "latest_on_or_before", "observed_on": "2026-07-22", "authority": "get_domain_history:health.weight", ...}`, unique `turn_id` per turn |

### 10.3 Residual — NOT fixed, logged deliberately

**Self-consistency reasoning miss (contributing failure #5) survives.** With two conflicting prior answers planted in the transcript for the same date, *"Why did you give me two different numbers?"* still returned *"Could you specify which numbers?"* — **2/2 probes, both before and after** the constitutional rule and the salience lead were added.

Proven, not assumed: `load_conversation_history()` was verified to return all six planted turns in order, so the transcript **was** present. This is a Layer-2 reasoning failure of the current model (gpt-4o) at this prompt size, not a truth or truth-delivery defect. The rules were left in place because they are correct and general; the alternative — a WLJ-side contradiction detector — is precisely the symptom-detection this codebase forbids. Options if it matters: a stronger `COS_MODEL`, or accept it, since the *original* contradiction can no longer be produced.

**Sleep residual.** `sleep_last_night` names a relative night, not a calendar date, and keeps its existing `latest_sleep` authority. Whether "last night" maps to yesterday's or today's `SleepEntry.sleep_date` (night-of vs wake date) is a separate truth question needing its own runtime proof. It now *discloses* `semantics: latest_observation` rather than implying exact-date.

**`calories_*` derived zero.** Pre-existing, deliberate: "no food logged" = a real 0 kcal. Preserved, and now declares `semantics: derived_zero`.

### 10.4 Certification gates

`apps/ai/tests/test_metric_date_authority.py` (18) — exact-date never carries forward; carry-forward only under its own name; envelope completeness; **generic** delegation gate enumerating `_DATE_SCOPED_FACTS` so a future key cannot reintroduce the class for another metric; curated surface agrees with `get_history`; `current_weight` not from SAE; lowest-level accessor exact-date.

`apps/ai/tests/test_truth_subject_anchoring.py` (17) — anchoring from every truth surface (built through the REAL envelope wrapper: an earlier draft read a `data` key the canonical envelope does not use, so anchoring silently never fired in the live path while a hand-built dict passed); references-only storage; grounding/self-consistency rules present and general; digest records returned values; conversation id separate; turn ids unique.

---

## 8. Reproduction assets

Scratchpad (not committed): `authority_census.py` (§3 table + §3a divergence), `repro_conversation.py` (§2 four-turn real-model trace), `repro_turn2.py` (§2 routing probe ×3).

## 9. Concurrent-session flag

Uncommitted foreign work was present in the tree throughout this investigation and was **not touched, staged, or committed**: `apps/ai/cos_services/domain_history.py`, `apps/core/truth/periods.py`, `apps/core/truth/domain.py`, `apps/ai/model_interface/constitution.py`, `.gitignore`. That work is an in-flight fix for the **date-contract drift** finding of the six-question investigation (natural date expressions resolved by WLJ instead of the model) — adjacent to this class but not the same defect, and it does not affect any finding above.
