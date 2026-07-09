# WLJ Executive Context Envelope — Phase II Design Review

> **⚠ ABSORBED 2026-07-09 into `WLJ_MODEL_INTERFACE_DESIGN.md`.** Phase II broadened from
> "the envelope" to the *complete WLJ ↔ conversational-model interface*; the envelope is
> now **Pillar 4 (Current Context) + the standing-context mechanism** within that broader
> design. One decision is **sharpened** there: the composed `headline` field is dropped
> (it is reasoning, not information — the model authors it). Read
> `WLJ_MODEL_INTERFACE_DESIGN.md` as authoritative; this doc is retained for its detailed
> shapes (truth envelope, action contract, audit, service mapping), which that doc
> references.

> **Design document — no implementation code.** This is the keystone design for the
> LLM/WLJ era: the structured contract by which WLJ hands the conversational model
> everything it needs to reason — truth, behavioral context, execution state, and
> constraints — without ever teaching it how to think.
>
> **Status:** Draft for review. **Established:** 2026-07-09.
> **Governed by:** `WLJ_PRODUCT_VISION.md` (esp. §3 Simplicity, §8 Truth).
> **Implements:** `WLJ_LLM_TRUTH_ACTION_CONTRACT.md` §3.6 (the envelope), §3.2 (truth
> envelope), §4 (actions), §9 (audit), §3.7 (sandbox).

---

## The Four Pillars (the organizing frame)

WLJ is built on four pillars, three of which are WLJ's and one the model's:

| Pillar | Answers | Owner |
|---|---|---|
| **WLJ Truth** | "What is true?" | WLJ |
| **WLJ Actions** | "What can be done safely?" | WLJ |
| **WLJ AI Relationship** | "How should we work together?" | WLJ |
| **Conversational Model** | "Given all of that — what should happen next?" | The model |

**AI Relationship is a first-class deterministic domain** (it *owns* AI-interaction the
way Health owns health), newly promoted and one of WLJ's core differentiators. The
Executive Context Envelope is simply **the structured serialization of the three WLJ
pillars, handed to the fourth. The envelope ASSEMBLES/PROJECTS the pillars; it does not
OWN them** — ownership stays with Truth, Actions, and AI Relationship respectively.

---

## Design principles (binding on everything below)

1. **The envelope is a structured contract, not a prompt.** WLJ delivers *data* — typed,
   keyed, machine-shaped — not paragraphs of instruction. If a section starts to read
   like coaching the model on how to reason, it is wrong; convert it to structured truth.
