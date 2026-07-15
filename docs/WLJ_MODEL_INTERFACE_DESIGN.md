# WLJ ↔ Conversational Model Interface — Phase II Design Review

> **Design document — no implementation code, migrations, UI, or prompt engineering.**
> This designs the *complete interface* between WLJ (deterministic truth, actions, AI
> Relationship, current context, audit) and the conversational model (all reasoning). The
> Executive Context Envelope is now **one part** of this interface (the standing-context
> projection), not the whole thing.
>
> **Status:** Draft for review. **Established:** 2026-07-09.
> **Governed by:** `WLJ_PRODUCT_VISION.md` (esp. §3 Simplicity, §8 Truth).
> **Implements:** `WLJ_LLM_TRUTH_ACTION_CONTRACT.md`.
> **Supersedes:** `WLJ_EXECUTIVE_CONTEXT_ENVELOPE_DESIGN.md` (absorbed as Pillar 4 +
> the standing-context mechanism; one decision is sharpened here — see §Pillar 4).

---

## The governing question: information or reasoning?

Every field, every tool, every byte of this interface must pass one test:

> **"Is this information, or is this reasoning?"**
> Information → WLJ owns and exposes it. Reasoning → the model owns it; WLJ must not send it.

This test is stricter than "is it useful." A composed *headline*, a *diagnosis*, a
*coaching plan*, a *priority narrative* are all useful — and all **reasoning**. WLJ
exposes the deterministic facts underneath them and lets the model reason. Worked
examples:

| Candidate | Verdict | Why |
|---|---|---|
| Current local time / daypart | **Information** | The model cannot reliably know the user's clock. |
| Last night's sleep = 6h12m (freshness/source) | **Information** | A measured fact. |
| "Recovery is your priority today" (headline) | **Reasoning** | Synthesis from facts — the model authors this. |
| Overdue medication dose exists, since 8:00 AM | **Information** | A deterministic clinical fact. |
| Ranked order of what matters (health-critical first) | **Information (policy)** | Deterministic clinical-safety policy; borderline — justified below. |
| "You seem stressed — want to talk?" | **Reasoning** | The model reads the conversation. |
| Which goal the user named | **Information** | A lookup. |
| "Why has weight loss slowed?" (the explanation) | **Reasoning** | The model reasons over exposed factors. |
| Whether today is a planned rest day | **Information** | A deterministic plan fact. |

**The default is EXCLUDE.** If a field could be reasoning, it is the model's until proven
to be a deterministic fact the model cannot know.

---

## The interface at a glance

Four pillars, delivered two ways, wrapped by audit.

```
                        ┌─────────────────────────────────────────┐
                        │        Conversational Model (reasoning)  │
                        └───────────────▲───────────────▲──────────┘
        standing context (always) ──────┘               │ on-demand (model pulls)
   ┌───────────────────────────────────┐    ┌───────────┴───────────────┐
   │  P4 baseline: clock · continuity  │    │  P1 Truth services (pull) │
   │      · safety policy · capability │    │  P4 relevant truth (pull) │
   │  P3 AI Relationship (projected)   │    │  P2 Action services       │
   │  + fixed constitution (small)     │    │      (execute + confirm)  │
   └───────────────────────────────────┘    └───────────────────────────┘
        every truth read + action + preference write ──► Audit (append-only, explains)
```

- **Standing context (push, every turn):** a *small* baseline — the **Current Context
  baseline (P4)** (clock, day-continuity, clinical-safety policy, capability index) + the
  **AI Relationship projection (P3)** + the fixed constitution. Deliberately minimal.
- **On-demand services (pull):** **Truth services (P1)** answer specific questions;
  **Action services (P2)** execute writes; and **most of Current Context (P4) is
  model-pulled** — the model reaches for the deterministic truth relevant to *this*
  conversation (see Pillar 4). WLJ exposes; the model decides what it needs.
