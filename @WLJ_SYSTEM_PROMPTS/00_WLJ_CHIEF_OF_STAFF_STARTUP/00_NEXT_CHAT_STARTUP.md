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

## Current sprint — WLJ Operations is the PRIMARY active initiative
Architecture is stable and constitutionally protected. **WLJ Operations is the project's primary active initiative** and stays so through the full Operations Vision (Phases II–IX) unless Danny explicitly redirects. **Phase I (Operations Visibility) is ✅ COMPLETE (2026-07-12)** — mission achieved: the critical infrastructure + execution surface is comprehensively observable (OPS-1…5,7). The residual OPS backlog is reclassified out of Phase I **by category** (`docs/WLJ_OPS_WALL_COVERAGE.md §4.1`), not a numbered list. Phase II/II-B recovery is **built and shipped dark** (3 R1 handlers). **Current Context (CC-*) and all other WLJ work are SECONDARY** until Danny changes direction. Every future chat should naturally continue progressing the Operations Vision.

## Current priorities (ranked) — Operations initiative
1. **Observability hardening is essentially COMPLETE** — OPS-5/7/8a/8b/9 all shipped (33 Ops Wall sections). The Ops Wall now covers infra, execution, recovery telemetry, correctness pipelines, media/capture persistence, and deployment/version. Remaining engineering is small **tech-debt** (present + discuss + "go"): **OPS-11** (retire inert legacy `_run_autonomous_remediation`) and the **expired-image cleanup task** (an *action* hygiene gap OPS-8b discovered — 72h `image_data` never purged). `docs/WLJ_OPS_WALL_COVERAGE.md §4.1`.
2. **Then the forward Operations roadmap** — with observability complete, the highest-value moves are the operator **O1→O2 production pilot** (Operational Rollout below) and reconsidering **Phase III** (recovery-as-config) once production recovery experience exists (`plan §14`). Deferred/closed: **OPS-6** (`owner`, near-zero value single-owner), **OPS-10** (direct Beat, accept-inference).
3. **Then the forward capability roadmap** — Phases II–IX. Phase III (recovery-as-config) stays **evidence-gated** until real production recovery experience exists (`plan §14`); IV–IX future.

### Secondary (only after Operations, or if Danny redirects)
- **CC-1** — `@register_page_summary` providers for the 8 core dashboards. `docs/WLJ_CURRENT_CONTEXT_HELP_COVERAGE.md §4`.
- **CC-2 / CC-4** — `CurrentContextMixin` on ~8 non-DetailView detail pages; spot-check ~45 auto-declared DetailViews.
- **Acceptance gaps** (`ACCEPTANCE_BASELINE §5`); **Help gaps** (finance per-page; `SECURITY_DASHBOARD`/`SPORTS_HUB`/`CALENDAR_EVENT_DETAIL`).

## Operational Rollout (OPERATOR — not engineering)
- **O1→O2 production pilot.** Engineering is **complete** (recovery framework + 3 R1 handlers + runbook). What remains is the operator's: set 3 Railway env vars — `OPS_RECOVERY_BEAT_RETRY_ALLOWLIST=apps.core.health_briefing.tasks.recompute_all_health_briefings_task`, `OPS_RECOVERY_BEAT_RETRY=true`, `OPS_RECOVERY_ENABLED=true` — then observe ≥3 SAME cycles via the Ops Wall "Recovery Activity" card. **Runbook: `docs/WLJ_OPERATIONS_PHASE2_PLAN.md §11.1`.** O2 is reached only after a real prod condition is recovered+verified. This is the highest-value single action overall, but Claude cannot do it.

