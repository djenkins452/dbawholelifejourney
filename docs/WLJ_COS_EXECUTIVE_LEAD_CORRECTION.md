# WLJ Chief of Staff — Executive Lead Responsibility Correction

**Type:** Investigate → minimal implementation → production certification. No architecture redesign. No new deterministic intent classifier. Execution Decision Authority (III.2) untouched.
**Date:** 2026-08-12
**Author:** Claude (Chief Architect seat)
**Governing principle:** *WLJ tells the Chief of Staff what is true; the Chief of Staff decides what that truth means for Danny. `current_action` is truth; whether it answers Danny's question is reasoning.*
**Runtime evidence:** production `cos-run` behavioral matrix (real `ModelInterfaceRuntime` + gpt-4o), before and after, worker-commit-verified.

---

## 1. The proven residual (from the Conversation Continuity milestone)

Once conversation history was actually delivered to the model (the token-governor fix), native reference resolution worked and the compensating prompt leads were removed. One residual remained, cleanly isolated: action-worded questions such as **"What should I focus on right now?"** — including *after the conversation had established a subject* — collapsed onto the deterministic `current_action` ("write in your journal"). This is not a conversation-history defect; it is an `_executive_lead` responsibility defect.

## 2. What `_executive_lead` was doing (runtime-mapped, post-continuity)

The lead fired whenever `current_action` had a headline and injected THREE things:

1. **The FACT** (deterministic truth, I.3) — "The single most important thing for this user right now: X. (Why it leads: reason.)" — a legitimate exposure of `current_action`.
2. **A phrase-list INTENT CLASSIFIER** (I.2/I.4 overreach) — four buckets (EXECUTION / COMPLETENESS / DAY-BRIEFING / ASSESSMENT), each a list of trigger phrases, telling the model which bucket a question falls in.
3. **A dictated CONCLUSION** (I.4 overreach) — most forcefully the EXECUTION bucket's *"you ALREADY KNOW the answer — LEAD with the item above."*

**Classification of the boundary crossing:** (1) is truth WLJ owns and should expose (I.3). (2) is intent interpretation the model owns (I.2). (3) is judgment/answer-behavior the model owns (I.4). The lead had WLJ performing (2) and (3) — deciding *in advance* that `current_action` should dominate. When the phrase-classifier mis-buckets a natural question ("what should I focus on right now?" — "focus" is ASSESSMENT, but the action shape reads as EXECUTION), the forceful imperative collapses it onto `current_action`, even over an established conversational subject. **This is exactly the deterministic-classifier-in-prose the milestone forbids.**

## 3. Behavioral matrix — BEFORE (real runtime, worker `55361964`)

| Category | Probe | Tools | Behavior |
|---|---|:--:|---|
| A execution | "What should I do next?" | 0 | ✓ leads with current_action (journal) |
| A execution | "What's left for today?" | 0 | ✓ journal + enumerated remaining items |
| B assessment | "How am I doing?" | 5 | ✓ cross-domain investigation |
| B assessment | "Is there anything you're concerned about?" | 0 | ✓ protein concern (from standing truth) |
| B drift | "What am I neglecting?" | 1 | ✓ protein + areas |
| C health-prio | "What should I focus on to improve my health?" | 0 | ✓ protein (health-grounded) |
| E day | "Walk me through my day" | 2 | ✓ completed tasks + walkthrough |
| D follow-up | "…What should I do about it?" | 0 | ✓ stays on protein |
| **Contrast-A** | **"What should I focus on right now?"** | 0 | ✗ **→ "write in your journal"** |
| **Contrast-B** | sleep established → **"What should I focus on right now?"** | 1→0 | ✗ **→ "write in your journal"** (overrides sleep) |

**First failing condition:** action-worded, standalone-*looking* questions ("what should I focus on right now?") collapse onto `current_action` — and even an established conversational subject (sleep) is overridden. Root: the phrase classifier + the "you ALREADY KNOW the answer — LEAD with X" imperative.

## 4. The minimal correction (implemented)

**Collapse the four behavioral buckets + the imperative into ONE compact factual exposure that delegates the judgment to the model.** Prefer deletion / narrowing / converting-command-to-fact over adding rules (the prompt got *smaller*).

- Surface `current_action` as a **deterministic FACT** — "WLJ's current top execution priority is X (why: reason)" — explicitly *not automatically the answer*.
- **Delegate**: "YOU decide what they are actually asking and whether this fact answers it." For "what to do / what's next" it leads; for anything broader it is *one input* to retrieve-and-reason-across, never a collapse target; for a list/day/everything-left, cover the rest (tasks + calendar); **and when the conversation has already established a subject, stay with it — this current action does not override it.**
- **Preserve** the one still-necessary deterministic protection: never hand the job back (don't ask the user to pick an area or name their own tasks — they are visible).
- **Removed:** the phrase-list classifier (four bucket headers) and the "you ALREADY KNOW the answer — LEAD with the item above" imperative.

**No deterministic intent classifier, no regex/phrase routing, no new model call, no new high-salience rule tree.** `_executive_lead` shrank from ~835 → 380 tokens. Execution Decision Authority (III.2) is untouched — the fact still has exactly one producer; only the *answer behavior* is returned to the model.

**Constitutional:** strengthens I.2 (model owns interpretation), I.4 (model owns judgment), IV.2 (simpler as the model improves), IV.4 (expose, don't command); preserves I.3 (WLJ owns the calculation) and III.2. No Article changed; no Review.

## 5. Certification — AFTER

*(Recorded after worker deploy of the correction — see the Certification section below.)*
