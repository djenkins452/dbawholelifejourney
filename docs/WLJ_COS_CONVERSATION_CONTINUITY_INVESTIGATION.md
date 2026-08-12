# WLJ Chief of Staff — Conversation Continuity Runtime Investigation

**Type:** Investigation only. No production behavior changed. No code modified. No Constitutional change proposed. No Conversation State expansion proposed.
**Date:** 2026-08-12
**Author:** Claude (Chief Architect seat)
**Runtime evidence:** production `cos-run` multi-turn (`?script=`) probes through the REAL `ModelInterfaceRuntime` + gpt-4o (worker `f7c2da68`); local structural reproduction of `load_conversation_history` + `_conversation_state_lead`; code trace.
**Governing docs obeyed:** `WLJ_CONVERSATION_STATE_ARCHITECTURE.md`, `01_READ_FIRST…ARCHITECTURE`, `02_WLJ_CONSTITUTION`, `03_ENGINEERING_OPERATING_GUIDE §3e/§3f`, `04_DANNY_WORKING_PREFERENCES`.

---

## 1. Executive conclusion

**The continuity defect is NOT what the previous investigation hypothesized, and it must not be fixed by expanding Conversation State.** Runtime evidence overturns the "broad multi-domain continuity fails" framing. The real, isolated defect is:

> **The Chief of Staff does not resolve bare elliptical / pronoun follow-ups ("Why?", "that", "is that getting worse?", "tell me more") to its own immediately-preceding answer — even though the full prior answer is in the model's context.** When the user *names* the subject, continuity works perfectly — including a five-domain re-synthesis. The failure is pure **reference resolution**, and it happens equally in broad and narrow conversations.

Three things are **proven false** as causes:

- **Not missing history.** Turn 2 receives the prior user turn AND the *complete, untruncated* prior assistant answer (structural repro: 366/366 chars). (§6)
- **Not `active_subject`.** The failure occurs identically **with** a coherent single-subject `active_subject` (narrow "Why?") and **without** any `active_subject` at all (seeded history). Its presence or absence does not change the outcome. (§9–§10)
- **Not a model limitation.** gpt-4o reasons happily over the same content the instant the reference is named (a bare ChatGPT resolves "Why?" natively). (§12)

The cause is **over-scaffolding (Hypothesis C)**: WLJ's ~40 k-char CONSTITUTION relentlessly conditions the model to *identify a concrete retrievable subject → retrieve deterministic truth → ground every value*, and **nothing anywhere tells it that a bare elliptical/pronoun follow-up simply continues its own prior turn.** A topic-less "Why?" has no subject to retrieve, so the over-conditioned model falls back to asking the user to clarify — the exact behavior the rest of the prompt tries hard to suppress, leaking through the one gap none of the "do NOT ask which…" rules cover. This is the **same class** as the Executive Over-Steer: deterministic scaffolding overriding conversational intelligence the model already possesses.

**Smallest correct fix:** ONE general, prompt-level reference-resolution instruction that restores the native behavior — an elliptical/pronoun follow-up refers to your own last answer; reason from it (retrieve deeper only if needed); never ask what they mean when your prior turn supplies the referent, unless they clearly changed topic. **No Conversation State change. No new tool. No memory system. No deterministic reference.** The architecture gets *smaller* — the prior investigation's "let Conversation State hold the assessment" proposal is **refuted and unnecessary** (§13/§19). *Conversation belongs to the conversation.*

A **second, separate residual** (§15): `_executive_lead` still hijacks some follow-ups ("which part concerns you most?", "is there anything you're concerned about?") to `current_action` ("write in your journal") — the same over-steer class as the prior milestone, distinct from the pronoun defect.

---

## 2. Exact failing runtime path

Multi-turn conversation through the real pipeline (per-turn tool attribution via `run_cos_acceptance_conversation`, `apps/core/tasks.py:94`):