- **Audit** records every truth read, action, and preference write — to *explain*, never to
  *reason* (§8).

Two invariants across all four pillars: **(a)** everything WLJ sends is a deterministic
fact, briefing, or policy — never a reasoning artifact; **(b)** every value carries
provenance (freshness · confidence · source · as-of).

---

## Pillar 1 — Truth interface

**Answers: "What is true?"** The queryable factual substrate of the user's life.

**Exposed (as composed briefings, not raw signals):** per-domain current facts, history
series, and briefings — each wearing the standard envelope
`{ value, freshness, confidence, source, as_of, status }`. Delivered as **on-demand truth
tools** (one per domain / question class), plus a **catalog** (`truth_catalog` /
`can_answer`) in the capability index so the model knows what it can ask for.

**NOT exposed:**
- **Raw rows / raw numbers** the model would recombine (`SleepEntry` rows, raw
  `build_today_execution` lists). Wrapped behind briefings — because handing raw numbers
  invites arithmetic and interpolation, i.e. fabrication.
- **Anything derivable** from already-exposed facts (the model does the derivation).
- **Composed conclusions** ("your trend is concerning") — that is reasoning.

**First-class honest answers:** `insufficient_evidence`, `missing`, `pending` are returned
statuses, never substituted with a plausible value or another domain's data (Laws 0, 1, 2).

**Integrity pre-check:** every value passes `apps/core/truth/integrity.validate_evidence`
(future timestamp? stale-as-current? previous-precedes-current? multi-source disagreement?)
before exposure; a `suspect` verdict downgrades confidence and carries its `investigation`
text.

**Implementation status (2026-07-15).** Pillar 1 is complete across **all four**
deterministic retrieval surfaces of `DomainTruth` — the Truth Resolution Layer is now
surface-complete:
- **state** (`.state()`) → `get_domain_state` (`DomainStateService`).
- **current** (`.current()`) → `get_foundational_health_facts`.
- **history** (`.history()`) → `get_history` (`DomainHistoryService`,
  `apps/ai/cos_services/domain_history.py`) — catalog-driven over `truth_catalog()`,
  so every domain that registers `history_metrics` participates automatically. The
  capability index (Current Context) advertises the answerable `(domain, metric)`
  history pairs as `truth_history`.
- **entity** (`.describe()` / `.describe_one()`) → `get_entity` (`DomainEntityService`,
  `apps/ai/cos_services/domain_entity.py`) — the record-level surface, catalog-driven
  over `truth_catalog()`, so every domain that registers `entity_types` participates
  automatically. Returns composed `CompleteEntity` objects (never raw rows). The
  capability index advertises the answerable `(domain, entity_type)` pairs as
  `truth_entities`. Today **legacy** (memory/person/place), **medicine**
  (medication/supplement/otc/wellness), and **health** (`workout`) participate; others
  light up as they register.
- Record search → `search_history` (`HistorySearchService`).

**The interface no longer blocks any domain.** Remaining work is purely per-domain
*provider* depth behind these four surfaces — history providers (nutrition, finance,
medicine-adherence-history) and entity providers (health: workouts→exercises, body-comp
InBody, labs; nutrition: meals) — each of which "lights up" automatically through the
completed interface the moment its provider registers `history_metrics` / `entity_types`.

---

## Pillar 2 — Action interface

**Answers: "What can be done?"** The single, safe write surface.

**Request flow:** the model emits a structured **action request** (a tool call typed to the
existing intent schemas) → `ActionExecutionService.execute_action` →
`IntentService.execute_intent` → `ActionHandler` → UAIO. The model never writes directly.

**Result flow:** WLJ returns a structured **result envelope**
`{ status: ok|confirmation_required|declined|error, result: <narrated from the REAL
ActionResult>, audit_id, confirmation? }`. The model communicates what *actually happened*
— never an assumed outcome; a failure returns the real reason.

