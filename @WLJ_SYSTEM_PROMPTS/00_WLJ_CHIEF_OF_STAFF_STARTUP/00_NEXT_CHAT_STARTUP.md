# 00 · NEXT CHAT STARTUP  (read me first — the bootloader)

**You are starting a WLJ Chief of Staff session. This is the only file to read before you begin.** It is the **one temporary document** in this package; everything else here is permanent institutional memory.

## Do this now
1. **Read the rest of this package, in order:** `01_READ_FIRST…ARCHITECTURE` → `02_WLJ_CONSTITUTION` → `03_ENGINEERING_OPERATING_GUIDE` → `04_DANNY_WORKING_PREFERENCES` → `98_SESSION_TRANSITION_PROTOCOL` → `99_REFERENCE_INDEX`.
2. **Those documents are the authoritative source of truth.** Every permanent architectural decision, principle, engineering rule, and working preference has already been folded into them.
3. **Do not summarize them back.** Read, absorb, act.
4. **Do not revisit constitutional decisions** unless a change genuinely requires a **Constitutional Review** (`02_WLJ_CONSTITUTION.md §3`, default NO, Danny's explicit written approval).
5. Continue from the live session state below.

*Regenerated at the end of every chat by `@WLJ_SYSTEM_PROMPTS/99_PREPARE_NEXT_CHAT.md`. Carries only what's below — nothing constitutional, architectural, or duplicated — and gets shorter over time.*

**Last regenerated:** 2026-07-11 (institutional-memory finalization).

---

## Current sprint
Architecture is stable and constitutionally protected; the startup/transition system is finalized. WLJ is in **product refinement** — remaining work is product + coverage, all inside the Constitution. No feature work in flight.

## Deferred (explicitly postponed — do not lose)
- **Ops Wall implementation** — the audit is complete; implementation is being worked down in priority order. **OPS-1 is DONE (2026-07-11)** — the generic scheduled-task monitor now gives MISSED_RUN coverage to all 23 non-engine Beat tasks. Remaining Ops Wall gaps are OPS-2..OPS-10. Governing principle: *"if it runs in production, it must be observable."* `docs/WLJ_OPS_WALL_COVERAGE.md §4`.

## Current priorities (ranked)
1. **CC-1** — `@register_page_summary` providers for the 8 core dashboards (pattern: `health.weight`). `docs/WLJ_CURRENT_CONTEXT_HELP_COVERAGE.md §4`.
2. **CC-2 / CC-4** — `CurrentContextMixin` on the ~8 non-DetailView detail pages; spot-check the ~45 auto-declared DetailViews inherit `UserOwnedModel`.
3. **Acceptance gaps** — end-to-end scheduled-check-in test; standalone conversation-integrity contract. `docs/WLJ_ACCEPTANCE_BASELINE.md §5`.
4. **OPS-2/3/4** — storage/volume monitoring, `chat` queue backlog, OpenAI upstream health.
5. **Help gaps** — per-page finance help; add `SECURITY_DASHBOARD`, `SPORTS_HUB`, `CALENDAR_EVENT_DETAIL` topics.

## Recently completed
- **OPS-1** (2026-07-11) — generic Beat-schedule-vs-actual-run reconciler: MISSED_RUN now fires for every non-engine Celery Beat task; new **Scheduled Beat Tasks** Ops Wall card. `apps/core/ai_observability/scheduled_task_monitor.py`, `docs/WLJ_OPS_WALL_COVERAGE.md §4`.

## Open investigations
- None active.

## Outstanding bugs
- None open.

## Waiting on Danny
- **Doc classification (14 uncertain)** — CURRENT vs HISTORICAL vs SUPERSEDED, especially the CLAUDE.md-linked `INTELLIGENCE_ARCHITECTURE`, `DOMAIN_INTELLIGENCE_ARCHITECTURE`, `ENGINE_COS_REFERENCE`, `ENGINE_INTEGRATION_GUIDE`. If retired, update CLAUDE.md in the same change. `docs/WLJ_DOCUMENTATION_INVENTORY.md §6`.
- **DB backup verification (operator)** — confirm the latest Railway Postgres snapshot; record its timestamp in `docs/WLJ_MILESTONE_COS_ARCHITECTURE.md`.
- **Production live-check** — confirm `/_health/` + Ops Wall are green after recent deploys.

## Immediate next steps
- If Danny is available: resolve the 14-doc classification (unblocks a CLAUDE.md cleanup).
- Otherwise: start **CC-1** (now the top-ranked open priority; OPS-1 shipped 2026-07-11).
