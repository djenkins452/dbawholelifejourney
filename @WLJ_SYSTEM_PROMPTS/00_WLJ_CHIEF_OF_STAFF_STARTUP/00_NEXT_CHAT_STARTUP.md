# 00 · NEXT CHAT STARTUP  (read me first — the bootloader)

**You are starting a WLJ Chief of Staff session. This is the only file to read before you begin.** It is the **one temporary document** in this package; everything else here is permanent institutional memory.

## Do this now
1. **Read the rest of this package, in order:** `01_READ_FIRST…ARCHITECTURE` → `02_WLJ_CONSTITUTION` → `03_ENGINEERING_OPERATING_GUIDE` → `04_DANNY_WORKING_PREFERENCES` → `98_SESSION_TRANSITION_PROTOCOL` → `99_REFERENCE_INDEX`.
2. **Those documents are the authoritative source of truth.** Every permanent architectural decision, principle, engineering rule, and working preference has already been folded into them.
3. **Do not summarize them back.** Read, absorb, act.
4. **Do not revisit constitutional decisions** unless a change genuinely requires a **Constitutional Review** (`02_WLJ_CONSTITUTION.md §3`, default NO, Danny's explicit written approval).
5. Continue from the live session state below.

*Regenerated at the end of every chat by `@WLJ_SYSTEM_PROMPTS/99_PREPARE_NEXT_CHAT.md`. Carries only what's below — nothing constitutional, architectural, or duplicated — and gets shorter over time.*

**Last regenerated:** 2026-07-12 (Shadow Validation COMPLETE; **O1→O2 ACTIVE recovery pilot ENABLED in production**; Recovery Engine made a first-class always-visible Ops Wall component + Recovery Events operator alerts shipped).

---

## Current sprint — WLJ Operations is the PRIMARY active initiative
Architecture is stable and constitutionally protected. **WLJ Operations is the project's primary active initiative** through the full Operations Vision (Phases II–IX) unless Danny redirects. **Phase I (Operations Visibility) is ✅ COMPLETE.** **Phase II Recovery is now LIVE in production, not dark:** the operator enabled the **O1→O2 ACTIVE pilot** (2026-07-12) after completing Stage-0 Shadow Validation. The single allowlisted handler is **Beat-retry for `apps.core.health_briefing.tasks.recompute_all_health_briefings_task`**; all other handlers stay disabled. **The active milestone is now MONITORING that pilot to confirm O2** (a real production `MISSED_RUN` recovered + verified). **Current Context (CC-*) and all other WLJ work are SECONDARY** until Danny redirects.

## Current priorities (ranked) — Operations initiative
1. **Monitor the ACTIVE recovery pilot → confirm O2 (the active milestone).** Production config: `OPS_RECOVERY_MODE=ACTIVE`, `OPS_RECOVERY_BEAT_RETRY=true`, `OPS_RECOVERY_BEAT_RETRY_ALLOWLIST=…recompute_all_health_briefings_task` (only that task; `OPS_RECOVERY_ENABLED` unset). Expected lifecycle on a real miss: `RECOVER_ATTEMPTED/PENDING` → (≥120s cooldown) `VERIFIED/SUCCESS` → `CLOSED` — verification predicate `compute_scheduled_task_states` (OPS-1 freshness). **O2 is reached** only after that real trail exists; then update the vision ledger (§15) + maturity (§6) + changelog. Watch the new **Recovery Events banner** (top of Ops Wall) for the success/failed/escalated alert. Stop conditions + evidence checklist: `docs/WLJ_OPERATIONS_PHASE2_PLAN.md §11.1`.
2. **Small remaining tech-debt** (present + discuss + "go"): **OPS-11** (retire inert legacy `_run_autonomous_remediation`) and the **expired-image cleanup task** (72h `image_data` never purged, found by OPS-8b). `docs/WLJ_OPS_WALL_COVERAGE.md §4.1`.
3. **Forward roadmap** — **Phase III (recovery-as-config)** stays **evidence-gated** until real ACTIVE recovery experience accrues from the pilot (`plan §14`); IV–IX future. Expanding the allowlist / adding a second handler / a first **R2** recovery all wait for the pilot to prove out.

### Secondary (only after Operations, or if Danny redirects)
- **CC-1** — `@register_page_summary` providers for the 8 core dashboards. `docs/WLJ_CURRENT_CONTEXT_HELP_COVERAGE.md §4`.
- **CC-2 / CC-4** — `CurrentContextMixin` on ~8 non-DetailView detail pages; spot-check ~45 auto-declared DetailViews.
- **Acceptance gaps** (`ACCEPTANCE_BASELINE §5`); **Help gaps** (finance per-page; `SECURITY_DASHBOARD`/`SPORTS_HUB`/`CALENDAR_EVENT_DETAIL`).

## Operational Rollout (OPERATOR — not engineering)
- **Stage 0 — Shadow Validation · ✅ COMPLETE.** Proven with production evidence: SHADOW honored, existing incidents evaluated, `SHADOW` audit rows written, no production actions. The lone R0 question (an allowlisted `MISSED_RUN` still shadowing R0) was **resolved and proven expected** — a stale shadow row frozen by the one-row-per-occurrence idempotency guard; a fresh occurrence under the current config classifies R1, and ACTIVE re-diagnoses every cycle (see `test_recovery_shadow_mode.py::ShadowBeatRetryO1O2Tests`; Vision §4a corollary). NOT a defect.
- **Stage 1 — O1→O2 production pilot · 🟢 ENABLED (monitoring).** The operator flipped `OPS_RECOVERY_MODE=ACTIVE`. Only the one Beat-retry handler acts; every other incident is observe-only/skipped. **Rollback (instant, one var):** `OPS_RECOVERY_MODE=SHADOW` (keeps observability) or `DISABLED`. Runbook + operator checklist: `PHASE2_PLAN §11.1`.

## Deferred (do not lose — preserved, NOT active work)
- **Post-Phase-I backlog (categorized)** — active list in `docs/WLJ_OPS_WALL_COVERAGE.md §4.1`: OPS-11 (retire legacy remediation), expired-image cleanup, OPS-8b (attachment/dedup/S3), OPS-9 (build-runner), OPS-6 (deferred), OPS-10 (accept-inference).
- **Operations Phases III–IX** — recovery-as-config → engineering escalation (Phase IV; currently only an audit-`ESCALATED` stub) → CoS awareness → autonomy → predictive → Mission Control; plus **Operations Memory** (future). Evidence-gated. `docs/WLJ_OPERATIONS_VISION.md §14`.
- **Deferred recovery expansion** — chat-queue requeue pilot (needs a proven idempotency/dedup design; `plan §1.1`) + a first **R2** recovery (worker/scheduler restart — the untested half of R0–R4; `plan §14`). Both wait for ACTIVE-pilot experience. *(Snapshot recoveries are settled, not deferred.)*
- **Backup verification** — future Operations capability; no trustworthy automated signal today (Railway-managed), operator-verified for now, never faked.

## Recently completed (this session — 2026-07-12)
- **Recovery Events — prominent, acknowledgeable operator alerts** (`8bc20855`) — a real ACTIVE recovery is never silent. `build_recovery_telemetry.events` is a deterministic reduction over the `RecoveryAttempt` rows already written (real `mode=ACTIVE` only; shadow excluded), rendered as a top-of-wall banner (success/failed/escalated, most-severe-first; failures louder), click-to-expand full detail, **acknowledge via localStorage** (ephemeral client state — no backend write/model/endpoint). New audit field `RecoveryAttempt.updated_at` (`auto_now`, migration `core/0133`) gives deterministic recovery **duration**. No new framework; recovery still never writes incident state. Tests: `RecoveryEventsTelemetryTests`.
- **O1→O2 R0 question — proven expected, not a defect** (`c3d085d4`) — see Stage 0 above. Test + docs only; no production code change.
- **Recovery Engine is a first-class, always-visible Ops Wall component** — three fixes: expose existing config truth as a Recovery Engine panel (`0f02f1b6`); `@never_cache` on `OperationsWallView` so the wall HTML shell isn't served stale (`9310c515`); and **promote the panel out of the collapsed Diagnostics drawer** into always-visible `ops-zone-recovery` (`ea130f32`, browser-traced: the card was 0×0 under `#diagnosticsBody{display:none}`). Telemetry now publishes every SAME cycle regardless of mode, so config/status is visible even when DISABLED.

## Recently completed (prior — 2026-07-11/12, established)
- **Operations Phase I visibility** (OPS-1…5,7,8a,8b,9 — 33+ Ops Wall sections) CLOSED complete; **Phase II-A/B recovery foundation** (engine/policy/registry/3 R1 handlers/`RecoveryAttempt`+migrations 0130–0132/kill switches/gated enqueue/contracts) shipped; **DB-level per-incident concurrency lock** (ADR-22); **Recovery Shadow Mode** (`OPS_RECOVERY_MODE`, ADR-23, migration 0132). Full ledger/ADRs in `docs/WLJ_OPERATIONS_VISION.md`; as-built in `WLJ_OPS_WALL_COVERAGE.md`.

## Open investigations / Outstanding bugs
- None.

## Waiting on Danny (operator — Claude has no prod access)
- **Monitor the ACTIVE pilot and confirm O2.** Watch the Ops Wall **Recovery Engine** panel (Mode = Active) and the **Recovery Events** banner. When a real `MISSED_RUN` of the allowlisted task occurs (or a brief controlled worker pause manufactures one), confirm the `RECOVER_ATTEMPTED → VERIFIED/SUCCESS → CLOSED` trail (non-simulated), 0 failed/escalated, no action on any other incident, `/_health/` green. Send back the panel screenshot + the `/admin-console/ops/stream/` `recovery` JSON so Claude can confirm O2 and update the ledger/maturity/changelog.
- **Doc classification (14 uncertain)** — CURRENT vs HISTORICAL, esp. the CLAUDE.md-linked `INTELLIGENCE_ARCHITECTURE`, `DOMAIN_INTELLIGENCE_ARCHITECTURE`, `ENGINE_COS_REFERENCE`, `ENGINE_INTEGRATION_GUIDE`. If retired, update CLAUDE.md in the same change. `docs/WLJ_DOCUMENTATION_INVENTORY.md §6`.
- **DB backup verification (operator)** — confirm the latest Railway Postgres snapshot; record its timestamp in `docs/WLJ_MILESTONE_COS_ARCHITECTURE.md`.

## Immediate next steps
- **WLJ Operations is the primary initiative; the active milestone is confirming O2 from the live ACTIVE pilot.** The blocking next action is **operator-run** — Danny observes the pilot and reports the recovery trail; Claude then confirms O2 and updates the vision ledger (§15) + maturity (§6). Do NOT expand the allowlist or enable a second handler until the pilot proves out.
- **Engineering (Claude), available in parallel if Danny redirects:** the small remaining tech-debt — **OPS-11** (retire inert legacy remediation) or the **expired-image cleanup task**. Present scope, discuss, wait for "go".
- CC-* and other WLJ work stay **secondary** until Danny explicitly redirects.
