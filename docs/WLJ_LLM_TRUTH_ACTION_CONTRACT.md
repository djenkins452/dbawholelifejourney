# WLJ LLM Truth & Action Contract — the Canonical Architecture

> **This is the primary architecture reference going forward.** It defines the
> boundary between WLJ (deterministic truth, preferences, history, actions, audit)
> and the conversational model (reasoning, conversation, coaching, analysis,
> planning, synthesis, communication).
>
> **Status:** Canonical. **Established:** 2026-07-09.
> **Anchored on:** `WLJ_ARCHITECTURE_LAWS.md` (the Platform Constitution — Laws 0–5).
> **Supersedes the framing of:** `WLJ_CONDUCTOR_DEVELOPMENT_MODEL.md` (the retired
> "WLJ owns orchestration + reasoning" four-layer model), the `BETH_*` reasoning
> corpus, and the CoS lane/classifier architecture. Where any document describes WLJ
> *building the conversational brain*, this contract governs instead.

---

## 0. The one sentence

**WLJ owns truth. The conversational model owns reasoning.**

WLJ is no longer trying to build an assistant's mind. A frontier conversational
model already is the conversational intelligence. WLJ's job is to be the best
deterministic personal **truth, preference, history, and action platform**
underneath it.

> **We do not build another reasoning engine inside WLJ. Ever.**

### Provider-agnostic by construction

This contract never names a vendor as an architectural constant. The conversational
intelligence is referred to as **"the conversational model"** or **"the LLM layer."**
The current provider is OpenAI (`COS_MODEL`, `apps/ai/services.py`), but the provider
is a **configuration detail behind one seam**, not a boundary. Swapping providers must
never require rewriting this contract or any truth/action service. If a document or
label names a specific provider as *the* architecture, that is a defect to fix.

---

## 1. The architecture — the control-flow inversion

The important change is not the diagram; it is **who drives the turn.**

**Retired model (WLJ drove):** WLJ classified the turn, selected a capability/lane,
composed a deterministic response, and the model *narrated* it. The agentic tool loop
was a demoted fallback.

**This model (the model drives):**

```
User
  → conversational model  (owns the turn)
      → needs deterministic truth?  → WLJ Truth tool  → composed briefing + metadata
      → continues reasoning
      → needs to act?               → WLJ Action tool → deterministic execution + real result
  → model responds naturally, in the user's chosen relationship/voice
```

The model requests truth and actions from WLJ; WLJ answers deterministically and
records every request. The model is not handed raw state to recombine — it is handed
**composed, executive-quality truth** and it reasons over it.

### Where the Answer Precondition Pipeline now lives

`WLJ_ARCHITECTURE_LAWS.md` requires every personal answer to pass Intent → Scope →
Freshness → Completeness → Confidence → Strategy → Retrieve → Stability → Narrate.
Under the retired model this ran as a pre-turn gate. **Under this contract it runs
_inside each truth tool_:** when the model calls a WLJ truth tool, that tool performs
intent-scoped retrieval, freshness/completeness/confidence composition, deterministic
aggregation, and stability — and returns validated, composed truth (or an honest
"insufficient evidence"). "Reasoning last, over validated composed truth" still holds
— now per tool call rather than per turn. Laws 0–5 are **not** relaxed by the
inversion; they are re-hosted.

This reframes Foundational Invariant **F3**: the tool loop is no longer the *demoted
fallback* — it is the *primary conversational drive*. F3's spirit is preserved by the
tool contract itself (§3): tools return deterministic composed truth; the model may
assert only what a tool returned.

---

## 2. Responsibility split