2. **Separate the constant constitution from the variable envelope.** There is a small,
   fixed, provider-agnostic *constitution* (a stable system preamble: "you reason over
   WLJ truth; derive, never invent; honor the AI Relationship; call tools for more")
   and a *variable envelope* (the per-turn structured data). The constitution rarely
   changes; the envelope changes every turn. Do not smuggle per-turn data into the
   constitution or instructions into the envelope.
3. **Simpler as models improve.** The envelope carries truth + minimal policy, never
   scaffolding that compensates for a weak model. Every field must justify itself as
   *truth the model cannot derive on its own.* As models improve, fields get removed, not
   added. Budget it; measure it; prune it.
4. **Push the compact picture; pull the detail.** A small always-on envelope gives the
   model the day's executive picture and behavioral context; anything deeper is a **tool
   call** (pull), not a bigger push. This bounds envelope size and keeps personal data
   from being sprayed (see §6).
5. **Every value carries its provenance.** Freshness, confidence, source, as-of ride
   with every truth value. This is the anti-fabrication mechanism at the data layer, not
   a plea in prose.

---

## 1. Executive Context Envelope — architecture

At the start of a personal turn, WLJ composes one structured envelope and delivers it
alongside the fixed constitution. Illustrative shape (JSON is *illustrative of the
philosophy*, not prescribed — the real representation should reuse WLJ's existing
composed-truth objects; see §7–8):

```jsonc
{
  "mode": "personal",                     // personal | external_focus (see §6)
  "as_of": "2026-07-09T14:07:00-05:00",
  "clock": { "local_time": "2:07 PM", "part_of_day": "afternoon" },

  "assistant": {                          // AI Relationship — identity + relationship
    "display_name": "Beth",
    "default_relationship": "chief_of_staff"
  },
  "communication": {                      // AI Relationship — how to show up
    "directness": "high",
    "detail_level": "balanced",
    "executive_summary_first": true,
    "formatting": { "tables": "preferred", "code_blocks": "for_copyable" },
    "recommendation_first": true,
    "avoid_generic_encouragement": true
  },
  "personality_overlay": { "name": null },   // tone/flavor only; never limits capability
  "truth_contract": {                        // constants surfaced for the model to read
    "authoritative_source": "WLJ",
    "may_invent_facts": false,               // ALWAYS false — not user-settable (see §9)
    "may_derive_conclusions": true,
    "may_state_hypotheses": true
  },

  "executive_context": {                  // Pillar 1 truth — the deterministic picture
    "headline": { "value": "Recovery is the priority — sleep down 4 nights.",
                  "freshness": "current", "confidence": "high", "source": "…" },
    "priorities": [                       // WLJ-ranked; the model must not re-rank
      { "text": "Take Metformin — overdue since 8:00 AM",
        "kind": "health_critical", "why": "…",
        "freshness": "current", "confidence": "high", "source": "medicine" }
    ],
    "agenda": [ /* executive-FILTERED items only — routine clutter removed (see §7) */ ],
    "day_continuity": { "decision": "continue", "material_changes": [] }
  },
  "execution_state": {                    // Pillar 2 — what's actionable / pending
    "actionable_today_count": 3,
    "pending_confirmation": null          // or a resumable pending action (see §4)
  },

  "capabilities": {                       // what WLJ can answer/do (from truth catalog)
    "answerable_domains": ["health","sleep","goals","calendar","finance","…"],
    "note": "call a truth tool for anything not present above"
  }
}
```

**What is deliberately NOT here:** no instructions on how to reason, no examples of good
answers, no lane logic, no phrasing templates. The model already knows how to converse.

**Composition:** built deterministically, request-path-safe, cache-first, by extending
`StandingContextService.get_standing_context` (already narration-ready and cache-first).
On cache miss it returns a `pending` shell — never a live heavy computation (Request-Path
Safety). `executive_context` is `interpret()` → `ExecutiveSignals`; `day_continuity` is
`day_continuity.assess`; the AI-Relationship sections come from the AI Relationship service
(§2). No new reasoning is introduced — this is assembly of existing deterministic outputs.

---

## 2. AI Relationship — structure (the third pillar)

**AI Relationship is a first-class WLJ domain that OWNS these settings; the envelope only
assembles them.** Recommendation: expose the domain as a **composed read-model (a
projection), not a new consolidated table** — assembled per-user from existing stores
plus one new table for learned communication preferences. This respects Simplicity,
avoids a risky data migration, avoids dual-write drift, and gives exactly one
serialization point. (User-facing, this domain is "Your AI Relationship"; see the
naming map in `WLJ_LLM_TRUTH_ACTION_CONTRACT.md` §5.)

Composed shape:

```jsonc
{
  "assistant": { "display_name": "Beth", "default_relationship": "chief_of_staff" },
  "communication": { "directness": "high", "detail_level": "balanced",
                     "executive_summary_first": true, "recommendation_first": true,
                     "formatting": { "tables": "preferred" } },
  "personality_overlay": { "name": null },
  "accountability": { "level": "high", "question_frequency": "as_needed" },
  "truth_preferences": { "confidence_visibility": "when_low" },
  "learning": { "enabled": true },
  "learned_preferences": [
    { "category": "communication", "key": "response_length", "value": "short",
      "source": "explicit", "confidence": "high",
      "evidence_count": 2, "last_evidence_at": "2026-07-08" }
  ]
}
```

**Sources (map, do not duplicate):**

| Profile field | Existing source | New? |
|---|---|---|
| `display_name` | `UserPreferences.cos_display_name` | reuse |
| `default_relationship` | — | **NEW field** (UserPreferences or profile row) |
| `directness` / `accountability` | `PersonalOperatingBlueprint.accountability_style` + `question_frequency` | reuse |
| `detail_level` | `UserPreferences.cos_response_style` / `ai_coaching_style` | reuse |
| `personality_overlay` | — | **NEW field** |
| `learning.enabled` | — | **NEW field** (`preference_learning_enabled`) |
| `learned_preferences[]` | — | **NEW table** `LearnedCommunicationPreference` |

**Naming hazard to avoid:** `cos_learning_mode_active` is the existing **Learning Mode**
(a UAIO action-suppression / teaching mode) — it is **not** preference-learning-enabled.
Do not conflate them. The new `preference_learning_enabled` flag is a distinct concept.

`default_relationship` is an enum with a graceful default (`chief_of_staff` or a neutral
`assistant`); a blank display name resolves to a neutral default.

---

## 3. Truth envelope — structure

Every truth value WLJ hands the model — in the envelope or from a tool — wears the same
envelope. **Reuse `apps/core/truth/current.py :: CurrentTruth.to_fact_dict()` as the
canonical shape** (it already composes value + freshness + confidence + as-of):

```jsonc
{
  "value": "6h 12m asleep",          // PRE-COMPOSED to executive quality (briefing, not raw)
  "freshness": "current",            // current | stale | pending | partial | missing
  "confidence": "high",              // high | medium | low | none
  "source": "Apple Health",
  "as_of": "2026-07-09T07:41-05:00",
  "status": "ok"                     // ok | pending | empty | insufficient_evidence | error
}
```

- **Briefings, not signals.** `value` is the composed sentence, not a raw number the model
  must phrase or do arithmetic over (Contract §3.1). History returns a `HistorySeries`
  (points + deterministic aggregates + coverage-based confidence); briefings return
  `ExecutiveBriefing` tiers. Raw accessors (`sleep_queries`, `read_training_plan`,
  `build_today_execution`) are **wrapped**, never exposed directly.
- **`insufficient_evidence` / `missing` / `pending` are first-class answers**, not
  failures. A tool that lacks data returns that status; it never substitutes a different
  domain's data and never fabricates.
- **Integrity pre-check.** Before a value is placed in an envelope or tool result, it
  passes `apps/core/truth/integrity.py :: validate_evidence` (future timestamp? stale-as-
  current? previous-precedes-current? multi-source disagreement?). A `suspect`/`impossible`
  verdict downgrades confidence and carries its human `investigation` text.

---

## 4. Action request / response contract

The model **requests**; WLJ **executes and reports**. Single write surface:
`ActionExecutionService.execute_action` → `IntentService.execute_intent` → `ActionHandler`
→ UAIO. No direct model writes, ever.

**Request (a tool call):** `execute_action(intent_type, params)` — structured, typed to
the existing intent schemas (`apps/ai/intents/*`).

**Response envelope:**
```jsonc
{
  "status": "ok",                    // ok | confirmation_required | declined | error
  "result": "Moved 'Check on Melissa's Pillow' to 9:00 PM today.",  // from REAL ActionResult
  "audit_id": "tc_…",
  "confirmation": null               // present only when status=confirmation_required
}
```

- **Result is narrated from actual execution output** — the real `ActionResult.message`,
  never an assumed outcome. Failure → `status:error` with the real reason.
- **Confirmation is STATEFUL on WLJ's side (eliminate-the-class fix).** The recent Layer-3
  bug was a *stateless* confirmation that relied on the model to "re-call with
  confirmed=true." Design: on a destructive/ambiguous action WLJ **stores a pending
  action server-side** (reuse `PendingConfirmation` / `store_pending_confirmation`) and
  returns `confirmation_required`. A subsequent user "yes" resolves the *stored* action —
  the model does not have to reconstruct it. This removes the whole class of "confirmed
  but nothing happened." Settings mutations always confirm.
- **UAIO / Learning Mode** suppression remains the fail-closed gate. Deletion and
  `force_override` rules unchanged.

---

## 5. Tool-call audit design

Audit is the mechanism that makes "derive, don't invent" *checkable* (Contract §9).

**New append-only table `ToolCallLog`** (request-path-safe writes — fire-and-forget, never
blocks the turn):

```
ToolCallLog: id · user · turn_id · surface · tool_name · args(json) ·
             result_status · result_digest(json: the fact keys+values returned) ·
             created_at
```

- Every truth request, action request, and preference write is logged with what was
  **returned** to the model. This yields the after-the-fact reconciliation: *what was the
  model told vs. what did it say.*
- **Honest scope (challenge to the original ambition):** real-time verification that every
  WLJ fact in the model's output traces to a returned fact is itself an AI/NLP problem —
  building it would violate Simplicity (a second brain to police the first). So audit is
  **detection + deterrence + a regression-test substrate**, not a real-time output gate.
  Enforcement of derive-don't-invent is: (a) the data-layer envelope (the model is only
  *given* real facts), (b) the audit trail for spot-checks and incident forensics, and
  (c) a golden-transcript test suite. We do **not** promise a synchronous fabrication
  blocker; we promise the model is never handed a fake fact and every claim is traceable.
