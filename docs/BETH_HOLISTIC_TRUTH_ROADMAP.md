# Beth Holistic Truth Roadmap

> **Prioritized, phased plan to move Beth from "health Chief of Staff + search box"
> to a whole-life Chief of Staff with holistic truth coverage.** Companion to
> `BETH_TRUTH_COVERAGE_AUDIT.md` and `BETH_TRUTH_GAP_ANALYSIS.md`.
> **Date:** 2026-06-26 · **No implementation — planning only.**

## Strategic insight

**The truth already exists.** WLJ's SAE computes rich canonical state for ~18
domains; the dashboard and proactive engine already surface ~9. The holistic-truth
work is therefore **not building truth — it is wiring existing canonical state into
Beth's three thin surfaces:** (1) foundational facts, (2) the reasoning lane, (3)
briefings/check-ins. This makes the whole roadmap a **framework extension** (P6/P13)
over already-validated engines, not a new-truth project — low architectural risk,
high CoS value.

This is also the natural maturation of **P25 (Personal Truth First)**: P25 routes
PERSONAL requests to `answer_from_wlj_truth`; today that dispatch only has health
depth. The roadmap fills out the PERSONAL branch domain by domain.

## Design rules (apply to every phase)

1. **Consume canonical engines, never recompute (P24).** Each domain reads its SAE
   `build_*_state` / canonical contract; no parallel truth.
2. **Framework-first (P6/P13).** Add a domain via a **registry-keyed curator** that
   mirrors the existing `HealthWorkingMemoryCurator` — domain-scoped, executive-clean
   (no enums/labels/source paths, GB-3.2/GB-5), with a **deterministic fallback (P5).**
3. **Domain isolation (P11).** Each curator returns only its own domain's truth — no
   cross-domain contamination (the health-scope guarantee, generalized).
4. **Privacy gates where ratified.** Finance, medical/labs, documents get explicit
   sensitivity handling (summaries ambient; raw detail on explicit ask).
5. **Shadow-then-activate** for any routing-affecting change (P25 discipline).
6. **No durability/notification/registry-order regressions.** Reuse the lane registry.

---

## Phase 0 — Governance & scaffolding *(no behavior change)*
- Ratify the **Truth Parity principle** (P-candidate): *"If WLJ knows it about Danny,
  Beth should know it, unless an explicit ratified reason says otherwise."* Record the
  three ratified exceptions (finance raw ledgers, medical diagnosis, document content)
  as *sensitivity gates*, not exclusions.
- Stand up a **Domain Curator Registry** contract (`domain -> curator + fallback +
  truth-scope`) so each later phase is "register one curator," not new plumbing.
- Add a **truth-coverage ops view** (which domains reach reasoning/facts/briefing) so
  drift is visible. *(Read-only.)*

## Phase 1 — Foundational facts for the whole life *(cheap, deterministic, high-frequency)*
Wire ~10 non-health fast-facts straight from existing SAE state (no LLM, no new truth):
- Finance: `net_worth`, `budget_status`, `next_bill` *(behind sensitivity gate)*
- Goals: `active_goal_count`, `next_goal_deadline`, `goal_completion_rate`
- Faith: `reading_plan_current`, `prayer_streak`
- Execution: `tasks_due_today`, `today_workout`, `journal_streak`
- Labs: `last_lab_result` / `latest_abnormal_lab`
- **Risk:** LOW (deterministic lookups, same pattern as the 12 health facts).
- **Value:** removes the most common "Beth doesn't know simple facts about me" misses.

## Phase 2 — Reasoning beyond health (the biggest lever) *(P25 PERSONAL-branch depth)*
Add reasoning curators + intents for the highest-value domains, **in order of
value × readiness**:
1. **Goals / Purpose** ("how are my goals tracking", "what am I behind on") — SAE
   `build_goal_state`/`build_habit_state` already rich.
2. **Execution / Tasks** (deepen beyond rhythm: "what's slipping", "am I overcommitted")
   — `build_task_state`/`build_execution_state`.
3. **Finance** ("am I overspending", "how's my savings goal") — `build_finance_state`
   *(sensitivity gate)*.
4. **Faith** ("how's my walk this week") — `build_faith_state`.
- Each is one registry-keyed curator + intent + deterministic fallback + tests,
  shipped and validated **one domain at a time** (own stable tag candidate).
- **Risk:** MEDIUM (new reasoning intents) — mitigated by the curator framework +
  per-domain isolation + the P25 shadow discipline.

## Phase 3 — Medical / labs into briefing + reasoning *(richest under-used truth)*
- Surface `build_medical_state` (abnormal-90d, glycemic labs, metabolic intelligence)
  into the executive briefing and a labs reasoning intent ("what do my recent labs
  say"), with the clinical-caution tone contract (narrate, never diagnose).
- **Value:** HIGH personal value; **Risk:** MEDIUM (tone/privacy) — reuse the health
  non-alarmist calibration.

## Phase 4 — Reclaim the orphans
- **Emotional state:** promote to a first-class signal — either a thin `emotional`
  SAE module or formally surface `journal.mood/stress` into briefings + a reasoning
  curator ("how have I been feeling").
- **Documents:** give Beth **explicit-retrieval** access (search/fetch a named
  document) — content stays non-ambient (privacy gate). Closes the "I uploaded it but
  Beth can't see it" gap.
- **Relationships / Journal reasoning:** add curators (SAE already rich).

## Phase 5 — Opportunistic low-stakes domains
- Sports, brain-training, meals/pantry, scan — wire into facts/briefing only where it
  adds CoS value; thin SAE means low effort, low priority.

---

## Sequencing summary

| Phase | Scope | Value | Risk | Depends on existing canonical state? |
|------|-------|-------|------|--------------------------------------|
| 0 | Governance + curator registry + ops view | enabling | none | — |
| 1 | ~10 non-health foundational facts | High (frequency) | LOW | ✅ |
| 2 | Reasoning: goals → tasks → finance → faith | **Highest** | MED | ✅ |
| 3 | Medical/labs briefing + reasoning | High | MED | ✅ |
| 4 | Orphans: emotional, documents, relationships/journal reasoning | High | MED–HIGH | partial (new for documents/emotional) |
| 5 | Sports/brain-training/meals/scan | Low | LOW | ◑ |

## Definition of "holistic truth coverage" (the target state)

For each domain WLJ tracks: a canonical SAE state → a foundational fast-fact for its
key scalar → an executive-briefing weave → a reasoning curator with deterministic
fallback → Beth can answer free-form judgment questions about it — all domain-scoped,
privacy-gated where ratified, and consuming one canonical source (P24). When every
"Yes — Beth should know it" row in the coverage audit reaches that bar, the principle
*"if WLJ knows it, Beth knows it"* is satisfied.

## Guardrails (do NOT regress while expanding)
All `beth-stable-v1`/`v2` Golden Behaviors: durability/recovery/notifications/thinking
indicators; health-only contamination guarantee (now generalized per-domain);
deterministic fallbacks; P24 canonical alignment; GB-5 no-deflection; P25 stays
shadow until separately activated. Each phase is step-gated under `BETH_CHANGE_CONTROL`
with its own Blast Radius Assessment and stable tag.
