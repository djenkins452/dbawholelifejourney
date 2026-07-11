# WLJ Chief of Staff — Known Limitations

**Status:** CURRENT · Milestone artifact (2026-07-11)
**Purpose:** Honest record of what is NOT finished. The milestone locks the *architecture*, not the *product*. Article IV.1 (results, not intentions) requires we state limitations plainly rather than imply completeness.

---

## This milestone does NOT claim

The product is **not finished**. The milestone establishes that the **fundamental architecture is considered stable and constitutionally protected** — expected to evolve slowly through Constitutional Review, not frozen forever. Future work improves the product within these boundaries.

## Current limitations (tracked, phased)

### Observability (from `WLJ_OPS_WALL_COVERAGE.md`)
- **OPS-1 (highest):** ~10 non-engine Celery Beat tasks have no heartbeat → MISSED_RUN never fires for them. Silent scheduled-job death is possible (affects Goal momentum, background cleanup, image-retention jobs). *Phase: next.*
- **OPS-2/3/4:** No monitoring for volumes/artifact storage/DB capacity; `chat` queue backlog not measured; no OpenAI/Model-Interface upstream health card. *Phase: next.*
- **OPS-5–10:** Postgres depth, per-component `owner` field, dead-job detection, confirmation-queue/attachment/dedup/audit-lag health, build-runner observability, direct Beat measurement. *Phase: following.*

### Current Context adoption (from `WLJ_CURRENT_CONTEXT_HELP_COVERAGE.md`)
- The overview page-summary pattern is live on **one** page (Weight). ~90 overview/list pages and ~8 non-DetailView detail pages still need declarations. The mechanism is complete; adoption is the work. *Phase: next (Tier-1 dashboards) → following (Tier-2).*
- Not yet verified that all ~45 auto-declared DetailViews inherit `UserOwnedModel` (faith/medical/legacy shared-content models may not). *Phase: next spot-check.*

### Help coverage
- finance (single generic prefix), security, sports, owner_finance, blueprint lack per-page context-aware help. *Phase: following.*

### Acceptance baseline (from `WLJ_ACCEPTANCE_BASELINE.md`)
- Scheduled check-ins lack an end-to-end test (scheduler → authored check-in). *Phase: next.*
- Conversation integrity has no standalone durable-transcript contract (covered only inside multimodal wiring). *Phase: next.*
- No cross-cutting duplicate-prevention contract (dedup is strong per-domain). *Phase: after CoS action-registry adoption.*

### Documentation
- 14 docs remain **uncertain** (CURRENT vs HISTORICAL vs SUPERSEDED) pending Danny's judgment — notably the CLAUDE.md-linked `INTELLIGENCE_ARCHITECTURE`, `DOMAIN_INTELLIGENCE_ARCHITECTURE`, `ENGINE_COS_REFERENCE`, `ENGINE_INTEGRATION_GUIDE` (see `WLJ_DOCUMENTATION_INVENTORY.md` §6). Until decided, they are treated as CURRENT-but-stale.
- Stale-path references (archive relocations) and 2 missing `docs/business/` files are housekeeping, not blockers.

### Environment note
- CLAUDE.md states "Django 5.x" but the runtime is **Django 4.2.27**. Some deprecated aliases (now cleaned) still warn. A deliberate 4.2→5.x upgrade is future work with its own testing.

## Design boundaries (intentional, not defects)

- **WLJ has no reasoning engine.** By design (Constitution I.2). If the model reasons poorly, the fix is better truth/context/tools — not a WLJ capability.
- **WLJ emits facts, not verdicts.** Interpretation is the model's. This is intentional even when a verdict would look "smarter."
- **No prod CLI/SSH.** One-off prod changes go through `RunPython` migrations only. This is a deliberate safety constraint.
- **Learning is default-deny.** The reflection layer observes; it never learns around a deterministic defect (it surfaces an EIO instead).

## How limitations get closed

Each item above carries a phase and lives in the relevant coverage doc. They are closed as ordinary in-Constitution work — none requires a Constitutional Review, because none changes the architecture.
