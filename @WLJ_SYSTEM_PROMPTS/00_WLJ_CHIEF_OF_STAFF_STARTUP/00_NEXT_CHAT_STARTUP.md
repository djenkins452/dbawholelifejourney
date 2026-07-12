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
Architecture is stable and constitutionally protected. **The near-term focus is COMPLETING WLJ Operations — not shifting to Current Context.** Operations is at maturity **O1 (Observable)**; Phase I visibility (OPS-1…4) + Phase II/II-B recovery (3 R1 handlers, 2 shapes) are **shipped dark** (`docs/WLJ_OPERATIONS_VISION.md`). Two tracks make Operations production-complete: **(a) the O1→O2 production enablement** (operator-gated — Claude can't do it) and **(b) Phase I observability hardening, OPS-5…10** (the next unblocked ENGINEERING work). Phase III (recovery-as-config) and Phases IV–IX stay **evidence-gated / future**, not active. No feature work in flight.

## Current priorities (ranked) — Operations first
1. **Operations O1→O2 production enablement (OPERATOR-GATED — the gate to O2).** Pilot selected + lifecycle proven in a controlled env; **the remaining step is the operator's** (Claude has no prod access). Set 3 Railway env vars: `OPS_RECOVERY_BEAT_RETRY_ALLOWLIST=apps.core.health_briefing.tasks.recompute_all_health_briefings_task`, `OPS_RECOVERY_BEAT_RETRY=true`, `OPS_RECOVERY_ENABLED=true`; observe ≥3 SAME cycles via the Ops Wall "Recovery Activity" card. **Runbook: `docs/WLJ_OPERATIONS_PHASE2_PLAN.md §11.1`.** O2 is reached only after a real prod condition is recovered+verified.
2. **Operations Phase I observability hardening — OPS-5…10 (the next unblocked ENGINEERING milestone).** Finishes *"if it runs in production, it must be observable."* Ranked backlog in `docs/WLJ_OPS_WALL_COVERAGE.md §4`: **OPS-5** Postgres depth + DB admin (connections/bloat/slow-query/backup-verification — ties to the open backup-verification operator item), **OPS-6** per-component `owner`, **OPS-7** dead-job/stuck-task/general-retry aggregation (synergizes with recovery — dead jobs are future recoverable candidates), **OPS-8** confirmation-queue/attachment/dedup/audit-lag, **OPS-9** build-runner/deploy, **OPS-10** direct Beat measurement. Backlog items — present + discuss scope, wait for "go". **Recommend leading with OPS-5 or OPS-7.**
3. **CC-1** — `@register_page_summary` providers for the 8 core dashboards (pattern: `health.weight`). `docs/WLJ_CURRENT_CONTEXT_HELP_COVERAGE.md §4`. *(Top non-Operations priority once the Operations near-term work lands.)*
4. **CC-2 / CC-4** — `CurrentContextMixin` on the ~8 non-DetailView detail pages; spot-check the ~45 auto-declared DetailViews inherit `UserOwnedModel`.
5. **Acceptance gaps** — end-to-end scheduled-check-in test; standalone conversation-integrity contract. `docs/WLJ_ACCEPTANCE_BASELINE.md §5`.
6. **Help gaps** — per-page finance help; add `SECURITY_DASHBOARD`, `SPORTS_HUB`, `CALENDAR_EVENT_DETAIL` topics.

## Deferred (do not lose — preserved, NOT active work)
- **Operations Phases III–IX** — recovery-as-config → engineering escalation (Phase IV; currently only an audit-`ESCALATED` stub) → CoS awareness → autonomy → predictive → Mission Control; plus **Operations Memory** (future). Evidence-gated. `docs/WLJ_OPERATIONS_VISION.md §14`.
- **Deferred recovery expansion** — chat-queue requeue pilot (needs a proven idempotency/dedup design; `plan §1.1`) + a first **R2** recovery (worker/scheduler restart — the untested half of the R0–R4 classification; `plan §14`). Both wait for production experience. *(Snapshot recoveries are settled, not deferred: integrity/storage aren't candidates — SAME rewrites them each cycle — and the maturity snapshot is implemented via `MATURITY_SNAPSHOT_STALE` + `MaturitySnapshotRefreshHandler`.)*

## Recently completed
- **Operations Phase I + II + II-B** (2026-07-11) — Ops Wall visibility (OPS-1…4), the Deterministic Recovery framework, and **Phase II-B expanded R1 recoveries** (three handlers across two shapes: Beat-retry, engine-starvation re-trigger, maturity-snapshot recompute) all **shipped dark**; architecture frozen. New `MATURITY_SNAPSHOT_STALE` detector covers the previously-unmonitored ISE maturity-job gap. Evidence-backed finding: **Phase III (recovery-as-config) NOT yet justified** — the gate is controlled production experience, not more abstraction. Full detail/ledger/ADRs in `docs/WLJ_OPERATIONS_VISION.md`; comparison + Phase III determination in `WLJ_OPERATIONS_PHASE2_PLAN.md §14`. **Committed + pushed to `main` (`5ca7a485`); Railway deploy triggered; production runtime NOT yet operator-verified.**

## Open investigations / Outstanding bugs
- None.

## Waiting on Danny
- **Production live-check (operator)** — the Operations Phase II/II-B work is pushed to `main` and Railway auto-deploy is triggered, but **production runtime is not yet independently verified**. Confirm `/_health/` + Ops Wall are green after the deploy; confirm all `OPS_RECOVERY_*` env vars remain **unset/disabled** in Railway (recovery ships dark unless deliberately enabled); confirm the "Recovery Activity" card renders "disabled".
- **Doc classification (14 uncertain)** — CURRENT vs HISTORICAL, especially the CLAUDE.md-linked `INTELLIGENCE_ARCHITECTURE`, `DOMAIN_INTELLIGENCE_ARCHITECTURE`, `ENGINE_COS_REFERENCE`, `ENGINE_INTEGRATION_GUIDE`. If retired, update CLAUDE.md in the same change. `docs/WLJ_DOCUMENTATION_INVENTORY.md §6`.
- **DB backup verification (operator)** — confirm the latest Railway Postgres snapshot; record its timestamp in `docs/WLJ_MILESTONE_COS_ARCHITECTURE.md`.

## Immediate next steps
- **Operations is the focus.** Two parallel tracks:
  - *Operator (Danny):* enable the first R1 pilot (priority 1) to reach **O2** — the one thing Claude cannot do.
  - *Engineering (Claude, this chat):* start **OPS-5…10** (priority 2) — Phase I observability hardening. Present the chosen OPS item, discuss scope, wait for "go". **Recommend leading with OPS-5** (DB observability; ties to the open backup-verification item) or **OPS-7** (dead-job/stuck-task detection; synergizes with the recovery framework).
- **CC-1** is the top non-Operations priority once the Operations near-term work is complete.
