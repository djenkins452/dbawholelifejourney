# Beth Phase 0 — Cognitive Mode Shadow Classifier + Model A/B Evaluation

**Status:** INERT BUILD COMPLETE (2026-06-07) — Steps 1, 3, 4, 6, 7 + A/B scaffold built & tested (21/21 pass, golden-corpus mode accuracy 100%). Steps 2 (migration), 5 (live hook), flag flips, and A/B API execution remain HELD for approval.
**Type:** Log-only, flag-gated, zero response-behavior change, fully reversible.
**Author:** Claude Code architecture review, 2026-06-07
**Predecessor docs:** Beth Evolution Strategy (review), Beth Architecture Pressure Test (round 2).

---

## 0. Purpose & Non-Goals

### Purpose
Phase 0 produces **evidence** to decide whether to build a real Analyze reasoning lane,
*before* writing any user-visible behavior. It answers five questions:

1. **Is Analyze traffic real?** (volume of "what do you think / how am I doing / should I be worried")
2. **Is Beth misrouting Analyze questions?** (predicted Analyze → actual Retrieve/Execute/task)
3. **Are deterministic routes too greedy?** (cheap-fix hypothesis A)
4. **Is the `gpt-4o` model itself the ceiling?** (cheap-fix hypothesis B)
5. **Is the legacy `is_asking_for_analysis` branch helping or contaminating?**

### Non-Goals (explicitly out of scope for Phase 0)
- Changing any response Beth gives.
- Building the real Analyze context packages (that is Phase 2).
- Building the bounded reasoning prompt (Phase 3).
- Routing any traffic to a new model in production.
- Any database write that affects user-facing state.

### Hard guarantee
Every artifact in this plan is **observation-only**. The shadow classifier runs *after*
the real routing decision is already made and logs what it *would* have decided. It never
feeds its output back into the response path. Model A/B runs candidate generations
**asynchronously and off the response path**; the candidate answer is never shown to a user.

---

## 1. Proposed Files

| File | Status | Purpose |
|------|--------|---------|
| `apps/ai/cognitive_mode/__init__.py` | NEW | Package marker |
| `apps/ai/cognitive_mode/shadow_classifier.py` | NEW | Pure function: message → predicted mode/domain/confidence/reason. No side effects. |
| `apps/ai/cognitive_mode/taxonomy.py` | NEW | Mode + domain enums, package-requirement registry, single source of truth |
| `apps/ai/cognitive_mode/telemetry.py` | NEW | `record_mode_observation(...)` — writes one row, wrapped in try/except, never raises |
| `apps/ai/cognitive_mode/probe.py` | NEW | Non-invasive hook called once per message from `send_message()`; gathers the actual-route facts and calls telemetry |
| `apps/ai/cognitive_mode/golden_corpus.py` | NEW | The labeled golden prompts + expected-mode assertions |
| `apps/ai/cognitive_mode/model_ab.py` | NEW | Offline/async candidate-model generation + scoring harness (no production wiring) |
| `apps/ai/models_cognitive.py` *(or new migration in `apps/ai/models.py`)* | NEW MODEL | `CognitiveModeObservation`, `ModelABResult` (see §2) |
| `apps/ai/tests/test_shadow_classifier.py` | NEW | Unit tests for classifier against golden corpus |
| `apps/ai/tests/test_cognitive_mode_telemetry.py` | NEW | Asserts telemetry never raises, never mutates response |
| `apps/ai/management/commands/beth_mode_report.py` | NEW | Read-only report command: aggregates observations into the success metrics in §8 |
| `apps/ai/management/commands/beth_model_ab.py` | NEW | Runs the offline A/B over the golden corpus + sampled real prompts |
| `config/settings.py` | EDIT (additive) | New flags (§3), all default OFF |

**One integration touch-point only:** a single guarded call inside
`send_message()` (and `send_message_stream()`) in `apps/ai/personal_assistant.py`,
placed *after* the real route is decided. Behind a flag, wrapped so any failure is a no-op.

---

## 2. Data Model / Log Structure

Two new models in the `ai` app. Both are append-only telemetry; neither is read on the
request path.

