# ChatGPT CoS — Phased Rollout Tracker

**Branch:** `feat/chatgpt-cos-transition` · **Baseline:** `a2e94d2b` (main)
**Status legend:** ⬜ Not started · 🟦 In progress · ✅ Done · ⏸️ Blocked

| Phase | Title | Status | Code? | Usable outcome | Commit(s) |
|-------|-------|--------|-------|----------------|-----------|
| **0** | Preserve Architecture Baseline | ✅ Done | No | Baseline committed; branch + trackers created | `a2e94d2b` (main), this branch |
| **1** | Standing Context Foundation | ✅ Done (on branch) | Yes (read-only) | Aware CoS — "how am I doing" from standing context | `<P1>` |
| **2** | Generic Domain Access | ⬜ Not started | Yes (read-only) | Holistic read CoS — any domain via `get_domain_state` | — |
| **3** | ChatGPT Integration Layer | ⬜ Not started | Yes | Natural conversation with dynamic evidence retrieval | — |
| **4** | Decision Surface Reuse | ⬜ Not started | Yes (reuse) | Execution/Risk/Fix answers via existing modes | — |
| **5** | Historical Intelligence | ⬜ Not started | Yes (reuse) | "Have I been here before" — time-based history | — |
| **6** | Action Execution | ⬜ Not started | Yes (reuse) | CoS that acts — tasks/journal/goals/events via UAIO | — |
| **7** | Persistent Conversation Infra | ⬜ Not started | Yes (reuse) | Server-owned execution; survives nav/refresh/disconnect; multi-tab reattach | — |
| **8** | Chat UI Transition | ⬜ Not started | Yes | ChatGPT path behind a flag; legacy live; rollback ready | — |
| **9** | Legacy Beth Retirement | ⬜ Not started | Yes (removal) | Legacy conversational orchestration retired | — |

> **Connection topology (DECIDED): HYBRID.** Conversation orchestration stays inside WLJ; OpenAI is the reasoning engine; tools are internal Python services (StandingContextService, DomainStateService, DecisionService, HistorySearchService, ActionExecutionService) reusing existing providers, designed to be wrapped by authenticated HTTP endpoints later with no logic change. No OAuth/public APIs during initial build.
>
> **Phase 7 reuse target:** the persistent/background-conversation requirement is largely already built — `apps/ai/chat_stream_bus.py` + `run_chat_generation` (Celery) + the resume-by-job_id endpoint (commit `50fb57e5`) already make Beth generation survive navigation. Phase 7 reuses this, it does not rebuild it.

---

## Phase 0 — completion record (this phase)

| Task | Status | Evidence |
|------|--------|----------|
| 1. Commit all architecture documents | ✅ | `a2e94d2b` on `main` (29 docs + changelog), pushed |
| 2. Create dedicated branch | ✅ | `feat/chatgpt-cos-transition` |
| 3. Implementation tracking documentation | ✅ | `IMPLEMENTATION_BACKLOG.md`, this tracker |
| 4. Migration checklist | ✅ | `MIGRATION_CHECKLIST.md` |
| Code changes | ✅ None (Phase 0 is no-code) | — |

---

## Critical-path milestones (from Day-1 rollout sequence, Doc 07/06)
- **Usable holistic read-only CoS** → end of **Phase 2**.
- **CoS that acts / feels real** → end of **Phase 6**.
- **Full conversational cutover** → **Phase 7**, with legacy retained.
- **Legacy retirement** → **Phase 8**, only after validated parity + rollback.

## Update protocol
After each phase: set status, record commit hash(es) + deployment status, and append a short report (Current state / Changes / Blast radius / Verification / Next phase) to `PHASE_REPORTS.md` (created when Phase 1 begins).