```
Turn 1 "How am I doing overall?"
 → CoSGateway.respond(surface=chat, conversation=conv, stream=False)
 → ModelInterfaceRuntime.respond → load_conversation_history(conv) = []   (first turn)
 → persist user msg → ModelInterfaceService.generate(history=[])
 → tool loop: model emits N get_analysis (one round) → serial dispatch → synthesis round
 → persist assistant answer (the full synthesis prose)
 → conversation_state.record_turn(subject = LAST get_analysis, last-wins)   apps/ai/model_interface/service.py:1031
Turn 2 "Why do you think that?"
 → ModelInterfaceRuntime.respond → load_conversation_history(conv) = [user1, assistant1]   ← FULL prior answer present
 → build_standing_context (incl. active_subject from Turn 1) + _system_prompt (CONSTITUTION + 6 leads)
 → generate(history=[user1, assistant1]) → messages = [system, user1, assistant1, user2]
 → model DEFLECTS: "Could you clarify what you're referring to?"     ← reference-resolution failure
```

The model receives a coherent `[system, user1, assistant1, user2]` transcript and still fails to bind "that" to `assistant1`.

## 3. Working single-subject control path

Identical path; the only difference is the Turn-2 wording. "How is my weight loss going?" → **"Why do you think it is slowing?"** → the model calls `get_analysis` and reasons about the weight trend. The transcript assembly is the same; the *named subject* ("it is slowing" = weight loss slowing) lets the model bind the reference. This is the control that isolates the variable (§12).

## 4. Turn-1 OpenAI context

`messages = [ {system: CONSTITUTION + attachment/conversation-state/executive/focus/profile leads + JSON(standing_context) + grounding lead + completion reminder}, {user: "How am I doing overall?"} ]`. History empty (first turn). The model fans out (`get_analysis` ×N in one round) and synthesizes — this half works well (established in prior milestones).

## 5. Turn-2 OpenAI context

`messages = [ {system: same standing frame, now including active_subject from Turn 1}, {user: "How am I doing overall?"}, {assistant: "<full Turn-1 synthesis>"}, {user: "Why do you think that?"} ]`. **The prior answer is present and complete.** What is *absent* is any instruction that a bare "Why?/that" continues `assistant1`. What is *present and competing* is ~40 k chars of retrieve-a-concrete-subject conditioning plus a high-salience `current_action` lead ("what matters right now: write in your journal").

## 6. Conversation-history delivery behavior

**Delivered, in full.** `load_conversation_history(conversation, limit=12)` (`apps/ai/model_interface/service.py:62`) loads the last 12 `role∈{user,assistant}` messages with non-empty content, chronologically, as `[{role, content}]`, and `_call_api_with_tools` prepends them between the system prompt and the current user turn (`apps/ai/services.py:733-748`). Local structural repro confirmed Turn 2 receives the prior user turn AND the **complete** prior assistant answer (366/366 chars, `ASSISTANT_FULL_DELIVERED=True`). It is called BEFORE persisting the current user message, so the current turn is not duplicated. **Hypotheses A (missing history) and B (malformed/truncated) are false.**

## 7. Transcript retention / truncation behavior

12-turn rolling window (`_HISTORY_LIMIT=12`), token-governed (`govern_prompt`). For a 2–4 turn conversation there is no truncation. Assistant content is stored and replayed verbatim (no summarization, no transformation). The transcript is a faithful conversational record — exactly what §11 of the prompt (transcript ≠ truth, but IS conversational context) requires. No defect here.

## 8. Tool-call / tool-result retention behavior

**Turn-1 tool calls and tool results are NOT persisted into the conversation** — they live only inside that turn's ephemeral `messages` array in the tool loop; the persisted `AssistantMessage` carries only the final prose answer. So on Turn 2 the model sees the *prose synthesis* but not the six `get_analysis` payloads that produced it. **This is appropriate and not the defect** — the prose answer is sufficient to explain "why," and when a follow-up genuinely needs the numbers, the model re-retrieves (as it did for every *named* follow-up, §12). Persisting raw tool evidence into the transcript would bloat context and risk staleness. The evidence-reuse posture (§13) is correct; the defect is purely reference binding.

## 9. Conversation State behavior

Carried inside the Executive Context Envelope as a facts-only field (per `WLJ_CONVERSATION_STATE_ARCHITECTURE.md`); surfaced to the model by `_conversation_state_lead` (`service.py:354`). Runtime finding: **it is not the cause of the continuity failure.** The failure reproduces with it empty (§10, Case A) and with it populated by a coherent single subject (§12, narrow "Why?"). Where it *does* misbehave is a secondary quality issue: for a `get_analysis` subject it emits partly-incoherent guidance (§10).

## 10. `active_subject` lifecycle