**Stateful confirmation (eliminate-the-class):** destructive/ambiguous actions store a
**server-side pending action** (reuse `PendingConfirmation`) and return
`confirmation_required`; a later user "yes" resolves the *stored* action. WLJ does not rely
on the model to reconstruct a "confirmed=true" re-call — this removes the "confirmed but
nothing happened" class. Settings mutations always confirm. UAIO / Learning-Mode
suppression remains the fail-closed gate.

---

## Pillar 3 — AI Relationship

**Answers: "How does this user want to work with their AI?"** The complete deterministic
understanding of the working relationship — no longer "mere preferences."

**Owns:** AI Name · Default Relationship · Communication Style · Personality · Trust &
Accuracy (truth/evidence preferences) · Formatting · Learning Preferences · Learned
Communication Preferences · future interaction preferences.

**Ownership vs. projection (the key rule):** **AI Relationship owns these; the interface
projects them.** The standing context carries a projection of the relationship every turn
(it is *how to show up*, not personal data — safe in every mode). Ownership, storage,
versioning, and audit stay with `AIRelationship` (the owned area).

**User-facing naming** (UI never exposes architectural terms — see
`WLJ_LLM_TRUTH_ACTION_CONTRACT.md` §5): "Your AI Relationship", "AI Name", "How should your
AI relate to you?", "Communication Style", "Trust & Accuracy", "What Your AI Has Learned".

*(Ownership design is reviewed and challenged in §9.)*

---

## Pillar 4 — Current Context

**Answers: "What does the conversational model need to know *right now*?"**

**Current Context is conversationally-relevant context, not merely temporal context.** It
is *not* "today's dashboard." Sometimes what's relevant right now is today's agenda —
sometimes it is retirement planning, a conversation about the user's daughter, payroll
analysis, a coding project, or a medical discussion. "Right now" means *this conversation*,
not *this calendar day*.

That reframing changes how the pillar is delivered:

