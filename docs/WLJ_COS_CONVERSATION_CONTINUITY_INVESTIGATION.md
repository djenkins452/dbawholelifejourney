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

## Certification Result (2026-08-12, worker `6be6572d`) — the minimal fix was INSUFFICIENT

The recommended smallest correction was implemented (CONSTITUTION precedence item 2 reference-resolution instruction + `_conversation_state_lead` analysis-branch fix) and certified through the real runtime. **It did not resolve the defect.** Reported honestly (results, not intentions).

**Certifications A–F (bare-pronoun follow-ups still fail):**

| Cert | Follow-up | Outcome |
|---|---|---|
| A | "Why do you think that?" | ✗ deflect ("clarify what you're referring to") |
| A | "Which part concerns you most?" · "What should I do about it?" | ✗ hijacked → "write in your journal" (`current_action`) |
| B | "Why?" | ✗ deflect |
| B | "What should I focus on this week?" | ✗ hijacked → `current_action` |
| C | "Tell me more about that." · "How long has that been happening?" | ✗ deflect |
| D | "Is that getting worse?" | ✗ deflect |
| E | "Which one concerns you more?" · "Why?" | ✗ deflect |
| F | "What should I do next?" | ✓ `current_action` (correct) |

Named follow-ups still work (A-T1 7×get_analysis; B-T2 "the biggest thing holding me back" 6×get_analysis; C-T1, D-T1, E-T1). The unit test confirms the instruction *is* in the assembled prompt — so it reached the model but was **out-weighed** at its low-salience position.

**Step-9 answers (runtime-grounded):**
1. **Solve broad multi-domain follow-ups?** No — bare pronouns still deflect.
2. **Preserve single-subject follow-ups?** Yes — named follow-ups (broad and narrow) still work.
3. **Preserve execution?** Yes — "what should I do next?" → `current_action`.
4. **Deterministic context still hijacking?** Yes — `_executive_lead` hijacks action-phrased follow-ups to `current_action` (A-T3/T4, B-T4). Now proven a **co-cause**, not a deferrable residual.
5. **Analysis-branch fix effect?** A genuine correctness fix (retained), but the deflection is not caused by that branch, so it did not move the needle alone.
6. **Continuity comparable to ChatGPT?** No.
7. **First remaining trust-breaking defect:** the bare-pronoun deflection persists **because the reference-resolution rule sits at low salience in the CONSTITUTION body while the high-salience `_executive_lead`/executive frame near the top dominates** — the exact salience dynamic the existing "leads" mechanism was invented to solve.
8. **Another code change necessary?** Yes.

**Reassessment — the "smallest prompt instruction buried in the constitution" hypothesis is FALSIFIED by runtime.** The over-scaffolding diagnosis (§1) stands and is reinforced: a low-salience instruction cannot override the high-salience deterministic frame. The corrected approach, both runtime-proven necessary:
- **(a) Raise the reference-resolution rule to the high-salience lead tier** — a compact lead placed near the user's turn (the same mechanism `_focus_lead`/`_profile_lead`/`_grounding_lead` use to survive the ~60k-char prompt). This is a placement change of the *same* instruction, not new machinery, and still no Conversation State expansion.
- **(b) The `_executive_lead` hijack is entangled with continuity** and can no longer be cleanly deferred — action-phrased reasoning follow-ups ("which part concerns you most", "what should I do about it") must resolve against the conversation, not collapse to `current_action`.

Both are prompt-level, in-Constitution (I.4/IV.2), and reduce/reposition scaffolding rather than add systems. **Stopped per Step 9 to report before implementing (b) touches the `_executive_lead` this milestone was scoped to leave alone).**

---

## DEFINITIVE ROOT CAUSE (2026-08-12, proven) — the token governor deletes the conversation history

**Both prompt-level corrections (v1 low-salience instruction; v2 high-salience lead + `_executive_lead` deference) FAILED certification.** Per the milestone's stop rule ("if certification still fails, prompt-level may be the wrong layer — STOP and investigate"), the next layer was traced — and the real defect was found. It is NOT a prompt problem and never was.

**The conversation history is assembled correctly and then DELETED before it reaches the model**, by the token governor:

