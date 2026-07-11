# 00 · NEXT CHAT STARTUP  (read me first — the bootloader)

**You are starting a WLJ Chief of Staff session. This is the only file to read before you begin.** It is the **one temporary document** in this package; everything else here is permanent institutional memory.

## Do this now
1. **Read the rest of this package, in order:** `01_READ_FIRST…ARCHITECTURE` → `02_WLJ_CONSTITUTION` → `03_ENGINEERING_OPERATING_GUIDE` → `04_DANNY_WORKING_PREFERENCES` → `98_SESSION_TRANSITION_PROTOCOL` → `99_REFERENCE_INDEX`.
2. **Those documents are the authoritative source of truth.** Every permanent architectural decision, principle, engineering rule, and working preference has already been folded into them.
3. **Do not summarize them back.** Read, absorb, act.
4. **Do not revisit constitutional decisions** unless a change genuinely requires a **Constitutional Review** (`02_WLJ_CONSTITUTION.md §3`, default NO, Danny's explicit written approval).
5. Continue from the live session state below.

*Regenerated at the end of every chat by `@WLJ_SYSTEM_PROMPTS/99_PREPARE_NEXT_CHAT.md`. Carries only what's below — nothing constitutional, architectural, or duplicated — and gets shorter over time.*

**Last regenerated:** 2026-07-11 (Operations Phase II recovery framework shipped dark + independently verified; milestone closeout).

---

## Current sprint
Architecture is stable and constitutionally protected. WLJ is in **product refinement**. **WLJ Operations** is now its own frozen Layer 1 truth domain (`docs/WLJ_OPERATIONS_VISION.md`): Phase I visibility + Phase II Deterministic Recovery framework are **shipped dark**. No feature work in flight.

## Current priorities (ranked)
1. **CC-1** — `@register_page_summary` providers for the 8 core dashboards (pattern: `health.weight`). `docs/WLJ_CURRENT_CONTEXT_HELP_COVERAGE.md §4`.
2. **CC-2 / CC-4** — `CurrentContextMixin` on the ~8 non-DetailView detail pages; spot-check the ~45 auto-declared DetailViews inherit `UserOwnedModel`.
3. **Operations pilot enablement (OPERATOR-GATED — the O1→O2 gate)** — pilot selected + lifecycle proven in a controlled env; **remaining step is the operator's** (Claude has no prod access). Set 3 Railway env vars: `OPS_RECOVERY_BEAT_RETRY_ALLOWLIST=apps.core.health_briefing.tasks.recompute_all_health_briefings_task`, `OPS_RECOVERY_BEAT_RETRY=true`, `OPS_RECOVERY_ENABLED=true`; observe ≥3 SAME cycles via the Ops Wall "Recovery Activity" card. **Full runbook: `docs/WLJ_OPERATIONS_PHASE2_PLAN.md §11.1`.** O2 is reached only after a real prod MISSED_RUN is recovered+verified.
4. **Acceptance gaps** — end-to-end scheduled-check-in test; standalone conversation-integrity contract. `docs/WLJ_ACCEPTANCE_BASELINE.md §5`.
5. **Help gaps** — per-page finance help; add `SECURITY_DASHBOARD`, `SPORTS_HUB`, `CALENDAR_EVENT_DETAIL` topics.

## Deferred (do not lose)
- **Ops Wall OPS-5…OPS-10** — further-out observability backlog (DB depth, `owner` field, dead-job aggregation, confirmation-queue/audit-lag, build-runner, direct Beat measurement). `docs/WLJ_OPS_WALL_COVERAGE.md §4`.
- **Operations Phases III–IX** — recovery-framework generalization → escalation → CoS awareness → autonomy → predictive → Mission Control. `docs/WLJ_OPERATIONS_VISION.md §14`.
- **Deferred recovery pilots** — snapshot-refresh (ADR-17: already covered by the Beat-retry pilot's condition) and chat-requeue (needs a proven idempotency/dedup design). Each has a promotion trigger in `WLJ_OPERATIONS_PHASE2_PLAN.md §1.1`.

## Recently completed
- **Operations Phase II** (2026-07-11, `b3e6c40a`) — **Deterministic Recovery framework shipped DARK.** `apps/core/operations/`: RecoveryEngine (diagnose→gate→recover→verify→audit→escalate), RecoveryPolicy (R0–R4, finite bounds, recurrence→permanent-fix), handler+registry, `RecoveryAttempt` audit model (migration 0130), verification reuses the detector predicate, separate downstream recovery task, kill switch, read-only Recovery Activity card, import-boundary + request-path CI contracts; one R1 pilot (Beat-task re-enqueue, allowlist empty). `OPS_RECOVERY_ENABLED=False` → zero behavior change. Recovery never writes incident state (SAME owns the lifecycle). Verified: operations 23, constitution, payload, OPS-1, Ops Wall v2 85 — all green.
- **Operations architecture** (2026-07-11) — vision + Phase II plan authored; architecture **frozen** (`WLJ_OPERATIONS_VISION.md` §§1–18, ADR-1…18).
- **OPS-1…4** (2026-07-11) — Ops Wall monitors: non-engine Beat tasks, storage/volume, chat-queue backlog, OpenAI upstream health. `docs/WLJ_OPS_WALL_COVERAGE.md §4`.

## Open investigations / Outstanding bugs
- None.

## Waiting on Danny
- **Production live-check (operator)** — confirm `/_health/` + Ops Wall are green after the Phase II deploy; confirm `OPS_RECOVERY_*` remain **unset/disabled** in the Railway env; confirm the "Recovery Activity" card renders "disabled". (Phase II ships dark — this just confirms no unexpected enablement.)
- **Doc classification (14 uncertain)** — CURRENT vs HISTORICAL, especially the CLAUDE.md-linked `INTELLIGENCE_ARCHITECTURE`, `DOMAIN_INTELLIGENCE_ARCHITECTURE`, `ENGINE_COS_REFERENCE`, `ENGINE_INTEGRATION_GUIDE`. If retired, update CLAUDE.md in the same change. `docs/WLJ_DOCUMENTATION_INVENTORY.md §6`.
- **DB backup verification (operator)** — confirm the latest Railway Postgres snapshot; record its timestamp in `docs/WLJ_MILESTONE_COS_ARCHITECTURE.md`.

## Immediate next steps
- If Danny is available: choose **CC-1** (product coverage) vs the **operator-gated Operations pilot enablement** (O1→O2). Recommendation: start **CC-1** in a fresh chat; treat pilot enablement as a separate, deliberate operator-gated step.
- Otherwise: start **CC-1** (top open priority).