### `CognitiveModeObservation`
```
id                      BigAutoField
created_at              DateTimeField(auto_now_add=True, db_index=True)
request_id              CharField(64, db_index=True)   # correlate with AssistantMessage
user                    FK(User, on_delete=CASCADE, db_index=True)

# --- prediction (shadow) ---
predicted_mode          CharField(choices=ModeChoices) # retrieve|analyze|analyze_coach|execute|reflect|unknown
predicted_domain        CharField(32, null=True)       # weight|glucose|nutrition|tasks|faith|journal|...
mode_confidence         FloatField                     # 0.0–1.0 from classifier
mode_reason             CharField(200)                 # short rule trace, NOT raw message

# --- actual routing (observed) ---
actual_route_taken      CharField(64)                  # RouteCategory or 'intent' or 'llm_fallthrough'
actual_handler          CharField(120, null=True)      # function/intent name that handled it
was_terminal            BooleanField                   # did deterministic router terminate?
deterministic_router_match  CharField(64, null=True)   # RouteResult.route_name if any
cos_shortcut_match      BooleanField(default=False)    # "what should I do" etc.
llm_intent_selected     CharField(64, null=True)       # intent_type chosen by function-call, if any
legacy_analysis_branch_fired  BooleanField(default=False)  # is_asking_for_analysis == True

# --- derived flags (computed at write time) ---
route_mismatch          BooleanField(db_index=True)    # predicted analyze* but actual != reasoning path
greedy_route_flag       BooleanField(db_index=True)    # predicted analyze* but a deterministic Retrieve route terminated it

# --- package gap analysis ---
package_needed          JSONField(default=list)        # fact keys the predicted package would require
package_available       JSONField(default=list)        # fact keys the actual path had access to

# --- privacy-safe message features (see §7) ---
message_hash            CharField(64, db_index=True)   # sha256(normalized message + per-deploy salt)
message_len             IntegerField
message_features        JSONField(default=dict)        # normalized non-PII features (verbs, anchors, domain tokens)
message_text            TextField(null=True)           # ONLY populated when WLJ_BETH_MODE_LOG_RAW=True (off by default)
```

**Indexes:** `(created_at)`, `(route_mismatch)`, `(greedy_route_flag)`, `(predicted_mode)`, `(user, created_at)`.
**Retention:** see §7. A management command prunes rows older than the retention window.

### `ModelABResult`
```
id                  BigAutoField
created_at          DateTimeField(auto_now_add=True)
source              CharField(16)        # 'golden' | 'sampled'
prompt_ref          CharField(120)       # golden id, or observation request_id
message_hash        CharField(64)
context_fingerprint CharField(64)        # hash of the grounded context package fed to BOTH models
model_a             CharField(40)        # 'gpt-4o'
model_b             CharField(40)        # candidate, e.g. frontier reasoning model
answer_a            TextField            # candidate generations — internal review only
answer_b            TextField
scores_a            JSONField            # {groundedness, helpfulness, specificity, hallucination_risk, context_use, tone, actionability}
scores_b            JSONField
auto_flags          JSONField(default=list)  # programmatic checks (ungrounded number, banned phrase, etc.)
human_reviewed      BooleanField(default=False)
human_verdict       CharField(16, null=True) # 'a' | 'b' | 'tie'
reviewer_notes      TextField(null=True)
```

Both models live behind the same migration. The migration is **additive only** (new tables,
no alterations to existing tables) — so it is reversible and cannot corrupt existing data.
*Note: per project rule, adding tables still requires `makemigrations`; this counts as a
DB migration and therefore needs explicit "go" before it ships (see §11/§12).*

---

## 3. Feature Flags

All new flags follow the existing `getattr(settings, 'WLJ_*', default)` convention
(see `apps/ai/deterministic_router.py:485-507`). **All default to the safe/off value.**

| Flag | Default | Effect when ON |
|------|---------|----------------|
| `WLJ_BETH_SHADOW_MODE_ENABLED` | `False` | Runs the shadow classifier + writes `CognitiveModeObservation`. Pure observation. |
| `WLJ_BETH_MODE_LOG_RAW` | `False` | Also stores raw `message_text` (PII). Off by default; only for short, consented debugging windows. |
| `WLJ_BETH_MODE_SAMPLE_RATE` | `1.0` | Fraction of messages to observe (allows 1.0 for the single-user owner account; lower for broader rollout). |
| `WLJ_BETH_MODEL_AB_ENABLED` | `False` | Enables the **async, off-path** candidate generation for sampled Analyze prompts. Never shows candidate to user. |
| `WLJ_BETH_MODEL_AB_CANDIDATE` | `''` | Candidate model id (e.g. a frontier reasoning model). Empty = A/B inert. |

