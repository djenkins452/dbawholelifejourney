# 00 · NEXT CHAT STARTUP  (read me first — the bootloader)

**You are starting a WLJ Chief of Staff session. This is the only file to read before you begin.** It is the **one temporary document** in this package; everything else here is permanent institutional memory.

## Do this now
1. **Read the rest of this package, in order:** `01_READ_FIRST…ARCHITECTURE` → `02_WLJ_CONSTITUTION` → `03_ENGINEERING_OPERATING_GUIDE` → `04_DANNY_WORKING_PREFERENCES` → `98_SESSION_TRANSITION_PROTOCOL` → `99_REFERENCE_INDEX`.
2. **Those documents are the authoritative source of truth.** Every permanent architectural decision, principle, engineering rule, and working preference has already been folded into them.
3. **Do not summarize them back.** Read, absorb, act.
4. **Do not revisit constitutional decisions** unless a change genuinely requires a **Constitutional Review** (`02_WLJ_CONSTITUTION.md §3`, default NO, Danny's explicit written approval).
5. Continue from the live session state below.

*Regenerated at the end of every chat by `@WLJ_SYSTEM_PROMPTS/99_PREPARE_NEXT_CHAT.md`. Carries only what's below — nothing constitutional, architectural, or duplicated — and gets shorter over time.*

**Last regenerated:** 2026-07-11 (OPS-1 shipped + verified; milestone-session cadence folded into `04`/`98`).

---

## Current sprint
Architecture is stable and constitutionally protected. WLJ is in **product refinement** — remaining work is product + coverage, all inside the Constitution. Roadmap now advances to **CC-1** (Current Context page-summary coverage). No feature work in flight.

## Current priorities (ranked)
1. **CC-1** — `@register_page_summary` providers for the 8 core dashboards (pattern: `health.weight`). `docs/WLJ_CURRENT_CONTEXT_HELP_COVERAGE.md §4`.
2. **CC-2 / CC-4** — `CurrentContextMixin` on the ~8 non-DetailView detail pages; spot-check the ~45 auto-declared DetailViews inherit `UserOwnedModel`.
3. **Acceptance gaps** — end-to-end scheduled-check-in test; standalone conversation-integrity contract. `docs/WLJ_ACCEPTANCE_BASELINE.md §5`.
4. **OPS-2 / OPS-3 / OPS-4** — storage/volume monitoring, `chat` queue backlog, OpenAI upstream health. `docs/WLJ_OPS_WALL_COVERAGE.md §4`.
5. **Help gaps** — per-page finance help; add `SECURITY_DASHBOARD`, `SPORTS_HUB`, `CALENDAR_EVENT_DETAIL` topics.

## Deferred (do not lose)
- **Ops Wall OPS-5..OPS-10** — further-out observability backlog (DB depth, `owner` field, dead-job aggregation, confirmation-queue/audit-lag, build-runner, direct Beat measurement). `docs/WLJ_OPS_WALL_COVERAGE.md §4`.

## Recently completed
- **OPS-1** (2026-07-11) — **shipped and independently verified.** Generic Beat-schedule-vs-actual-run reconciler: all 25 `CELERY_BEAT_SCHEDULE` entries observable (23 via `ScheduledTaskMonitor`, 2 via `SchedulerHeartbeat`); MISSED_RUN fires for every non-engine Beat task; new **Scheduled Beat Tasks** Ops Wall card. `apps/core/ai_observability/scheduled_task_monitor.py`, `docs/WLJ_OPS_WALL_COVERAGE.md §4`.

## Open investigations / Outstanding bugs
- None.

## Waiting on Danny
- **Doc classification (14 uncertain)** — CURRENT vs HISTORICAL vs SUPERSEDED, especially the CLAUDE.md-linked `INTELLIGENCE_ARCHITECTURE`, `DOMAIN_INTELLIGENCE_ARCHITECTURE`, `ENGINE_COS_REFERENCE`, `ENGINE_INTEGRATION_GUIDE`. If retired, update CLAUDE.md in the same change. `docs/WLJ_DOCUMENTATION_INVENTORY.md §6`.
- **DB backup verification (operator)** — confirm the latest Railway Postgres snapshot; record its timestamp in `docs/WLJ_MILESTONE_COS_ARCHITECTURE.md`.
- **Production live-check** — confirm `/_health/` + Ops Wall are green after the OPS-1 deploy.

## Immediate next steps
- If Danny is available: resolve the 14-doc classification (unblocks a CLAUDE.md cleanup).
- Otherwise: start **CC-1** (top-ranked open priority).
