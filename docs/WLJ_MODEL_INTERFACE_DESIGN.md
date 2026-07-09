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
        standing context (always) ──────┘               │ on-demand
   ┌───────────────────────────────────┐    ┌───────────┴───────────────┐
   │  P4 Current Context (compact)     │    │  P1 Truth services (pull) │
   │  P3 AI Relationship (projected)   │    │  P2 Action services       │
   │  Capability index (what exists)   │    │      (execute + confirm)  │
   │  + fixed constitution (small)     │    └───────────────────────────┘
   └───────────────────────────────────┘
        every truth read + action + preference write ──► Audit (append-only, explains)
```

- **Standing context (push, every turn):** a compact projection of **Current Context (P4)**
  + **AI Relationship (P3)** + a **capability index** (what Truth/Actions exist) + the fixed
  constitution. This is the Executive Context Envelope.
- **On-demand services (pull):** **Truth services (P1)** answer specific questions;
  **Action services (P2)** execute writes. The model calls these when it needs more.
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
versioning, and audit stay with the AI Relationship domain.

**User-facing naming** (UI never exposes architectural terms — see
`WLJ_LLM_TRUTH_ACTION_CONTRACT.md` §5): "Your AI Relationship", "AI Name", "How should your
AI relate to you?", "Communication Style", "Trust & Accuracy", "What Your AI Has Learned".

*(Ownership design is reviewed and challenged in §9.)*

---

## Pillar 4 — Current Context (the sharpened pillar)

**Answers: "What is happening right now that is relevant?"** The time-sensitive executive
"now," pushed every personal turn. This is the pillar most prone to scope creep, so the
information/reasoning test is applied hardest here.

**INCLUDE (deterministic "now" facts the model cannot know):**
- **Clock** — current local time + daypart. (Pure information; the model can't know it.)
- **Actionable state today** — deterministic overdue / due / actionable items and their
  status, from `build_today_execution` (wrapped, not raw). What exists, not what to do.
- **Ranked priority (policy)** — the deterministic executive-value order, health-critical
  first (`_rank_priority_actions` / `_health_critical_actions`). *Borderline* — see the
  challenge below; included because it encodes clinical-safety policy the model must not
  re-derive, not because it is a good guess.
- **Day-continuity decision** — orient_full / reorient_delta / continue, and the list of
  **material changes** since last turn (`day_continuity.assess`). Cross-turn state the
  model cannot reconstruct.
- **Plan facts** — e.g. today is a planned rest day (`has_recovery_day`). A fact, not advice.
- **Relevance-filtered agenda** — routine/log clutter and reconciled items removed
  (`_agenda_worth_surfacing`). This is a *what-data-to-include* policy (WLJ's job), not
  reasoning about the data.

**EXCLUDE — now moved to the model (sharpened decisions):**
- **~~Headline / executive summary~~** — a composed "Recovery is your priority" sentence is
  **synthesis = reasoning.** *Change from the envelope draft:* drop the `headline` field;
  ship the ranked facts and let the model author the headline. (This is the clearest win
  from the sharper test.)
- **Any narrative / prose framing** — the model writes.
- **Coaching, diagnosis, mood read, "what you should do"** — reasoning.
- **Insight/prediction *interpretations*** — expose the deterministic signal + confidence;
  the model interprets.

**The shrink principle:** Current Context must get **smaller** as models improve. Every
field carries an implicit "still needed?" — when a model can reliably derive it, remove it.
The only permanent residents are facts a model structurally cannot know (the clock,
cross-turn continuity state, clinical-safety policy, and what data exists).

**Sandbox:** in `external_focus` mode Current Context is omitted entirely and personal
truth tools leave scope — only AI Relationship (how to talk) + the constitution remain
(Contract §3.7). Mode is set by an explicit affordance, never a content classifier (§6
open decision below).

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
| Deep personal data (relationships, finance detail, journal) | **ON-DEMAND, sandbox-gated** | Sensitive; never pushed. |
| External/general-knowledge context | **NEVER (personal); model-native** | Model already knows; sandbox forbids personal data. |
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

## 9. AI Relationship ownership — reviewed and challenged

**Your framing:** AI Relationship is "another deterministic area of WLJ," like Health or
Calendar. **My assessment: conceptually yes, implementationally no — and the distinction
matters.**

- **Conceptually, treat it as a first-class domain.** It gives clean ownership ("AI
  Relationship owns AI interaction"), a natural UI home ("Your AI Relationship"), and the
  right mental model (the envelope projects it, doesn't own it). Keep this framing.
- **Implementationally, do NOT build a full Layer-1 certified domain.** A Layer-1 domain in
  WLJ carries heavy ceremony (canonical entity, certification gates, completeness contract,
  freshness/confidence per dimension, maturity ladder). AI Relationship is **configuration +
  a little learned data** — it has no external sync, no measurement freshness, no clinical
  safety surface. Wrapping it in Layer-1 machinery would violate Simplicity (building
  infrastructure the problem doesn't require).
- **Recommendation: "domain in concept, projection in implementation."** A thin
  `AIRelationshipService` that projects existing preference stores + one
  `LearnedCommunicationPreference` table into the composed object. One service, one new
  table, one serialization point. If it ever grows real domain complexity, promote it then
  — not speculatively.

**One genuine risk to flag:** three preference sources (`UserPreferences`,
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

## Open decisions (unchanged from the envelope draft — still the gate)

1. **Sandbox entry:** explicit mode/affordance (recommended — keeps the proactive picture)
   vs. pull-only (purest privacy). No content classifier either way.
2. **AI Relationship implementation:** confirm "domain in concept, projection in
   implementation" (§9).
3. **Four Pillars in the Vision:** promote, or leave as design framing?

---

*Last updated: 2026-07-09 (initial — the complete WLJ ↔ model interface; absorbs and
sharpens the Executive Context Envelope draft).*