- **Mostly model-pulled.** Because relevance depends on what is being discussed, the bulk
  of Current Context is **the deterministic truth the model pulls** for the conversation at
  hand (retirement numbers, the daughter's relationship facts, payroll figures) via the
  Truth services (P1). WLJ does not *decide* what's relevant by reasoning or classifying —
  **the model decides what it needs and pulls it; WLJ exposes the truth.** The pulled
  truth, in the context of the current conversation, *is* the current context for that turn.
- **A minimal always-on baseline** carries only what the model cannot know it needs, or
  must be told regardless of topic:
  - **Clock** — current local time + daypart (the model can't know it).
  - **Day-continuity** — orient / reorient / continue + material changes since last turn
    (`day_continuity.assess`); cross-turn state the model cannot reconstruct.
  - **Clinical-safety / executive policy** — the deterministic priority the model must not
    override (see the policy clarification below), e.g. an overdue medication dose.
  - **Capability index** — what truth/actions exist to pull.

**Deterministic policy IS allowed here; conversational reasoning is NOT.** This is the
crucial distinction, and it is *not* the same cut as the removed headline:

- **Deterministic executive policy is information, and it belongs here.** "Highest
  priority = overdue medication" is computed by fixed rules from canonical truth
  (`_rank_priority_actions` / `_health_critical_actions`). **The model must not be asked to
  re-rank deterministic executive policy** — clinical-safety ordering is WLJ's to compute
  and the model's to honor, not to second-guess. Ranking of this kind is policy, not a guess.
- **Conversational reasoning is not.** A composed *headline* ("Recovery is your priority
  today"), a narrative, a diagnosis, a mood read, a coaching plan, or an *interpretation* of
  a signal are **synthesis over the conversation** — the model authors those. The headline
  was removed for this reason (it is conversational reasoning), **not** because ranking is
  reasoning. Expose the deterministic signal + confidence + the policy order; let the model
  narrate.

**Sandbox — explicit, model-decides (Decision, 2026-07-09).** There is **no sandbox
classifier and no inferred mode.** Personal truth is not sprayed into the standing context;
it is **pulled by the model when the model determines it needs it.** In a general or
external-work conversation the model simply does not pull personal truth, so none is
exposed — the guarantee is structural (pull, not push), not a mode the model or WLJ has to
detect. WLJ's job is only to **expose the appropriate interface**; the model decides
whether to reach for personal context. (Deep/sensitive personal data is always
pull-only and audited; see §6.)

**The shrink principle → future-proofing.** Current Context must get **smaller** as models
improve, never larger. Every baseline field carries an implicit "still needed?" — when a
future model can reliably derive it from truth, **remove it.** The only permanent residents
are facts a model structurally cannot know (the clock, cross-turn continuity, clinical-
safety policy, what data exists). See the Future-Proofing principle below.

---

## 6. Boundary review — field by field

Applying "could the model already determine this itself?" → if yes, EXCLUDE.

| Candidate field | Verdict | Rationale |
|---|---|---|
| Current local time / daypart | **ALWAYS** | Model can't know the user's clock. |
| AI Name / relationship / comm style | **ALWAYS** (projected) | Deterministic user config; shapes every turn. |
| Ranked priorities (health-critical first) | **ALWAYS** | Clinical-safety policy; must not be re-derived. |
| Day-continuity decision + material changes | **ALWAYS** | Cross-turn state; unreconstructable. |
| Actionable-today state (counts/overdue) | **ALWAYS** | Deterministic; model can't know. |
| Capability index (what truth/actions exist) | **ALWAYS** | So the model knows what to pull; cheap. |
| Plan facts (rest day, next session type) | **ALWAYS** | Deterministic fact. |
| Specific domain fact (sleep avg, med list, goal detail) | **ON-DEMAND** | Pull only when the turn needs it. |
| History series / trends | **ON-DEMAND** | Large; pulled when relevant. |
| Deep personal data (relationships, finance detail, journal) | **ON-DEMAND, pull-only, audited** | Sensitive; never pushed — the model pulls it only when it decides it needs it. |
| External/general-knowledge context | **NEVER pushed; model-native** | Model already knows; personal truth is pull-only, so general conversations expose none. |
| Headline / narrative / summary | **NEVER (it's reasoning)** | The model authors it. |
| Diagnosis / coaching / mood read | **NEVER (reasoning)** | Model owns. |
| "Suggested response" / phrasing | **NEVER (reasoning)** | Model owns voice. |

---

## 7. Existing service mapping (reuse over new infrastructure)

| Interface element | Existing service | New? |
|---|---|---|
| Standing context builder (P3+P4 projection + capability index) | extend `StandingContextService.get_standing_context` | reuse (extend) |
| Current Context facts | `interpret()`/`ExecutiveSignals`, `_rank_priority_actions`, `_health_critical_actions`, `day_continuity.assess`, `build_today_execution`, `read_training_plan` | reuse |
| Relevance filter | `_agenda_worth_surfacing` / executive filter | reuse (keep filter, drop prose) |
| Truth tools (P1) | `DomainStateService`, `HistorySearchService`, `apps/core/truth/*` (`CurrentTruth`, `ExecutiveBriefing`, `integrity`, `catalog`) | reuse; wrap in envelope |
| Truth fact shape | `CurrentTruth.to_fact_dict()` | reuse |
| Action services (P2) | `ActionExecutionService` → `IntentService.execute_intent` → UAIO; `PendingConfirmation` | reuse; add stateful confirm |
| AI Relationship (P3) | projection over `UserPreferences` + `PersonalOperatingBlueprint` + new `LearnedCommunicationPreference` | 1 new table + 3 fields |
| Tool exposure + mode scoping | `tool_registry` / `tool_dispatcher` | reuse (extend for mode) |
| Audit (§8) | new `ToolCallLog`; reflection observer | 1 new table |
| Runtime slot (flag) | `CoSGateway.resolve_runtime()` | add 3rd runtime |
| Provider seam | `apps/ai/services.py` (`COS_MODEL`) | reuse (one seam) |

**Total new infrastructure: 2 tables (`LearnedCommunicationPreference`, `ToolCallLog`) +
3 fields.** Everything else is re-fronting existing deterministic services.

---

## 8. Audit — traceability, not judgment

The audit exists to **explain**, not to reason. **Do not build a second AI to judge the
first.** An append-only `ToolCallLog` (request-path-safe, fire-and-forget) records, per
turn, enough to answer exactly four questions:

1. **What truth was provided?** (every truth tool call + returned value/status/provenance)
2. **What actions were requested?** (every action request + params)
3. **What actions actually occurred?** (the real `ActionResult` / confirmation outcome)
4. **What response was returned?** (the model's final message, linked to the above)

That is the whole job. It is a ledger, not a critic. Fabrication *prevention* lives at the
data layer (the model is only handed real facts); this ledger provides *detection,
forensics, and a golden-transcript test substrate* — a spot-check and regression tool, not
a synchronous "is this fact real?" gate (which would be the forbidden second AI). Reflection
(`apps/ai/reflection/`) may *observe* this stream (append-only, never a turn-owner).

---

## 9. AI Relationship ownership — resolved

**Decision (2026-07-09):** AI Relationship is **another owned deterministic area of WLJ**
— ownership stays with WLJ, projection happens at runtime — but we **do not call it a
"domain."** "Domain" is an architectural term; users don't think in domains, and it isn't
useful to label it one. Internally it is `AIRelationship` / `AIRelationshipService`;
user-facing it is **"Your AI Relationship,"** and everything (AI Name, Default Relationship,
Communication Style, Personality, Trust & Accuracy, Formatting, Learning) fits naturally
underneath that.

- **Ownership is separate; projection is at runtime.** `AIRelationship` owns the settings;
  the standing context *projects* them each turn. It does not own the projection.
- **Do NOT build Layer-1 certification machinery for it.** A Layer-1 canonical domain
  carries heavy ceremony (canonical entity, certification gates, completeness contract,
  freshness/confidence per dimension, maturity ladder). AI Relationship is **configuration +
  a little learned data** — no external sync, no measurement freshness, no clinical-safety
  surface. Wrapping it in that machinery would violate Simplicity.
- **Implementation:** a thin `AIRelationshipService` that projects existing preference
  stores + one `LearnedCommunicationPreference` table into the composed object. One service,
  one new table, one serialization point. If it ever grows real complexity, add it then —
  not speculatively.

**One risk to flag:** three preference sources (`UserPreferences`,
`PersonalOperatingBlueprint`, learned) mean drift risk. Mitigation: the projection is
**read-only** and there is **one write path per field**; the service is the single reader.

---

## What we are NOT building

No new planner, classifier, coach, strategist, therapist, router, or reasoning engine of
any kind. Those are the conversational model's strengths. If a proposed interface element
starts to resemble any of them, it is misclassified reasoning — move it to the model.

---

## Final review — the four questions

**1. What does the model need *every* conversation (always-loaded)?**
Only what it cannot know and cannot derive: the **clock**, the **AI Relationship
projection** (how to show up), the **ranked priority policy** (clinical-safety order),
**day-continuity state + material changes**, **actionable-today state**, **plan facts**, and
a **capability index** of what it can pull. Compact by design; no narrative, no headline.

**2. What should be requested on demand?**
Specific domain facts, history/trends, briefings for a particular question, and any deeper
truth beyond the compact "now." Pull, not push — keyed to the actual question.

**3. What should never be sent unless explicitly requested?**
Sensitive/deep personal data (relationships, finance detail, journal contents) — pulled
only on an audited, intentional call; and **all personal context in `external_focus`
mode** (the sandbox). Also never sent at all: reasoning artifacts (headline, diagnosis,
coaching, suggested phrasing) — those aren't "on demand," they're the model's to produce.

**4. What can now be deleted or dramatically simplified?**
Because the model owns reasoning, the entire custom reasoning/orchestration layer can go
(from the Phase I triage) — deletable once the interface + flagged runtime prove out:
- **Routing/classification:** `classifier.py` (9-level), `p25_classifier.py`, `lanes.py`
  `route_message` + `LANE_REGISTRY`, `reasoning_mode.classify_mode`, `mission_delta` /
  `thinking_partner_delta`, `classify_need` / `classify_subjective_energy`,
  `why_explainer` / `referential` / `clarification` / `conversation_planner` routing lanes.
- **Composition/narration:** `compose_continuation`, `naturalize`, the `harmonize`/`repair`
  rewrite pass, `_agenda_narrative` prose (keep its filter), `daily_agenda` prose (keep its
  time policy), the composed `headline`.
- **Bespoke reasoning:** `reasoning/diagnosis` prompt scaffold, `general_continuity` /
  `thinking_partner` LLM wrappers (the model does this natively).
- **KEEP (all deterministic):** `interpret()`/`ExecutiveSignals`, priority ranking,
  `_health_critical_actions`, `day_continuity`, `_scope_to_focal_goal`, `apps/core/truth/*`,
  the action path + UAIO, `executive_evidence`, `commit_turn`, the reflection learning gate.

Net: a large deletion of custom-reasoning code, a small addition of interface + audit.
**WLJ gets simpler; the model does the thinking.**

---

## Future-Proofing (a binding principle)

**Do not optimize this interface for today's conversational models. Optimize it for
whatever the world's best model is five years from now.** As frontier models improve:

- The interface should become **smaller, not larger.**
- WLJ keeps owning **information**; the model keeps owning **reasoning**.
- If a future model no longer needs something because it can reason it from deterministic
  truth, **remove it.** The interface should continuously simplify.

A field that exists only to compensate for a *current* model's weakness is technical debt
the moment the next model ships. The permanent surface is only what a model structurally
cannot know: the clock, cross-turn continuity, clinical-safety policy, what data exists, and
the deterministic facts themselves.

---

## Implementation guidance — build around stable responsibilities

Do **not** implement around today's implementation details (or today's provider). Implement
around the four stable responsibilities — **Truth · Actions · AI Relationship · Current
Context** — which remain constant regardless of the provider (OpenAI, Anthropic, Google,
xAI, or any future model). **The provider is replaceable behind one seam; the interface
remains.**

Implementation order follows the Product Vision's principles, in priority order:

1. **Reuse before rebuilding.**
2. **Expose before inventing.**
3. **Information before reasoning.**
4. **Deterministic truth before conversational intelligence.**
5. **Simplicity before sophistication.**

Keep challenging assumptions whenever the codebase suggests a cleaner, simpler, or safer
solution. Three heads remain better than one.

---

## Resolved decisions (2026-07-09)

1. **Sandbox:** **explicit, model-decides.** No inferred mode, no classifier. Personal
   truth is pull-only; the model decides when it needs personal context and pulls it; WLJ
   exposes the appropriate interface. General conversations expose no personal data because
   the model never pulls it (Pillar 4).
2. **AI Relationship:** ownership separate, projection at runtime; **not called a
   "domain"** — internally `AIRelationship` / `AIRelationshipService`, user-facing "Your AI
   Relationship"; no Layer-1 certification machinery (§9).
3. **Four Pillars:** **promoted into `WLJ_PRODUCT_VISION.md`** — they now describe the
   architecture (Truth · Actions · AI Relationship · Current Context → the model), not just
   design framing.

---

*Last updated: 2026-07-09 (incorporated the four decisions: Four Pillars promoted; AI
Relationship not a "domain"; explicit model-decides sandbox; Current Context = conversation-
ally relevant not merely temporal; deterministic policy stays, reasoning does not; Future-
Proofing + stable-responsibility implementation guidance).*