Kill switch: setting `WLJ_BETH_SHADOW_MODE_ENABLED=False` instantly and completely
disables all Phase 0 behavior with zero residue.

---

## 4. Shadow Classifier Logic

`shadow_classifier.classify(message, user, page_context) -> ModePrediction`

A **deterministic, rule-based-first** classifier (no LLM call on the request path — we are
not adding latency or cost to live traffic). It is intentionally simple and auditable;
its job is to *measure*, not to be the final production classifier.

```
ModePrediction = {
    mode: 'retrieve'|'analyze'|'analyze_coach'|'execute'|'reflect'|'unknown',
    domain: str|None,
    confidence: float,
    reason: str,         # e.g. "analyze: judgment_verb('what do you think')+domain('weight')"
    package_needed: [str],
}
```

### Mode signals (illustrative, refined against the golden corpus)
- **Retrieve** — point-fact phrasing + single domain anchor: "what is / what was / latest / current / last X". Short, factual, time-pointed.
- **Analyze** — judgment/interpretation verbs over a domain or the whole life: "what do you think", "how am I doing", "what patterns", "evaluate my trend", "should I be worried", "am I on track". No explicit ask-to-act.
- **Analyze+Coach** — an Analyze signal **plus** a prescriptive ask: "should I change anything", "do I need to push harder / slow down", "what should I adjust". (See §4.1 — we log it as a sub-type of Analyze, not a separate top-level lane.)
- **Execute** — next-action / prioritization: "what should I do next", "what's the best use of the next hour", "biggest risk", "what should I fix".
- **Reflect** — emotional / faith / journal interpretation: "I feel off", "what do you notice in my journaling", "am I living my values".
- **Unknown** — none fire confidently; logged as such (a high Unknown rate is itself a finding).

### 4.1 Taxonomy pressure-test (asked for explicitly)
**Recommendation: collapse to FOUR top-level lanes, log Coach as a flag, not a lane.**

```
Retrieve | Analyze | Execute | Reflect      (top-level modes)
+ coach_tail: bool                          (a flag ON the Analyze prediction)
```

Rationale (from the round-2 pressure test):
- Analyze and Analyze+Coach **share the identical context package** — they differ only in
  whether a recommendation tail is appended. Making Coach a separate top-level mode doubles
  the classifier's confusion surface for zero context-assembly benefit.
- Every additional top-level mode is a new misroute surface, and WLJ's bug history *is*
  routing seams. Fewer lanes = fewer misroutes.
- We still capture the Coach signal (as `coach_tail=True`) so Phase 0 can measure how often
  users want a prescriptive tail — without paying the classifier cost of a 5th class.

So the logged `predicted_mode` uses four values + `unknown`; `analyze_coach` in the data
model is stored as `mode='analyze'` with `message_features.coach_tail=True`. (The enum keeps
`analyze_coach` as an accepted value only for backward-compat in reporting.)

### Probe (actual-route capture)
`probe.observe(message, user, route_result, intent_result, legacy_branch_fired, ...)` runs
**after** `classify_and_route()` and intent recognition have already produced the real
decision. It reads the already-computed `RouteResult` (category, route_name, domain,
is_terminal), the selected intent (if any), and the `is_asking_for_analysis` outcome, then:
1. calls `shadow_classifier.classify(...)`,
2. computes `route_mismatch` / `greedy_route_flag`,
3. computes `package_needed` (from taxonomy) vs `package_available` (from what the actual
   path touched),
4. calls `telemetry.record_mode_observation(...)`.

`route_mismatch` = predicted ∈ {analyze, reflect} **and** actual ∈ {deterministic Retrieve fact, task/execute intent, single-metric lookup}.
`greedy_route_flag` = predicted ∈ {analyze} **and** `was_terminal=True` **and** `deterministic_router_match` is a single-fact Retrieve route.