- **Relationship to Reflection:** `apps/ai/reflection/` currently observes *turns*.
  Extend it (or a sibling) to also observe the *tool-call stream* — the same append-only,
  observer-only posture. Reflection never becomes a turn-owner.

---

## 6. The external-work sandbox in the envelope

Guarantee (Contract §3.7, Vision §5): when the user is doing outside/general work,
personal WLJ truth is **not sprayed into the conversation.** Personal truth is used
intentionally.

**Mechanism — mode gates loading, and mode must not be a content classifier** (a
pre-turn "is this personal?" classifier is exactly the retired approach):

- **Two modes on the envelope:** `personal` and `external_focus`.
- In **`personal`** (default on the assistant surface): the full envelope is pushed
  (executive_context + AI Relationship), and personal truth/action tools are in scope.
- In **`external_focus`:** the envelope carries **only** the AI Relationship
  (relationship + communication — these are *how to talk*, not personal data) and the
  fixed constitution. **`executive_context` is omitted and personal truth/action tools are
  removed from the tool set** — so the model *cannot* reach personal data even if it tried.
  The guarantee is a tool-availability rule, not the model's discretion.
- **Pull-not-push everywhere.** Even in personal mode, personal truth *beyond the compact
  envelope* is a tool call — so "sprayed by default" is structurally limited to the small
  executive picture that is the whole point of a Chief of Staff surface.