- **Written** deterministically after each turn by `record_turn` from `turn_capture["subject"]` — the subject of the **last** truth retrieval in the turn (`service.py` dispatch sets it per-call, last-wins; `conversation_state.py:242`).
- **Single-subject.** After six `get_analysis` calls, `active_subject` = the sixth only, as `{kind:"analysis", ref:"<domain>.overall", label:"overall"}`.
- **Injected** by `_conversation_state_lead`. For a `get_history` metric (kind="metric") it has a good branch ("a follow-up asking WHY is about THIS metric — reason about it"). For a `get_analysis` subject (kind="analysis") it falls into the **else/entity branch**, which (local repro) emits: *"ACTIVE SUBJECT: the analysis 'overall'… a short follow-up ('tell me more', 'it/that/this') refers to THIS… To re-check it, retrieve it with get_entity (domain='artifacts' for an uploaded file)."* — a contentless referent plus **nonsensical artifact-retrieval guidance** for an analysis subject (`service.py:419-426`).
- **Proven not the primary cause:** narrow "Why?" fails **despite** a coherent `active_subject` explicitly naming the subject and stating that short follow-ups refer to it; and broad "Why do you think that?" fails **without** any `active_subject` (seeded history). The lead's analysis-branch incoherence is a real *quality* bug but is **not** what causes the deflection.

## 11. Context salience / precedence findings

The system prompt front-loads high-salience leads ("check BEFORE page context"), a ~40 k-char CONSTITUTION built around *identify-the-concrete-ask → retrieve → ground*, and a forceful `current_action` lead. Against all of that, a bare "Why?" carries almost no salience and no retrievable subject. Two consequences observed:
- **Reference starvation:** with no instruction that an elliptical follow-up = the prior turn, and heavy pressure to find a concrete subject, the model deflects to clarification.
- **Referent competition:** the `current_action` lead asserts a *different* "current topic" ("write in your journal"), so some follow-ups bind to *it* instead of the prior answer (§15). The deterministic scaffolding competes with, and sometimes overrides, the conversational referent.

## 12. Natural-reference probe results (the decisive 2×2)

Real production runtime, per-turn tools captured. **The controlling variable is bare-pronoun vs named-subject — NOT broad-vs-narrow:**

| Turn 1 | Turn 2 | Tools | Result |
|---|---|:--:|---|
| How is my weight loss going? | Why do you think **it is slowing**? *(named)* | `get_analysis` | ✓ reasoned about the weight trend |
| How is my weight loss going? | **Why?** *(pronoun)* | (none) | ✗ "clarify what you're asking about" |
| How am I doing overall? | Why do you think **I am doing well overall**? *(named)* | `get_analysis` ×5 | ✓ full 5-domain re-synthesis |
| How am I doing overall? | **Why do you think that?** *(pronoun)* | (none) | ✗ "provide more context / specify" |
| Is there anything you're concerned about? | **Is that getting worse?** *(pronoun)* | (none) | ✗ "clarify what specific area" |

**Named references always work (broad and narrow). Bare pronouns always fail (broad and narrow).** Broad continuity is *not* broken — reference binding is. Additional isolation:

- **Seed A/B (rules out `active_subject`):** seed the full synthesis as history with NO tool calls (so NO `active_subject`) → "Why do you think that?" → **still deflects.** Absent state, same failure.

## 13. Evidence-reuse findings

Correct and efficient. Every *named* follow-up that needed depth re-retrieved exactly what it needed (one `get_analysis` for a weight "why"; five for a whole-life "why") rather than blindly replaying everything or nothing. Prose answers are retained; raw tool payloads are not (§8), which is the right trade-off (fresh, not stale). **No model conclusion is cached as deterministic truth, and the fix in §18 keeps it that way** — it does not store AI prose as state; it lets the model reason over the transcript it already has and re-retrieve at its own discretion.

## 14. Follow-up latency findings

Preserved. Named follow-ups measured in the same ~5–11 s band as the prior milestone (single-domain "why" ~5–7 s; broad "why…overall" re-synthesis ~11 s). **The recommended fix (§18) is a prompt sentence — it adds no retrieval, no round trips, no state, and cannot degrade latency.** It also *reduces* wasted turns: today a deflected "Why?" costs a full model round that produces nothing usable and forces the user to re-ask.

## 15. Residual proactive-over-steer finding

