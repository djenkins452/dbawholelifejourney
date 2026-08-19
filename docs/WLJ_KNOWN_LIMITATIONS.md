# WLJ Chief of Staff — Known Limitations

**Status:** CURRENT · Milestone artifact (2026-07-11)
**Purpose:** Honest record of what is NOT finished. The milestone locks the *architecture*, not the *product*. Article IV.1 (results, not intentions) requires we state limitations plainly rather than imply completeness.

---

## This milestone does NOT claim

The product is **not finished**. The milestone establishes that the **fundamental architecture is considered stable and constitutionally protected** — expected to evolve slowly through Constitutional Review, not frozen forever. Future work improves the product within these boundaries.

## Current limitations (tracked, phased)

### Observability (from `WLJ_OPS_WALL_COVERAGE.md`)
- ~~**OPS-1 (highest):** non-engine Celery Beat tasks have no heartbeat → MISSED_RUN never fires.~~ **RESOLVED 2026-07-11** — the generic scheduled-task monitor (`apps/core/ai_observability/scheduled_task_monitor.py`) now covers all 23 non-engine Beat tasks (Goal momentum, background cleanup, image-retention, etc.); MISSED_RUN fires for every scheduled job.
- **OPS-2/3/4:** No monitoring for volumes/artifact storage/DB capacity; `chat` queue backlog not measured; no OpenAI/Model-Interface upstream health card. *Phase: next.*
- **OPS-5–10:** Postgres depth, per-component `owner` field, dead-job detection, confirmation-queue/attachment/dedup/audit-lag health, build-runner observability, direct Beat measurement. *Phase: following.*

### Security hardening (from the 2026-08-19 M2 encryption gate)
- **One key protects three different things.** `OAUTH_TOKEN_ENCRYPTION_KEY` currently encrypts OAuth tokens, the legacy AI-personal-context blob, and Personal Knowledge statements. **Evaluate separating durable personal-data encryption from OAuth-token encryption into distinct keys, with a safe backwards-compatible migration/rotation strategy.** Rotating the current key would make existing values permanently undecryptable, so this needs dual-read + re-encryption planning. Not required for M3. *Phase: following.*
- **`PERSONAL_DATA_ENCRYPTION_KEY` is dead configuration.** It is read via `getattr(settings, ...)` but never declared in `config/settings.py`, so it can never resolve from the environment and the code always falls through to the OAuth key. Setting it in Railway has no effect. Either declare it properly as part of the key-separation work above, or remove the misleading branch. *Phase: following.*

### Test-suite debt (from the 2026-08-19 action-safety audit)
- **`apps.ai.tests.test_action_interface.BoundConfirmationTests` — 2 stale failures.** Verified PRE-EXISTING on three separate occasions by stashing every changed file; they predate the action-integrity work and are unrelated to it. They assert an older confirmation summary shape (`out["confirmation"]["summary"]` containing the action name) that the current Rich-Confirmation `view` architecture builds differently. **Follow-up: reconcile these tests with the certified deterministic confirmation architecture.** Deliberately NOT fixed opportunistically during M2 — nothing in M2 touches that behaviour, and a drive-by change to confirmation tests during a Personal Knowledge milestone is exactly the kind of unscoped edit that hides regressions. *Phase: next.*
- **`apps.ai.tests.test_personal_truth.ProtectedBehaviorsUnregressedTests.test_truth_tool_set_is_the_expected_seven` — 1 stale failure.** The truth-tool set legitimately grew (`get_data_health`, `get_consistency`, `get_change_point`, `get_ranked_entity`, `get_execution_review`) at `019146f1` and later, without this counting test being updated. *Phase: next.*

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
