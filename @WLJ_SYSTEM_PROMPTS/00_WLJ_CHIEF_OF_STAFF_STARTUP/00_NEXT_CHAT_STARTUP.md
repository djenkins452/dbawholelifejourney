# 00 · NEXT CHAT STARTUP  (read me first — the bootloader)

**You are starting a WLJ Chief of Staff session. This is the only file to read before you begin.** It is the **one temporary document** in this package; everything else here is permanent institutional memory.

## Do this now
1. **Read the rest of this startup package, in order:** `01_READ_FIRST…ARCHITECTURE` → `02_WLJ_CONSTITUTION` → `03_ENGINEERING_OPERATING_GUIDE` → `04_DANNY_WORKING_PREFERENCES` → `98_SESSION_TRANSITION_PROTOCOL` → `99_REFERENCE_INDEX`.
2. **Those documents are the authoritative source of truth.** Every permanent architectural decision, principle, engineering rule, and working preference has already been folded into them.
3. **Do not summarize them back.** Read them, absorb them, and act.
4. **Do not revisit constitutional decisions** unless a change genuinely requires a **Constitutional Review** (`02_WLJ_CONSTITUTION.md §3`, default NO, Danny's explicit written approval).
5. Then continue from the live session state below.

*This file is regenerated at the end of every chat by `@WLJ_SYSTEM_PROMPTS/99_PREPARE_NEXT_CHAT.md`. It carries only what's below — nothing constitutional, architectural, or duplicated — and gets shorter over time as durable knowledge folds up into the permanent documents.*

**Last regenerated:** 2026-07-11 (startup-system finalization).

---

## Current sprint
Post-milestone: the WLJ Chief of Staff Architecture Milestone and the permanent startup/transition system are established. Remaining work is **product + coverage**, all inside the Constitution. No feature work is in flight.

## Current priorities (ranked)
1. **OPS-1** — ~10 non-engine Celery Beat tasks have no heartbeat → MISSED_RUN never fires (Goal momentum, cleanup, image-retention). Register as engines or add a generic Beat-run reconciler. `docs/WLJ_OPS_WALL_COVERAGE.md §4`.
2. **CC-1** — ship `@register_page_summary` providers for the 8 core dashboards (pattern: `health.weight`). `docs/WLJ_CURRENT_CONTEXT_HELP_COVERAGE.md §4`.
3. **CC-2 / CC-4** — add `CurrentContextMixin` to the ~8 non-DetailView detail pages; spot-check the ~45 auto-declared DetailViews inherit `UserOwnedModel`.
4. **Acceptance gaps** — end-to-end scheduled-check-in test; standalone conversation-integrity contract. `docs/WLJ_ACCEPTANCE_BASELINE.md §5`.
5. **OPS-2/3/4** — storage/volume monitoring, `chat` queue backlog, OpenAI upstream health.
6. **Help gaps** — per-page finance help; add `SECURITY_DASHBOARD`, `SPORTS_HUB`, `CALENDAR_EVENT_DETAIL` topics.

## Open investigations
- None active.

## Remaining work / outstanding bugs
- No open bugs from recent sessions. Backlog items above are the remaining work.

## Waiting on Danny
- **Doc classification (14 uncertain):** CURRENT vs HISTORICAL vs SUPERSEDED for boundary docs — especially the CLAUDE.md-linked `INTELLIGENCE_ARCHITECTURE`, `DOMAIN_INTELLIGENCE_ARCHITECTURE`, `ENGINE_COS_REFERENCE`, `ENGINE_INTEGRATION_GUIDE`. If retired, update CLAUDE.md in the same change. `docs/WLJ_DOCUMENTATION_INVENTORY.md §6`.
- **DB backup verification (operator):** confirm the latest Railway Postgres snapshot; record its timestamp in `docs/WLJ_MILESTONE_COS_ARCHITECTURE.md`.
- **Production live-check:** confirm `/_health/` + Ops Wall are green after recent deploys.

## Immediate next steps
- If Danny is available: resolve the 14-doc classification (unblocks a CLAUDE.md cleanup).
- Otherwise: start **OPS-1** (highest-leverage coverage gap) or **CC-1** (Tier-1 Current Context summaries).

---

## Housekeeping
- `docs/business/README.md` + `MASTER_PROMPT.md` referenced but missing; stale archive-path refs in `ENGINE_COS_REFERENCE.md` + changelog — fix opportunistically.
- Django is 4.2.27 (CLAUDE.md says 5.x); deliberate 4.2→5.x upgrade is future work.