**The one genuine open decision:** how does a turn *enter* `external_focus` without a
content classifier? Options (I recommend A, and A+C combined):
- **A. Explicit surface/affordance** — an explicit "think with me (no personal data)"
  toggle/thread the user or UI engages. Deterministic, honest, no classifier. *Recommended
  default.*
- **B. Model-declared** — the model calls `set_focus("external")` when it recognizes
  external work. Simple, but the *model* decides the privacy boundary — weaker guarantee.
- **C. Deterministic tool-scope, no explicit mode** — never push personal context; require
  the model to *pull* it via `get_executive_context`; that tool is the personal boundary
  and its calls are audited. Personal data enters only on an audited, intentional pull.
  This dissolves "mode" into "tool availability" and needs no classifier — but it also
  gives up the always-on proactive executive picture on the personal surface.

A (explicit mode) preserves the proactive CoS experience while keeping the guarantee
deterministic; C is the purest privacy stance but less proactive. **This needs your call
(§Open decisions).**

---

## 7. Mapping existing services into the new architecture

Nothing here is rebuilt; it is re-fronted. (From the Phase I capability triage.)

| Existing | New role | Change |
|---|---|---|
| `StandingContextService.get_standing_context` | **Envelope builder** (§1) | Extend to emit the structured envelope; already cache-first + narration-ready |
| `executive_interpretation.interpret()` / `ExecutiveSignals` | `executive_context` (headline, priorities, health_critical) | Reuse as-is; it does not call an LLM |
| `_rank_priority_actions`, `_health_critical_actions` | `priorities[]` (WLJ-ranked; model must not re-rank) | Reuse |
| `day_continuity.assess` | `executive_context.day_continuity` | Reuse |
| `_agenda_worth_surfacing` / executive filter | `agenda[]` filtered **before** the model | Keep the filter, drop prose weaving |
| `apps/core/truth/*` (`CurrentTruth`, `ExecutiveBriefing`, `integrity`, `freshness`, `confidence`, `catalog`, `domain.get_domain_truth`) | Truth-tool internals + per-fact envelope shape (§3) | Reuse; `catalog.can_answer()` → `capabilities` |
| `DomainStateService`, `HistorySearchService` | Truth tools (pull) | Wrap output in the §3 envelope |
| `ActionExecutionService` → `IntentService.execute_intent` → UAIO | Action tool (§4) | Reuse; add stateful confirmation |
| `tool_registry` / `tool_dispatcher` | Tool exposure + **scope gating by mode** (§6) | Extend for mode-based scoping |
| `UserPreferences` + `PersonalOperatingBlueprint` (+ new `LearnedCommunicationPreference`) | AI Relationship service (§2) | New projection service; no consolidation migration |
| `apps/ai/reflection/` (learning gate, `ReflectionEvent`) | Preference-persist gate + audit observer (§5) | Reuse default-deny gate; add tool-call observation |
| `CoSGateway.resolve_runtime()` | Feature-flag slot for the new "LLM-drives" runtime | Add a third runtime alongside ChatGPTCoS / Legacy |
| `apps/ai/services.py :: AIService` (`COS_MODEL`) | The **provider seam** | The one config seam; no provider named in the contract |

