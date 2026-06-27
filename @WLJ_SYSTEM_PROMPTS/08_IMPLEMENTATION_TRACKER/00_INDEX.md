# ChatGPT CoS — Implementation Tracking

```text
Version:      2.0
Last updated: 2026-06-26
Authority:    Danny Jenkins
Applies to:   ChatGPT CoS transition (implementation status)
Load class:   SPECIALIZED_ON_DEMAND (load for CoS transition work)
```

**Branch:** `feat/chatgpt-cos-transition` · **Architecture baseline:** `a2e94d2b` on `main` (folders 04–07).

This folder tracks the *implementation* of the ChatGPT Chief of Staff transition. The *architecture* is frozen in `../04_DISCOVERY_REFERENCE` … `../07_COS_TOOLS_REFERENCE` and is the authoritative baseline.

**Mission:** build the smallest amount of infrastructure so ChatGPT can be Danny's full-time CoS while WLJ keeps owning truth. **Expose · Serialize · Reuse · Launch · Iterate later.**

## Documents
| Doc | Purpose |
|-----|---------|
| [IMPLEMENTATION_BACKLOG.md](IMPLEMENTATION_BACKLOG.md) | Per-phase work items, what each reuses, acceptance signals, anti-pattern watchlist |
| [PHASED_ROLLOUT_TRACKER.md](PHASED_ROLLOUT_TRACKER.md) | Live status of Phases 0–9 + critical-path milestones (authoritative status) |
| [MIGRATION_CHECKLIST.md](MIGRATION_CHECKLIST.md) | Gated cutover safety checklist (Gates A–F) |

## Where we are — AS BUILT (2026-06-26)

> Verified against git + code: `apps/ai/cos_services/` exists; merge commit
> `43e3bcb3` ("deploy ChatGPT CoS Phases 3-7") is an ancestor of `main` HEAD.
> See `PHASED_ROLLOUT_TRACKER.md` for the per-phase commit table — it is the
> authoritative status; this section summarizes it.

- **Phases 0–7: ✅ complete, merged to `main`, deployed** (per-account, owner-enabled).
  - Phase 0 — Architecture baseline (`a2e94d2b`)
  - Phase 1 — StandingContextService (`d1dcd9b0`) → `apps/ai/cos_services/standing_context.py`
  - Phase 2 — DomainStateService (`f8cc390d`) → `apps/ai/cos_services/domain_state.py`
  - Phase 3 — ChatGPT integration: tool registry + dispatcher (`786204bd`) → `tool_registry.py`, `tool_dispatcher.py`
  - Phase 4 — Decision surface (`9f5b86bf`) → `get_decision` tool (wraps CosDecisionView pipeline)
  - Phase 5 — History search (`5b7b44a4`) → `apps/ai/cos_services/history_search.py`
  - Phase 6 — Action execution (`e68be088`) → `apps/ai/cos_services/action_execution.py`
  - Phase 7 — Tool loop in persistent/background path + distinct CoS header (`a8a406db`)
- **Gating:** The tool loop ships **dark by default**. It activates per-account via
  `UserPreferences.use_chatgpt_cos`, or globally via the
  `WLJ_COS_EVIDENCE_TOOLS_ENABLED` setting (default `False`). Danny = Alpha User #1.
  Toggling the flag off is the zero-deploy, zero-code rollback.
- **Remaining:**
  - **Phase 8 — Full conversational cutover** (⬜ not started): flag ChatGPT path on
    broadly; legacy live; rollback ready. Gated on live OpenAI-key tool-selection
    validation (`python manage.py validate_cos_tools --email <you@example.com>`).
  - **Phase 9 — Legacy Beth retirement** (⬜ not started): retire the legacy
    conversational orchestration **only**; deterministic core untouched.

> The production tool surface is now canonized in
> `../03_CANON_REFERENCE/WLJ COS TOOL & STANDING CONTEXT CONTRACT.md`. The design
> rationale in folders 06–07 is preserved as **as-built design reference**.

## The one rule that governs everything
Before building anything: **prove it already exists, then serialize/reuse it.** No new engines. No parallel pipelines. No Beth rebuild. WLJ owns truth; ChatGPT owns understanding.