**Separate defect, same class as the Executive Over-Steer.** "Is there anything you're concerned about?" and "Which part concerns you most?" collapsed to `current_action` ("write in your journal") with zero retrieval. This is `_executive_lead` (`service.py:526`) capturing these phrasings into its execution bucket — NOT the pronoun-binding issue (those turns weren't asking to clarify a pronoun; they were redirected to the next task). It shares the root pattern — *a deterministic lead overriding the conversational thread* — and would be closed by the same "narrow the trigger" shape used last milestone. Documented here; a scoped fast-follow, not bundled into the continuity fix.

## 16. First failing layer

**Layer 2/4 — the model-facing reasoning frame (the prompt/scaffolding), not Layer 1 truth and not conversation persistence.** Truth is correct; history is delivered; state is not the cause. The failure is that WLJ's prompt suppresses the model's native reference resolution. Two distinct instances: (1) **pronoun/elliptical binding starvation** (primary); (2) **`_executive_lead` follow-up hijack** (residual, §15).

## 17. Root cause with file:line / runtime evidence

- **Primary — an ABSENCE.** No instruction in `apps/ai/model_interface/constitution.py` (CONSTITUTION) or the `service.py` leads tells the model that a short elliptical/pronoun follow-up ("why?", "that", "how so?", "tell me more", "and?") continues its own immediately-prior answer. Meanwhile the CONSTITUTION's "FIRST INTERNAL QUESTION" (`constitution.py:40-68`), ANSWER GROUNDING (`:80-89`), RETRIEVE-vs-REASON (`:230-245`), and INVESTIGATE-BEFORE-CONCLUDING (`:294-330`) blocks condition the model to seek a concrete retrievable subject. A topic-less "Why?" fits none of it. Runtime proof: the 2×2 (§12) + seed A/B.
- **Secondary quality bug.** `_conversation_state_lead`'s else/entity branch (`service.py:419-426`) applies artifact/entity guidance ("retrieve with get_entity(domain='artifacts')") to a `get_analysis` subject, producing an incoherent referent for broad answers. Real, but not the deflection cause.
- **Residual.** `_executive_lead` (`service.py:526`) over-captures follow-up phrasings → `current_action` (§15).

## 18. Smallest compliant correction

**One general, unconditional reference-resolution instruction, prompt-only** (in the CONSTITUTION's conversation/retrieval-precedence region), approximately:

> "A short elliptical or pronoun follow-up — 'why?', 'why that?', 'how so?', 'tell me more', 'what about it?', 'and?', 'is that getting worse?' — continues the conversation you are already in. 'That / it / this' refers to YOUR OWN immediately-preceding answer and its subject(s). Resolve it exactly as you would in a normal conversation: reason from your prior answer, and re-retrieve the underlying deterministic truth (get_analysis / get_history / …) if explaining or extending it needs more depth. Never ask the user what they are referring to when your previous turn plainly supplies the referent — unless they have clearly changed the subject."

Properties: **general** (no per-question, no keyword list that must be maintained), **removes the need for deterministic continuity machinery** (so it *shrinks* architecture), **prompt-only** (same mechanism as the existing leads), **reversible**, and it **restores** a native model capability the scaffolding suppressed rather than adding a new one. Pair (optionally, same change) with fixing the `_conversation_state_lead` analysis-branch (§17 secondary) so it stops emitting `get_entity(artifacts)` guidance for analysis subjects.

**Explicitly NOT part of the fix:** no Conversation State field, no "active assessment" object, no new tool, no memory system, no cached AI prose.

## 19. Conversation State Expansion Test

**Not triggered — and the prior investigation's proposal fails it.** The previous milestone suggested letting Conversation State "hold the assessment we just did." Runtime evidence refutes it: narrow "Why?" fails with a perfectly coherent single-subject `active_subject`, so a richer assessment object would not have fixed the primary defect; and broad "Why do you think that?" is fully answerable from the transcript the model *already has*. Per the Expansion Test (`03 §3f`), an expansion is justified only if it replaces a deterministic system AND eliminates duplicate logic — this would do neither; it would *add* an AI-derived state store to recreate what conversation history already carries, risking exactly the model-authored-prose-as-state the architecture forbids. **The correct move is the opposite of expansion: a one-line instruction that lets the transcript do its job.**

## 20. Constitutional assessment

**Fully inside the Constitution. No Article changed, weakened, or inverted. No Review required.** The fix strengthens **I.4** (the model owns reasoning/conversation — reference resolution is reasoning, returned to the model) and **IV.2** (as frontier models improve, WLJ gets simpler — we delete the *need* for continuity machinery). It touches no deterministic authority (III), no Current Context (II), no action path (I.7), and stores no truth in the model. It honors the prompt's own principle: *truth belongs to WLJ, reasoning to the model, and conversation to the conversation.*

## 21. Regression risks

- **Over-binding after a topic change:** an instruction to bind pronouns to the prior turn could, in principle, make the model assume continuity when the user actually switched topics. **Mitigated** by the explicit "unless they have clearly changed the subject" clause and by the model's native topic-shift detection (which already works — named new subjects route correctly today). Low risk.
- **Interaction with `active_subject`:** the new instruction and the (fixed) `_conversation_state_lead` must agree — both should point the pronoun at the prior turn's subject(s). Fixing the analysis-branch incoherence (§17) removes the only conflicting signal.
- **No latency/truth/action regression:** prompt-only; no new retrieval, no state write, no tool.
- **Test strategy:** the §12 2×2 + the multi-turn natural-reference sets (broad/health/drift/pronoun/comparison chains) as a permanent natural-conversation certification, scored on whether pronoun follow-ups resolve without deflection AND named follow-ups still work — run on Danny's account pre/post, worker-commit-verified.

## 22. Recommended implementation milestone

> **Conversation Continuity Correction — restore native reference resolution (prompt-only).**

1. Add the one general reference-resolution instruction (§18) to the CONSTITUTION.
2. Fix the `_conversation_state_lead` analysis-branch incoherence (§17 secondary) in the same change (small, same file).
3. Certify through the real runtime with the §21 probe suite: every bare-pronoun follow-up ("Why?", "that", "is that getting worse?", "which part concerns you most?") resolves to the prior turn; every named follow-up still works; latency unchanged.
4. **Fast-follow (separate, optional in the same milestone):** narrow the `_executive_lead` residual (§15) so "concerned about / which part / focus on there" follow-ups are not hijacked to `current_action` — same shape as the Executive Over-Steer fix.

Deferred to the following milestone (unchanged): the truth-exposure gaps (Relationships history, Projects tasks, Finance entities) via the existing `DomainTruth` pattern. **Continuity first.**

**Definition of done answer — "Why can ChatGPT maintain 'what we were just talking about' while the WLJ CoS sometimes cannot?"** Because ChatGPT resolves an elliptical follow-up from the transcript natively, whereas WLJ hands the model the same transcript but wraps it in ~40 k chars of retrieve-a-concrete-subject conditioning with no instruction to bind a bare pronoun to the prior turn — so the model, starved of a retrievable subject, asks the user to clarify. The prior user turn IS delivered; the prior assistant answer IS delivered (in full); prior tool evidence is not (correctly); history is not truncated or transformed; deterministic state (`active_subject`) is NOT overriding it (proven). **A code change is required, and the smallest correct one is a single prompt-level instruction that returns pronoun resolution to the model — not a new memory layer.**

---

## Appendix A — Runtime evidence log (reproducible)

- **Path:** `run_cos_acceptance_conversation` (`apps/core/tasks.py:94`) → `CoSGateway.respond` per turn → `ModelInterfaceRuntime` → `ModelInterfaceService.generate` (history via `load_conversation_history`, `service.py:62`; tool loop `services.py:685`).
- **History delivery (structural repro, local):** `load_conversation_history` returns [user, assistant] with the assistant answer FULL (366/366). `_conversation_state_lead` for `{kind:"analysis", label:"overall"}` emits the "get_entity(domain='artifacts')" guidance.
- **2×2 (production, worker `f7c2da68`):** narrow+named ✓ (`get_analysis`); narrow+pronoun "Why?" ✗ (deflect); broad+named ✓ (`get_analysis`×5); broad+pronoun ✗ (deflect).
- **Seed A/B:** seeded synthesis history, no `active_subject` → "Why do you think that?" ✗ (deflect) — rules out `active_subject`.
- **Concern set:** "anything you're concerned about?" → `current_action` hijack (§15); "is that getting worse?" → pronoun deflect (§12).
- **Ruled out:** missing history (A), truncated/malformed history (B), `active_subject` (present-and-absent both fail), model incapacity (named works). **Confirmed:** over-scaffolding suppresses native pronoun binding (C).