Legacy world (`personal_assistant` + `deterministic_router` + `apps/core/ai_orchestrator/`)
remains frozen and out of scope.

---

## 8. Recommended data structures (new vs. reused)

**New (minimal — the Simplicity bar):**
- `LearnedCommunicationPreference` (table) — `user, category, key, value, source
  (explicit|inferred|system_default), confidence, evidence_count, last_evidence_at,
  active, notes`. The only new persistent model needed for the profile.
- `ToolCallLog` (table, append-only) — audit (§5).
- Three new fields: `default_relationship`, `personality_overlay`,
  `preference_learning_enabled` (on `UserPreferences` or a tiny `AIProfile` row).
- `ExecutiveContextEnvelope` and `BehavioralProfile` — **composed read objects, not
  persisted** (like `StandingContext` today).

**Reused unchanged:** `CurrentTruth`/`to_fact_dict` (fact envelope), `ExecutiveSignals`,
`HistorySeries`, `ExecutiveBriefing`, `integrity` verdicts, `PendingConfirmation`,
`ActionResult`, intent schemas, the reflection learning gate.

That is one to two new tables and three fields for all of Phase II's foundation.

---

## 9. Risks

1. **Sandbox mode without a classifier** (the main open design risk) — resolved by §6-A
   (explicit mode) or §6-C (pull-only). Do not reach for a content classifier.
2. **Envelope becomes the giant prompt we're avoiding.** Guard: structured-only, a hard
   size budget, no instructional prose, and a rule that every field justifies itself as
   non-derivable truth. Review the envelope's size each phase and prune.
3. **AI Relationship source drift** (UserPreferences vs Blueprint vs Learned). Mitigate
   with one composition service and one write path per field; the projection is read-only.
4. **Fabrication enforcement is detection, not prevention** (§5). Set expectations
   honestly; do not let a stakeholder believe there is a synchronous fabrication blocker.
5. **Confirmation-state bug class** — solved by server-side pending state (§4); regression
   test it explicitly.
6. **Latency from tool round-trips.** Push the compact envelope so common truth needs no
   round-trip; budget tool calls per turn; stream.
7. **Provider variance in structured-context handling.** Keep the envelope text-
   serializable (JSON-in-context) and provider-agnostic; the seam (`AIService`) absorbs
   format differences. Streaming + non-streaming must use the same envelope + tools.
8. **`may_invent_facts` must never be user-settable to true** — it is a constant surfaced
   as data for the model to read, not a preference. Enforce in the profile schema.
9. **Learning-Mode vs preference-learning naming collision** (§2) — keep them distinct in
   code and UI.

---

## 10. Alternatives considered

- **Consolidated `AIInteractionProfile` table** (migrate all preference fields into one
  new model) — *rejected* for Phase II: risky migration + dual-write drift + violates
  Simplicity. The projection approach (§2) delivers the same serialized object with one
  new table. Revisit only if the projection proves insufficient.
- **Envelope as a pull-only tool (`get_context`) instead of a pushed object** — cleaner
  privacy (§6-C) but loses the always-on proactive executive picture. Recommended hybrid:
  push a compact envelope, pull detail.
- **Real-time fact-provenance verification of model output** — *rejected*: it is a second
  AI policing the first (anti-Simplicity). Replaced by data-layer prevention + audit +
  golden-transcript tests (§5).
- **Prose system prompt carrying the day's state** (the status quo of the retired path) —
  *rejected*: this is precisely the "giant prompt" to avoid; structured contract instead.

---

## Open decisions (need your call before implementation)

1. **Sandbox entry (§6):** A (explicit mode/affordance, keeps proactive picture) — my
   recommendation — vs C (pull-only, purest privacy, less proactive) vs a hybrid.
2. **Profile storage (§2/§8):** confirm the projection + one-new-table approach over a
   consolidated `AIInteractionProfile` migration.
3. **Four Pillars in the Vision:** the four-pillar framing currently lives here as the
   design frame. Promote it into `WLJ_PRODUCT_VISION.md` §3 area, or leave it as design
   framing? (You said it should not change the Vision — confirming.)

## Non-goals (Phase II)

No implementation code. No UI. No inferred-preference learning (explicit-first only; §2
learning is persistence, not inference). No legacy-world changes. No new reasoning
anywhere in WLJ.

---

*Last updated: 2026-07-09 (initial design draft for review).*