| Concern | Owner | Notes |
|---|---|---|
| Reasoning, conversation, coaching, analysis, planning, synthesis, tone, wording | **The conversational model** | Do not reimplement any of this in WLJ. |
| Deciding which relationship/role fits the moment | **The conversational model** | Default relationship is a *baseline*, not a cage (§5). |
| Deterministic personal truth (health, meds, sleep, goals, calendar, finance, relationships, history) | **WLJ** | One canonical query per concept; freshness + confidence + source attached. |
| Executive priority / ranking (what matters most now) | **WLJ** | Deterministic policy fed to the model, not re-derived by it (§3.4). |
| What is worth surfacing (executive filtering) | **WLJ** | Routine clutter filtered *before* the model sees the agenda (§3.5). |
| Day continuity / orientation state across a day | **WLJ** | Per-user, per-local-day ledger the model cannot reconstruct (§3.4). |
| Actions / writes to user data | **WLJ** | All writes through the deterministic action path with confirmation + audit (§4). |
| Preferences: identity, relationship, communication, personality, truth contract | **WLJ** | Stored, versioned, per-user, serialized into the model's context (§5). |
| Learning of communication/preference from conversation | **WLJ persists; the model detects** | Explicit-first; default-deny gate; never learn around a truth/reasoning defect (§6). |
| Audit of every truth request, action, and learned preference | **WLJ** | The mechanism that makes fabrication detectable (§9). |

---

## 3. The Truth Boundary

### 3.1 Briefings, not signals (the load-bearing rule)

WLJ hands the model **composed, deterministic briefings/verdicts with the verdict
already inside** — never a pile of raw numbers for the model to recombine. This is
`WLJ_ARCHITECTURE_LAWS.md` F8 ("consumes briefings, not signals"), and it is *more*
important now, not less: when the model drives, the surest way to reintroduce
fabrication is to hand it raw figures and let it do arithmetic and interpolation
between tool calls.

- **Do:** `sleep.last_night → { value: "6h 12m asleep", freshness: current, confidence:
  high, source: "Apple Health", as_of: "07:41 today" }`.
- **Don't:** expose the raw `SleepEntry` rows and let the model compute "last night."

Raw accessors (`sleep_queries`, `HistorySeries`, `read_training_plan`,
`build_today_execution`, domain state payloads) must be exposed **only behind briefing
wrappers**, never as raw tools. The composed objects in `apps/core/truth/`
(`CurrentTruth`, `ExecutiveBriefing`, `integrity.validate_evidence`, freshness /
confidence / stability verdicts) are the reference shape.

### 3.2 The truth-tool envelope

Every WLJ truth tool returns a structured envelope carrying, at minimum:

- **value** — the composed, human-readable fact (already narrated to executive
  quality; not a raw number the model must phrase).
- **freshness** — `current | stale | pending | partial | missing` (Law 1).
- **confidence** — `high | medium | low | none`, composed deterministically from
  freshness + completeness + source + sync + evidence (Law 2).
- **source** — provenance (e.g. "Apple Health", "user-entered", "canonical goal").
- **as_of** — the timestamp the value is true as of.
- **status** — `ok | pending | empty | unsupported | insufficient_evidence | error`.

`insufficient_evidence` and `missing` are **first-class answers**, not failures. A
tool that lacks the data says so; it never substitutes a different domain's data
(Law 0) and never fabricates a plausible number.

### 3.3 What the model may only assert

> **The model may state a WLJ personal fact only if that fact was returned by a truth
> tool in this turn (or is present in the standing context).** Everything else is
> reasoning, and must be labeled as hypothesis, not presented as WLJ truth.

This is enforced structurally (§9 audit) and instructed behaviorally (§11), not by
hope. If the model needs a fact it does not have, it calls a tool; if the tool cannot
answer, the model tells the user WLJ cannot determine it.

### 3.4 Deterministic policy is truth, not reasoning

Certain judgments are **deterministic policy** that WLJ owns and **feeds** to the
model as truth. The model reasons *with* them; it must not silently re-derive them:

- **Executive priority / ranking** — health-critical (e.g. overdue medication doses)
  outranks strategic outranks opportunity outranks routine; time-of-day is decisive;
  completed/deferred items are removed. (`executive_interpretation.interpret()`,
  `_rank_priority_actions`, `_health_critical_actions`.) If the model re-ranks freely,
  it will eventually bury a clinical-safety item. WLJ hands it the ranked list.
- **Day continuity** — a per-user, per-local-day ledger of "have we oriented today /
  what has materially changed since we last spoke" (`day_continuity.assess`). The
  model cannot reconstruct this across turns; WLJ feeds it.