## Deferred (do not lose — preserved, NOT active work)
- **Post-Phase-I backlog (categorized)** — the active list lives in `docs/WLJ_OPS_WALL_COVERAGE.md §4.1`: OPS-8b (attachment/dedup/S3), OPS-9 (build-runner), OPS-11 (retire legacy remediation), OPS-6 (deferred), OPS-10 (accept-inference).
- **Operations Phases III–IX** — recovery-as-config → engineering escalation (Phase IV; currently only an audit-`ESCALATED` stub) → CoS awareness → autonomy → predictive → Mission Control; plus **Operations Memory** (future). Evidence-gated. `docs/WLJ_OPERATIONS_VISION.md §14`.
- **Deferred recovery expansion** — chat-queue requeue pilot (needs a proven idempotency/dedup design; `plan §1.1`) + a first **R2** recovery (worker/scheduler restart — the untested half of the R0–R4 classification; `plan §14`). Both wait for production experience. *(Snapshot recoveries are settled, not deferred: integrity/storage aren't candidates — SAME rewrites them each cycle — and the maturity snapshot is implemented via `MATURITY_SNAPSHOT_STALE` + `MaturitySnapshotRefreshHandler`.)*
- **Backup verification** — future Operations capability; no trustworthy automated signal today (Railway-managed), operator-verified for now, never faked.

## Recently completed
- **OPS-9 — Deployment & version health** (2026-07-12) — new `deployment` Ops Wall section: running commit SHA + environment + runtime versions, **migration status** (deterministic partial-deploy / "did the deploy fully succeed?" signal), and **self-observed deploy detection** (SHA-change tracking). NO external Railway/GitHub poll. **Roadmap corrected:** build status/failures/duration + failed-deploys + rollback are Railway-side, invisible to a running process → NOT built. Telemetry-only, no migration. Answers "what's running / did the deploy succeed / can I trust prod?". `docs/WLJ_OPS_WALL_COVERAGE.md §4.1`.
- **OPS-8b — Media & persistence health** (2026-07-12) — new `media_persistence` Ops Wall section: capture-audio pipeline (status/failed/**stuck**/abandoned from `CaptureEntry`+`PendingCapture`), expired-image retention (surfaces a **missing cleanup task**), storage-config facts. **Roadmap corrected:** NO S3 in use (prod media = **Cloudinary**); dedup-rate/orphan/verification-failure signals NOT built (mechanisms don't exist → would be fabricated). Discovered gap: no expired-image cleaner (72h `image_data` accrues in Postgres). Telemetry-only, no migration. `docs/WLJ_OPS_WALL_COVERAGE.md §4.1`.
- **OPS-8a — Confirmation & Audit health** (2026-07-12) — new `confirmation_audit` Ops Wall section: confirmation-queue health (pending-active, **stalled**=orphaned-past-expiry, oldest age, 24h flow) from `PendingAction`; audit-stream **liveness** (throughput + last-write recency) for `DecisionRecord`+`AIActionMetric`. Evidence-driven scope refinement: auditing is synchronous → no queue-lag exists, so stream-liveness facts (not a fabricated "lag" verdict). Telemetry-only, request-path-safe, no migration. `docs/WLJ_OPS_WALL_COVERAGE.md §4.1`.
- **Phase I — Operations Visibility CLOSED (COMPLETE)** (2026-07-12) — mission achieved (critical infra + execution surface comprehensively observable via OPS-1…5,7). Residual reclassified out of Phase I by category (`WLJ_OPS_WALL_COVERAGE.md §4.1`). O1→O2 pilot reframed as an **Operational Rollout** (operator), separate from engineering. WLJ Operations established as the **primary active initiative**. Docs-only.
- **OPS-7 — Background task health** (2026-07-11) — new `task_health` Ops Wall section: pool-wide worker-side capture of the Celery lifecycle for ALL task names (active/oldest-age/**stuck**, **failures** recurring-vs-isolated, **retries**, **revocations**). Filled a real gap (`task_failure`/`task_retry`/`task_revoked` captured nowhere; no result backend, `CELERY_TASK_IGNORE_RESULT=True`). Redis-only, worker-side (zero request-path), telemetry-only. Reuses OPS-3's signal→Redis pattern. `docs/WLJ_OPS_WALL_COVERAGE.md §4`.
- **OPS-5 — DB health** (2026-07-11) — new `db_health` Ops Wall section (connections vs `max_connections`, long-running queries, dead-tuple bloat + autovacuum age, unapplied-migration/partial-deploy detection). Telemetry-only, request-path-safe, no migration. Reuses the OPS-2 pattern. Backup verification correctly stayed operator-only (no in-DB signal). `docs/WLJ_OPS_WALL_COVERAGE.md §4`.
- **Legacy-remediation investigation** (2026-07-11) — `_run_autonomous_remediation` is inert dead code (P3 filter never matches P1/P2 MISSED_RUN/SUPPRESSION_STORM). Single-authority holds. Filed **OPS-11** to retire it later (not urgent).
- **Operations Phase I + II + II-B** (2026-07-11) — Ops Wall visibility (OPS-1…4), the Deterministic Recovery framework, and **Phase II-B expanded R1 recoveries** (three handlers across two shapes: Beat-retry, engine-starvation re-trigger, maturity-snapshot recompute) all **shipped dark**; architecture frozen. New `MATURITY_SNAPSHOT_STALE` detector covers the previously-unmonitored ISE maturity-job gap. Evidence-backed finding: **Phase III (recovery-as-config) NOT yet justified** — the gate is controlled production experience, not more abstraction. Full detail/ledger/ADRs in `docs/WLJ_OPERATIONS_VISION.md`; comparison + Phase III determination in `WLJ_OPERATIONS_PHASE2_PLAN.md §14`. **Committed + pushed to `main` (`5ca7a485`); Railway deploy triggered; production runtime NOT yet operator-verified.**

## Open investigations / Outstanding bugs
- None.

## Waiting on Danny
- **Production live-check (operator)** — the Operations Phase II/II-B work is pushed to `main` and Railway auto-deploy is triggered, but **production runtime is not yet independently verified**. Confirm `/_health/` + Ops Wall are green after the deploy; confirm all `OPS_RECOVERY_*` env vars remain **unset/disabled** in Railway (recovery ships dark unless deliberately enabled); confirm the "Recovery Activity" card renders "disabled".
- **Doc classification (14 uncertain)** — CURRENT vs HISTORICAL, especially the CLAUDE.md-linked `INTELLIGENCE_ARCHITECTURE`, `DOMAIN_INTELLIGENCE_ARCHITECTURE`, `ENGINE_COS_REFERENCE`, `ENGINE_INTEGRATION_GUIDE`. If retired, update CLAUDE.md in the same change. `docs/WLJ_DOCUMENTATION_INVENTORY.md §6`.
- **DB backup verification (operator)** — confirm the latest Railway Postgres snapshot; record its timestamp in `docs/WLJ_MILESTONE_COS_ARCHITECTURE.md`.

## Immediate next steps
- **WLJ Operations is the primary initiative.** Observability hardening is essentially complete (OPS-5/7/8a/8b/9 shipped). Engineering (Claude, next chat): the small remaining tech-debt — **OPS-11** (retire inert legacy remediation) or the **expired-image cleanup task** — or, with observability done, help push the operator **O1→O2 pilot** / reconsider **Phase III**. Present the scope, discuss, wait for "go".
- **Operator (Danny), in parallel:** the O1→O2 production pilot (Operational Rollout above) — the highest-value single action overall, but operator-gated.
- CC-* and other WLJ work stay **secondary** until Danny explicitly redirects.
