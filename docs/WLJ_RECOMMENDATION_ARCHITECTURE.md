# WLJ Recommendation Architecture — observation, not prescription

**Status:** governing architecture for who authors recommendations. Established 2026-07-15
(the recommendation-authoring audit + class solution).

## The rule

> **WLJ owns deterministic truth, observations, calculations, signals, scores, patterns,
> confidence, and supporting evidence — and then STOPS. The Chief of Staff (the reasoning
> layer) owns investigation, cross-domain reasoning, and recommendations.**

The end-state pipeline:

```
deterministic truth
  → deterministic observations + domain expertise (evidence providers)
    → CoS cross-domain investigation
      → evidence-based reasoning
        → principles, not prescriptions
          → user decision
```

NOT: `single-domain trigger → canned behavioral directive`.

## The three categories (from the audit)

- **A — Deterministic truth** (status, warnings, facts, health state, progress, risk
  indicators). **Keep in WLJ.**
- **B — Deterministic observations** ("Lean mass has declined", "carb intake 3× target",
  "adherence slipped"). **Keep in WLJ** — these are the *inputs* the CoS reasons over.
- **C — Evidence-independent prescriptions** — an action-verb recommendation ("add
  resistance training", "eat less…", "set a daily alarm", "may unlock…") selected from a
  **single-domain trigger**, delivered directly to a surface (or force-led into the prompt)
  **without the cross-domain investigation that could confirm or contradict it.**
  **This is the class being corrected** — the *observation* stays; the *prescription* moves
  to the reasoning layer.

## The correction contract (every changed surface)

1. Preserve the underlying deterministic **observation**.
2. Preserve its **evidence, severity, confidence, provenance**.
3. Confirm the observation remains **reachable by the CoS reasoning layer**.
4. Confirm no user-facing surface becomes **misleading, empty, or incoherent**.
5. Confirm **no consumer expects the removed prescription as a contract field** — adjust
   contracts intentionally, never silently.
6. Do **not** merely delete strings and reduce product value.

## Preserved — domain expertise that already investigates (do NOT weaken)

These gather the appropriate cross-domain evidence before advising. They are **evidence
providers**, not the class defect — keep them:
`apps/health/services/physical_decision.py` (nutrition + fitness + recovery + hydration +
glucose), `apps/health/services/double_progression.py` (per-exercise history + recovery
holds), `apps/ai/chatgpt_cos/executive_interpretation.py` (tasks + health + purpose +
subjective — the intended cross-domain reasoning home; "the Composer narrates these
conclusions, it never invents them").

## Category-C ledger

| Surface | Status |
|---|---|
| `cdce_engine.py` detector narratives; `cos_intelligence.py` pattern `action` | **Corrected (Increment 1)** — causal/prescriptive suffixes → observation-only, matching the already-correct `detect_sleep_mood`/`detect_exercise_mood` |
| `cos_context.py` health-coaching injection + `:4041` "lead with this" mandate | **Corrected (Increment 2)** — the CoS-prompt injection now surfaces the health **observation** (primary constraint, insight/evidence, positive momentum, supporting signals) and instructs the model to REASON over it; the prescriptive `primary_action`/`secondary_action` are no longer injected and "MUST lead with the action" became "reason over this observation." Builder output shapes (`trend_analyzer`, `health_coaching_builder`) unchanged so other consumers (`nudge_engine`, etc.) are unaffected — the dashboard nudge surface is a separate later increment |
| `health_signals.py` (muscle-loss, metabolic) | **Corrected (Increment 3)** — the four prescriptive `insight` strings ("consider increasing protein and resistance training", "consider a diet break or refeed", "may need to adjust approach", "monitor for metabolic slowdown") → observation-only (the finding + its basis). Consumers verified: only `nudge_engine` reads the `insight` text (still a valid message); arbitration/narrative/intervention read structural fields (`state`/`trend`/`key`) — unaffected |
| `purpose/recommendation_service.py`, mission coach line, `goal_pace`, `significant_events._what_next` | Awaiting increment — **goal page = facts + observations only; add "Ask your CoS" affordance that passes goal context to the existing CoS path; no auto target write-back; goal changes stay explicit user-approved actions** |
| `measurement_interpretation._VERDICT_COPY` `focus` (Body Intelligence) | **Deferred — active concurrent development** (fetch main + reassess before applying the same rule; do not restore older behavior or duplicate completed work) |
| `cos_briefing/executive_summary.py`, dashboard executive-summary / recommendation files | **Deferred — foreign uncommitted work** |
