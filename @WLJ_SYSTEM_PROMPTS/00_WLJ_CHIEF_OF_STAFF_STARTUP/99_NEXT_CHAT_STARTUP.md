# 99 · NEXT CHAT STARTUP (bootloader)

**This is a bootloader, not a continuation summary. It carries only current priorities and open work — nothing constitutional, architectural, or duplicated.**
**Regenerated via the Session Transition Protocol** (`02_ENGINEERING_OPERATING_GUIDE.md §15`). It should get *shorter* over time as knowledge folds up into the governing docs.
**Last regenerated:** 2026-07-11 (after the Architecture Milestone).

---

## To the next AI

1. **Read the four governing documents in this folder:** `00_READ_FIRST…ARCHITECTURE`, `01_WLJ_CONSTITUTION`, `02_ENGINEERING_OPERATING_GUIDE`, `03_DANNY_WORKING_PREFERENCES`.
2. **Assume they contain every stable architectural decision.** Do not re-derive them. If you'd change one, that's a **Constitutional Review** (default NO).
3. **Continue from the remaining work below.**

## Where things stand

The WLJ Chief of Staff Architecture Milestone is established (tag `milestone-cos-architecture-v1`, Constitution v1.0). Architecture is stable and constitutionally protected. Remaining work is **product + coverage**, all inside the Constitution.

## Decisions waiting on Danny (do these first if he's available)

- **Doc classification (14 uncertain):** decide CURRENT vs HISTORICAL vs SUPERSEDED for the boundary docs — especially the **CLAUDE.md-linked** `INTELLIGENCE_ARCHITECTURE`, `DOMAIN_INTELLIGENCE_ARCHITECTURE`, `ENGINE_COS_REFERENCE`, `ENGINE_INTEGRATION_GUIDE`. If retired, update CLAUDE.md in the same change. List: `docs/WLJ_DOCUMENTATION_INVENTORY.md §6`.
- **DB backup verification (operator):** confirm the latest Railway Postgres snapshot in the dashboard and record its timestamp in `docs/WLJ_MILESTONE_COS_ARCHITECTURE.md`. Code recovery point is already verified; DB backup is not.
- **Production live-check:** confirm `/_health/` + Ops Wall are green after the milestone deploy.

## Open work backlog (ranked)

1. **OPS-1 — highest observability gap:** ~10 non-engine Celery Beat tasks have no heartbeat → MISSED_RUN never fires (Goal momentum, cleanup, image-retention). Register them as engines or add a generic Beat-run reconciler. Full backlog: `docs/WLJ_OPS_WALL_COVERAGE.md §4`.
2. **CC-1 — Current Context Tier-1 summaries:** ship `@register_page_summary` providers for the 8 core dashboards (Dashboard, Glucose, Health overview, Calendar overview, Finance, Goals, Tasks, Reports). Pattern reference: `health.weight`. Backlog: `docs/WLJ_CURRENT_CONTEXT_HELP_COVERAGE.md §4`.
3. **CC-2 / CC-4:** add `CurrentContextMixin` to the ~8 non-DetailView detail pages; spot-check that the ~45 auto-declared DetailViews inherit `UserOwnedModel`.
4. **Acceptance gaps:** add an end-to-end scheduled-check-in test and a standalone conversation-integrity contract (`docs/WLJ_ACCEPTANCE_BASELINE.md §5`).
5. **OPS-2/3/4:** storage/volume monitoring, `chat` queue backlog, OpenAI upstream health.
6. **Help gaps:** per-page help for finance; add `SECURITY_DASHBOARD`, `SPORTS_HUB`, `CALENDAR_EVENT_DETAIL` topics.

## Housekeeping

- `docs/business/README.md` + `MASTER_PROMPT.md` referenced but missing; stale archive-path references in `ENGINE_COS_REFERENCE.md` + changelog. Fix opportunistically.
- Django is 4.2.27 (CLAUDE.md says 5.x) — a deliberate 4.2→5.x upgrade is future work.

---

*When Danny signals this chat is getting large, run the Session Transition Protocol and rewrite this file. Fold anything durable UP into the governing docs; keep this list short.*