- **Plan-aware recovery** — whether the user's structured training plan already
  includes a rest day (`read_training_plan.has_recovery_day`), so "take a rest day"
  is never recommended against a plan that already has one.
- **Goal-question scoping** — a question about one named goal is answered about that
  goal only; the portfolio is never dumped unasked (`_scope_to_focal_goal`). This is a
  disclosure rule that shapes what truth the model is permitted to see.
- **Clock / part-of-day** — the current local time and daypart are always in context so
  no response can contradict the clock.
- **Mission continuity** — the active conversational mission/subject is carried in
  context so the model can hold one thread until it is completed, reframed, or
  replaced (the *decision* to continue/reframe/replace is the model's; the *fact* that
  a mission is active is WLJ's).

These are delivered every turn through the **executive-context envelope** (§3.6), not
gated behind a classifier.

### 3.5 Executive filtering happens before the model (decision, 2026-07-09)

WLJ decides what is worth surfacing. Routine supplement/log noise, low-value routine
clutter, and already-reconciled items are **filtered before the model sees the
agenda**. The model reasons over an **executive-quality briefing**, not raw
operational clutter. (`_agenda_worth_surfacing` and the executive filter logic are
retained as WLJ policy; only the prose-weaving is retired.)

### 3.6 The executive-context envelope (the delivery mechanism)

Because the routing/classifier layer is retired, the deterministic policies in §3.4–3.5
need a delivery path that does not depend on a lane winning. That path is a single
**executive-context envelope**: a deterministic, per-turn, pre-computed context object
(built on the existing `StandingContextService` and `interpret()`) that carries the
filtered agenda, ranked priorities, health-critical items, day-continuity decision,
clock, active mission, and freshness/confidence metadata — narration-ready — into the
model's standing context. Designing this envelope + the truth-tool briefing contract is
the keystone of the next phase; nothing else is safe to build first.

### 3.7 The external-work sandbox (decision, 2026-07-09)

When the user is discussing **outside work or general thinking that does not require
WLJ personal data**, the model must **not** receive personal WLJ context by default.
Personal truth is powerful and is used **intentionally, not sprayed into every
conversation**. This is an explicit context mode: general/external reasoning runs
without the personal-truth envelope and without personal truth tools in scope; personal
context is loaded only when the conversation is actually about the user's life. The
guarantee ("thinking out loud about work does not leak personal data") is preserved as
a **tool-availability rule**, not left to the model's discretion.

---

## 4. The Action Boundary

- **All writes go through the existing deterministic action path.** The model requests
  an action; WLJ executes it via `IntentService.execute_intent` →
  `ActionHandler.handle_*` → UAIO. The model never writes to models directly and never
  bypasses the action handlers or safety gates.
- **Destructive or ambiguous actions require confirmation.** The CRUD confirmation
  gate and `requires_confirmation` policy stay in force; settings mutations always
  confirm.
- **Results are narrated from actual execution output.** The model describes what
  *actually happened* (the returned `ActionResult`), never an assumed or hoped-for
  outcome. If an action failed, the model says it failed, with the real reason.
- **Learning Mode / UAIO suppression is honored** as the fail-closed safety gate it
  already is.
- **Streaming and non-streaming parity.** Both `/assistant/api/chat/` and
  `/assistant/api/chat/stream/` resolve the same runtime through `CoSGateway` and use
  the same truth/action tools and context. A change to one path is verified on the
  other.

---

## 5. The Preference Boundary — "how the model works with me"

Preferences configure **how the conversational model interacts with this user**. They
are stored by WLJ, versioned, per-user, and serialized into the model's context.
Five separable concerns:

1. **Assistant identity** — the user-selected display name (Beth, Steve, Coach,
   Jarvis, or nothing). *"Beth" is one user's chosen name, never a system identity.*
   A blank name resolves gracefully to a neutral default.
2. **Default relationship** — the baseline the user wants the model to be (Chief of
   Staff, Best Friend, Trusted Companion, Executive Coach, Mentor, Accountability
   Partner, Trusted Advisor, Teacher, Parent Figure, …). This is a **baseline, not a
   cage** — the model still pivots to fit the request (emotional support → trusted
   listener; data question → analyst; health trend → health analyst; planning →
   strategist), then returns to baseline.
3. **Communication preferences** — directness, response length, detail level,
   summary-first, bullets/tables/copy-boxes, ask-clarifying-questions, challenge
   assumptions, recommendation-first, avoid generic encouragement, etc.
4. **Personality overlay** — tone/flavor only (Drill Sergeant, Calm Wise Observer,
   Texas Rancher, Southern Belle, Witty Commentator). **Overlay never limits
   capability** — it flavors voice, it does not restrict what the model can do.
5. **Truth & evidence contract** — configurable with strict safe defaults (§7).

Existing fields are **consolidated, not duplicated.** `UserPreferences.cos_display_name`,
`ai_coaching_style`, `cos_response_style`, `assistant_confirm_actions`,
`assistant_proactive_checkins`; and `PersonalOperatingBlueprint.operating_style`,
`accountability_style`, `question_frequency`, `cos_learning_mode_active` already exist
and are the migration source for a consolidated AI-interaction profile. No user loses
current configuration.

---

## 6. The Learning Boundary — explicit-first (amendment, 2026-07-09)

When a user says "be more direct," "shorter answers," "don't sugarcoat," "use tables,"
"lead with the recommendation," WLJ learns and applies it.

- **The model detects the preference request; WLJ persists it.** We do **not** build a
  separate preference-inference brain. When the user states a preference, the model
  recognizes it and calls a WLJ tool to persist it (e.g.
  `set_communication_preference`). WLJ stores it; future context carries it.
- **Reuse the existing default-deny learning gate** (`apps/ai/reflection/engine.py`
  `_gate_allows_learning`). Learnable loci are **communication and preference only**.
  Truth, reasoning, and execution loci can never be learned around — a deterministic
  defect becomes an Executive Improvement Opportunity (EIO), surfaced to a human, never
  silently learned. (`WLJ_EXECUTIVE_REFLECTION_ARCHITECTURE.md`.)
- **Explicit beats inferred.** Explicit user requests are high-confidence and applied
  immediately in the current conversation and persisted. *Inferred* learning (raising
  confidence from repeated patterns) is **deferred to a later phase** with an explicit
  promotion trigger — it is where WLJ risks drifting back into building a brain, so it
  ships only after the explicit path is proven.
- **Transparency & control.** Learned preferences are visible, with source
  (explicit / learned / default), confidence, and last-updated, and are editable and
  removable. Preferences are never changed silently.
- **Safety.** Learning targets *interaction behavior*, never identity classification.
  Sensitive inferred traits are not persisted unless the user explicitly asks.

---

## 7. Evidence & Confidence Rules (strict safe defaults)

The truth/evidence contract is configurable but defaults to strict:

- WLJ is authoritative for WLJ user data.
- Never invent WLJ facts — measurements, events, history, preferences, health data,
  relationships, or actions.
- Separate known facts from hypotheses; label hypotheses.
- If evidence is insufficient, say so (Law 2). Never replace uncertainty with
  confidence.
- If more WLJ truth is required, request it through a truth tool.
- If WLJ cannot answer, tell the user WLJ cannot determine it — never a fabricated
  answer, never an "assistant unavailable" for a question a deterministic contract
  could answer (Law 4).
- Never silently answer a narrower question while implying the full question was
  answered (Law 0).
- Evidence integrity is validated before presentation: future timestamps, stale-as-
  current, previous-precedes-current, multi-source disagreement
  (`apps/core/truth/integrity.py`).

---

## 8. What the model may do naturally vs must never invent

**May do naturally (and should — do not over-constrain it):**
- Reason, plan, coach, analyze, synthesize, and write.
- Pivot role to fit the request despite the default relationship (§5.2).
- Answer general-knowledge and external-work questions (in the sandbox, §3.7).
- Do arithmetic and analysis **over truth a tool returned**, showing its work.
- Ask clarifying questions when the request is ambiguous.

**Must never invent:**
- Any WLJ personal fact not returned by a truth tool or present in standing context.
- Priority ordering that contradicts WLJ's ranked policy (§3.4).
- The outcome of an action it has not actually executed (§4).
- Freshness or confidence — those come from the envelope, not from phrasing.
- A plausible number to fill a gap the tool reported as missing.

---

## 9. Audit — the fabrication-prevention mechanism

Fabrication prevention is a **tool-contract + audit** problem, not a prompt-only
problem. Every WLJ truth request, action, and learned-preference write is logged with:
the tool called, the arguments, the returned value/status, and the turn it belongs to.
This makes it possible to prove, after the fact, **what the model was told vs. what it
said** — the only reliable way to catch a fabricated fact. The reflection layer
(`apps/ai/reflection/`) observes turns today; under this contract it (or a dedicated
tool-call audit) must also observe the **tool-call stream**. Audit is a first-class
requirement, not an afterthought.

---

## 10. How WLJ exposes truth and receives action requests (interface shape)

- **Standing context** carries the always-on executive-context envelope (§3.6) and the
  behavioral profile (§5) so the model starts every personal turn already grounded and
  in-voice, minimizing round-trips.
- **Truth tools** (built on `cos_services`: `StandingContextService`,
  `DomainStateService`, `HistorySearchService`, and the `apps/core/truth/` composers)
  answer specific deterministic questions with the §3.2 envelope.
- **Action tools** (`ActionExecutionService` → `IntentService.execute_intent`) are the
  single write surface (§4).
- **Preference tools** persist explicit communication/relationship preferences (§6).
- The provider/model is selected behind one configuration seam (§0); tools and context
  are provider-agnostic.

Latency note: prefer pre-loading the common truth into standing context over forcing a
round-trip for the obvious; budget tool calls per turn.

---

## 11. Unknown or unavailable data

The honest-unknown path is a product feature, not an error:

- Missing/pending data → say what is missing and why ("Apple Health hasn't synced
  today's sleep yet"), never a substituted or zero value.
- Out-of-scope question → answer the asked domain or defer honestly; never substitute
  available-but-unasked data.
- Deterministic-lookup failure → report the retrieval failure, never "assistant
  unavailable."
- Genuinely unanswerable by WLJ → tell the user WLJ cannot determine it, and (if
  useful) what would be needed to answer.

---

## 12. Relationship to existing docs

- **`WLJ_ARCHITECTURE_LAWS.md`** — the constitution this contract anchors on; Laws 0–5
  are re-hosted inside truth tools (§1). Unchanged in force.
- **`WLJ_CONDUCTOR_DEVELOPMENT_MODEL.md`** — reframed: the retired "WLJ owns
  orchestration + reasoning" model is replaced by Truth (WLJ) → Reasoning (model) →
  Action (WLJ) → Experience. Its product-first and eliminate-the-class disciplines are
  retained here.
- **`WLJ_EXECUTIVE_REFLECTION_ARCHITECTURE.md`** — its default-deny learning gate and
  "never learn around determinism" invariants are the mechanism behind §6 and §9.
- **The `BETH_*` / CoS lane/classifier corpus** — the reasoning/orchestration machinery
  is retired; the *truth inventories* inside those docs remain valid WLJ truth specs.
- **LAYER1/LAYER2, SAE, signal/domain-truth contracts, Visual Truth, Request-Path
  Safety, Runtime-Trace Debugging** — WLJ's retained domain; unchanged.

---

## 13. Non-negotiables

1. Do not build another reasoning engine inside WLJ.
2. Do not duplicate deterministic truth.
3. Do not hardcode any assistant name (e.g. "Beth") as a system identity.
4. Do not treat Chief of Staff as the only possible relationship.
5. Do not remove the safe deterministic action infrastructure.
6. Do not bypass deterministic truth providers.
7. Do not fabricate WLJ data — the model asserts only tool-returned truth.
8. Do not preserve old abstractions merely because they exist.
9. Do not overengineer before shipping usable value.
10. Do not change learned preferences without user visibility.
11. Do not name a provider as an architectural constant — the model lives behind config.
12. Do not spray personal truth into external/general conversation (the sandbox).

---

*Last updated: 2026-07-09 (initial — establishes the provider-agnostic LLM truth/action
contract as the canonical architecture; supersedes the Conductor four-layer model's
framing).*