The entire probe is wrapped:
```python
try:
    if _shadow_mode_enabled() and _sampled(user):
        observe(...)
except Exception:
    logger.debug("shadow mode probe failed (non-fatal)", exc_info=True)
# response path continues regardless
```

---

## 5. Model A/B Design

Goal: decide whether the **model** (gpt-4o) is the ceiling, holding the **grounded context
constant**. We are testing reasoning quality, not prose.

### Safety design
- Runs **off the response path** entirely. Two execution modes:
  1. **Offline** (preferred for Phase 0): `beth_model_ab` management command iterates the
     golden corpus + a sample of logged Analyze prompts, rebuilds the *same* grounded context
     that Beth would have used, and generates with **both** `gpt-4o` and the candidate. Writes
     `ModelABResult`. Never touches live traffic.
  2. **Async shadow** (optional, flag-gated): when `WLJ_BETH_MODEL_AB_ENABLED=True`, a sampled
     live Analyze message spawns a background generation with the candidate model using the
     *already-built* context. The candidate answer is **logged only**, never returned. The
     user still gets the normal gpt-4o answer through the unchanged path.
- **Identical context** to both models (same `context_fingerprint`) so the only variable is
  the model. This is the whole point — we are isolating the model lever.

### Scoring (NOT fluency)
Each answer scored on a 1–5 rubric across seven axes, by an **LLM judge** (a separate model
instance with a strict rubric) **and** programmatic auto-flags, then sampled for human review:

| Axis | What it measures | Auto-check available? |
|------|------------------|----------------------|
| groundedness | every claim traces to a provided fact | yes — flag numbers/dates not in context |
| helpfulness | does it answer the actual question | partial |
| specificity | uses the user's real data vs generic | yes — generic-phrase detector |
| hallucination_risk | invented facts / causal overreach | yes — fact + causal-claim detector |
| context_use | uses the supplied package vs ignores it | yes — package-token overlap |
| tone | grounded executive, not life-coach template | partial |
| actionability | concrete next step when warranted | partial |

The decisive comparison is **groundedness + specificity + hallucination_risk** — not tone.
A candidate model that is more fluent but equally generic is **not** a win.

### Human review
`ModelABResult` rows surface in a read-only admin/report. Reviewer marks `human_verdict`
(a/b/tie) blind to model identity where feasible. ≥30 reviewed Analyze prompts gives a
directional signal; the gate is in §8.

---

## 6. Golden Test Corpus

`golden_corpus.py` — labeled real failure prompts. Each entry:

```python
{
  "id": "weight_history_analyze",
  "message": "What do you think about my weight history?",
  "expected_mode": "analyze",
  "expected_domain": "weight",
  "coach_tail_expected": False,
  "must_not_route_to": ["create_task", "deterministic_single_fact", "execute"],
  "required_package": [
      "weight_current", "weight_start", "weight_velocity",
      "weight_trend_30_60_90", "waist_change", "body_comp_deltas",
      "med_changes_in_window", "weight_goal_target", "healthy_loss_threshold",
      "age", "diabetes_context", "data_completeness"
  ],
  "success_criteria": "predicted analyze+weight; does not route to task/single-fact"
}
```

Initial corpus (all from real failures you reported):

| id | prompt | expected_mode | domain | must_not_route_to |
|----|--------|---------------|--------|-------------------|
| weight_history_analyze | "What do you think about my weight history?" | analyze | weight | task list / single fact |
| weight_eval_coach | "No, I want you to evaluate my trend and tell me if I need to be doing better, or slower, or anything else you pick up." | analyze (coach_tail) | weight | single fact / generic advice |
| glucose_last_event | "What was my last blood glucose reading and when?" | retrieve | glucose | weekly average |
| protein_today | "How am I doing on protein today?" | retrieve | nutrition | sleep/macro coaching |
| body_comp_compare | "Compare my body measurements to last time." | retrieve→analyze | body_composition | "I don't have them" |
| perfect_amino_source | "Where is Perfect Amino coming from?" | retrieve (provenance) | nutrition/intake | generic |
| what_next | "What should I do next?" | execute | — | generic advice |
| feel_off | "I feel off lately." | reflect | journal/mood | clinical/generic |
| overall_checkin | "How am I doing overall?" | analyze | cross_domain | task list |
| should_i_worry | "Should I be worried?" | analyze | (context-dependent) | dismissive one-liner |