- `AIService._call_api_with_tools` calls `govern_prompt(messages)` (`apps/ai/services.py:753`) on `[system, ...history..., user]`.
- `govern_prompt` (`apps/ai/conversation/token_governor.py`) enforces `WLJ_TOKEN_BUDGET_MAX` (**12,000**, `WLJ_TOKEN_BUDGET_ENABLED=True`, `config/settings.py:1620`). Over budget, **Phase 1 removes conversation history oldest-first**; Phase 2 then truncates the system-prompt tail.
- **Measured (local, commit `acc14d38`):** CONSTITUTION alone = **12,883 tokens** (already over the 12k budget); the full assembled system prompt = **74,635 chars ≈ 21,325 tokens** (production is larger — real `personal_truth`/`understanding`/`missions`/`execution_state`). Simulating a Turn-2 payload `[system, user1, assistant1, user2]` through `govern_prompt` returns **`['system', 'user']`** — `history survived? False`, `trimmed: ['conversation_history', 'system_prompt']`.

**This explains every observation:**
- **Bare pronouns deflect** ("Why?", "that") — the prior assistant answer they refer to was deleted; the model even says "a follow-up to something I mentioned earlier" but cannot see the content.
- **Named follow-ups work** ("why do you think it's slowing?") — the named subject lets the model re-retrieve fresh via `get_analysis`, needing no history.
- **Both prompt fixes failed and made it worse** — they enlarged the system prompt, increasing what the governor trims; the v2 lead literally instructs "refer to your prior answer" while the governor has removed that answer from context.

**Why the earlier "history delivered in full" finding (§6) was wrong:** it verified `load_conversation_history` in isolation (which correctly returns the turns) but never traced the payload THROUGH `govern_prompt`. A passing isolated check is not proof of the runtime path — the exact discipline WLJ mandates.

**Layer: context assembly / token budget (not prompt, not truth, not Conversation State).** The 12,000-token budget is a legacy value incompatible with the current ~21k-token model-interface system prompt and gpt-4o's 128k context window; it silently strips the conversation on every multi-turn turn.

**Smallest fix shape (recommended, NOT implemented — new layer, real blast radius; reported per Step 9):** give the model-interface path a token budget sized to fit the system prompt PLUS a real conversation-history window (the model's context window is 128k; the 12k ceiling is the defect). Options to weigh with Danny: raise `WLJ_TOKEN_BUDGET_MAX` for the model-interface endpoint specifically; or make `govern_prompt` protect the most-recent N turns from Phase-1 trimming; or reduce the system-prompt size (the CONSTITUTION is 12.9k tokens by itself — a separate simplification lever). **Blast radius:** token budget affects prompt cost and latency for every model-interface turn — a deliberate, measured change, not a silent one. **The two prompt fixes are now suspect** — once history is actually delivered, the model may resolve pronouns natively without them (they may be revertible to reduce prompt size). Re-certify (A–F + contrast) after the budget fix to decide.

---

## ROOT-CAUSE FIX — CERTIFIED (2026-08-12, worker `55361964`)

The token-governor root cause was fixed and the compensating prompt leads reverted (the clean experiment: *give the model the conversation, then get out of its way*). **Certification PASSES: delivering the conversation restored native reference resolution — no prompt scaffolding needed.**

**The fix (context-assembly layer, `55361964`):**
- `token_governor.govern_prompt`: an explicit caller budget now WINS over the setting; new `protect_recent` (default 6) guarantees the most-recent turns are NEVER trimmed (the "system + bare user sentence" condition is eliminated structurally).
- `services.py`: the tool loop passes `TOOL_LOOP_GOVERN_BUDGET = 64000` (sized to gpt-4o's 128k window; holds the ~21k system prompt + the bounded 12-turn history + margin).
- **Reverted** the v1/v2 compensating reference-resolution leads (kept the analysis-branch bug fix; preserved the Executive Over-Steer fix).

**Certifications A–F + contrast (bare-pronoun and reference follow-ups now resolve):**

| Cert | Follow-up | v2 (broken) | Root-cause fix |
|---|---|---|---|
| A | Why do you think that? | deflect | ✓ "the reasoning behind the assessment…" (4 tools) |
| A | Which part concerns you most? | journal-hijack | ✓ "nutrition, protein at 67.8%" |
| A | What should I do about it? | deflect | ✓ "to address the protein concern…" (stays on subject) |
| B | Why? | deflect | ✓ protein/lean-mass reasoning |
| C | Tell me more · How long…? | deflect | ✓ resolved (4 tools) |
| E | Which one concerns you more? · Why? | deflect | ✓ "lean mass concerns me more…" |
| D | Is that getting worse? | deflect | ✓ resolved to the nutrition subject (retrieved) |
| F | What should I do next? | ✓ | ✓ current_action |

**Step-16 answers (runtime-grounded):**
1. **Was the 12k governor deleting history?** Yes — proven: it reduced a Turn-2 payload to `['system','user']`.
2. **What budget now, and why correct?** 64,000 for the tool-loop assembly — model is gpt-4o (128k window); holds the ~21k system prompt + the 12-turn history bound + wide margin, leaving ~64k for tool-round growth + output.
3. **Trimming guarantees?** `protect_recent=6` — the immediate turns are never trimmed; only older history beyond that window is removable, and only when genuinely over budget.
4. **v1/v2 prompt leads removed?** Yes — reverted; analysis-branch bug fix kept; Executive Over-Steer preserved.
5. **Native reference resolution once history is delivered?** **Yes** — the central result. No reference-resolution scaffolding remains, and every reference follow-up resolves.
6. **"Why?"** works (A, B, E).
7. **"What should I do about it?"** stays attached to the established subject (A-T4 → protein).
8. **"Which one concerns you more?"** works after a multi-subject answer (E-T2).
9. **Standalone "What should I do next?"** still uses execution truth (F).
10. **Broad multi-domain conversation like ChatGPT?** Yes for reference follow-ups (A/C/E flow coherently across 3–4 turns).
11. **Context per turn:** system ~20.6k tokens (empty local; prod larger) + tool schemas ~11k (sent separately) + history (grows with the conversation) + user. Well within 64k govern / 128k window.
12. **Latency/cost:** single-turn ~11.5s wall-clock (incl. queue + 2s poll quantization) — same band as the pre-fix ~5–11s baseline; no material regression. Multi-turn adds history tokens (the cost of correctness).
13. **Is the ~21k system prompt now the next constraint?** It is the next *simplification* lever, not a correctness constraint. Inventory: CONSTITUTION 12,597 tokens (61%), standing JSON 6,032 (29%), reminders+leads ~2k (10%); tool schemas 11k separate. The CONSTITUTION is the obvious target if prompt reduction is later pursued (report only — not optimized here).
14. **Any continuity-specific prompt scaffolding still necessary?** **No** — proven by reverting it and still passing.
15. **Conversation State expansion necessary?** **No** — history carries the referent; `active_subject` stays a compact deterministic pointer (its role is unchanged and correct).
16. **First remaining trust-breaking defect:** the residual `_executive_lead` behavior — action-phrased *standalone-looking* questions ("what should I focus on right now?", "is there anything you're concerned about?") answer from `current_action` rather than the established conversational subject (contrast-B; D-T1). This is NOT a continuity/reference failure (the actual reference follow-ups all resolve) — it is the `_executive_lead` residual explicitly scoped OUT of this milestone, now cleanly isolated. It is the natural candidate for the next milestone.

**Architectural conclusion:** the defect was never in the prompt, the model, the truth, or Conversation State — it was context assembly silently deleting the conversation. Give the model the conversation and it is the Chief of Staff. The two prompt milestones were compensating for missing input and were correctly reverted; WLJ got *simpler*.

---

## Appendix A — Runtime evidence log (reproducible)

- **Path:** `run_cos_acceptance_conversation` (`apps/core/tasks.py:94`) → `CoSGateway.respond` per turn → `ModelInterfaceRuntime` → `ModelInterfaceService.generate` (history via `load_conversation_history`, `service.py:62`; tool loop `services.py:685`).
- **History delivery (structural repro, local):** `load_conversation_history` returns [user, assistant] with the assistant answer FULL (366/366). `_conversation_state_lead` for `{kind:"analysis", label:"overall"}` emits the "get_entity(domain='artifacts')" guidance.
- **2×2 (production, worker `f7c2da68`):** narrow+named ✓ (`get_analysis`); narrow+pronoun "Why?" ✗ (deflect); broad+named ✓ (`get_analysis`×5); broad+pronoun ✗ (deflect).
- **Seed A/B:** seeded synthesis history, no `active_subject` → "Why do you think that?" ✗ (deflect) — rules out `active_subject`.
- **Concern set:** "anything you're concerned about?" → `current_action` hijack (§15); "is that getting worse?" → pronoun deflect (§12).
- **Ruled out:** missing history (A), truncated/malformed history (B), `active_subject` (present-and-absent both fail), model incapacity (named works). **Confirmed:** over-scaffolding suppresses native pronoun binding (C).