The corpus doubles as: (a) the shadow classifier's unit-test oracle, and (b) the model A/B
prompt set. It will grow as logged real prompts reveal new shapes.

---

## 7. Privacy Safeguards

WLJ holds health, journal, faith, and personal data. Logging defaults to **minimal and
de-identified**.

| Question | Decision |
|----------|----------|
| Log raw user message? | **No, by default.** Only when `WLJ_BETH_MODE_LOG_RAW=True` for a short, owner-consented debugging window. |
| Hash the message? | **Yes.** `message_hash = sha256(normalize(message) + per_deploy_salt)` for dedup/correlation without storing content. Salt is per-deploy so hashes aren't cross-correlatable externally. |
| Store only normalized features? | **Yes — this is the default payload.** `message_features` holds non-PII signals: detected verbs, anchors, domain tokens, length bucket, coach_tail bool. No names, numbers, or free text. |
| Where do logs live? | Same Postgres DB, new dedicated tables (`CognitiveModeObservation`, `ModelABResult`). No third-party logging. Not emitted to stdout/log files (which ship to infra) beyond `logger.debug`. |
| Retention? | **30 days** for `CognitiveModeObservation` (raw text, if ever enabled, **7 days**). `ModelABResult` answers retained until reviewed + 30 days, then text fields nulled. Pruning via scheduled management command. |
| How to review? | Read-only management command `beth_mode_report` (aggregates only) + Django admin list (features/flags, raw text hidden unless explicitly enabled). |
| Model A/B candidate answers | Contain PII-derived reasoning. Stored only with `WLJ_BETH_MODEL_AB_ENABLED`, reviewed internally, text nulled after review window. Never sent anywhere except the model API (same provider already used). |

The `gpt-4o`/candidate model calls send the same grounded context Beth already sends today,
to the same provider — **no new data leaves the system** that wasn't already leaving it.

---

## 8. Success Metrics & Stop Conditions

### Success criteria (the architecture is worth building if…)
| Metric | Target | Meaning |
|--------|--------|---------|
| Shadow classifier accuracy on golden corpus | **≥ 85%** exact-mode | Taxonomy is crisp and learnable |
| Analyze-class share of real traffic | **material (define ≥ ~10%)** | The lane is worth building |
| Analyze route-mismatch rate | **high (e.g. ≥ 40% of predicted-Analyze)** | The lane is genuinely missing, not occasionally missed |
| Greedy-route rate | **low** | Problem is a missing lane, not greedy Retrieve routes |
| Model A/B: candidate wins on groundedness+specificity | **measured delta**, with CI | Quantifies the model ceiling |
| Legacy branch contamination rate | **measured** | % of `legacy_analysis_branch_fired` where package was execution-shaped but question was domain-analytical |

### Stop / rethink conditions (do NOT build the lane if…)
| Signal | Implication |
|--------|-------------|
| Analyze traffic is rare (< ~5%) | Optimizing a corner case — fix routing + model instead |
| Greedy-route rate is dominant | Cheaper fix: make Retrieve routes conservative; no new lane |
| Classifier can't beat ~85% even after tuning | Mode boundaries aren't crisp; a discrete classifier just relocates misrouting — reconsider single rich-context path |
| Model swap alone closes most of the quality gap | Bottleneck was the model — re-scope hard, defer the lane |
| Telemetry shows the legacy branch *helps* more than it harms | Re-examine the diagnosis before investing |

These thresholds are pre-registered **before** looking at data, to avoid post-hoc rationalization.

---

## 9. Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Probe throws and breaks a live response | Low | Fully wrapped in try/except → no-op; unit test asserts response unaffected on probe exception |
| Telemetry write adds latency | Low | Write is a single insert; can be deferred to a background thread (same pattern as existing post-response intelligence at PA:1052) |
| Rule-based shadow classifier is itself inaccurate, biasing the "is the lane missing" answer | Medium | Validate classifier against golden corpus first; report its own accuracy alongside findings; treat <85% self-accuracy as "instrument not trustworthy yet" |
| Privacy leak via raw message logging | Low (default off) | Raw logging flag default off, 7-day retention, owner-consented only |
| Model A/B cost (double generation) | Low | Offline mode over a bounded corpus + sampling; not full live traffic |
| Pre-registered thresholds are wrong | Medium | They're directional; document reasoning so they can be revised transparently, not silently |

---

## 10. Exact Implementation Sequence

Each step is independently committable and reversible. Steps 1–7 are pure additions behind
an off-by-default flag.

1. **Taxonomy + classifier (pure, no wiring).** `taxonomy.py`, `shadow_classifier.py`,
   `golden_corpus.py` + `test_shadow_classifier.py`. Provable in isolation; zero runtime impact.
   → Gate: classifier ≥85% on golden corpus before proceeding.
2. **Data model + migration.** `CognitiveModeObservation`, `ModelABResult`. Additive tables.
   *(requires "go" — it's a migration; see §12.)*
3. **Telemetry writer.** `telemetry.py` + `test_cognitive_mode_telemetry.py` (asserts never-raises).
4. **Probe.** `probe.py` — assembles observation from already-decided route. Unit tested with
   synthetic route results. No PA wiring yet.
5. **Single PA hook.** Add the guarded `observe(...)` call in `send_message()` and
   `send_message_stream()`, behind `WLJ_BETH_SHADOW_MODE_ENABLED` (default False).
   *(This touches the live file — see §11/§12 for the approval boundary.)*
6. **Flags in settings.py** (additive, all safe defaults).
7. **Report command.** `beth_mode_report` — read-only aggregation.
8. **Enable on owner account only.** Set `WLJ_BETH_SHADOW_MODE_ENABLED=True` +
   `SAMPLE_RATE=1.0` scoped to the owner user. Collect ~1–2 weeks.
9. **Model A/B harness.** `model_ab.py` + `beth_model_ab` command. Run offline over golden
   corpus + sampled logged prompts. *(candidate model call — see §12.)*
10. **Analyze findings → decision.** Produce a Phase 0 results report against §8 metrics.
    Recommend build / re-scope / stop.

---

## 11. What Can Be Implemented Without Further Approval

Per the operating instruction (safe / log-only / flag-gated / no behavior change / reversible),
the following can proceed to **code** without another check-in — but I will still bring the
result before enabling anything:

- ✅ Steps 1, 3, 4, 6, 7 (taxonomy, classifier, telemetry writer, probe, **flag definitions
  defaulting OFF**, read-only report command) — these are inert until a flag is flipped.
- ✅ `golden_corpus.py` and all unit tests.
- ✅ `model_ab.py` harness code (not run against the API; just the scaffolding) and the
  `beth_model_ab` command file.

All of the above are no-ops in production until a flag is set, and none alter any response.

---

## 12. What Still Requires Approval Before Shipping

These cross a guarded boundary and I will **hold** for explicit "go":

- ⛔ **The migration (Step 2).** Adding tables is a DB migration; per project policy it ships
  on deploy. Requires "go" even though it's additive.
- ⛔ **The PA hook (Step 5).** It edits the live `personal_assistant.py` request path. Even
  though it's flag-gated and wrapped, it touches the file that produces Beth's answers —
  approval required before commit/deploy.
- ⛔ **Flipping any flag ON in production** (`WLJ_BETH_SHADOW_MODE_ENABLED`,
  `WLJ_BETH_MODE_LOG_RAW`, `WLJ_BETH_MODEL_AB_ENABLED`).
- ⛔ **Running the model A/B against the candidate API** (Step 9 execution) — cost + sends
  context to the model; approval for the candidate model id and run scope.
- ⛔ **Enabling raw message logging** (`WLJ_BETH_MODE_LOG_RAW`) — PII; explicit consent + window.

---

## Appendix A — Integration point (reference)

Hook site: `apps/ai/personal_assistant.py :: send_message()` and `send_message_stream()`,
immediately *after* the real route is resolved (the `_classify_route(...)` call at
`personal_assistant.py:1512` returns `_route_result`) and after intent recognition. The probe
reads, never writes, the response path.

Flag convention mirrors `apps/ai/deterministic_router.py:485-507`
(`getattr(settings, 'WLJ_*_ENABLED', default)`).

Telemetry models live alongside existing observability infra in
`apps/core/ai_observability/` (where `EngineRun` lives) — or in the `ai` app if FK locality
to `User`/`AssistantMessage` is cleaner. Final placement decided at implementation.
